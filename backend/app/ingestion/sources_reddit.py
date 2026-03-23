from __future__ import annotations

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
import re

from app.ingestion.normalizers import NormalizedReport
from app.config import get_settings
import praw


_DELAY_KEYWORDS = [
    "delay",
    "late",
    "cancel",
    "canceled",
    "cancellation",
    "cancelled",
    "suspended",
    "no service",
    "stuck",
    "stalled",
    "broken",
    "mechanical",
    "signals",
    "signal",
    "power",
    "train is",
    "stopped",
    "platform",
    "incident",
    "rerouted",
    "detour",
]

_CALTRAIN_STATIONS = [
    "4th & King",
    "4th and King",
    "22nd Street",
    "25th Avenue",
    "San Bruno",
    "South San Francisco",
    "San Mateo",
    "Hayward Park",
    "Burlingame",
    "Millbrae",
    "Redwood City",
    "Palo Alto",
    "Menlo Park",
    "Mountain View",
    "Sunnyvale",
    "Lawrence",
    "San Jose",
    "Santa Clara",
    "San Francisco",
]


def _contains_delay_keywords(text: str) -> bool:
    t = text.lower()
    for kw in _DELAY_KEYWORDS:
        if kw in t:
            return True
    return False


def _extract_station_hints(text: str) -> list[str]:
    hints: list[str] = []
    for st in _CALTRAIN_STATIONS:
        if re.search(rf"\b{re.escape(st)}\b", text, flags=re.IGNORECASE):
            hints.append(st)
    # Also handle ampersand variations.
    if "4th & king" in text.lower() or "4th and king" in text.lower():
        hints.append("4th & King")
    return sorted(set(hints))


def _extract_route_hints(text: str) -> list[str]:
    t = text.lower()
    hints: list[str] = []
    if "baby bullet" in t:
        hints.append("Baby Bullet")
    if "express" in t:
        hints.append("Express")
    if "local" in t:
        hints.append("Local")
    if "sf" in t or "san francisco" in t:
        hints.append("SF")
    if "sj" in t or "san jose" in t:
        hints.append("San Jose")
    return sorted(set(hints))


def _iter_posts(reddit: praw.Reddit, subreddit: str, limit: int) -> Iterable[praw.models.reddit.submission.Submission]:
    sr = reddit.subreddit(subreddit)
    # MVP: check both recent and currently trending.
    yield from sr.new(limit=limit)
    yield from sr.hot(limit=limit)


def fetch_reddit_delay_reports() -> list[NormalizedReport]:
    """Fetch and normalize Reddit delay-related reports via OAuth (praw)."""
    s = get_settings()
    if not s.sources_reddit_enabled:
        return []

    if not (s.reddit_client_id and s.reddit_client_secret and s.reddit_username and s.reddit_password):
        return []

    reddit = praw.Reddit(
        client_id=s.reddit_client_id,
        client_secret=s.reddit_client_secret,
        username=s.reddit_username,
        password=s.reddit_password,
        user_agent=s.reddit_user_agent,
    )

    subreddits = [ss.strip() for ss in (s.reddit_subreddits or "").split(",") if ss.strip()]
    if not subreddits:
        return []

    now = datetime.now(timezone.utc)
    max_age_seconds = max(60, s.poll_reddit_interval_seconds * 3)
    min_created_utc = now.timestamp() - max_age_seconds

    posts_seen: set[str] = set()
    reports: list[NormalizedReport] = []
    limit = max(5, s.reddit_limit)

    for subreddit in subreddits:
        for post in _iter_posts(reddit=reddit, subreddit=subreddit, limit=limit):
            if not getattr(post, "id", None):
                continue
            if post.id in posts_seen:
                continue
            posts_seen.add(post.id)

            created_utc = float(getattr(post, "created_utc", 0.0) or 0.0)
            if created_utc < min_created_utc:
                continue

            title = str(getattr(post, "title", "") or "").strip()
            body = str(getattr(post, "selftext", "") or "").strip()
            text = (title + "\n" + body).strip()
            if not text or not _contains_delay_keywords(text):
                continue

            station_hints = _extract_station_hints(text)
            route_hints = _extract_route_hints(text)

            reports.append(
                NormalizedReport(
                    source_name="reddit",
                    external_id=post.id,
                    fetched_at=now,
                    title=title or "Reddit transit report",
                    description=body or title,
                    station_hints=station_hints,
                    route_hints=route_hints,
                    evidence_sources=["reddit"],
                    raw_text_for_model=" ".join(
                        [
                            f"TITLE: {title}",
                            f"BODY: {body[:1000]}",
                            f"STATIONS: {station_hints}",
                            f"ROUTES: {route_hints}",
                        ]
                    ).strip(),
                )
            )

    return reports

