class Munager extends Gui {
    static call(Name, vscroll := 0, font := 50, bold := 0, close?) {
        created := super("Resize SysMenu " vscroll ? "+0x200000" : "", Name)
        created.SetFont("s" (created.font := font) (bold ? " bold" : ""))
        created.OnEvent("Size", (*) => created.onResize())
        if IsSet(close) {
            created.onClose(close)
        }
        return created
    }

    onClose(event) {
        this.OnEvent("Close", event)
    }

    onResize() {
        resize(obj) {
            if (!obj.HasProp("W")) {
                return
            }
            obj.GetPos(,,&newW, &newH)
            xMult := newW/obj.W
            yMult := newH/obj.H
            obj.W := newW
            obj.H := newH
            for ctrl in obj {
                ctrl.GetPos(&x, &y, &w, &h)
                ctrl.Move(x*xMult, y*yMult,w*xMult, h*yMult)
            }
            for _, ctrl in obj {
                ctrl.Redraw()
            }
        }

        static bound := Map()
        if (!bound.Has(this.Hwnd)) {
            bound[this.Hwnd] := resize.Bind(this)
        }
        SetTimer(bound[this.Hwnd], -100)

        WinGetClientPos( , , &GuiW, &GuiH, this.Hwnd)
        L := T := 2147483647   ; Left, Top
        R := B := -2147483648  ; Right, Bottom
        For CtrlHwnd In WinGetControlsHwnd(this.Hwnd) {
            ControlGetPos(&CX, &CY, &CW, &CH, CtrlHwnd)
            L := Min(CX, L)
            T := Min(CY, T)
            R := Max(CX + CW, R)
            B := Max(CY + CH, B)
        }
        ; L -= 8, T -= 8
        ; R += 8, B += 8
        ScrW := R - L ; scroll width
        ScrH := B - T ; scroll height
        ; Initialize SCROLLINFO.
        SI := Buffer(28, 0)
        NumPut("UInt", 28, "UInt", 3, SI, 0) ; cbSize , fMask: SIF_RANGE | SIF_PAGE
        ; Update vertical scroll bar.
        ; NumPut("UInt", SIF_RANGE | SIF_PAGE | SIF_DISABLENOSCROLL, SI, 4) ; fMask
        NumPut("Int", ScrH, "UInt", GuiH,  SI, 12) ; nMax , nPage
        DllCall("SetScrollInfo", "Ptr", this.Hwnd, "Int", 1, "Ptr", SI, "Int", 1) ; SB_VERT
        ; Scroll if necessary
        X := (L < 0) && (R < GuiW) ? Min(Abs(L), GuiW - R) : 0
        Y := (T < 0) && (B < GuiH) ? Min(Abs(T), GuiH - B) : 0
        If (X || Y)
            DllCall("ScrollWindow", "Ptr", this.Hwnd, "Int", X, "Int", Y, "Ptr", 0, "Ptr", 0)
    }

    show(max := 0) {
        static other := 0
        if !other {
            count := MonitorGetCount()
            if (MonitorGetPrimary() == count) {
                count--
            }
            if (!count) {
                count := 1
            }
            MonitorGet(count, &other)
            other += 10
        }
        switch max {
            case 0: super.Show("AutoSize Center")
            case 1: super.Show("maximize x" other)
            case -1: super.Show("AutoSize x" other)
        }
        
        super.GetPos(,,&w, &h)
        super.W := w
        super.H := h
        this.onResize()
        if (max == -1) {
            super.Maximize()
            this.onResize()
        }
    }

    bold() {
        this.SetFont("bold s" this.font)
    }

    norm() {
        this.SetFont("norm s" this.font)
    }

    size(size) {
        this.SetFont("s" this.font := size)
    }

    AddButton(options?, text?, event?) {
        button := super.AddButton(options, text)
        if IsSet(event) {
            button.OnEvent("Click", event)
        }
        return button
    }

    AddUpDown(options?, text := 0, event?) {
        ud := super.AddUpDown(options, text)
        if IsSet(event) {
            ud.OnEvent("Change", event)
        }
        return ud
    }

    AddDDL(options?, text := [], event?) {
        ud := super.AddDDL(options, text)
        if IsSet(event) {
            ud.OnEvent("Change", event)
        }
        return ud
    }

