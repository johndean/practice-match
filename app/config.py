"""Runtime settings. Every required variable is read once at import; a missing one
exits the process naming it, so a misconfigured deploy fails at boot, not on the
first request."""
from __future__ import annotations

import sys

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    redis_url: str
    environment: str  # qa | production | test
    api_secret_key: str
    allowed_origins: str = ""
    commit_sha: str = "dev"
    public_indexing: bool = False  # flip to true at launch; until then every response is noindex

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        names = ", ".join(sorted({str(e["loc"][0]).upper() for e in exc.errors()}))
        print(f"[config] missing or invalid environment variables: {names}", file=sys.stderr)
        raise SystemExit(1) from None


settings = load_settings()
