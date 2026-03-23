"""Pure UTXO coin-selection and aggregation functions.

All functions are stateless and operate on plain dicts following the
UTXO schema used by MultiUserWalletLedger (keys: utxo_id, wallet_id,
currency, amount, source, created_at).
"""

from __future__ import annotations

from decimal import Decimal

from domain.precision import normalize_amount


def sum_utxos(utxos: list[dict], currency: str) -> Decimal:
    """Return the total amount of *utxos* matching *currency*."""
    total = Decimal("0")
    for utxo in utxos:
        if str(utxo.get("currency", "")) != currency:
            continue
        total += normalize_amount(utxo.get("amount", "0"))
    return total


def select_utxos(
    utxos: list[dict],
    currency: str,
    target_amount: Decimal,
) -> tuple[list[dict], Decimal]:
    """Greedy-select UTXOs until *target_amount* is covered.

    Returns ``(selected, selected_total)`` where *selected* is the list
    of chosen UTXO dicts and *selected_total* is their summed amount.
    The caller must verify that ``selected_total >= target_amount``.
    """
    selected: list[dict] = []
    selected_total = Decimal("0")
    for utxo in utxos:
        if str(utxo.get("currency", "")) != currency:
            continue
        selected.append(utxo)
        selected_total += normalize_amount(utxo.get("amount", "0"))
        if selected_total >= target_amount:
            break
    return selected, selected_total


def consumed_utxo_ids(selected: list[dict]) -> set[str]:
    """Return the set of ``utxo_id`` values from *selected*."""
    return {str(item.get("utxo_id", "")) for item in selected}


def remove_consumed_utxos(utxos: list[dict], ids_to_remove: set[str]) -> list[dict]:
    """Return *utxos* with entries whose ``utxo_id`` is in *ids_to_remove* filtered out."""
    return [
        utxo for utxo in utxos
        if str(utxo.get("utxo_id", "")) not in ids_to_remove
    ]
