#Include net.ahk
#Include JSON.ahk
#Include class.ahk
#SingleInstance Force
single := MsgBox("Are you running on a single computer?",,0x4) == "Yes"
if (!single) {
    if (MsgBox("Your IP address is " . SysGetIPAddresses()[1] " copy to clipboard? ",,0x4)=="Yes") {
        A_Clipboard := SysGetIPAddresses()[1]
    }
    Server((socket) {
        global countries
        socket := Length_Socket(socket)
        socket.on("data",(data) {
            val := StrGet(data,"UTF-8")
            if (val == "start") {
                socket.write(JSON.Dump(countries))
                global client := Length_Socket(connect(8000,SysGetIPAddresses()[1]))
            } else {
                obj := JSON.Load(val)
                countries[obj["country"]].unmod := obj["unmod"]
                countries[obj["country"]].mod := obj["mod"]
            }
        })
    }).listen(8080,SysGetIPAddresses()[1])
}

list := false
countries := {}
fileFinder()

chair := Munager("Chair screen",,40,,(*) => ExitApp())
chair.AddButton("Center w500", "Roll call", (*) => call())
chair.AddButton("Center wp", "Motions", (*) => motion())
chair.AddButton("Center wp", "Roll call vote", (*) => vote())
chair.AddButton("Center wp", "Show feedback", (*) => feedback())
chair.AddButton("Center wp", "Awards", (*) => awards())
if (single) {
    chair.AddButton("Center wp", "Save", (*) => save())
    chair.AddButton("Center wp", "Sync secondary", (*) => RunWait("git pull", settingsRead("file") "\.."))
}
chair.AddButton("Center wp", "Settings", (*) => settings())
chair.Show()

OnExit((*) => save(single))

feedback() {
    global chair
    chosen() {
        update() {
            display.Hide()
            if (Trim(display["notes"].Text, " `t`n`r")) {
                cur.unmod := display["score"].Value ":" Trim(display["notes"].text, " `t`n`r")
            } else {
                cur.unmod := ""
            }

            i := 1
            j := 1
            while (i <= cur.mod.Length) {
                if (Trim(display["notes" j].Text, " `t`n`r")) {
                    cur.mod[i++] := display["score" j].Value ":" Trim(display["notes" j].text, " `t`n`r")
                } else {
                    cur.mod.RemoveAt(i)
                }
                j++
            }
            write(JSON.Dump({country:select["del"].Text, unmod:cur.unmod, mod:cur.mod}))
            select.show()
        }
        add() {
            update() {
                speech.Hide()
                if (Trim(speech["notes"].Text, " `t`n`r")) {
                    new := speech["score"].Value ":" Trim(speech["notes"].Text, " `t`n`r")
                    cur.mod.Push(new)
                    write(select["del"].Text "/" new)
                }
                chosen()
            }

            display.Hide()
            speech := Munager("Speech feedback",,30,1,(*) => update())
            speech.AddText("w500 Center", select["del"].Text)
            speech.norm()
            speech.AddEdit("wp")
            speech.AddUpDown("Range1-5 vscore")
            speech.AddEdit("wp r4 VScroll vnotes")
            speech.show()
        }
        

        select.Hide()
        cur := countries[select["del"].Text]
        display := Munager("Feedback screen",,30,1,(*) => update())
        static test := Munager("tester",,30,1).AddEdit("w500").Gui
        display.AddText("w500 Center", select["del"].Text)
        display.norm()
        display.AddText("wp", "UNMOD:")
        display.AddEdit("wp")
        display.AddUpDown("Range1-5 vscore", SubStr(cur.unmod, 1, 1))
        display.AddEdit("wp r4 VScroll vnotes", SubStr(cur.unmod, 3))
        if (cur.mod) {
            display.AddText("wp", "MOD feedback:")
            for i, speech in cur.mod {
                display.AddText("wp", "Speech number " i ":")
                display.AddEdit("wp")
                display.AddUpDown("Range1-5 vscore" i, SubStr(speech, 1, 1))
                display.AddEdit("wp r" Min(EditGetLineCount(test.AddEdit("wp", SubStr(speech, 3)).Hwnd, test.Hwnd), 4) " vnotes" i, SubStr(speech, 3))
            }
        }
        display.AddButton("wp", "Add speech", (*) => add())
        display.show()
    }

    chair.Hide()
    select := Munager("Feedback selector",,30,1,(*) => chair.show())
    arr := []
    for country, val in countries {
        if (val.stat) {
            arr.Push(country)
        }
    }
    select.AddDDL("w500 sort vdel", arr)
    select.AddButton("wp", "Select", (*) => chosen())
    select.show()
}

