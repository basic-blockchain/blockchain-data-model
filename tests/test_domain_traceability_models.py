from domain.traceability_models import (
    CertificateRecord,
    LogisticsEvent,
    TraceabilityLot,
)


def test_traceability_lot_defaults():
    lot = TraceabilityLot(
        lot_id="LOT-1",
        product="CAFE",
        origin="HUILA",
        owner="owner",
        created_at="2026-03-20T00:00:00+00:00",
        certificate_ids=[],
        event_ids=[],
    )

    assert lot.compliance_status == "PENDING"
    assert lot.min_active_certificates == 1


def test_certificate_and_event_models():
    cert = CertificateRecord(
        certificate_id="CERT-1",
        lot_id="LOT-1",
        cert_type="Fitosanitario",
        issuer="ICA",
        document_hash="abc",
        issued_at="2026-03-20T00:00:00+00:00",
        valid_until="2027-03-20T00:00:00+00:00",
    )

    event = LogisticsEvent(
        event_id="EVT-1",
        lot_id="LOT-1",
        event_type="COSECHA",
        actor="Finca",
        location="Huila",
        timestamp="2026-03-20T00:00:00+00:00",
        metadata={"note": "ok"},
    )

    assert cert.revoked is False
    assert event.metadata["note"] == "ok"
