"""Tests for domain auth module: password hashing, JWT, roles, and ledger integration."""

from __future__ import annotations

import time

import pytest

from domain.auth import (
    Role,
    Permission,
    ROLE_PERMISSIONS,
    has_permission,
    hash_password,
    verify_password,
    create_jwt,
    decode_jwt,
)
from domain.multiuser_wallet_ledger import MultiUserWalletLedger


# ── Password hashing ────────────────────────────────────


def test_hash_and_verify_password():
    hashed = hash_password("secret123", rounds=4)
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_hash_produces_different_salts():
    h1 = hash_password("same", rounds=4)
    h2 = hash_password("same", rounds=4)
    assert h1 != h2
    assert verify_password("same", h1)
    assert verify_password("same", h2)


# ── JWT ──────────────────────────────────────────────────


def test_create_and_decode_jwt():
    token = create_jwt("u-alice", ["ADMIN"], "test-secret", ttl_seconds=60)
    payload = decode_jwt(token, "test-secret")
    assert payload["sub"] == "u-alice"
    assert payload["roles"] == ["ADMIN"]
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_wrong_secret_raises():
    token = create_jwt("u-alice", ["VIEWER"], "correct-secret")
    with pytest.raises(Exception):
        decode_jwt(token, "wrong-secret")


def test_jwt_expired_raises():
    token = create_jwt("u-alice", ["VIEWER"], "secret", ttl_seconds=-1)
    with pytest.raises(Exception):
        decode_jwt(token, "secret")


# ── Roles & Permissions ─────────────────────────────────


def test_admin_has_all_permissions():
    for perm in Permission:
        assert has_permission([Role.ADMIN], perm.value)


def test_operator_can_transfer_but_not_assign_roles():
    assert has_permission([Role.OPERATOR], Permission.TRANSFER)
    assert has_permission([Role.OPERATOR], Permission.MINT)
    assert has_permission([Role.OPERATOR], Permission.VIEW_WALLETS)
    assert not has_permission([Role.OPERATOR], Permission.ASSIGN_ROLE)
    assert not has_permission([Role.OPERATOR], Permission.SET_POLICY)


def test_viewer_can_only_read():
    assert has_permission([Role.VIEWER], Permission.VIEW_USERS)
    assert has_permission([Role.VIEWER], Permission.VIEW_WALLETS)
    assert not has_permission([Role.VIEWER], Permission.TRANSFER)
    assert not has_permission([Role.VIEWER], Permission.MINT)
    assert not has_permission([Role.VIEWER], Permission.CREATE_USER)


def test_multiple_roles_combine_permissions():
    assert has_permission([Role.VIEWER, Role.OPERATOR], Permission.TRANSFER)
    assert has_permission([Role.VIEWER, Role.OPERATOR], Permission.VIEW_USERS)


def test_empty_roles_has_no_permissions():
    assert not has_permission([], Permission.VIEW_USERS)


# ── Ledger integration ──────────────────────────────────


def test_create_user_with_password():
    ledger = MultiUserWalletLedger()
    result = ledger.create_user("u-alice", "Alice", password="pass123")
    assert "creado" in result
    assert "u-alice" in ledger.user_credentials
    assert ledger.user_credentials["u-alice"]["password_hash"] != "pass123"


def test_create_user_without_password():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")
    assert "u-bob" not in ledger.user_credentials
    assert ledger.user_roles.get("u-bob") == []


def test_authenticate_success_and_failure():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="secret")
    assert ledger.authenticate("u-alice", "secret") is True
    assert ledger.authenticate("u-alice", "wrong") is False
    assert ledger.authenticate("u-nobody", "secret") is False


def test_set_user_password():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    assert not ledger.authenticate("u-alice", "new-pass")
    result = ledger.set_user_password("u-alice", "new-pass")
    assert "actualizado" in result.lower()
    assert ledger.authenticate("u-alice", "new-pass")


def test_login_returns_jwt():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass")
    ledger.assign_role("u-alice", "ADMIN")
    result = ledger.login("u-alice", "pass", jwt_secret="test-secret")
    assert isinstance(result, dict)
    assert result["token_type"] == "Bearer"
    assert result["user_id"] == "u-alice"
    assert "ADMIN" in result["roles"]
    payload = decode_jwt(result["access_token"], "test-secret")
    assert payload["sub"] == "u-alice"


def test_login_invalid_credentials():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass")
    result = ledger.login("u-alice", "wrong", jwt_secret="secret")
    assert isinstance(result, str)
    assert "Error" in result


def test_assign_and_remove_role():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    assert ledger.get_user_roles("u-alice") == []

    result = ledger.assign_role("u-alice", "OPERATOR")
    assert "asignado" in result.lower()
    assert "OPERATOR" in ledger.get_user_roles("u-alice")

    result = ledger.assign_role("u-alice", "VIEWER")
    assert "VIEWER" in ledger.get_user_roles("u-alice")

    result = ledger.remove_role("u-alice", "OPERATOR")
    assert "removido" in result.lower()
    assert "OPERATOR" not in ledger.get_user_roles("u-alice")
    assert "VIEWER" in ledger.get_user_roles("u-alice")


def test_assign_invalid_role():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice")
    result = ledger.assign_role("u-alice", "SUPERUSER")
    assert "Error" in result


def test_snapshot_roundtrip_preserves_credentials_and_roles():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-alice", "Alice", password="pass123")
    ledger.assign_role("u-alice", "ADMIN")
    ledger.assign_role("u-alice", "OPERATOR")

    snapshot = ledger.state_snapshot()
    assert len(snapshot["credentials"]) == 1
    assert len(snapshot["roles"]) == 2

    restored = MultiUserWalletLedger.from_snapshot(snapshot)
    assert restored.authenticate("u-alice", "pass123")
    assert set(restored.get_user_roles("u-alice")) == {"ADMIN", "OPERATOR"}
