"""Tests for corporate treasury wallet and top-up feature."""

from decimal import Decimal

from domain.multiuser_wallet_ledger import MultiUserWalletLedger, TREASURY_USER_ID


def _setup_treasury_ledger(model="ACCOUNT", currency="USDX"):
    """Create ledger with treasury wallet (funded) and a target user wallet."""
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    ledger.ensure_treasury_user()
    tw = ledger.create_treasury_wallet(currency=currency, model=model)
    uw = ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001", currency=currency, model=model)
    ledger.mint(tw["wallet_id"], "10000")
    return ledger, tw["wallet_id"], uw["wallet_id"]


def test_ensure_treasury_user_creates_system_user():
    ledger = MultiUserWalletLedger()
    result = ledger.ensure_treasury_user()
    assert TREASURY_USER_ID in result
    assert TREASURY_USER_ID in ledger.users
    assert ledger.user_roles.get(TREASURY_USER_ID) == []


def test_ensure_treasury_user_idempotent():
    ledger = MultiUserWalletLedger()
    ledger.ensure_treasury_user()
    result = ledger.ensure_treasury_user()
    assert "ya existe" in result


def test_create_treasury_wallet():
    ledger = MultiUserWalletLedger()
    result = ledger.create_treasury_wallet(currency="BTC", model="ACCOUNT")
    assert isinstance(result, dict)
    assert result["user_id"] == TREASURY_USER_ID
    assert result["currency"] == "BTC"
    assert result["model"] == "ACCOUNT"


def test_list_treasury_wallets():
    ledger = MultiUserWalletLedger()
    ledger.create_treasury_wallet(currency="BTC")
    ledger.create_treasury_wallet(currency="SOL")
    wallets = ledger.list_treasury_wallets()
    assert len(wallets) == 2
    assert all(w["user_id"] == TREASURY_USER_ID for w in wallets)


def test_top_up_account_model():
    ledger, tw_id, uw_id = _setup_treasury_ledger("ACCOUNT")
    result = ledger.top_up(tw_id, uw_id, "500", reference="RECARGA")
    assert "Top-up" in result
    assert ledger.get_wallet_balance(tw_id) == Decimal("9500.00000000")
    assert ledger.get_wallet_balance(uw_id) == Decimal("500.00000000")


def test_top_up_utxo_model():
    ledger, tw_id, uw_id = _setup_treasury_ledger("UTXO")
    result = ledger.top_up(tw_id, uw_id, "200")
    assert "Top-up" in result
    assert ledger.get_wallet_balance(tw_id) == Decimal("9800.00000000")
    assert ledger.get_wallet_balance(uw_id) == Decimal("200.00000000")
    target_utxos = [u for u in ledger.list_utxos(wallet_id=uw_id) if u["source"] == "TOP_UP"]
    assert len(target_utxos) == 1


def test_top_up_insufficient_funds():
    ledger, tw_id, uw_id = _setup_treasury_ledger("ACCOUNT")
    result = ledger.top_up(tw_id, uw_id, "99999")
    assert "Error" in result
    assert "fondos insuficientes" in result.lower()


def test_top_up_invalid_treasury_wallet():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    uw = ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    ledger.create_user("u-bob", "Bob")
    bw = ledger.create_wallet("u-bob", wallet_id="wallet_bob_usdx_00001")
    ledger.mint("wallet_alice_usdx_001", "1000")
    result = ledger.top_up("wallet_alice_usdx_001", "wallet_bob_usdx_00001", "100")
    assert "Error" in result
    assert "tesoreria" in result.lower()


def test_top_up_nonexistent_target_wallet():
    ledger = MultiUserWalletLedger()
    tw = ledger.create_treasury_wallet()
    ledger.mint(tw["wallet_id"], "1000")
    result = ledger.top_up(tw["wallet_id"], "nonexistent_wallet_id", "100")
    assert "Error" in result
    assert "no existe" in result.lower()


def test_top_up_transfer_type_is_top_up():
    ledger, tw_id, uw_id = _setup_treasury_ledger("ACCOUNT")
    ledger.top_up(tw_id, uw_id, "100")
    transfers = ledger.state_snapshot()["transfers"]
    top_up_txs = [t for t in transfers if t["type"] == "TOP_UP"]
    assert len(top_up_txs) == 1
    assert top_up_txs[0]["sender_wallet"] == tw_id
    assert top_up_txs[0]["receiver_wallet"] == uw_id


def test_block_external_create_user_treasury_id():
    ledger = MultiUserWalletLedger()
    result = ledger.create_user(TREASURY_USER_ID, "Hacker")
    assert isinstance(result, str)
    assert "Error" in result
    assert "reservado" in result.lower()


def test_treasury_snapshot_roundtrip():
    ledger, tw_id, uw_id = _setup_treasury_ledger("ACCOUNT")
    ledger.top_up(tw_id, uw_id, "300")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert TREASURY_USER_ID in restored.users
    assert restored.get_wallet_balance(tw_id) == Decimal("9700.00000000")
    assert restored.get_wallet_balance(uw_id) == Decimal("300.00000000")
    top_up_txs = [t for t in restored.transfers if t["type"] == "TOP_UP"]
    assert len(top_up_txs) == 1
