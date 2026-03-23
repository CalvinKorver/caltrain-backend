from __future__ import annotations

from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.models import RawReport, Incident, Classification, Subscriber, SendLog
from app.db.session import session_scope
from app.ingestion.sources_511 import fetch_511_service_alert_reports
from app.ingestion.sources_reddit import fetch_reddit_delay_reports
from app.ingestion.normalizers import NormalizedReport
from app.intelligence.claude_classifier import classify_severity
from app.intelligence.dedup import upsert_incident
from app.notifications.send_sms import send_sms


SEVERITY_RANK = {"NO_ALERT": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}


def _normalized_report_to_payload(r: NormalizedReport) -> dict:
    return {
        "title": r.title,
        "description": r.description,
        "station_hints": r.station_hints,
        "route_hints": r.route_hints,
        "evidence_sources": r.evidence_sources,
        "raw_text_for_model": r.raw_text_for_model,
    }


@shared_task(name="app.tasks.poll_tasks.poll_511")
def poll_511() -> int:
    reports = fetch_511_service_alert_reports()
    if not reports:
        return 0

    created_ids: list[int] = []
    with session_scope() as db:
        for r in reports:
            payload = _normalized_report_to_payload(r)
            exists = db.execute(
                select(RawReport.id).where(
                    RawReport.source_name == r.source_name,
                    RawReport.external_id == r.external_id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            rr = RawReport(
                    source_name=r.source_name,
                    external_id=r.external_id,
                    fetched_at=r.fetched_at,
                    payload=payload,
                )
            db.add(rr)
            db.flush()  # populate rr.id
            created_ids.append(rr.id)

    for raw_report_id in created_ids:
        handle_raw_report.delay(raw_report_id)

    return len(created_ids)


@shared_task(name="app.tasks.poll_tasks.poll_reddit")
def poll_reddit() -> int:
    reports = fetch_reddit_delay_reports()
    if not reports:
        return 0

    created_ids: list[int] = []
    with session_scope() as db:
        for r in reports:
            payload = _normalized_report_to_payload(r)
            exists = db.execute(
                select(RawReport.id).where(
                    RawReport.source_name == r.source_name,
                    RawReport.external_id == r.external_id,
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            rr = RawReport(
                    source_name=r.source_name,
                    external_id=r.external_id,
                    fetched_at=r.fetched_at,
                    payload=payload,
                )
            db.add(rr)
            db.flush()
            created_ids.append(rr.id)

    for raw_report_id in created_ids:
        handle_raw_report.delay(raw_report_id)

    return len(created_ids)


@shared_task(name="app.tasks.poll_tasks.handle_raw_report")
def handle_raw_report(raw_report_id: int) -> None:
    s = get_settings()
    with session_scope() as db:
        raw = db.execute(select(RawReport).where(RawReport.id == raw_report_id)).scalar_one_or_none()
        if not raw:
            return

        payload = raw.payload or {}
        normalized = NormalizedReport(
            source_name=raw.source_name,
            external_id=raw.external_id,
            fetched_at=raw.fetched_at,
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            station_hints=list(payload.get("station_hints") or []),
            route_hints=list(payload.get("route_hints") or []),
            evidence_sources=list(payload.get("evidence_sources") or [raw.source_name]),
            raw_text_for_model=str(payload.get("raw_text_for_model") or f"{payload.get('title','')} {payload.get('description','')}").strip(),
        )

        now = datetime.now(timezone.utc)
        incident = upsert_incident(
            db=db,
            report=normalized,
            dedup_window_minutes=s.incident_dedup_window_minutes,
        )

        raw.incident_id = incident.id

        # Classify once per incident fingerprint.
        existing_class = db.execute(
            select(Classification).where(Classification.incident_id == incident.id)
        ).scalar_one_or_none()
        if existing_class is None:
            try:
                result = classify_severity(
                    report_text=normalized.raw_text_for_model or normalized.description,
                    source_evidence=normalized.evidence_sources,
                )
                existing_class = Classification(
                    incident_id=incident.id,
                    severity=result.severity,
                    title=result.title[:256],
                    message=result.message[:2048],
                    evidence_sources=result.evidence_sources,
                    model=s.anthropic_model,
                    raw_output=result.raw_output,
                )
                db.add(existing_class)
                db.flush()
            except IntegrityError:
                db.rollback()
                existing_class = db.execute(
                    select(Classification).where(Classification.incident_id == incident.id)
                ).scalar_one()

        severity = existing_class.severity
        threshold_rank = SEVERITY_RANK.get(str(s.send_min_severity).upper(), 3)
        if SEVERITY_RANK.get(severity, 0) < threshold_rank:
            return

        # Notify subscribers, avoiding spam with cooldown.
        cooldown = timedelta(minutes=s.subscriber_send_cooldown_minutes)
        cutoff = now - cooldown

        subscribers = db.execute(select(Subscriber).where(Subscriber.is_active.is_(True))).scalars().all()

        for sub in subscribers:
            already_sent = db.execute(
                select(SendLog.id).where(
                    SendLog.incident_id == incident.id,
                    SendLog.subscriber_id == sub.id,
                )
            ).scalar_one_or_none()
            if already_sent is not None:
                continue

            recent_sent = db.execute(
                select(SendLog.id)
                .where(SendLog.subscriber_id == sub.id, SendLog.sent_at >= cutoff)
                .order_by(SendLog.sent_at.desc())
            ).first()
            if recent_sent is not None:
                continue

            ok = send_sms(
                to_phone=sub.phone_number,
                severity=existing_class.severity,
                title=existing_class.title,
                message=existing_class.message,
            )
            if not ok:
                continue

            db.add(
                SendLog(
                    incident_id=incident.id,
                    subscriber_id=sub.id,
                    sent_at=now,
                    severity=existing_class.severity,
                    message=existing_class.message[:2048],
                )
            )

