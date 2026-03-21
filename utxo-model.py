import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, getcontext

from domain.compliance import DEFAULT_COMPLIANCE_PROFILES, evaluate_compliance, resolve_profile
from domain.traceability_models import CertificateRecord, LogisticsEvent, TraceabilityLot

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
    lot_id: str | None = None
    metadata: dict | None = None


@dataclass
class WalletKeys:
    address: str
    public_key: str
    private_key: str
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
    signer_public_key: str
    signature: str
    block_height: int | None = None
    confirmations: int = 0
    lot_id: str | None = None


@dataclass
class Block:
    height: int
    previous_hash: str
    block_hash: str
    tx_ids: list[str]
    mined_by: str
    timestamp: str


class UTXO_Blockchain:
    def __init__(self, confirmations_required=2, max_txs_per_block=10):
        # UTXO set activo: solo salidas no gastadas.
        self.unspent_outputs = {}
        self.spent_outputs = set()
        self.transaction_history = []
        self.tx_index = {}
        self.pending_tx_ids = []
        self.validator_pool = Decimal("0")
        self.wallets = {}
        self.confirmations_required = confirmations_required
        self.max_txs_per_block = max_txs_per_block
        self.blocks = []
        self.lots = {}
        self.certificates = {}
        self.logistics_events = {}
        self.compliance_profiles = dict(DEFAULT_COMPLIANCE_PROFILES)
        self._create_genesis_block()

    def _timestamp(self):
        return datetime.now(timezone.utc).isoformat()

    def _build_tx_id(self, payload):
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    def _block_hash(self, payload):
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    def _create_genesis_block(self):
        payload = {
            "height": 0,
            "previous_hash": "0" * 64,
            "tx_ids": [],
            "mined_by": "GENESIS",
            "timestamp": self._timestamp(),
        }
        genesis_hash = self._block_hash(payload)
        self.blocks.append(
            Block(
                height=0,
                previous_hash=payload["previous_hash"],
                block_hash=genesis_hash,
                tx_ids=[],
                mined_by="GENESIS",
                timestamp=payload["timestamp"],
            )
        )

    def create_wallet(self, address):
        if not self._validate_participant(address):
            return "Error: Dirección inválida para wallet.", None
        if address in self.wallets:
            return f"Aviso: Wallet existente para {address}.", self.wallets[address]

        private_key = secrets.token_hex(32)
        public_key = hashlib.sha256(private_key.encode()).hexdigest()
        wallet = WalletKeys(
            address=address,
            public_key=public_key,
            private_key=private_key,
            created_at=self._timestamp(),
        )
        self.wallets[address] = wallet
        return f"Wallet creada para {address}.", wallet

    def _ensure_wallet(self, address):
        if address not in self.wallets:
            self.create_wallet(address)
        return self.wallets[address]

    def _sign_payload(self, address, payload):
        wallet = self._ensure_wallet(address)
        message = json.dumps(payload, sort_keys=True)
        signature = hashlib.sha256(f"{wallet.private_key}:{message}".encode()).hexdigest()
        return wallet.public_key, signature

    def _verify_signature(self, public_key, payload, signature):
        for wallet in self.wallets.values():
            if wallet.public_key != public_key:
                continue
            message = json.dumps(payload, sort_keys=True)
            expected = hashlib.sha256(f"{wallet.private_key}:{message}".encode()).hexdigest()
            return expected == signature
        return False

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

    def _validate_participant(self, participant):
        return isinstance(participant, str) and participant.strip() != ""

    def configure_compliance_profile(self, profile_name, required_events, min_active_certificates=1):
        if not self._validate_participant(profile_name):
            return "Error: profile_name inválido."
        if not required_events or not all(self._validate_participant(item) for item in required_events):
            return "Error: required_events inválido."
        if min_active_certificates < 1:
            return "Error: min_active_certificates debe ser >= 1."

        self.compliance_profiles[profile_name.upper()] = {
            "required_events": [item.upper() for item in required_events],
            "min_active_certificates": int(min_active_certificates),
        }
        return f"Perfil de compliance {profile_name.upper()} configurado."

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

    def mine_block(self, miner):
        if not self._validate_participant(miner):
            return "Error: Miner inválido."
        if not self.pending_tx_ids:
            return "No hay transacciones pendientes para minar."

        tx_ids = self.pending_tx_ids[: self.max_txs_per_block]
        self.pending_tx_ids = self.pending_tx_ids[self.max_txs_per_block :]
        previous = self.blocks[-1]
        height = len(self.blocks)
        timestamp = self._timestamp()
        payload = {
            "height": height,
            "previous_hash": previous.block_hash,
            "tx_ids": tx_ids,
            "mined_by": miner,
            "timestamp": timestamp,
        }
        block_hash = self._block_hash(payload)
        self.blocks.append(
            Block(
                height=height,
                previous_hash=previous.block_hash,
                block_hash=block_hash,
                tx_ids=tx_ids,
                mined_by=miner,
                timestamp=timestamp,
            )
        )

        for tx_id in tx_ids:
            tx = self.tx_index.get(tx_id)
            if tx is None:
                continue
            tx.block_height = height

        self._refresh_confirmations()
        return f"Bloque {height} minado por {miner} con {len(tx_ids)} transacciones."

    def _refresh_confirmations(self):
        chain_height = len(self.blocks) - 1
        for tx in self.transaction_history:
            if tx.block_height is None:
                tx.confirmations = 0
                tx.status = "PENDING"
                continue
            tx.confirmations = chain_height - tx.block_height + 1
            tx.status = (
                "FINALIZED"
                if tx.confirmations >= self.confirmations_required
                else "CONFIRMED"
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

    def issue_certificate(self, lot_id, cert_type, issuer, valid_days=365, metadata=None):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."
        if not self._validate_participant(cert_type) or not self._validate_participant(issuer):
            return "Error: Datos inválidos para certificado."

        issued_at = self._timestamp()
        valid_until_ts = datetime.now(timezone.utc).timestamp() + (valid_days * 24 * 3600)
        valid_until = datetime.fromtimestamp(valid_until_ts, tz=timezone.utc).isoformat()
        doc_payload = {
            "lot_id": lot_id,
            "cert_type": cert_type,
            "issuer": issuer,
            "metadata": metadata or {},
            "issued_at": issued_at,
        }
        cert_hash = self._build_tx_id(doc_payload)
        certificate_id = f"CERT-{cert_hash[:12]}"
        certificate = CertificateRecord(
            certificate_id=certificate_id,
            lot_id=lot_id,
            cert_type=cert_type,
            issuer=issuer,
            document_hash=cert_hash,
            issued_at=issued_at,
            valid_until=valid_until,
        )
        self.certificates[certificate_id] = certificate
        lot.certificate_ids.append(certificate_id)
        return f"Certificado {certificate_id} emitido para lote {lot_id}."

    def record_logistics_event(self, lot_id, event_type, actor, location, metadata=None):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."
        if not all([
            self._validate_participant(event_type),
            self._validate_participant(actor),
            self._validate_participant(location),
        ]):
            return "Error: Datos inválidos de evento logístico."

        event_seed = {
            "lot_id": lot_id,
            "event_type": event_type,
            "actor": actor,
            "location": location,
            "ts": time.time_ns(),
        }
        event_id = f"EVT-{self._build_tx_id(event_seed)[:12]}"
        event = LogisticsEvent(
            event_id=event_id,
            lot_id=lot_id,
            event_type=event_type,
            actor=actor,
            location=location,
            timestamp=self._timestamp(),
            metadata=metadata or {},
        )
        self.logistics_events[event_id] = event
        lot.event_ids.append(event_id)
        return f"Evento logístico {event_type} registrado para lote {lot_id}."

    def audit_compliance(self, lot_id):
        lot = self.lots.get(lot_id)
        if lot is None:
            return {"status": "FAIL", "reason": "Lote no encontrado"}

        report = evaluate_compliance(
            lot=lot,
            certificates=self.certificates,
            logistics_events=self.logistics_events,
        )
        lot.compliance_status = report["status"]

        report["lot_id"] = lot_id
        report["owner"] = lot.owner
        return report

    def ledger_snapshot(self):
        return [asdict(tx) for tx in self.transaction_history]

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