awards() {
    global chair

    chair.Hide()
    awards := Munager("Awards info",,10,,(*) => chair.show())
    arr := []
    for country, val in countries {
        unmod := (val.unmod?Integer(StrSplit(val.unmod, ":")[1]):0) + (val.unmod_feed?Integer(StrSplit(val.unmod_feed, ":")[1]):0)
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
        l := (val.mod.Length?val.mod.Length:0) + (val.mod_feed.Length?val.mod_feed.Length:0)
        avg := l?tot/l:0
        arr.Push(["", country, Round(avg+unmod, 2), Round(avg, 2), Round(unmod, 2), Round(Abs(avg-unmod), 2), l?Round(square/l - avg*avg, 2):100])
    }
    awards.AddListView("w500 Grid", ["Country", "Total", "Speech", "UNMOD", "Diff", "Speech dev"], arr)
    awards.show()
}

call() {
    global chair
    chair.Hide()
    static control := "", show := ""

    update(ctrl, *) {
        show[ctrl.Name].Text := ctrl.Text := (ctrl.Text := !ctrl.Text) ? Chr(0x2713) : ""
        if (InStr(ctrl.Name, "v") == 1 && ctrl.Text) {
            name := "p" SubStr(ctrl.Name, 2)
            show[name].Text := control[name].Text := ctrl.Text
        } else if (InStr(ctrl.Name, "p") == 1 && !ctrl.Text) {
            name := "v" SubStr(ctrl.Name, 2)
            if (control[name].Enabled) {
                show[name].Text := control[name].Text := ctrl.Text
            }
        }
    }

    submit() {
        pres := 0
        vote := 0
        for country, val in countries {
            dash := StrReplace(country, " ", "-")
            pres++
            if (control["v" dash].Text) {
                val.stat := "V"
                vote++
            } else if (control["p" dash].Text) {
                val.stat := "P"
                if (val.type != "O") {
                    vote++
                }
            } else {
                pres--
            }
        }

        MsgBox("Regular majority: " Floor(pres/2+1) "`nSpecial majority: " Ceil(pres*2/3) "`nOperative threshold: " Floor(vote/2+1))
        write("update")
        show.Hide()
        control.Hide()
        chair.show()
    }

    if (!control) {
        control := Munager("Roll call control", 1,,1,(*) => submit())
        control.AddText("xm w500", "Country")
        control.AddText("yp w250", "Present")
        control.AddText("yp", "Voting")
        control.norm()

        show := Munager("Roll call show",,50,1)
        show.AddText("xm w500", "Country")
        show.AddText("yp w250", "Present")
        show.AddText("yp", "Voting")
        show.norm()

        for country, vals in countries {
            dash := StrReplace(country, " ", "-")
            control.AddText("xm w500", country)
            control.AddButton("yp w250 vp" dash, vals.stat ? Chr(0x2713) : "", update)
            control.AddButton("yp w250" (vals.type ? " Disabled" : "") " vv" dash, vals.stat == "V" ? Chr(0x2713) : "", update)
            show.AddText("xm w500", country)
            show.AddButton("yp w250 vp" dash, vals.stat ? Chr(0x2713) : "")
            show.AddButton("yp w250 vv" dash, vals.type ? vals.type : (vals.stat == "V" ? Chr(0x2713) : ""))
        }

        control.AddButton("w1050 xm", "Submit", (*) => submit())
    }
    show.show(-1)
    control.show()
    global guis := [show.Hwnd]
}

