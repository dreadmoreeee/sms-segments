"""Safe replacements and the before/after segment comparison."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .core import UCS2, Analysis, Trigger, analyze
from .gsm import GSM_ALL
from .replacements import (
    _GUILLEMET_SPACES,
    FOLD_TRADEOFFS,
    GUILLEMETS,
    SAFE_MAP,
    fold_char,
    is_combining,
    normalize_lang,
)


@dataclass
class Change:
    index: int  # 0-based code point index in the ORIGINAL text
    original: str
    replacement: str
    rule: str  # quote, dash, ellipsis, whitespace, invisible, symbol, guillemets, normalize, accent
    optin: bool  # True for accent folding

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "original": self.original,
            "codepoints": " ".join(f"U+{ord(c):04X}" for c in self.original),
            "replacement": self.replacement,
            "rule": self.rule,
            "optin": self.optin,
        }


@dataclass
class Suggestion:
    lang: str
    fold_accents: bool
    original: str
    text: str
    before: Analysis
    after: Analysis
    changes: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    optin_segments: int | None = None  # segments if accent folding were enabled

    @property
    def saved_segments(self) -> int:
        return self.before.segments - self.after.segments

    @property
    def saved_units(self) -> int:
        return self.before.units - self.after.units

    @property
    def still_ucs2(self) -> bool:
        return self.after.encoding == UCS2

    @property
    def remaining(self) -> list[Trigger]:
        return self.after.triggers

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "fold_accents": self.fold_accents,
            "changed": self.text != self.original,
            "text_after": self.text,
            "encoding_before": self.before.encoding,
            "encoding_after": self.after.encoding,
            "segments_before": self.before.segments,
            "segments_after": self.after.segments,
            "units_before": self.before.units,
            "units_after": self.after.units,
            "saved_segments": self.saved_segments,
            "saved_units": self.saved_units,
            "changes": [c.to_dict() for c in self.changes],
            "remaining_triggers": [t.to_dict() for t in self.remaining],
            "segments_if_accents_folded": self.optin_segments,
            "warnings": list(self.warnings),
        }


def _replace_single(ch: str, lang: str, fold: bool) -> tuple[str, str, bool] | None:
    """(replacement, rule, optin) for one non-GSM character, or None."""
    if ch in SAFE_MAP:
        repl, rule = SAFE_MAP[ch]
        return repl, rule, False
    if fold:
        repl = fold_char(ch, lang)
        if repl is not None:
            return repl, "accent", True
    return None


def _rewrite(text: str, lang: str, fold: bool) -> tuple[str, list[Change]]:
    out: list[str] = []
    changes: list[Change] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]

        # guillemets: swallow the padding spaces inside them (fr/es typography)
        if ch in GUILLEMETS:
            j = i + 1
            if ch == "\u00ab":
                while j < n and text[j] in _GUILLEMET_SPACES:
                    j += 1
                changes.append(Change(i, text[i:j], '"', "guillemets", False))
                out.append('"')
                i = j
                continue
            out.append('"')
            changes.append(Change(i, ch, '"', "guillemets", False))
            i += 1
            continue
        if ch in _GUILLEMET_SPACES:
            j = i
            while j < n and text[j] in _GUILLEMET_SPACES:
                j += 1
            if j < n and text[j] == "\u00bb":
                changes.append(Change(i, text[i : j + 1], '"', "guillemets", False))
                out.append('"')
                i = j + 1
                continue

        # base letter + combining marks: compose to a GSM letter when possible
        if i + 1 < n and is_combining(text[i + 1]) and not is_combining(ch):
            j = i + 1
            while j < n and is_combining(text[j]):
                j += 1
            cluster = text[i:j]
            composed = unicodedata.normalize("NFC", cluster)
            if len(composed) == 1:
                if composed in GSM_ALL:
                    out.append(composed)
                    changes.append(Change(i, cluster, composed, "normalize", False))
                    i = j
                    continue
                res = _replace_single(composed, lang, fold)
                if res is not None:
                    out.append(res[0])
                    changes.append(Change(i, cluster, res[0], res[1], res[2]))
                    i = j
                    continue

        if ch in GSM_ALL:
            out.append(ch)
        else:
            res = _replace_single(ch, lang, fold)
            if res is None:
                out.append(ch)
            else:
                out.append(res[0])
                changes.append(Change(i, ch, res[0], res[1], res[2]))
        i += 1
    return "".join(out), changes


def apply_replacements(text: str, lang: str = "en", fold_accents: bool = False) -> str:
    """The text with safe replacements (and optionally accent folding) applied."""
    return _rewrite(text, normalize_lang(lang), fold_accents)[0]


def suggest(text: str, lang: str = "en", fold_accents: bool = False) -> Suggestion:
    """Apply replacements and compare segment counts before and after.

    Safe rules always run. ``fold_accents=True`` also maps accented letters
    that are not in GSM-7 to the nearest GSM form (opt-in, language aware).
    """
    lang = normalize_lang(lang)
    new_text, changes = _rewrite(text, lang, fold_accents)
    before = analyze(text, lang)
    after = analyze(new_text, lang)
    s = Suggestion(lang, fold_accents, text, new_text, before, after, changes)

    if not fold_accents and any(t.fold_replacement is not None for t in after.triggers):
        folded_text, _ = _rewrite(text, lang, True)
        s.optin_segments = analyze(folded_text, lang).segments
        s.warnings.append(
            "Accented letters outside GSM-7 remain; folding them is opt-in "
            f"(fold_accents / --fold-accents). {FOLD_TRADEOFFS[lang]}"
        )
    if fold_accents and any(c.optin for c in changes):
        s.warnings.append(FOLD_TRADEOFFS[lang])
    unfixable = [t for t in after.triggers if t.fold_replacement is None or fold_accents]
    if unfixable:
        cps = ", ".join(sorted({t.codepoint for t in unfixable}))
        s.warnings.append(f"No safe replacement for: {cps}; the message stays UCS-2.")
    return s
