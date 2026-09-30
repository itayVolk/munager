"""Shared feedback UI used by both munager (chair) and feedback (co-chair)."""
from __future__ import annotations

from typing import Any, Callable

from munager_proto import Feedback
from munager_data import countries
from munager_gui import Ctrl, Munager


def awards_rows() -> list[list[Any]]:
    rows: list[list[Any]] = []
    for name, c in countries.items():
        rows.append([
            name,
            round(c.total, 2),
            round(c.speech, 2),
            round(c.unmod_score, 2),
            round(c.diff, 2),
            round(c.speech_dev, 2),
            c.speech,                      # hidden sort helper (speech tiebreak)
        ])

    # sort: total desc, then speech avg desc; stable, numeric
    rows.sort(key=lambda r: (r[1], r[6]), reverse=True)
    for r in rows:
        r.pop()                       # drop the hidden helper column
    return rows


def speech_feedback(country: str,
                    add_mod: Callable[[Feedback], None],
                    on_saved: Callable[[], None],
                    score0: int = -1, note0: str = "",) -> Munager:
    """One speech's feedback (score + notes). `add_mod(entry)` stores it."""
    score: Ctrl
    notes: Ctrl

    def save_and_close() -> None:
        entry = Feedback(score=score.Value, note=notes.Value)
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


def feedback_viewer(country: str, on_back: Callable[[], None]) -> Munager:
    c = countries[country]
    own_u, own_m = c.unmod, c.mod
    oth_u, oth_m = c.unmod_feed, c.mod_feed

    win = Munager("Feedback", font=30, close=on_back)
    win.AddText(country, width=500)

    if own_u or oth_u:
        win.AddText("UNMOD:")
        if own_u:
            win.AddText(f"  chair: {own_u}")
        if oth_u:
            win.AddText(f"  co-chair: {oth_u}")
    else:
        win.AddText("UNMOD: -")

    speeches = max(len(own_m), len(oth_m))
    if speeches:
        win.AddText("MOD feedback:")
        for i in range(speeches):
            oe = own_m[i] if i < len(own_m) else None
            xe = oth_m[i] if i < len(oth_m) else None
            win.AddText(f"Speech {i + 1}:")
            if oe:
                win.AddText(f"  chair: {oe}")
            if xe:
                win.AddText(f"  co-chair: {xe}")
    else:
        win.AddText("No MOD feedback.")

    win.AddButton("Back", event=lambda e: on_back())
    win.show()
    return win