settings() {
    static descriptions := Map("file", "save file",
                                "time", "default motion speaking time",
                                "tip", "whether you used a timer",
                                "veto", "#countries required for veto",
                                "list", "speaker list(1)/round robin(0)",
                                "listT", "whether you heard of ^l")
    update(list, item, select) {
        if (select) {
            if (item == 1) {
                file := FileSelect(1,,,"CSV File (*.csv)")
                settingsWrite(list.GetText(item, 1), file)
                SplitPath(file, &dis)
                list.Modify(item,,,,dis)
            } else {
                obj := InputBox("What is the new value (m for minutes if time)?")
                if (obj.Result == "OK") {
                    if (!RegExMatch(obj.Value, "^\d+$")) {
                        switch item {
                            case 2: obj.Value := StrSplit(formatSecond(obj.Value), ":")
                                    obj.Value := obj.Value[1]*60 + obj.Value[2]
                            case 3: obj.Value := (obj.Value = "yes")
                        }
                    }
                    settingsWrite(list.GetText(item, 1), obj.Value)
                    nice := obj.Value
                    switch item {
                        case 2: nice := formatSecond(nice)
                        case 3: nice := nice ? "yes" : "no"
                    }
                    list.Modify(item,,,,nice)
                }
            }
        }
    }

    if (!FileExist("munager.ini")) {
        FileOpen("munager.ini", "rw")
    }
    screen := Munager("Settings",,, 1, (*) => chair.show())
    list := screen.AddListView("-LV0x10 NoSort NoSortHdr Grid", ["Name", "Description", "Value"], [], update)
    for setting, description in descriptions {
        nice := settingsRead(setting)
        switch A_Index {
            case 1: SplitPath(nice, &nice)
            case 2: nice := formatSecond(nice)
            case 3: nice := nice ? "yes" : "no"
        }
        list.Insert(2147483647,,setting, description, nice)
    }
    list.ModifyCol()
    list.ModifyCol(1, "AutoHdr")
    screen.show()
}

formatSecond(s) {
    if s is String {
        if (InStr(s, ":")) {
            return StrReplace(s, " ")
        } else if (InStr(s, "m")) {
            return StrReplace(s, "m", ":00")
        } else {
            return formatSecond(Integer(s))
        }
    }
    if s < 60 {
        return String(s)
    }
    return String(Floor(s/60)) ":" Format("{1:+02}", Mod(s, 60))
}

class MotionDisplay extends Munager {
    static Call(motions := []) {
        show := super("Motion proposal display",,,1)
        show.AddText("w500", "Proposer")
        show.AddText("yp", "Motion")
        show.norm()
        show.motions := motions
        return show
    }
}

write(text) {
    if (!single) {
        client.write(text)
    }
}

if (!settingsRead("listT")) {
    MsgBox("You can use control+l to toggle round robin/speakers list and to add countries to the speakers list")
    settingsWrite("listT", true)
}
^l:: {
    ins(ctrl, *) {
        global speakersList
        speakersList.Push(ctrl.gui["add"].Text)
        ctrl.gui["add"].Text := ""
    }

    control := Munager("Add speakers",,30, 1)
    arr := []
    for country, val in countries {
        if (val.stat) {
            arr.Push(country)
        }
    }
    mode := control.AddText("w500 vmode center", "Currently on: " (settingsRead("list")?"Speaker List":"Round Robin"))
    control.AddButton("wp center", "Toggle", (*) => mode.Text := "Currently on: " (settingsWrite("list", !settingsRead("list"))?"Speaker List":"Round Robin"))
    control.AddDDL("wp sort vadd", arr)
    control.AddButton("wp center", "Add speaker", ins)
    control.show()
}

