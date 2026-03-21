from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

UNIT = Decimal("0.00000001")


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
    currency: str
    balance: Decimal
    created_at: str


@dataclass
class UserPolicyRecord:
    user_id: str
    can_transfer: bool
    daily_limit: Decimal | None
    updated_at: str


class MultiUserWalletLedger:
    def __init__(self):
        self.users: dict[str, UserRecord] = {}
        self.wallets: dict[str, WalletRecord] = {}
        self.user_wallets: dict[str, list[str]] = {}
        self.user_policies: dict[str, UserPolicyRecord] = {}
        self.transfers: list[dict] = []

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _build_wallet_id() -> str:
        return f"wlt-{secrets.token_hex(6)}"

    @staticmethod
    def _build_transfer_id() -> str:
        return f"tx-{secrets.token_hex(8)}"

    def create_user(self, user_id: str, display_name: str) -> str:
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
        self.user_policies[user_id] = UserPolicyRecord(
            user_id=user_id,
            can_transfer=True,
            daily_limit=None,
            updated_at=self._timestamp(),
        )
        return f"Usuario {user_id} creado."

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
            return {
                "user_id": user_id,
                "can_transfer": True,
                "daily_limit": None,
                "updated_at": "",
            }
        return {
            "user_id": policy.user_id,
            "can_transfer": policy.can_transfer,
            "daily_limit": str(policy.daily_limit) if policy.daily_limit is not None else None,
            "updated_at": policy.updated_at,
        }

    def list_user_policies(self) -> list[dict]:
        return [self.get_user_policy(user_id) for user_id in self.users.keys()]

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

    def create_wallet(self, user_id: str, wallet_id: str = "", currency: str = "USDX") -> str:
        if user_id not in self.users:
            return f"Error: el usuario {user_id} no existe."

        final_wallet_id = wallet_id.strip() or self._build_wallet_id()
        if final_wallet_id in self.wallets:
            return f"Error: wallet {final_wallet_id} ya existe."

        wallet = WalletRecord(
            wallet_id=final_wallet_id,
            user_id=user_id,
            currency=currency,
            balance=Decimal("0"),
            created_at=self._timestamp(),
        )
        self.wallets[final_wallet_id] = wallet
        self.user_wallets[user_id].append(final_wallet_id)
        return f"Wallet {final_wallet_id} creada para {user_id}."

    def mint(self, wallet_id: str, amount: Decimal | int | float | str, reference: str = "MINT") -> str:
        minted = normalize_amount(amount)
        if minted <= 0:
            return "Error: amount debe ser mayor a cero."
        if wallet_id not in self.wallets:
            return f"Error: wallet {wallet_id} no existe."

        wallet = self.wallets[wallet_id]
        wallet.balance += minted
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
        if sender.currency != receiver.currency:
            return "Error: transfer entre wallets de distinta moneda no soportada."

        sender_policy = self.user_policies.get(
            sender.user_id,
            UserPolicyRecord(
                user_id=sender.user_id,
                can_transfer=True,
                daily_limit=None,
                updated_at=self._timestamp(),
            ),
        )
        if not sender_policy.can_transfer:
            return "Error: política de usuario impide transferencias para este emisor."

        if sender_policy.daily_limit is not None:
            day_prefix = self._timestamp()[:10]
            day_total = self._daily_transfer_total(sender.user_id, day_prefix)
            projected_total = day_total + transfer_amount
            if projected_total > sender_policy.daily_limit:
                return (
                    "Error: límite diario excedido. "
                    f"Actual={day_total}, Intento={transfer_amount}, Límite={sender_policy.daily_limit}."
                )

        total_cost = transfer_amount + tx_fee
        if sender.balance < total_cost:
            return (
                f"Error: fondos insuficientes. Disponible={sender.balance}, "
                f"Requerido={total_cost}."
            )

        sender.balance -= total_cost
        receiver.balance += transfer_amount

        self.transfers.append(
            {
                "transfer_id": self._build_transfer_id(),
                "type": "TRANSFER",
                "sender_wallet": sender_wallet,
                "receiver_wallet": receiver_wallet,
                "amount": str(transfer_amount),
                "fee": str(tx_fee),
                "reference": reference,
                "status": "SETTLED",
                "created_at": self._timestamp(),
            }
        )
        return f"Transferencia {transfer_amount} de {sender_wallet} a {receiver_wallet} aplicada."

    def get_wallet_balance(self, wallet_id: str) -> Decimal:
        if wallet_id not in self.wallets:
            return Decimal("0")
        return self.wallets[wallet_id].balance

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

        return [
            {
                "wallet_id": wallet.wallet_id,
                "user_id": wallet.user_id,
                "currency": wallet.currency,
                "balance": str(wallet.balance),
                "created_at": wallet.created_at,
            }
            for wallet in records
        ]

    def state_snapshot(self) -> dict:
        return {
            "users": self.list_users(),
            "wallets": self.list_wallets(),
            "policies": self.list_user_policies(),
            "transfers": list(self.transfers),
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
                currency=str(wallet.get("currency", "USDX")),
                balance=normalize_amount(wallet.get("balance", "0")),
                created_at=str(wallet.get("created_at", cls._timestamp())),
            )
            ledger.wallets[wallet_id] = record
            ledger.user_wallets[user_id].append(wallet_id)

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

        ledger.transfers = [
            {
                "transfer_id": str(item.get("transfer_id", "")),
                "type": str(item.get("type", "TRANSFER")),
                "sender_wallet": str(item.get("sender_wallet", "")),
                "receiver_wallet": str(item.get("receiver_wallet", "")),
                "amount": str(normalize_amount(item.get("amount", "0"))),
                "fee": str(normalize_amount(item.get("fee", "0"))),
                "reference": str(item.get("reference", "")),
                "status": str(item.get("status", "SETTLED")),
                "created_at": str(item.get("created_at", cls._timestamp())),
            }
            for item in snapshot.get("transfers", [])
        ]

        return ledger
