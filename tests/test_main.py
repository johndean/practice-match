import asyncio
import logging
import sys

import httpx
from httpx import ASGITransport

from app import db, main
from app.checks import async_dsn
from app.config import settings
from app.main import create_app

PREFLIGHT_HEADERS = {
    "Origin": "https://qa.foundation.vin",
    "Access-Control-Request-Method": "GET",
}


async def test_cors_preflight_allows_configured_origin(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "https://qa.foundation.vin")
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/api/healthz", headers=PREFLIGHT_HEADERS)
        assert r.headers.get("access-control-allow-origin") == "https://qa.foundation.vin"


async def test_cors_header_absent_without_configured_origins(monkeypatch):
    monkeypatch.setattr(settings, "allowed_origins", "")
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/api/healthz", headers=PREFLIGHT_HEADERS)
        assert "access-control-allow-origin" not in r.headers


async def test_lifespan_disposes_the_pool_on_shutdown():
    """Round 4: dispose_all() is wired into the app's own lifespan (not a
    loop-close hook) — production's one long-lived loop is cleaned up on shutdown."""
    dsn = async_dsn(settings.database_url)
    loop = asyncio.get_running_loop()
    app = create_app()
    db.get_engine(dsn)
    assert dsn in db._engines.get(loop, {})
    async with app.router.lifespan_context(app):
        pass
    assert dsn not in db._engines.get(loop, {})


def test_app_info_records_reach_the_deployment_log():
    """Measured on QA at `db8bf67`: `railway logs --service api` carried uvicorn's access lines and
    nothing else. `app/api/market.py:527`'s structured cost line — `log.info("boundaries miss
    outcome=... ")` on the module logger `logging.getLogger("app.api.market")` — never appeared,
    because NOTHING configured logging: neither `app/main.py` nor `scripts/start.sh` calls
    `basicConfig` or `dictConfig`, uvicorn's own `LOGGING_CONFIG` configures only the `uvicorn*`
    loggers, and the root logger therefore sat at its default WARNING with the last-resort handler.
    `log.warning` surfaced; `log.info` was written into the void. Every INFO record the api emits
    was unreachable, so a cost line nobody can read is a measurement nobody has.

    Creating the app now configures the `app` logger hierarchy — the api's own namespace and
    nothing else — so `app.api.market` INHERITS the level rather than being named here: any module
    under `app.` gets the same treatment without a list to maintain."""
    create_app()
    assert logging.getLogger("app.api.market").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("app.census.serve").getEffectiveLevel() == logging.INFO


def test_the_app_logger_writes_one_plain_stderr_line_per_record_and_is_added_once():
    """The handler is added at app creation, which the test suite alone does dozens of times (every
    `create_app()` above, every client fixture). Without a guard each one would stack another
    handler on the same logger and one INFO record would be printed once per app ever created — the
    classic idempotence bug in this exact position. Two creations, still exactly one handler.

    stderr, not stdout: Railway captures both, and the api's own diagnostics must not interleave
    with anything a process writes to stdout. The format is deliberately plain — the level, the
    logger that emitted it, the message — because the records themselves are already structured
    (`key=value` pairs); wrapping them in JSON here would give an operator reading `railway logs`
    two layers to unpick."""
    create_app()
    create_app()
    app_logger = logging.getLogger("app")
    handlers = [h for h in app_logger.handlers if h.get_name() == main._LOG_HANDLER_NAME]
    assert len(handlers) == 1
    handler = handlers[0]
    assert handler.formatter is not None and handler.formatter._fmt == "%(levelname)s %(name)s: %(message)s"
    assert handler.format(logging.LogRecord("app.api.market", logging.INFO, __file__, 1, "boundaries miss outcome=x", None, None)) == (
        "INFO app.api.market: boundaries miss outcome=x"
    )
    # The stream is asserted against a handler this test installs ITSELF, not the one the session
    # already had. pytest swaps `sys.stderr` for its own capture object, and the session's handler
    # was built during whichever earlier `create_app()` came first, under a different one — so
    # `handlers[0].stream is sys.stderr` compares two capture objects and fails in a full run while
    # passing alone. Re-running the installer here asserts what the code actually does: it binds to
    # stderr as it stands at that moment, never stdout. The original handler is put back afterwards,
    # so the rest of the session is left exactly as it was found.
    app_logger.removeHandler(handler)
    try:
        main._configure_logging()
        fresh = [h for h in app_logger.handlers if h.get_name() == main._LOG_HANDLER_NAME]
        assert len(fresh) == 1 and fresh[0] is not handler
        assert fresh[0].stream is sys.stderr
        assert fresh[0].stream is not sys.stdout
        app_logger.removeHandler(fresh[0])
    finally:
        app_logger.addHandler(handler)


def test_an_info_record_from_a_real_app_module_logger_is_emitted():
    """The level and the handler are two halves of one claim; neither alone puts a line in the log.
    This asserts the whole path end to end on the REAL module logger the QA finding names, through
    the `app` logger's own handler rather than through pytest's root capture, which would pass even
    with the defect (`caplog` attaches at the root and forces its own level)."""
    create_app()
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    app_logger = logging.getLogger("app")
    capture = _Capture()
    app_logger.addHandler(capture)
    try:
        logging.getLogger("app.api.market").info("boundaries miss outcome=%s features=%d", "empty", 0)
    finally:
        app_logger.removeHandler(capture)
    assert [r.getMessage() for r in records] == ["boundaries miss outcome=empty features=0"]


def test_configuring_the_app_logger_leaves_uvicorns_own_loggers_alone():
    """The fix is scoped to the `app` namespace. uvicorn owns `uvicorn`, `uvicorn.error` and
    `uvicorn.access` and configures them itself at server start; touching their level or handlers
    here would either duplicate its access lines or silence them, and neither is this change's
    business."""
    create_app()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert logging.getLogger(name).handlers == [], name
        assert logging.getLogger(name).level == logging.NOTSET, name
