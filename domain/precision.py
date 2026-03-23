"""
Monetary precision constants and normalization for blockchain amounts.
Single source of truth for UNIT/SATOSHI and normalize_amount().
"""
from decimal import Decimal, ROUND_DOWN

UNIT = Decimal("0.00000001")
SATOSHI = UNIT  # alias for UTXO model compatibility


def normalize_amount(value: Decimal | int | float | str) -> Decimal:
    """Normalize a monetary value to 8 decimal places, rounded down."""
    normalized = Decimal(str(value)).quantize(UNIT, rounding=ROUND_DOWN)
    return Decimal(format(normalized, "f")).quantize(UNIT, rounding=ROUND_DOWN)
