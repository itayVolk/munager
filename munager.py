from __future__ import annotations

import json
import random
import socket
import tkinter as tk
from tkinter import messagebox, simpledialog
import tkinter.font as tkfont
from typing import Callable, Optional, cast

import munager_data as data
import munager_net as net
from munager_data import countries
from munager_gui import Ctrl, Munager, mainloop
from munager_feedback_ui import speech_feedback, awards_window, feedback_viewer

# ---- globals ----------------------------------------------------------------
single: bool = True
server_clients: list[net.LengthSocket] = []
chair: Optional[Munager] = None
speakers_list: list[str] = []


# ---- helpers ----------------------------------------------------------------

def format_second(s: int) -> str:
    s = int(s)
    return f"{s // 60}:{s % 66:02d}"


def parse_time(s: str) -> int:
    s = str(s).strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m or 0) * 60 + int(sec or 0)
    return int(s or 0)


def _focus(parent: tk.Misc) -> None:
    try:
        parent.lift()
        parent.focus_force()
        parent.update_idletasks()
    except Exception:
        pass


def _grab_dialog_focus(parent: tk.Misc) -> None:
    def find_entry(w: tk.Misc) -> Optional[tk.Entry]:
        for c in w.winfo_children():
            if isinstance(c, tk.Entry):
                return c
            found = find_entry(c)
            if found is not None:
                return found
        return None

    def do() -> None:
        for w in parent.winfo_children():
            if isinstance(w, tk.Toplevel) and w.winfo_viewable():
                w.lift()
                w.focus_force()
                entry = find_entry(w)
                if entry is not None:
                    entry.focus_set()
                    entry.select_range(0, "end")
                return
    parent.after(50, do)


def ask_time(prompt: str, parent: tk.Misc) -> Optional[int]:
    raw = ask_string(prompt, parent)
    if raw is None:
        return None
    try:
        return parse_time(raw)
    except ValueError:
        return None


def ask_string(prompt: str, parent: tk.Misc) -> Optional[str]:
    _focus(parent)
    _grab_dialog_focus(parent)
    return simpledialog.askstring("munager", prompt, parent=parent)


def sorted_countries() -> list[str]:
    return sorted(countries.keys())


def present_countries() -> list[str]:
    return sorted(n for n, c in countries.items() if c.stat)


def _resume_chair() -> None:
    if chair is not None:
        chair.show()


# ---- networking -------------------------------------------------------------

def broadcast(country: str) -> None:
    c = countries.get(country)
    if not c:
        return
    payload = json.dumps({
        "country": country,
        "unmod": c.unmod, "mod": c.mod,
        "unmod_feed": c.unmod_feed, "mod_feed": c.mod_feed,
    })
    for cli in list(server_clients):
        cli.write(payload)


def write(text: str) -> None:
    """Send a raw feedback message to all connected co-chairs (no-op if single)."""
    if single:
        return
    for cli in list(server_clients):
        cli.write(text)


def _on_client_data(cli: net.LengthSocket, raw: bytes) -> None:
    text = raw.decode("utf-8")
    if text == "start":
        full = {name: {"unmod": c.unmod, "mod": c.mod,
                       "unmod_feed": c.unmod_feed, "mod_feed": c.mod_feed,
                       "stat": c.stat, "type": c.type}
                for name, c in countries.items()}
        cli.write(json.dumps(full))
        return
    try:
        msg = json.loads(text)
    except ValueError:
        return
    country = msg.get("country", "")
    c = countries.get(country)
    if not c:
        c = data.Country(country)
        countries[country] = c
    c.unmod_feed = msg.get("unmod", c.unmod_feed)
    c.mod_feed = list(msg.get("mod", c.mod_feed))
    data.save(sync=single)     # networked: co-chair feedback merged into main csv


def _on_connection(cli: net.LengthSocket) -> None:
    server_clients.append(cli)
    cli.on("data", lambda raw, cli=cli: _on_client_data(cli, raw))
    full = {name: {"unmod": c.unmod, "mod": c.mod,
                   "unmod_feed": c.unmod_feed, "mod_feed": c.mod_feed,
                   "stat": c.stat, "type": c.type}
            for name, c in countries.items()}
    cli.write(json.dumps(full))


# ---- feedback display -------------------------------------------------------


def feedback() -> None:
    global chair
    assert chair is not None
    ch = chair
    ch.Hide()

    def chosen(sel: Ctrl) -> None:
        country = sel.Text
        if country not in countries:
            messagebox.showerror("munager", "Please select a country first")
            select.show()
            return
        select.Hide()

        def back() -> None:
            view.Destroy()
            select.show()

        view = feedback_viewer(country, back)   # same defaults
        view.show()

    select = Munager("Feedback selector", font=30, bold=1,
                     close=lambda: (select.Destroy(), ch.show()))
    select.AddDDL("w500 sort vdel", sorted_countries())
    select.AddButton("wp", "Select", lambda e: chosen(select["del"]))
    select.show()


