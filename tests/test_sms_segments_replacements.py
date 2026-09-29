import pytest

from sms_segments import analyze, apply_replacements, suggest


@pytest.mark.parametrize(
    "src,dst",
    [
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201a", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u201e", '"'),
        ("\u00a0", " "),
        ("\u202f", " "),
        ("\u2009", " "),
        ("\t", " "),
        ("\u2013", "-"),
        ("\u2014", "-"),
        ("\u2212", "-"),
        ("\u2010", "-"),
        ("\u2026", "..."),
        ("`", "'"),
        ("\u2022", "*"),
        ("\u200b", ""),
        ("\u00ad", ""),
        ("\ufeff", ""),
        ("\u2122", "TM"),
    ],
)
def test_each_safe_rule(src, dst):
    assert apply_replacements("a" + src + "b") == "a" + dst + "b"


def test_curly_quotes():
    s = suggest("It\u2019s \u201cdone\u201d")
    assert s.text == 'It\'s "done"'
    assert s.after.encoding == "GSM-7"


def test_guillemets_swallow_padding():
    assert apply_replacements("\u00ab\u00a0Bonjour\u00a0\u00bb", "fr") == '"Bonjour"'
    assert apply_replacements("\u00ab Bonjour \u00bb", "fr") == '"Bonjour"'
    assert apply_replacements("\u00abBonjour\u00bb", "fr") == '"Bonjour"'
    assert apply_replacements("\u00ab\u202fOui\u202f\u00bb", "fr") == '"Oui"'


def test_plain_spaces_untouched_without_guillemet():
    assert apply_replacements("a  b") == "a  b"


def test_french_nnbsp_saves_segments():
    text = "Rendez-vous demain\u202f: 14\u202fh 30. " + "x" * 50
    s = suggest(text, "fr")
    assert s.before.encoding == "UCS-2" and s.before.segments == 2
    assert s.after.encoding == "GSM-7" and s.after.segments == 1
    assert s.saved_segments == 1


def test_before_after_counts_ucs2_boundary():
    # 71 units UCS-2 (2 segments); after replacement 71 septets GSM-7 (1 segment)
    text = "a" * 70 + "\u2019"
    s = suggest(text)
    assert (s.before.segments, s.after.segments) == (2, 1)
    assert s.saved_units == 0


def test_gsm_accents_are_not_touched():
    text = "Caf\u00e9 \u00e8 \u00e0 \u00f9 \u00ec \u00f2 \u00c7 \u00c9"
    s = suggest(text, "fr", fold_accents=True)
    assert s.text == text and s.changes == []


def test_accents_are_opt_in():
    text = "Ch\u00e2teau de for\u00eat \u00e7a"
    s = suggest(text, "fr")
    assert s.text == text
    assert s.still_ucs2
    assert s.optin_segments == 1
    assert any("readability" in w for w in s.warnings)


def test_fold_accents_french():
    s = suggest(
        "Ch\u00e2teau de for\u00eat \u00e7a, \u0153uvre, ma\u00efs, \u00f4, \u00fb, \u00ee",
        "fr",
        fold_accents=True,
    )
    assert s.text == "Chateau de foret ca, oeuvre, mais, o, u, i"
    assert s.after.encoding == "GSM-7"
    assert all(c.optin for c in s.changes)


def test_fold_accents_spanish():
    s = suggest("Est\u00e1 aqu\u00ed, \u00f3ptimo, \u00fatil, \u00c1lvaro, \u00da, \u00aa", "es", fold_accents=True)
    assert s.text == "Esta aqui, optimo, util, Alvaro, U, a"
    assert s.after.encoding == "GSM-7"


def test_fold_accents_english_names():
    s = suggest("Zo\u00eb Beyonc\u00e9 na\u00efve", "en", fold_accents=True)
    assert s.text == "Zoe Beyonc\u00e9 naive"  # e-acute is GSM-7 and stays


def test_spanish_warning_text():
    s = suggest("Est\u00e1", "es", fold_accents=True)
    assert any("Spanish" in w for w in s.warnings)


def test_french_warning_mentions_tradeoff():
    s = suggest("for\u00eat", "fr", fold_accents=True)
    assert any("French" in w for w in s.warnings)


def test_emoji_has_no_replacement():
    s = suggest("Hi \U0001F600\u2019")
    assert s.text == "Hi \U0001F600'"
    assert s.still_ucs2
    assert [t.codepoint for t in s.remaining] == ["U+1F600"]
    assert any("No safe replacement" in w for w in s.warnings)


def test_decomposed_letter_is_composed_safely():
    # e + combining acute -> e-acute (GSM-7)
    s = suggest("cafe\u0301")
    assert s.text == "caf\u00e9"
    assert s.after.encoding == "GSM-7"
    assert s.changes[0].rule == "normalize"


def test_decomposed_non_gsm_letter_folds_only_when_opted_in():
    assert suggest("e\u0302").after.encoding == "UCS-2"
    assert suggest("e\u0302", fold_accents=True).text == "e"


def test_changes_record_index_and_codepoints():
    s = suggest("a\u2019b\u2026")
    assert [(c.index, c.replacement, c.rule) for c in s.changes] == [
        (1, "'", "quote"),
        (3, "...", "ellipsis"),
    ]
    assert s.changes[0].to_dict()["codepoints"] == "U+2019"


def test_language_fallback():
    assert apply_replacements("a\u2019", "fr-CA") == "a'"
    assert apply_replacements("a\u2019", "xx") == "a'"


def test_lengthening_replacement_is_counted_honestly():
    # ellipsis (1 unit) -> "..." (3 septets)
    s = suggest("a" * 68 + "\u2026")
    assert s.before.units == 69
    assert s.after.units == 71 and s.after.encoding == "GSM-7"
    assert s.after.segments == 1


def test_replacement_is_idempotent():
    text = "\u201cHi\u201d \u2013 5\u202f$"
    once = apply_replacements(text)
    assert apply_replacements(once) == once
    assert analyze(once).encoding == "GSM-7"
