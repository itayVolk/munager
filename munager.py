from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox, simpledialog
import tkinter.font as tkfont
from typing import Any, Callable, Optional

from munager_proto import (CountryDelta, Feedback, FullState, Hello, Power, Presence, PresenceDTO,
                           PresenceSync, SpeechStart, decode, encode)
import munager_data as data
import munager_net as net
from munager_data import countries
from munager_gui import Ctrl, Munager, mainloop
from munager_feedback_ui import awards_window, feedback_viewer

# ---- globals ----------------------------------------------------------------
server_clients: list[net.LengthSocket] = []
chair: Optional[Munager] = None
speakers_list: list[str] = []
quick: Optional[Munager] = None          # persistent quick-edit window
list_caucus_active: bool = False         # a speakers-list caucus is running


# ---- helpers ----------------------------------------------------------------

def format_second(s: int) -> str:
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


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
    return sorted(n for n, c in countries.items() if c.presence)


# ---- networking -------------------------------------------------------------
def broadcast(country: str) -> None:
    c = countries.get(country)
    if c is None:
        return
    payload = encode(CountryDelta(c))
    for cli in list(server_clients):
        cli.write(payload)


def write(text: str) -> None:
    """Send a raw feedback message to all connected co-chairs."""
    for cli in list(server_clients):
        cli.write(encode(SpeechStart(text)))


def full_state() -> FullState:
    """The entire model as a wire message (initial co-chair sync)."""
    return FullState(list(countries.values()))


def _on_client_data(cli: net.LengthSocket, raw: bytes) -> None:
    msg = decode(raw)
    if isinstance(msg, Hello):
        cli.write(encode(full_state()))
    elif isinstance(msg, CountryDelta):
        d = msg.country
        c = countries.get(d.name)
        if c is None:
            c = data.Country(d.name)
            countries[d.name] = c
        # co-chair's own feedback (its unmod/mod) lands in the *_feed slots
        c.unmod_feed = d.unmod
        c.mod_feed = list(d.mod)
        data.save()
    # (primary ignores FullState/PresenceSync/SpeechStart echoes)


def _on_connection(cli: net.LengthSocket) -> None:
    server_clients.append(cli)
    cli.on("data", lambda raw, cli=cli: _on_client_data(cli, raw))
    cli.write(encode(full_state()))


# ---- feedback display -------------------------------------------------------


def feedback() -> None:
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
    country = select.AddDDL(sorted_countries(), width=500, sort=True)
    select.AddButton("Select", event=lambda e: chosen(country))
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
    """Push every country's presence/power to co-chairs (roll-call sync)."""
    payload = encode(PresenceSync(
        [PresenceDTO(name, c.presence, c.power)
         for name, c in countries.items()]))
    for cli in list(server_clients):
        cli.write(payload)


def call() -> None:
    assert chair is not None
    ch = chair
    ch.Hide()
    if quick is not None and quick.win.winfo_exists():
        quick.Hide()                    # closed during roll call

    control = Munager("Roll call (control)", font=20,
                      close=lambda: (submit(), ch.show()))
    display = Munager("Roll call (display)", font=30, close=lambda: None)
    control.link_display(display)

    order = sorted_countries()
    rows: dict[str, dict[str, Ctrl]] = {}

    def counts() -> dict[str, int]:
        present = sum(1 for n in order if countries[n].presence)
        voting = sum(1 for n in order if countries[n].presence == Presence.PRESENT_VOTING)
        present_nonobs = sum(1 for n in order
                             if countries[n].presence
                             and countries[n].power != Power.OBSERVER)
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
            tag = str(countries[n].power)
            label = f"{n} ({tag})" if tag else n
            d_view.insert_full(d_view.count() + 1,
                               [label, str(countries[n].presence)])
        d_view.set_height(len(order))

    def set_state(name: str, state: Presence) -> None:
        countries[name].presence = state
        r = rows[name]
        r["abs"].widget["relief"] = "sunken" if state else "raised"
        r["pre"].widget["relief"] = "sunken" if state == Presence.PRESENT else "raised"
        if "vot" in r:
            r["vot"].widget["relief"] = "sunken" if state == Presence.PRESENT_VOTING else "raised"
        refresh_display()

    c_summary = control.AddText("", width=700)

    for name in order:
        c = countries[name]
        row = control.AddRow()
        tag = str(c.power)
        row.label(f"{name}  ({tag})" if tag else name, width=24)
        rm: dict[str, Ctrl] = {}
        rm["abs"] = row.button("Absent", lambda e, n=name: set_state(n, Presence.ABSENT))
        rm["pre"] = row.button("Present", lambda e, n=name: set_state(n, Presence.PRESENT))
        # observers/permanent may not be "Present & Voting"
        if not c.power:
            rm["vot"] = row.button("Present & Voting",
                                   lambda e, n=name: set_state(n, Presence.PRESENT_VOTING))
        rows[name] = rm

    def submit() -> None:
        data.save()
        broadcast_presence()          # sync roll call to co-chairs
        control.Destroy()
        display.Destroy()
        if quick is not None:
            quick.show()                # reopen the companion panel
        _refresh_quick()                # sync to new presences
        ch.show()

    control.AddButton("Submit", event=lambda e: submit())

    summary = display.AddText("")
    d_view = display.AddListView(["Country", "Status"])

    for name in order:
        set_state(name, countries[name].presence)

    control.show()
    display.show(1)


