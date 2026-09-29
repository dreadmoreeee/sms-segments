"""Encoding detection and segment counting.

Rules implemented (GSM 03.38 / 3GPP TS 23.040 concatenated SMS):

* GSM-7: 160 septets in one segment, 153 per segment when concatenated
  (7 septets are used by the UDH). Extension characters cost 2 septets.
* UCS-2: 70 UTF-16 code units in one segment, 67 per segment when concatenated.
  Characters outside the BMP (most emoji) are surrogate pairs and cost 2 units.
* One character outside GSM-7 forces the WHOLE message to UCS-2.
* A 2-septet extension character, or a UCS-2 surrogate pair, is never split
  across two segments: if it does not fit in the room left, it starts the next
  segment (so a segment can hold 152 septets or 66 units).
* Characters are Unicode code points. Grapheme clusters (e.g. an emoji ZWJ
  sequence or a base letter plus combining mark) are NOT kept together, so a
  segment boundary can fall inside one; the count is still correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gsm import GSM_ALL, GSM_EXTENSION, gsm_units
from .replacements import SAFE_MAP, categorize, char_name, fold_char

GSM7 = "GSM-7"
UCS2 = "UCS-2"

# encoding -> (single segment limit, per-segment limit when concatenated)
LIMITS = {GSM7: (160, 153), UCS2: (70, 67)}
UNIT_NAMES = {GSM7: "septets", UCS2: "UTF-16 code units"}


@dataclass
class Trigger:
    """A character that forces UCS-2."""

    index: int  # 0-based code point index in the text
    char: str
    codepoint: str  # "U+00A0"
    name: str
    category: str
    safe_replacement: str | None  # applied automatically by suggest()
    fold_replacement: str | None  # opt-in accent folding (language dependent)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "char": self.char,
            "codepoint": self.codepoint,
            "name": self.name,
            "category": self.category,
            "safe_replacement": self.safe_replacement,
            "fold_replacement": self.fold_replacement,
        }


@dataclass
class Analysis:
    encoding: str
    characters: int  # Unicode code points
    units: int  # septets (GSM-7) or UTF-16 code units (UCS-2)
    segments: int
    segment_units: list[int] = field(default_factory=list)
    extension_chars: int = 0
    triggers: list[Trigger] = field(default_factory=list)

    @property
    def unit_name(self) -> str:
        return UNIT_NAMES[self.encoding]

    @property
    def single_limit(self) -> int:
        return LIMITS[self.encoding][0]

    @property
    def multi_limit(self) -> int:
        return LIMITS[self.encoding][1]

    @property
    def units_left(self) -> int:
        """Units still free in the last segment (0 for an empty message)."""
        if not self.segments:
            return 0
        limit = self.single_limit if self.segments == 1 else self.multi_limit
        return limit - self.segment_units[-1]

    def to_dict(self) -> dict:
        return {
            "encoding": self.encoding,
            "characters": self.characters,
            "units": self.units,
            "unit_name": self.unit_name,
            "segments": self.segments,
            "segment_units": list(self.segment_units),
            "limits": {"single": self.single_limit, "concatenated": self.multi_limit},
            "units_left_in_last_segment": self.units_left,
            "extension_chars": self.extension_chars,
            "ucs2_triggers": [t.to_dict() for t in self.triggers],
        }


def detect_encoding(text: str) -> str:
    """GSM-7 if every character is in the basic or extension table, else UCS-2."""
    return GSM7 if all(ch in GSM_ALL for ch in text) else UCS2


def char_units(ch: str, encoding: str) -> int:
    """Units one character costs under the given encoding."""
    if encoding == GSM7:
        return gsm_units(ch)
    return 2 if ord(ch) > 0xFFFF else 1


def _pack(text: str, encoding: str) -> list[tuple[str, int]]:
    """Greedy packing into segments; returns (segment text, units) pairs."""
    if not text:
        return []
    single, multi = LIMITS[encoding]
    units = [char_units(ch, encoding) for ch in text]
    total = sum(units)
    if total <= single:
        return [(text, total)]
    parts: list[tuple[str, int]] = []
    start = 0
    used = 0
    for i, u in enumerate(units):
        if used + u > multi:  # atomic: a 2-unit character moves whole to the next segment
            parts.append((text[start:i], used))
            start, used = i, 0
        used += u
    parts.append((text[start:], used))
    return parts


def split_segments(text: str) -> list[str]:
    """The text of each segment as it would be packed (no character is split)."""
    return [p for p, _ in _pack(text, detect_encoding(text))]


def find_triggers(text: str, lang: str = "en") -> list[Trigger]:
    out = []
    for i, ch in enumerate(text):
        if ch in GSM_ALL:
            continue
        safe = SAFE_MAP.get(ch, (None, None))[0]
        # guillemets are paired in suggest(); report the plain quote here
        if ch in ("\u00ab", "\u00bb"):
            safe = '"'
        out.append(
            Trigger(
                index=i,
                char=ch,
                codepoint=f"U+{ord(ch):04X}",
                name=char_name(ch),
                category=categorize(ch),
                safe_replacement=safe,
                fold_replacement=fold_char(ch, lang) if safe is None else None,
            )
        )
    return out


def analyze(text: str, lang: str = "en") -> Analysis:
    """Encoding, length, segment count and UCS-2 triggers of a message.

    ``lang`` (en/fr/es) only selects the opt-in accent fold shown per trigger.
    """
    encoding = detect_encoding(text)
    parts = _pack(text, encoding)
    return Analysis(
        encoding=encoding,
        characters=len(text),
        units=sum(u for _, u in parts),
        segments=len(parts),
        segment_units=[u for _, u in parts],
        extension_chars=sum(1 for ch in text if ch in GSM_EXTENSION) if encoding == GSM7 else 0,
        triggers=find_triggers(text, lang),
    )
