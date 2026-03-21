import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 28
UNIT = Decimal("0.00000001")


def normalize_amount(value):
    normalized = Decimal(str(value)).quantize(UNIT, rounding=ROUND_DOWN)
    return Decimal(format(normalized, "f")).quantize(UNIT, rounding=ROUND_DOWN)


@dataclass
class AccountState:
    balance: Decimal
    nonce: int
    created_at: str


@dataclass
class AccountTransaction:
    tx_id: str
    sender: str
    receiver: str
    amount: Decimal
    fee: Decimal
    nonce: int
    status: str
    timestamp: str


class AccountBased_Blockchain:
    def __init__(self):
        # Estado global de cuentas con control de nonce por dirección.
        self.accounts = {}
        self.transaction_history = []
        self.validator_pool = Decimal("0")

    def _timestamp(self):
        return datetime.now(timezone.utc).isoformat()

    def _build_tx_id(self, payload):
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    def _is_valid_address(self, address):
        return isinstance(address, str) and address.strip() != ""

    def create_account(self, address, initial_balance=0):
        if not self._is_valid_address(address):
            return "Error: Dirección inválida."
        if address in self.accounts:
            return f"Aviso: La cuenta {address} ya existe."

        balance = normalize_amount(initial_balance)
        if balance < 0:
            return "Error: Saldo inicial inválido."

        self.accounts[address] = AccountState(
            balance=balance,
            nonce=0,
            created_at=self._timestamp(),
        )
        return f"Cuenta creada: {address} con saldo {balance}."

    def mint(self, receiver, amount):
        minted = normalize_amount(amount)
        if minted <= 0 or not self._is_valid_address(receiver):
            return "Error: Datos inválidos para mint."

        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        self.accounts[receiver].balance += minted
        tx_payload = {
            "type": "mint",
            "receiver": receiver,
            "amount": str(minted),
            "ts": time.time_ns(),
        }
        tx_id = self._build_tx_id(tx_payload)
        self.transaction_history.append(
            AccountTransaction(
                tx_id=tx_id,
                sender="TREASURY",
                receiver=receiver,
                amount=minted,
                fee=Decimal("0"),
                nonce=-1,
                status="CONFIRMED",
                timestamp=self._timestamp(),
            )
        )
        return f"Mint confirmado: {minted} para {receiver}."

    def send_transaction(self, sender, receiver, amount, fee=0, expected_nonce=None):
        transfer_amount = normalize_amount(amount)
        tx_fee = normalize_amount(fee)

        if not self._is_valid_address(sender) or not self._is_valid_address(receiver):
            return "Error: Dirección inválida."
        if sender == receiver:
            return "Error: Sender y receiver deben ser distintos."
        if transfer_amount <= 0:
            return "Error: El monto debe ser mayor a cero."
        if tx_fee < 0:
            return "Error: La comisión no puede ser negativa."
        if sender not in self.accounts:
            return "Error: La cuenta emisora no existe."
        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        sender_state = self.accounts[sender]
        receiver_state = self.accounts[receiver]

        if expected_nonce is not None and expected_nonce != sender_state.nonce:
            return (
                f"Error: Nonce inválido. Esperado={sender_state.nonce}, "
                f"Recibido={expected_nonce}."
            )

        total_cost = transfer_amount + tx_fee
        if sender_state.balance < total_cost:
            return (
                f"Error: Fondos insuficientes. Disponible={sender_state.balance}, "
                f"Requerido={total_cost}."
            )

        sender_state.balance -= total_cost
        sender_state.nonce += 1
        receiver_state.balance += transfer_amount
        self.validator_pool += tx_fee

        tx_payload = {
            "type": "transfer",
            "sender": sender,
            "receiver": receiver,
            "amount": str(transfer_amount),
            "fee": str(tx_fee),
            "nonce": sender_state.nonce,
            "ts": time.time_ns(),
        }
        tx_id = self._build_tx_id(tx_payload)

        self.transaction_history.append(
            AccountTransaction(
                tx_id=tx_id,
                sender=sender,
                receiver=receiver,
                amount=transfer_amount,
                fee=tx_fee,
                nonce=sender_state.nonce,
                status="CONFIRMED",
                timestamp=self._timestamp(),
            )
        )

        return (
            f"Transacción confirmada: {transfer_amount} de {sender} a {receiver}. "
            f"Fee={tx_fee}. Nonce={sender_state.nonce}."
        )

    def get_balance(self, address):
        if address not in self.accounts:
            return Decimal("0")
        return self.accounts[address].balance

    def state_snapshot(self):
        return {address: asdict(state) for address, state in self.accounts.items()}

    def ledger_snapshot(self):
        return [asdict(tx) for tx in self.transaction_history]


if __name__ == "__main__":
    print("\n--- SISTEMA DE MODELO DE CUENTAS ---")
    agro_eth = AccountBased_Blockchain()
    print(agro_eth.create_account("Exportador_Colombia", 100))
    print(agro_eth.create_account("Logistica_Latam", 0))

    status_1 = agro_eth.send_transaction(
        "Exportador_Colombia", "Logistica_Latam", 30, fee=0.15, expected_nonce=0
    )
    print(status_1)

    status_2 = agro_eth.send_transaction(
        "Exportador_Colombia", "Aduana_Pacifico", 20, fee=0.10, expected_nonce=1
    )
    print(status_2)

    print("Balance Exportador:", agro_eth.get_balance("Exportador_Colombia"))
    print("Balance Logistica:", agro_eth.get_balance("Logistica_Latam"))
    print("Balance Aduana:", agro_eth.get_balance("Aduana_Pacifico"))
    print("Pool de validadores:", agro_eth.validator_pool)
    print("Estado final:", agro_eth.state_snapshot())