# ---- settings ---------------------------------------------------------------

def settings() -> None:
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
            if data.choose_file():
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
            _refresh_quick()          # update add-to-list availability live
            reopen()

        def toggle_tip() -> None:
            data.settings_write("tip", "" if tip_on else "1")
            reopen()

        # file
        r = view.AddRow()
        r.label("Save file: " + (data._get_file() or "(none)"))
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

        view.AddButton("Back", event=lambda e: (view.Destroy(), ch.show()))
        view.show()

    build()


def add_countries(parent: Munager) -> None:
    parent.Hide()
    entry = Munager("Add countries", font=20,
                    close=lambda: (entry.Destroy(), parent.show()))
    entry.AddText("Country name:", width=400)
    name = entry.AddEdit()
    entry.AddText("Type:")
    type = entry.AddDDL(["Normal (can vote)", "Veto holder", "Observer"])

    def add_one() -> None:
        name_val = name.Text.strip()
        if not name_val:
            messagebox.showerror("munager", "Enter a country name.")
            return
        if name_val in countries:
            messagebox.showerror("munager", f"{name_val} already exists.")
            return
        ctype = {2: Power.VETO, 3: Power.OBSERVER}.get(type.Index, Power.NONE)
        c = data.Country(name_val)
        c.power = ctype
        c.presence = Presence.ABSENT
        countries[name_val] = c
        name.Text = ""
        messagebox.showinfo("munager", f"Added {name_val}.")

    def done() -> None:
        data.save()
        entry.Destroy()
        parent.show()

    entry.AddButton("Add", event=lambda e: add_one())
    entry.AddButton("Done (save)", event=lambda e: done())
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


