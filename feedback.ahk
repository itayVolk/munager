#Include net.ahk
#Include JSON.ahk
#Include class.ahk
#SingleInstance Force

ip := InputBox("What is the server's IP address? Click cancel to run with a single computer.")
if (ip.Result == "OK") {
    ask := 1
    ip := ip.Value
    Server((socket) {
        socket := Length_Socket(socket)
        socket.on("data",(data) {
            global countries
            data := StrGet(data,"UTF-8")
            if (data == "update")
                client.write("start")
            else {
                if (SubStr(data, 1, 1) == "{") {
                    obj := JSON.Load(data)
                    countries[obj["country"]].unmod := obj["unmod"]
                    countries[obj["country"]].mod := obj["mod"]
                } else {
                    val := StrSplit(data, "|")
                    if (val.Length > 1)
                        countries[val[1]].unmod := val[2]
                    else {
                        val := StrSplit(data, "/")
                        if (val.Length > 1)
                            countries[val[1]].mod.Push(val[2])
                        else
                            mod(data, ask)
                    }
                }
            }
        })
    }).listen(8000,ip)

    client := Length_Socket(connect(8080,ip))
    client.on("data",(data) {
        data := StrGet(data,"UTF-8")
        global countries, select
        if (IsSet(select)) {
            select.Destroy()
        }
        countries := JSON.Load(data)
        for country in countries {
            countries[country].unmod := countries[country]["unmod"]
            countries[country].mod := countries[country]["mod"]
            countries[country].stat := countries[country]["stat"]
        }
        primary()
    })
    client.write("start")
} else {
    ip := ""
    fileFinder()
    primary()
    OnExit((*) => save(, false))
}

write(country, unmod, mod) {
    if (IsSet(client)) {
        client.write(JSON.Dump({country:country, unmod:unmod, mod:mod}))
    }
}

mod(country, ask := 0) {
    update() {
        display.Hide()
        if (Trim(display["notes"].Text, " `t`n`r")) {
            cur.%"mod" (ip?"":"_feed")%.Push(display["score"].Value ":" Trim(display["notes"].text, " `t`n`r"))
        }
        write(country, cur.unmod, cur.mod)
        select.show()
    }

    if (!ask or (ask == 1 and MsgBox("Do you want to give feedback on " country "'s speech?",,0x4) == "Yes")) {
        select.Hide()
        cur := countries[country]
        display := Munager("Speech feedback",,30,1,(*) => update())
        display.AddText("w500 Center", country)
        display.norm()
        display.AddEdit("wp")
        display.AddUpDown("Range1-5 vscore")
        display.AddEdit("wp r4 VScroll vnotes")
        display.show()
    }
}

primary() {
    show() {
        update() {
            display.Hide()
            if (Trim(display["notes"].Text, " `t`n`r")) {
                cur.%"unmod" (ip?"":"_feed")% := display["score"].Value ":" Trim(display["notes"].text, " `t`n`r")
            } else {
                cur.%"unmod" (ip?"":"_feed")% := ""
            }

            i := 1
            j := 1
            while (i <= cur.%"mod" (ip?"":"_feed")%.Length) {
                if (Trim(display["notes" j].Text, " `t`n`r")) {
                    cur.%"mod" (ip?"":"_feed")%[i++] := display["score" j].Value ":" Trim(display["notes" j].text, " `t`n`r")
                } else {
                    cur.%"mod" (ip?"":"_feed")%.RemoveAt(i)
                }
                j++
            }
            write(select["del"].Text, cur.unmod, cur.mod)
            select.show()
        }

        select.Hide()
        cur := countries[select["del"].Text]
        display := Munager("Feedback screen",,30,1,(*) => update())
        display.AddText("w500 Center", select["del"].Text)
        display.norm()
        display.AddText("wp", "UNMOD:")
        display.AddEdit("wp")
        display.AddUpDown("Range1-5 vscore", SubStr(cur.%"unmod" (ip?"":"_feed")%, 1, 1))
        display.AddEdit("wp r4 VScroll vnotes", SubStr(cur.%"unmod" (ip?"":"_feed")%, 3))
        if (!ip) {
            display.AddText("wp", "Server UNMOD:")
            display.AddEdit("wp Disabled")
            display.AddUpDown("Range1-5 Disabled", SubStr(cur.unmod, 1, 1))
            display.AddEdit("wp r4 VScroll Disabled", SubStr(cur.unmod, 3))
        } 
        if (cur.%"mod" (ip?"":"_feed")%) {
            display.AddText("wp", "MOD feedback:")
            for i, speech in cur.%"mod" (ip?"":"_feed")% {
                display.AddText("wp", "Speech number " i ":")
                display.AddEdit("wp")
                display.AddUpDown("Range1-5 vscore" i, SubStr(speech, 1, 1))
                display.AddEdit("wp r4 VScroll vnotes" i, SubStr(speech, 3))
            }
        }
        if (!ip && cur.mod) {
            display.AddText("wp", "Server MOD feedback:")
            for i, speech in cur.mod {
                display.AddText("wp", "Speech number " i ":")
                display.AddEdit("wp Disabled")
                display.AddUpDown("Range1-5 Disabled" i, SubStr(speech, 1, 1))
                display.AddEdit("wp r4 VScroll Disabled" i, SubStr(speech, 3))
            }
        }
        display.show()
    }

    awards() {
        select.Hide()
        display := Munager("Awards info",,10,,(*) => select.show())
        arr := []
        for country, val in countries {
            unmod := val.unmod?Integer(StrSplit(val.unmod, ":")[1]):0 + val.unmod_feed?Integer(StrSplit(val.unmod_feed, ":")[1]):0
            tot := 0
            square := 0
            for speech in val.mod {
                temp := Integer(StrSplit(speech, ":")[1])
                tot += temp
                square += temp * temp
            }
            for speech in val.mod_feed {
                temp := Integer(StrSplit(speech, ":")[1])
                tot += temp
                square += temp * temp
            }
            l := val.mod.Length?val.mod.Length:0 + val.mod_feed.Length?val.mod_feed.Length:0
            avg := l?tot/l:0
            arr.Push(["", country, Round(avg+unmod, 2), Round(avg, 2), Round(unmod, 2), Round(Abs(avg-unmod), 2), l?Round(square/l - avg*avg, 2):100])
        }
        display.AddListView("w500 Grid", ["Country", "Total", "Speech", "UNMOD", "Diff", "Speech dev"], arr)
        display.show()
    }

    global ask, select := Munager("Feedback selector",,30,1,(*) => ExitApp())
    arr := []
    for country, val in countries {
        if (val.stat) {
            arr.Push(country)
        }
    }
    select.AddDDL("w500 sort vdel", arr)
    select.AddButton("wp", "Speech", (*) => mod(select["del"].Text))
    select.AddButton("wp", "Show feedback", (*) => show())
    select.AddButton("wp", "Awards", (*) => awards())
    if (ip) {
        select.AddText("wp", "Incoming speeches ")
        select.AddListBox("r3 wp Choose" (ask+2), ["are ignored", "take control", "prompt you"]).OnEvent("Change", (ctrl, *) => ask := ctrl.Value-2)
    } else if (FileExist(settingsRead("file") "\..\.git")){
        select.AddButton("wp", "Save feedback", (*) => save(,false))
        select.AddButton("wp", "Download from server", (*) => RunWait("git pull", settingsRead("file") "\.."))
    }
    select.show()
}