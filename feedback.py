from __future__ import annotations

from tkinter import messagebox, simpledialog
import tkinter.font as tkfont
from typing import Optional

from munager_proto import (Country, CountryDelta, Feedback, FullState, Hello,
                           PresenceSync, SpeechStart, decode, encode)
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
    return sorted(n for n, c in countries.items() if c.presence)


# ---- networking -------------------------------------------------------------

def push(name: str) -> None:
    """Send this co-chair's feedback for one delegation to the primary."""
    if client is None:
        return
    c = countries.get(name)
    if c is None:
        return
    client.write(encode(CountryDelta(c)))


def _on_server_data(raw: bytes) -> None:
    """Messages from the primary on the client socket."""
    global select
    message = decode(raw)

    if isinstance(message, SpeechStart):
        mod(message.country, ask)
        return

    if isinstance(message, PresenceSync):
        for p in message.presence:
            c = countries.get(p.name)
            if c is None:
                c = Country(p.name)
                countries[p.name] = c
            c.presence = p.presence
            c.power = p.power
        _reopen()
        return

    if isinstance(message, CountryDelta):
        d = message.country
        c = countries.get(d.name)
        if c is None:
            c = Country(d.name)
            countries[d.name] = c
        # chair's feedback (its unmod/mod) lands in OUR *_feed slots
        c.unmod_feed = d.unmod
        c.mod_feed = list(d.mod)
        c.presence = d.presence
        c.power = d.power
        _reopen()
        return

    if isinstance(message, FullState):
        if select is not None:
            select.Destroy()
            select = None
        countries.clear()
        for c in message.countries:
            countries[c.name] = c
        primary()
        return


# ---- speech feedback (single edit) ------------------------------------------

def mod(country: str, ask_mode: int = 0) -> None:
    assert select is not None
    sel = select

    if country not in countries:
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

    def add_mod(entry: Feedback) -> None:
        c.mod.append(entry)          # co-chair's own -> unmod/mod

    def on_saved() -> None:
        push(country)
        sel.show()

    speech_feedback(country, add_mod, on_saved)


# ---- full feedback editor ---------------------------------------------------

def show_feedback(del_ctrl: Ctrl) -> None:
    assert select is not None
    sel = select
    name = del_ctrl.Text
    if name not in countries:
        messagebox.showerror("munager", "Please select a country first")
        sel.show()
        return
    sel.Hide()

    def back() -> None:
        view.Destroy()
        sel.show()

    view = feedback_viewer(name, back)


# ---- awards (combined own + _feed) ------------------------------------------

def awards() -> None:
    assert select is not None
    sel = select
    sel.Hide()

    def back() -> None:
        win.Destroy()
        sel.show()

    win = awards_window(back)


# ---- UNMOD feedback ---------------------------------------------------------

def enter_unmod(del_ctrl: Ctrl) -> None:
    assert select is not None
    sel = select
    name = del_ctrl.Text
    if name not in countries:
        messagebox.showerror("munager", "Please select a country first")
        return
    sel.Hide()
    c = countries[name]

    def add_mod(entry: Feedback) -> None:
        c.unmod = entry                     # co-chair's own unmod

    def on_saved() -> None:
        push(name)
        sel.show()

    fb = c.unmod
    speech_feedback(name, add_mod, on_saved,
                    score0=fb.score if fb.score >= 1 else 3,
                    note0=fb.note)


# ---- main selector ----------------------------------------------------------

def primary() -> None:
    global select
    select = Munager("Feedback selector", font=30,
                     close=lambda: Munager.root().destroy())
    sel = select

    ddl = sel.AddDDL(sorted_present(), width=500, sort=True)
    sel.AddButton("Speech", event=lambda e: mod(ddl.Text, 2))
    sel.AddButton("Show feedback", event=lambda e: show_feedback(ddl))
    sel.AddButton("Awards", event=lambda e: awards())
    sel.AddButton("UNMOD feedback", event=lambda e: enter_unmod(ddl))

    sel.AddText("Incoming speeches ")
    lb = sel.AddListBox(["are ignored", "prompt you", "take control"],
                        rows=3, choose=ask + 1)

    def on_mode(c: Ctrl) -> None:
        global ask
        ask = {1: 0, 2: 1, 3: 2}.get(c.Value, 1)

    lb.widget.bind("<<ListboxSelect>>", lambda _e: on_mode(lb))
    sel.show()


# ---- startup ----------------------------------------------------------------

def _reopen() -> None:
    """Rebuild the selector after the model changed."""
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

    entered = simpledialog.askstring("munager", "Server IP address?",
                                     parent=root)
    assert entered

    ip = entered
    client = net.connect(8080, entered)
    client.on("data", _on_server_data)
    client.write(encode(Hello()))            # request full state
    mainloop()


if __name__ == "__main__":
    main()