# ---- voting -----------------------------------------------------------------
def vote() -> None:
    assert chair is not None
    ch = chair
    ch.Hide()

    veto_setting = data.settings_read("veto")
    veto_needed = int(veto_setting) if str(veto_setting).isdigit() else 0

    voters = [n for n in sorted_countries()
              if countries[n].presence and countries[n].power != Power.OBSERVER]

    state = {"i": 0, "yes": 0, "no": 0, "abstain": 0, "veto": 0}
    deferred: list[str] = []
    phase = {"n": 1}

    control = Munager("Roll call vote (control)", font=20,
                      close=lambda: (control.Destroy(),
                                     display.Destroy(), ch.show()))
    display = Munager("Roll call vote (display)", font=40, bold=1,
                      close=lambda: None)
    control.link_display(display)

    cur = display.AddText("", width=600)
    total = display.AddText("", width=600)

    def queue() -> list[str]:
        return voters if phase["n"] == 1 else deferred

    def current_name() -> Optional[str]:
        q = queue()
        return q[state["i"]] if state["i"] < len(q) else None

    def abstain_allowed(name: str) -> bool:
        return countries[name].presence != Presence.PRESENT_VOTING

    def update_total() -> None:
        total.Text = (f'For: {state["yes"]}   Against: {state["no"]}   '
                      f'Abstain: {state["abstain"]}   Veto: {state["veto"]}')

    def finish() -> None:
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

    passed_btn: Ctrl

    def advance() -> None:
        q = queue()
        if state["i"] >= len(q):
            if phase["n"] == 1 and deferred:
                phase["n"] = 2
                state["i"] = 0
                passed_btn.widget["state"] = "disabled"
            else:
                finish()
                return
        show_current()

    def cast(kind: str) -> None:
        name = current_name()
        if name is None:
            return
        if kind == "abstain" and not abstain_allowed(name):
            return
        state[kind] += 1
        if kind == "no" and countries[name].power == Power.VETO:
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
        cur_ctrl.Text = (f"[DEFERRED] {name}" if phase["n"] == 2 else name)
        abtstain_btn.widget["state"] = (
            "normal" if abstain_allowed(name) else "disabled")
        passed_btn.widget["state"] = (
            "disabled" if phase["n"] == 2 else "normal")
        control.win.update_idletasks()
        control.show()

    widest = max((len(n) for n in voters), default=10) + 12
    cur_ctrl = control.AddText("", width=widest * 12)
    control.AddButton("For", event=lambda e: cast("yes"))
    abtstain_btn = control.AddButton("Abstain", event=lambda e: cast("abstain"))
    control.AddButton("Against", event=lambda e: cast("no"))
    passed_btn = control.AddButton("Pass", event=lambda e: do_pass())

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
        if mode == "open":  # non-speakers list/round robin: empty queue initially
            if not use_list:  # round robin auto-fills
                pool = present_countries()
                if veto_only:
                    pool = [n for n in pool if countries[n].power == Power.VETO]
                random.shuffle(pool)
                self.queue = pool
            elif self.has_speakers:
                self.queue = speakers_list          # persistent, chair-filled
        self.veto_only = veto_only
        self.idx = 0
        # flag: a speakers-list caucus is live (blocks quick-edit list adds)
        global list_caucus_active
        self._is_list_caucus = (self.has_speakers and use_list
                                and mode == "open")
        if self._is_list_caucus:
            list_caucus_active = True
            _refresh_quick()

        # ---- display window ----
        self.display = Munager(f"{title} (display)", font=40, bold=1,
                               close=lambda: None)
        self.d_name = self.display.AddText(title, width=900)
        self.d_speaker = self.display.AddText("", width=900)
        self.d_bar = self.display.AddProgress(width=900)
        if self.has_total:
            self.d_total = self.display.AddText("", width=900)
            self.d_total_bar = self.display.AddProgress(width=900)
        if self.has_speakers:
            self.display.AddText("Up next:", width=900)
            self.d_next = self.display.AddListView(["Next speakers"])

        # ---- control window ----
        self.control = Munager(f"{title} (control)", font=22,
                               close=self._close)
        self.c_speaker = self.control.AddText("", width=500)
        if self.has_total:
            self.c_total = self.control.AddText("", width=500)
        crow = self.control.AddRow()
        self.startbtn = crow.button("Start", lambda e: self.toggle())
        self._sync_button()
        crow.button("Reset", lambda e: self.reset())

        if self.has_speakers:
            self.control.AddText("Add speaker:")
            arow = self.control.AddRow()
            pool = present_countries()
            if self.veto_only:
                pool = [n for n in pool if countries[n].power == Power.VETO]
            self.add_ddl = self.control.AddDDL(pool, width=300, sort=True)
            arow.button("Add", lambda e: self._add_speaker())
            # full queue on the control screen with remove buttons
            self.control.AddText("Speakers:")
            self.speaker_rows: list[tk.Frame] = []
            self.sp_holder = self.control.AddRow()   # container marker

        # inline feedback
        if self.mode == "unmod":
            self.control.AddText("Delegate:")
            self.u_ddl = self.control.AddDDL(present_countries(), width=300, sort=True,
                                             event=lambda c: self._unmod_switch())
            self._unmod_current: Optional[str] = None
        self.control.AddText("Score (1-5):")
        self.fb_score = self.control.AddUpDown(3)
        self.control.AddText("Notes:")
        self.fb_notes = self.control.AddEdit("", rows=3)

        next_label = "Next speaker" if self.has_speakers else "Save feedback"
        self.control.AddButton(next_label,
                               event=lambda e: self._next_speaker())

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

    def _unmod_switch(self) -> None:
        prev = self._unmod_current
        if prev:
            note = self.fb_notes.Text.strip()
            fb = Feedback(self.fb_score.Value, note)
            if fb:                              # score>=1 AND note present
                countries[prev].unmod = fb
                broadcast(prev)
                data.save()
        name = self.u_ddl.Text
        self._unmod_current = name or None
        if name:
            cur = countries[name].unmod
            self.fb_score.Value = cur.score if cur.score >= 1 else 3
            self.fb_notes.Text = cur.note
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
        entry = Feedback(score=self.fb_score.Value, note=note)
        if self.mode == "unmod":
            name = self.u_ddl.Text or self._unmod_current
            if name and entry:                   # match mod-speech policy
                countries[name].unmod = entry
                self._unmod_current = name
                broadcast(name)
        elif self.current and entry:
            countries[self.current].mod.append(entry)
            broadcast(self.current)
        data.save()      # chair feedback -> main JSON

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
            if frac <= 1 / 3:
                self.d_bar.Opt("cRed")
            elif frac <= 0.5:
                self.d_bar.Opt("cYellow")
            elif frac <= 2 / 3:
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
        _clear_list_caucus(self)
        self.display.Destroy()
        self.control.Destroy()
        self.after()

    def _close(self) -> None:
        self._save_current_feedback()
        _clear_list_caucus(self)
        self.display.Destroy()
        self.control.Destroy()
        self.after()


