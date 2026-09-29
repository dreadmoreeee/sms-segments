from decimal import Decimal

import pytest

from sms_segments import estimate_cost, lint_template


# ---------------------------------------------------------------- cost


def test_cost_basic():
    c = estimate_cost(2, "0.0079", 10000, "CAD")
    assert c.monthly_segments == 20000
    assert c.monthly_cost == Decimal("158.0000")
    assert c.to_dict()["monthly_cost"] == 158.0


def test_cost_zero_segments():
    assert estimate_cost(0, 0.01, 100).monthly_cost == 0


@pytest.mark.parametrize("price,volume", [(-1, 10), (0.01, -5), ("abc", 1), (float("nan"), 1)])
def test_cost_rejects_bad_input(price, volume):
    with pytest.raises(ValueError):
        estimate_cost(1, price, volume)


# ---------------------------------------------------------------- lint


def test_lint_finds_both_placeholder_styles():
    r = lint_template("Hi {name}, see {{time}} and {name}", default_max=5)
    names = {p.name: p.count for p in r.placeholders}
    assert names == {"name": 2, "time": 1}


def test_lint_worst_case_length():
    r = lint_template("Hi {name}!", max_lengths={"name": 20})
    assert r.worst_case.units == 3 + 20 + 1
    assert r.worst_case.segments == 1
    assert r.literal.units == 4


def test_lint_worst_case_crosses_segment_boundary():
    r = lint_template("x" * 150 + "{a}", max_lengths={"a": 10})
    assert r.worst_case.units == 160 and r.worst_case.segments == 1
    r = lint_template("x" * 150 + "{a}", max_lengths={"a": 11})
    assert r.worst_case.segments == 2


def test_lint_default_max_and_warning():
    r = lint_template("Hi {name}", default_max=12)
    assert r.worst_case.units == 3 + 12
    assert any("Default maximum" in w for w in r.warnings)


def test_lint_ext_charset_costs_double():
    r = lint_template("{a}", max_lengths={"a": 10}, values_charset="gsm-ext")
    assert r.worst_case.units == 20


def test_lint_ucs2_charset_switches_encoding():
    r = lint_template("x" * 60 + "{name}", max_lengths={"name": 10}, values_charset="ucs2")
    assert r.worst_case.encoding == "UCS-2"
    assert r.worst_case.units == 70 and r.worst_case.segments == 1
    r = lint_template("x" * 60 + "{name}", max_lengths={"name": 11}, values_charset="ucs2")
    assert r.worst_case.segments == 2


def test_lint_ucs2_only_for_named_placeholders():
    r = lint_template("{name} {ref}", max_lengths={"name": 5, "ref": 5}, ucs2_placeholders=["name"])
    assert r.worst_case.encoding == "UCS-2"
    by = {p.name: p.charset for p in r.placeholders}
    assert by == {"name": "ucs2", "ref": "gsm"}


def test_lint_warns_about_ucs2_risk():
    r = lint_template("x" * 100 + "{name}", max_lengths={"name": 20})
    assert r.worst_case.segments == 1
    assert r.ucs2_risk_segments == 2
    assert any("worst case rises" in w for w in r.warnings)


def test_lint_literal_ucs2_warning():
    r = lint_template("Merci\u202f! {name}")
    assert r.literal.encoding == "UCS-2"
    assert any("U+202F" in w for w in r.warnings)


def test_lint_unmatched_brace():
    r = lint_template("Hello {name and {ok}")
    assert any("Unmatched brace" in w for w in r.warnings)


def test_lint_max_segments_gate():
    r = lint_template("x" * 150 + "{a}", max_lengths={"a": 30}, max_segments=1)
    assert not r.ok
    r = lint_template("x" * 150 + "{a}", max_lengths={"a": 5}, max_segments=1)
    assert r.ok


def test_lint_no_placeholders_warns():
    assert any("No placeholders" in w for w in lint_template("plain").warnings)


def test_lint_bad_charset():
    with pytest.raises(ValueError):
        lint_template("{a}", values_charset="latin1")
