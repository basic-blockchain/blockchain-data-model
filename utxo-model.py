import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 28
SATOSHI = Decimal("0.00000001")


def normalize_amount(value):
    normalized = Decimal(str(value)).quantize(SATOSHI, rounding=ROUND_DOWN)
    return Decimal(format(normalized, "f")).quantize(SATOSHI, rounding=ROUND_DOWN)


@dataclass
class UTXO:
    utxo_id: str
    tx_id: str
    output_index: int
    amount: Decimal
    owner: str
    created_at: str


@dataclass
class TransactionRecord:
    tx_id: str
    sender: str
    receiver: str
    amount: Decimal
    fee: Decimal
    inputs: list[str]
    outputs: list[str]
    status: str
    timestamp: str


class UTXO_Blockchain:
    def __init__(self):
        # UTXO set activo: solo salidas no gastadas.
        self.unspent_outputs = {}
        self.spent_outputs = set()
        self.transaction_history = []
        self.validator_pool = Decimal("0")

    def _timestamp(self):
        return datetime.now(timezone.utc).isoformat()

    def _build_tx_id(self, payload):
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    def _create_utxo(self, tx_id, output_index, amount, owner):
        utxo_id = f"{tx_id}:{output_index}"
        utxo = UTXO(
            utxo_id=utxo_id,
            tx_id=tx_id,
            output_index=output_index,
            amount=normalize_amount(amount),
            owner=owner,
            created_at=self._timestamp(),
        )
        self.unspent_outputs[utxo_id] = utxo
        return utxo_id

    def _validate_participant(self, participant):
        return isinstance(participant, str) and participant.strip() != ""

    def get_balance(self, owner):
        return sum(
            (u.amount for u in self.unspent_outputs.values() if u.owner == owner),
            Decimal("0"),
        )

    def _select_inputs(self, owner, target_amount):
        candidates = sorted(
            [u for u in self.unspent_outputs.values() if u.owner == owner],
            key=lambda item: item.amount,
        )
        selected = []
        collected = Decimal("0")

        for utxo in candidates:
            selected.append(utxo)
            collected += utxo.amount
            if collected >= target_amount:
                break

        return selected, collected

    def mint_initial_coins(self, amount, owner):
        minted = normalize_amount(amount)
        if minted <= 0 or not self._validate_participant(owner):
            return "Error: Datos inválidos para la emisión inicial."

        tx_payload = {
            "type": "coinbase",
            "owner": owner,
            "amount": str(minted),
            "ts": time.time_ns(),
        }
        tx_id = self._build_tx_id(tx_payload)
        out_id = self._create_utxo(tx_id, 0, minted, owner)
        self.transaction_history.append(
            TransactionRecord(
                tx_id=tx_id,
                sender="COINBASE",
                receiver=owner,
                amount=minted,
                fee=Decimal("0"),
                inputs=[],
                outputs=[out_id],
                status="CONFIRMED",
                timestamp=self._timestamp(),
            )
        )
        return f"Emisión inicial exitosa: {minted} para {owner}."

    def send_transaction(self, sender, receiver, amount_to_send, fee=0):
        amount = normalize_amount(amount_to_send)
        tx_fee = normalize_amount(fee)

        if not self._validate_participant(sender) or not self._validate_participant(receiver):
            return "Error: Dirección inválida."
        if sender == receiver:
            return "Error: Sender y receiver deben ser distintos."
        if amount <= 0:
            return "Error: El monto debe ser mayor que cero."
        if tx_fee < 0:
            return "Error: La comisión no puede ser negativa."

        target = amount + tx_fee
        selected, total_available = self._select_inputs(sender, target)

        if total_available < target:
            return (
                f"Error: Fondos insuficientes. Disponible={total_available}, "
                f"Requerido={target}."
            )

        input_ids = [u.utxo_id for u in selected]
        change = normalize_amount(total_available - target)
        tx_payload = {
            "type": "transfer",
            "sender": sender,
            "receiver": receiver,
            "amount": str(amount),
            "fee": str(tx_fee),
            "inputs": input_ids,
            "nonce": len(self.transaction_history) + 1,
            "ts": time.time_ns(),
        }
        tx_id = self._build_tx_id(tx_payload)

        for utxo in selected:
            self.unspent_outputs.pop(utxo.utxo_id, None)
            self.spent_outputs.add(utxo.utxo_id)

        output_ids = [self._create_utxo(tx_id, 0, amount, receiver)]
        if change > 0:
            output_ids.append(self._create_utxo(tx_id, 1, change, sender))

        self.validator_pool += tx_fee
        self.transaction_history.append(
            TransactionRecord(
                tx_id=tx_id,
                sender=sender,
                receiver=receiver,
                amount=amount,
                fee=tx_fee,
                inputs=input_ids,
                outputs=output_ids,
                status="CONFIRMED",
                timestamp=self._timestamp(),
            )
        )

        return (
            f"Transacción confirmada: {amount} a {receiver}. "
            f"Comisión={tx_fee}. Cambio={change}."
        )

    def ledger_snapshot(self):
        return [asdict(tx) for tx in self.transaction_history]

    def utxo_snapshot(self):
        return [asdict(utxo) for utxo in self.unspent_outputs.values()]


if __name__ == "__main__":
    print("--- SISTEMA MODELO UTXO ---")
    agro_bolsa = UTXO_Blockchain()
    print(agro_bolsa.mint_initial_coins(100, "Exportador_Colombia"))

    print("Balance Exportador:", agro_bolsa.get_balance("Exportador_Colombia"))
    status_1 = agro_bolsa.send_transaction(
        "Exportador_Colombia", "Logistica_Latam", 30, fee=0.25
    )
    print(status_1)

    status_2 = agro_bolsa.send_transaction(
        "Exportador_Colombia", "Aduana_Pacifico", 40, fee=0.10
    )
    print(status_2)

    print("Balance Exportador:", agro_bolsa.get_balance("Exportador_Colombia"))
    print("Balance Logistica:", agro_bolsa.get_balance("Logistica_Latam"))
    print("Balance Aduana:", agro_bolsa.get_balance("Aduana_Pacifico"))
    print("Pool de validadores:", agro_bolsa.validator_pool)
    print("UTXOs activos:", agro_bolsa.utxo_snapshot())