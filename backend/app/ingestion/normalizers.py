from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class NormalizedReport:
    # Common shape for all sources.
    source_name: str  # e.g. "511"
    external_id: str  # unique per source item
    fetched_at: datetime

    title: str
    description: str

    # Cues for dedup/classification/routing.
    station_hints: list[str] = field(default_factory=list)
    route_hints: list[str] = field(default_factory=list)

    # Evidence for classification.
    evidence_sources: list[str] = field(default_factory=list)
    raw_text_for_model: str = ""

