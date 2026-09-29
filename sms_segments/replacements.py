"""Replacement rules and character classification.

Two layers:

* SAFE rules (always applied by ``suggest``): typographic look-alikes that
  have an exact ASCII/GSM-7 equivalent (curly quotes, dashes, ellipsis,
  non-breaking spaces, ...).
* FOLD rules (opt-in): accented letters that are not in GSM 03.38 are mapped
  to the nearest GSM form. This changes spelling, so it is never automatic.
  Note that e-acute, e-grave, a-grave, u-grave, i-grave, o-grave and capital
  C-cedilla ARE in GSM-7 and are never touched.
"""

from __future__ import annotations

import unicodedata

from .gsm import GSM_ALL

SUPPORTED_LANGS = ("en", "fr", "es")

# rule name -> (characters, replacement)
_SAFE_GROUPS = (
    ("quote", "\u2018\u2019\u201a\u201b\u2032\u2035\u02bc\u00b4`", "'"),
    ("quote", "\u201c\u201d\u201e\u201f\u2033\u2036", '"'),
    ("dash", "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u2043", "-"),
    ("ellipsis", "\u2026", "..."),
    (
        "whitespace",
        "\u00a0\u202f\u2007\u2009\u2002\u2003\u2004\u2005\u2006\u2008\u200a\u205f\u3000\u1680\t",
        " ",
    ),
    ("whitespace", "\u2028\u2029", "\n"),
    ("invisible", "\u200b\u200c\u200d\u2060\ufeff\u00ad\u200e\u200f", ""),
    ("symbol", "\u2022\u25cf\u25aa", "*"),
    ("symbol", "\u00b7", "-"),
    ("symbol", "\u2122", "TM"),
    ("symbol", "\u00a9", "(c)"),
    ("symbol", "\u00ae", "(R)"),
    ("symbol", "\u00d7", "x"),
    ("symbol", "\u2192", "->"),
    ("symbol", "\u2190", "<-"),
    ("symbol", "\u2044", "/"),
)

SAFE_MAP: dict[str, tuple[str, str]] = {}
for _rule, _chars, _repl in _SAFE_GROUPS:
    for _c in _chars:
        SAFE_MAP[_c] = (_repl, _rule)

GUILLEMETS = {"\u00ab", "\u00bb"}  # handled as a pair, see suggest.py
_GUILLEMET_SPACES = frozenset(" \u00a0\u202f\u2009")

# Language specific opt-in folds, applied before the generic NFD fallback.
_FOLD_OVERRIDES = {
    "en": {},
    "fr": {"\u0153": "oe", "\u0152": "OE", "\u00ff": "y", "\u0178": "Y"},
    "es": {"\u00aa": "a", "\u00ba": "o"},
}
_FOLD_EXTRA = {
    "\u0141": "L",
    "\u0142": "l",
    "\u0110": "D",
    "\u0111": "d",
    "\u0131": "i",
}

FOLD_TRADEOFFS = {
    "en": "Dropping diacritics is usually harmless in English (naive, cafe), but proper names change spelling.",
    "fr": (
        "French readability tradeoff: circumflexes, diaereses and cedillas disappear "
        "(garcon, foret, Noel). Some words collide or read oddly (sur/sur, mur/mur, cote/cote). "
        "e-acute, e-grave, a-grave and u-grave are already GSM-7 and stay."
    ),
    "es": (
        "Spanish readability tradeoff: dropping the acute accent from a, i, o, u can change "
        "meaning (papa/papa, esta/esta, si/si). n-tilde and e-acute are already GSM-7 and stay."
    ),
}

_CONTROL_NAMES = {
    "\t": "CHARACTER TABULATION",
    "\x0b": "LINE TABULATION",
    "\x1b": "ESCAPE",
    "\x7f": "DELETE",
    "\u2028": "LINE SEPARATOR",
    "\u2029": "PARAGRAPH SEPARATOR",
}


def normalize_lang(lang: str | None, default: str = "en") -> str:
    """Reduce 'fr-CA' / 'FR_ca' to 'fr'; unknown languages fall back to default."""
    if not lang:
        return default
    primary = lang.replace("_", "-").split("-")[0].lower()
    return primary if primary in SUPPORTED_LANGS else default


def char_name(ch: str) -> str:
    try:
        return unicodedata.name(ch)
    except ValueError:
        return _CONTROL_NAMES.get(ch, f"<control U+{ord(ch):04X}>")


def is_combining(ch: str) -> bool:
    return unicodedata.category(ch) in ("Mn", "Mc", "Me")


def fold_char(ch: str, lang: str = "en") -> str | None:
    """Nearest GSM-7 form of a non-GSM letter, or None when there is none."""
    if is_combining(ch):
        return ""
    override = _FOLD_OVERRIDES.get(normalize_lang(lang), {})
    if ch in override:
        return override[ch]
    if ch in _FOLD_EXTRA:
        return _FOLD_EXTRA[ch]
    base = "".join(c for c in unicodedata.normalize("NFD", ch) if not is_combining(c))
    if base and base != ch and all(c in GSM_ALL for c in base):
        return base
    return None


def _is_emoji(cp: int) -> bool:
    return (
        cp >= 0x1F000
        or 0x2600 <= cp <= 0x27BF
        or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF
        or cp in (0xFE0F, 0xFE0E, 0x3030, 0x303D)
    )


def categorize(ch: str) -> str:
    """Coarse class of a non-GSM character, used in reports."""
    if ch in SAFE_MAP:
        rule = SAFE_MAP[ch][1]
        return rule if rule != "symbol" else "symbol"
    if ch in GUILLEMETS:
        return "quote"
    cp = ord(ch)
    if _is_emoji(cp):
        return "emoji"
    if is_combining(ch):
        return "combining"
    if any(fold_char(ch, lang) is not None for lang in SUPPORTED_LANGS):
        return "accent"
    if unicodedata.category(ch).startswith("S"):
        return "symbol"
    return "other"
