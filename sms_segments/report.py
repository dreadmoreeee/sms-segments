"""Batch report building and JSON / Markdown rendering."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from dataclasses import dataclass

from .core import Analysis, Trigger
from .cost import CostEstimate, estimate_cost
from .suggest import Suggestion, suggest
from .template import LintResult, lint_template


@dataclass
class Message:
    text: str
    lang: str = "en"
    type: str = ""


@dataclass
class MessageReport:
    message: Message
    suggestion: Suggestion
    cost_before: CostEstimate | None = None
    cost_after: CostEstimate | None = None

    @property
    def before(self) -> Analysis:
        return self.suggestion.before

    @property
    def after(self) -> Analysis:
        return self.suggestion.after

    def to_dict(self) -> dict:
        d = {
            "lang": self.message.lang,
            "type": self.message.type,
            "text": self.message.text,
            "analysis": self.before.to_dict(),
            "replacements": self.suggestion.to_dict(),
        }
        if self.cost_before is not None:
            d["cost"] = {
                "before": self.cost_before.to_dict(),
                "after": self.cost_after.to_dict(),
                "monthly_saving": float(
                    round(self.cost_before.monthly_cost - self.cost_after.monthly_cost, 4)
                ),
            }
        return d


def build_report(
    messages: list[Message],
    fold_accents: bool = False,
    price=None,
    volume=None,
    currency: str = "CAD",
) -> dict:
    """Analyze every message; returns a dict with 'messages' and 'summary'."""
    with_cost = price is not None and volume is not None
    reports = []
    for m in messages:
        s = suggest(m.text, m.lang, fold_accents)
        r = MessageReport(m, s)
        if with_cost:
            r.cost_before = estimate_cost(s.before.segments, price, volume, currency)
            r.cost_after = estimate_cost(s.after.segments, price, volume, currency)
        reports.append(r)

    summary = {
        "messages": len(reports),
        "ucs2_messages": sum(1 for r in reports if r.before.encoding == "UCS-2"),
        "ucs2_messages_after": sum(1 for r in reports if r.after.encoding == "UCS-2"),
        "segments": sum(r.before.segments for r in reports),
        "segments_after": sum(r.after.segments for r in reports),
        "max_segments": max((r.before.segments for r in reports), default=0),
    }
    summary["saved_segments"] = summary["segments"] - summary["segments_after"]
    if with_cost:
        cb = sum(r.cost_before.monthly_cost for r in reports)
        ca = sum(r.cost_after.monthly_cost for r in reports)
        summary["cost"] = {
            "price_per_segment": reports[0].cost_before.to_dict()["price_per_segment"] if reports else None,
            "monthly_volume_per_message": float(reports[0].cost_before.monthly_volume) if reports else None,
            "monthly_cost_before": float(round(cb, 4)),
            "monthly_cost_after": float(round(ca, 4)),
            "monthly_saving": float(round(cb - ca, 4)),
            "currency": currency,
        }
    return {"messages": reports, "summary": summary}


def report_to_dict(report: dict) -> dict:
    return {
        "messages": [r.to_dict() for r in report["messages"]],
        "summary": report["summary"],
    }


def to_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- Markdown


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines


def _visible(t: Trigger) -> str:
    cat = unicodedata.category(t.char)
    if cat.startswith(("Z", "C", "M")) or t.char.isspace():
        return "(invisible)"
    return t.char


def _triggers_summary(triggers: list[Trigger]) -> str:
    if not triggers:
        return "none"
    counts = Counter(t.codepoint for t in triggers)
    return ", ".join(f"{cp}{'' if n == 1 else ' x' + str(n)}" for cp, n in counts.items())


def _seg(n: int) -> str:
    return f"{n} segment{'' if n == 1 else 's'}"


def report_to_markdown(report: dict) -> str:
    reports: list[MessageReport] = report["messages"]
    summary = report["summary"]
    out = ["# SMS segment report", ""]
    rows = []
    for i, r in enumerate(reports, 1):
        rows.append(
            [
                i,
                r.message.lang,
                r.message.type or "-",
                r.before.encoding,
                r.before.characters,
                f"{r.before.units} {'sept.' if r.before.encoding == 'GSM-7' else 'u16'}",
                r.before.segments,
                _triggers_summary(r.before.triggers),
                r.after.encoding,
                r.after.segments,
                r.suggestion.saved_segments,
            ]
        )
    out += _table(
        ["#", "Lang", "Type", "Encoding", "Chars", "Units", "Segments", "Forces UCS-2",
         "After: encoding", "After: segments", "Saved"],
        rows,
    )
    out += [""]
    out.append(
        f"{summary['messages']} message(s): {summary['ucs2_messages']} UCS-2, "
        f"{summary['segments']} segment(s) in total, {summary['segments_after']} after safe "
        f"replacements (saved {summary['saved_segments']})."
    )

    for i, r in enumerate(reports, 1):
        detail = r.before.triggers or r.suggestion.warnings
        if not detail:
            continue
        label = f"{i}. {r.message.lang}/{r.message.type}" if r.message.type else f"{i}. {r.message.lang}"
        out += ["", f"## Message {label}", ""]
        if r.before.triggers:
            out += _table(
                ["Index", "Char", "Codepoint", "Name", "Kind", "Safe replacement", "Opt-in (accent fold)"],
                [
                    [
                        t.index,
                        f"`{_visible(t)}`" if _visible(t) != "(invisible)" else _visible(t),
                        t.codepoint,
                        t.name,
                        t.category,
                        repr(t.safe_replacement) if t.safe_replacement is not None else "-",
                        repr(t.fold_replacement) if t.fold_replacement is not None else "-",
                    ]
                    for t in r.before.triggers
                ],
            )
            out.append("")
            out.append(
                f"After replacements: {r.after.encoding}, {_seg(r.after.segments)} "
                f"({r.before.units} -> {r.after.units} units)."
            )
            if r.suggestion.optin_segments is not None:
                out.append(
                    f"With accent folding (opt-in): {_seg(r.suggestion.optin_segments)}."
                )
        for w in r.suggestion.warnings:
            out += ["", f"> Warning: {w}"]

    if "cost" in summary:
        c = summary["cost"]
        out += ["", "## Monthly cost", ""]
        out += _table(
            ["#", "Segments before", "Segments after", f"Cost before ({c['currency']})",
             f"Cost after ({c['currency']})", "Saving"],
            [
                [
                    i,
                    r.before.segments,
                    r.after.segments,
                    f"{r.cost_before.monthly_cost:.2f}",
                    f"{r.cost_after.monthly_cost:.2f}",
                    f"{r.cost_before.monthly_cost - r.cost_after.monthly_cost:.2f}",
                ]
                for i, r in enumerate(reports, 1)
            ],
        )
        out += [
            "",
            f"Price {c['price_per_segment']} per segment, each message sent "
            f"{c['monthly_volume_per_message']:g} times a month: "
            f"{c['monthly_cost_before']:.2f} {c['currency']} as written, "
            f"{c['monthly_cost_after']:.2f} {c['currency']} after safe replacements "
            f"(saving {c['monthly_saving']:.2f}).",
        ]
    return "\n".join(out) + "\n"


def lint_to_markdown(results: list[LintResult]) -> str:
    out = ["# SMS template lint", ""]
    rows = []
    for i, r in enumerate(results, 1):
        rows.append(
            [
                i,
                r.literal.units,
                r.worst_case.encoding,
                r.worst_case.characters,
                r.worst_case.units,
                r.worst_case.segments,
                r.ucs2_risk_segments if r.ucs2_risk_segments is not None else "-",
                "ok" if r.ok else "OVER LIMIT",
            ]
        )
    out += _table(
        ["#", "Literal units", "Worst encoding", "Worst chars", "Worst units",
         "Worst segments", "If a value forces UCS-2", "Status"],
        rows,
    )
    for i, r in enumerate(results, 1):
        out += ["", f"## Template {i}", "", "```", r.template, "```", ""]
        if r.placeholders:
            out += _table(
                ["Placeholder", "Uses", "Max length", "Assumed charset"],
                [[p.name, p.count, f"{p.max_length}{' (default)' if p.default_used else ''}", p.charset]
                 for p in r.placeholders],
            )
        for w in r.warnings:
            out += ["", f"> Warning: {w}"]
    return "\n".join(out) + "\n"


def lint_report(templates: list[str], **kwargs) -> list[LintResult]:
    return [lint_template(t, **kwargs) for t in templates]
