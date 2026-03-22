from __future__ import annotations

import secrets
import re
import string
import time
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

UNIT = Decimal("0.00000001")
TOKEN_ALPHABET = string.ascii_letters + string.digits


def normalize_amount(value: Decimal | int | float | str) -> Decimal:
    normalized = Decimal(str(value)).quantize(UNIT, rounding=ROUND_DOWN)
    return Decimal(format(normalized, "f")).quantize(UNIT, rounding=ROUND_DOWN)


@dataclass
class UserRecord:
    user_id: str
    display_name: str
    created_at: str


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
    TOKEN_TTL_SECONDS = 120

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

    def is_empty(self) -> bool:
        return len(self.users) == 0

    def create_user(self, user_id: str, display_name: str, password: str = "") -> str:
        if not user_id or not display_name:
            return "Error: user_id y display_name son requeridos."
        if user_id in self.users:
            return f"Aviso: el usuario {user_id} ya existe."

        self.users[user_id] = UserRecord(
            user_id=user_id,
            display_name=display_name,
            created_at=self._timestamp(),
        )
        self.user_wallets[user_id] = []
        self.user_policies[user_id] = self._new_user_policy(user_id)
        self.user_risk_profiles[user_id] = self._new_user_risk_profile(user_id)
        self.user_roles[user_id] = []

        if password:
            from domain.auth import hash_password
            now = self._timestamp()
            self.user_credentials[user_id] = {
                "user_id": user_id,
                "password_hash": hash_password(password),
                "created_at": now,
                "updated_at": now,
            }

        return f"Usuario {user_id} creado."

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

    def login(self, user_id: str, password: str, jwt_secret: str, jwt_ttl: int = 3600) -> dict | str:
        if not self.authenticate(user_id, password):
            return "Error: credenciales invalidas."
        from domain.auth import create_jwt
        roles = self.user_roles.get(user_id, [])
        token = create_jwt(user_id, roles, jwt_secret, jwt_ttl)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": jwt_ttl,
            "user_id": user_id,
            "roles": roles,
        }

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
        return f"Role {role} asignado a {user_id}."

    def remove_role(self, user_id: str, role: str) -> str:
        if user_id not in self.users:
            return f"Error: usuario {user_id} no existe."
        role = role.upper()
        roles = self.user_roles.get(user_id, [])
        if role not in roles:
            return f"Error: {user_id} no tiene el role {role}."
        roles.remove(role)
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
        total = Decimal("0")
        for utxo in self.utxos.get(wallet_id, []):
            if str(utxo.get("currency", "")) != currency:
                continue
            total += normalize_amount(utxo.get("amount", "0"))
        return total

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
        return f"Mint {minted} aplicado a {wallet_id}."

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
        self._refresh_wallet_token_if_expired(receiver)
        if sender.model != receiver.model:
            return "Error: transfer entre wallets de distinto modelo no soportada."
        if sender.currency != receiver.currency:
            return "Error: transfer entre wallets de distinta moneda no soportada."

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

        total_cost = transfer_amount + tx_fee
        if sender.model == "ACCOUNT":
            if sender.balance < total_cost:
                return (
                    f"Error: fondos insuficientes. Disponible={sender.balance}, "
                    f"Requerido={total_cost}."
                )
            sender.balance -= total_cost
            receiver.balance += transfer_amount
        else:
            selected: list[dict] = []
            selected_total = Decimal("0")
            for utxo in self.utxos.get(sender_wallet, []):
                if str(utxo.get("currency", "")) != sender.currency:
                    continue
                selected.append(utxo)
                selected_total += normalize_amount(utxo.get("amount", "0"))
                if selected_total >= total_cost:
                    break

            if selected_total < total_cost:
                available = self._sum_wallet_utxos(sender_wallet, sender.currency)
                return (
                    f"Error: fondos insuficientes. Disponible={available}, "
                    f"Requerido={total_cost}."
                )

            consumed_ids = {str(item.get("utxo_id", "")) for item in selected}
            self.utxos[sender_wallet] = [
                utxo
                for utxo in self.utxos.get(sender_wallet, [])
                if str(utxo.get("utxo_id", "")) not in consumed_ids
            ]

            self.utxos.setdefault(receiver_wallet, []).append(
                {
                    "utxo_id": self._build_utxo_id(),
                    "wallet_id": receiver_wallet,
                    "currency": receiver.currency,
                    "amount": str(transfer_amount),
                    "source": "TRANSFER",
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
        self.transfers.append(
            {
                "transfer_id": transfer_id,
                "type": "TRANSFER",
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
        )
        self.wallet_nonces[sender_wallet] = transfer_nonce

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
                {"user_id": uid, "password_hash": c["password_hash"], "created_at": c.get("created_at", ""), "updated_at": c.get("updated_at", "")}
                for uid, c in self.user_credentials.items()
            ],
            "roles": [
                {"user_id": uid, "role": role, "granted_at": self._timestamp()}
                for uid, roles in self.user_roles.items()
                for role in roles
            ],
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

        return ledger
