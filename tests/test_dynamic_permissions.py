"""Tests for dynamic permission management (DB-persisted overrides)."""

from domain.auth import has_permission, effective_permissions, Permission
from domain.multiuser_wallet_ledger import MultiUserWalletLedger


# ── has_permission function tests ────────────────────────


def test_has_permission_defaults_without_overrides():
    assert has_permission(["ADMIN"], Permission.MINT) is True
    assert has_permission(["VIEWER"], Permission.MINT) is False
    assert has_permission(["OPERATOR"], Permission.TRANSFER) is True


def test_has_permission_with_role_overrides():
    overrides = {"VIEWER": ["MINT", "TRANSFER", "VIEW_WALLETS"]}
    assert has_permission(["VIEWER"], "MINT", role_overrides=overrides) is True
    assert has_permission(["VIEWER"], "SET_POLICY", role_overrides=overrides) is False


def test_has_permission_with_user_permissions():
    user_perms = {"u-bob": ["SET_POLICY", "SET_RISK_PROFILE"]}
    assert has_permission(["VIEWER"], "SET_POLICY", user_permissions=user_perms, user_id="u-bob") is True
    assert has_permission(["VIEWER"], "SET_POLICY", user_permissions=user_perms, user_id="u-alice") is False


def test_user_permissions_take_priority():
    overrides = {"VIEWER": []}
    user_perms = {"u-bob": ["TRANSFER"]}
    assert has_permission(["VIEWER"], "TRANSFER", role_overrides=overrides, user_permissions=user_perms, user_id="u-bob") is True


def test_effective_permissions_default():
    perms = effective_permissions("OPERATOR")
    assert "TRANSFER" in perms
    assert "SET_POLICY" not in perms


def test_effective_permissions_with_override():
    overrides = {"OPERATOR": ["TRANSFER", "MINT", "SET_POLICY"]}
    perms = effective_permissions("OPERATOR", overrides=overrides)
    assert perms == {"TRANSFER", "MINT", "SET_POLICY"}


# ── Ledger permission CRUD tests ─────────────────────────


def test_grant_role_permission():
    ledger = MultiUserWalletLedger()
    result = ledger.grant_role_permission("VIEWER", "MINT")
    assert isinstance(result, dict)
    assert result["action"] == "granted"
    assert "MINT" in ledger.role_permission_overrides["VIEWER"]


def test_revoke_role_permission():
    ledger = MultiUserWalletLedger()
    ledger.grant_role_permission("OPERATOR", "MINT")
    result = ledger.revoke_role_permission("OPERATOR", "MINT")
    assert isinstance(result, dict)
    assert result["action"] == "revoked"
    assert "MINT" not in ledger.role_permission_overrides["OPERATOR"]


def test_grant_user_permission():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")
    result = ledger.grant_user_permission("u-bob", "SET_POLICY")
    assert isinstance(result, dict)
    assert result["action"] == "granted"
    assert "SET_POLICY" in ledger.user_permission_overrides["u-bob"]


def test_revoke_user_permission():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")
    ledger.grant_user_permission("u-bob", "SET_POLICY")
    result = ledger.revoke_user_permission("u-bob", "SET_POLICY")
    assert isinstance(result, dict)
    assert result["action"] == "revoked"
    assert "SET_POLICY" not in ledger.user_permission_overrides["u-bob"]


def test_grant_user_permission_nonexistent_user():
    ledger = MultiUserWalletLedger()
    result = ledger.grant_user_permission("u-ghost", "MINT")
    assert isinstance(result, str)
    assert "Error" in result


def test_reset_role_permissions():
    ledger = MultiUserWalletLedger()
    ledger.grant_role_permission("OPERATOR", "SET_POLICY")
    assert "OPERATOR" in ledger.role_permission_overrides
    result = ledger.reset_role_permissions("OPERATOR")
    assert "reseteados" in result.lower()
    assert "OPERATOR" not in ledger.role_permission_overrides


def test_list_role_permissions_default():
    ledger = MultiUserWalletLedger()
    result = ledger.list_role_permissions("OPERATOR")
    assert result["source"] == "default"
    assert "TRANSFER" in result["permissions"]


def test_list_role_permissions_override():
    ledger = MultiUserWalletLedger()
    ledger.grant_role_permission("OPERATOR", "SET_POLICY")
    result = ledger.list_role_permissions("OPERATOR")
    assert result["source"] == "override"
    assert "SET_POLICY" in result["permissions"]


def test_list_user_permissions():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")
    ledger.grant_user_permission("u-bob", "MINT")
    ledger.grant_user_permission("u-bob", "SET_POLICY")
    result = ledger.list_user_permissions("u-bob")
    assert sorted(result["permissions"]) == ["MINT", "SET_POLICY"]


def test_cannot_revoke_manage_permissions_from_admin():
    ledger = MultiUserWalletLedger()
    result = ledger.revoke_role_permission("ADMIN", "MANAGE_PERMISSIONS")
    assert isinstance(result, str)
    assert "Error" in result


def test_invalid_role_rejected():
    ledger = MultiUserWalletLedger()
    result = ledger.grant_role_permission("SUPERADMIN", "MINT")
    assert isinstance(result, str)
    assert "Error" in result


def test_invalid_permission_rejected():
    ledger = MultiUserWalletLedger()
    result = ledger.grant_role_permission("ADMIN", "FLY_TO_MOON")
    assert isinstance(result, str)
    assert "Error" in result


def test_permission_overrides_snapshot_roundtrip():
    ledger = MultiUserWalletLedger()
    ledger.create_user("u-bob", "Bob")
    ledger.grant_role_permission("OPERATOR", "SET_POLICY")
    ledger.grant_user_permission("u-bob", "MINT")

    snapshot = ledger.state_snapshot()
    restored = MultiUserWalletLedger.from_snapshot(snapshot)

    assert "OPERATOR" in restored.role_permission_overrides
    assert "SET_POLICY" in restored.role_permission_overrides["OPERATOR"]
    assert "u-bob" in restored.user_permission_overrides
    assert "MINT" in restored.user_permission_overrides["u-bob"]
