from __future__ import annotations

import configparser
import json
import os
import sys
from typing import Any, Optional
from munager_proto import Country, Power


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


def _set_file(path: str) -> None:
    cp = _boot_config()
    cp.set(BOOT_SECTION, "file", path)
    with open(BOOTSTRAP_INI, "w", encoding="utf-8") as f:
        cp.write(f)


def _get_file() -> str:
    cp = _boot_config()
    return cp.get(BOOT_SECTION, "file", fallback="")


def _ini_path() -> str:
    """Settings ini sits beside the chosen data file (same base name)."""
    f = _get_file()
    if not f:
        return BOOTSTRAP_INI
    return os.path.splitext(f)[0] + ".ini"


# Shared model, mirroring the AHK global `countries` map.
countries: dict[str, Country] = {}


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


def load() -> None:
    """Load the full model from the single JSON file."""
    countries.clear()
    f = _get_file()
    if not f or not os.path.exists(f):
        return
    try:
        with open(f, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (ValueError, OSError):
        return
    for item in raw if isinstance(raw, list) else []:
        dto = Country.from_dict(item)
        if dto.name:
            countries[dto.name] = dto


def save() -> None:
    """Persist the model. Only the primary writes; the co-chair streams."""
    f = _get_file()
    if not f:
        return
    try:
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            json.dump([c.to_dict() for c in countries.values()],
                      fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


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
    import csv
    countries.clear()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip():
                continue
            name = row[0].strip()
            c = Country(name)
            c.power = Power.parse(row[1]) if len(row) > 1 else Power.NONE
            countries[name] = c


# --- save file picker ------------------------------------------------

def choose_file() -> Optional[str]:
    """Pick the working file. Loads the model after."""
    from tkinter import filedialog
    f = filedialog.asksaveasfilename(
        title="Select the munager JSON file",
        filetypes=[("JSON File", "*.json"), ("All files", "*.*")],
        confirmoverwrite=True)
    if not f:
        return None
    _set_file(f)          # remembered in the bootstrap ini
    load()
    return f


def has_data() -> bool:
    """True if a persisted model already exists for the current dir."""
    f = _get_file()
    return bool(f) and os.path.exists(f)
