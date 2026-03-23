from __future__ import annotations

from typing import Optional

from twilio.rest import Client

from app.config import get_settings


def get_twilio_client() -> Optional[Client]:
    s = get_settings()
    if not s.twilio_account_sid or not s.twilio_auth_token:
        return None
    return Client(s.twilio_account_sid, s.twilio_auth_token)

