"""Tests for cross-currency exchange feature (v2.6.0)."""

from decimal import Decimal

from domain.exchange import convert_amount, pair_key, ExchangeRate
from domain.multiuser_wallet_ledger import MultiUserWalletLedger


# ── Helpers ──────────────────────────────────────────────


def _setup_two_currency_ledger(model="ACCOUNT"):
    """Create a ledger with Alice (BTC) and Bob (SOL), mint 100 BTC to Alice."""
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    ledger.create_user("u-bob", "Bob")
    wa = ledger.create_wallet("u-alice", wallet_id="wallet_alice_btc_001", currency="BTC", model=model)
    ledger.create_wallet("u-bob", wallet_id="wallet_bob_sol_00001", currency="SOL", model=model)
    ledger.mint("wallet_alice_btc_001", "100")
    ledger.mint("wallet_bob_sol_00001", "0")
    return ledger, wa["auth_token"]


# ── Unit tests: domain/exchange.py ───────────────────────


def test_pair_key_format():
    assert pair_key("btc", "sol") == "BTC-SOL"
    assert pair_key("SOL", "btc") == "SOL-BTC"


def test_convert_amount_basic():
    result = convert_amount(Decimal("10"), Decimal("150"), Decimal("1"))
    assert result["gross_amount"] == "1500.00000000"
    assert result["commission"] == "15.00000000"
    assert result["net_amount"] == "1485.00000000"


def test_convert_amount_zero_commission():
    result = convert_amount(Decimal("5"), Decimal("200"), Decimal("0"))
    assert Decimal(result["commission"]) == Decimal("0")
    assert result["net_amount"] == result["gross_amount"]


# ── Integration tests: ledger exchange ───────────────────


def test_set_and_get_exchange_rate():
    ledger = MultiUserWalletLedger()
    result = ledger.set_exchange_rate("BTC", "SOL", "150.0", commission_pct="1.0")
    assert isinstance(result, dict)
    assert result["pair_id"] == "BTC-SOL"
    assert result["rate"] == "150.00000000"
    assert result["commission_pct"] == "1.00"

    fetched = ledger.get_exchange_rate("BTC", "SOL")
    assert fetched is not None
    assert fetched["rate"] == "150.00000000"

    assert ledger.get_exchange_rate("SOL", "BTC") is None


def test_set_exchange_rate_validations():
    ledger = MultiUserWalletLedger()
    assert ledger.set_exchange_rate("BTC", "BTC", "1").startswith("Error")
    assert ledger.set_exchange_rate("BTC", "SOL", "0").startswith("Error")
    assert ledger.set_exchange_rate("BTC", "SOL", "-5").startswith("Error")
    assert ledger.set_exchange_rate("", "SOL", "1").startswith("Error")


def test_list_exchange_rates():
    ledger = MultiUserWalletLedger()
    assert ledger.list_exchange_rates() == []
    ledger.set_exchange_rate("BTC", "SOL", "150")
    ledger.set_exchange_rate("SOL", "ETH", "0.005")
    rates = ledger.list_exchange_rates()
    assert len(rates) == 2


def test_exchange_btc_to_sol_account():
    ledger, token = _setup_two_currency_ledger("ACCOUNT")
    ledger.set_exchange_rate("BTC", "SOL", "150", commission_pct="1.0")

    result = ledger.transfer(
        "wallet_alice_btc_001", "wallet_bob_sol_00001", "10",
        fee="0", sender_token=token,
    )
    assert "Transferencia" in result

    alice_balance = ledger.get_wallet_balance("wallet_alice_btc_001")
    bob_balance = ledger.get_wallet_balance("wallet_bob_sol_00001")
    assert alice_balance == Decimal("90.00000000")
    assert bob_balance == Decimal("1485.00000000")


def test_exchange_with_commission():
    ledger, token = _setup_two_currency_ledger("ACCOUNT")
    ledger.set_exchange_rate("BTC", "SOL", "100", commission_pct="2.5")

    ledger.transfer(
        "wallet_alice_btc_001", "wallet_bob_sol_00001", "1",
        fee="0", sender_token=token,
    )
    bob_balance = ledger.get_wallet_balance("wallet_bob_sol_00001")
    # gross = 100, commission = 2.5, net = 97.5
    assert bob_balance == Decimal("97.50000000")


