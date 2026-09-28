import socket
import struct
import threading
import queue

# Cross-thread callback dispatch. The GUI installs a Tk `after` pump that
# drains this queue on the main thread.
_dispatch = queue.Queue()


def pump():
    """Call from the Tk main loop to run queued socket callbacks safely."""
    while True:
        try:
            fn = _dispatch.get_nowait()
        except queue.Empty:
            break
        try:
            fn()
        except Exception as e:
            print("callback error:", e)


def _later(fn):
    _dispatch.put(fn)


class LengthSocket:
    """Length-prefixed message socket, mirroring net.ahk Length_Socket."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._listeners = []
        self._closed = False
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()

    def on(self, event, listener):
        if event == "data":
            self._listeners.append(listener)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            self.sock.sendall(struct.pack("<I", len(data)) + data)
        except OSError:
            self.destroy()

    def _reader(self):
        buf = b""
        want = 4
        state = "length"
        try:
            while not self._closed:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= want:
                    if state == "length":
                        want = struct.unpack("<I", buf[:4])[0]
                        buf = buf[4:]
                        state = "data"
                    else:
                        msg = buf[:want]
                        buf = buf[want:]
                        want = 4
                        state = "length"
                        for l in list(self._listeners):
                            _later(lambda l=l, m=msg: l(m))
        except OSError:
            pass
        finally:
            self.destroy()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Server:
    def __init__(self, connection_listener):
        self._cb = connection_listener

    def listen(self, port, host):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, int(port)))
        srv.listen(200)

        def accept_loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    break
                ls = LengthSocket(conn)
                _later(lambda ls=ls: self._cb(ls))

        threading.Thread(target=accept_loop, daemon=True).start()
        return self


def connect(port, host):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, int(port)))
    return LengthSocket(sock)


def local_ip():
    """Best-effort primary IPv4, mirroring SysGetIPAddresses()[1]."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"