import json

import pytest

from sms_segments import (
    GSM_BASIC,
    GSM_EXTENSION,
    analyze,
    detect_encoding,
    split_segments,
)
from sms_segments.gsm import BASIC_TABLE, gsm_units

EMOJI = "\U0001F600"  # grinning face, outside the BMP -> surrogate pair


def seg(text):
    a = analyze(text)
    return a.encoding, a.units, a.segments


# ---------------------------------------------------------------- GSM table


def test_basic_table_has_128_entries():
    assert len(BASIC_TABLE) == 128


def test_basic_set_contents():
    assert len(GSM_BASIC) == 127  # 128 minus the ESC code
    assert len(GSM_EXTENSION) == 10


@pytest.mark.parametrize(
    "ch",
    list("\u00e9\u00e8\u00e0\u00f9\u00ec\u00f2\u00c7\u00c9\u00f1\u00e4\u00f6\u00fc@$_\u00a3\u00a5\u00a4\u00a7\u00bf\u00a1\n\r"),
)
def test_gsm7_characters(ch):
    assert detect_encoding(ch) == "GSM-7"
    assert gsm_units(ch) == 1


@pytest.mark.parametrize("ch", list("\u20ac[]{}~^|\\\x0c"))
def test_extension_characters_cost_two(ch):
    assert detect_encoding(ch) == "GSM-7"
    assert gsm_units(ch) == 2


@pytest.mark.parametrize(
    "ch",
    list("\u00ea\u00f4\u00fb\u00ee\u00e7\u00e2\u00eb\u00ef\u00c0\u00c8")
    + ["\u2019", "\u201c", "\u00a0", "\u202f", "\u2013", "\u2026", "`", "\t", "\u00e1", "\u00ed", "\u00f3", "\u00fa", EMOJI],
)
def test_ucs2_forcing_characters(ch):
    assert detect_encoding("abc" + ch) == "UCS-2"


# ---------------------------------------------------------------- GSM-7 boundaries


def test_empty_message():
    assert seg("") == ("GSM-7", 0, 0)


def test_gsm_160_is_one_segment():
    assert seg("a" * 160) == ("GSM-7", 160, 1)


def test_gsm_161_is_two_segments():
    assert seg("a" * 161) == ("GSM-7", 161, 2)


def test_gsm_306_is_two_segments():
    assert analyze("a" * 306).segments == 2  # 153 * 2


def test_gsm_307_is_three_segments():
    assert analyze("a" * 307).segments == 3


def test_gsm_459_and_460():
    assert analyze("a" * 459).segments == 3  # 153 * 3
    assert analyze("a" * 460).segments == 4


def test_gsm_segment_units_split_153():
    assert analyze("a" * 161).segment_units == [153, 8]


def test_units_left():
    assert analyze("a" * 100).units_left == 60
    assert analyze("a" * 161).units_left == 153 - 8


# ---------------------------------------------------------------- extension characters


def test_extension_counts_double():
    assert seg("\u20ac") == ("GSM-7", 2, 1)
    assert analyze("[a]").units == 5
    assert analyze("[a]").characters == 3
    assert analyze("[a]").extension_chars == 2


def test_extension_at_end_of_single_segment():
    # 159 + 2-septet char = 161 septets -> concatenated
    assert seg("a" * 159 + "\u20ac") == ("GSM-7", 161, 2)


def test_extension_fills_160_exactly():
    assert seg("a" * 158 + "\u20ac") == ("GSM-7", 160, 1)


def test_extension_not_split_across_segments():
    # 152 septets then a 2-septet char: it does not fit in the 153 limit
    a = analyze("a" * 152 + "\u20ac" + "b" * 10)
    assert a.segments == 2
    assert a.segment_units == [152, 12]


def test_extension_exactly_at_edge_153():
    a = analyze("a" * 151 + "\u20ac" + "b" * 10)  # 151 + 2 = 153, then the b's
    assert a.segment_units == [153, 10]


def test_split_segments_keeps_extension_whole():
    parts = split_segments("a" * 152 + "\u20ac" + "b" * 10)
    assert parts == ["a" * 152, "\u20ac" + "b" * 10]


def test_two_by_153_with_extension_boundary():
    text = "a" * 152 + "[" + "a" * 151 + "]"
    a = analyze(text)
    assert a.segment_units == [152, 153, 2]
    assert a.segments == 3


# ---------------------------------------------------------------- UCS-2 boundaries


def test_ucs2_70_is_one_segment():
    assert seg("\u00ea" * 70) == ("UCS-2", 70, 1)


def test_ucs2_71_is_two_segments():
    assert seg("\u00ea" * 71) == ("UCS-2", 71, 2)


def test_ucs2_134_and_135():
    assert analyze("\u00ea" * 134).segments == 2  # 67 * 2
    assert analyze("\u00ea" * 135).segments == 3


def test_ucs2_201_and_202():
    assert analyze("\u00ea" * 201).segments == 3  # 67 * 3
    assert analyze("\u00ea" * 202).segments == 4


def test_ucs2_one_trigger_makes_message_ucs2():
    a = analyze("a" * 70 + "\u00ea")  # 71 units
    assert a.encoding == "UCS-2"
    assert a.segments == 2


def test_ucs2_message_that_would_be_one_gsm_segment():
    assert analyze("a" * 100 + "\u00ea").segments == 2  # 101 units > 70


# ---------------------------------------------------------------- emoji / surrogates


def test_emoji_counts_two_units():
    a = analyze(EMOJI)
    assert (a.encoding, a.characters, a.units, a.segments) == ("UCS-2", 1, 2, 1)


def test_emoji_35_fit_one_segment():
    assert seg(EMOJI * 35) == ("UCS-2", 70, 1)


def test_emoji_36_need_two_segments():
    assert seg(EMOJI * 36) == ("UCS-2", 72, 2)


def test_surrogate_pair_not_split_at_67():
    # 66 BMP units then an emoji (2 units): 68 > 67 so the emoji starts segment two
    text = "\u00ea" * 66 + EMOJI + "\u00ea" * 3
    a = analyze(text)
    assert a.segment_units == [66, 5]
    assert split_segments(text) == ["\u00ea" * 66, EMOJI + "\u00ea" * 3]


def test_surrogate_pair_exactly_at_edge():
    a = analyze("\u00ea" * 65 + EMOJI + "\u00ea" * 10)  # 65 + 2 = 67, then 10
    assert a.segment_units == [67, 10]


def test_emoji_between_gsm_text_forces_ucs2():
    a = analyze("Hello " + EMOJI)
    assert a.encoding == "UCS-2"
    assert a.units == 8
    assert a.triggers[0].codepoint == "U+1F600"
    assert a.triggers[0].category == "emoji"


# ---------------------------------------------------------------- triggers


def test_triggers_report_position_codepoint_name():
    a = analyze("Hi\u202fthere \u00ea")
    idx = [(t.index, t.codepoint, t.name) for t in a.triggers]
    assert idx == [
        (2, "U+202F", "NARROW NO-BREAK SPACE"),
        (9, "U+00EA", "LATIN SMALL LETTER E WITH CIRCUMFLEX"),
    ]


def test_no_triggers_for_gsm_text():
    assert analyze("Caf\u00e9 \u00e8 \u00e0 \u00f9 \u20ac").triggers == []


def test_tab_is_a_trigger():
    t = analyze("a\tb").triggers[0]
    assert t.name == "CHARACTER TABULATION"
    assert t.safe_replacement == " "


def test_to_dict_serialisable():
    json.dumps(analyze("a\u2019b " + EMOJI).to_dict())
