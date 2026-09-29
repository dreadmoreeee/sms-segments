"""Template lint: worst-case length of a message with {name} / {{name}} placeholders."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .core import UCS2, Analysis, analyze

PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}|\{(\w+)\}")

# What a placeholder value is assumed to be made of in the worst case.
CHARSETS = {
    "gsm": "W",  # plain GSM-7 letter, 1 septet
    "gsm-ext": "|",  # GSM-7 extension character, 2 septets
    "ucs2": "\u00ea",  # e-circumflex: not in GSM-7, forces UCS-2 (BMP, 1 unit)
}


@dataclass
class PlaceholderInfo:
    name: str
    count: int
    max_length: int
    charset: str
    default_used: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "count": self.count,
            "max_length": self.max_length,
            "charset": self.charset,
            "default_max_used": self.default_used,
        }


@dataclass
class LintResult:
    template: str
    placeholders: list[PlaceholderInfo]
    literal: Analysis  # template with placeholders removed (best case)
    worst_case: Analysis
    worst_case_text: str
    max_segments: int | None = None
    ucs2_risk_segments: int | None = None  # worst case if a value forces UCS-2
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.max_segments is None or self.worst_case.segments <= self.max_segments

    def to_dict(self) -> dict:
        return {
            "template": self.template,
            "placeholders": [p.to_dict() for p in self.placeholders],
            "literal_only": self.literal.to_dict(),
            "worst_case": self.worst_case.to_dict(),
            "worst_case_text": self.worst_case_text,
            "segments_worst_case": self.worst_case.segments,
            "segments_if_a_value_forces_ucs2": self.ucs2_risk_segments,
            "max_segments": self.max_segments,
            "ok": self.ok,
            "warnings": list(self.warnings),
        }


def find_placeholders(template: str) -> list[tuple[str, int, int]]:
    """(name, start, end) of each {name} or {{name}} placeholder."""
    return [(m.group(1) or m.group(2), m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(template)]


def _render(template: str, fill) -> str:
    return PLACEHOLDER_RE.sub(lambda m: fill(m.group(1) or m.group(2)), template)


def lint_template(
    template: str,
    max_lengths: dict[str, int] | None = None,
    default_max: int = 15,
    values_charset: str = "gsm",
    ucs2_placeholders=(),
    max_segments: int | None = None,
) -> LintResult:
    """Worst-case analysis of a template.

    Each placeholder is replaced by ``max_lengths[name]`` (or ``default_max``)
    characters of the assumed value charset:

    * ``gsm``      plain GSM-7 letters (1 septet each)
    * ``gsm-ext``  extension characters such as ``|`` (2 septets each)
    * ``ucs2``     a character outside GSM-7 (e.g. an accented name): the whole
                   message becomes UCS-2

    Names in ``ucs2_placeholders`` use ``ucs2`` whatever the global charset.
    Lengths are in characters; an emoji in a value would count 2 UTF-16 units.
    """
    if values_charset not in CHARSETS:
        raise ValueError(f"values_charset must be one of {sorted(CHARSETS)}")
    if default_max < 0 or any(v < 0 for v in (max_lengths or {}).values()):
        raise ValueError("maximum lengths must be >= 0")
    max_lengths = dict(max_lengths or {})
    ucs2_names = set(ucs2_placeholders)

    def charset_for(name: str) -> str:
        return "ucs2" if name in ucs2_names else values_charset

    def fill_with(cs_for):
        return lambda name: CHARSETS[cs_for(name)] * max_lengths.get(name, default_max)

    found = find_placeholders(template)
    infos: list[PlaceholderInfo] = []
    for name in dict.fromkeys(n for n, _, _ in found):
        infos.append(
            PlaceholderInfo(
                name,
                sum(1 for n, _, _ in found if n == name),
                max_lengths.get(name, default_max),
                charset_for(name),
                name not in max_lengths,
            )
        )

    literal = analyze(_render(template, lambda _n: ""))
    worst_text = _render(template, fill_with(charset_for))
    worst = analyze(worst_text)
    result = LintResult(template, infos, literal, worst, worst_text, max_segments)

    if not found:
        result.warnings.append("No placeholders found; only {name} and {{name}} are recognised.")
    if any(p.default_used for p in infos):
        names = ", ".join(p.name for p in infos if p.default_used)
        result.warnings.append(f"Default maximum length ({default_max}) used for: {names}.")
    stray = PLACEHOLDER_RE.sub("", template)
    if "{" in stray or "}" in stray:
        result.warnings.append(
            "Unmatched brace: '{' and '}' cost 2 septets each and are not placeholders here."
        )
    if literal.encoding == UCS2:
        cps = ", ".join(sorted({t.codepoint for t in literal.triggers}))
        result.warnings.append(f"The literal text already forces UCS-2 ({cps}).")
    if worst.encoding != UCS2 and infos:
        risk = analyze(_render(template, fill_with(lambda _n: "ucs2")))
        result.ucs2_risk_segments = risk.segments
        if risk.segments > worst.segments:
            result.warnings.append(
                f"If a value contains a character outside GSM-7 (e.g. an accented name) the "
                f"worst case rises from {worst.segments} to {risk.segments} segments "
                "(use --values-charset ucs2 or --ucs2-placeholders)."
            )
    if not result.ok:
        result.warnings.append(
            f"Worst case is {worst.segments} segments, over the limit of {max_segments}."
        )
    return result
