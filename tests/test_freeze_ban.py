"""Tests for wallet freeze and user ban features."""

from decimal import Decimal
from unittest.mock import patch

from domain.multiuser_wallet_ledger import MultiUserWalletLedger, TREASURY_USER_ID


# ── Helpers ──────────────────────────────────────────────


def _setup_ledger():
    """Create ledger with Alice and Bob, each with an ACCOUNT wallet, Alice funded."""
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    ledger.create_user("u-bob", "Bob")
    wa = ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    wb = ledger.create_wallet("u-bob", wallet_id="wallet_bob_usdx_00001")
    ledger.mint("wallet_alice_usdx_001", "1000")
    return ledger, wa["auth_token"], wb["auth_token"]


# ── Freeze wallet tests ──────────────────────────────────


def test_freeze_wallet():
    ledger, _, _ = _setup_ledger()
    result = ledger.freeze_wallet("wallet_alice_usdx_001")
    assert isinstance(result, dict)
    assert result["frozen"] is True
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is True


def test_unfreeze_wallet():
    ledger, _, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_alice_usdx_001")
    result = ledger.unfreeze_wallet("wallet_alice_usdx_001")
    assert isinstance(result, dict)
    assert result["frozen"] is False
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is False


def test_freeze_nonexistent_wallet():
    ledger = MultiUserWalletLedger()
    result = ledger.freeze_wallet("nonexistent_wallet_id")
    assert isinstance(result, str)
    assert "Error" in result


def test_is_wallet_frozen():
    ledger, _, _ = _setup_ledger()
    assert ledger.is_wallet_frozen("wallet_alice_usdx_001") is False
    ledger.freeze_wallet("wallet_alice_usdx_001")
    assert ledger.is_wallet_frozen("wallet_alice_usdx_001") is True


def test_frozen_wallet_blocks_transfer_as_sender():
    ledger, token_a, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_alice_usdx_001")
    result = ledger.transfer(
        "wallet_alice_usdx_001", "wallet_bob_usdx_00001", "10",
        fee="0", sender_token=token_a,
    )
    assert "Error" in result
    assert "congelada" in result.lower()


def test_frozen_wallet_blocks_transfer_as_receiver():
    ledger, token_a, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_bob_usdx_00001")
    result = ledger.transfer(
        "wallet_alice_usdx_001", "wallet_bob_usdx_00001", "10",
        fee="0", sender_token=token_a,
    )
    assert "Error" in result
    assert "congelada" in result.lower()


def test_frozen_wallet_blocks_mint():
    ledger, _, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_alice_usdx_001")
    result = ledger.mint("wallet_alice_usdx_001", "100")
    assert "Error" in result
    assert "congelada" in result.lower()


def test_frozen_wallet_blocks_top_up():
    ledger, _, _ = _setup_ledger()
    ledger.ensure_treasury_user()
    tw = ledger.create_treasury_wallet()
    ledger.mint(tw["wallet_id"], "5000")
    ledger.freeze_wallet("wallet_alice_usdx_001")
    result = ledger.top_up(tw["wallet_id"], "wallet_alice_usdx_001", "100")
    assert "Error" in result
    assert "congelada" in result.lower()


# ── Ban user tests ───────────────────────────────────────


def test_ban_user_sets_banned_and_freezes_wallets():
    ledger, _, _ = _setup_ledger()
    result = ledger.ban_user("u-alice")
    assert isinstance(result, dict)
    assert result["banned"] is True
    assert "wallet_alice_usdx_001" in result["frozen_wallets"]
    assert ledger.users["u-alice"].banned is True
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is True


def test_ban_nonexistent_user_fails():
    ledger = MultiUserWalletLedger()
    result = ledger.ban_user("u-ghost")
    assert isinstance(result, str)
    assert "Error" in result


def test_ban_treasury_user_fails():
    ledger = MultiUserWalletLedger()
    ledger.ensure_treasury_user()
    result = ledger.ban_user(TREASURY_USER_ID)
    assert isinstance(result, str)
    assert "Error" in result


def test_banned_user_cannot_login():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass1234")
    ledger.assign_role("u-alice", "VIEWER")
    ledger.activate_account("u-alice", "")
    ledger.ban_user("u-alice")
    result = ledger.login("u-alice", "pass1234", "test-secret-key-32chars-long!!")
    assert isinstance(result, str)
    assert "suspendida" in result.lower()


def test_banned_user_blocks_transfer():
    ledger, token_a, _ = _setup_ledger()
    ledger.ban_user("u-alice")
    result = ledger.transfer(
        "wallet_alice_usdx_001", "wallet_bob_usdx_00001", "10",
        fee="0", sender_token=token_a,
    )
    assert "Error" in result


def test_unban_user_with_unfreeze():
    ledger, _, _ = _setup_ledger()
    ledger.ban_user("u-alice")
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is True
    result = ledger.unban_user("u-alice", unfreeze_wallets=True)
    assert isinstance(result, dict)
    assert result["banned"] is False
    assert ledger.users["u-alice"].banned is False
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is False


def test_unban_user_without_unfreeze():
    ledger, _, _ = _setup_ledger()
    ledger.ban_user("u-alice")
    result = ledger.unban_user("u-alice", unfreeze_wallets=False)
    assert isinstance(result, dict)
    assert result["banned"] is False
    assert ledger.users["u-alice"].banned is False
    assert ledger.wallets["wallet_alice_usdx_001"].frozen is True


def test_is_user_banned():
    ledger, _, _ = _setup_ledger()
    assert ledger.is_user_banned("u-alice") is False
    ledger.ban_user("u-alice")
    assert ledger.is_user_banned("u-alice") is True
    ledger.unban_user("u-alice")
    assert ledger.is_user_banned("u-alice") is False


# ── Snapshot roundtrip tests ─────────────────────────────


def test_frozen_wallet_snapshot_roundtrip():
    ledger, _, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_alice_usdx_001")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert restored.wallets["wallet_alice_usdx_001"].frozen is True
    assert restored.wallets["wallet_bob_usdx_00001"].frozen is False


def test_banned_user_snapshot_roundtrip():
    ledger, _, _ = _setup_ledger()
    ledger.ban_user("u-alice")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert restored.users["u-alice"].banned is True
    assert restored.users["u-bob"].banned is False
    assert restored.wallets["wallet_alice_usdx_001"].frozen is True


def test_list_users_includes_banned():
    ledger, _, _ = _setup_ledger()
    ledger.ban_user("u-alice")
    users = ledger.list_users()
    alice = next(u for u in users if u["user_id"] == "u-alice")
    bob = next(u for u in users if u["user_id"] == "u-bob")
    assert alice["banned"] is True
    assert bob["banned"] is False


def test_list_wallets_includes_frozen():
    ledger, _, _ = _setup_ledger()
    ledger.freeze_wallet("wallet_alice_usdx_001")
    wallets = ledger.list_wallets()
    wa = next(w for w in wallets if w["wallet_id"] == "wallet_alice_usdx_001")
    wb = next(w for w in wallets if w["wallet_id"] == "wallet_bob_usdx_00001")
    assert wa["frozen"] is True
    assert wb["frozen"] is False
