from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator, AliasChoices
from urllib.parse import quote
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development")
    database_url: str = Field(default="postgresql+psycopg2://postgres:postgres@localhost:5432/caltrain_alerts")
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_public_url: Optional[str] = Field(default=None, validation_alias="REDIS_PUBLIC_URL")

    # Railway managed Redis often exposes pieces with these exact names.
    redis_host: Optional[str] = Field(default=None, validation_alias=AliasChoices("REDIS_HOST", "REDISHOST"))
    redis_port: int = Field(default=6379, validation_alias=AliasChoices("REDIS_PORT", "REDISPORT"))
    redis_user: Optional[str] = Field(default=None, validation_alias=AliasChoices("REDIS_USER", "REDISUSER"))
    redis_password: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("REDIS_PASSWORD", "REDISPASSWORD")
    )
    redis_db: int = Field(default=0, validation_alias=AliasChoices("REDIS_DB", "REDISDB"))

    # If using `REDIS_HOST` pieces, set this to match the scheme (rediss:// vs redis://).
    redis_tls: bool = Field(default=False, validation_alias=AliasChoices("REDIS_TLS"))

    # Sources toggles
    sources_511_enabled: bool = Field(default=True)
    sources_reddit_enabled: bool = Field(default=True)

    api_511_key: Optional[str] = Field(default=None)

    # Reddit / praw
    reddit_client_id: Optional[str] = Field(default=None)
    reddit_client_secret: Optional[str] = Field(default=None)
    reddit_username: Optional[str] = Field(default=None)
    reddit_password: Optional[str] = Field(default=None)
    reddit_user_agent: str = Field(default="caltrain-alerts-mvp/0.1")
    reddit_subreddits: str = Field(default="caltrain,bayarea")
    reddit_limit: int = Field(default=20)

    # Anthropic
    anthropic_api_key: Optional[str] = Field(default=None)
    anthropic_model: str = Field(default="claude-3-5-haiku-latest")

    # Claude classification / behavior
    send_min_severity: str = Field(default="CRITICAL")
    incident_dedup_window_minutes: int = Field(default=10)
    subscriber_send_cooldown_minutes: int = Field(default=60)

    # Twilio
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    twilio_from_number: Optional[str] = Field(default=None)
    sms_template: str = Field(
        default="Caltrain alert ({{severity}}): {{title}}\n{{message}}"
    )

    # Polling
    poll_511_interval_seconds: int = Field(default=60)
    poll_reddit_interval_seconds: int = Field(default=120)

    # Admin (optional)
    admin_api_key: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def _build_redis_url_from_parts(self) -> "Settings":
        """
        Railway often provides either a full `REDIS_URL` or connection pieces.
        If `redis_host` is set, we build the URL from the parts.
        """
        default_url = "redis://localhost:6379/0"

        # If Railway provides `REDIS_PUBLIC_URL` and you didn't override `REDIS_URL`,
        # use the public URL by default (common for managed Redis connectivity).
        if self.redis_public_url and (not self.redis_url or self.redis_url == default_url):
            self.redis_url = self.redis_public_url

        # Auto-detect TLS scheme from provided URLs.
        if (self.redis_public_url and self.redis_public_url.startswith("rediss://")) or (
            self.redis_url and self.redis_url.startswith("rediss://")
        ):
            self.redis_tls = True

        if self.redis_host:
            scheme = "rediss" if self.redis_tls else "redis"
            password = quote(self.redis_password) if self.redis_password else ""
            if self.redis_user:
                user = quote(self.redis_user)
                auth = f"{user}:{password}@" if password else f"{user}@"
            else:
                auth = f":{password}@" if password else ""
            self.redis_url = f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return self


def get_settings() -> Settings:
    return Settings()  # reads from env

