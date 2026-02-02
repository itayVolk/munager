#Requires AutoHotkey v2.1-alpha
#DllLoad Ws2_32

class Socket {

    __New(socket) {
        this.socket := socket
        this.onDataListeners := []
        this.timeout_BoundFunc := () {
            Critical
            ;this is not a Data recv, this is to check if the client is still connected
            DllCall('ws2_32\recv','ptr',socket,'ptr',0,'int',0,'int',0)
            WSALastError:=DllCall('ws2_32\WSAGetLastError')
            switch WSALastError {
                case 10054,10053: ;ECONNRESET, ECONNABORTED
                    this.destroy()
                case 10035: ;EWOULDBLOCK
                    SetTimer(this.timeout_BoundFunc, -5000)
                default:
                    throw WSALastError
            }
        }
        SetTimer(this.timeout_BoundFunc, -5000)
    }

    on(event,listener) {
        switch event {
            case "data":
                this.onDataListeners.Push(listener)
        }
    }

    write(data) {
        if (Type(data) = "String") {
            data:=net.utf8(data)
        }
        DllCall('ws2_32\send','ptr',this.socket,'ptr',data,'int',data.Size,'int',0)
    }

    destroy() {
        net.clients_by_socket.Delete(this.socket) ;Release
        DllCall('ws2_32\closesocket','ptr',this.socket)
        this.onDataListeners.Length := 0 ;Release
        SetTimer(this.timeout_BoundFunc, 0)
        this.timeout_BoundFunc := 0 ;Release
    }

}

class net {
    static WM_SOCKET := DllCall('RegisterWindowMessage','str','WM_AHK_SOCKET','uint')
    static _init := (OnMessage(net.WM_SOCKET,net.On_WM_SOCKET.Bind(Server)),DllCall('ws2_32\WSAStartup','ushort',0x0202,'ptr',Buffer(A_PtrSize*2+0x188)))
    static servers_by_socket := Map()
    static clients_by_socket := Map()

    static On_WM_SOCKET(wParam,lParam,Msg,hWnd) {
        Critical

        lParam &= 0xffffffff ;long

        switch lParam {
            case 8:
                client_socket:=DllCall("Ws2_32\accept","Ptr",wParam,"Ptr",0,"Ptr",0,"Ptr")
                client := Socket(client_socket)
                net.clients_by_socket[client_socket] := client
                net.servers_by_socket[wParam].connectionListener.Call(client)
            case 1:
                client:=net.clients_by_socket[wParam]
                SetTimer(client.timeout_BoundFunc, -5000)

                DllCall('ws2_32\ioctlsocket','ptr',wParam,'uint',0x4004667F,'uint*',&argp := 0)
                buf := Buffer(argp)
                DllCall('ws2_32\recv','ptr',wParam,'ptr',buf,'int',buf.Size,'int',0)
                for listener in client.onDataListeners {
                    listener.Call(buf)
                }
            ; case 0x20:
            ;     ok:=DllCall('ws2_32\closesocket','ptr',wParam)
            ;     ok:=0
        }
    }

    static utf8(text) {
        buf:=Buffer(StrPut(text,"UTF-8")-1) ;we don't want the null-terminator
        StrPut(text,buf,"UTF-8") ;A null-terminator is written and included in the return value only when there is sufficient space
        return buf
    }

    static sockaddr_in(port,host) {
        pHints:=Buffer(A_PtrSize*4+0x10,0)
        DllCall("Ws2_32\GetAddrInfoW","WStr",host,"WStr",port,"Ptr",pHints,"Ptr*",&ppResult:=0)
        ai_addrlen:=NumGet(ppResult,0x10,"Ptr")
        ai_addr:=NumGet(ppResult,A_PtrSize*2+0x10,"Ptr")
        return ({
            Size:ai_addrlen,
            Ptr:ai_addr,
            __Delete: (this) {
                DllCall("Ws2_32\FreeAddrInfoW","Ptr",ppResult)
            }
        })
    }
}

