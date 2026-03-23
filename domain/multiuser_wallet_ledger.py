from __future__ import annotations

import secrets
import re
import string
import time
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from domain.precision import UNIT, normalize_amount  # re-exported for terminal
from domain.utxo_operations import (
    select_utxos as _select_utxos,
    sum_utxos as _sum_utxos,
    consumed_utxo_ids as _consumed_utxo_ids,
    remove_consumed_utxos as _remove_consumed_utxos,
)

TOKEN_ALPHABET = string.ascii_letters + string.digits
TREASURY_USER_ID = "__TREASURY__"


@dataclass
class UserRecord:
    user_id: str
    display_name: str
    created_at: str
    banned: bool = False
    updated_at: str = ""
    deleted_at: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    username: str = ""


@dataclass
class WalletRecord:
    wallet_id: str
    user_id: str
    model: str
    currency: str
    balance: Decimal
    auth_token: str
    token_issued_at: int
    created_at: str
    frozen: bool = False


@dataclass
class UserPolicyRecord:
    user_id: str
    can_transfer: bool
    daily_limit: Decimal | None
    updated_at: str


@dataclass
class UserRiskProfileRecord:
    user_id: str
    profile_name: str
    daily_limit: Decimal | None
    transfer_alert_threshold: Decimal | None
    daily_alert_threshold: Decimal | None
    updated_at: str