speakersList := []
motion() {
    global chair
    tip() {
        if (!settingsRead("tip")) {
            MsgBox("Press middle mouse button to start/stop timer.`nRight click to reset timer.")
            settingsWrite("tip", true)
        }
    }

    toggle(bound, *) {
        global stat
        SetTimer(bound, stat := !stat ? 1000 : 0)
    }

    close(gui, *) {
        Hotkey("MButton", "Off")
        Hotkey("RButton", "Off")
        chair.show()
    }

    adjustSingle(guiObjs) {
        for guiObj in guiObjs {
            guiObj["prog"].Value--
            if (guiObj["prog"].Value <= guiObj["prog"].Range/3) {
                guiObj["prog"].Opt("CRed")
            } else if (guiObj["prog"].Value <= guiObj["prog"].Range/2) {
                guiObj["prog"].Opt("CYellow")
            } else if (guiObj["prog"].Value <= guiObj["prog"].Range/3*2) {
                guiObj["prog"].Opt("CGreen")
            }
            guiObj["left"].Text := "Left: " formatSecond(guiObj["prog"].Value)
            if (!guiObj["prog"].Value) {
                SetTimer(, 0)
            }
        }
    }

    resetSingle(guiObjs, bound, *) {
        SetTimer(bound, 0)
        global stat := 0
        for guiObj in guiObjs {
            guiObj["left"].Text := "Left: " formatSecond(guiObj["prog"].Value := guiObj["prog"].Range)
            guiObj["prog"].Opt("cDefault")
        }
    }

    default(veto, ctrl, *) {
        remove(list, item, select) {
            if (select) {
                list.Delete(item)
                list.Gui.other["next"].Delete(item)
                if (settingsRead("list")) {
                    speakersList.RemoveAt(item)
                }
            }
        }

        ins(ctrl, *) {
            ctrl.Gui["next"].Insert(2147483647,, ctrl.Gui["add"].text)
            ctrl.Gui.other["next"].Insert(2147483647,, ctrl.Gui["add"].text)
            global speakersList
            speakersList.Push(ctrl.Gui["add"].text) 
        }

        submit(bound, gui, *) {
            done(true, bound, gui["cur"])
            close(gui)
        }

        done(last, bound, ctrl, *) {
            SetTimer(bound, 0)
            global stat := 0
            cur := ctrl.Gui["cur"].Text
            if (Trim(ctrl.Gui["notes"].Text, " `t`n`r") and cur != "No current speaker") {
                new := ctrl.Gui["score"].Value ":" Trim(ctrl.Gui["notes"].Text, " `t`n`r")
                countries[cur].mod.Push(new)
                write(cur "/" new)
            }
            ctrl.Gui["score"].Value := 1
            ctrl.Gui["notes"].Text := ""
            ctrl.Gui.other["left"].Text := ctrl.Gui["left"].Text := "Left:" formatSecond(time)
            ctrl.Gui.other["prog"].Value := ctrl.Gui["prog"].Value := time
            ctrl.Gui["prog"].Opt("cDefault")
            ctrl.Gui.other["prog"].Opt("cDefault")
            if ctrl.Gui["next"].GetCount() {
                if (!last) {
                    write(ctrl.Gui.other["cur"].text := ctrl.Gui["cur"].text := ctrl.Gui["next"].GetText(1))
                    ctrl.Gui["next"].Delete(1)
                    ctrl.Gui.other["next"].Delete(1)
                    if (settingsRead("list")) {
                        speakersList.Pop()
                    }
                }
            }
        }

        time := 0
        if (veto) {
            i := 1
            while (show.motions[i].count != SubStr(ctrl.name, 5)) {
                i++
            }
            obj := show.motions[i]
            if (InStr(StrSplit(obj.text, " ")[1], ":")) {
                split := StrSplit(StrSplit(obj.text, " ")[1], ":")
                time := split[1]*60 + split[2]
            } else {
                time := Integer(StrSplit(obj.text, " ")[1])
            }
        } else {
            time := settingsRead("time")
            if (time) {
                time := Integer(time)
            } else {
                time := formatSecond(InputBox("What is the speaking time?").Value)
                if (InStr(time, ":")) {
                    split := StrSplit(time, ":")
                    time := split[1]*60 + split[2]
                } else {
                    time := Integer(time)
                }
                settingsWrite("time", time)
            }
        }
        

        show.Destroy()
        control.Destroy()
        
        display := Munager((settingsRead("list")?"Speakers list":"Round robin") "display",, 30, 1, close)
        control := Munager("Speech feedback",,30, 1)
        control.other := display

        bound := adjustSingle.Bind([control, display])
        control.onClose(submit.Bind(bound))

        display.AddText("w500 center vleft", "Left: " formatSecond(time))
        display.AddProgress("wp vprog Smooth cDefault Range0-" time, time).Range := time
        display.AddText("wp center vcur", "No current speaker")
        dView := display.AddListView("wp -hdr vnext r5 Grid Center", ["Country"])

        control.AddText("w500 center vleft", "Left: " formatSecond(time))
        control.AddProgress("wp vprog Smooth cDefault Range0-" time, time).Range := time
        control.AddText("wp center vcur", "No current speaker")
        control.AddEdit("wp")
        control.AddUpDown("Range1-5 vscore")
        control.AddEdit("wp r4 VScroll vnotes")
        if (settingsRead("list")) {
            control.AddDDL("wp sort vadd", arr)
            control.AddButton("wp center", "Add speaker", ins)
        }
        cView := control.AddListView("wp -hdr vnext r5 Grid Center", ["Country"], [], remove)
        control.AddButton("wp center", "Next speaker", done.Bind(false, bound))

        if (settingsRead("list")) {
            for (val in speakersList) {
                dView.Insert(dView.GetCount()+1,,val)
                cView.Insert(cView.GetCount()+1,,val)
            }
            if (speakersList.Length >= 1) {
                speakersList.Pop()
            }
        } else {
            temp := arr.Clone()
            while (temp.Length) {
                pos := Random(1,dView.GetCount()+1)
                item := temp.Pop()
                if (!veto || countries[item].type == 'V') {
                    dView.Insert(pos,,item)
                    cView.Insert(pos,,item)
                }
            }
        }

        if (dView.GetCount() >= 1) {
            write(control["cur"].text := display["cur"].text := dView.GetText(1))
            dView.Delete(1)
            cView.Delete(1)
        }

        display.show(-1)
        control.show()

        global stat := 0
        Hotkey("MButton", toggle.Bind(bound), "On")
        Hotkey("RButton", resetSingle.Bind([control, display], bound), "On")
        tip()
    }

    chair.Hide()

    control := Munager("Motion proposal control",,30,1,(*) => chair.show())
    control.AddDDL("w1100 vtype", ["Text", "Timer", "Speaking", "Change time/veto"])
    arr := []
    for country, val in countries {
        if (val.stat) {
            arr.Push(country)
        }
    }
    control.AddDDL("wp sort vprop", arr)
    control.AddButton("wp", "Add motion", (*) => add())
    control.AddButton("wp", settingsRead("list")?"Speakers list":"Round robin", default.Bind(false))
    control.AddText("xm yp+100 w300", "Proposer")
    control.AddText("yp w417", "Motion")
    control.AddText("yp w97", "Prio")
    control.AddText("yp wp", "Pass")
    control.AddText("yp wp", "Fail")
    control.norm()
    control.count := 0
    show := MotionDisplay()
    show.Show(1)
    control.show()
    global guis := [show.Hwnd]

    add() {
        if (!control["type"].Value) {
            MsgBox("Please select a type.",,"IconX")
            return
        }

        text := ""
        if (control["type"].Text != "Change time/veto") {
            res := InputBox("What is the motion/text?")
            if (res.Result != "OK") {
                return
            }
            text := res.Value
        }
        
        time := 0
        veto := false
        if (control["type"].Text == "Change time/veto") {
            if (!settingsRead("list")) {
                veto := MsgBox("Do you want just the veto holders to speak?",,0x4) == "Yes"
            }
            formatted := formatSecond(InputBox("What is the speaking time? (put m for minutes)").Value)
            if (InStr(formatted, ":")) {
                split := StrSplit(formatted, ":")
                time := split[1]*60 + split[2]
            } else {
                time := Integer(formatted)
            }
            if (!veto) {
                settingsWrite("time", time)
            }
            text := formatted . " " (veto?"Veto ":"") . (settingsRead("list")?"Speakers list":"Round Robin")
        } else if (control["type"].Text != "Text") {
            formatted := formatSecond(InputBox("What is the total time? (put m for minutes)").Value)
            text := formatted " " text
            if (InStr(formatted, ":")) {
                split := StrSplit(formatted, ":")
                time := split[1]*60 + split[2]
            } else {
                time := Integer(formatted)
            }
            if (control["type"].Text == "Speaking") {
                text := formatSecond(InputBox("What is the individual speaking time? (put m for minutes)").Value) "/" . text
            }
        }

        change(ctrl, *) {
            i := 1
            while (show.motions[i].count != SubStr(ctrl.name, 5)) {
                i++
            }
            out := show.motions.RemoveAt(i)
            sort(out.proposer, out.text, ctrl.Value, out.time, SubStr(ctrl.name, 5))
        }

        sort(proposer, text, priority, time, count) {
            motions := show.motions

            i := 1
            while (i <= motions.Length && motions[i].priority <= priority && motions[i].time >= time && motions[i].count <= count) {
                i++
            }
            motions.InsertAt(i, {proposer: proposer, text: text, priority: priority, time: time, count: count})
            reShow(motions)
        }

        reShow(motions) {
            show.Destroy()
            show := MotionDisplay(motions)
            for motion in motions {
                show.AddText("xm w500 vprop" motion.count, motion.proposer)
                show.AddText("yp vtext" motion.count, motion.text)
            }
            show.show(1)
        }

        succeed(ctrl, *) {
            ins(ctrl, *) {
                ctrl.Gui["next"].Insert(2147483647,, ctrl.Gui["add"].text)
                ctrl.Gui.other["next"].Insert(2147483647,, ctrl.Gui["add"].text)
            }

            remove(list, item, select) {
                if (select) {
                    list.Delete(item)
                    list.Gui.other["next"].Delete(item)
                }
            }

            if (control["type"].Text == "Change time/veto") {
                default(veto, ctrl)
                return
            }

            i := 1
            while (show.motions[i].count != SubStr(ctrl.name, 5)) {
                i++
            }
            obj := show.motions[i]
            show.Destroy()
            control.Destroy()

            if (InStr(obj.text, "/")) {
                adjustMulti(guiObjs) {
                    for guiObj in guiObjs {
                        try {
                            if guiObj["progTot"].Value {
                                guiObj["leftTot"].Text := "Total left: " formatSecond(--guiObj["progTot"].Value)
                            }
                        } catch {
                            if (guiObj["leftTot"].Value) {
                                --guiObj["leftTot"].Value
                            }
                        }
                        if (guiObj["progSin"].Value == 1) {
                            try {
                                guiObj["progTot"].Prev := guiObj["progTot"].Value + guiObj["progSin"].Range
                            } catch {
                                guiObj["leftTot"].Prev := guiObj["leftTot"].Value + guiObj["progSin"].Range
                            }
                        }
                        guiObj["progSin"].Value--
                        if (guiObj["progSin"].Value <= guiObj["progSin"].Range/3) {
                            guiObj["progSin"].Opt("CRed")
                        } else if (guiObj["progSin"].Value <= guiObj["progSin"].Range/2) {
                            guiObj["progSin"].Opt("CYellow")
                        } else if (guiObj["progSin"].Value <= guiObj["progSin"].Range/3*2) {
                            guiObj["progSin"].Opt("CGreen")
                        }
                        guiObj["leftSin"].Text := "Left: " formatSecond(guiObj["progSin"].Value)
                    }
                }

                submit(bound, gui, *) {
                    done(bound, gui["cur"])
                    close(gui)
                }

                done(bound, ctrl, *) {
                    SetTimer(bound, 0)
                    global stat := 0
                    cur := ctrl.Gui["cur"].Text

                    ctrl.Gui.other["leftSin"].Text := ctrl.Gui["leftSin"].Text := "Left: " singleTime
                    ctrl.Gui.other["progSin"].Value := ctrl.Gui["progSin"].Value := timeS
                    ctrl.Gui["progSin"].Opt("cDefault")
                    ctrl.Gui.other["progSin"].Opt("cDefault")
                    if (ctrl.Gui["next"].GetCount()) {
                        write(ctrl.Gui.other["cur"].text := ctrl.Gui["cur"].text := ctrl.Gui["next"].GetText(1))
                        ctrl.Gui["next"].Delete(1)
                        ctrl.Gui.other["next"].Delete(1)
                    }
                    if (cur != "No current speaker" and Trim(ctrl.Gui["notes"].Text, " `t`n`r")) {
                        countries[cur].mod.Push(ctrl.Gui["score"].Value ":" Trim(ctrl.Gui["notes"].Text, " `t`n`r"))
                    }

                    ctrl.Gui["score"].Value := 1
                    ctrl.Gui["notes"].Text := ""
                }

                yield(ctrl, *) {
                    global stat := 0
                    cur := ctrl.Gui["cur"].Text

                    write(ctrl.Gui.other["cur"].text := ctrl.Gui["cur"].text := ctrl.Gui["add"].Text)
                    if (cur != "No current speaker" and Trim(ctrl.Gui["notes"].Text, " `t`n`r")) {
                        countries[cur].mod.Push(ctrl.Gui["score"].Value ":" Trim(ctrl.Gui["notes"].Text, " `t`n`r"))
                    }

                    ctrl.Gui["score"].Value := 1
                    ctrl.Gui["notes"].Text := ""
                }

                resetMulti(guiObjs, bound) {
                    SetTimer(bound, 0)
                    global stat := 0
                    for guiObj in guiObjs {
                        dif := guiObj["progSin"].Range - guiObj["progSin"].Value
                        if (dif) {
                            if (guiObj["progSin"].Value > 0) {
                                try {
                                    guiObj["leftTot"].Text := "Total left: " formatSecond(guiObj["progTot"].Value += dif)
                                } catch {
                                    guiObj["leftTot"].Value += dif
                                }
                            } else {
                                try {
                                    guiObj["leftTot"].Text := "Total left: " formatSecond(guiObj["progTot"].Value := guiObj["progTot"].Prev)
                                } catch {
                                    guiObj["leftTot"].Value := guiObj["leftTot"].Prev
                                }
                            }
                            guiObj["leftSin"].Text := "Left: " formatSecond(guiObj["progSin"].Value += dif)
                            guiObj["progSin"].Opt("cDefault")
                        } else {
                            try {
                                guiObj["leftTot"].Text := "Total left: " formatSecond(guiObj["progTot"].Value := guiObj["progTot"].Range)
                            } catch {
                                guiObj["leftTot"].Value := obj.Time
                            }
                        }
                    }
                }

                singleTime := StrSplit(obj.text, "/")[1]
                timeS := 0
                if (InStr(singleTime, ":")) {
                    split := StrSplit(singleTime, ":")
                    timeS := split[1]*60 + split[2]
                } else {
                    timeS := Integer(singleTime)
                }
                
                display := Munager("Mod timer",, 30, 1)
                control := Munager("Speech feedback",, 20, 1)
                control.double := 1
                control.other := display

                bound := adjustMulti.Bind([control, display])
                control.onClose(submit.Bind(bound))

                display.AddText("w500 center", obj.text)
                display.AddText("wp center vleftTot", "Total left: " formatSecond(obj.time))
                display.AddProgress("wp vprogTot cDefault Smooth Range0-" obj.time, obj.time).Range := obj.time
                display.AddText("wp center vleftSin", "Left:  " singleTime)
                display.AddProgress("wp vprogSin cDefault Smooth Range0-" timeS, timeS).Range := timeS
                display.AddText("wp center vcur", "No current speaker")
                display.AddListView("wp -hdr vnext r5 Grid", ["Country"])
                display.show(-1)

                control.AddText("w500 center", obj.text)
                control.AddText("wp center vleftTot", obj.time)
                control.AddText("wp center vleftSin", "Left: " singleTime)
                control.AddProgress("wp vprogSin cDefault Smooth Range0-" timeS, timeS).Range := timeS
                control.AddText("wp center vcur", "No current speaker")
                control.AddEdit("wp")
                control.AddUpDown("Range1-5 vscore")
                control.AddEdit("w500 r4 VScroll vnotes")
                control.AddButton("wp center", "Next speaker", done.Bind(bound))
                control.AddDDL("wp sort vadd", arr)
                control.AddButton("wp center", "Add speaker", ins)
                control.AddButton("wp center", "Yield to speaker", yield)
                control.AddListView("wp -hdr vnext r5 Grid", ["Country"], [], remove)
                control.show()

                global stat := 0
                Hotkey("MButton", toggle.Bind(bound), "On")
                Hotkey("RButton", (*) => resetMulti([control, display], bound), "On")
                tip()
            } else if (obj.time) {
                prev := ""
                updateFeedback(ctrl, *) {
                    if (prev != "") {
                        new := ctrl.Gui["score"].Value ":" Trim(ctrl.Gui["notes"].Text, " `t`n`r")
                        if (new != countries[prev].unmod)
                            write(prev "|" (countries[prev].unmod := new))
                    }
                    cur := countries[prev := ctrl.Text].unmod
                    ctrl.Gui["score"].Value := cur == "" ? 1 : SubStr(cur, 1, 1)
                    ctrl.Gui["notes"].Value :=  SubStr(cur, 3)
                }

                display := Munager("Timer display",, 30, 1, close)
                control := Munager("Timer control",, 30, 1, close)
                control.other := display
                screens := [display, control]
                bound := adjustSingle.Bind(screens)

                display.AddText("w500 center", obj.text)
                display.AddText("wp center vleft", "Left: " formatSecond(obj.time))
                display.AddProgress("wp vprog cDefault Smooth Range0-" obj.time, obj.time).Range := obj.time
                display.show(-1)

                control.AddText("w500 center", obj.text)
                control.AddText("wp center vleft", "Left: " formatSecond(obj.time))
                control.AddProgress("wp vprog cDefault Smooth Range0-" obj.time, obj.time).Range := obj.time
                arr := []
                for country, val in countries {
                    if (val.stat) {
                        arr.Push(country)
                    }
                }
                control.AddDDL("wp sort vcur", arr, updateFeedback)
                control.AddEdit("wp")
                control.AddUpDown("Range1-5 vscore")
                control.AddEdit("wp r4 VScroll vnotes")
                control.show()
                global stat := 0
                Hotkey("MButton", toggle.Bind(bound), "On")
                Hotkey("RButton", resetSingle.Bind(screens, bound), "On")
                tip()
            } else {
                chair.show()
            }
        }

        fail(ctrl, *) {
            num := SubStr(ctrl.Name, 5)
            control["prop" num].SetFont("strike")
            control["text" num].SetFont("strike")
            control["prio" num].Enabled := false
            control["edit" num].Enabled := false
            control["pass" num].Enabled := false
            control["fail" num].Enabled := false
            i := 1
            while (show.motions[i].count != num) {
                i++
            }
            show.motions.RemoveAt(i)
            reShow(show.motions)
        }

        control.AddText("xm w300 vprop" control.count, control["prop"].text)
        control.AddText("yp w417 vtext" control.count, text)
        control.AddEdit("yp w97 vedit" control.count)
        control.AddUpDown("wp vprio" control.count, control["type"].Value, change)
        control.AddButton("yp wp h55 vpass" control.count, Chr(0x2713), succeed)
        control.AddButton("yp wp h55 vfail" control.count, Chr(0x2717), fail)
        control.show()
        sort(control["prop"].text, text, control["type"].Value, time, control.count++)
    }
}

