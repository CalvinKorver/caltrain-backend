from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.notifications.twilio_client import get_twilio_client


@dataclass(frozen=True)
class SmsPayload:
    to_phone: str
    body: str


def render_sms_template(severity: str, title: str, message: str) -> str:
    s = get_settings()
    return s.sms_template.replace("{{severity}}", severity).replace("{{title}}", title).replace(
        "{{message}}", message
    )


def send_sms(to_phone: str, severity: str, title: str, message: str) -> bool:
    """
    Send an SMS via Twilio. Returns True on success.
    """
    s = get_settings()
    if not (s.twilio_from_number and s.twilio_account_sid and s.twilio_auth_token):
        return False

    client = get_twilio_client()
    if not client:
        return False

    body = render_sms_template(severity=severity, title=title, message=message)
    # Twilio expects E.164 formatting in most cases; caller should enforce.
    msg = client.messages.create(
        to=to_phone,
        from_=s.twilio_from_number,
        body=body,
    )
    return bool(getattr(msg, "sid", None))