# ---- awards -----------------------------------------------------------------
def awards() -> None:
    assert chair is not None
    ch = chair
    ch.Hide()

    def back() -> None:
        win.Destroy()
        ch.show()

    win = awards_window(back)


# ---- roll call --------------------------------------------------------------
def broadcast_presence() -> None:
    """Push every country's presence/type to co-chairs (roll-call sync)."""
    if single:
        return
    payload = json.dumps({
        "presence": {name: {"stat": c.stat, "type": c.type}
                     for name, c in countries.items()}
    })
    for cli in list(server_clients):
        cli.write(payload)

def call() -> None:
    global chair
    assert chair is not None
    ch = chair
    ch.Hide()

    control = Munager("Roll call (control)", font=20,
                      close=lambda: (data.save(sync=single),
                                     control.Destroy(),
                                     display.Destroy(), ch.show()))
    display = Munager("Roll call (display)", font=30, close=lambda: None)
    control.link_display(display)

    order = sorted_countries()
    rows: dict[str, dict[str, Ctrl]] = {}

    def status_label(state: str) -> str:
        return {"": "Absent", "P": "Present",
                "V": "Present & Voting", "O": "Observer"}.get(state, "Absent")

    def type_label(c: data.Country) -> str:
        return {"O": "Observer", "V": "Permanent"}.get(c.type, "")

    def counts() -> dict[str, int]:
        present = sum(1 for n in order if countries[n].stat in ("P", "V"))
        voting = sum(1 for n in order if countries[n].stat == "V")
        present_nonobs = sum(1 for n in order
                             if countries[n].stat in ("P", "V")
                             and countries[n].type != "O")
        return {"present": present, "voting": voting,
                "present_nonobs": present_nonobs}

    def summary_text() -> str:
        c = counts()
        pres = c["present"]                 # includes observers
        pno = c["present_nonobs"]
        reg = pres // 2 + 1
        two_thirds = -(-2 * pres // 3)      # ceil(2/3 of present incl. obs)
        vote_maj = pno // 2 + 1             # voting majority excl. observers
        return (f'Present: {pres}\n'
                f'Present (excl. observers): {pno}\n'
                f'Regular majority: {reg}    2/3 majority: {two_thirds}\n'
                f'Voting majority: {vote_maj}')

    def refresh_display() -> None:
        summary.Text = summary_text()
        c_summary.Text = summary_text()
        d_view.clear()
        for n in order:
            tag = type_label(countries[n])
            label = f"{n} ({tag})" if tag else n
            d_view.insert_full(d_view.count() + 1,
                               [label, status_label(countries[n].stat)])
        d_view.set_height(len(order))

    def set_state(name: str, state: str) -> None:
        countries[name].stat = state
        r = rows[name]
        r["abs"].widget["relief"] = "sunken" if state == "" else "raised"
        r["pre"].widget["relief"] = "sunken" if state == "P" else "raised"
        if "vot" in r:
            r["vot"].widget["relief"] = "sunken" if state == "V" else "raised"
        refresh_display()

    c_summary = control.AddText("w700", "")

    for name in order:
        c = countries[name]
        row = control.AddRow()
        tag = type_label(c)
        row.label(f"{name}  ({tag})" if tag else name, width=24)
        rm: dict[str, Ctrl] = {}
        rm["abs"] = row.button("Absent", lambda e, n=name: set_state(n, ""))
        rm["pre"] = row.button("Present", lambda e, n=name: set_state(n, "P"))
        # observers/permanent may not be "Present & Voting"
        if not c.type:
            rm["vot"] = row.button("Present & Voting",
                                   lambda e, n=name: set_state(n, "V"))
        rows[name] = rm

    def submit() -> None:
        data.save(sync=single)
        broadcast_presence()          # sync roll call to co-chairs
        control.Destroy()
        display.Destroy()
        ch.show()

    control.AddButton("", "Submit", lambda e: submit())

    summary = display.AddText("", "")
    d_view = display.AddListView("w600 Grid", ["Country", "Status"])

    for name in order:
        set_state(name, countries[name].stat)

    control.show()
    display.show(1)


# ---- settings ---------------------------------------------------------------

def settings() -> None:
    global chair
    assert chair is not None
    ch = chair
    ch.Hide()

    def build() -> None:
        view = Munager("Settings", font=20,
                       close=lambda: (view.Destroy(), ch.show()))

        def reopen() -> None:
            view.Destroy()
            build()

        def change_dir() -> None:
            if data.choose_dir():
                reopen()

        def set_time() -> None:
            got = ask_time("Default speaking time? (m:ss)", view.win)
            if got is not None:
                data.settings_write("time", got)
                reopen()

        def set_veto() -> None:
            n = simpledialog.askinteger(
                "Settings", "How many veto votes are required to block?",
                initialvalue=int(veto) if str(veto).isdigit() else 1,
                minvalue=0, parent=view.win)
            if n is not None:
                data.settings_write("veto", n)
                reopen()

        def toggle_mode() -> None:
            data.settings_write("list", "" if use_list else "1")
            reopen()

        def toggle_tip() -> None:
            data.settings_write("tip", "" if tip_on else "1")
            reopen()

        # file
        r = view.AddRow()
        r.label("Working folder: " + (data._dir() or "(none)"))
        r.button("Change / choose", lambda e: change_dir())
        r.button("Add countries", lambda e: add_countries(view))

        # speaking time
        st = data.settings_read("time")
        st_disp = format_second(int(st)) if str(st).isdigit() else "(unset)"
        r = view.AddRow()
        r.label(f"Default speaking time: {st_disp}", width=30)
        r.button("Set", lambda e: set_time())

        # veto
        veto = data.settings_read("veto")
        veto_disp = veto if str(veto).isdigit() else "(unset)"
        r = view.AddRow()
        r.label(f"Vetoes required: {veto_disp}", width=30)
        r.button("Set", lambda e: set_veto())

        # mode
        use_list = bool(data.settings_read("list"))
        r = view.AddRow()
        r.label(f"Mode: {'Speakers list' if use_list else 'Round robin'}",
                width=30)
        r.button("Switch to Round robin" if use_list
                 else "Switch to Speakers list", lambda e: toggle_mode())

        # tip
        tip_on = bool(data.settings_read("tip"))
        r = view.AddRow()
        r.label(f"Hotkey tips: {'suppressed' if tip_on else 'on'}", width=30)
        r.button("Re-enable" if tip_on else "Suppress",
                 lambda e: toggle_tip())

        view.AddButton("", "Back", lambda e: (view.Destroy(), ch.show()))
        view.show()

    build()


def add_countries(parent: Munager) -> None:
    parent.Hide()
    entry = Munager("Add countries", font=20,
                    close=lambda: (entry.Destroy(), parent.show()))
    entry.AddText("w400", "Country name:")
    entry.AddEdit("wp vname")
    entry.AddText("wp", "Type:")
    entry.AddDDL("wp vtype",
                 ["Normal (can vote)", "Veto holder", "Observer"])

    def add_one() -> None:
        name = entry["name"].Text.strip()
        if not name:
            messagebox.showerror("munager", "Enter a country name.")
            return
        if name in countries:
            messagebox.showerror("munager", f"{name} already exists.")
            return
        ctype = {2: "V", 3: "O"}.get(entry["type"].Index, "")
        c = data.Country(name)
        c.type = ctype
        c.stat = ""
        countries[name] = c
        entry["name"].Text = ""
        messagebox.showinfo("munager", f"Added {name}.")

    def done() -> None:
        data.save(sync=single)
        entry.Destroy()
        parent.show()

    entry.AddButton("wp", "Add", lambda e: add_one())
    entry.AddButton("wp", "Done (save)", lambda e: done())
    entry.show()

# ---- hotkey tip -------------------------------------------------------------

def tip() -> None:
    if data.settings_read("tip"):
        return
    messagebox.showinfo(
        "munager hotkeys",
        "During a caucus (control window):\n"
        "  Right click   - start / pause the timer\n"
        "  Middle click   - reset the speaker timer")
    data.settings_write("tip", "1")


# ---- speech feedback entry --------------------------------------------------

def enter_feedback(country: str, is_unmod: bool,
                   after: Callable[[], None]) -> None:
    c = countries[country]

    def add_mod(entry: str) -> None:
        if is_unmod:
            c.unmod = entry
        else:
            c.mod.append(entry)

    def on_saved() -> None:
        broadcast(country)
        data.save(sync=single)
        after()

    speech_feedback(country, lambda: c.unmod, add_mod, on_saved)


# ---- voting -----------------------------------------------------------------

def vote() -> None:
    global chair
    assert chair is not None
    ch = chair
    ch.Hide()

    veto_setting = data.settings_read("veto")
    veto_needed = int(veto_setting) if str(veto_setting).isdigit() else 0

    voters = [n for n in sorted_countries()
              if countries[n].stat in ("P", "V") and countries[n].type != "O"]

    state = {"i": 0, "yes": 0, "no": 0, "abstain": 0, "veto": 0}
    deferred: list[str] = []
    phase = {"n": 1}

    control = Munager("Roll call vote (control)", font=20,
                      close=lambda: (control.Destroy(),
                                     display.Destroy(), ch.show()))
    display = Munager("Roll call vote (display)", font=40, bold=1,
                      close=lambda: None)
    control.link_display(display)

    cur = display.AddText("w600 Center", "")
    total = display.AddText("w600 Center", "")

    def queue() -> list[str]:
        return voters if phase["n"] == 1 else deferred

    def current_name() -> Optional[str]:
        q = queue()
        return q[state["i"]] if state["i"] < len(q) else None

    def abstain_allowed(name: str) -> bool:
        return countries[name].stat != "V"

    def update_total() -> None:
        total.Text = (f'For: {state["yes"]}   Against: {state["no"]}   '
                      f'Abstain: {state["abstain"]}   Veto: {state["veto"]}')

    def finish() -> None:
        p = sum(1 for n in voters)
        blocked = veto_needed and state["veto"] >= veto_needed
        passed = (state["yes"] > state["no"]) and not blocked
        verdict = ("BLOCKED by veto" if blocked
                   else "PASSES" if passed else "FAILS")
        messagebox.showinfo(
            "Vote result",
            f'With {state["yes"]} vote(s) for, {state["no"]} against, '
            f'{state["abstain"]} abstention(s), and {state["veto"]} veto(s), '
            f'this motion {verdict}.')
        control.Destroy()
        display.Destroy()
        ch.show()

    def advance() -> None:
        q = queue()
        if state["i"] >= len(q):
            if phase["n"] == 1 and deferred:
                phase["n"] = 2
                state["i"] = 0
                control["Pass"].widget["state"] = "disabled"
            else:
                finish()
                return
        show_current()

    def cast(kind: str) -> None:
        name = current_name()
        if name is None:
            return
        state[kind] += 1
        if kind == "no" and countries[name].type == "V":
            state["veto"] += 1
        state["i"] += 1
        update_total()
        advance()

    def do_pass() -> None:
        name = current_name()
        if name is None:
            return
        deferred.append(name)
        state["i"] += 1
        advance()

    def show_current() -> None:
        name = current_name()
        if name is None:
            finish()
            return
        cur.Text = name
        control["cur"].Text = (f"[DEFERRED] {name}"
                               if phase["n"] == 2 else name)
        control["Abstain"].widget["state"] = (
            "normal" if abstain_allowed(name) else "disabled")
        control["Pass"].widget["state"] = (
            "disabled" if phase["n"] == 2 else "normal")
        control.win.update_idletasks()
        control.show()

    widest = max((len(n) for n in voters), default=10) + 12
    control.AddText(f"w{widest * 12} vcur", "")
    control.AddButton("", "For", lambda e: cast("yes"))
    control.AddButton("vAbstain", "Abstain", lambda e: cast("abstain"))
    control.AddButton("", "Against", lambda e: cast("no"))
    control.AddButton("vPass", "Pass", lambda e: do_pass())

    update_total()
    show_current()
    control.show()
    display.show(1)


# ---- motions ----------------------------------------------------------------

class Motion:
    def __init__(self, proposer: str, text: str, priority: int,
                 time: int, num: int) -> None:
        self.proposer = proposer
        self.text = text
        self.priority = priority        # editable; default = type index
        self.time = time                # total time (0 if none)
        self.num = num                  # proposal order
        self.kind: int = 1
        self.per_speech: int = 0
        self.veto_only: bool = False

    def timer_count(self) -> int:
        return (1 if self.time else 0) + (1 if self.per_speech else 0)

    def sort_key(self) -> tuple:
        # higher priority first  -> negate
        # then more total time first, then more per-speech first
        # then FEWER timers first, then earlier proposal order
        return (
            -self.priority,
            -self.time,
            -self.per_speech,
            self.timer_count(),
            self.num,
        )


class CaucusWindow:
    """
    Two-window caucus.

    mode:
      "mod"    -> per-speaker timer + total timer; chair-filled speakers
      "open"   -> per-speaker timer, NO total; chair-filled speakers
      "unmod"  -> single total timer, NO speakers, one feedback (unmod score)
    """

    def __init__(self, title: str, mode: str,
                 total: int, per_speech: int,
                 use_list: bool, veto_only: bool,
                 after: Callable[[], None]) -> None:
        self.mode = mode
        self.has_speakers = mode in ("mod", "open")
        self.has_total = mode == "mod" and bool(total)
        self.total = total if self.has_total else 0
        self.per_speech = per_speech
        self.after = after
        self.total_left = self.total
        self.speaker_left = per_speech
        self.running = False
        self.current: Optional[str] = None
        self._tick_id: Optional[str] = None
        self.speaker_left = per_speech
        self._speaker_start_left = per_speech

        tip()

        self.queue = []
        if mode == "open": # non-speakers list/round robin: empty queue initially
            if not use_list: # round robin auto-fills
                pool = present_countries()
                if veto_only:
                    pool = [n for n in pool if countries[n].type == "V"]
                random.shuffle(pool)
                self.queue = pool
            elif self.has_speakers:
                self.queue = speakers_list          # persistent, chair-filled
        self.veto_only = veto_only
        self.idx = 0

        # ---- display window ----
        self.display = Munager(f"{title} (display)", font=40, bold=1,
                               close=lambda: None)
        self.d_name = self.display.AddText("w900 Center", title)
        self.d_speaker = self.display.AddText("w900 Center", "")
        self.d_bar = self.display.AddProgress("w900")
        if self.has_total:
            self.d_total = self.display.AddText("w900 Center", "")
            self.d_total_bar = self.display.AddProgress("w900")
        if self.has_speakers:
            self.display.AddText("w900 Center", "Up next:")
            self.d_next = self.display.AddListView("w900", ["Next speakers"])

        # ---- control window ----
        self.control = Munager(f"{title} (control)", font=22,
                               close=self._close)
        self.c_speaker = self.control.AddText("w500", "")
        if self.has_total:
            self.c_total = self.control.AddText("w500", "")
        crow = self.control.AddRow()
        self.startbtn = crow.button("Start", lambda e: self.toggle())
        self._sync_button()
        crow.button("Reset", lambda e: self.reset())

        if self.has_speakers:
            self.control.AddText("", "Add speaker:")
            arow = self.control.AddRow()
            pool = present_countries()
            if self.veto_only:
                pool = [n for n in pool if countries[n].type == "V"]
            self.add_ddl = self.control.AddDDL("w300 sort vadd", pool)
            arow.button("Add", lambda e: self._add_speaker())
            # full queue on the control screen with remove buttons
            self.control.AddText("", "Speakers:")
            self.speaker_rows: list[tk.Frame] = []
            self.sp_holder = self.control.AddRow()   # container marker

        # inline feedback
        if self.mode == "unmod":
            self.control.AddText("", "Delegate:")
            self.u_ddl = self.control.AddDDL(
                "w300 sort vdel", present_countries())
            self._unmod_current: Optional[str] = None
            self.u_ddl.on_change(lambda c=self.u_ddl: self._unmod_switch())
        self.control.AddText("", "Score (1-5):")
        self.fb_score = self.control.AddUpDown("Range1-5 vscore", 3)
        self.control.AddText("", "Notes:")
        self.fb_notes = self.control.AddEdit("r3 VScroll vnotes")

        next_label = "Next speaker" if self.has_speakers else "Save feedback"
        self.control.AddButton("", next_label,
                               lambda e: self._next_speaker())

        self.control.bind_mouse("middle", lambda *_a: self.reset())
        # bind right-click directly; some bind_mouse impls miss <Button-3>
        self.control.win.bind("<Button-3>",
                              lambda e: (self.toggle(), "break")[1])
        self.display.win.bind("<Button-3>",
                              lambda e: (self.toggle(), "break")[1])

        if self.has_speakers:
            self._refresh_next()
            self._refresh_control_queue()
        self._start_speaker()
        self.control.show()
        self.display.show(1)

    def _parse_score_note(self, entry: str) -> tuple[int, str]:
        if entry and ":" in entry:
            score, note = entry.split(":", 1)
            try:
                return int(score), note
            except ValueError:
                return 3, entry
        return 3, entry or ""

    def _unmod_switch(self) -> None:
        # save notes for the delegate we were editing
        prev = self._unmod_current
        if prev:
            note = self.fb_notes.Text.strip()
            entry = f"{self.fb_score.Value}:{note}" if note else ""
            countries[prev].unmod = entry
            broadcast(prev)
            data.save(sync=single)
        # load the newly selected delegate's existing feedback
        name = self.u_ddl.Text
        self._unmod_current = name or None
        if name:
            score, note = self._parse_score_note(countries[name].unmod)
            self.fb_score.Value = score
            self.fb_notes.Text = note
        else:
            self.fb_score.Value = 3
            self.fb_notes.Text = ""

    # ---- timing --------------------------------------------------------
    def _sync_button(self) -> None:
        self.startbtn.Text = "Pause" if self.running else "Start"

    def toggle(self) -> None:
        self.running = not self.running
        self._sync_button()
        if self.running:
            self._schedule()
        else:
            # pausing: cancel the pending tick immediately
            if self._tick_id is not None:
                try:
                    self.control.win.after_cancel(self._tick_id)
                except Exception:
                    pass
                self._tick_id = None

    def reset(self) -> None:
        self.running = False
        if self._tick_id is not None:
            try:
                self.control.win.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        if self.has_total:
            used = self._speaker_start_left - self.speaker_left
            self.total_left = min(self.total, self.total_left + used)
        self.speaker_left = getattr(self, "_speaker_start_left",
                                    self.per_speech)
        self._sync_button()
        self._render()

    def _schedule(self) -> None:
        # cancel any pending tick so we never stack two timer chains
        if self._tick_id is not None:
            try:
                self.control.win.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self._tick_id = self.control.win.after(1000, self._tick)

    def _tick(self) -> None:
        self._tick_id = None
        if not self.running:
            return
        self.speaker_left -= 1
        if self.has_total:
            self.total_left -= 1
        self._render()
        self._schedule()


    # ---- speaker flow --------------------------------------------------
    def _start_speaker(self) -> None:
        if self.has_total and self.total_left <= 0:
            self._finish()
            return
        if not self.has_speakers:
            # unmod: single running timer, no speaker cycling
            self.current = None
            self.speaker_left = self.per_speech
            self.running = False
            self._render()
            return
        if self.idx >= len(self.queue):
            self.current = None            # wait for chair to add speakers
            self.speaker_left = self.per_speech
            self._render()
            return
        self.current = self.queue[self.idx]
        self.idx += 1
        write(self.current)          # notify co-chairs a speech is starting
        self.speaker_left = (min(self.per_speech, self.total_left)
                             if self.has_total else self.per_speech)
        self._speaker_start_left = self.speaker_left   # remember allotment
        self.running = False
        self._sync_button()
        self.fb_score.Value = 3
        self.fb_notes.Text = ""
        self._refresh_next()
        self._refresh_control_queue()
        self._render()

    def _save_current_feedback(self) -> None:
        note = self.fb_notes.Text.strip()
        entry = f"{self.fb_score.Value}:{note}" if note else ""
        if self.mode == "unmod":
            name = self.u_ddl.Text or self._unmod_current
            if name:
                countries[name].unmod = entry
                self._unmod_current = name
                broadcast(name)
        elif self.current and entry:
            countries[self.current].mod.append(entry)
            broadcast(self.current)
        data.save(sync=single)      # chair feedback -> main csv

    def _next_speaker(self) -> None:
        self._save_current_feedback()
        if self.mode == "unmod":
            return
        self._start_speaker()

    def _add_speaker(self) -> None:
        name = self.add_ddl.Text
        if name:
            self.queue.append(name)
            if self.current is None:
                self._start_speaker()
            else:
                self._refresh_next()
                self._refresh_control_queue()

    # ---- rendering -----------------------------------------------------
    def _refresh_next(self) -> None:
        if not self.has_speakers:
            return
        self.d_next.clear()
        for n in self.queue[self.idx:]:
            self.d_next.insert_full(self.d_next.count() + 1, [n])
        self.d_next.set_height(max(len(self.queue) - self.idx, 3))

    def _refresh_control_queue(self) -> None:
        if not self.has_speakers:
            return
        for frame in self.speaker_rows:
            frame.destroy()
        self.speaker_rows = []
        for i in range(self.idx, len(self.queue)):
            name = self.queue[i]
            row = self.control.AddRow()
            self.speaker_rows.append(row.frame)
            row.label(name, width=20)
            row.button("Remove", lambda e, idx=i: self._remove_speaker(idx))
        self.control.win.update_idletasks()
        self.control.show()          # re-fit to the new queue

    def _remove_speaker(self, idx: int) -> None:
        if 0 <= idx < len(self.queue):
            self.queue.pop(idx)
            self._refresh_next()
            self._refresh_control_queue()

    def _render(self) -> None:
        if self.has_speakers:
            cur = self.current or "(add a speaker)"
        else:
            cur = ""
        st = format_second(max(self.speaker_left, 0))
        self.d_speaker.Text = f"{cur}   {st}".strip()
        self.c_speaker.Text = f"{cur}   {st}".strip()
        if self.per_speech:
            frac = max(0, min(1, self.speaker_left / self.per_speech))
            self.d_bar.Value = int(frac * 100)
            if frac <= 1/3:
                self.d_bar.Opt("cRed")
            elif frac <= 0.5:
                self.d_bar.Opt("cYellow")
            elif frac <= 2/3:
                self.d_bar.Opt("cGreen")
            else:
                self.d_bar.Opt("cDefault")
        if self.has_total:
            tt = format_second(max(self.total_left, 0))
            self.d_total.Text = f"Total left: {tt}"
            self.c_total.Text = f"Total left: {tt}"
            tfrac = max(0, min(1, self.total_left / self.total))
            self.d_total_bar.Value = int(tfrac * 100)

    # ---- teardown ------------------------------------------------------
    def _finish(self) -> None:
        self.display.Destroy()
        self.control.Destroy()
        self.after()

    def _close(self) -> None:
        self._save_current_feedback()
        self.display.Destroy()
        self.control.Destroy()
        self.after()


def motion() -> None:
    global chair
    assert chair is not None
    ch = chair
    ch.Hide()

    motions: list[Motion] = []
    counter = {"n": 0}
    motion_row_frames: list[tk.Frame] = []

    control = Munager("Motions (control)", font=20,
                      close=lambda: (control.Destroy(),
                                     board.Destroy(), ch.show()))
    board = Munager("Motions", font=30, close=lambda: None)
    control.link_display(board)

    control.AddText("", "Proposer:")
    control.AddDDL("w300 sort vprop", present_countries())
    control.AddText("", "Type / priority:")
    type_ddl = control.AddDDL(
        "w300 vtype",
        ["Text", "MOD", "UNMOD", "Change speaking time / open list"])

    def find(num: int) -> int:
        for i, m in enumerate(motions):
            if m.num == num:
                return i
        return -1

    def rebuild_rows() -> None:
        for frame in motion_row_frames:
            frame.destroy()
        motion_row_frames.clear()
        for m in motions:
            row = control.AddRow()
            motion_row_frames.append(row.frame)
            row.label(f"[{m.priority}]", width=5)
            row.label(m.proposer, width=15)
            row.label(m.text, width=30)
            row.button("Prio", lambda e, mm=m: edit_priority(mm))
            row.button("Time", lambda e, mm=m: edit_time(mm))
            row.button("\u2713", lambda e, mm=m: succeed(mm.num))
            row.button("\u2717", lambda e, mm=m: fail(mm.num))
        control.win.update_idletasks()
        control.show()          # re-fit to new content

    def edit_priority(m: Motion) -> None:
        n = simpledialog.askinteger(
            "munager", f"Priority for '{m.text}'?",
            initialvalue=m.priority, parent=control.win)
        if n is not None:
            m.priority = n
            motions.sort(key=lambda x: x.sort_key())
            reshow()
            rebuild_rows()

    def sort_insert(m: Motion) -> None:
        motions.append(m)
        motions.sort(key=lambda x: x.sort_key())
        reshow()
        rebuild_rows()

    def edit_time(m: Motion) -> None:
        if m.kind not in (2, 3, 4):
            messagebox.showinfo("munager", "This motion type has no timer.")
            return
        tot = ask_time("Total time? (blank to skip) (m:ss)", control.win)
        if tot is not None:
            m.time = tot
        if m.kind in (2, 4):
            per = ask_time("Per-speech time? (m:ss)", control.win)
            if per is not None:
                m.per_speech = per
        motions.sort(key=lambda x: x.sort_key())
        reshow()
        rebuild_rows()

    def reshow() -> None:
        nonlocal board
        board.Destroy()
        board = Munager("Motions", font=30, close=lambda: None)
        control.other = board
        for m in motions:
            board.AddText("w500", m.proposer)
            board.AddText("w900 wrap2", m.text)
        board.show(1)

    def fail(num: int) -> None:
        i = find(num)
        if i < 0:
            return
        motions.pop(i)
        rebuild_rows()
        reshow()

    def succeed(num: int) -> None:
        i = find(num)
        if i < 0:
            return
        m = motions.pop(i)
        motions.clear()                # a passing motion supersedes all others
        rebuild_rows()
        reshow()

        def back() -> None:
            control.show()

        control.Hide()
        board.Hide()

        if m.kind == 1:                       # Text
            back()
        elif m.kind == 2:                     # MOD (per-speaker + total)
            CaucusWindow(m.text, "mod",
                         total=m.time, per_speech=m.per_speech or m.time,
                         use_list=bool(data.settings_read("list")),
                         veto_only=False, after=back)
        elif m.kind == 3:                     # UNMOD (single timer, no speakers)
            CaucusWindow(m.text, "unmod",
                         total=m.time, per_speech=m.time,
                         use_list=False, veto_only=False, after=back)
        elif m.kind == 4:                     # RR / speakers list (no total)
            CaucusWindow(m.text, "open",
                         total=0, per_speech=m.per_speech,
                         use_list=bool(data.settings_read("list")),
                         veto_only=m.veto_only, after=back)
        else:
            back()

    def add_motion() -> None:
        kind = type_ddl.Index          # 1=Text 2=Timer 3=Speaker 4=Change
        if kind == 0:
            messagebox.showerror("munager", "Please select a type.")
            return
        prop = control["prop"].Text

        # --- Change speaking time / open list ---
        veto_only = False
        if kind == 4:
            if not bool(data.settings_read("list")):
                veto_only = messagebox.askyesno(
                    "munager",
                    "Round robin: should ONLY permanent members speak?")
            got = ask_time("Speaking time for this caucus? (m:ss)",
                           control.win)
            if got is None:
                return
            if not veto_only:
                data.settings_write("time", got)
            mode = ("Speakers list" if data.settings_read("list")
                    else "Round Robin")
            text = f"{format_second(got)} {'Veto ' if veto_only else ''}{mode}"
            total_time = 0
            per_speech = got
        else:
            _focus(control.win)
            res = ask_string("Motion / topic text?", control.win)
            if res is None:
                return
            text = res
            total_time = 0
            per_speech = 0
            if kind in (2, 3):  # Timer & Speaker(unmod) need a total time
                tot = ask_time("Total time? (m:ss)", control.win)
                if tot is None:
                    return
                total_time = tot
                text = f"{format_second(tot)} {text}"
            if kind == 2:       # only Timer (mod) needs a per-speech time
                per = ask_time("Individual speaking time? (m:ss)",
                               control.win)
                if per is None:
                    return
                per_speech = per
                text = f"{format_second(per)}/{text}"

        prio = kind             # priority by type index (matches AHK ordering)
        num = counter["n"]
        counter["n"] += 1
        m = Motion(prop, text, prio, total_time, num)
        m.kind = kind
        m.per_speech = per_speech
        m.veto_only = veto_only if kind == 4 else False
        sort_insert(m)

    control.AddButton("", "Add motion", lambda e: add_motion())

    def open_speaking() -> None:
        use_list = bool(data.settings_read("list"))
        st = data.settings_read("time")
        per = int(st) if str(st).isdigit() else 60
        control.Hide()
        board.Hide()
        CaucusWindow("Speaking", "open", total=0, per_speech=per,
                     use_list=use_list, veto_only=False,
                     after=lambda: control.show())

    open_label = ("Open speakers list"
                  if data.settings_read("list") else "Start round robin")
    control.AddButton("", open_label, lambda e: open_speaking())

    control.AddButton("", "Back",
                      lambda e: (control.Destroy(),
                                 board.Destroy(), ch.show()))

    control.show()
    board.show(1)


# ---- chair main menu --------------------------------------------------------

def build_chair() -> None:
    global chair
    chair = Munager("munager", font=30, bold=1,
                    close=lambda: Munager.root().destroy())
    chair.AddButton("Center w500", "Roll call", lambda e: call())
    chair.AddButton("Center w500", "Motions", lambda e: motion())
    chair.AddButton("Center w500", "Vote", lambda e: vote())
    chair.AddButton("Center w500", "Feedback", lambda e: feedback())
    chair.AddButton("Center w500", "Awards", lambda e: awards())
    if single:
        chair.AddButton("Center w500", "Save", lambda e: data.save(sync=single))
        chair.AddButton("Center w500", "Sync (git pull)",
                        lambda e: (data.load(), rebuild_chair()))
    chair.AddButton("Center w500", "Settings", lambda e: settings())
    chair.show()


def rebuild_chair() -> None:
    if chair is not None:
        chair.Destroy()
    build_chair()


# ---- startup ----------------------------------------------------------------

def show_address(addr: str, after: Callable[[], None]) -> None:
    def done() -> None:
        win.Destroy()
        after()

    win = Munager("munager", font=20, close=done)
    win.AddText("w500 Center", "Co-chairs connect to this IP:")
    e = win.AddEdit("wp vaddr", addr)
    win.AddButton("wp", "OK", lambda ev: done())
    win.show()
    txt = cast(tk.Text, e.widget)
    txt.tag_add("sel", "1.0", "end-1c")
    txt.focus_set()

def main() -> None:
    global single
    root = Munager.root()

    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                  "TkHeadingFont", "TkCaptionFont", "TkFixedFont"):
        try:
            tkfont.nametofont(fname).configure(size=22)
        except Exception:
            pass

    networked = messagebox.askyesno(
        "munager", "Run networked (accept remote co-chairs)?")
    if networked:
        single = False
        data.set_mode("online", primary=True)
        if not data._dir():
            data.choose_dir()
        if data.has_data():             # munager.csv already exists -> resume
            data.load()
        else:                           # first run this conference
            data.import_table()
            data.save()
        net.Server(_on_connection).listen(8080, "0.0.0.0")
        root.protocol("WM_DELETE_WINDOW",
                      lambda: (data.save(sync=single), root.destroy()))
        show_address(net.local_ip(), build_chair)   # IP only; menu after close
        mainloop()
        return
    else:
        single = True
        data.set_mode("offline", primary=True)
        if not data._dir():
            data.choose_dir()
        if data.has_data():
            data.load()
        else:
            data.import_table()
            data.save(sync=False)

    build_chair()
    root.protocol("WM_DELETE_WINDOW",
                  lambda: (data.save(sync=single), root.destroy()))
    mainloop()


if __name__ == "__main__":
    main()