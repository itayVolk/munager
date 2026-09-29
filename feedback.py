from __future__ import annotations

import json
from tkinter import messagebox, simpledialog
import tkinter.font as tkfont
from typing import Optional

import munager_data as data
import munager_net as net
from munager_data import countries
from munager_gui import Ctrl, Munager, mainloop
from munager_feedback_ui import speech_feedback, awards_window, feedback_viewer

# ---- connection state -------------------------------------------------------
ip: str = ""                       # server IP; "" => local/git mode
ask: int = 1                       # 0 ignore, 1 prompt-yesno, 2 take control
client: Optional[net.LengthSocket] = None
select: Optional[Munager] = None


def sorted_present() -> list[str]:
    return sorted(n for n, c in countries.items() if c.stat)


# ---- networking -------------------------------------------------------------

def write(country: str, unmod: str, mod: list[str]) -> None:
    if ip:                              # online: stream to primary, no disk
        if client is not None:
            client.write(json.dumps(
                {"country": country, "unmod": unmod, "mod": mod}))
    else:                               # offline: write own half + git
        data.save(sync=True)


def _on_server_data(raw: bytes) -> None:
    """Messages from the primary (the co-chair) on the client socket."""
    global select
    text = raw.decode("utf-8")

    if not text.startswith("{") and not text.startswith("["):
        mod(text, ask)                 # bare name => speech happened
        return

    loaded = json.loads(text)

    # presence/roll-call update from primary
    if isinstance(loaded, dict) and "presence" in loaded:
        for name, obj in loaded["presence"].items():
            c = countries.get(name) or data.Country(name)
            c.stat = obj.get("stat", c.stat)
            c.type = obj.get("type", c.type)
            countries[name] = c
        _reopen()                     # rebuild selector with new present list
        return

    # single-country update from primary = chair's feedback -> unmod/mod
    if isinstance(loaded, dict) and "country" in loaded:
        c = countries.get(loaded["country"])
        if c:
            c.unmod = loaded.get("unmod", c.unmod)
            c.mod = list(loaded.get("mod", c.mod))
        return

    # full state map (initial sync) = chair's data -> unmod/mod
    if select is not None:
        select.Destroy()
        select = None
    countries.clear()
    for name, obj in loaded.items():
        c = data.Country(name)
        c.unmod = obj.get("unmod", "")
        c.mod = list(obj.get("mod", []))
        c.unmod_feed = obj.get("unmod_feed", "")   # if primary sends it
        c.mod_feed = list(obj.get("mod_feed", []))
        c.stat = obj.get("stat", "")
        c.type = obj.get("type", "")
        countries[name] = c
    primary()


# ---- speech feedback (single edit) ------------------------------------------

def mod(country: str, ask_mode: int = 0) -> None:
    assert select is not None
    sel = select

    if country == "":
        messagebox.showerror("munager", "Please select a country first")
        sel.show()
        return
    if ask_mode == 1:
        if not messagebox.askyesno(
                "munager", f"Give feedback on {country}'s speech?"):
            return
    elif ask_mode == 0:
        return

    sel.Hide()
    c = countries[country]

    def add_mod(entry: str) -> None:
        c.mod_feed.append(entry)                 # co-chair's own stream

    def on_saved() -> None:
        write(country, c.unmod_feed, c.mod_feed)
        sel.show()

    speech_feedback(country, lambda: c.unmod_feed, add_mod, on_saved)


# ---- full feedback editor ---------------------------------------------------

def show_feedback(del_ctrl: Ctrl) -> None:
    assert select is not None
    sel = select
    name = del_ctrl.Text
    if name == "":
        messagebox.showerror("munager", "Please select a country first")
        sel.show()
        return
    sel.Hide()

    def back() -> None:
        view.Destroy()
        sel.show()

    view = feedback_viewer(name, back, own_is_secondary=True)      # defaults: chair / co-chair


# ---- awards (combined own + _feed) ------------------------------------------
def awards() -> None:
    assert select is not None
    sel = select
    sel.Hide()

    def back() -> None:
        win.Destroy()
        sel.show()

    win = awards_window(back)


# ---- main selector ----------------------------------------------------------

def primary() -> None:
    global select
    select = Munager("Feedback selector", font=30,
                     close=lambda: Munager.root().destroy())
    sel = select

    sel.AddDDL(sorted_present(), width=500, sort=True)
    sel.AddButton("Speech", event=lambda e: mod(e.Text, 2))
    sel.AddButton("Show feedback", event=show_feedback)
    sel.AddButton("Awards", event=lambda e: awards())
    sel.AddButton("UNMOD feedback", event=enter_unmod)

    if ip:
        sel.AddText("Incoming speeches ")
        lb = sel.AddListBox(["are ignored", "prompt you", "take control"], rows=3, choose=ask + 1)

        def on_mode(c: Ctrl) -> None:
            global ask
            # 1->ignore(0), 2->prompt(1), 3->control(2) mapping to AHK ask
            v = c.Value
            ask = {1: 0, 2: 1, 3: 2}.get(v, 1)

        lb.widget.bind("<<ListboxSelect>>", lambda _e: on_mode(lb))
    else:
        sel.AddButton("Save feedback", event=lambda e: data.save(sync=False))
        sel.AddButton("Sync (git pull/merge)", event=lambda e: (data.load(), _reopen()))

    sel.show()


def enter_unmod(del_ctrl: Ctrl) -> None:
    assert select is not None
    sel = select
    name = del_ctrl.Text
    if name == "":
        messagebox.showerror("munager", "Please select a country first")
        return
    sel.Hide()
    c = countries[name]

    def add_mod(entry: str) -> None:
        c.unmod_feed = entry

    def on_saved() -> None:
        write(name, c.unmod_feed, c.mod_feed)
        sel.show()

    speech_feedback(name, lambda: c.unmod_feed, add_mod,
                    on_saved, initial=c.unmod_feed)


# ---- startup ----------------------------------------------------------------

def _reopen() -> None:
    """Rebuild the selector after the model changed (e.g. git sync)."""
    global select
    if select is not None:
        select.Destroy()
        select = None
    primary()


def main() -> None:
    global ip, client
    root = Munager.root()

    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                  "TkHeadingFont", "TkCaptionFont", "TkFixedFont"):
        try:
            tkfont.nametofont(fname).configure(size=22)
        except Exception:
            pass

    entered = simpledialog.askstring(
        "munager",
        "Server IP address? Cancel to run locally (git/file).",
        parent=root)

    if entered:                      # IP given => online
        ip = entered
        data.set_mode("online", primary=False)
        client = net.connect(8080, entered)      # (port, host)
        client.on("data", _on_server_data)
        client.write("start")                    # request full state
    else:                            # offline => owns secondary.csv, git-merged
        ip = ""
        data.set_mode("offline", primary=False)
        if not data._dir():
            if not data.choose_dir():     # user cancelled folder pick
                messagebox.showinfo("munager", "No folder selected. Exiting.")
                root.destroy()
                return
        else:
            data.load()
        primary()                         # build the selector immediately
    mainloop()


if __name__ == "__main__":
    main()
