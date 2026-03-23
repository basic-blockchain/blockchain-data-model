import time
from dataclasses import asdict, dataclass
from decimal import Decimal, getcontext

from domain.blockchain_base import BaseBlockchain, Block, WalletKeys  # noqa: F401
from domain.compliance import resolve_profile
from domain.precision import SATOSHI, normalize_amount  # noqa: F401 — SATOSHI re-exported
from domain.traceability_models import TraceabilityLot

getcontext().prec = 28


@dataclass
class UTXO:
    utxo_id: str
    tx_id: str
    output_index: int
    amount: Decimal
    owner: str
    created_at: str
    lot_id: str | None = None
    metadata: dict | None = None


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
    signer_public_key: str
    signature: str
    block_height: int | None = None
    confirmations: int = 0
    lot_id: str | None = None


class UTXO_Blockchain(BaseBlockchain):
    def __init__(self, confirmations_required=2, max_txs_per_block=10):
        # UTXO set activo: solo salidas no gastadas.
        self.unspent_outputs = {}
        self.spent_outputs = set()
        super().__init__(confirmations_required=confirmations_required, max_txs_per_block=max_txs_per_block)

    def _create_utxo(self, tx_id, output_index, amount, owner, lot_id=None, metadata=None):
        utxo_id = f"{tx_id}:{output_index}"
        utxo = UTXO(
            utxo_id=utxo_id,
            tx_id=tx_id,
            output_index=output_index,
            amount=normalize_amount(amount),
            owner=owner,
            created_at=self._timestamp(),
            lot_id=lot_id,
            metadata=metadata or {},
        )
        self.unspent_outputs[utxo_id] = utxo
        return utxo_id

    def get_balance(self, owner):
        return sum(
            (u.amount for u in self.unspent_outputs.values() if u.owner == owner),
            Decimal("0"),
        )

    def _select_inputs(self, owner, target_amount, lot_id=None):
        candidates = sorted(
            [
                u
                for u in self.unspent_outputs.values()
                if u.owner == owner and (lot_id is None or u.lot_id == lot_id)
            ],
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

    def mint_initial_coins(self, amount, owner, lot_id=None, metadata=None):
        minted = normalize_amount(amount)
        if minted <= 0 or not self._validate_participant(owner):
            return "Error: Datos inválidos para la emisión inicial."

        self._ensure_wallet(owner)

        tx_payload = {
            "type": "coinbase",
            "owner": owner,
            "amount": str(minted),
            "lot_id": lot_id,
            "ts": time.time_ns(),
        }
        tx_id = self._build_tx_id(tx_payload)
        out_id = self._create_utxo(tx_id, 0, minted, owner, lot_id=lot_id, metadata=metadata)
        tx_record = TransactionRecord(
            tx_id=tx_id,
            sender="COINBASE",
            receiver=owner,
            amount=minted,
            fee=Decimal("0"),
            inputs=[],
            outputs=[out_id],
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key="COINBASE",
            signature="SYSTEM",
            lot_id=lot_id,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)
        return f"Emisión inicial exitosa: {minted} para {owner}."

    def send_transaction(self, sender, receiver, amount_to_send, fee=0, lot_id=None):
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
        self._ensure_wallet(sender)
        self._ensure_wallet(receiver)
        selected, total_available = self._select_inputs(sender, target, lot_id=lot_id)

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
            "lot_id": lot_id,
            "nonce": len(self.transaction_history) + 1,
            "ts": time.time_ns(),
        }
        public_key, signature = self._sign_payload(sender, tx_payload)
        if not self._verify_signature(public_key, tx_payload, signature):
            return "Error: Firma digital inválida."

        tx_id = self._build_tx_id(tx_payload)

        for utxo in selected:
            self.unspent_outputs.pop(utxo.utxo_id, None)
            self.spent_outputs.add(utxo.utxo_id)

        output_ids = [
            self._create_utxo(
                tx_id,
                0,
                amount,
                receiver,
                lot_id=lot_id,
                metadata={"event": "transfer", "from": sender, "to": receiver},
            )
        ]
        if change > 0:
            output_ids.append(
                self._create_utxo(
                    tx_id,
                    1,
                    change,
                    sender,
                    lot_id=lot_id,
                    metadata={"event": "change", "owner": sender},
                )
            )

        self.validator_pool += tx_fee
        tx_record = TransactionRecord(
            tx_id=tx_id,
            sender=sender,
            receiver=receiver,
            amount=amount,
            fee=tx_fee,
            inputs=input_ids,
            outputs=output_ids,
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key=public_key,
            signature=signature,
            lot_id=lot_id,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)

        if lot_id and lot_id in self.lots:
            self.lots[lot_id].owner = receiver

        return (
            f"Transacción aceptada en mempool: {amount} a {receiver}. "
            f"Comisión={tx_fee}. Cambio={change}."
        )

    def register_lot(self, lot_id, owner, product, origin, initial_amount):
        if lot_id in self.lots:
            return "Error: El lote ya existe."
        if not all([
            self._validate_participant(lot_id),
            self._validate_participant(owner),
            self._validate_participant(product),
            self._validate_participant(origin),
        ]):
            return "Error: Datos inválidos para registrar lote."

        profile = resolve_profile(product, custom_profiles=self.compliance_profiles)

        self.lots[lot_id] = TraceabilityLot(
            lot_id=lot_id,
            product=product,
            origin=origin,
            owner=owner,
            created_at=self._timestamp(),
            certificate_ids=[],
            event_ids=[],
            required_events=profile["required_events"],
            min_active_certificates=profile["min_active_certificates"],
        )
        return self.mint_initial_coins(
            initial_amount,
            owner,
            lot_id=lot_id,
            metadata={"product": product, "origin": origin},
        )

    def utxo_snapshot(self):
        return [asdict(utxo) for utxo in self.unspent_outputs.values()]


