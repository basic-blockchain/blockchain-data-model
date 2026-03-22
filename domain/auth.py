"""Authentication, authorization, and role-based access control (pure domain, no framework imports)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

import bcrypt
import jwt


# ── Roles & Permissions ──────────────────────────────────


class Role(str, Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class Permission(str, Enum):
    CREATE_USER = "CREATE_USER"
    CREATE_WALLET = "CREATE_WALLET"
    TRANSFER = "TRANSFER"
    MINT = "MINT"
    SET_POLICY = "SET_POLICY"
    SET_RISK_PROFILE = "SET_RISK_PROFILE"
    ASSIGN_ROLE = "ASSIGN_ROLE"
    VIEW_USERS = "VIEW_USERS"
    VIEW_WALLETS = "VIEW_WALLETS"
    VIEW_TRANSFERS = "VIEW_TRANSFERS"
    VIEW_ALERTS = "VIEW_ALERTS"
    VIEW_POLICIES = "VIEW_POLICIES"
    VIEW_RISK_PROFILES = "VIEW_RISK_PROFILES"
    VIEW_REVISIONS = "VIEW_REVISIONS"
    EXCHANGE = "EXCHANGE"
    SET_EXCHANGE_RATE = "SET_EXCHANGE_RATE"
    TOP_UP = "TOP_UP"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"
    FREEZE_WALLET = "FREEZE_WALLET"
    UNFREEZE_WALLET = "UNFREEZE_WALLET"
    BAN_USER = "BAN_USER"
    UNBAN_USER = "UNBAN_USER"


ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN: {p.value for p in Permission},
    Role.OPERATOR: {
        Permission.CREATE_WALLET,
        Permission.TRANSFER,
        Permission.EXCHANGE,
        Permission.MINT,
        Permission.VIEW_USERS,
        Permission.VIEW_WALLETS,
        Permission.VIEW_TRANSFERS,
        Permission.VIEW_ALERTS,
        Permission.VIEW_POLICIES,
        Permission.VIEW_RISK_PROFILES,
        Permission.VIEW_REVISIONS,
    },
    Role.VIEWER: {
        Permission.CREATE_WALLET,
        Permission.TRANSFER,
        Permission.EXCHANGE,
        Permission.VIEW_USERS,
        Permission.VIEW_WALLETS,
        Permission.VIEW_TRANSFERS,
        Permission.VIEW_ALERTS,
        Permission.VIEW_POLICIES,
        Permission.VIEW_RISK_PROFILES,
        Permission.VIEW_REVISIONS,
    },
}


def has_permission(
    roles: list[str],
    permission: str,
    *,
    role_overrides: dict[str, list[str]] | None = None,
    user_permissions: dict[str, list[str]] | None = None,
    user_id: str | None = None,
) -> bool:
    if user_permissions and user_id and user_id in user_permissions:
        if permission in user_permissions[user_id]:
            return True
    for role in roles:
        if role_overrides and role in role_overrides:
            if permission in role_overrides[role]:
                return True
        else:
            role_perms = ROLE_PERMISSIONS.get(role, set())
            if permission in role_perms:
                return True
    return False


def effective_permissions(role: str, overrides: dict[str, list[str]] | None = None) -> set[str]:
    if overrides and role in overrides:
        return {p.value if hasattr(p, "value") else str(p) for p in overrides[role]}
    return {p.value if hasattr(p, "value") else str(p) for p in ROLE_PERMISSIONS.get(role, set())}


# ── Dataclasses ──────────────────────────────────────────


@dataclass
class UserCredential:
    user_id: str
    password_hash: str
    created_at: str
    updated_at: str = ""


@dataclass
class UserRoleRecord:
    user_id: str
    role: str
    granted_at: str


# ── Password hashing ────────────────────────────────────


def hash_password(plain: str, rounds: int = 12) -> str:
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Invitation & Activation tokens ──────────────────────

import secrets
import string

_ACTIVATION_ALPHABET = string.ascii_uppercase + string.digits


def generate_invitation_token() -> str:
    return secrets.token_hex(16)


def generate_activation_code() -> str:
    return "".join(secrets.choice(_ACTIVATION_ALPHABET) for _ in range(16))


# ── JWT ──────────────────────────────────────────────────


def create_jwt(user_id: str, roles: list[str], secret: str, ttl_seconds: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "roles": roles,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
