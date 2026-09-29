"""Command line interface: ``sms-segments`` / ``python -m sms_segments``."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .replacements import normalize_lang
from .report import (
    Message,
    build_report,
    lint_report,
    lint_to_markdown,
    report_to_dict,
    report_to_markdown,
    to_json,
)

COMMANDS = ("analyze", "lint")


class InputError(Exception):
    pass


def _read(path: str) -> str:
    try:
        if path == "-":
            return sys.stdin.read()
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise InputError(f"{path} is not valid UTF-8: {exc}") from exc


def _messages_from_json(raw: str, default_lang: str, source: str) -> list[Message]:
    """Accepts [{"lang","type","text"}, ...], a single object, or a list of strings."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputError(f"{source} is not valid JSON: {exc}") from exc
    if isinstance(data, (dict, str)):
        data = [data]
    if not isinstance(data, list):
        raise InputError(f"{source}: expected a list of messages")
    out = []
    for n, item in enumerate(data, 1):
        if isinstance(item, str):
            out.append(Message(item, default_lang))
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            out.append(
                Message(
                    item["text"],
                    normalize_lang(item.get("lang"), default_lang),
                    str(item.get("type", "")),
                )
            )
        else:
            raise InputError(f"{source}: item {n} needs a string 'text' field")
    return out


def _collect(args) -> list[Message]:
    msgs: list[Message] = []
    lang = normalize_lang(args.lang)
    for t in args.texts:
        msgs.append(Message(t, lang))
    if args.json:
        msgs += _messages_from_json(_read(args.json), lang, args.json)
    if args.file:
        raw = _read(args.file)
        if args.lines:
            msgs += [Message(line, lang) for line in raw.splitlines() if line]
        else:
            msgs.append(Message(raw[:-1] if raw.endswith("\n") else raw, lang))
    if not msgs:
        raise InputError("no input: give TEXT, --json FILE or --file FILE")
    return msgs


def _add_input(p: argparse.ArgumentParser) -> None:
    p.add_argument("texts", nargs="*", metavar="TEXT", help="message text (repeatable)")
    p.add_argument("--json", metavar="FILE", help="JSON list of {lang,type,text} objects ('-' = stdin)")
    p.add_argument("--file", metavar="FILE", help="plain text file, one message ('-' = stdin)")
    p.add_argument("--lines", action="store_true", help="with --file: one message per line")
    p.add_argument("--lang", default="en", help="default language: en, fr or es (default en)")
    p.add_argument("--format", choices=("json", "markdown"), default="markdown", help="output format")
    p.add_argument("--max-segments", type=int, metavar="N", help="exit 1 if any message needs more than N segments")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="sms-segments",
        description="SMS length, encoding and cost calculator (GSM 03.38 / UCS-2).",
    )
    ap.add_argument("--version", action="version", version=f"sms-segments {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="{analyze,lint}")

    a = sub.add_parser("analyze", help="encoding, segments, UCS-2 triggers, replacements, cost")
    _add_input(a)
    a.add_argument("--fold-accents", action="store_true",
                   help="opt-in: also map accented letters outside GSM-7 to the nearest GSM form")
    a.add_argument("--price", type=float, metavar="P", help="price per segment")
    a.add_argument("--volume", type=float, metavar="N", help="messages per month (each message is sent N times)")
    a.add_argument("--currency", default="CAD", help="currency label (default CAD)")

    l = sub.add_parser("lint", help="worst-case length of templates with {name} / {{name}} placeholders")
    _add_input(l)
    l.add_argument("--max", action="append", default=[], metavar="NAME=N",
                   help="maximum length of a placeholder value (repeatable)")
    l.add_argument("--default-max", type=int, default=15, metavar="N",
                   help="maximum length for placeholders without --max (default 15)")
    l.add_argument("--values-charset", choices=("gsm", "gsm-ext", "ucs2"), default="gsm",
                   help="assume values are plain GSM-7, all extension characters, or force UCS-2")
    l.add_argument("--ucs2-placeholders", default="", metavar="A,B",
                   help="placeholders whose values may contain accents / non-GSM characters")
    return ap


def _emit(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _run_analyze(args) -> int:
    if (args.price is None) != (args.volume is None):
        raise InputError("--price and --volume must be given together")
    messages = _collect(args)
    rep = build_report(messages, args.fold_accents, args.price, args.volume, args.currency)
    _emit(to_json(report_to_dict(rep)) if args.format == "json" else report_to_markdown(rep))
    if args.max_segments is not None and rep["summary"]["max_segments"] > args.max_segments:
        print(f"error: a message needs more than {args.max_segments} segment(s)", file=sys.stderr)
        return 1
    return 0


def _run_lint(args) -> int:
    limits = {}
    for item in args.max:
        name, sep, val = item.partition("=")
        if not sep or not val.isdigit():
            raise InputError(f"--max expects NAME=N, got {item!r}")
        limits[name] = int(val)
    templates = [m.text for m in _collect(args)]
    try:
        results = lint_report(
            templates,
            max_lengths=limits,
            default_max=args.default_max,
            values_charset=args.values_charset,
            ucs2_placeholders=[n for n in args.ucs2_placeholders.split(",") if n],
            max_segments=args.max_segments,
        )
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    if args.format == "json":
        _emit(to_json({"templates": [r.to_dict() for r in results]}))
    else:
        _emit(lint_to_markdown(results))
    return 0 if all(r.ok for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "--version"):
        argv.insert(0, "analyze")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help()
        return 2
    try:
        return _run_analyze(args) if args.command == "analyze" else _run_lint(args)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
