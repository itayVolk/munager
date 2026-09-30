"""Typed wire protocol + serialisable model DTOs for munager."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import statistics
from typing import Any, Optional, Union
import struct


# --- enums -------------------------------------------------------------------
class Power(IntEnum):
    NONE = 0        # ''
    OBSERVER = 1    # 'O'
    VETO = 2        # 'V'

    @staticmethod
    def parse(raw: str) -> "Power":
        r = raw.strip().lower()
        if r == "o":
            return Power.OBSERVER
        if r in ("p", "v"):
            return Power.VETO
        return Power.NONE

    def code(self) -> str:
        return {Power.NONE: "", Power.OBSERVER: "O", Power.VETO: "V"}[self]

    def __str__(self):
        match self:
            case Power.NONE:
                return ""
            case Power.OBSERVER:
                return "Observer"
            case Power.VETO:
                return "Permanent"
        return ""

    def __bool__(self) -> bool:
        return self != Power.NONE


class Presence(IntEnum):
    ABSENT = 0      # ''
    PRESENT = 1     # 'P'
    PRESENT_VOTING = 2  # 'V'

    @staticmethod
    def parse(raw: str) -> "Presence":
        r = raw.strip().upper()
        if r == "P":
            return Presence.PRESENT
        if r == "V":
            return Presence.PRESENT_VOTING
        return Presence.ABSENT

    def code(self) -> str:
        return {Presence.ABSENT: "", Presence.PRESENT: "P",
                Presence.PRESENT_VOTING: "V"}[self]

    def __str__(self):
        match self:
            case Presence.ABSENT:
                return ""
            case Presence.PRESENT:
                return "Present"
            case Presence.PRESENT_VOTING:
                return "Present & Voting"
        return ""

    def __bool__(self) -> bool:
        return self != Presence.ABSENT


# --- structured feedback -----------------------------------------------------
@dataclass(init=False, repr=False)
class Feedback:
    """One feedback entry: an optional score plus a note.

    score == -1 means 'no score' (note-only).
    """
    score: int
    note: str

    def __init__(self, score: int = -1, note: str = "") -> None:
        self.score = score
        self.note = note

    def __bool__(self) -> bool:
        return self.score >= 0 and self.note != ""

    def __str__(self) -> str:
        """Render back to the display string used across the UI."""
        if self:
            return f"{self.score}: {self.note}"
        return self.note

    def to_tuple(self) -> tuple[int, str]:
        return (self.score, self.note)


# --- serialisable model DTOs -------------------------------------------------
@dataclass(init=False, repr=False)
class Country:
    """Wire/disk representation of one delegation (no behaviour)."""
    name: str
    power: Power
    presence: Presence
    unmod: Feedback
    unmod_feed: Feedback
    mod: list[Feedback]
    mod_feed: list[Feedback]

    def __init__(self, name: str = "", power: Power = Power.NONE,
                 presence: Presence = Presence.ABSENT,
                 unmod: Feedback | None = None, unmod_feed: Feedback | None = None,
                 mod: list[Feedback] | None = None, mod_feed: list[Feedback] | None = None):
        self.name = name
        self.power = power
        self.presence = presence
        self.unmod = unmod if unmod is not None else Feedback()
        self.unmod_feed = unmod_feed if unmod_feed is not None else Feedback()
        self.mod = mod if mod is not None else []
        self.mod_feed = mod_feed if mod_feed is not None else []

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Country":
        return Country(
            name=str(d.get("name", "")).strip(),
            power=Power.parse(str(d.get("power", ""))),
            presence=Presence.parse(str(d.get("presence", ""))),
            unmod=Feedback(*d.get("unmod", [-1, ""])),
            unmod_feed=Feedback(*d.get("unmod_feed", [-1, ""])),
            mod=[Feedback(*x) for x in d.get("mod", [])],
            mod_feed=[Feedback(*x) for x in d.get("mod_feed", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "power": self.power.code(),
            "presence": self.presence.code(),
            "unmod": self.unmod.to_tuple(),
            "unmod_feed": self.unmod_feed.to_tuple(),
            "mod": [f.to_tuple() for f in self.mod],
            "mod_feed": [f.to_tuple() for f in self.mod_feed],
        }

    # --- awards metrics (combined across both chairs) ---
    @property
    def _mod_scores(self) -> list[int]:
        return [s.score for s in (*self.mod, *self.mod_feed) if s]

    @property
    def _unmod_scores(self) -> list[int]:
        return [s.score for s in (self.unmod, self.unmod_feed) if s]

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


@dataclass
class PresenceDTO:
    """Just the roll-call fields for a delegation."""
    name: str
    presence: Presence = Presence.ABSENT
    power: Power = Power.NONE

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "PresenceDTO":
        return PresenceDTO(
            name=str(d.get("name", "")),
            presence=Presence.parse(str(d.get("presence", ""))),
            power=Power.parse(str(d.get("power", ""))),
        )


# --- low-level codec ---------------------------------------------------------

class _Reader:
    __slots__ = ("_b", "_i")

    def __init__(self, b: bytes) -> None:
        self._b = b
        self._i = 0

    def u8(self) -> int:
        v = self._b[self._i]
        self._i += 1
        return v

    def i16(self) -> int:
        (v,) = struct.unpack_from(">h", self._b, self._i)
        self._i += 2
        return v

    def u16(self) -> int:
        (v,) = struct.unpack_from(">H", self._b, self._i)
        self._i += 2
        return v

    def text(self) -> str:
        n = self.u16()
        s = self._b[self._i:self._i + n].decode("utf-8")
        self._i += n
        return s


class _Writer:
    __slots__ = ("_parts",)

    def __init__(self) -> None:
        self._parts: list[bytes] = []

    def u8(self, v: int) -> "_Writer":
        self._parts.append(struct.pack(">B", v & 0xFF))
        return self

    def i16(self, v: int) -> "_Writer":
        self._parts.append(struct.pack(">h", v))
        return self

    def u16(self, v: int) -> "_Writer":
        self._parts.append(struct.pack(">H", v))
        return self

    def text(self, s: str) -> "_Writer":
        b = s.encode("utf-8")
        if len(b) > 0xFFFF:
            b = b[:0xFFFF]
        self._parts.append(struct.pack(">H", len(b)))
        self._parts.append(b)
        return self

    def bytes(self) -> bytes:
        return b"".join(self._parts)


# --- composite (Feedback / CountryDTO) codecs --------------------------------

def _w_feedback(w: _Writer, f: Feedback) -> None:
    w.i16(f.score)          # -1..N  (i16 covers -1 sentinel + scores)
    w.text(f.note)


def _r_feedback(r: _Reader) -> Feedback:
    return Feedback(r.i16(), r.text())


def _w_feedback_list(w: _Writer, items: list[Feedback]) -> None:
    w.u8(min(len(items), 0xFF))
    for f in items[:0xFF]:
        _w_feedback(w, f)


def _r_feedback_list(r: _Reader) -> list[Feedback]:
    return [_r_feedback(r) for _ in range(r.u8())]


def _w_country(w: _Writer, c: Country) -> None:
    w.text(c.name)
    w.u8(int(c.power))
    w.u8(int(c.presence))
    _w_feedback(w, c.unmod)
    _w_feedback(w, c.unmod_feed)
    _w_feedback_list(w, c.mod)
    _w_feedback_list(w, c.mod_feed)


def _r_country(r: _Reader) -> Country:
    name = r.text()
    power = Power(r.u8())
    presence = Presence(r.u8())
    unmod = _r_feedback(r)
    unmod_feed = _r_feedback(r)
    mod = _r_feedback_list(r)
    mod_feed = _r_feedback_list(r)
    return Country(name, power, presence,
                   unmod, unmod_feed, mod, mod_feed)


# --- message tags ------------------------------------------------------------

class Tag(IntEnum):
    HELLO = 0
    FULL = 1
    COUNTRY = 2
    PRESENCE = 3
    SPEECH = 4


@dataclass
class Hello:
    pass


@dataclass
class FullState:
    countries: list[Country]


@dataclass
class CountryDelta:
    country: Country


@dataclass
class PresenceSync:
    presence: list[PresenceDTO]


@dataclass
class SpeechStart:
    country: str


Message = Union[Hello, FullState, CountryDelta, PresenceSync, SpeechStart]


def encode(msg: Message) -> bytes:
    w = _Writer()
    if isinstance(msg, Hello):
        w.u8(Tag.HELLO)
    elif isinstance(msg, FullState):
        w.u8(Tag.FULL)
        w.u16(len(msg.countries))
        for c in msg.countries:
            _w_country(w, c)
    elif isinstance(msg, CountryDelta):
        w.u8(Tag.COUNTRY)
        _w_country(w, msg.country)
    elif isinstance(msg, PresenceSync):
        w.u8(Tag.PRESENCE)
        w.u16(len(msg.presence))
        for p in msg.presence:
            w.text(p.name).u8(int(p.presence)).u8(int(p.power))
    elif isinstance(msg, SpeechStart):
        w.u8(Tag.SPEECH)
        w.text(msg.country)
    else:                       # exhaustiveness guard
        raise TypeError(f"unencodable message: {msg!r}")
    return w.bytes()


def decode(raw: bytes) -> Optional[Message]:
    if not raw:
        return None
    try:
        r = _Reader(raw)
        tag = Tag(r.u8())
        if tag is Tag.HELLO:
            return Hello()
        if tag is Tag.FULL:
            return FullState([_r_country(r) for _ in range(r.u16())])
        if tag is Tag.COUNTRY:
            return CountryDelta(_r_country(r))
        if tag is Tag.PRESENCE:
            n = r.u16()
            return PresenceSync(
                [PresenceDTO(r.text(), Presence(r.u8()), Power(r.u8()))
                 for _ in range(n)])
        if tag is Tag.SPEECH:
            return SpeechStart(r.text())
    except (IndexError, struct.error, ValueError, UnicodeDecodeError):
        return None
    return None
