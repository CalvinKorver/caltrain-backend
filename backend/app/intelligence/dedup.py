from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.ingestion.normalizers import NormalizedReport

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Incident


_KEYWORDS = [
    "delay",
    "cancel",
    "canceled",
    "cancellation",
    "suspended",
    "no service",
    "no-service",
    "breakdown",
    "stuck",
    "stopped",
    "issue",
    "incident",
    "signal",
    "power",
    "mechanical",
    "outage",
]


def _floor_to_window(dt: datetime, window_minutes: int) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    bucket_seconds = window_minutes * 60
    ts = int(dt.timestamp())
    floored = ts - (ts % bucket_seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def extract_keyword_signature(report_text: str) -> str:
    text = report_text.lower()
    hits = [kw for kw in _KEYWORDS if kw in text]
    # Keep stable order while removing duplicates.
    unique_hits = []
    for h in hits:
        if h not in unique_hits:
            unique_hits.append(h)
    return ",".join(unique_hits)[:256]


def compute_incident_fingerprint(report: NormalizedReport, dedup_window_minutes: int) -> str:
    """
    Deterministic fingerprint: time bucket + station/route hints + keyword signature.
    This is intentionally simple for the MVP.
    """
    bucket = _floor_to_window(report.fetched_at, dedup_window_minutes).isoformat()
    station_key = ",".join(sorted(report.station_hints))[:256]
    route_key = ",".join(sorted(report.route_hints))[:256]
    kw_key = extract_keyword_signature(report.raw_text_for_model)

    raw = f"{bucket}|{station_key}|{route_key}|{kw_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_incident_from_report(incident: Incident, report: NormalizedReport, now: datetime) -> Incident:
    """Merge new report evidence into an existing incident row."""
    incident.last_seen_at = now

    # Enrich routing/cue hints.
    incident.station_hints = sorted(set(incident.station_hints or []) | set(report.station_hints or []))
    incident.route_hints = sorted(set(incident.route_hints or []) | set(report.route_hints or []))
    incident.evidence_sources = sorted(
        set(incident.evidence_sources or []) | set(report.evidence_sources or [])
    )

    # Keep canonical text stable but allow enrichment.
    incoming_msg = report.description or report.raw_text_for_model
    if incoming_msg and (not incident.canonical_message or len(incoming_msg) > len(incident.canonical_message)):
        incident.canonical_message = incoming_msg[:2048]
    if report.title and (not incident.canonical_title or incident.canonical_title == "Caltrain alert"):
        incident.canonical_title = report.title[:256]

    return incident


def upsert_incident(
    db: Session,
    report: NormalizedReport,
    dedup_window_minutes: int,
) -> Incident:
    """
    Find or create an incident using deterministic fingerprinting.

    Idempotency: incident fingerprint is unique. On race, re-fetch and merge.
    """
    now = datetime.now(timezone.utc)
    fingerprint = compute_incident_fingerprint(report, dedup_window_minutes)

    incident = db.execute(select(Incident).where(Incident.fingerprint == fingerprint)).scalar_one_or_none()
    if incident is None:
        incident = Incident(
            fingerprint=fingerprint,
            canonical_title=report.title[:256] or "Caltrain alert",
            canonical_message=(report.description or report.raw_text_for_model or "")[:2048],
            last_seen_at=now,
            station_hints=sorted(set(report.station_hints or [])),
            route_hints=sorted(set(report.route_hints or [])),
            evidence_sources=sorted(set(report.evidence_sources or [])),
        )
        try:
            db.add(incident)
            db.flush()  # get id
        except IntegrityError:
            db.rollback()
            incident = db.execute(select(Incident).where(Incident.fingerprint == fingerprint)).scalar_one()
            # Merge after successful re-fetch.
            incident = merge_incident_from_report(incident, report, now)
            db.add(incident)
            db.flush()
    else:
        incident = merge_incident_from_report(incident, report, now)
        db.add(incident)
        db.flush()

    return incident