def test_exchange_same_currency_uses_normal_transfer():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    wa = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01", currency="BTC")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02", currency="BTC")
    ledger.mint("wallet_user_alpha_01", "50")

    result = ledger.transfer(
        "wallet_user_alpha_01", "wallet_user_bravo_02", "10",
        fee="0", sender_token=wa["auth_token"],
    )
    assert "Transferencia" in result
    transfers = ledger.state_snapshot()["transfers"]
    last_transfer = transfers[-1]
    assert last_transfer["type"] == "TRANSFER"
    assert "sender_currency" not in last_transfer


def test_exchange_without_rate_fails():
    ledger, token = _setup_two_currency_ledger("ACCOUNT")

    result = ledger.transfer(
        "wallet_alice_btc_001", "wallet_bob_sol_00001", "10",
        fee="0", sender_token=token,
    )
    assert "Error" in result
    assert "tasa de conversion" in result.lower() or "no hay tasa" in result.lower()


def test_exchange_cross_model_still_blocked():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-a", "A")
    ledger.create_user("u-b", "B")
    wa = ledger.create_wallet("u-a", wallet_id="wallet_user_alpha_01", currency="BTC", model="ACCOUNT")
    ledger.create_wallet("u-b", wallet_id="wallet_user_bravo_02", currency="SOL", model="UTXO")
    ledger.mint("wallet_user_alpha_01", "50")
    ledger.set_exchange_rate("BTC", "SOL", "150")

    result = ledger.transfer(
        "wallet_user_alpha_01", "wallet_user_bravo_02", "10",
        fee="0", sender_token=wa["auth_token"],
    )
    assert "Error" in result
    assert "modelos diferentes" in result.lower()


def test_exchange_rate_snapshot_roundtrip():
    ledger = MultiUserWalletLedger()
    ledger.set_exchange_rate("BTC", "SOL", "150", commission_pct="1.5")
    ledger.set_exchange_rate("ETH", "BTC", "0.05", commission_pct="0.5")

    snapshot = ledger.state_snapshot()
    assert len(snapshot["exchange_rates"]) == 2

    restored = MultiUserWalletLedger.from_snapshot(snapshot)
    assert len(restored.exchange_rates) == 2
    rate = restored.get_exchange_rate("BTC", "SOL")
    assert rate is not None
    assert rate["rate"] == "150.00000000"
    assert rate["commission_pct"] == "1.50"


def test_exchange_appears_in_transfer_history_as_type_exchange():
    ledger, token = _setup_two_currency_ledger("ACCOUNT")
    ledger.set_exchange_rate("BTC", "SOL", "150", commission_pct="1.0")

    ledger.transfer(
        "wallet_alice_btc_001", "wallet_bob_sol_00001", "5",
        fee="0", sender_token=token,
    )
    transfers = ledger.state_snapshot()["transfers"]
    exchange_tx = [t for t in transfers if t["type"] == "EXCHANGE"]
    assert len(exchange_tx) == 1
    tx = exchange_tx[0]
    assert tx["sender_currency"] == "BTC"
    assert tx["receiver_currency"] == "SOL"
    assert tx["exchange_rate"] == "150.00000000"
    assert tx["converted_amount"] == "742.50000000"


def test_exchange_utxo_model():
    ledger, token = _setup_two_currency_ledger("UTXO")
    ledger.set_exchange_rate("BTC", "SOL", "150", commission_pct="1.0")

    result = ledger.transfer(
        "wallet_alice_btc_001", "wallet_bob_sol_00001", "10",
        fee="0", sender_token=token,
    )
    assert "Transferencia" in result

    alice_balance = ledger.get_wallet_balance("wallet_alice_btc_001")
    bob_balance = ledger.get_wallet_balance("wallet_bob_sol_00001")
    assert alice_balance == Decimal("90.00000000")
    assert bob_balance == Decimal("1485.00000000")

    bob_utxos = ledger.list_utxos(wallet_id="wallet_bob_sol_00001")
    exchange_utxos = [u for u in bob_utxos if u["source"] == "EXCHANGE"]
    assert len(exchange_utxos) == 1
    assert exchange_utxos[0]["currency"] == "SOL"
    assert exchange_utxos[0]["amount"] == "1485.00000000"
