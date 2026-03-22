"""Cross-currency exchange: rates, conversion, and commission logic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

UNIT = Decimal("0.00000001")


@dataclass
class ExchangeRate:
    from_currency: str
    to_currency: str
    rate: Decimal
    commission_pct: Decimal
    updated_at: str


def pair_key(from_currency: str, to_currency: str) -> str:
    return f"{from_currency.upper()}-{to_currency.upper()}"


def convert_amount(amount: Decimal, rate: Decimal, commission_pct: Decimal) -> dict:
    """Convert amount using rate and apply commission.

    Returns dict with gross_amount, commission, net_amount (all quantized to 8 decimals).
    """
    gross = (amount * rate).quantize(UNIT, rounding=ROUND_DOWN)
    commission = (gross * commission_pct / Decimal("100")).quantize(UNIT, rounding=ROUND_DOWN)
    net = gross - commission
    return {
        "gross_amount": str(gross),
        "commission": str(commission),
        "net_amount": str(net),
        "rate": str(rate),
        "commission_pct": str(commission_pct),
    }
