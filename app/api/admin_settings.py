"""The Admin > Settings surface (admin control surface spec §2) — the settings-shaped writes that
existed as scattered admin actions with no screen, and the one read behind them.

Three rows today (family A41); a fourth, api tokens, arrives with A46.

* **Market data visible to anonymous visitors is READ-ONLY here, and deliberately** (controller
  decision D1, 2026-09-14). `MARKET_DATA_PUBLIC` is a Railway environment variable
  (`app/config.py`), no route has ever written it, and `scripts/verify-deploy.sh` refuses a
  production deploy where it is true. A button that cannot complete is not drawn (spec §1 rule 3),
  so this row reports the value and says where it is set.
* **Census data vintage is the one NEW write.** `engine.activate` has been a permission with no
  HTTP route since Task I5, reachable only from `scripts/census_load.py activate`. The route below
  delegates to `app.census.vintage.activate` — the CLI's own function, with its own QA gate — so
  there is ONE activation path and not two.
* **Launch mail to sign-ups** reports the counts; the SEND is `admin_signups`'s own
  `POST /api/admin/signups/launch-mail` and is not duplicated here.

Guarded by `data_sources.read`, and `tests/api/test_admin_settings.py` pins
`MATRIX["data_sources.read"] == MATRIX["signups.read"] == MATRIX["page.admin"]` so the day those
three diverge this aggregate read fails loudly instead of serving one row's facts to the holder of
another row's permission (decision D3).

Two shapes `app/api/admin_users.py` documents are load-bearing here too: every guard is a
module-level constant, never wrapped (`tests/auth/test_permissions.py` resolves a route's
permission by the guard's object IDENTITY), and `audit.write(` is called in the audited endpoint's
OWN body (the drift test reads `inspect.getsource(route.endpoint)`).
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.census import vintage as V
from app.config import settings
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

REQUIRE_SETTINGS_READ = require("data_sources.read")
REQUIRE_ACTIVATE = require("engine.activate")
Activator = Annotated[S.Principal, Depends(REQUIRE_ACTIVATE)]

MAX_NOTE = 4_000
#: Where `MARKET_DATA_PUBLIC` is really set — stated, not guessed: it is a Railway environment
#: variable, per service per environment (CLAUDE.md), and this row exists to tell a reader that.
MARKET_FLAG_SOURCE = "Railway environment variable MARKET_DATA_PUBLIC"

VINTAGE_SQL = """
SELECT r.dataset_key, r.display_name,
       a.vintage, a.activated_at, a.activated_by, a.note,
       (SELECT i.vintage FROM ingest_run i
         WHERE i.dataset_key = r.dataset_key AND i.status = 'succeeded'
         ORDER BY i.id DESC LIMIT 1),
       (SELECT i.finished_at FROM ingest_run i
         WHERE i.dataset_key = r.dataset_key AND i.status = 'succeeded'
         ORDER BY i.id DESC LIMIT 1)
  FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key)
 ORDER BY r.dataset_key
"""

SIGNUP_SQL = """
SELECT count(*), count(*) FILTER (WHERE launch_mailed_at IS NOT NULL), max(launch_mailed_at)
  FROM interest_signup
"""


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body, the shape `app/api/admin_data_sources.py` uses."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _vintage_row(r: tuple[Any, ...]) -> dict[str, Any]:
    """One dataset's vintage facts.

    `activatable` is exactly the spec's "only when a newer load exists": a SUCCEEDED load whose
    vintage is not the one already active. It is a hint for the screen and never the gate — the
    route re-asks `vintage.qa` on the way in, so a stale tab cannot force an activation this flag
    would have hidden."""
    loaded = r[6]
    return {"dataset_key": r[0], "display_name": r[1], "active_vintage": r[2],
            "activated_at": _iso(r[3]), "activated_by": r[4], "activation_note": r[5],
            "loaded_vintage": loaded, "last_load_finished_at": _iso(r[7]),
            "activatable": loaded is not None and loaded != r[2]}


@router.get("/settings", dependencies=[Depends(REQUIRE_SETTINGS_READ)])
def read_settings() -> dict[str, Any]:
    """The three Settings rows' live facts.

    A plain `def`, so FastAPI runs it in its threadpool (`admin_data_sources.list_data_sources`'s
    own rule): everything below it is blocking psycopg2, and on the event loop that would park
    every other request for the duration.

    NOT audited: `data_sources.read` is not in `permissions.AUDITED`, and one row per poll of a
    settings screen into a table whose triggers refuse DELETE is the leak `users.review` was split
    out to avoid."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(VINTAGE_SQL)
        vintages = [_vintage_row(row) for row in cur.fetchall()]
        cur.execute(SIGNUP_SQL)
        total, mailed, last = cast("tuple[int, int, datetime | None]", cur.fetchone())
    return {
        "market_data_public": {"value": settings.market_data_public, "environment": settings.environment,
                               "set_in": MARKET_FLAG_SOURCE, "writable": False},
        "vintages": vintages,
        "signups": {"total": total, "launch_mailed": mailed, "not_mailed": total - mailed,
                    "last_mailed_at": _iso(last), "sendable": settings.site_mode == "app"},
    }


class ActivationIn(BaseModel):
    vintage: str = Field(max_length=64)
    force: bool = False
    note: str | None = Field(default=None, max_length=MAX_NOTE)


@router.post("/vintages/{dataset_key}/activate")
def activate_vintage(dataset_key: str, body: ActivationIn, request: Request, principal: Activator) -> JSONResponse:
    """Flip `active_vintage` for one dataset — the CLI's own `app.census.vintage.activate`, reached
    from a screen.

    A plain `def` for `read_settings`' reason, and more so: this takes a row lock across the QA
    counts and the upsert.

    `engine.activate` is admin-only, in `permissions.REAUTH` (the caller confirmed their password
    within ten minutes, and no api token can reach it at all — `deps.TokenCannotReauth`) and in
    `permissions.AUDITED`, so `audit.write(` is called HERE and never through a helper.

    A forced activation requires a note for the reason `scripts/census_load.py`'s argparse requires
    one: a row-count ratio outside [0.8, 1.25] overridden with no recorded why is precisely what
    that gate exists to prevent."""
    if dataset_key not in V.TABLE_FOR:
        return _error("BAD_DATASET", f"dataset_key must be one of {', '.join(sorted(V.TABLE_FOR))}.", 422)
    if body.force and not (body.note or "").strip():
        return _error("NOTE_REQUIRED", "A forced activation must record why.", 422)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM account WHERE id=%s", (principal.account_id,))
            found = cur.fetchone()
        # `deps.require` exempts a legacy operator from the re-auth window and that principal names
        # no `account` row (`deps.LEGACY_ADMIN` is synthetic), so `activated_by` says so rather than
        # carrying a uuid nobody can resolve.
        by = cast("tuple[str]", found)[0] if found is not None else "operator"
        try:
            report = V.activate(conn, dataset_key, body.vintage, by, force=body.force, note=body.note)
        except V.ActivationRefused as exc:
            return _error("ACTIVATION_REFUSED", str(exc), 409)
        audit.write(conn, actor=principal, action="engine.activate", target_type="dataset",
                    target_id=dataset_key, before={"vintage": report.prior_vintage},
                    after={"vintage": body.vintage, "force": body.force}, reason=body.note, request=request)
    return JSONResponse({"dataset_key": dataset_key, "vintage": body.vintage,
                         "prior_vintage": report.prior_vintage, "rows": report.rows_new,
                         "ratio": report.ratio, "note": body.note})
