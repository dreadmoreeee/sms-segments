"""Python API tour. Run from the tool folder: python examples/api_example.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sms_segments import analyze, estimate_cost, lint_template, suggest  # noqa: E402

text = "Hi Sam, it\u2019s a reminder \u2013 see you tomorrow at 2:30 PM\u2026 " + "x" * 30

a = analyze(text)
print(a.encoding, a.characters, "chars,", a.units, a.unit_name, "->", a.segments, "segment(s)")
for t in a.triggers:
    print(f"  index {t.index}: {t.codepoint} {t.name} -> {t.safe_replacement!r}")

s = suggest(text, lang="en")
print("after safe replacements:", s.after.encoding, s.after.segments, "segment(s), saved", s.saved_segments)
print(s.text)

cost = estimate_cost(s.before.segments, "0.0079", 12000, "CAD")
saving = cost.monthly_cost - estimate_cost(s.after.segments, "0.0079", 12000, "CAD").monthly_cost
print(f"monthly cost as written: {cost.monthly_cost:.2f} CAD, saving {saving:.2f} CAD")

lint = lint_template(
    "{shop}: Hi {name}, reminder: {service} on {date}.",
    max_lengths={"shop": 25, "name": 20, "service": 30, "date": 20},
    ucs2_placeholders=["name"],
    max_segments=1,
)
print("template worst case:", lint.worst_case.encoding, lint.worst_case.segments, "segment(s), ok =", lint.ok)
for w in lint.warnings:
    print("  warning:", w)
