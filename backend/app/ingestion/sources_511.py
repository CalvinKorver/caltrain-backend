from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.ingestion.normalizers import NormalizedReport
from app.config import get_settings

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from google.transit import gtfs_realtime_pb2


def _get_first_text(translation_list) -> str:
    try:
        if not translation_list:
            return ""
        # gtfs-realtime-bindings uses `translation` with `.text`
        return str(translation_list[0].text or "")
    except Exception:
        return ""


def _extract_alert_text(alert) -> tuple[str, str]:
    header = _get_first_text(alert.header_text.translation) if alert.HasField("header_text") else ""
    desc = _get_first_text(alert.description_text.translation) if alert.HasField("description_text") else ""

    # Some feeds only populate one of them; fall back to message/cause.
    if not header and alert.HasField("cause"):
        header = str(getattr(alert.cause, "text", "")) or "Service alert"
    if not desc:
        # Last resort: stringify the object.
        desc = ""
    return header.strip(), desc.strip()


def _extract_time_bounds(alert) -> tuple[Optional[datetime], Optional[datetime]]:
    # Prefer active_period entries when present.
    try:
        if not alert.active_period:
            return (None, None)
    except Exception:
        return (None, None)

    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    for period in alert.active_period:
        if period.HasField("start") and start_dt is None:
            start_dt = datetime.fromtimestamp(period.start, tz=timezone.utc)
        if period.HasField("end") and end_dt is None:
            end_dt = datetime.fromtimestamp(period.end, tz=timezone.utc)
    return (start_dt, end_dt)


def _extract_hints(alert) -> tuple[list[str], list[str]]:
    station_hints: list[str] = []
    route_hints: list[str] = []
    # informed_entity is the most useful place for stop/route names.
    try:
        for entity in alert.informed_entity:
            if hasattr(entity, "stop_name") and entity.stop_name:
                station_hints.append(str(entity.stop_name))
            elif hasattr(entity, "stop_id") and entity.stop_id:
                station_hints.append(str(entity.stop_id))

            # Route hints can come from route_id / route_type depending on feed.
            if hasattr(entity, "route_id") and entity.route_id:
                route_hints.append(str(entity.route_id))
            elif hasattr(entity, "route_type") and entity.route_type is not None:
                route_hints.append(str(entity.route_type))
    except Exception:
        pass

    # Stabilize ordering and remove empties.
    station_hints = [s for s in station_hints if s]
    route_hints = [s for s in route_hints if s]
    return (sorted(set(station_hints)), sorted(set(route_hints)))


@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def fetch_511_service_alert_reports() -> list[NormalizedReport]:
    """Fetch and normalize 511 GTFS-RT service alerts (Protocol Buffers)."""
    s = get_settings()
    if not s.sources_511_enabled:
        return []
    if not s.api_511_key:
        return []

    # 511 docs: http://api.511.org/transit/servicealerts?api_key=...&agency=RG
    url = "https://api.511.org/transit/servicealerts"
    params = {"api_key": s.api_511_key, "agency": "RG"}
    now = datetime.now(timezone.utc)

    resp = httpx.get(url, params=params, timeout=20)
    resp.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)

    reports: list[NormalizedReport] = []
    for entity in getattr(feed, "entity", []):
        if not entity.HasField("alert"):
            continue
        alert = entity.alert

        title, desc = _extract_alert_text(alert)
        station_hints, route_hints = _extract_hints(alert)
        start_dt, end_dt = _extract_time_bounds(alert)

        # Stable external id for this alert.
        # If alert.id is missing, fall back to a hash of the extracted fields.
        ext_id = str(alert.id) if getattr(alert, "id", None) else None
        if not ext_id:
            ext_id = str(
                hash(
                    (title, desc, ",".join(station_hints), ",".join(route_hints), start_dt.isoformat() if start_dt else None)
                )
            )

        raw_text_for_model = " ".join(
            [f"TITLE: {title}", f"DESC: {desc}", f"STATIONS: {station_hints}", f"ROUTES: {route_hints}"]
        ).strip()

        reports.append(
            NormalizedReport(
                source_name="511",
                external_id=ext_id,
                fetched_at=now,
                title=title or "Service alert",
                description=desc or title or "Service alert reported.",
                station_hints=station_hints,
                route_hints=route_hints,
                evidence_sources=["511"],
                raw_text_for_model=raw_text_for_model,
            )
        )

    return reports

