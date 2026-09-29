# sms-segments

SMS length, encoding and cost calculator for businesses that send text reminders. It tells you whether a message goes out as GSM-7 or UCS-2, how many segments it costs, which characters forced UCS-2, and what a safe cleanup would save. Pure Python standard library, no dependencies.

## Quick start

```bash
python -m sms_segments "Hi Sam, your visit is tomorrow at 2:30 PM"   # or: sms-segments ...
python -m sms_segments --json messages.json --format json
python -m sms_segments --json messages.json --price 0.0079 --volume 12000
python -m sms_segments lint --json templates.json --max name=20 --ucs2-placeholders name
```

Install with `pip install .` for the `sms-segments` console script, or run it in place with `python -m sms_segments` from this folder (Python 3.10+).

`analyze` is the default command. Input is TEXT arguments, `--file FILE` (`--lines` for one message per line) or `--json FILE`, a list of `{"lang", "type", "text"}` objects (`lang` is en/fr/es; a plain list of strings also works). Output is Markdown by default, `--format json` for machines.

## How segments are counted

| Encoding | One segment | Concatenated, per segment |
|---|---|---|
| GSM-7 (GSM 03.38) | 160 septets | 153 |
| UCS-2 | 70 UTF-16 code units | 67 |

- The GSM 03.38 basic table plus extension table are in `sms_segments/gsm.py`, with the 3GPP TS 23.038 source noted.
- Extension characters (`EURO SIGN`, `[ ] { } ~ ^ | \` and form feed) cost 2 septets.
- One character outside GSM-7 forces the whole message to UCS-2. Note that e-acute, e-grave, a-grave, u-grave and capital C-cedilla are GSM-7; e-circumflex, o-circumflex, u-circumflex, i-circumflex and lowercase c-cedilla are not.
- Length is counted in UTF-16 code units, so an emoji outside the BMP costs 2.
- **No character is split across segments.** A 2-septet extension character or a UCS-2 surrogate pair that does not fit in the room left starts the next segment, so a segment can hold 152 septets or 66 units. Characters are code points: a grapheme cluster (an emoji ZWJ sequence, a letter plus combining mark) can still straddle a boundary, though the count stays correct.

## What forces UCS-2

Every trigger is listed with its 0-based index, codepoint, Unicode name and kind: curly quotes, the non-breaking space U+00A0, the narrow no-break space U+202F (common in French, e.g. before `:` or in `14 h`), dashes, the ellipsis, tabs, emoji and accented letters outside GSM-7.

## Safe replacements

Always applied to compute the "after" count:

| Found | Replaced with |
|---|---|
| curly single / double quotes, backtick | `'` / `"` |
| guillemets (with padding spaces) | `"` |
| NBSP, NNBSP, thin and other spaces, tab | space |
| en / em dash, minus, hyphen variants | `-` |
| ellipsis | `...` |
| zero-width characters, soft hyphen | removed |
| bullet, TM, (c), (R), arrows | `*`, `TM`, `(c)`, `(R)`, `->` |
| letter + combining accent that composes to a GSM letter | the composed letter |

The report shows segments before and after; a replacement can lengthen the text (`...` is 3 septets), and the count says so.

**Accent folding is opt-in** (`--fold-accents`, `fold_accents=True`) because it changes spelling. Per language (en / fr / es): French drops circumflexes, diaereses and cedillas (`foret`, `garcon`; `oeuvre`), which can read oddly or collide with other words; Spanish drops the acute on a, i, o, u (`esta`, `papa`), which can change meaning. Letters already in GSM-7 are never touched. Without the flag the report still shows how many segments folding would give.

## Cost

`--price` (per segment) and `--volume` (messages a month) give `segments x volume x price`, before and after replacements. With several messages, each is assumed sent `--volume` times.

## Template lint

```bash
sms-segments lint "{shop}: Hi {name}, {service} on {date}." --max name=20 --max shop=25 --default-max 15
```

Placeholders are `{name}` or `{{name}}`. The worst case fills each with its maximum length (`--max NAME=N`, `--default-max`). Values are assumed plain GSM-7 by default; `--values-charset gsm-ext` assumes 2-septet characters, `--values-charset ucs2` assumes a non-GSM character (the whole message becomes UCS-2), and `--ucs2-placeholders name,city` does that only for names that may carry accents. Lint also warns when a UCS-2 value would raise the segment count, when the literal text already forces UCS-2, and on unmatched braces.

## CI gates

`--max-segments N` exits 1 when a message (or a template's worst case) needs more than N segments; exit 2 means bad input. A ready-made job is in `examples/ci-example.yml`.

## Python API

```python
from sms_segments import analyze, suggest, estimate_cost, lint_template

a = analyze("Total: 20\u20ac")           # encoding, units, segments, triggers
s = suggest(text, lang="fr")             # s.before, s.after, s.text, s.changes, s.saved_segments
c = estimate_cost(a.segments, "0.0079", 12000, "CAD").monthly_cost
r = lint_template("Hi {name}", max_lengths={"name": 20}, ucs2_placeholders=["name"])
```

More in `examples/api_example.py`; sample inputs are `examples/messages.json` and `examples/templates.json`.

## Tests

```bash
python -m pytest -q -p no:cacheprovider --import-mode=importlib sms-segments
```

Covers 160/161 GSM, 306/307, 70/71 UCS-2, 134/135, extension characters and surrogate pairs at segment edges, and every replacement rule.

## Measured result

The CLI run on the real DeMark Studio messages (`_demark-sms/samples.json`, 8 messages in en and fr), from this folder:

```
python -m sms_segments --json ../_demark-sms/samples.json
```

```
# SMS segment report

| # | Lang | Type | Encoding | Chars | Units | Segments | Forces UCS-2 | After: encoding | After: segments | Saved |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | en | cancelacion | GSM-7 | 94 | 94 sept. | 1 | none | GSM-7 | 1 | 0 |
| 2 | en | confirmacion | GSM-7 | 136 | 136 sept. | 1 | none | GSM-7 | 1 | 0 |
| 3 | en | recordatorio | GSM-7 | 93 | 93 sept. | 1 | none | GSM-7 | 1 | 0 |
| 4 | en | reprogramada | GSM-7 | 142 | 142 sept. | 1 | none | GSM-7 | 1 | 0 |
| 5 | fr | cancelacion | GSM-7 | 110 | 110 sept. | 1 | none | GSM-7 | 1 | 0 |
| 6 | fr | confirmacion | GSM-7 | 156 | 156 sept. | 1 | none | GSM-7 | 1 | 0 |
| 7 | fr | recordatorio | GSM-7 | 110 | 110 sept. | 1 | none | GSM-7 | 1 | 0 |
| 8 | fr | reprogramada | GSM-7 | 167 | 167 sept. | 2 | none | GSM-7 | 2 | 0 |

8 message(s): 0 UCS-2, 9 segment(s) in total, 9 after safe replacements (saved 0).
```

What it shows, honestly:

- All 8 messages are GSM-7. Nothing forces UCS-2: the French texts use only e-acute (in GSM-7) and plain ASCII spaces, so there is nothing to replace and the saving is 0 segments.
- 7 of 8 messages are 1 segment. The exception is the French "reprogramada" message: 167 septets, 7 over the 160 limit, so it costs 2 segments. The French "confirmacion" message (156) has only 4 septets of headroom.
- Check with `--max-segments 1`: exit code 1, because of that one message.

pytest: `164 passed in 0.40s`

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
