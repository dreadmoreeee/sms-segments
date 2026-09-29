import json
import subprocess
import sys
from pathlib import Path

from sms_segments.cli import main

TOOL = Path(__file__).resolve().parent.parent


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_default_subcommand_is_analyze(capsys):
    code, out, _ = run(capsys, "Hello there", "--format", "json")
    data = json.loads(out)
    assert code == 0
    assert data["messages"][0]["analysis"]["segments"] == 1


def test_json_samples_shape(tmp_path, capsys):
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            [
                {"lang": "fr", "type": "confirmacion", "text": "Rendez-vous\u202f: demain"},
                {"lang": "en", "type": "recordatorio", "text": "See you soon"},
            ]
        ),
        encoding="utf-8",
    )
    code, out, _ = run(capsys, "--json", str(p), "--format", "json")
    data = json.loads(out)
    assert code == 0
    m0, m1 = data["messages"]
    assert (m0["lang"], m0["type"]) == ("fr", "confirmacion")
    assert m0["analysis"]["encoding"] == "UCS-2"
    assert m0["replacements"]["encoding_after"] == "GSM-7"
    assert m1["analysis"]["encoding"] == "GSM-7"
    assert data["summary"]["ucs2_messages"] == 1


def test_markdown_output(capsys):
    code, out, _ = run(capsys, "It\u2019s ok")
    assert code == 0
    assert out.startswith("# SMS segment report")
    assert "U+2019" in out


def test_cost_requires_both_flags(capsys):
    code, _, err = run(capsys, "hi", "--price", "0.01")
    assert code == 2 and "together" in err


def test_cost_in_output(capsys):
    code, out, _ = run(capsys, "hi", "--price", "0.01", "--volume", "1000", "--format", "json")
    cost = json.loads(out)["messages"][0]["cost"]
    assert cost["before"]["monthly_cost"] == 10.0


def test_max_segments_gate(capsys):
    code, _, err = run(capsys, "a" * 161, "--max-segments", "1")
    assert code == 1 and "more than 1" in err
    code, _, _ = run(capsys, "a" * 160, "--max-segments", "1")
    assert code == 0


def test_no_input_is_error(capsys):
    code, _, err = run(capsys, "analyze")
    assert code == 2 and "no input" in err


def test_bad_json_is_error(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    code, _, err = run(capsys, "--json", str(p))
    assert code == 2 and "not valid JSON" in err


def test_json_item_without_text(tmp_path, capsys):
    p = tmp_path / "x.json"
    p.write_text('[{"lang": "en"}]', encoding="utf-8")
    code, _, err = run(capsys, "--json", str(p))
    assert code == 2 and "text" in err


def test_file_lines(tmp_path, capsys):
    p = tmp_path / "m.txt"
    p.write_text("one\ntwo\n\nthree\n", encoding="utf-8")
    code, out, _ = run(capsys, "--file", str(p), "--lines", "--format", "json")
    assert len(json.loads(out)["messages"]) == 3


def test_fold_accents_flag(capsys):
    _, out, _ = run(capsys, "for\u00eat", "--lang", "fr", "--fold-accents", "--format", "json")
    r = json.loads(out)["messages"][0]["replacements"]
    assert r["text_after"] == "foret" and r["encoding_after"] == "GSM-7"


def test_lint_command(capsys):
    code, out, _ = run(capsys, "lint", "Hi {name}!", "--max", "name=20", "--format", "json")
    t = json.loads(out)["templates"][0]
    assert code == 0 and t["worst_case"]["units"] == 24


def test_lint_gate_and_ucs2(capsys):
    code, out, _ = run(
        capsys,
        "lint",
        "x" * 60 + "{name}",
        "--max",
        "name=11",
        "--ucs2-placeholders",
        "name",
        "--max-segments",
        "1",
        "--format",
        "json",
    )
    t = json.loads(out)["templates"][0]
    assert code == 1 and t["worst_case"]["encoding"] == "UCS-2" and not t["ok"]


def test_lint_bad_max(capsys):
    code, _, _ = run(capsys, "lint", "{a}", "--max", "oops")
    assert code == 2


def test_lint_markdown(capsys):
    _, out, _ = run(capsys, "lint", "Hi {name}")
    assert out.startswith("# SMS template lint")


def test_python_dash_m():
    proc = subprocess.run(
        [sys.executable, "-m", "sms_segments", "Hello", "--format", "json"],
        cwd=TOOL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["summary"]["segments"] == 1