def motion() -> None:
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

    prop_ctrl = control.AddText("Proposer:")
    control.AddDDL(present_countries(), width=300, sort=True)
    control.AddText("Type / priority:")
    _list = bool(data.settings_read("list"))
    type_ddl = control.AddDDL(["Text", "MOD", "UNMOD",
                               "Open speakers list" if _list else "Change RR time"],
                              width=300)

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
            board.AddText(m.proposer, width=500)
            board.AddText(m.text, width=900, clamp2=True)
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
        prop = prop_ctrl.Text

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

    control.AddButton("Add motion", event=lambda e: add_motion())

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
    control.AddButton(open_label, event=lambda e: open_speaking())

    control.AddButton("Back", event=lambda e: (control.Destroy(), board.Destroy(), ch.show()))

    control.show()
    board.show(1)


# ---- quick edit (presence / speakers list) ----------------------------------
def _clear_list_caucus(cw: "CaucusWindow") -> None:
    global list_caucus_active
    if getattr(cw, "_is_list_caucus", False):
        list_caucus_active = False
        _refresh_quick()


_quick_state: dict[str, Any] = {"sel": None}


def _refresh_quick() -> None:
    """Rebuild the quick-edit body if the window is open."""
    if quick is not None and quick.win.winfo_exists():
        _quick_build()


def quick_hide() -> None:
    """Hide the quick-edit panel (it can be reopened; menu is unaffected)."""
    if quick is not None:
        quick.Hide()