vote() {
    global chair
    did := ""
    standard(ctrl, *) {
        display[did := ctrl.Text].Value++
    }

    pass() {
        skip.Push({name: chair["cur"].Text, Abstain: chair["Abstain"].Enabled})
        did := "pass"
    }

    chair.Hide()

    if (!settingsRead("veto")) {
        settingsWrite("veto", InputBox("How many veto votes do you require?").Value)
    }

    display := Munager("Roll call vote display",, 30, 1)
    display.AddText("w100 Center", "For")
    display.AddText("yp wp Center", "Abstain")
    display.AddText("yp wp Center", "Against")
    display.AddText("xm wp Center vFor", 0)
    display.AddText("yp wp Center vAbstain", 0)
    display.AddText("yp wp Center vAgainst", 0)
    display.show(-1)

    control := Munager("Roll call vote control",, 30, 1, (*) => chair.show())
    control.AddText("w350 vcur")
    control.AddButton("wp", "For", standard)
    control.AddButton("wp vAbstain", "Abstain", standard)
    control.AddButton("wp", "Against", standard)
    control.AddButton("wp vPass", "Pass", (*) => pass())
    control.show()

    skip := []
    veto := 0
    for country, val in countries {
        if (val.stat && val.type != "O") {
            control["Abstain"].Enabled := val.stat == "P"
            control["cur"].Text := country
            did := ""
            while(!did) {
                Sleep(100)
            }
            if (did == "Against" && val.type == "V") {
                veto++
            }
        }
    }

    control["Pass"].Enabled := false
    for country in skip {
        control["Abstain"].Enabled := country.Abstain
        control["cur"].Text := country.name
        did := ""
        while(!did) {
            Sleep(100)
        }
        if (did == "Against" && countries[country.name].type == "V") {
            veto++
        }
    }

    MsgBox("With a total of "
            display["For"].Value " vote(s) for, "
            display["Against"].Value " vote(s) against, "
            display["Abstain"].Value " abstention(s), "
            "and " veto " veto(s), "
            "This motion " ((display["For"].Value > display["Against"].Value && veto < settingsRead("veto")) ? "passes" : "fails") ".")
    
    control.Destroy()
    display.Destroy()
    chair.show()
}