class Server {

    __New(connectionListener) {
        this.connectionListener:=connectionListener
    }
    listen(port,host) {
        server_socket := DllCall("Ws2_32\socket","Int",2,"Int",1,"Int",6,"Ptr")

        sockaddr_in := net.sockaddr_in(port,host)
        DllCall("Ws2_32\bind","Ptr",server_socket,"Ptr",sockaddr_in,"Int",sockaddr_in.Size)

        DllCall("Ws2_32\WSAAsyncSelect","UInt",server_socket,"Ptr",A_ScriptHwnd,"UInt",net.WM_SOCKET,"Int",0x29)
        net.servers_by_socket[server_socket] := this
        DllCall("Ws2_32\listen","Ptr",server_socket,"Int",200)
    }

}

createServer(connectionListener) {
    return Server(connectionListener)
}

connect(port,host) {
    client_socket := DllCall("Ws2_32\socket","Int",2,"Int",1,"Int",6,"Ptr")
    _socket := Socket(client_socket)

    DllCall("Ws2_32\WSAAsyncSelect","UInt",client_socket,"Ptr",A_ScriptHwnd,"UInt",net.WM_SOCKET,"Int",0x21)
    net.clients_by_socket[client_socket] := _socket

    sockaddr_in := net.sockaddr_in(port,host)
    DllCall('ws2_32\connect','ptr',client_socket,'ptr',sockaddr_in,'Int',sockaddr_in.Size)
    return _socket
}

class Length_Socket extends Socket {

    static Call(socket) {
        socket.DefineProp("write",{ call: Length_Socket.Prototype.write })
        socket.DefineProp("on",{ call: Length_Socket.Prototype.on })
        Length_Socket.Prototype.__New.Call(socket)
        return socket
    }

    __New() {
        this.accumulatedSize := 0
        this.waitForSize := 4
        this.waitForType := "length"
        this.toConcat := []
    }

    write(data) {
        if (Type(data) = "String") {
            data:=net.utf8(data)
        }
        NumPut("Uint",data.Size,data_length:=Buffer(4))
        DllCall('ws2_32\send','ptr',this.socket,'ptr',data_length,'int',data_length.Size,'int',0)
        DllCall('ws2_32\send','ptr',this.socket,'ptr',data,'int',data.Size,'int',0)
    }

    on(event,listener) {
        switch event {
            case "data":
                this.onDataListeners.Push((data) {
                    this.accumulatedSize += data.Size
                    this.toConcat.Push(data)
                    while (this.accumulatedSize >= this.waitForSize) {
                        ;we need up until the last
                        concatenated:=Length_Socket.concat(this.toConcat,this.accumulatedSize)
                        switch this.waitForType {
                            case "length":
                                this.toConcat:=[Length_Socket.subarray(concatenated,4)]
                                this.accumulatedSize-=4
                                this.waitForSize:=NumGet(concatenated,"Uint")
                                this.waitForType:="data"
                            case "data":
                                message := Length_Socket.subarray(concatenated,0,this.waitForSize)
                                this.toConcat:=[Length_Socket.subarray(concatenated,this.waitForSize)]
                                this.accumulatedSize-=this.waitForSize
                                this.waitForSize:=4
                                this.waitForType:="length"
                                listener(message)
                        }
                    }
                })
        }
    }

    static concat(toConcat, accumulatedSize) {
        if (toConcat.length == 1) {
            return toConcat[1]
        }
        concatenated := Buffer(accumulatedSize)
        dest:=concatenated.Ptr
        for v in toConcat {
            DllCall("ntdll\memcpy","Ptr",dest,"Ptr",v,"Ptr",v.Size)
            dest+=v.Size
        }
        return concatenated
    }

    static subarray(buf,start,end:=buf.Size) {
        return {buf:buf,Ptr:buf.Ptr+start,Size:end-start}
    }
}