if __name__ == "__main__":
    print("--- SISTEMA MODELO UTXO - ITERACION 2 ---")
    agro_bolsa = UTXO_Blockchain(confirmations_required=2, max_txs_per_block=5)
    print(agro_bolsa.create_wallet("Exportador_Colombia")[0])
    print(agro_bolsa.create_wallet("Logistica_Latam")[0])
    print(agro_bolsa.create_wallet("Aduana_Pacifico")[0])

    print(
        agro_bolsa.register_lot(
            lot_id="Lote_Cafe_001",
            owner="Exportador_Colombia",
            product="Cafe Arabe",
            origin="Huila_Colombia",
            initial_amount=100,
        )
    )
    print(agro_bolsa.issue_certificate("Lote_Cafe_001", "Fitosanitario", "ICA"))
    print(
        agro_bolsa.record_logistics_event(
            "Lote_Cafe_001", "COSECHA", "Cooperativa_Huila", "Finca_El_Roble"
        )
    )
    print(
        agro_bolsa.record_logistics_event(
            "Lote_Cafe_001", "PROCESAMIENTO", "Planta_Trillado", "Neiva"
        )
    )

    print(
        agro_bolsa.send_transaction(
            "Exportador_Colombia",
            "Logistica_Latam",
            30,
            fee=0.25,
            lot_id="Lote_Cafe_001",
        )
    )
    print(agro_bolsa.mine_block("Nodo_Validador_1"))
    print(
        agro_bolsa.record_logistics_event(
            "Lote_Cafe_001", "EXPORTACION", "Puerto_Buenaventura", "Buenaventura"
        )
    )
    print(agro_bolsa.mine_block("Nodo_Validador_2"))

    print("Auditoria compliance:", agro_bolsa.audit_compliance("Lote_Cafe_001"))
    print("Balance Exportador:", agro_bolsa.get_balance("Exportador_Colombia"))
    print("Balance Logistica:", agro_bolsa.get_balance("Logistica_Latam"))
    print("Altura cadena:", len(agro_bolsa.blocks) - 1)
    print("Pool de validadores:", agro_bolsa.validator_pool)
    print("Estado lotes:", {k: asdict(v) for k, v in agro_bolsa.lots.items()})
