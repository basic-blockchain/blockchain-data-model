"""Tests for user management: update, soft delete, restore, temp password, change password."""

from decimal import Decimal

from domain.multiuser_wallet_ledger import MultiUserWalletLedger, TREASURY_USER_ID


def _setup():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass1234")
    ledger.create_user("u-bob", "Bob", password="pass5678")
    return ledger


def test_update_user_display_name():
    ledger = _setup()
    result = ledger.update_user("u-bob", new_display_name="Roberto")
    assert isinstance(result, dict)
    assert result["changes"]["display_name"] == "Roberto"
    assert ledger.users["u-bob"].display_name == "Roberto"
    assert ledger.users["u-bob"].updated_at != ""


def test_update_user_id():
    ledger = _setup()
    wa = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    result = ledger.update_user("u-bob", new_user_id="u-roberto")
    assert isinstance(result, dict)
    assert "u-roberto" in ledger.users
    assert "u-bob" not in ledger.users
    assert ledger.wallets["wallet_user_bravo_02"].user_id == "u-roberto"
    assert "wallet_user_bravo_02" in ledger.user_wallets["u-roberto"]


def test_update_user_id_conflict():
    ledger = _setup()
    result = ledger.update_user("u-bob", new_user_id="u-alice")
    assert isinstance(result, str)
    assert "Error" in result


def test_update_treasury_blocked():
    ledger = _setup()
    ledger.ensure_treasury_user()
    result = ledger.update_user(TREASURY_USER_ID, new_display_name="Hacked")
    assert isinstance(result, str)
    assert "Error" in result


def test_delete_user_soft_delete():
    ledger = _setup()
    wa = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    result = ledger.delete_user("u-bob")
    assert isinstance(result, dict)
    assert result["deleted_at"] != ""
    assert ledger.users["u-bob"].deleted_at != ""
    assert ledger.wallets["wallet_user_bravo_02"].frozen is True


def test_deleted_user_cannot_login():
    ledger = _setup()
    ledger.delete_user("u-bob")
    result = ledger.login("u-bob", "pass5678", "test-secret-key-32chars-long!!")
    assert isinstance(result, str)
    assert "eliminada" in result.lower()


def test_restore_user():
    ledger = _setup()
    wa = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    ledger.delete_user("u-bob")
    result = ledger.restore_user("u-bob", unfreeze_wallets=True)
    assert isinstance(result, dict)
    assert ledger.users["u-bob"].deleted_at == ""
    assert ledger.wallets["wallet_user_bravo_02"].frozen is False


def test_restore_user_without_unfreeze():
    ledger = _setup()
    wa = ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    ledger.delete_user("u-bob")
    result = ledger.restore_user("u-bob", unfreeze_wallets=False)
    assert ledger.users["u-bob"].deleted_at == ""
    assert ledger.wallets["wallet_user_bravo_02"].frozen is True


def test_is_user_deleted():
    ledger = _setup()
    assert ledger.is_user_deleted("u-bob") is False
    ledger.delete_user("u-bob")
    assert ledger.is_user_deleted("u-bob") is True
    ledger.restore_user("u-bob")
    assert ledger.is_user_deleted("u-bob") is False


def test_generate_temp_password():
    ledger = _setup()
    result = ledger.generate_temp_password_for_user("u-bob")
    assert isinstance(result, dict)
    assert "temp_password" in result
    assert "token_temp" in result
    assert len(result["temp_password"]) == 12
    cred = ledger.user_credentials["u-bob"]
    assert cred["password_temp"] is True
    assert cred["token_temp"] != ""


def test_login_with_temp_password_returns_must_change():
    ledger = _setup()
    result = ledger.generate_temp_password_for_user("u-bob")
    temp_pw = result["temp_password"]
    login_result = ledger.login("u-bob", temp_pw, "test-secret-key-32chars-long!!")
    assert isinstance(login_result, dict)
    assert login_result.get("must_change_password") is True


def test_change_password():
    ledger = _setup()
    result = ledger.change_password("u-bob", "pass5678", "newpass99")
    assert isinstance(result, dict)
    assert "actualizado" in result["message"].lower()
    assert ledger.authenticate("u-bob", "newpass99") is True
    assert ledger.authenticate("u-bob", "pass5678") is False


def test_change_password_wrong_current():
    ledger = _setup()
    result = ledger.change_password("u-bob", "wrongpass", "newpass99")
    assert isinstance(result, str)
    assert "Error" in result


def test_reset_password_with_token():
    ledger = _setup()
    gen_result = ledger.generate_temp_password_for_user("u-bob")
    token = gen_result["token_temp"]
    result = ledger.reset_password_with_token("u-bob", token, "restored123")
    assert isinstance(result, dict)
    assert "restablecido" in result["message"].lower()
    assert ledger.authenticate("u-bob", "restored123") is True
    cred = ledger.user_credentials["u-bob"]
    assert cred["password_temp"] is False
    assert cred["token_temp"] == ""


def test_reset_password_with_invalid_token():
    ledger = _setup()
    result = ledger.reset_password_with_token("u-bob", "invalid-token", "newpass")
    assert isinstance(result, str)
    assert "Error" in result


def test_snapshot_roundtrip_user_management():
    ledger = _setup()
    ledger.create_wallet("u-bob", wallet_id="wallet_user_bravo_02")
    ledger.delete_user("u-bob")
    ledger.generate_temp_password_for_user("u-alice")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert restored.users["u-bob"].deleted_at != ""
    assert restored.users["u-alice"].deleted_at == ""
    assert restored.user_credentials["u-alice"]["password_temp"] is True
    assert restored.user_credentials["u-alice"]["token_temp"] != ""
