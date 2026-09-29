"""Shared feedback UI used by both munager (chair) and feedback (co-chair)."""
from __future__ import annotations

from typing import Any, Callable

from munager_data import countries
from munager_gui import Ctrl, Munager


def parse_entry(entry: str) -> tuple[int, str]:
    """'3:notes' -> (3, 'notes'); tolerant of malformed input."""
    if entry and ":" in entry:
        score, note = entry.split(":", 1)
        try:
            return int(score), note
        except ValueError:
            return 3, entry
    return 3, entry or ""


def make_entry(score: int, note: str) -> str:
    note = note.strip()
    return f"{score}:{note}" if note else ""


def _score(entry: str) -> int:
    try:
        return int(entry.split(":", 1)[0])
    except (ValueError, IndexError):
        return 0


def _scores(entries: list[str]) -> list[int]:
    out: list[int] = []
    for e in entries:
        if e and ":" in e:
            h = e.split(":", 1)[0].strip()
            if h.lstrip("-").isdigit():
                out.append(int(h))
    return out


def awards_rows() -> list[list[Any]]:
    rows: list[list[Any]] = []
    for name, c in countries.items():
        # UNMOD: average across the two chairs (only those who scored)
        unmod_vals = _scores([c.unmod, getattr(c, "unmod_feed", "") or ""])
        unmod = sum(unmod_vals) / len(unmod_vals) if unmod_vals else 0.0

        # MOD: every speech from both chairs counts (two scores per speech)
        speeches = _scores(list(c.mod) + list(getattr(c, "mod_feed", []) or []))
        n = len(speeches)
        avg = sum(speeches) / n if n else 0.0
        var = (sum(s * s for s in speeches) / n - avg * avg) if n else None

        total = avg + unmod
        rows.append([
            name,
            round(total, 2),
            round(avg, 2),
            round(unmod, 2),
            round(abs(avg - unmod), 2),
            "inf" if var is None else round(var, 2),
            avg,                      # hidden sort helper (speech tiebreak)
        ])

    # sort: total desc, then speech avg desc; stable, numeric
    rows.sort(key=lambda r: (r[1], r[6]), reverse=True)
    for r in rows:
        r.pop()                       # drop the hidden helper column
    return rows


def speech_feedback(country: str,
                    get_unmod: Callable[[], str],
                    add_mod: Callable[[str], None],
                    on_saved: Callable[[], None],
                    initial: str = "") -> Munager:
    """One speech's feedback (score + notes). `add_mod(entry)` stores it."""
    score0, note0 = parse_entry(initial)

    score: Ctrl
    notes: Ctrl

    def save_and_close() -> None:
        entry = make_entry(score.Value, notes.Value)
        add_mod(entry)
        on_saved()
        win.Destroy()

    win = Munager("Speech feedback", font=30, close=save_and_close)
    win.AddText(country, width=500)
    win.AddText("Score (1-5):")
    score = win.AddUpDown(score0)
    win.AddText("Notes:")
    notes = win.AddEdit(note0, rows=4)
    win.AddButton("Save", event=lambda e: save_and_close())
    win.show()
    return win


def awards_window(on_back: Callable[[], None]) -> Munager:
    cols = ["Country", "Total", "Speech", "UNMOD", "Diff", "Speech dev"]
    data_rows = awards_rows()
    win = Munager("Awards info", font=20, close=on_back)
    lv = win.AddListView(cols, data_rows)
    lv.set_height(len(data_rows))
    lv.fit_columns()
    win.AddButton("Back", event=lambda e: on_back())
    win.show()
    return win


def feedback_viewer(country: str, on_back: Callable[[], None],
                    own_is_secondary: bool = False) -> Munager:
    c = countries[country]
    if own_is_secondary:
        own_u, own_m = c.unmod_feed, c.mod_feed
        oth_u, oth_m = c.unmod, c.mod
    else:
        own_u, own_m = c.unmod, c.mod
        oth_u, oth_m = c.unmod_feed, c.mod_feed

    win = Munager("Feedback", font=30, close=on_back)
    win.AddText(country, width=500)

    if own_u or oth_u:
        win.AddText("UNMOD:")
        if own_u:
            s, n = parse_entry(own_u)
            win.AddText(f"  chair: {s}  {n}")
        if oth_u:
            s, n = parse_entry(oth_u)
            win.AddText(f"  co-chair: {s}  {n}")
    else:
        win.AddText("UNMOD: -")

    speeches = max(len(own_m), len(oth_m))
    if speeches:
        win.AddText("MOD feedback:")
        for i in range(speeches):
            oe = own_m[i] if i < len(own_m) else ""
            xe = oth_m[i] if i < len(oth_m) else ""
            win.AddText(f"Speech {i + 1}:")
            if oe:
                s, n = parse_entry(oe)
                win.AddText(f"  chair: {s}  {n}")
            if xe:
                s, n = parse_entry(xe)
                win.AddText(f"  co-chair: {s}  {n}")
    else:
        win.AddText("No MOD feedback.")

    win.AddButton("Back", event=lambda e: on_back())
    win.show()
    return win
