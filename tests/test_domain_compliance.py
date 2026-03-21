from datetime import datetime, timedelta, timezone

from domain.compliance import evaluate_compliance, resolve_profile
from domain.traceability_models import CertificateRecord, LogisticsEvent, TraceabilityLot


def test_resolve_profile_cacao():
    profile = resolve_profile("CACAO")
    assert "FERMENTACION" in profile["required_events"]


def test_evaluate_compliance_pass():
    lot = TraceabilityLot(
        lot_id="LOT-1",
        product="CAFE",
        origin="HUILA",
        owner="owner",
        created_at="2026-03-20T00:00:00+00:00",
        certificate_ids=["CERT-1"],
        event_ids=["E1", "E2", "E3"],
        required_events=["COSECHA", "PROCESAMIENTO", "EXPORTACION"],
        min_active_certificates=1,
    )

    cert = CertificateRecord(
        certificate_id="CERT-1",
        lot_id="LOT-1",
        cert_type="Fitosanitario",
        issuer="ICA",
        document_hash="hash",
        issued_at="2026-03-20T00:00:00+00:00",
        valid_until=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    )

    events = {
        "E1": LogisticsEvent("E1", "LOT-1", "COSECHA", "A", "L1", "t", {}),
        "E2": LogisticsEvent("E2", "LOT-1", "PROCESAMIENTO", "B", "L2", "t", {}),
        "E3": LogisticsEvent("E3", "LOT-1", "EXPORTACION", "C", "L3", "t", {}),
    }

    report = evaluate_compliance(lot, {"CERT-1": cert}, events)
    assert report["status"] == "PASS"
    assert report["active_certificates"] == 1


def test_evaluate_compliance_fail_missing_event():
    lot = TraceabilityLot(
        lot_id="LOT-2",
        product="CACAO",
        origin="TUMACO",
        owner="owner",
        created_at="2026-03-20T00:00:00+00:00",
        certificate_ids=[],
        event_ids=["E1"],
        required_events=["COSECHA", "FERMENTACION", "EXPORTACION"],
        min_active_certificates=1,
    )

    events = {
        "E1": LogisticsEvent("E1", "LOT-2", "COSECHA", "A", "L1", "t", {}),
    }

    report = evaluate_compliance(lot, {}, events)
    assert report["status"] == "FAIL"
    assert report["has_required_events"] is False
