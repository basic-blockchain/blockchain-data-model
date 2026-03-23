"""
Base class for UTXO and Account-based blockchain models.
Contains shared infrastructure: blocks, wallets, signing, mining, compliance.
"""
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

from domain.compliance import DEFAULT_COMPLIANCE_PROFILES, evaluate_compliance, resolve_profile
from domain.precision import UNIT, normalize_amount  # noqa: F401 — re-exported
from domain.traceability_models import CertificateRecord, LogisticsEvent, TraceabilityLot


@dataclass
class WalletKeys:
    address: str
    public_key: str
    private_key: str
    created_at: str


@dataclass
class Block:
    height: int
    previous_hash: str
    block_hash: str
    tx_ids: list[str]
    mined_by: str
    timestamp: str


class BaseBlockchain:
    """Shared blockchain infrastructure for both UTXO and Account-based models."""

    def __init__(self, confirmations_required: int = 2, max_txs_per_block: int = 10):
        self.transaction_history: list = []
        self.tx_index: dict = {}
        self.pending_tx_ids: list[str] = []
        self.validator_pool: Decimal = Decimal("0")
        self.wallets: dict[str, WalletKeys] = {}
        self.blocks: list[Block] = []
        self.confirmations_required: int = confirmations_required
        self.max_txs_per_block: int = max_txs_per_block
        self.lots: dict[str, TraceabilityLot] = {}
        self.certificates: dict[str, CertificateRecord] = {}
        self.logistics_events: dict[str, LogisticsEvent] = {}
        self.compliance_profiles: dict = dict(DEFAULT_COMPLIANCE_PROFILES)
        self._create_genesis_block()

    # ------------------------------------------------------------------
    # Timestamps & hashing
    # ------------------------------------------------------------------

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _build_tx_id(self, payload: dict) -> str:
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    def _block_hash(self, payload: dict) -> str:
        canonical_payload = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical_payload.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Genesis block
    # ------------------------------------------------------------------

    def _create_genesis_block(self) -> None:
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

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_participant(self, participant: str) -> bool:
        return isinstance(participant, str) and participant.strip() != ""

    # Alias used by AccountBased_Blockchain for backward compatibility.
    _is_valid_address = _validate_participant

    # ------------------------------------------------------------------
    # Wallet management
    # ------------------------------------------------------------------

    def create_wallet(self, address: str) -> tuple[str, WalletKeys | None]:
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

    def _ensure_wallet(self, address: str) -> WalletKeys:
        if address not in self.wallets:
            self.create_wallet(address)
        return self.wallets[address]

    # ------------------------------------------------------------------
    # Signing & verification
    # ------------------------------------------------------------------

    def _sign_payload(self, address: str, payload: dict) -> tuple[str, str]:
        wallet = self._ensure_wallet(address)
        message = json.dumps(payload, sort_keys=True)
        signature = hashlib.sha256(f"{wallet.private_key}:{message}".encode()).hexdigest()
        return wallet.public_key, signature

    def _verify_signature(self, public_key: str, payload: dict, signature: str) -> bool:
        for wallet in self.wallets.values():
            if wallet.public_key != public_key:
                continue
            message = json.dumps(payload, sort_keys=True)
            expected = hashlib.sha256(f"{wallet.private_key}:{message}".encode()).hexdigest()
            return expected == signature
        return False

    # ------------------------------------------------------------------
    # Mining & confirmations
    # ------------------------------------------------------------------

    def mine_block(self, miner: str) -> str:
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

    def _refresh_confirmations(self) -> None:
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

    # ------------------------------------------------------------------
    # Compliance profiles
    # ------------------------------------------------------------------

    def configure_compliance_profile(
        self, profile_name: str, required_events: list[str], min_active_certificates: int = 1
    ) -> str:
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

    # ------------------------------------------------------------------
    # Certificates
    # ------------------------------------------------------------------

    def issue_certificate(
        self, lot_id: str, cert_type: str, issuer: str, valid_days: int = 365, metadata: dict | None = None
    ) -> str:
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

    # ------------------------------------------------------------------
    # Logistics events
    # ------------------------------------------------------------------

    def record_logistics_event(
        self, lot_id: str, event_type: str, actor: str, location: str, metadata: dict | None = None
    ) -> str:
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

    # ------------------------------------------------------------------
    # Compliance audit
    # ------------------------------------------------------------------

    def audit_compliance(self, lot_id: str) -> dict:
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

    # ------------------------------------------------------------------
    # Ledger snapshot
    # ------------------------------------------------------------------

    def ledger_snapshot(self) -> list[dict]:
        return [asdict(tx) for tx in self.transaction_history]
