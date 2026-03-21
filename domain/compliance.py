from datetime import datetime, timezone


DEFAULT_COMPLIANCE_PROFILES = {
    "DEFAULT": {
        "required_events": ["COSECHA", "PROCESAMIENTO", "EXPORTACION"],
        "min_active_certificates": 1,
    },
    "CAFE": {
        "required_events": ["COSECHA", "PROCESAMIENTO", "EXPORTACION"],
        "min_active_certificates": 1,
    },
    "CACAO": {
        "required_events": ["COSECHA", "FERMENTACION", "EXPORTACION"],
        "min_active_certificates": 1,
    },
}


def resolve_profile(product, custom_profiles=None):
    profiles = dict(DEFAULT_COMPLIANCE_PROFILES)
    if custom_profiles:
        profiles.update(custom_profiles)

    key = str(product).strip().upper()
    return profiles.get(key, profiles["DEFAULT"])


def evaluate_compliance(lot, certificates, logistics_events):
    event_types = {
        logistics_events[event_id].event_type
        for event_id in lot.event_ids
        if event_id in logistics_events
    }
    required_events = set(lot.required_events or DEFAULT_COMPLIANCE_PROFILES["DEFAULT"]["required_events"])
    has_required_events = required_events.issubset(event_types)

    active_certificates = 0
    now = datetime.now(timezone.utc)
    for cert_id in lot.certificate_ids:
        cert = certificates.get(cert_id)
        if cert is None or cert.revoked:
            continue
        if datetime.fromisoformat(cert.valid_until) >= now:
            active_certificates += 1

    compliant = has_required_events and active_certificates >= lot.min_active_certificates
    return {
        "status": "PASS" if compliant else "FAIL",
        "has_required_events": has_required_events,
        "active_certificates": active_certificates,
        "required_events": sorted(required_events),
        "min_active_certificates": lot.min_active_certificates,
    }
