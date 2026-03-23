from __future__ import annotations

from fastapi import FastAPI
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.config import get_settings
from app.db.session import session_scope
from app.db.models import Subscriber

app = FastAPI(title="caltrain-alerts")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    # Fail fast if settings are missing.
    s = get_settings()
    return {"status": "ok", "environment": s.environment}


class SubscriberCreate(BaseModel):
    phone_number: str = Field(..., description="Phone number in E.164 format (+1415...) preferred.")
    route_preferences: dict = Field(default_factory=dict)
    is_active: bool = Field(default=True)


def _require_admin(x_admin_token: Optional[str]) -> None:
    s = get_settings()
    if s.admin_api_key and x_admin_token != s.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/admin/subscribers")
def create_or_update_subscriber(
    sub: SubscriberCreate,
    x_admin_token: Optional[str] = Header(default=None, convert_underscores=False),
) -> dict:
    _require_admin(x_admin_token)
    with session_scope() as db:
        existing = db.query(Subscriber).filter(Subscriber.phone_number == sub.phone_number).one_or_none()
        if existing is None:
            existing = Subscriber(
                phone_number=sub.phone_number,
                route_preferences=sub.route_preferences or {},
                is_active=sub.is_active,
            )
            db.add(existing)
            db.flush()
        else:
            existing.route_preferences = sub.route_preferences or {}
            existing.is_active = sub.is_active

        return {"id": existing.id, "phone_number": existing.phone_number, "is_active": existing.is_active}


@app.get("/admin/subscribers")
def list_subscribers(
    x_admin_token: Optional[str] = Header(default=None, convert_underscores=False),
) -> list[dict]:
    _require_admin(x_admin_token)
    with session_scope() as db:
        subs = db.query(Subscriber).order_by(Subscriber.id.desc()).all()
        return [
            {"id": s.id, "phone_number": s.phone_number, "is_active": s.is_active, "route_preferences": s.route_preferences}
            for s in subs
        ]

