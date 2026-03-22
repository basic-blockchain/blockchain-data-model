"""Tests for self-registration, activation codes, and admin invitations."""

from __future__ import annotations

import pytest

from domain.multiuser_wallet_ledger import MultiUserWalletLedger
from domain.auth import decode_jwt

JWT_SECRET = "test-secret-key-for-jwt-minimum-32-chars!!"


def _make_admin_ledger():
    ledger = MultiUserWalletLedger()
    ledger.create_user("admin1", "Admin One", password="admin123")
    ledger.assign_role("admin1", "ADMIN")
    return ledger


# ── Registration ─────────────────────────────────────────


def test_register_operator_generates_activation_code():
    ledger = _make_admin_ledger()
    result = ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    assert isinstance(result, dict)
    assert "activation_code" in result
    assert "op1" in ledger.activation_codes
    assert ledger.activation_codes["op1"]["activated"] is False


def test_register_viewer_generates_activation_code():
    ledger = _make_admin_ledger()
    result = ledger.create_user("v1", "V1", password="pass", role="VIEWER")
    assert isinstance(result, dict)
    assert "activation_code" in result
    assert "v1" in ledger.activation_codes
    assert ledger.activation_codes["v1"]["activated"] is False


def test_register_admin_requires_invitation_token():
    ledger = _make_admin_ledger()
    result = ledger.create_user("admin2", "Admin2", password="pass", role="ADMIN")
    assert isinstance(result, str)
    assert "invitacion" in result.lower() or "token" in result.lower()


def test_register_admin_with_valid_invitation():
    ledger = _make_admin_ledger()
    inv = ledger.generate_admin_invitation("admin1")
    token = inv["token"]
    result = ledger.create_user("admin2", "Admin2", password="pass", role="ADMIN", invitation_token=token)
    assert isinstance(result, dict)
    assert result["role"] == "ADMIN"
    # Invitation token should now be marked as used
    used_tokens = [t for t in ledger.admin_invitation_tokens if t["token"] == token]
    assert len(used_tokens) == 1
    assert used_tokens[0]["used"] is True


def test_register_admin_with_used_invitation_fails():
    ledger = _make_admin_ledger()
    inv = ledger.generate_admin_invitation("admin1")
    token = inv["token"]
    ledger.create_user("admin2", "Admin2", password="pass", role="ADMIN", invitation_token=token)
    result = ledger.create_user("admin3", "Admin3", password="pass", role="ADMIN", invitation_token=token)
    assert isinstance(result, str)
    assert "Error" in result


# ── Login with activation codes ──────────────────────────


def test_login_unactivated_account_without_code_fails():
    ledger = _make_admin_ledger()
    ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    result = ledger.login("op1", "pass", jwt_secret=JWT_SECRET)
    assert isinstance(result, str)
    assert "activaci" in result.lower() or "activacion" in result.lower()


def test_login_unactivated_account_with_correct_code():
    ledger = _make_admin_ledger()
    reg = ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    code = reg["activation_code"]
    result = ledger.login("op1", "pass", jwt_secret=JWT_SECRET, activation_code=code)
    assert isinstance(result, dict)
    assert "access_token" in result


def test_login_unactivated_account_with_wrong_code():
    ledger = _make_admin_ledger()
    ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    result = ledger.login("op1", "pass", jwt_secret=JWT_SECRET, activation_code="WRONG-CODE")
    assert isinstance(result, str)
    assert "Error" in result


def test_login_activated_account_no_code_needed():
    ledger = _make_admin_ledger()
    reg = ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    code = reg["activation_code"]
    ledger.activate_account("op1", code)
    result = ledger.login("op1", "pass", jwt_secret=JWT_SECRET)
    assert isinstance(result, dict)
    assert "access_token" in result


# ── Activation ───────────────────────────────────────────


def test_activate_account():
    ledger = _make_admin_ledger()
    reg = ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")
    code = reg["activation_code"]
    ledger.activate_account("op1", code)
    assert ledger.is_account_activated("op1") is True


# ── Snapshot roundtrip ───────────────────────────────────


def test_snapshot_roundtrip_preserves_invitations_and_activations():
    ledger = _make_admin_ledger()
    inv = ledger.generate_admin_invitation("admin1")
    reg = ledger.create_user("op1", "Op1", password="pass", role="OPERATOR")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert len(restored.admin_invitation_tokens) == len(ledger.admin_invitation_tokens)
    assert restored.admin_invitation_tokens[0]["token"] == inv["token"]
    assert "op1" in restored.activation_codes
    assert restored.activation_codes["op1"]["code"] == reg["activation_code"]
    assert restored.activation_codes["op1"]["activated"] is False


# ── Admin invitation generation ──────────────────────────


def test_generate_admin_invitation():
    ledger = _make_admin_ledger()
    result = ledger.generate_admin_invitation("admin1")
    assert isinstance(result, dict)
    assert "token" in result
    assert len(ledger.admin_invitation_tokens) == 1