def _quick_counts_text() -> str:
    names = list(countries)
    pres = sum(1 for n in names if countries[n].presence)
    pno = sum(1 for n in names
              if countries[n].presence and countries[n].power != Power.OBSERVER)
    reg = pres // 2 + 1
    two_thirds = -(-2 * pres // 3)
    vote_maj = pno // 2 + 1
    return (f"Present: {pres}    Present (excl. observers): {pno}\n"
            f"Regular majority: {reg}    2/3 majority: {two_thirds}    "
            f"Voting majority: {vote_maj}")


def _quick_build() -> None:
    """(Re)draw the quick-edit contents based on the live setting/state."""
    global quick
    prev_sel = _quick_state.get("sel")

    # recreate the window fresh (Munager has no Clear(); reusing a destroyed
    # body raises 'bad window path name')
    if quick is not None:
        try:
            quick.Destroy()
        except Exception:
            pass
    quick = Munager("Quick edit", font=20, close=lambda: quick_hide())

    use_list = bool(data.settings_read("list"))

    summary = quick.AddText(_quick_counts_text(), width=700)

    quick.AddText("Country:")
    ddl = quick.AddDDL(sorted_countries(), width=320, sort=True,
                       event=lambda c: refresh_selection())
    power = quick.AddText("Power: —", width=700)

    prow = quick.AddRow()
    b_abs = prow.button("Absent", lambda e: set_pres(Presence.ABSENT))
    b_pre = prow.button("Present", lambda e: set_pres(Presence.PRESENT))
    b_vot = prow.button("Present & Voting", lambda e: set_pres(Presence.PRESENT_VOTING))

    add_btn = quick.AddButton("Add to speakers list", event=lambda e: add_to_list())

    # ---- behaviour ----
    def selected() -> Optional[str]:
        name = ddl.Text
        return name if name in countries else None

    def refresh_selection() -> None:
        name = selected()
        _quick_state["sel"] = name
        if name is None:
            power.Text = "Power: —"
            for b in (b_abs, b_pre, b_vot):
                b.widget["state"] = "disabled"
                b.widget["relief"] = "raised"
            add_btn.widget["state"] = "disabled"
            summary.Text = _quick_counts_text()
            return
        c = countries[name]
        power.Text = f"Power: {str(c.power)}"

        b_abs.widget["state"] = "normal"
        b_pre.widget["state"] = "normal"
        b_vot.widget["state"] = "disabled" if c.power else "normal"
        b_abs.widget["relief"] = "sunken" if not c.presence else "raised"
        b_pre.widget["relief"] = "sunken" if c.presence == Presence.PRESENT else "raised"
        b_vot.widget["relief"] = "sunken" if c.presence == Presence.PRESENT_VOTING else "raised"

        can_add = use_list and c.presence and not list_caucus_active
        add_btn.widget["state"] = "normal" if can_add else "disabled"
        summary.Text = _quick_counts_text()

    def set_pres(state: Presence) -> None:
        name = selected()
        if name is None:
            messagebox.showerror("munager", "Pick a country first.")
            return
        c = countries[name]
        if state == Presence.PRESENT_VOTING and c.power:
            return                      # guarded by disabled button anyway
        c.presence = state
        data.save()
        broadcast_presence()
        refresh_selection()

    def add_to_list() -> None:
        name = selected()
        if name is None:
            return
        if not (bool(data.settings_read("list"))
                and countries[name].presence
                and not list_caucus_active):
            return
        speakers_list.append(name)

    # restore prior selection if still valid
    if prev_sel and prev_sel in countries:
        ddl.Text = prev_sel
    refresh_selection()

    quick.show()
    quick.win.update_idletasks()
    quick.win.minsize(600, quick.win.winfo_height())
    # pin to the far left of the primary screen
    h = quick.win.winfo_height()
    w = quick.win.winfo_width()
    sh = quick.win.winfo_screenheight()
    y = (sh - h) // 2
    quick.win.geometry(f"{w}x{h}+50+{y}")


# ---- chair main menu --------------------------------------------------------

def build_chair() -> None:
    global chair
    chair = Munager("munager", font=30, bold=1,
                    close=lambda: Munager.root().destroy())
    chair.AddButton("Roll call", event=lambda e: call())
    chair.AddButton("Motions", event=lambda e: motion())
    chair.AddButton("Vote", event=lambda e: vote())
    chair.AddButton("Feedback", event=lambda e: feedback())
    chair.AddButton("Awards", event=lambda e: awards())
    chair.AddButton("Settings", event=lambda e: settings())
    chair.show()
    chair.win.update_idletasks()
    h = chair.win.winfo_height()
    chair.win.minsize(600, h)          # force a wide menu


def rebuild_chair() -> None:
    if chair is not None:
        chair.Destroy()
    build_chair()
    _refresh_quick()


def _start_chair() -> None:
    build_chair()
    _quick_build()          # persistent companion, opens with the menu


# ---- startup ----------------------------------------------------------------

def show_address(addrs: list[str], after: Callable[[], None]) -> None:
    def done() -> None:
        win.Destroy()
        after()

    win = Munager("munager", font=20, close=done)
    win.AddText("Co-chairs connect to this IP:", width=400)
    lines = [addr.strip() for addr in addrs] if addrs else \
            ["(no network address found)"]
    text = "\n".join(lines)
    longest = max((len(x) for x in lines), default=20)
    win.AddEdit(text, rows=len(lines), width=longest + 2, disabled=True, select_on_focus=True)
    win.AddButton("OK", event=lambda ev: done())
    win.show()


def main() -> None:
    root = Munager.root()

    for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                  "TkHeadingFont", "TkCaptionFont", "TkFixedFont"):
        try:
            tkfont.nametofont(fname).configure(size=22)
        except Exception:
            pass

    if not data.has_data():
        if not data.choose_file():
            root.destroy()
            return
    data.load()
    if not countries:
        data.import_table()
        data.save()
    net.Server(_on_connection).listen(8080, "0.0.0.0")
    root.protocol("WM_DELETE_WINDOW", lambda: (data.save(), root.destroy()))
    show_address(net.all_ipv4(), _start_chair)   # hotspot IP included
    mainloop()


if __name__ == "__main__":
    main()