class MultiUserWalletLedger:
    TOKEN_TTL_SECONDS = 300  # 5 minutes for wallet transfer tokens

    def __init__(self):
        self.users: dict[str, UserRecord] = {}
        self.wallets: dict[str, WalletRecord] = {}
        self.utxos: dict[str, list[dict]] = {}
        self.user_wallets: dict[str, list[str]] = {}
        self.user_policies: dict[str, UserPolicyRecord] = {}
        self.user_risk_profiles: dict[str, UserRiskProfileRecord] = {}
        self.wallet_nonces: dict[str, int] = {}
        self.transfers: list[dict] = []
        self.alerts: list[dict] = []
        self.user_credentials: dict[str, dict] = {}
        self.user_roles: dict[str, list[str]] = {}
        self.admin_invitation_tokens: list[dict] = []
        self.activation_codes: dict[str, dict] = {}
        self.exchange_rates: dict[str, dict] = {}
        self.role_permission_overrides: dict[str, list[str]] = {}
        self.audit_log: list[dict] = []
        self._user_seq: int = 0
        self.user_permission_overrides: dict[str, list[str]] = {}

    RISK_PROFILE_DEFAULTS: dict[str, dict[str, str | None]] = {
        "STANDARD": {
            "daily_limit": None,
            "transfer_alert_threshold": None,
            "daily_alert_threshold": None,
        },
        "LOW": {
            "daily_limit": "25000",
            "transfer_alert_threshold": "10000",
            "daily_alert_threshold": "20000",
        },
        "MEDIUM": {
            "daily_limit": "10000",
            "transfer_alert_threshold": "5000",
            "daily_alert_threshold": "8000",
        },
        "HIGH": {
            "daily_limit": "5000",
            "transfer_alert_threshold": "2000",
            "daily_alert_threshold": "4000",
        },
        "RESTRICTED": {
            "daily_limit": "1000",
            "transfer_alert_threshold": "300",
            "daily_alert_threshold": "800",
        },
    }

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _build_wallet_id() -> str:
        return f"wlt-{secrets.token_hex(10)}"

    @staticmethod
    def _now_epoch() -> int:
        return int(time.time())

    @staticmethod
    def _build_wallet_token(length: int = 12) -> str:
        return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))

    @staticmethod
    def _is_valid_wallet_id(value: str) -> bool:
        return re.fullmatch(r"[A-Za-z0-9_-]{20,30}", value) is not None

    @staticmethod
    def _normalize_model(model: str) -> str:
        normalized = str(model or "ACCOUNT").strip().upper()
        if normalized not in {"ACCOUNT", "UTXO"}:
            return ""
        return normalized

    @staticmethod
    def _build_utxo_id() -> str:
        return f"utxo-{secrets.token_hex(10)}"

    def _new_user_policy(self, user_id: str) -> UserPolicyRecord:
        return UserPolicyRecord(
            user_id=user_id,
            can_transfer=True,
            daily_limit=None,
            updated_at=self._timestamp(),
        )

    def _new_user_risk_profile(self, user_id: str) -> UserRiskProfileRecord:
        return UserRiskProfileRecord(
            user_id=user_id,
            profile_name="STANDARD",
            daily_limit=None,
            transfer_alert_threshold=None,
            daily_alert_threshold=None,
            updated_at=self._timestamp(),
        )

    def _rotate_wallet_token(self, wallet: WalletRecord, now: int | None = None) -> None:
        issue_time = self._now_epoch() if now is None else int(now)
        wallet.auth_token = self._build_wallet_token(12)
        wallet.token_issued_at = issue_time

    def _token_payload(self, wallet: WalletRecord) -> dict:
        return {
            "auth_token": wallet.auth_token,
            "token_issued_at": wallet.token_issued_at,
            "token_expires_at": wallet.token_issued_at + self.TOKEN_TTL_SECONDS,
        }

    def _token_is_expired(self, wallet: WalletRecord, now: int | None = None) -> bool:
        check_time = self._now_epoch() if now is None else int(now)
        return check_time - int(wallet.token_issued_at) >= self.TOKEN_TTL_SECONDS

    def _refresh_wallet_token_if_expired(self, wallet: WalletRecord) -> None:
        now = self._now_epoch()
        if self._token_is_expired(wallet, now=now):
            self._rotate_wallet_token(wallet, now=now)

    def refresh_wallet_token(self, user_id: str, wallet_id: str, current_token: str = "") -> str | dict:
        resolved = self.resolve_user_id(user_id)
        if resolved:
            user_id = resolved
        if user_id not in self.users:
            return f"Error: el usuario {user_id} no existe."
        if wallet_id not in self.wallets:
            return f"Error: wallet {wallet_id} no existe."

        wallet = self.wallets[wallet_id]
        if wallet.user_id != user_id:
            return "Error: el usuario no es propietario de la wallet."

        now = self._now_epoch()
        provided_token = current_token.strip()
        previous_matches = bool(provided_token and provided_token == wallet.auth_token)
        previous_expired = self._token_is_expired(wallet, now=now)

        self._rotate_wallet_token(wallet, now=now)

        return {
            "message": f"Token renovado para wallet {wallet_id}.",
            "wallet_id": wallet_id,
            "user_id": user_id,
            **self._token_payload(wallet),
            "previous_token_matches": previous_matches,
            "previous_token_expired": previous_expired,
        }

    @staticmethod
    def _build_transfer_id() -> str:
        return f"tx-{secrets.token_hex(8)}"

    @staticmethod
    def _build_alert_id() -> str:
        return f"alt-{secrets.token_hex(8)}"

    @classmethod
    def _risk_defaults_for(cls, profile_name: str) -> dict[str, str | None]:
        return cls.RISK_PROFILE_DEFAULTS.get(profile_name.upper(), cls.RISK_PROFILE_DEFAULTS["STANDARD"])

    @staticmethod
    def _min_limit(*limits: Decimal | None) -> Decimal | None:
        values = [value for value in limits if value is not None]
        if not values:
            return None
        return min(values)

    def _audit(self, actor_id: str, action: str, target_type: str, target_id: str, details: dict | None = None) -> None:
        self.audit_log.append({
            "log_id": f"aud-{secrets.token_hex(8)}",
            "timestamp": self._timestamp(),
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details or {},
        })

    def list_audit_log(self, limit: int = 50, user_id: str = "", action: str = "") -> list[dict]:
        filtered = self.audit_log
        if user_id:
            filtered = [e for e in filtered if e["actor_id"] == user_id or e["target_id"] == user_id]
        if action:
            filtered = [e for e in filtered if e["action"] == action.upper()]
        return filtered[-limit:]

    def is_empty(self) -> bool:
        return len(self.users) == 0

    def _next_user_id(self) -> str:
        self._user_seq += 1
        return f"USR-{self._user_seq:05d}"

    def resolve_user_id(self, identifier: str) -> str | None:
        if identifier in self.users:
            return identifier
        for user in self.users.values():
            if user.username and user.username == identifier:
                return user.user_id
        return None

    def create_user(self, user_id: str = "", display_name: str = "", password: str = "", role: str = "", invitation_token: str = "", first_name: str = "", last_name: str = "", email: str = "", username: str = "") -> dict | str:
        if not display_name:
            return "Error: display_name es requerido."
        if not user_id:
            user_id = self._next_user_id()
        if user_id == TREASURY_USER_ID:
            return "Error: el identificador __TREASURY__ esta reservado para el sistema."
        if user_id in self.users:
            return f"Aviso: el usuario {user_id} ya existe."

        from domain.auth import Role, hash_password, generate_activation_code

        role = role.upper() if role else ""
        valid_roles = {r.value for r in Role}

        if role == "ADMIN":
            if not invitation_token:
                return "Error: se requiere un token de invitacion para crear usuario ADMIN."
            if not self.validate_admin_invitation(invitation_token):
                return "Error: token de invitacion invalido o ya utilizado."

        if role and role not in valid_roles:
            return f"Error: role invalido. Opciones: {', '.join(sorted(valid_roles))}."

        self.users[user_id] = UserRecord(
            user_id=user_id,
            display_name=display_name,
            created_at=self._timestamp(),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email.strip(),
            username=(username.strip() if username.strip() else display_name.strip()),
        )
        self.user_wallets[user_id] = []
        self.user_policies[user_id] = self._new_user_policy(user_id)
        self.user_risk_profiles[user_id] = self._new_user_risk_profile(user_id)
        self.user_roles[user_id] = [role] if role else []

        if password:
            now = self._timestamp()
            self.user_credentials[user_id] = {
                "user_id": user_id,
                "password_hash": hash_password(password),
                "created_at": now,
                "updated_at": now,
                "password_temp": False,
                "token_temp": "",
            }

        if not role:
            self._audit("SYSTEM", "USER_CREATED", "USER", user_id, {"role": ""})
            return f"Usuario {user_id} creado."

        result: dict = {"message": f"Usuario {user_id} creado.", "user_id": user_id, "role": role}
        self._audit("SYSTEM", "USER_CREATED", "USER", user_id, {"role": role})

        if role in ("OPERATOR", "VIEWER"):
            code = generate_activation_code()
            self.activation_codes[user_id] = {
                "user_id": user_id,
                "code": code,
                "activated": False,
                "created_at": self._timestamp(),
            }
            result["activation_code"] = code
            result["activation_notice"] = "Guarda este codigo. Lo necesitaras en tu primer inicio de sesion."

        if role == "ADMIN":
            result["activation_notice"] = "Cuenta ADMIN creada. Inicia sesion con tu password."

        return result

    def generate_admin_invitation(self, created_by_user_id: str) -> dict | str:
        if created_by_user_id not in self.users:
            return f"Error: usuario {created_by_user_id} no existe."
        from domain.auth import generate_invitation_token
        token = generate_invitation_token()
        self.admin_invitation_tokens.append({
            "token": token,
            "created_by": created_by_user_id,
            "created_at": self._timestamp(),
            "used": False,
            "used_by": "",
        })
        return {"token": token, "created_by": created_by_user_id}

    def validate_admin_invitation(self, token: str) -> bool:
        for inv in self.admin_invitation_tokens:
            if inv["token"] == token and not inv["used"]:
                inv["used"] = True
                return True
        return False

    def is_account_activated(self, user_id: str) -> bool:
        ac = self.activation_codes.get(user_id)
        if ac is None:
            return True
        return bool(ac.get("activated", False))

    def activate_account(self, user_id: str, code: str) -> str:
        ac = self.activation_codes.get(user_id)
        if ac is None:
            return "Error: usuario no tiene codigo de activacion pendiente."
        if ac["activated"]:
            return "Aviso: cuenta ya activada."
        if ac["code"] != code:
            return "Error: codigo de activacion incorrecto."
        ac["activated"] = True
        return f"Cuenta {user_id} activada exitosamente."

    def set_user_password(self, user_id: str, password: str) -> str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if not password:
            return "Error: password es requerido."
        from domain.auth import hash_password
        now = self._timestamp()
        self.user_credentials[user_id] = {
            "user_id": user_id,
            "password_hash": hash_password(password),
            "created_at": self.user_credentials.get(user_id, {}).get("created_at", now),
            "updated_at": now,
        }
        return f"Password actualizado para {user_id}."

    def authenticate(self, user_id: str, password: str) -> bool:
        cred = self.user_credentials.get(user_id)
        if not cred:
            return False
        from domain.auth import verify_password
        return verify_password(password, cred["password_hash"])

    def login(self, user_id: str, password: str, jwt_secret: str, jwt_ttl: int = 3600, activation_code: str = "") -> dict | str:
        resolved = self.resolve_user_id(user_id)
        if resolved:
            user_id = resolved
        if not self.authenticate(user_id, password):
            self._audit(user_id, "LOGIN_FAILED", "USER", user_id)
            return "Error: credenciales invalidas."
        if self.is_user_deleted(user_id):
            return "Error: cuenta eliminada. Contacta a soporte tecnico."
        if self.is_user_banned(user_id):
            self._audit(user_id, "LOGIN_BANNED", "USER", user_id)
            return "Error: cuenta suspendida. Contacta a soporte tecnico o servicio al cliente."
        if not self.is_account_activated(user_id):
            if not activation_code:
                return "Error: cuenta no activada. Se requiere codigo de activacion para el primer inicio de sesion."
            activate_result = self.activate_account(user_id, activation_code)
            if activate_result.startswith("Error"):
                return activate_result
        from domain.auth import create_jwt
        roles = self.user_roles.get(user_id, [])
        token = create_jwt(user_id, roles, jwt_secret, jwt_ttl)
        cred = self.user_credentials.get(user_id, {})
        must_change = bool(cred.get("password_temp", False))
        result = {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": jwt_ttl,
            "user_id": user_id,
            "roles": roles,
        }
        if must_change:
            result["must_change_password"] = True
        self._audit(user_id, "LOGIN_SUCCESS", "USER", user_id)
        return result

    def assign_role(self, user_id: str, role: str) -> str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        from domain.auth import Role
        valid_roles = {r.value for r in Role}
        role = role.upper()
        if role not in valid_roles:
            return f"Error: role invalido. Opciones: {', '.join(sorted(valid_roles))}."
        roles = self.user_roles.setdefault(user_id, [])
        if role in roles:
            return f"Aviso: {user_id} ya tiene el role {role}."
        roles.append(role)
        self._audit("SYSTEM", "ROLE_ASSIGNED", "USER", user_id, {"role": role})
        return f"Role {role} asignado a {user_id}."

    def remove_role(self, user_id: str, role: str) -> str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        role = role.upper()
        roles = self.user_roles.get(user_id, [])
        if role not in roles:
            return f"Error: {user_id} no tiene el role {role}."
        roles.remove(role)
        self._audit("SYSTEM", "ROLE_REMOVED", "USER", user_id, {"role": role})
        return f"Role {role} removido de {user_id}."

    def get_user_roles(self, user_id: str) -> list[str]:
        return list(self.user_roles.get(user_id, []))

    def set_user_policy(
        self,
        user_id: str,
        can_transfer: bool | None = None,
        daily_limit: Decimal | int | float | str | None = None,
    ) -> str:
        if user_id not in self.users:
            return f"Error: el usuario {user_id} no existe."

        policy = self.user_policies.get(
            user_id,
            UserPolicyRecord(
                user_id=user_id,
                can_transfer=True,
                daily_limit=None,
                updated_at=self._timestamp(),
            ),
        )

        if can_transfer is not None:
            policy.can_transfer = bool(can_transfer)

        if daily_limit is not None:
            limit_value = normalize_amount(daily_limit)
            if limit_value <= 0:
                return "Error: daily_limit debe ser mayor a cero cuando se define."
            policy.daily_limit = limit_value

        policy.updated_at = self._timestamp()
        self.user_policies[user_id] = policy
        return f"Política de usuario {user_id} actualizada."

    def get_user_policy(self, user_id: str) -> dict:
        policy = self.user_policies.get(user_id)
        if policy is None:
            default = self._new_user_policy(user_id)
            return {
                "user_id": user_id,
                "can_transfer": default.can_transfer,
                "daily_limit": None,
                "updated_at": default.updated_at,
            }
        return {
            "user_id": policy.user_id,
            "can_transfer": policy.can_transfer,
            "daily_limit": str(policy.daily_limit) if policy.daily_limit is not None else None,
            "updated_at": policy.updated_at,
        }

    def list_user_policies(self) -> list[dict]:
        return [self.get_user_policy(user_id) for user_id in self.users.keys()]

    def set_user_risk_profile(
        self,
        user_id: str,
        profile_name: str | None = None,
        daily_limit: Decimal | int | float | str | None = None,
        transfer_alert_threshold: Decimal | int | float | str | None = None,
        daily_alert_threshold: Decimal | int | float | str | None = None,
    ) -> str:
        if user_id not in self.users:
            return f"Error: el usuario {user_id} no existe."

        current = self.user_risk_profiles.get(
            user_id,
            UserRiskProfileRecord(
                user_id=user_id,
                profile_name="STANDARD",
                daily_limit=None,
                transfer_alert_threshold=None,
                daily_alert_threshold=None,
                updated_at=self._timestamp(),
            ),
        )

        resolved_profile_name = current.profile_name
        if profile_name is not None and str(profile_name).strip():
            resolved_profile_name = str(profile_name).strip().upper()

        defaults = self._risk_defaults_for(resolved_profile_name)
        if profile_name is not None and str(profile_name).strip():
            current.profile_name = resolved_profile_name
            current.daily_limit = (
                normalize_amount(defaults["daily_limit"]) if defaults["daily_limit"] is not None else None
            )
            current.transfer_alert_threshold = (
                normalize_amount(defaults["transfer_alert_threshold"])
                if defaults["transfer_alert_threshold"] is not None
                else None
            )
            current.daily_alert_threshold = (
                normalize_amount(defaults["daily_alert_threshold"])
                if defaults["daily_alert_threshold"] is not None
                else None
            )

        if daily_limit is not None:
            limit_value = normalize_amount(daily_limit)
            if limit_value <= 0:
                return "Error: daily_limit debe ser mayor a cero cuando se define."
            current.daily_limit = limit_value

        if transfer_alert_threshold is not None:
            single_threshold = normalize_amount(transfer_alert_threshold)
            if single_threshold <= 0:
                return "Error: transfer_alert_threshold debe ser mayor a cero cuando se define."
            current.transfer_alert_threshold = single_threshold

        if daily_alert_threshold is not None:
            daily_threshold = normalize_amount(daily_alert_threshold)
            if daily_threshold <= 0:
                return "Error: daily_alert_threshold debe ser mayor a cero cuando se define."
            current.daily_alert_threshold = daily_threshold

        current.updated_at = self._timestamp()
        self.user_risk_profiles[user_id] = current
        return f"Perfil de riesgo de usuario {user_id} actualizado."

    def get_user_risk_profile(self, user_id: str) -> dict:
        profile = self.user_risk_profiles.get(user_id)
        if profile is None:
            default = self._new_user_risk_profile(user_id)
            return {
                "user_id": user_id,
                "profile_name": default.profile_name,
                "daily_limit": None,
                "transfer_alert_threshold": None,
                "daily_alert_threshold": None,
                "updated_at": default.updated_at,
            }
        return {
            "user_id": profile.user_id,
            "profile_name": profile.profile_name,
            "daily_limit": str(profile.daily_limit) if profile.daily_limit is not None else None,
            "transfer_alert_threshold": (
                str(profile.transfer_alert_threshold) if profile.transfer_alert_threshold is not None else None
            ),
            "daily_alert_threshold": str(profile.daily_alert_threshold) if profile.daily_alert_threshold is not None else None,
            "updated_at": profile.updated_at,
        }

    def list_user_risk_profiles(self) -> list[dict]:
        return [self.get_user_risk_profile(user_id) for user_id in self.users.keys()]

    def list_alerts(self, limit: int = 50, user_id: str = "", severity: str = "") -> list[dict]:
        selected = self.alerts
        if user_id:
            selected = [alert for alert in selected if alert.get("user_id") == user_id]
        if severity:
            normalized = severity.strip().upper()
            selected = [alert for alert in selected if str(alert.get("severity", "")).upper() == normalized]

        if limit > 0:
            selected = selected[-limit:]
        return list(reversed(selected))

    def _register_alert(
        self,
        user_id: str,
        profile_name: str,
        alert_type: str,
        threshold: Decimal,
        observed: Decimal,
        transfer_id: str,
    ) -> None:
        ratio = observed / threshold if threshold > 0 else Decimal("0")
        severity = "HIGH" if ratio >= Decimal("1.5") else "MEDIUM"
        self.alerts.append(
            {
                "alert_id": self._build_alert_id(),
                "user_id": user_id,
                "profile_name": profile_name,
                "type": alert_type,
                "severity": severity,
                "threshold": str(threshold),
                "observed": str(observed),
                "transfer_id": transfer_id,
                "created_at": self._timestamp(),
            }
        )

    def _daily_transfer_total(self, user_id: str, day_prefix: str) -> Decimal:
        wallet_ids = set(self.user_wallets.get(user_id, []))
        total = Decimal("0")
        for transfer in self.transfers:
            if transfer.get("type") != "TRANSFER":
                continue
            if transfer.get("sender_wallet") not in wallet_ids:
                continue
            created_at = str(transfer.get("created_at", ""))
            if not created_at.startswith(day_prefix):
                continue
            total += normalize_amount(transfer.get("amount", "0"))
        return total

    @staticmethod
    def _build_transfer_hash(
        *,
        transfer_id: str,
        model: str,
        sender_wallet: str,
        receiver_wallet: str,
        amount: Decimal,
        fee: Decimal,
        reference: str,
        nonce: int,
        created_at: str,
        previous_hash: str,
    ) -> str:
        payload = (
            f"{transfer_id}|{model}|{sender_wallet}|{receiver_wallet}|"
            f"{amount.normalize()}|{fee.normalize()}|{reference}|"
            f"{nonce}|{created_at}|{previous_hash}"
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def _sum_wallet_utxos(self, wallet_id: str, currency: str) -> Decimal:
        return _sum_utxos(self.utxos.get(wallet_id, []), currency)

    def _sync_wallet_balance(self, wallet_id: str) -> None:
        wallet = self.wallets.get(wallet_id)
        if wallet is None:
            return
        if wallet.model == "UTXO":
            wallet.balance = self._sum_wallet_utxos(wallet_id, wallet.currency)

    def _last_transfer_hash(self) -> str:
        for transfer in reversed(self.transfers):
            if transfer.get("type") != "TRANSFER":
                continue
            tx_hash = str(transfer.get("tx_hash", "")).strip()
            if tx_hash:
                return tx_hash
        return "GENESIS"

    def current_wallet_nonce(self, wallet_id: str) -> int:
        return int(self.wallet_nonces.get(wallet_id, 0))

    def verify_transfer_integrity(self) -> dict:
        previous_hash = "GENESIS"
        nonce_tracker: dict[str, int] = {}
        checked = 0

        for transfer in self.transfers:
            if transfer.get("type") != "TRANSFER":
                continue

            sender_wallet = str(transfer.get("sender_wallet", ""))
            receiver_wallet = str(transfer.get("receiver_wallet", ""))
            transfer_id = str(transfer.get("transfer_id", ""))
            model = str(transfer.get("model", "ACCOUNT")).upper()
            reference = str(transfer.get("reference", ""))
            created_at = str(transfer.get("created_at", ""))
            nonce = int(str(transfer.get("nonce", "-1")))
            current_previous_hash = str(transfer.get("previous_hash", ""))
            current_tx_hash = str(transfer.get("tx_hash", ""))
            amount = normalize_amount(transfer.get("amount", "0"))
            fee = normalize_amount(transfer.get("fee", "0"))

            expected_nonce = nonce_tracker.get(sender_wallet, 0) + 1
            if nonce != expected_nonce:
                return {
                    "valid": False,
                    "checked_transfers": checked,
                    "reason": (
                        f"Nonce inválido en {transfer_id}. "
                        f"Esperado={expected_nonce}, Recibido={nonce}."
                    ),
                }

            if current_previous_hash != previous_hash:
                return {
                    "valid": False,
                    "checked_transfers": checked,
                    "reason": (
                        f"Hash previo inválido en {transfer_id}. "
                        f"Esperado={previous_hash}, Recibido={current_previous_hash}."
                    ),
                }

            expected_hash = self._build_transfer_hash(
                transfer_id=transfer_id,
                model=model,
                sender_wallet=sender_wallet,
                receiver_wallet=receiver_wallet,
                amount=amount,
                fee=fee,
                reference=reference,
                nonce=nonce,
                created_at=created_at,
                previous_hash=current_previous_hash,
            )
            if current_tx_hash != expected_hash:
                return {
                    "valid": False,
                    "checked_transfers": checked,
                    "reason": (
                        f"Hash de transferencia inválido en {transfer_id}. "
                        f"Esperado={expected_hash}, Recibido={current_tx_hash}."
                    ),
                }

            nonce_tracker[sender_wallet] = nonce
            previous_hash = current_tx_hash
            checked += 1

        return {
            "valid": True,
            "checked_transfers": checked,
            "reason": "Integridad verificada correctamente.",
        }

    def create_wallet(
        self,
        user_id: str,
        wallet_id: str = "",
        currency: str = "USDX",
        model: str = "ACCOUNT",
    ) -> str | dict:
        if user_id not in self.users:
            return f"Error: el usuario {user_id} no existe."

        wallet_model = self._normalize_model(model)
        if not wallet_model:
            return "Error: model inválido. Usa ACCOUNT o UTXO."

        final_wallet_id = wallet_id.strip() or self._build_wallet_id()
        if not self._is_valid_wallet_id(final_wallet_id):
            return "Wallet invalida. Usa 20-30 caracteres: letras, numeros, '-' o '_'."
        if final_wallet_id in self.wallets:
            return f"Error: wallet {final_wallet_id} ya existe."

        wallet = WalletRecord(
            wallet_id=final_wallet_id,
            user_id=user_id,
            model=wallet_model,
            currency=currency,
            balance=Decimal("0"),
            auth_token=self._build_wallet_token(12),
            token_issued_at=self._now_epoch(),
            created_at=self._timestamp(),
        )
        self.wallets[final_wallet_id] = wallet
        self.utxos[final_wallet_id] = []
        self.user_wallets[user_id].append(final_wallet_id)
        self._audit(user_id, "WALLET_CREATED", "WALLET", final_wallet_id, {"model": wallet_model, "currency": currency})
        return {
            "message": f"Wallet {final_wallet_id} creada para {user_id}.",
            "wallet_id": final_wallet_id,
            "user_id": user_id,
            "model": wallet_model,
            "currency": currency,
            **self._token_payload(wallet),
        }

    def mint(self, wallet_id: str, amount: Decimal | int | float | str, reference: str = "MINT") -> str:
        minted = normalize_amount(amount)
        if minted <= 0:
            return "Error: amount debe ser mayor a cero."
        if wallet_id not in self.wallets:
            return f"Error: wallet {wallet_id} no existe."
        if self.wallets[wallet_id].frozen:
            return f"Error: wallet {wallet_id} esta congelada. No se puede realizar mint."

        wallet = self.wallets[wallet_id]
        self._refresh_wallet_token_if_expired(wallet)
        if wallet.model == "ACCOUNT":
            wallet.balance += minted
        else:
            self.utxos.setdefault(wallet_id, []).append(
                {
                    "utxo_id": self._build_utxo_id(),
                    "wallet_id": wallet_id,
                    "currency": wallet.currency,
                    "amount": str(minted),
                    "source": "MINT",
                    "created_at": self._timestamp(),
                }
            )
            self._sync_wallet_balance(wallet_id)
        self.transfers.append(
            {
                "transfer_id": self._build_transfer_id(),
                "type": "MINT",
                "sender_wallet": "TREASURY",
                "receiver_wallet": wallet_id,
                "amount": str(minted),
                "fee": "0.00000000",
                "reference": reference,
                "status": "SETTLED",
                "created_at": self._timestamp(),
            }
        )
        self._audit("SYSTEM", "MINT", "WALLET", wallet_id, {"amount": str(minted)})
        return f"Mint {minted} aplicado a {wallet_id}."

    # ── Treasury (corporate wallet) ────────────────────────

    def ensure_treasury_user(self) -> str:
        if TREASURY_USER_ID in self.users:
            return f"Usuario {TREASURY_USER_ID} ya existe."
        self.users[TREASURY_USER_ID] = UserRecord(
            user_id=TREASURY_USER_ID,
            display_name="Tesoreria Corporativa",
            created_at=self._timestamp(),
        )
        self.user_wallets[TREASURY_USER_ID] = []
        self.user_roles[TREASURY_USER_ID] = []
        return f"Usuario {TREASURY_USER_ID} creado."

    def create_treasury_wallet(self, currency: str = "USDX", model: str = "ACCOUNT") -> dict | str:
        self.ensure_treasury_user()
        return self.create_wallet(TREASURY_USER_ID, currency=currency, model=model)

    def list_treasury_wallets(self) -> list[dict]:
        return self.list_wallets(user_id=TREASURY_USER_ID)

    def top_up(self, treasury_wallet_id: str, target_wallet_id: str, amount: str | Decimal, reference: str = "TOP_UP") -> str:
        top_amount = normalize_amount(amount)
        if top_amount <= 0:
            return "Error: amount debe ser mayor a cero."
        if treasury_wallet_id not in self.wallets:
            return f"Error: wallet de tesoreria {treasury_wallet_id} no existe."
        if target_wallet_id not in self.wallets:
            return f"Error: wallet destino {target_wallet_id} no existe."
        if treasury_wallet_id == target_wallet_id:
            return "Error: wallet de tesoreria y destino deben ser distintas."

        treasury = self.wallets[treasury_wallet_id]
        target = self.wallets[target_wallet_id]

        if treasury.user_id != TREASURY_USER_ID:
            return f"Error: wallet {treasury_wallet_id} no pertenece a tesoreria."
        if treasury.model != target.model:
            return f"Error: no se puede recargar entre modelos diferentes ({treasury.model} -> {target.model})."
        if target.frozen:
            return f"Error: wallet destino {target_wallet_id} esta congelada. No se puede recargar."

        is_cross_currency = treasury.currency != target.currency
        exchange_metadata = {}
        credit_amount = top_amount

        if is_cross_currency:
            rate_info = self.get_exchange_rate(treasury.currency, target.currency)
            if not rate_info:
                return f"Error: no hay tasa de conversion configurada para {treasury.currency} -> {target.currency}."
            from domain.exchange import convert_amount as _convert
            rate_decimal = normalize_amount(rate_info["rate"])
            comm_decimal = Decimal(str(rate_info["commission_pct"]))
            conversion = _convert(top_amount, rate_decimal, comm_decimal)
            credit_amount = normalize_amount(conversion["net_amount"])
            exchange_metadata = {
                "sender_currency": treasury.currency,
                "receiver_currency": target.currency,
                "exchange_rate": conversion["rate"],
                "exchange_commission": conversion["commission"],
                "converted_amount": conversion["net_amount"],
            }

        if treasury.model == "ACCOUNT":
            if treasury.balance < top_amount:
                return f"Error: fondos insuficientes en tesoreria. Disponible={treasury.balance}, Requerido={top_amount}."
            treasury.balance -= top_amount
            target.balance += credit_amount
        else:
            selected, selected_total = _select_utxos(
                self.utxos.get(treasury_wallet_id, []), treasury.currency, top_amount,
            )
            if selected_total < top_amount:
                available = self._sum_wallet_utxos(treasury_wallet_id, treasury.currency)
                return f"Error: fondos insuficientes en tesoreria. Disponible={available}, Requerido={top_amount}."
            self.utxos[treasury_wallet_id] = _remove_consumed_utxos(
                self.utxos.get(treasury_wallet_id, []), _consumed_utxo_ids(selected),
            )
            self.utxos.setdefault(target_wallet_id, []).append({
                "utxo_id": self._build_utxo_id(),
                "wallet_id": target_wallet_id,
                "currency": target.currency,
                "amount": str(credit_amount),
                "source": "TOP_UP",
                "created_at": self._timestamp(),
            })
            change = selected_total - top_amount
            if change > 0:
                self.utxos.setdefault(treasury_wallet_id, []).append({
                    "utxo_id": self._build_utxo_id(),
                    "wallet_id": treasury_wallet_id,
                    "currency": treasury.currency,
                    "amount": str(change),
                    "source": "CHANGE",
                    "created_at": self._timestamp(),
                })
            self._sync_wallet_balance(treasury_wallet_id)
            self._sync_wallet_balance(target_wallet_id)

        transfer_record = {
            "transfer_id": self._build_transfer_id(),
            "type": "TOP_UP",
            "sender_wallet": treasury_wallet_id,
            "receiver_wallet": target_wallet_id,
            "amount": str(top_amount),
            "fee": "0.00000000",
            "reference": reference,
            "status": "SETTLED",
            "created_at": self._timestamp(),
        }
        transfer_record.update(exchange_metadata)
        self.transfers.append(transfer_record)
        self._audit("SYSTEM", "TOP_UP", "WALLET", target_wallet_id, {"treasury": treasury_wallet_id, "amount": str(top_amount)})
        return f"Top-up {top_amount} de {treasury_wallet_id} a {target_wallet_id} aplicado."

    # ── Exchange rate management ──────────────────────────

    def set_exchange_rate(self, from_currency: str, to_currency: str, rate: str | Decimal, commission_pct: str | Decimal = "1.0") -> dict | str:
        from domain.exchange import pair_key
        from_c = from_currency.upper().strip()
        to_c = to_currency.upper().strip()
        if not from_c or not to_c:
            return "Error: from_currency y to_currency son requeridos."
        if from_c == to_c:
            return "Error: las monedas deben ser diferentes."
        rate_val = normalize_amount(rate)
        comm_val = Decimal(str(commission_pct)).quantize(Decimal("0.01"))
        if rate_val <= 0:
            return "Error: rate debe ser mayor a cero."
        if comm_val < 0:
            return "Error: commission_pct no puede ser negativa."
        key = pair_key(from_c, to_c)
        self.exchange_rates[key] = {
            "pair_id": key,
            "from_currency": from_c,
            "to_currency": to_c,
            "rate": str(rate_val),
            "commission_pct": str(comm_val),
            "updated_at": self._timestamp(),
        }
        return {"pair_id": key, "from_currency": from_c, "to_currency": to_c, "rate": str(rate_val), "commission_pct": str(comm_val)}

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> dict | None:
        from domain.exchange import pair_key
        return self.exchange_rates.get(pair_key(from_currency.upper(), to_currency.upper()))

    def list_exchange_rates(self) -> list[dict]:
        return list(self.exchange_rates.values())

    # ── Dynamic permission management ────────────────────

    def _valid_permission(self, permission: str) -> bool:
        from domain.auth import Permission
        return permission in {p.value for p in Permission}

    def _valid_role(self, role: str) -> bool:
        from domain.auth import Role
        return role in {r.value for r in Role}

    def grant_role_permission(self, role: str, permission: str) -> dict | str:
        role = role.upper()
        permission = permission.upper()
        if not self._valid_role(role):
            return f"Error: rol invalido: {role}."
        if not self._valid_permission(permission):
            return f"Error: permiso invalido: {permission}."
        from domain.auth import ROLE_PERMISSIONS
        if role not in self.role_permission_overrides:
            self.role_permission_overrides[role] = [str(p) for p in ROLE_PERMISSIONS.get(role, set())]
        if permission not in self.role_permission_overrides[role]:
            self.role_permission_overrides[role].append(permission)
        self._audit("SYSTEM", "PERMISSION_GRANTED", "ROLE", role, {"permission": permission})
        return {"role": role, "permission": permission, "action": "granted"}

    def revoke_role_permission(self, role: str, permission: str) -> dict | str:
        role = role.upper()
        permission = permission.upper()
        if not self._valid_role(role):
            return f"Error: rol invalido: {role}."
        if not self._valid_permission(permission):
            return f"Error: permiso invalido: {permission}."
        if role == "ADMIN" and permission == "MANAGE_PERMISSIONS":
            return "Error: no se puede revocar MANAGE_PERMISSIONS del rol ADMIN."
        from domain.auth import ROLE_PERMISSIONS
        if role not in self.role_permission_overrides:
            self.role_permission_overrides[role] = [str(p) for p in ROLE_PERMISSIONS.get(role, set())]
        if permission in self.role_permission_overrides[role]:
            self.role_permission_overrides[role].remove(permission)
        self._audit("SYSTEM", "PERMISSION_REVOKED", "ROLE", role, {"permission": permission})
        return {"role": role, "permission": permission, "action": "revoked"}

    def grant_user_permission(self, user_id: str, permission: str) -> dict | str:
        permission = permission.upper()
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if not self._valid_permission(permission):
            return f"Error: permiso invalido: {permission}."
        self.user_permission_overrides.setdefault(user_id, [])
        if permission not in self.user_permission_overrides[user_id]:
            self.user_permission_overrides[user_id].append(permission)
        return {"user_id": user_id, "permission": permission, "action": "granted"}

    def revoke_user_permission(self, user_id: str, permission: str) -> dict | str:
        permission = permission.upper()
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if not self._valid_permission(permission):
            return f"Error: permiso invalido: {permission}."
        if user_id in self.user_permission_overrides and permission in self.user_permission_overrides[user_id]:
            self.user_permission_overrides[user_id].remove(permission)
        return {"user_id": user_id, "permission": permission, "action": "revoked"}

    def reset_role_permissions(self, role: str) -> str:
        role = role.upper()
        if not self._valid_role(role):
            return f"Error: rol invalido: {role}."
        self.role_permission_overrides.pop(role, None)
        return f"Permisos del rol {role} reseteados a defaults."

    def list_role_permissions(self, role: str) -> dict:
        role = role.upper()
        from domain.auth import effective_permissions
        perms = effective_permissions(role, overrides=self.role_permission_overrides)
        has_override = role in self.role_permission_overrides
        return {"role": role, "permissions": sorted(perms), "source": "override" if has_override else "default"}

    def list_user_permissions(self, user_id: str) -> dict:
        perms = self.user_permission_overrides.get(user_id, [])
        return {"user_id": user_id, "permissions": sorted(perms)}

    # ── Freeze wallet / Ban user ────────────────────────

    def freeze_wallet(self, wallet_id: str) -> dict | str:
        if wallet_id not in self.wallets:
            return f"Error: wallet {wallet_id} no existe."
        self.wallets[wallet_id].frozen = True
        self._audit("SYSTEM", "WALLET_FROZEN", "WALLET", wallet_id)
        return {"wallet_id": wallet_id, "frozen": True, "message": f"Wallet {wallet_id} congelada."}

    def unfreeze_wallet(self, wallet_id: str) -> dict | str:
        if wallet_id not in self.wallets:
            return f"Error: wallet {wallet_id} no existe."
        self.wallets[wallet_id].frozen = False
        self._audit("SYSTEM", "WALLET_UNFROZEN", "WALLET", wallet_id)
        return {"wallet_id": wallet_id, "frozen": False, "message": f"Wallet {wallet_id} descongelada."}

    def is_wallet_frozen(self, wallet_id: str) -> bool:
        wallet = self.wallets.get(wallet_id)
        return wallet.frozen if wallet else False

    def ban_user(self, user_id: str) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if user_id == TREASURY_USER_ID:
            return "Error: no se puede banear al usuario de tesoreria."
        self.users[user_id].banned = True
        frozen_wallets = []
        for wid in self.user_wallets.get(user_id, []):
            self.wallets[wid].frozen = True
            frozen_wallets.append(wid)
        self._audit("SYSTEM", "USER_BANNED", "USER", user_id, {"frozen_wallets": frozen_wallets})
        return {"user_id": user_id, "banned": True, "frozen_wallets": frozen_wallets, "message": f"Usuario {user_id} baneado. {len(frozen_wallets)} wallet(s) congelada(s)."}

    def unban_user(self, user_id: str, unfreeze_wallets: bool = True) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        self.users[user_id].banned = False
        unfrozen_wallets = []
        if unfreeze_wallets:
            for wid in self.user_wallets.get(user_id, []):
                self.wallets[wid].frozen = False
                unfrozen_wallets.append(wid)
        self._audit("SYSTEM", "USER_UNBANNED", "USER", user_id, {"unfrozen_wallets": unfrozen_wallets})
        return {"user_id": user_id, "banned": False, "unfrozen_wallets": unfrozen_wallets, "message": f"Usuario {user_id} desbaneado. {len(unfrozen_wallets)} wallet(s) descongelada(s)."}

    def is_user_banned(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        return user.banned if user else False

    def is_user_deleted(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        return bool(user.deleted_at) if user else False

    # ── User management (ADMIN) ──────────────────────────

    def update_user(self, user_id: str, new_user_id: str | None = None, new_display_name: str | None = None) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if user_id == TREASURY_USER_ID:
            return "Error: no se puede modificar al usuario de tesoreria."
        user = self.users[user_id]
        changes = {}
        if new_display_name and new_display_name != user.display_name:
            user.display_name = new_display_name
            changes["display_name"] = new_display_name
        if new_user_id and new_user_id != user_id:
            if new_user_id in self.users:
                return f"Error: el user_id {new_user_id} ya esta en uso."
            if new_user_id == TREASURY_USER_ID:
                return "Error: el identificador __TREASURY__ esta reservado."
            user.user_id = new_user_id
            self.users[new_user_id] = self.users.pop(user_id)
            self.user_wallets[new_user_id] = self.user_wallets.pop(user_id, [])
            if user_id in self.user_policies:
                self.user_policies[new_user_id] = self.user_policies.pop(user_id)
                self.user_policies[new_user_id].user_id = new_user_id
            if user_id in self.user_risk_profiles:
                self.user_risk_profiles[new_user_id] = self.user_risk_profiles.pop(user_id)
                self.user_risk_profiles[new_user_id].user_id = new_user_id
            if user_id in self.user_roles:
                self.user_roles[new_user_id] = self.user_roles.pop(user_id)
            if user_id in self.user_credentials:
                cred = self.user_credentials.pop(user_id)
                cred["user_id"] = new_user_id
                self.user_credentials[new_user_id] = cred
            if user_id in self.activation_codes:
                ac = self.activation_codes.pop(user_id)
                ac["user_id"] = new_user_id
                self.activation_codes[new_user_id] = ac
            if user_id in self.user_permission_overrides:
                self.user_permission_overrides[new_user_id] = self.user_permission_overrides.pop(user_id)
            for wid in self.user_wallets.get(new_user_id, []):
                if wid in self.wallets:
                    self.wallets[wid].user_id = new_user_id
            changes["user_id"] = {"old": user_id, "new": new_user_id}
        if not changes:
            return "Error: no se especificaron cambios."
        user.updated_at = self._timestamp()
        self._audit("SYSTEM", "USER_UPDATED", "USER", user.user_id, changes)
        return {"user_id": user.user_id, "changes": changes, "message": f"Usuario actualizado."}

    def update_profile(self, user_id: str, first_name: str | None = None, last_name: str | None = None, email: str | None = None, username: str | None = None) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        user = self.users[user_id]
        changes = {}
        if first_name is not None and first_name != user.first_name:
            user.first_name = first_name.strip()
            changes["first_name"] = user.first_name
        if last_name is not None and last_name != user.last_name:
            user.last_name = last_name.strip()
            changes["last_name"] = user.last_name
        if email is not None and email != user.email:
            user.email = email.strip()
            changes["email"] = user.email
        if username is not None and username != user.username:
            user.username = username.strip()
            changes["username"] = user.username
        if not changes:
            return "Error: no se especificaron cambios."
        user.updated_at = self._timestamp()
        self._audit("SYSTEM", "USER_UPDATED", "USER", user_id, {"profile_changes": changes})
        return {"user_id": user_id, "changes": changes, "message": "Perfil actualizado."}

    def delete_user(self, user_id: str) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        if user_id == TREASURY_USER_ID:
            return "Error: no se puede eliminar al usuario de tesoreria."
        user = self.users[user_id]
        if user.deleted_at:
            return f"Error: usuario {user_id} ya esta eliminado."
        user.deleted_at = self._timestamp()
        user.updated_at = self._timestamp()
        frozen_wallets = []
        for wid in self.user_wallets.get(user_id, []):
            self.wallets[wid].frozen = True
            frozen_wallets.append(wid)
        self._audit("SYSTEM", "USER_DELETED", "USER", user_id)
        return {"user_id": user_id, "deleted_at": user.deleted_at, "frozen_wallets": frozen_wallets, "message": f"Usuario {user_id} eliminado (soft delete)."}

    def restore_user(self, user_id: str, unfreeze_wallets: bool = True) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        user = self.users[user_id]
        if not user.deleted_at:
            return f"Error: usuario {user_id} no esta eliminado."
        user.deleted_at = ""
        user.updated_at = self._timestamp()
        unfrozen = []
        if unfreeze_wallets:
            for wid in self.user_wallets.get(user_id, []):
                self.wallets[wid].frozen = False
                unfrozen.append(wid)
        self._audit("SYSTEM", "USER_RESTORED", "USER", user_id)
        return {"user_id": user_id, "unfrozen_wallets": unfrozen, "message": f"Usuario {user_id} restaurado."}

    # ── Password management ──────────────────────────────

    def generate_temp_password_for_user(self, user_id: str) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        cred = self.user_credentials.get(user_id)
        if not cred:
            return f"Error: usuario {user_id} no tiene credenciales."
        from domain.auth import generate_temp_password, generate_temp_token, hash_password
        temp_pass = generate_temp_password()
        temp_token = generate_temp_token()
        cred["password_hash"] = hash_password(temp_pass)
        cred["password_temp"] = True
        cred["token_temp"] = temp_token
        cred["updated_at"] = self._timestamp()
        self._audit("SYSTEM", "PASSWORD_TEMP_GENERATED", "USER", user_id)
        return {"user_id": user_id, "temp_password": temp_pass, "token_temp": temp_token, "message": f"Password temporal generado para {user_id}. Entregar al usuario."}

    def change_password(self, user_id: str, current_password: str, new_password: str) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        cred = self.user_credentials.get(user_id)
        if not cred:
            return f"Error: usuario {user_id} no tiene credenciales."
        from domain.auth import verify_password, hash_password
        if not verify_password(current_password, cred["password_hash"]):
            return "Error: password actual incorrecto."
        if len(new_password) < 4:
            return "Error: el nuevo password debe tener al menos 4 caracteres."
        cred["password_hash"] = hash_password(new_password)
        cred["password_temp"] = False
        cred["token_temp"] = ""
        cred["updated_at"] = self._timestamp()
        self._audit(user_id, "PASSWORD_CHANGED", "USER", user_id)
        return {"user_id": user_id, "message": "Password actualizado exitosamente."}

    def reset_password_with_token(self, user_id: str, token_temp: str, new_password: str) -> dict | str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        cred = self.user_credentials.get(user_id)
        if not cred:
            return f"Error: usuario {user_id} no tiene credenciales."
        stored_token = cred.get("token_temp", "")
        if not stored_token or stored_token != token_temp:
            return "Error: token temporal invalido o ya utilizado."
        if len(new_password) < 4:
            return "Error: el nuevo password debe tener al menos 4 caracteres."
        from domain.auth import hash_password
        cred["password_hash"] = hash_password(new_password)
        cred["password_temp"] = False
        cred["token_temp"] = ""
        cred["updated_at"] = self._timestamp()
        self._audit(user_id, "PASSWORD_CHANGED", "USER", user_id, {"method": "token_temp"})
        return {"user_id": user_id, "message": "Password restablecido exitosamente con token temporal."}

    # ── Transfer ─────────────────────────────────────────

    def transfer(
        self,
        sender_wallet: str,
        receiver_wallet: str,
        amount: Decimal | int | float | str,
        fee: Decimal | int | float | str = 0,
        reference: str = "",
        sender_token: str = "",
        expected_nonce: int | None = None,
    ) -> str:
        transfer_amount = normalize_amount(amount)
        tx_fee = normalize_amount(fee)

        if sender_wallet == receiver_wallet:
            return "Error: sender_wallet y receiver_wallet deben ser distintos."
        if sender_wallet not in self.wallets or receiver_wallet not in self.wallets:
            return "Error: wallet emisor o receptor inexistente."
        if transfer_amount <= 0:
            return "Error: amount debe ser mayor a cero."
        if tx_fee < 0:
            return "Error: fee no puede ser negativa."

        sender = self.wallets[sender_wallet]
        receiver = self.wallets[receiver_wallet]
        if sender.frozen:
            return f"Error: wallet emisor {sender_wallet} esta congelada. No se puede transferir."
        if receiver.frozen:
            return f"Error: wallet receptor {receiver_wallet} esta congelada. No se puede recibir transferencias."
        if self.is_user_banned(sender.user_id):
            return f"Error: usuario {sender.user_id} esta suspendido. No se puede transferir."
        self._refresh_wallet_token_if_expired(receiver)
        if sender.model != receiver.model:
            return f"Error: no se puede transferir entre modelos diferentes ({sender.model} -> {receiver.model})."
        is_cross_currency = sender.currency != receiver.currency
        if is_cross_currency:
            rate_info = self.get_exchange_rate(sender.currency, receiver.currency)
            if not rate_info:
                return f"Error: no hay tasa de conversion configurada para {sender.currency} -> {receiver.currency}. Un ADMIN debe configurar la tasa primero."

        if not sender_token.strip():
            return "Error: sender_token es requerido para transferir."

        now = self._now_epoch()
        if self._token_is_expired(sender, now=now):
            self._rotate_wallet_token(sender, now=now)
            return "Error: token expirado para wallet emisor. Solicita refresh-token."

        if sender_token.strip() != sender.auth_token:
            return "Error: token inválido para wallet emisor."

        next_nonce = self.current_wallet_nonce(sender_wallet) + 1
        if expected_nonce is not None and int(expected_nonce) != next_nonce:
            return (
                "Error: nonce inválido para wallet emisor. "
                f"Esperado={next_nonce}, Recibido={expected_nonce}."
            )

        sender_policy = self.user_policies.get(sender.user_id, self._new_user_policy(sender.user_id))
        if not sender_policy.can_transfer:
            return "Error: política de usuario impide transferencias para este emisor."

        sender_risk_profile = self.user_risk_profiles.get(
            sender.user_id,
            self._new_user_risk_profile(sender.user_id),
        )

        day_prefix = self._timestamp()[:10]
        day_total = self._daily_transfer_total(sender.user_id, day_prefix)
        projected_total = day_total + transfer_amount

        effective_daily_limit = self._min_limit(sender_policy.daily_limit, sender_risk_profile.daily_limit)
        if effective_daily_limit is not None and projected_total > effective_daily_limit:
            return (
                "Error: límite diario excedido. "
                f"Actual={day_total}, Intento={transfer_amount}, Límite={effective_daily_limit}."
            )

        exchange_metadata = {}
        credit_amount = transfer_amount
        if is_cross_currency:
            from domain.exchange import convert_amount as _convert
            rate_decimal = normalize_amount(rate_info["rate"])
            comm_decimal = Decimal(str(rate_info["commission_pct"]))
            conversion = _convert(transfer_amount, rate_decimal, comm_decimal)
            credit_amount = normalize_amount(conversion["net_amount"])
            exchange_metadata = {
                "sender_currency": sender.currency,
                "receiver_currency": receiver.currency,
                "exchange_rate": conversion["rate"],
                "exchange_commission": conversion["commission"],
                "converted_amount": conversion["net_amount"],
            }

        total_cost = transfer_amount + tx_fee
        if sender.model == "ACCOUNT":
            if sender.balance < total_cost:
                return (
                    f"Error: fondos insuficientes. Disponible={sender.balance}, "
                    f"Requerido={total_cost}."
                )
            sender.balance -= total_cost
            receiver.balance += credit_amount
        else:
            selected, selected_total = _select_utxos(
                self.utxos.get(sender_wallet, []), sender.currency, total_cost,
            )

            if selected_total < total_cost:
                available = self._sum_wallet_utxos(sender_wallet, sender.currency)
                return (
                    f"Error: fondos insuficientes. Disponible={available}, "
                    f"Requerido={total_cost}."
                )

            self.utxos[sender_wallet] = _remove_consumed_utxos(
                self.utxos.get(sender_wallet, []), _consumed_utxo_ids(selected),
            )

            self.utxos.setdefault(receiver_wallet, []).append(
                {
                    "utxo_id": self._build_utxo_id(),
                    "wallet_id": receiver_wallet,
                    "currency": receiver.currency,
                    "amount": str(credit_amount),
                    "source": "EXCHANGE" if is_cross_currency else "TRANSFER",
                    "created_at": self._timestamp(),
                }
            )

            change = selected_total - total_cost
            if change > 0:
                self.utxos.setdefault(sender_wallet, []).append(
                    {
                        "utxo_id": self._build_utxo_id(),
                        "wallet_id": sender_wallet,
                        "currency": sender.currency,
                        "amount": str(change),
                        "source": "CHANGE",
                        "created_at": self._timestamp(),
                    }
                )

            self._sync_wallet_balance(sender_wallet)
            self._sync_wallet_balance(receiver_wallet)

        transfer_id = self._build_transfer_id()
        transfer_nonce = next_nonce
        previous_hash = self._last_transfer_hash()
        created_at = self._timestamp()
        tx_hash = self._build_transfer_hash(
            transfer_id=transfer_id,
            model=sender.model,
            sender_wallet=sender_wallet,
            receiver_wallet=receiver_wallet,
            amount=transfer_amount,
            fee=tx_fee,
            reference=reference,
            nonce=transfer_nonce,
            created_at=created_at,
            previous_hash=previous_hash,
        )
        transfer_record = {
            "transfer_id": transfer_id,
            "type": "EXCHANGE" if is_cross_currency else "TRANSFER",
            "model": sender.model,
            "sender_wallet": sender_wallet,
            "receiver_wallet": receiver_wallet,
            "amount": str(transfer_amount),
            "fee": str(tx_fee),
            "nonce": transfer_nonce,
            "previous_hash": previous_hash,
            "tx_hash": tx_hash,
            "reference": reference,
            "status": "SETTLED",
            "created_at": created_at,
        }
        transfer_record.update(exchange_metadata)
        self.transfers.append(transfer_record)
        self.wallet_nonces[sender_wallet] = transfer_nonce
        self._audit(sender.user_id, "EXCHANGE" if is_cross_currency else "TRANSFER", "WALLET", sender_wallet, {"receiver": receiver_wallet, "amount": str(transfer_amount)})

        if (
            sender_risk_profile.transfer_alert_threshold is not None
            and transfer_amount >= sender_risk_profile.transfer_alert_threshold
        ):
            self._register_alert(
                user_id=sender.user_id,
                profile_name=sender_risk_profile.profile_name,
                alert_type="TRANSFER_THRESHOLD",
                threshold=sender_risk_profile.transfer_alert_threshold,
                observed=transfer_amount,
                transfer_id=transfer_id,
            )

        if (
            sender_risk_profile.daily_alert_threshold is not None
            and projected_total >= sender_risk_profile.daily_alert_threshold
        ):
            self._register_alert(
                user_id=sender.user_id,
                profile_name=sender_risk_profile.profile_name,
                alert_type="DAILY_THRESHOLD",
                threshold=sender_risk_profile.daily_alert_threshold,
                observed=projected_total,
                transfer_id=transfer_id,
            )

        return f"Transferencia {transfer_amount} de {sender_wallet} a {receiver_wallet} aplicada."

    def get_wallet_balance(self, wallet_id: str) -> Decimal:
        if wallet_id not in self.wallets:
            return Decimal("0")
        self._refresh_wallet_token_if_expired(self.wallets[wallet_id])
        self._sync_wallet_balance(wallet_id)
        return self.wallets[wallet_id].balance

    def list_utxos(self, wallet_id: str = "") -> list[dict]:
        if wallet_id:
            source = self.utxos.get(wallet_id, [])
        else:
            source = [item for items in self.utxos.values() for item in items]
        return [
            {
                "utxo_id": str(item.get("utxo_id", "")),
                "wallet_id": str(item.get("wallet_id", "")),
                "currency": str(item.get("currency", "")),
                "amount": str(normalize_amount(item.get("amount", "0"))),
                "source": str(item.get("source", "")),
                "created_at": str(item.get("created_at", "")),
            }
            for item in source
        ]

    def list_users(self) -> list[dict]:
        return [
            {
                "user_id": user.user_id,
                "display_name": user.display_name,
                "created_at": user.created_at,
                "wallet_ids": list(self.user_wallets.get(user.user_id, [])),
                "banned": user.banned,
                "updated_at": user.updated_at,
                "deleted_at": user.deleted_at,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "username": user.username,
            }
            for user in self.users.values()
        ]

    def list_wallets(self, user_id: str = "") -> list[dict]:
        if user_id:
            wallet_ids = self.user_wallets.get(user_id, [])
            records = [self.wallets[wallet_id] for wallet_id in wallet_ids if wallet_id in self.wallets]
        else:
            records = list(self.wallets.values())

        for wallet in records:
            self._refresh_wallet_token_if_expired(wallet)

        return [
            {
                "wallet_id": wallet.wallet_id,
                "user_id": wallet.user_id,
                "model": wallet.model,
                "currency": wallet.currency,
                "balance": str(wallet.balance),
                "utxo_count": len(self.utxos.get(wallet.wallet_id, [])),
                **self._token_payload(wallet),
                "created_at": wallet.created_at,
                "frozen": wallet.frozen,
            }
            for wallet in records
        ]

    def state_snapshot(self) -> dict:
        return {
            "users": self.list_users(),
            "wallets": self.list_wallets(),
            "policies": self.list_user_policies(),
            "risk_profiles": self.list_user_risk_profiles(),
            "utxos": self.list_utxos(),
            "transfers": list(self.transfers),
            "alerts": list(self.alerts),
            "credentials": [
                {"user_id": uid, "password_hash": c["password_hash"], "created_at": c.get("created_at", ""), "updated_at": c.get("updated_at", ""), "password_temp": c.get("password_temp", False), "token_temp": c.get("token_temp", "")}
                for uid, c in self.user_credentials.items()
            ],
            "roles": [
                {"user_id": uid, "role": role, "granted_at": self._timestamp()}
                for uid, roles in self.user_roles.items()
                for role in roles
            ],
            "admin_invitation_tokens": list(self.admin_invitation_tokens),
            "activation_codes": list(self.activation_codes.values()),
            "exchange_rates": list(self.exchange_rates.values()),
            "role_permission_overrides": {k: list(v) for k, v in self.role_permission_overrides.items()},
            "user_permission_overrides": {k: list(v) for k, v in self.user_permission_overrides.items()},
            "audit_log": list(self.audit_log),
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "MultiUserWalletLedger":
        ledger = cls()

        for user in snapshot.get("users", []):
            user_id = str(user.get("user_id", "")).strip()
            if not user_id:
                continue
            ledger.users[user_id] = UserRecord(
                user_id=user_id,
                display_name=str(user.get("display_name", user_id)),
                created_at=str(user.get("created_at", cls._timestamp())),
                banned=bool(user.get("banned", False)),
                updated_at=str(user.get("updated_at", "")),
                deleted_at=str(user.get("deleted_at", "")),
                first_name=str(user.get("first_name", "")),
                last_name=str(user.get("last_name", "")),
                email=str(user.get("email", "")),
                username=str(user.get("username", "")),
            )
            ledger.user_wallets[user_id] = []

        for wallet in snapshot.get("wallets", []):
            wallet_id = str(wallet.get("wallet_id", "")).strip()
            user_id = str(wallet.get("user_id", "")).strip()
            if not wallet_id or not user_id:
                continue
            if user_id not in ledger.users:
                continue

            record = WalletRecord(
                wallet_id=wallet_id,
                user_id=user_id,
                model=cls._normalize_model(wallet.get("model", "ACCOUNT")) or "ACCOUNT",
                currency=str(wallet.get("currency", "USDX")),
                balance=normalize_amount(wallet.get("balance", "0")),
                auth_token=str(wallet.get("auth_token", cls._build_wallet_token(12))),
                token_issued_at=int(str(wallet.get("token_issued_at", cls._now_epoch()))),
                created_at=str(wallet.get("created_at", cls._timestamp())),
                frozen=bool(wallet.get("frozen", False)),
            )
            ledger.wallets[wallet_id] = record
            ledger.utxos[wallet_id] = []
            ledger.user_wallets[user_id].append(wallet_id)

        for utxo in snapshot.get("utxos", []):
            wallet_id = str(utxo.get("wallet_id", "")).strip()
            if not wallet_id or wallet_id not in ledger.wallets:
                continue
            ledger.utxos.setdefault(wallet_id, []).append(
                {
                    "utxo_id": str(utxo.get("utxo_id", cls._build_utxo_id())),
                    "wallet_id": wallet_id,
                    "currency": str(utxo.get("currency", ledger.wallets[wallet_id].currency)),
                    "amount": str(normalize_amount(utxo.get("amount", "0"))),
                    "source": str(utxo.get("source", "")),
                    "created_at": str(utxo.get("created_at", cls._timestamp())),
                }
            )

        for policy in snapshot.get("policies", []):
            user_id = str(policy.get("user_id", "")).strip()
            if not user_id or user_id not in ledger.users:
                continue
            raw_limit = policy.get("daily_limit", None)
            daily_limit = None
            if raw_limit not in (None, "", "null"):
                daily_limit = normalize_amount(raw_limit)
            ledger.user_policies[user_id] = UserPolicyRecord(
                user_id=user_id,
                can_transfer=bool(policy.get("can_transfer", True)),
                daily_limit=daily_limit,
                updated_at=str(policy.get("updated_at", cls._timestamp())),
            )

        for user_id in ledger.users.keys():
            if user_id not in ledger.user_policies:
                ledger.user_policies[user_id] = UserPolicyRecord(
                    user_id=user_id,
                    can_transfer=True,
                    daily_limit=None,
                    updated_at=cls._timestamp(),
                )

        for profile in snapshot.get("risk_profiles", []):
            user_id = str(profile.get("user_id", "")).strip()
            if not user_id or user_id not in ledger.users:
                continue
            raw_daily_limit = profile.get("daily_limit", None)
            daily_limit = None
            if raw_daily_limit not in (None, "", "null"):
                daily_limit = normalize_amount(raw_daily_limit)
            raw_transfer_threshold = profile.get("transfer_alert_threshold", None)
            transfer_alert_threshold = None
            if raw_transfer_threshold not in (None, "", "null"):
                transfer_alert_threshold = normalize_amount(raw_transfer_threshold)
            raw_daily_threshold = profile.get("daily_alert_threshold", None)
            daily_alert_threshold = None
            if raw_daily_threshold not in (None, "", "null"):
                daily_alert_threshold = normalize_amount(raw_daily_threshold)

            ledger.user_risk_profiles[user_id] = UserRiskProfileRecord(
                user_id=user_id,
                profile_name=str(profile.get("profile_name", "STANDARD")).upper(),
                daily_limit=daily_limit,
                transfer_alert_threshold=transfer_alert_threshold,
                daily_alert_threshold=daily_alert_threshold,
                updated_at=str(profile.get("updated_at", cls._timestamp())),
            )

        for user_id in ledger.users.keys():
            if user_id not in ledger.user_risk_profiles:
                ledger.user_risk_profiles[user_id] = UserRiskProfileRecord(
                    user_id=user_id,
                    profile_name="STANDARD",
                    daily_limit=None,
                    transfer_alert_threshold=None,
                    daily_alert_threshold=None,
                    updated_at=cls._timestamp(),
                )

        inferred_nonces: dict[str, int] = {}
        ledger.transfers = []
        for item in snapshot.get("transfers", []):
            transfer_type = str(item.get("type", "TRANSFER"))
            sender_wallet = str(item.get("sender_wallet", ""))
            raw_nonce = item.get("nonce", None)
            if transfer_type == "TRANSFER":
                if raw_nonce in (None, "", "null"):
                    nonce = inferred_nonces.get(sender_wallet, 0) + 1
                else:
                    nonce = int(str(raw_nonce))
                inferred_nonces[sender_wallet] = max(inferred_nonces.get(sender_wallet, 0), nonce)
            else:
                nonce = 0

            ledger.transfers.append(
                {
                    "transfer_id": str(item.get("transfer_id", "")),
                    "type": transfer_type,
                    "model": cls._normalize_model(item.get("model", "ACCOUNT")) or "ACCOUNT",
                    "sender_wallet": sender_wallet,
                    "receiver_wallet": str(item.get("receiver_wallet", "")),
                    "amount": str(normalize_amount(item.get("amount", "0"))),
                    "fee": str(normalize_amount(item.get("fee", "0"))),
                    "nonce": nonce,
                    "previous_hash": str(item.get("previous_hash", "")),
                    "tx_hash": str(item.get("tx_hash", "")),
                    "reference": str(item.get("reference", "")),
                    "status": str(item.get("status", "SETTLED")),
                    "created_at": str(item.get("created_at", cls._timestamp())),
                }
            )

        for transfer in ledger.transfers:
            if transfer.get("type") != "TRANSFER":
                continue
            sender_wallet = str(transfer.get("sender_wallet", ""))
            nonce = int(str(transfer.get("nonce", "0")))
            if sender_wallet:
                ledger.wallet_nonces[sender_wallet] = max(ledger.wallet_nonces.get(sender_wallet, 0), nonce)

        for wallet_id in ledger.wallets.keys():
            ledger._sync_wallet_balance(wallet_id)

        ledger.alerts = [
            {
                "alert_id": str(item.get("alert_id", "")),
                "user_id": str(item.get("user_id", "")),
                "profile_name": str(item.get("profile_name", "STANDARD")).upper(),
                "type": str(item.get("type", "TRANSFER_THRESHOLD")),
                "severity": str(item.get("severity", "MEDIUM")).upper(),
                "threshold": str(normalize_amount(item.get("threshold", "0"))),
                "observed": str(normalize_amount(item.get("observed", "0"))),
                "transfer_id": str(item.get("transfer_id", "")),
                "created_at": str(item.get("created_at", cls._timestamp())),
            }
            for item in snapshot.get("alerts", [])
        ]

        for cred in snapshot.get("credentials", []):
            uid = str(cred.get("user_id", "")).strip()
            if uid and uid in ledger.users:
                ledger.user_credentials[uid] = {
                    "user_id": uid,
                    "password_hash": str(cred.get("password_hash", "")),
                    "created_at": str(cred.get("created_at", cls._timestamp())),
                    "updated_at": str(cred.get("updated_at", "")),
                    "password_temp": bool(cred.get("password_temp", False)),
                    "token_temp": str(cred.get("token_temp", "")),
                }

        for role_rec in snapshot.get("roles", []):
            uid = str(role_rec.get("user_id", "")).strip()
            role = str(role_rec.get("role", "")).upper()
            if uid and uid in ledger.users and role:
                ledger.user_roles.setdefault(uid, [])
                if role not in ledger.user_roles[uid]:
                    ledger.user_roles[uid].append(role)

        for uid in ledger.users:
            if uid not in ledger.user_roles:
                ledger.user_roles[uid] = []

        ledger.admin_invitation_tokens = list(snapshot.get("admin_invitation_tokens", []))

        for ac in snapshot.get("activation_codes", []):
            uid = str(ac.get("user_id", "")).strip()
            if uid:
                ledger.activation_codes[uid] = {
                    "user_id": uid,
                    "code": str(ac.get("code", "")),
                    "activated": bool(ac.get("activated", False)),
                    "created_at": str(ac.get("created_at", cls._timestamp())),
                }

        for er in snapshot.get("exchange_rates", []):
            key = str(er.get("pair_id", "")).strip()
            if key:
                ledger.exchange_rates[key] = {
                    "pair_id": key,
                    "from_currency": str(er.get("from_currency", "")),
                    "to_currency": str(er.get("to_currency", "")),
                    "rate": str(er.get("rate", "0")),
                    "commission_pct": str(er.get("commission_pct", "1.0")),
                    "updated_at": str(er.get("updated_at", cls._timestamp())),
                }

        for role, perms in snapshot.get("role_permission_overrides", {}).items():
            ledger.role_permission_overrides[role] = list(perms)

        for uid, perms in snapshot.get("user_permission_overrides", {}).items():
            ledger.user_permission_overrides[uid] = list(perms)

        ledger.audit_log = list(snapshot.get("audit_log", []))

        max_seq = 0
        for uid in ledger.users:
            if uid.startswith("USR-"):
                try:
                    seq = int(uid.split("-", 1)[1])
                    if seq > max_seq:
                        max_seq = seq
                except (ValueError, IndexError):
                    pass
        ledger._user_seq = max_seq

        return ledger