    AddListView(options?, header := [], vals := [], event?) {
        lv := super.AddListView(options " Count" vals.Length, header)
        for row in vals {
            lv.Add(row*)
        }
        loop header.Length {
            lv.ModifyCol(A_Index, "AutoHdr")
        }
        if IsSet(event) {
            lv.OnEvent("ItemSelect", event)
        }
        return lv
    }
}

guis := []
OnMessage(0x0115, OnScroll) ; WM_VSCROLL
OnMessage(0x020A, OnWheel)  ; WM_MOUSEWHEEL

OnWheel(W, L, M, H) {
    HWND := WinExist()
    WM_NCHITTEST  := DllCall("SendMessage", "Ptr", HWND, "UInt", 0x0084, "Ptr", 0, "Ptr", l)
    If (WM_NCHITTEST  = 7 || WM_NCHITTEST  = 1) {
        OnScroll((W & 0x80000000) ? 1 : 0, 0, 0x0115, HWND)
    }
}
OnScroll(WP, LP, M, H) {
    Static SCROLL_STEP := 50
    If !(LP = 0) ; not sent by a standard scrollbar
        Return
    Bar := (M = 0x0115) ; SB_VERT=1
    SI := Buffer(28, 0)
    NumPut("UInt", 28, "UInt", 0x17, SI) ; cbSize, fMask: SIF_ALL
    If !DllCall("GetScrollInfo", "Ptr", H, "Int", Bar, "Ptr", SI)
        Return
    RC := Buffer(16, 0)
    DllCall("GetClientRect", "Ptr", H, "Ptr", RC)
    NewPos := NumGet(SI, 20, "Int") ; nPos
    MinPos := NumGet(SI,  8, "Int") ; nMin
    MaxPos := NumGet(SI, 12, "Int") ; nMax
    Switch (WP & 0xFFFF) {
        Case 0: NewPos -= SCROLL_STEP ; SB_LINEUP
        Case 1: NewPos += SCROLL_STEP ; SB_LINEDOWN
        Case 2: NewPos -= NumGet(RC, 12, "Int") - SCROLL_STEP ; SB_PAGEUP
        Case 3: NewPos += NumGet(RC, 12, "Int") - SCROLL_STEP ; SB_PAGEDOWN
        Case 4, 5: NewPos := WP >> 16 ; SB_THUMBTRACK, SB_THUMBPOSITION
        Case 6: NewPos := MinPos ; SB_TOP
        Case 7: NewPos := MaxPos ; SB_BOTTOM
        Default: Return
    }
    MaxPos -= NumGet(SI, 16, "Int") ; nPage
    NewPos := Min(NewPos, MaxPos)
    NewPos := Max(MinPos, NewPos)
    OldPos := NumGet(SI, 20, "Int") ; nPos
    X := (Bar = 0) ? OldPos - NewPos : 0
    Y := (Bar = 1) ? OldPos - NewPos : 0
    If (X || Y) {
        ; Scroll contents of window and invalidate uncovered area.
        DllCall("ScrollWindow", "Ptr", H, "Int", X, "Int", Y, "Ptr", 0, "Ptr", 0)
        ; Update scroll bar.
        NumPut("Int", NewPos, SI, 20) ; nPos
        DllCall("SetScrollInfo", "ptr", H, "Int", Bar, "Ptr", SI, "Int", 1)
    }
    if guis {
        for gui in guis {
            if gui != H
                OnScroll(WP, 0, 0x0115, gui)
        }
    }
}

