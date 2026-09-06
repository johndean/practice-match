"""Runtime settings. Every required variable is read once at import; a missing one
exits the process naming it, so a misconfigured deploy fails at boot, not on the
first request."""
from __future__ import annotations

import sys

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    environment: str  # qa | production | test
    api_secret_key: str
    allowed_origins: str = ""
    commit_sha: str = "dev"
    public_indexing: bool = False  # QA leaves this unset (noindex); production runs true — the Coming Soon page is meant to be found
    site_mode: str = "app"  # app | coming_soon — which built site the api serves (spec 2026-09-06)

    @field_validator("site_mode")
    @classmethod
    def _site_mode_known(cls, v: str) -> str:
        if v not in ("app", "coming_soon"):
            raise ValueError("SITE_MODE must be 'app' or 'coming_soon'")
        return v

    @model_validator(mode="after")
    def _qa_never_serves_the_coming_soon_page(self) -> Settings:
        if self.environment == "qa" and self.site_mode == "coming_soon":
            raise ValueError("SITE_MODE=coming_soon is never valid on QA (John, 2026-09-06)")
        return self

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # required fields come from the environment at runtime, not this call site (fix round 1, incidental)
    except ValidationError as exc:
        names = ", ".join(sorted({str(e["loc"][0]).upper() for e in exc.errors()}))
        print(f"[config] missing or invalid environment variables: {names}", file=sys.stderr)
        raise SystemExit(1) from None


settings = load_settings()
