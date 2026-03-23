from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Integer, UniqueConstraint, Index, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    pass


class RawReport(Base):
    __tablename__ = "raw_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    incident_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("incidents.id"), nullable=True, index=True
    )
    incident: Mapped["Incident"] = relationship(back_populates="raw_reports", lazy="joined")

    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_raw_reports_source_external"),
        Index("ix_raw_reports_source_external", "source_name", "external_id"),
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    canonical_title: Mapped[str] = mapped_column(String(256), nullable=False)
    canonical_message: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Simple denormalized routing cues for future filtering.
    station_hints: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    route_hints: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    raw_reports: Mapped[list["RawReport"]] = relationship(back_populates="incident", lazy="selectin")
    classifications: Mapped[list["Classification"]] = relationship(back_populates="incident", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_incidents_fingerprint"),
    )


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True, unique=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_sources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    incident: Mapped["Incident"] = relationship(back_populates="classifications", lazy="joined")

    __table_args__ = (
        Index("ix_classifications_severity", "severity"),
    )


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    route_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class SendLog(Base):
    __tablename__ = "send_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id"), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)

    __table_args__ = (
        UniqueConstraint("incident_id", "subscriber_id", name="uq_send_log_incident_subscriber"),
    )