fileFinder() {
    if(!settingsRead("file") || !FileExist(settingsRead("file"))) {
        if (MsgBox("Do you have a csv file?",,4) == "Yes") {
            MsgBox("Please select the .csv file with the countries.")
            settingsWrite("file", FileSelect(1,,,"CSV File (*.csv)"))
        } else {
            ins(ctrl, *) {
                ctrl := ctrl.Gui
                if (Trim(ctrl["country"].Text, " `t`n`r")) {
                    ctrl.Text .= Trim(ctrl["country"].Text, " `t`n`r") "," (ctrl["Type"].Value>1 ? SubStr(ctrl["Type"].Text, 1, 1) : "") "`n"
                    ctrl["country"].Text := ""
                }
            }

            done(ctrlOrGui, *) {
                if !(ctrlOrGui is Gui) {
                    ctrlOrGui := ctrlOrGui.Gui
                }
                ins(ctrlOrGui["country"])
                fp := FileOpen(settingsRead("file"), 1)
                fp.Write(ctrlOrGui.Text)
                fp.Close()
                ctrlOrGui.Destroy()
            }

            MsgBox("Please select the .csv file you want to write to.")
            settingsWrite("file", FileSelect(16,,,"CSV File (*.csv)"))
            select := Munager("Countries Adder",,30,, done)
            select.Text := ""
            select.AddText("xm w100", "Country:")
            select.AddEdit("yp w300 vcountry")
            select.AddDDL("xm w450 vtype", ["Standard", "Observer", "Veto"])
            select.AddButton("wp", "Insert", ins)
            select.AddButton("wp", "done", done)
            select.Show()
            WinWaitClose(select.Hwnd)
        }
    }

    temp := StrSplit(FileRead(settingsRead("file")),"`n")
    global countries := Map()
    for country in temp {
        if (!country) {
            continue
        }
        split := StrSplit(country, ",")
        while (split.Length < 4) {
            split.Push("")
        }
        countries[Trim(split[1], " `t`n`r")] := {type: Trim(split[2], " `t`n`r"), stat: Trim(split[3], " `t`n`r"), unmod: Trim(StrReplace(StrReplace(split[4], "``n", "`r`n"), "``c", ","), " `t`n`r"), mod: [], unmod_feed: "", mod_feed: []}
        if (split.Length >= 5) {
            i := 5
            while (i <= split.Length) {
                if (!Trim(split[i], " `t`n`r")) {
                    break
                }
                countries[Trim(split[1], " `t`n`r")].mod.Push(Trim(StrReplace(StrReplace(split[i], "``n", "`r`n"), "``c", ","), " `t`n`r"))
                i++
            }
        }
    }

    if (FileExist(settingsRead("file") "\..\secondary.csv")) {
        temp := StrSplit(FileRead(settingsRead("file") "\..\secondary.csv"),"`n")
        for country in temp {
            if (!country) {
                continue
            }
            split := StrSplit(country, ",")
            while (split.Length < 2) {
                split.Push("")
            }
            countries[Trim(split[1], " `t`n`r")].unmod_feed := Trim(StrReplace(StrReplace(split[2], "``n", "`r`n"), "``c", ","), " `t`n`r")
            if (split.Length >= 3) {
                i := 3
                while (i <= split.Length) {
                    if (!Trim(split[i], " `t`n`r")) {
                        break
                    }
                    countries[Trim(split[1], " `t`n`r")].mod_feed.Push(Trim(StrReplace(StrReplace(split[i], "``n", "`r`n"), "``c", ","), " `t`n`r"))
                    i++
                }
            }
        }
    }
}

settingsWrite(key, val) {
    if (!FileExist("munager.ini")) {
        FileOpen("munager.ini", "rw")
    }
    IniWrite(val, "munager.ini", "settings", key)
    return val
}

settingsRead(key) {
    if (!FileExist("munager.ini")) {
        FileOpen("munager.ini", "rw")
    }
    try {
        return IniRead("munager.ini", "settings", key)
    } catch {
        return IniWrite(0, "munager.ini", "settings", key)
    }
}

save(sync := true, main := true) {
    if (main) {
        FileDelete(settingsRead("file"))
        fp := FileOpen(settingsRead("file"), "w")
        text := ""
        for country, val in countries {
            text .= country "," val.type "," val.stat "," StrReplace(StrReplace(val.unmod, "`r`n", "``n"), ",", "``c")
            for speech in val.mod {
                text .= "," StrReplace(StrReplace(speech, "`r`n", "``n"), ",", "``c")
            }
            text .= "`n"
        }
    } else {
        secondary := settingsRead("file") "\..\secondary.csv"
        if (FileExist(secondary))
            FileDelete(secondary)
        fp := FileOpen(secondary, "w")
        text := ""
        for country, val in countries {
            text .= country "," StrReplace(StrReplace(val.unmod_feed, "`r`n", "``n"), ",", "``c")
            for speech in val.mod_feed {
                text .= "," StrReplace(StrReplace(speech, "`r`n", "``n"), ",", "``c")
            }
            text .= "`n"
        }
    }
    fp.Write(Trim(text, " `t`n`r"))
    fp.Close()
    if (sync) {
        RunWait("git add .", settingsRead("file") "\..")
        RunWait('git commit -m "saved data"', settingsRead("file") "\..")
        RunWait("git push", settingsRead("file") "\..")
    }
}