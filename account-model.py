import hashlib
import json
import secrets
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
    public_key: str


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
    signer_public_key: str
    signature: str
    block_height: int | None = None
    confirmations: int = 0


@dataclass
class Block:
    height: int
    previous_hash: str
    block_hash: str
    tx_ids: list[str]
    mined_by: str
    timestamp: str


@dataclass
class WalletKeys:
    address: str
    public_key: str
    private_key: str
    created_at: str


@dataclass
class TraceabilityLot:
    lot_id: str
    product: str
    origin: str
    owner: str
    created_at: str
    certificate_ids: list[str]
    event_ids: list[str]
    compliance_status: str = "PENDING"


@dataclass
class CertificateRecord:
    certificate_id: str
    lot_id: str
    cert_type: str
    issuer: str
    document_hash: str
    issued_at: str
    valid_until: str
    revoked: bool = False


@dataclass
class LogisticsEvent:
    event_id: str
    lot_id: str
    event_type: str
    actor: str
    location: str
    timestamp: str
    metadata: dict


class AccountBased_Blockchain:
    def __init__(self, confirmations_required=2, max_txs_per_block=10):
        # Estado global de cuentas con control de nonce por dirección.
        self.accounts = {}
        self.transaction_history = []
        self.tx_index = {}
        self.pending_tx_ids = []
        self.validator_pool = Decimal("0")
        self.wallets = {}
        self.blocks = []
        self.confirmations_required = confirmations_required
        self.max_txs_per_block = max_txs_per_block
        self.lots = {}
        self.certificates = {}
        self.logistics_events = {}
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
        block_hash = self._block_hash(payload)
        self.blocks.append(
            Block(
                height=0,
                previous_hash=payload["previous_hash"],
                block_hash=block_hash,
                tx_ids=[],
                mined_by="GENESIS",
                timestamp=payload["timestamp"],
            )
        )

    def _is_valid_address(self, address):
        return isinstance(address, str) and address.strip() != ""

    def create_wallet(self, address):
        if not self._is_valid_address(address):
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

    def create_account(self, address, initial_balance=0):
        if not self._is_valid_address(address):
            return "Error: Dirección inválida."
        if address in self.accounts:
            return f"Aviso: La cuenta {address} ya existe."

        balance = normalize_amount(initial_balance)
        if balance < 0:
            return "Error: Saldo inicial inválido."

        wallet = self._ensure_wallet(address)
        self.accounts[address] = AccountState(
            balance=balance,
            nonce=0,
            created_at=self._timestamp(),
            public_key=wallet.public_key,
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
        public_key, signature = self._sign_payload(receiver, tx_payload)
        if not self._verify_signature(public_key, tx_payload, signature):
            return "Error: Firma digital inválida en mint."

        tx_id = self._build_tx_id(tx_payload)
        tx_record = AccountTransaction(
            tx_id=tx_id,
            sender="TREASURY",
            receiver=receiver,
            amount=minted,
            fee=Decimal("0"),
            nonce=-1,
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key=public_key,
            signature=signature,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)
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

        next_nonce = sender_state.nonce + 1

        tx_payload = {
            "type": "transfer",
            "sender": sender,
            "receiver": receiver,
            "amount": str(transfer_amount),
            "fee": str(tx_fee),
            "nonce": next_nonce,
            "ts": time.time_ns(),
        }
        public_key, signature = self._sign_payload(sender, tx_payload)
        if sender_state.public_key != public_key:
            return "Error: La llave pública no coincide con la cuenta emisora."
        if not self._verify_signature(public_key, tx_payload, signature):
            return "Error: Firma digital inválida en transferencia."

        sender_state.balance -= total_cost
        sender_state.nonce = next_nonce
        receiver_state.balance += transfer_amount
        self.validator_pool += tx_fee

        tx_id = self._build_tx_id(tx_payload)

        tx_record = AccountTransaction(
            tx_id=tx_id,
            sender=sender,
            receiver=receiver,
            amount=transfer_amount,
            fee=tx_fee,
            nonce=sender_state.nonce,
            status="PENDING",
            timestamp=self._timestamp(),
            signer_public_key=public_key,
            signature=signature,
        )
        self.transaction_history.append(tx_record)
        self.tx_index[tx_id] = tx_record
        self.pending_tx_ids.append(tx_id)

        return (
            f"Transacción aceptada en mempool: {transfer_amount} de {sender} a {receiver}. "
            f"Fee={tx_fee}. Nonce={sender_state.nonce}."
        )

    def mine_block(self, miner):
        if not self._is_valid_address(miner):
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

    def register_lot(self, lot_id, owner, product, origin):
        if lot_id in self.lots:
            return "Error: El lote ya existe."
        if not all(
            [
                self._is_valid_address(lot_id),
                self._is_valid_address(owner),
                self._is_valid_address(product),
                self._is_valid_address(origin),
            ]
        ):
            return "Error: Datos inválidos para lote."

        if owner not in self.accounts:
            self.create_account(owner, 0)

        self.lots[lot_id] = TraceabilityLot(
            lot_id=lot_id,
            product=product,
            origin=origin,
            owner=owner,
            created_at=self._timestamp(),
            certificate_ids=[],
            event_ids=[],
        )
        return f"Lote {lot_id} registrado para {owner}."

    def issue_certificate(self, lot_id, cert_type, issuer, valid_days=365, metadata=None):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."
        if not self._is_valid_address(cert_type) or not self._is_valid_address(issuer):
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
        document_hash = self._build_tx_id(doc_payload)
        certificate_id = f"CERT-{document_hash[:12]}"

        cert = CertificateRecord(
            certificate_id=certificate_id,
            lot_id=lot_id,
            cert_type=cert_type,
            issuer=issuer,
            document_hash=document_hash,
            issued_at=issued_at,
            valid_until=valid_until,
        )
        self.certificates[certificate_id] = cert
        lot.certificate_ids.append(certificate_id)
        return f"Certificado {certificate_id} emitido para lote {lot_id}."

    def record_logistics_event(self, lot_id, event_type, actor, location, metadata=None):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."

        if not all(
            [
                self._is_valid_address(event_type),
                self._is_valid_address(actor),
                self._is_valid_address(location),
            ]
        ):
            return "Error: Datos inválidos para evento logístico."

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
        return f"Evento {event_type} registrado para lote {lot_id}."

    def transfer_lot(self, lot_id, sender, receiver):
        lot = self.lots.get(lot_id)
        if lot is None:
            return "Error: Lote no encontrado."
        if lot.owner != sender:
            return "Error: El sender no es propietario del lote."
        if not self._is_valid_address(receiver):
            return "Error: Receiver inválido."

        if receiver not in self.accounts:
            self.create_account(receiver, 0)

        lot.owner = receiver
        return f"Lote {lot_id} transferido de {sender} a {receiver}."

    def audit_compliance(self, lot_id):
        lot = self.lots.get(lot_id)
        if lot is None:
            return {"status": "FAIL", "reason": "Lote no encontrado"}

        events = [self.logistics_events[eid] for eid in lot.event_ids]
        event_types = {event.event_type for event in events}
        required_events = {"COSECHA", "PROCESAMIENTO", "EXPORTACION"}
        has_required_events = required_events.issubset(event_types)

        active_certificates = []
        now = datetime.now(timezone.utc)
        for cert_id in lot.certificate_ids:
            cert = self.certificates.get(cert_id)
            if cert is None or cert.revoked:
                continue
            if datetime.fromisoformat(cert.valid_until) >= now:
                active_certificates.append(cert)

        compliant = has_required_events and len(active_certificates) > 0
        lot.compliance_status = "PASS" if compliant else "FAIL"

        return {
            "lot_id": lot_id,
            "status": lot.compliance_status,
            "has_required_events": has_required_events,
            "active_certificates": len(active_certificates),
            "owner": lot.owner,
        }

    def get_balance(self, address):
        if address not in self.accounts:
            return Decimal("0")
        return self.accounts[address].balance

    def state_snapshot(self):
        return {address: asdict(state) for address, state in self.accounts.items()}

    def ledger_snapshot(self):
        return [asdict(tx) for tx in self.transaction_history]


if __name__ == "__main__":
    print("\n--- SISTEMA DE MODELO DE CUENTAS - ITERACION 2 ---")
    agro_eth = AccountBased_Blockchain(confirmations_required=2, max_txs_per_block=5)
    print(agro_eth.create_wallet("Exportador_Colombia")[0])
    print(agro_eth.create_wallet("Logistica_Latam")[0])
    print(agro_eth.create_wallet("Aduana_Pacifico")[0])
    print(agro_eth.create_account("Exportador_Colombia", 100))
    print(agro_eth.create_account("Logistica_Latam", 0))
    print(agro_eth.register_lot("Lote_Cafe_001", "Exportador_Colombia", "Cafe Arabe", "Huila_Colombia"))
    print(agro_eth.issue_certificate("Lote_Cafe_001", "Fitosanitario", "ICA"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "COSECHA", "Cooperativa_Huila", "Finca_El_Roble"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "PROCESAMIENTO", "Planta_Trillado", "Neiva"))

    status_1 = agro_eth.send_transaction(
        "Exportador_Colombia", "Logistica_Latam", 30, fee=0.15, expected_nonce=0
    )
    print(status_1)

    status_2 = agro_eth.send_transaction(
        "Exportador_Colombia", "Aduana_Pacifico", 20, fee=0.10, expected_nonce=1
    )
    print(status_2)
    print(agro_eth.mine_block("Nodo_Validador_1"))
    print(agro_eth.record_logistics_event("Lote_Cafe_001", "EXPORTACION", "Puerto_Buenaventura", "Buenaventura"))
    print(agro_eth.mine_block("Nodo_Validador_2"))
    print(agro_eth.transfer_lot("Lote_Cafe_001", "Exportador_Colombia", "Aduana_Pacifico"))
    print("Auditoria compliance:", agro_eth.audit_compliance("Lote_Cafe_001"))

    print("Balance Exportador:", agro_eth.get_balance("Exportador_Colombia"))
    print("Balance Logistica:", agro_eth.get_balance("Logistica_Latam"))
    print("Balance Aduana:", agro_eth.get_balance("Aduana_Pacifico"))
    print("Altura cadena:", len(agro_eth.blocks) - 1)
    print("Pool de validadores:", agro_eth.validator_pool)
    print("Estado final:", agro_eth.state_snapshot())