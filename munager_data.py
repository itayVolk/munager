from __future__ import annotations

import configparser
import csv
import os
import sys
import statistics
import subprocess
from typing import Any, Optional


def _config_home() -> str:
    """A stable, writable per-user folder that survives runs (all OSes)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:  # Linux / other
        base = (os.environ.get("XDG_CONFIG_HOME")
                or os.path.expanduser("~/.config"))
    d = os.path.join(base, "munager")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


# Bootstrap ini in a STABLE per-user folder (PyInstaller/one-file safe).
BOOTSTRAP_INI = os.path.join(_config_home(), "munager_boot.ini")
BOOT_SECTION = "boot"

# The real settings ini lives INSIDE the working directory.
SECTION = "settings"


def _boot_config() -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    if os.path.exists(BOOTSTRAP_INI):
        cp.read(BOOTSTRAP_INI, encoding="utf-8")
    if not cp.has_section(BOOT_SECTION):
        cp.add_section(BOOT_SECTION)
    return cp


def _get_dir() -> str:
    cp = _boot_config()
    return cp.get(BOOT_SECTION, "dir", fallback="")


def _set_dir(d: str) -> None:
    cp = _boot_config()
    cp.set(BOOT_SECTION, "dir", d)
    with open(BOOTSTRAP_INI, "w", encoding="utf-8") as f:
        cp.write(f)


def _ini_path() -> str:
    d = _get_dir()
    return os.path.join(d, "munager.ini") if d else BOOTSTRAP_INI


# Shared model, mirroring the AHK global `countries` map.
countries: dict[str, "Country"] = {}

# --- persistence mode --------------------------------------------------------
# "online"  : chairs communicate directly. Only munager.py (the primary)
#             writes, and it writes exactly ONE file. The co-chair streams its
#             feedback over the socket; the primary folds it into that one file.
# "offline" : no direct comms. Each chair writes its OWN file (primary.csv /
#             secondary.csv) so git can merge the two sides without conflicts.
mode: str = "offline"

# In offline mode, which side is THIS process:
#   True  -> primary   (owns primary.csv,   reads secondary.csv)
#   False -> secondary (owns secondary.csv, reads primary.csv)
is_primary: bool = True


def set_mode(m: str, primary: bool = True) -> None:
    global mode, is_primary
    mode = m
    is_primary = primary


def _score_of(entry: str) -> Optional[int]:
    if ":" in entry:
        head = entry.split(":", 1)[0].strip()
        if head.isdigit():
            return int(head)
    return None


def _decode(cell: str) -> str:
    return cell.replace("``n", "\r\n").replace("``c", ",").strip(" \t\r\n")


class Country:
    """One delegation.

    Feedback is stored per chair:
        unmod       / mod        -> the PRIMARY chair's feedback
        unmod_feed  / mod_feed   -> the SECONDARY (co-)chair's feedback

    Every speech and the general unmod carry feedback from each chair.
    """

    def __init__(self, name: str) -> None:
        self.name: str = name
        self.type: str = ""                 # power flag ('', 'O', 'V')
        self.stat: str = ""                 # presence  ('', 'P', 'V')
        self.unmod: str = ""                # primary chair unmod feedback
        self.mod: list[str] = []            # primary chair mod speeches
        self.unmod_feed: str = ""           # secondary chair unmod feedback
        self.mod_feed: list[str] = []       # secondary chair mod speeches

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    # --- awards metrics (combined across both chairs) ---
    @property
    def _mod_scores(self) -> list[int]:
        out: list[int] = []
        for s in (*self.mod, *self.mod_feed):
            v = _score_of(s)
            if v is not None:
                out.append(v)
        return out

    @property
    def _unmod_scores(self) -> list[int]:
        out: list[int] = []
        for s in (self.unmod, self.unmod_feed):
            v = _score_of(s)
            if v is not None:
                out.append(v)
        return out

    @property
    def speech(self) -> float:
        s = self._mod_scores
        return sum(s) / len(s) if s else 0.0

    @property
    def unmod_score(self) -> float:
        s = self._unmod_scores
        return sum(s) / len(s) if s else 0.0

    @property
    def total(self) -> float:
        return self.speech + self.unmod_score

    @property
    def diff(self) -> float:
        return abs(self.speech - self.unmod_score)

    @property
    def speech_dev(self) -> float:
        s = self._mod_scores
        if not s:
            return float("inf")
        return statistics.pstdev(s) if len(s) > 1 else 0.0


# --- settings (.ini) ---------------------------------------------------------

def _config() -> configparser.ConfigParser:
    cp = configparser.ConfigParser()
    path = _ini_path()
    if os.path.exists(path):
        cp.read(path, encoding="utf-8")
    if not cp.has_section(SECTION):
        cp.add_section(SECTION)
    return cp


def settings_write(key: str, val: Any) -> Any:
    cp = _config()
    cp.set(SECTION, key, str(val))
    with open(_ini_path(), "w", encoding="utf-8") as f:
        cp.write(f)
    return val


def settings_read(key: str) -> str:
    cp = _config()
    try:
        return cp.get(SECTION, key)
    except (configparser.NoOptionError, configparser.NoSectionError):
        return ""


# --- paths -------------------------------------------------------------------

def _dir() -> str:
    """The working directory (a folder the user picks once; may be a git repo)."""
    return _get_dir()


def _online_file() -> str:
    return os.path.join(_dir(), "munager.csv") if _dir() else ""


def _primary_file() -> str:
    return os.path.join(_dir(), "primary.csv") if _dir() else ""


def _secondary_file() -> str:
    return os.path.join(_dir(), "secondary.csv") if _dir() else ""


def _git_dir() -> Optional[str]:
    d = _dir()
    if d and os.path.exists(os.path.join(d, ".git")):
        return d
    return None


def _normalize_type(raw: str) -> str:
    r = raw.strip().lower()
    if r == "o":
        return "O"
    if r in ("p", "v"):
        return "V"
    return ""


# --- CSV row (de)serialisation ----------------------------------------------
# A single row fully describes one country's four-way feedback, using an
# in-cell separator so the whole model round-trips through ONE file (online).
#
# Row layout (online, one file):
#   name, type, stat, unmod, unmod_feed, mod..., "|", mod_feed...
# The "|" sentinel splits the primary mod list from the secondary mod list.

MOD_SPLIT = "|"


def _row_full(c: "Country") -> list[str]:
    row = [c.name, c.type, c.stat, c.unmod, c.unmod_feed]
    row.extend(c.mod)
    row.append(MOD_SPLIT)
    row.extend(c.mod_feed)
    return row


def _parse_full(row: list[str]) -> Optional["Country"]:
    if not row or not row[0].strip():
        return None
    c = Country(row[0].strip())
    c.type = _normalize_type(row[1]) if len(row) > 1 else ""
    c.stat = _decode(row[2]).upper() if len(row) > 2 else ""
    c.unmod = _decode(row[3]) if len(row) > 3 else ""
    c.unmod_feed = _decode(row[4]) if len(row) > 4 else ""
    rest = row[5:]
    if MOD_SPLIT in rest:
        k = rest.index(MOD_SPLIT)
        c.mod = [_decode(x) for x in rest[:k] if x.strip()]
        c.mod_feed = [_decode(x) for x in rest[k + 1:] if x.strip()]
    else:
        c.mod = [_decode(x) for x in rest if x.strip()]
    return c


# Offline half-rows: each side stores only ITS OWN feedback, so git never sees
# the same file edited by both chairs.

def _row_half(c: "Country", primary: bool) -> list[str]:
    if primary:
        return [c.name, c.type, c.stat, c.unmod, *c.mod]
    return [c.name, c.unmod_feed, *c.mod_feed]


def _apply_primary(row: list[str]) -> None:
    if not row or not row[0].strip():
        return
    name = row[0].strip()
    c = countries.get(name) or Country(name)
    c.type = _normalize_type(row[1]) if len(row) > 1 else c.type
    c.stat = _decode(row[2]).upper() if len(row) > 2 else c.stat
    c.unmod = _decode(row[3]) if len(row) > 3 else ""
    c.mod = [_decode(x) for x in row[4:] if x.strip()]
    countries[name] = c


def _apply_secondary(row: list[str]) -> None:
    if not row or not row[0].strip():
        return
    name = row[0].strip()
    c = countries.get(name)
    if c is None:                       # secondary may know a country first
        c = Country(name)
        countries[name] = c
    c.unmod_feed = _decode(row[1]) if len(row) > 1 else ""
    c.mod_feed = [_decode(x) for x in row[2:] if x.strip()]


# --- load --------------------------------------------------------------------

def _read_csv(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.reader(f)]


def _write_csv(path: str, rows: list[list[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


def _git_pull() -> None:
    g = _git_dir()
    if g:
        try:
            subprocess.run(["git", "pull"], cwd=g, check=False,
                           stdin=subprocess.DEVNULL, timeout=30,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


def _git_push(fname: str, label: str) -> None:
    g = _git_dir()
    if not g:
        return
    try:
        subprocess.run(["git", "commit", "--only", fname,
                        "-m", f"saved {label} data"], cwd=g, check=False)
        subprocess.run(["git", "push"], cwd=g, check=False)
    except FileNotFoundError:
        pass


def load() -> None:
    """Load the full model according to the current mode."""
    if mode == "online":
        f = _online_file()
        countries.clear()
        if f and os.path.exists(f):
            for row in _read_csv(f):
                c = _parse_full(row)
                if c is not None:
                    countries[c.name] = c
        return

    # offline: pull, then merge BOTH half-files into one in-memory model
    _git_pull()
    countries.clear()
    p, s = _primary_file(), _secondary_file()
    if p and os.path.exists(p):
        for row in _read_csv(p):
            _apply_primary(row)
    if s and os.path.exists(s):
        for row in _read_csv(s):
            _apply_secondary(row)


# --- save --------------------------------------------------------------------

def save(sync: bool = True) -> None:
    """Persist the model.

    online : ONLY the primary writes, and only ONE file (munager.csv).
    offline: THIS side writes ONLY its own half-file, then git-syncs it,
             so the two chairs never touch the same file.
    """
    if mode == "online":
        if not is_primary:
            return                          # co-chair streams via socket only
        f = _online_file()
        if not f:
            return
        _write_csv(f, [_row_full(c) for c in countries.values()])
        return

    # offline: each side owns exactly one file
    if is_primary:
        path = _primary_file()
        rows = [_row_half(c, True) for c in countries.values()]
        label = "primary"
    else:
        path = _secondary_file()
        rows = [_row_half(c, False) for c in countries.values()]
        label = "secondary"
    if not path:
        return
    _write_csv(path, rows)
    if sync:
        _git_push(os.path.basename(path), label)


# --- initial table import (name + power only) --------------------------------

def import_table(path: Optional[str] = None) -> None:
    """Import ONLY name + power from a CSV (used once per conference)."""
    if path is None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select the countries CSV (name,power)",
            filetypes=[("CSV File", "*.csv"), ("All files", "*.*")])
        if not path:
            return
    countries.clear()
    for row in _read_csv(path):
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        c = Country(name)
        c.type = _normalize_type(row[1]) if len(row) > 1 else ""
        countries[name] = c


# --- working directory picker ------------------------------------------------

def choose_dir() -> Optional[str]:
    """Pick the working folder (may be a git repo). Loads the model after."""
    from tkinter import filedialog
    d = filedialog.askdirectory(title="Select the munager working folder")
    if not d:
        return None
    _set_dir(d)          # remembered in the bootstrap ini
    load()
    return d


def has_data() -> bool:
    """True if a persisted model already exists for the current mode/dir."""
    if mode == "online":
        f = _online_file()
        return bool(f) and os.path.exists(f)
    p, s = _primary_file(), _secondary_file()
    return bool(p and os.path.exists(p)) or bool(s and os.path.exists(s))
