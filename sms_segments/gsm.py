"""GSM 03.38 (GSM 7-bit default alphabet) tables.

Source: 3GPP TS 23.038 (formerly GSM 03.38), section 6.2.1 "GSM 7 bit Default
Alphabet" (basic table) and its extension table (reached through the escape
code 0x1B). Codes below are the septet values in the specification.

A character in the basic table costs 1 septet. A character in the extension
table costs 2 septets (ESC + code). Anything else cannot be sent in GSM-7 and
forces the whole message to UCS-2.
"""

# Basic table, indexed by septet value 0x00..0x7F.
# 0x1B is the escape-to-extension code, not a printable character.
_ESC = "\x1b"
BASIC_TABLE = (
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n\u00d8\u00f8\r\u00c5\u00e5"  # 0x00-0x0F
    "\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e" + _ESC + "\u00c6\u00e6\u00df\u00c9"  # 0x10-0x1F
    " !\"#\u00a4%&'()*+,-./"  # 0x20-0x2F
    "0123456789:;<=>?"  # 0x30-0x3F
    "\u00a1ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7"  # 0x40-0x5F
    "\u00bfabcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0"  # 0x60-0x7F
)

# Extension table: character -> septet value that follows ESC (0x1B).
EXTENSION_TABLE = {
    "\x0c": 0x0A,  # form feed
    "^": 0x14,
    "{": 0x28,
    "}": 0x29,
    "\\": 0x2F,
    "[": 0x3C,
    "~": 0x3D,
    "]": 0x3E,
    "|": 0x40,
    "\u20ac": 0x65,  # euro sign
}

GSM_BASIC = frozenset(BASIC_TABLE) - {_ESC}
GSM_EXTENSION = frozenset(EXTENSION_TABLE)
GSM_ALL = GSM_BASIC | GSM_EXTENSION


def is_gsm7(ch: str) -> bool:
    """True if the single character can be sent in GSM-7 (basic or extension)."""
    return ch in GSM_ALL


def gsm_units(ch: str) -> int:
    """Septets a GSM-7 character costs: 1 (basic) or 2 (extension).

    Raises ValueError for a character outside the GSM-7 set.
    """
    if ch in GSM_BASIC:
        return 1
    if ch in GSM_EXTENSION:
        return 2
    raise ValueError(f"character U+{ord(ch):04X} is not in the GSM 03.38 set")
