"""Tests for audit log traceability across all ledger operations."""

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def _setup():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass1234")
    ledger.create_user("u-bob", "Bob", password="pass5678")
    return ledger


def test_audit_user_created():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    entries = [e for e in ledger.audit_log if e["action"] == "USER_CREATED"]
    assert len(entries) == 1
    assert entries[0]["target_id"] == "u-alice"


def test_audit_login_success():
    ledger = _setup()
    ledger.login("u-alice", "pass1234", "test-secret-key-32chars-long!!")
    entries = [e for e in ledger.audit_log if e["action"] == "LOGIN_SUCCESS"]
    assert len(entries) == 1
    assert entries[0]["actor_id"] == "u-alice"


def test_audit_login_failed():
    ledger = _setup()
    ledger.login("u-alice", "wrongpass", "test-secret-key-32chars-long!!")
    entries = [e for e in ledger.audit_log if e["action"] == "LOGIN_FAILED"]
    assert len(entries) == 1
    assert entries[0]["actor_id"] == "u-alice"


def test_audit_login_banned():
    ledger = _setup()
    ledger.ban_user("u-bob")
    ledger.login("u-bob", "pass5678", "test-secret-key-32chars-long!!")
    entries = [e for e in ledger.audit_log if e["action"] == "LOGIN_BANNED"]
    assert len(entries) == 1


def test_audit_transfer():
    ledger = _setup()
    wa = ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    ledger.create_wallet("u-bob", wallet_id="wallet_bob_usdx_00001")
    ledger.mint("wallet_alice_usdx_001", "1000")
    ledger.transfer(
        "wallet_alice_usdx_001", "wallet_bob_usdx_00001", "100",
        fee="0", sender_token=wa["auth_token"],
    )
    entries = [e for e in ledger.audit_log if e["action"] == "TRANSFER"]
    assert len(entries) == 1
    assert entries[0]["details"]["receiver"] == "wallet_bob_usdx_00001"


def test_audit_mint():
    ledger = _setup()
    ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    ledger.mint("wallet_alice_usdx_001", "500")
    entries = [e for e in ledger.audit_log if e["action"] == "MINT"]
    assert len(entries) == 1
    assert entries[0]["details"]["amount"] == "500.00000000"


def test_audit_ban_user():
    ledger = _setup()
    ledger.ban_user("u-bob")
    entries = [e for e in ledger.audit_log if e["action"] == "USER_BANNED"]
    assert len(entries) == 1
    assert entries[0]["target_id"] == "u-bob"


def test_audit_freeze_wallet():
    ledger = _setup()
    ledger.create_wallet("u-bob", wallet_id="wallet_bob_usdx_00001")
    ledger.freeze_wallet("wallet_bob_usdx_00001")
    entries = [e for e in ledger.audit_log if e["action"] == "WALLET_FROZEN"]
    assert len(entries) == 1
    assert entries[0]["target_id"] == "wallet_bob_usdx_00001"


def test_audit_role_assigned():
    ledger = _setup()
    ledger.assign_role("u-bob", "OPERATOR")
    entries = [e for e in ledger.audit_log if e["action"] == "ROLE_ASSIGNED"]
    assert len(entries) == 1
    assert entries[0]["details"]["role"] == "OPERATOR"


def test_audit_password_changed():
    ledger = _setup()
    ledger.change_password("u-bob", "pass5678", "newpass99")
    entries = [e for e in ledger.audit_log if e["action"] == "PASSWORD_CHANGED"]
    assert len(entries) == 1
    assert entries[0]["actor_id"] == "u-bob"


def test_audit_user_updated():
    ledger = _setup()
    ledger.update_user("u-bob", new_display_name="Roberto")
    entries = [e for e in ledger.audit_log if e["action"] == "USER_UPDATED"]
    assert len(entries) == 1


def test_audit_user_deleted():
    ledger = _setup()
    ledger.delete_user("u-bob")
    entries = [e for e in ledger.audit_log if e["action"] == "USER_DELETED"]
    assert len(entries) == 1


def test_audit_permission_granted():
    ledger = _setup()
    ledger.grant_role_permission("OPERATOR", "SET_POLICY")
    entries = [e for e in ledger.audit_log if e["action"] == "PERMISSION_GRANTED"]
    assert len(entries) == 1
    assert entries[0]["details"]["permission"] == "SET_POLICY"


def test_list_audit_log_filter_by_action():
    ledger = _setup()
    ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    ledger.mint("wallet_alice_usdx_001", "100")
    result = ledger.list_audit_log(action="MINT")
    assert all(e["action"] == "MINT" for e in result)
    assert len(result) >= 1


def test_list_audit_log_filter_by_user():
    ledger = _setup()
    ledger.ban_user("u-bob")
    result = ledger.list_audit_log(user_id="u-bob")
    assert all(e["actor_id"] == "u-bob" or e["target_id"] == "u-bob" for e in result)


def test_audit_log_snapshot_roundtrip():
    ledger = _setup()
    ledger.create_wallet("u-alice", wallet_id="wallet_alice_usdx_001")
    ledger.mint("wallet_alice_usdx_001", "100")
    ledger.ban_user("u-bob")

    original_count = len(ledger.audit_log)
    assert original_count > 0

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert len(restored.audit_log) == original_count
    assert restored.audit_log[0]["log_id"] == ledger.audit_log[0]["log_id"]
