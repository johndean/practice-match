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
    hibp_enabled: bool = True  # Have I Been Pwned k-anonymity check on password change; falls back to the bundled offline list on any error
    market_data_public: bool = False  # anonymous visitors gain permissions.MATRIX["market.read"] only while true — QA evaluation only (spec's MARKET_DATA_PUBLIC), never production
    consolidator_keywords: str = ""  # comma-separated employer-domain keywords (VIN Foundation-supplied); an application-review hint only, never a decision (spec §6)
    link_base_url: str = "https://qa.foundation.vin"  # origin the verify/reset links in transactional email point at; production sets https://foundation.vin
    # Comma-separated WHOLE ADDRESSES (not domains) transactional email may be delivered to outside
    # production. Fail-closed: an EMPTY list on QA delivers to nobody — every row is recorded
    # `suppressed` — which is what stops a QA sign-up emailing a real person. Ignored on production
    # (spec §5 QA safety; Task I6, comment corrected in fix round 1 F5).
    email_allowlist: str = ""
    # Resend (Task I6). The two secrets are set only in Railway — `RESEND_API_KEY` on the worker
    # (the only service that sends) and `RESEND_WEBHOOK_SECRET` on the api (the only service that
    # receives) — so each service boots with the other one unset, which is why both are optional
    # here rather than required: a missing key is refused at the moment it is USED, naming itself
    # (`app.mail.tasks.send_due`, `app.api.webhooks`), not at import on a service that never needs it.
    resend_api_key: str | None = None
    resend_webhook_secret: str | None = None
    mail_from: str = "VIN Foundation — Practice Match <no-reply@foundation.vin>"  # spec §2: foundation.vin is the SENDER domain
    mail_reply_to: str = "practicematch@vin.com"  # placeholder until the VIN Foundation names the mailbox (spec §10 open item)
    db_pool_max: int = 10  # size of the psycopg2 REUSE pool per DSN (app/db.py); past it a caller gets an un-pooled connection, so this does not cap the connection count

    @field_validator("site_mode")
    @classmethod
    def _site_mode_known(cls, v: str) -> str:
        if v not in ("app", "coming_soon"):
            raise ValueError("SITE_MODE must be 'app' or 'coming_soon'")
        return v

    @model_validator(mode="after")
    def _qa_never_serves_the_coming_soon_page(self) -> Settings:
        if self.environment.lower() == "qa" and self.site_mode == "coming_soon":
            raise ValueError("SITE_MODE=coming_soon is never valid on QA (John, 2026-09-06)")
        return self

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]  # required fields come from the environment at runtime, not this call site (fix round 1, incidental)
    except ValidationError as exc:
        names = ", ".join(sorted({str(e["loc"][0]).upper() if e["loc"] else e["msg"] for e in exc.errors()}))
        print(f"[config] missing or invalid environment variables: {names}", file=sys.stderr)
        raise SystemExit(1) from None


settings = load_settings()
