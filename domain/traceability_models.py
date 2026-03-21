from dataclasses import dataclass


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
    required_events: list[str] | None = None
    min_active_certificates: int = 1


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
