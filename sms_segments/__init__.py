"""SMS length, encoding and cost calculator (GSM 03.38 / UCS-2)."""

from .core import (
    GSM7,
    LIMITS,
    UCS2,
    Analysis,
    Trigger,
    analyze,
    detect_encoding,
    split_segments,
)
from .cost import CostEstimate, estimate_cost
from .gsm import EXTENSION_TABLE, GSM_ALL, GSM_BASIC, GSM_EXTENSION, is_gsm7
from .suggest import Change, Suggestion, apply_replacements, suggest
from .template import LintResult, lint_template

__version__ = "0.1.0"

__all__ = [
    "GSM7",
    "UCS2",
    "LIMITS",
    "Analysis",
    "Trigger",
    "Change",
    "Suggestion",
    "CostEstimate",
    "LintResult",
    "analyze",
    "detect_encoding",
    "split_segments",
    "suggest",
    "apply_replacements",
    "estimate_cost",
    "lint_template",
    "is_gsm7",
    "GSM_BASIC",
    "GSM_EXTENSION",
    "GSM_ALL",
    "EXTENSION_TABLE",
    "__version__",
]
