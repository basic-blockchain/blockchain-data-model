"""Tests for user profile fields (first_name, last_name, email, username)."""

from domain.multiuser_wallet_ledger import MultiUserWalletLedger


def test_create_user_with_profile_fields():
    ledger = MultiUserWalletLedger()
    result = ledger.create_user(
        "u-alice", "Alice", password="pass1234",
        first_name="Alice", last_name="Smith", email="alice@example.com", username="alicesmith",
    )
    user = ledger.users["u-alice"]
    assert user.first_name == "Alice"
    assert user.last_name == "Smith"
    assert user.email == "alice@example.com"
    assert user.username == "alicesmith"


def test_create_user_username_defaults_to_display_name():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob Builder", password="pass1234")
    assert ledger.users["u-bob"].username == "Bob Builder"


def test_update_profile():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass1234")
    result = ledger.update_profile("u-alice", first_name="Alicia", email="alicia@mail.com")
    assert isinstance(result, dict)
    assert result["changes"]["first_name"] == "Alicia"
    assert result["changes"]["email"] == "alicia@mail.com"
    assert ledger.users["u-alice"].first_name == "Alicia"
    assert ledger.users["u-alice"].email == "alicia@mail.com"


def test_update_profile_no_changes():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    result = ledger.update_profile("u-alice")
    assert isinstance(result, str)
    assert "Error" in result


def test_update_profile_nonexistent_user():
    ledger = MultiUserWalletLedger()
    result = ledger.update_profile("u-ghost", first_name="Ghost")
    assert isinstance(result, str)
    assert "Error" in result


def test_list_users_includes_profile_fields():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", first_name="Alice", last_name="Smith", email="a@b.com")
    users = ledger.list_users()
    alice = users[0]
    assert alice["first_name"] == "Alice"
    assert alice["last_name"] == "Smith"
    assert alice["email"] == "a@b.com"
    assert alice["username"] == "Alice"


def test_profile_snapshot_roundtrip():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", first_name="Alice", last_name="Smith", email="a@b.com", username="asmith")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    user = restored.users["u-alice"]
    assert user.first_name == "Alice"
    assert user.last_name == "Smith"
    assert user.email == "a@b.com"
    assert user.username == "asmith"


def test_audit_update_profile():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    ledger.update_profile("u-alice", first_name="Alicia")
    entries = [e for e in ledger.audit_log if e["action"] == "USER_UPDATED" and "profile_changes" in e.get("details", {})]
    assert len(entries) == 1
    assert entries[0]["details"]["profile_changes"]["first_name"] == "Alicia"
