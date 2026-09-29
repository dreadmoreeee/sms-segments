"""Monthly cost estimate from a per-segment price and a monthly volume."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _dec(value, name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{name} must be a number, got {value!r}") from None
    if not d.is_finite() or d < 0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
    return d


@dataclass
class CostEstimate:
    segments_per_message: int
    price_per_segment: Decimal
    monthly_volume: Decimal  # messages per month
    currency: str

    @property
    def monthly_segments(self) -> Decimal:
        return self.monthly_volume * self.segments_per_message

    @property
    def monthly_cost(self) -> Decimal:
        return self.monthly_segments * self.price_per_segment

    def to_dict(self) -> dict:
        return {
            "segments_per_message": self.segments_per_message,
            "price_per_segment": float(self.price_per_segment),
            "monthly_volume": float(self.monthly_volume),
            "monthly_segments": float(self.monthly_segments),
            "monthly_cost": float(round(self.monthly_cost, 4)),
            "currency": self.currency,
        }


def estimate_cost(
    segments: int, price_per_segment, monthly_volume, currency: str = "CAD"
) -> CostEstimate:
    """Cost of sending a ``segments``-segment message ``monthly_volume`` times a month.

    Carriers bill per segment, so cost = segments x volume x price.
    """
    if segments < 0:
        raise ValueError("segments must be >= 0")
    return CostEstimate(
        segments,
        _dec(price_per_segment, "price"),
        _dec(monthly_volume, "volume"),
        currency,
    )
