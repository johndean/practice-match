"""The vision adapter (spec 2026-09-09 C.5 step 4).

Directive 4 step 4: vision "MUST NOT replace OCR. It supplements OCR", and is used "where
available". So there are three outcomes and the difference between two of them is the whole point:
UNAVAILABLE (no key) is not a failure and the pipeline continues; FAILED (a key that did not
produce a usable answer) is a failure and the photograph goes to PROCESSING_FAILED. A failure is
never treated as unavailable, because that would quietly downgrade a listing's protection.

The seam is the ADAPTER's own client, not an httpx transport: the SDK is built on httpx2 and a v1
MockTransport cannot be handed to it."""
from __future__ import annotations

import base64
import logging
import os
import socket
from typing import Any, NoReturn

import pytest
from pydantic import ValidationError

from app.privacy import vision

IMAGE = b"\x00" * 64
#: Distinctive bytes, so a base64 fragment of THIS is searchable in a log capture.
PHOTOGRAPH = b"\x89PNG\r\n\x1a\nPHOTOBYTES-DO-NOT-LOG-ME" * 8
PROMPT_FACTS = {"name": "Hill Country Animal Hospital", "city": "Cedar Park", "state": "TX"}
#: A `BetaRefusalStopDetails.category` value the pinned SDK actually declares — measured on
#: anthropic 1.5.0 as `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`, `general_harms`, and
#: pinned by `test_the_refusal_fixture_uses_a_category_the_sdk_declares` rather than by this comment
#: (review Minor 5; re-review Finding 3, which found the pin deleted rather than made robust).
REFUSAL_CATEGORY = "general_harms"


def _banned_connect(self: socket.socket, address: object) -> NoReturn:
    raise AssertionError(f"the test suite must never open a socket: {address!r}")


def _banned_getaddrinfo(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError(f"the test suite must never resolve a name: {args!r}")


class _SdkClient:
    """A stand-in for a CONSTRUCTED `anthropic.Anthropic`, so the real `_client()` can run.

    It answers nothing: the one test that installs it asserts the constructor is NEVER reached, so
    the only way `create` is called is a mutation, and what that mutation must fail on is the
    constructor COUNT. (`close()` is deliberately absent -- `app/privacy/vision.py` never closes the
    client it builds, which the first report records as its own open concern; a `close()` here would
    read as a path something exercises.)"""

    def __init__(self) -> None:
        self.beta = type("B", (), {"messages": type("M", (), {"create": lambda *a, **k: None})()})()


def _record_sdk_constructor(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch `anthropic.Anthropic` itself and record every constructor call.

    Patching the SDK's own constructor rather than the adapter's `_client` is what lets a test run
    the PRODUCTION path -- the lazy import, the logger pin, the keyword arguments the adapter
    actually passes -- and still open no socket. Returns the list the spy appends to, so
    `len(built)` is a count that can go up."""
    import anthropic

    built: list[dict[str, Any]] = []

    def _factory(**kwargs: Any) -> _SdkClient:
        built.append(kwargs)
        return _SdkClient()

    monkeypatch.setattr(anthropic, "Anthropic", _factory)
    return built


class _Client:
    """Stands in for `anthropic.Anthropic`, recording what the adapter sent."""

    def __init__(self, answer: Any) -> None:
        self.answer, self.sent = answer, []
        self.beta = type("B", (), {"messages": self})()

    def create(self, **kwargs: Any) -> Any:
        self.sent.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _message(text: str, *, stop_reason: str = "end_turn", model: str = "claude-opus-5") -> Any:
    block = type("Block", (), {"type": "text", "text": text})()
    return type("Message", (), {"content": [block], "stop_reason": stop_reason, "model": model,
                                "stop_details": None, "_request_id": "req_abc123"})()


OK_BODY = ('{"identifies_practice": true, "regions": [{"kind": "signage", "label": "monument sign",'
           ' "box": [10, 20, 300, 90], "confidence": "high"}]}')


@pytest.mark.parametrize("key", [None, "", "   ", "  \n", "\t"])
def test_no_key_is_unavailable_and_not_a_failure(monkeypatch: pytest.MonkeyPatch, key: str | None) -> None:
    """Controller amendment A-IDP-12, 2026-09-14, correcting the spec's own literal `is None`.

    pydantic-settings produces `""` -- not `None` -- for a Railway variable that is PRESENT and
    empty, which is what an operator gets by setting the variable to nothing or clearing it. Under
    the identity check that shipped, `""` took the AVAILABLE path: the SDK raised building the auth
    header and every photograph in the queue went PROCESSING_FAILED -> three attempts ->
    REVIEW_REQUIRED, blocking submit for every seller while the true state was "no key configured".
    A whitespace-only key was worse: the SDK opened a TLS connection to api.anthropic.com and SENT
    THE PHOTOGRAPH with a junk credential -- the third-party egress D-IDP-1 is still unruled on, and
    the one thing this branch exists to prevent.

    Blank is UNAVAILABLE: no client is built, and therefore nothing is sent. The egress proof is the
    CONSTRUCTOR count through the production door -- `anthropic.Anthropic` itself, with the real
    `_client()` left in place -- rather than a socket assertion taken around a stubbed `_client`,
    which could not fail (re-review Minor 5): `_client()` is the only door to the SDK, so with it
    stubbed no mutation of the guarded code could ever reach a socket and the assertion was
    vacuous. A spy that COUNTS bites: move the guard and it reads 1."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", key)
    built = _record_sdk_constructor(monkeypatch)
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "unavailable"}
    assert len(built) == 0, "a blank key must not reach the SDK client constructor"


def test_the_unavailable_branch_names_the_variable_and_never_a_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Global Constraint (h): the key is "refused at the moment it is USED, naming the variable and
    never its value". `unavailable` is a status rather than a raised refusal (the spec's design,
    `last_error` untouched), so the name is carried by this one line -- otherwise an operator reading
    a privacy row sees a status and has to go to DEPLOY.md to learn what to set."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "")
    with caplog.at_level(logging.DEBUG):
        vision.analyse(IMAGE, **PROMPT_FACTS)
    assert "ANTHROPIC_API_KEY" in caplog.text
    # "is not set" alone is false for the case A-IDP-12 exists for -- the variable IS set, to a
    # blank -- and sends an operator who can see it in Railway looking for another cause
    # (re-review Minor 3).
    assert "not set or blank" in caplog.text
    assert "Hill Country Animal Hospital" not in caplog.text


def test_the_sdk_never_logs_the_photograph_the_prompt_or_the_practice_at_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global Constraint (h), through the SDK rather than through this module's own lines.

    `anthropic._base_client` emits `log.debug("Request options: %s", model_dump(options, ...))`, and
    its `exclude={"content"}` arm applies to pydantic v1 only -- this project is on v2, so NOTHING is
    excluded. The doors are `ANTHROPIC_LOG=debug`, which sets that logger to DEBUG inside
    `import anthropic`, and a worker started with celery's `--loglevel debug`, which sets the ROOT
    logger it propagates to -- NOT `LOG_LEVEL`, which reaches only the `app` logger on the api
    (re-review Minor 2). Either put the base64 photograph, the whole prompt and the practice's name
    into `railway logs`, three times over, once per SDK retry -- precisely the un-redacted hospital
    photograph this sub-project exists to protect.

    This drives the REAL SDK -- `anthropic.Anthropic`, the real `_base_client`, the real request
    build, which is when the dump happens -- over an `httpx2.MockTransport`, so the whole path runs
    and NO socket is opened and no name is resolved (Global Constraint (i); the reviewer's own ban
    records zero attempts for this file). It answers a schema-valid body, so the SUCCESS path is
    what is under the DEBUG root: the photograph, the prompt and the practice name must be absent
    from the capture even when everything worked."""
    import anthropic
    import httpx2

    def _answer(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5",
            "stop_reason": "end_turn", "stop_sequence": None, "content": [{"type": "text", "text": OK_BODY}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    root, captured = logging.getLogger(), []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(f"{record.name} {record.getMessage()}")

    handler = _Capture()
    client = anthropic.Anthropic(api_key="sk-test", max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(_answer)))
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    # The SDK's CONSTRUCTOR is replaced, never the adapter's `_client` -- so the production line
    # that applies the pin runs. Patching `_client` (fix round 1's own shape) meant the one wired
    # call could be deleted with every test green at 100 % coverage: a gate that could not fail on
    # the wiring it claimed to prove (re-review Minor 1).
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: client)
    monkeypatch.setattr(socket.socket, "connect", _banned_connect)  # belt and braces: nothing may dial out
    monkeypatch.setattr(socket, "getaddrinfo", _banned_getaddrinfo)
    monkeypatch.setattr(logging.getLogger("anthropic"), "level", logging.NOTSET)  # an operator's DEBUG, not ours
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        result = vision.analyse(PHOTOGRAPH, **PROMPT_FACTS)
    finally:
        root.setLevel(previous)
        root.removeHandler(handler)
        client.close()
    blob = "\n".join(captured)
    assert result["status"] == "ok"  # the whole request/response path really did run
    # Stated directly, not only implied by the capture: the NOTSET line in this test's own setup
    # above put the SDK logger back to NOTSET, so INFO here can only have come from `_client()`'s
    # own call on the production path.
    assert logging.getLogger("anthropic").level == logging.INFO, "_client() did not pin the SDK logger"
    assert base64.b64encode(PHOTOGRAPH).decode()[:40] not in blob, "the photograph reached the log"
    assert "could let a reader identify" not in blob, "the prompt reached the log"
    assert "Hill Country Animal Hospital" not in blob, "the practice name reached the log"
    assert "sk-test" not in blob


#: Run in a FRESH interpreter by the test below. `import anthropic` runs the SDK's own
#: `setup_logging()`, which reads `ANTHROPIC_LOG` and sets `logging.getLogger("anthropic")` to DEBUG
#: — so the pin only holds if it runs AFTER that import. Every socket door is banned before the
#: adapter is touched; constructing a client dials nothing, and the ban is what proves it.
_ORDER_PROBE = """
import socket, sys
for name in ("connect", "connect_ex"):
    setattr(socket.socket, name, lambda *a, **k: (_ for _ in ()).throw(AssertionError("socket banned")))
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError("socket banned"))
socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(AssertionError("socket banned"))
import logging
from app.privacy import vision
vision.settings.anthropic_api_key = "sk-test"
vision._client()
print(logging.getLogger("anthropic").level)
"""


def test_the_pin_runs_after_the_lazy_import_so_anthropic_log_cannot_win(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ORDER inside `_client()` is load-bearing and needs its own red (re-review Finding 2).

    `_silence_sdk_logging()` beats `ANTHROPIC_LOG=debug` only because it runs AFTER the lazy
    `import anthropic`: that import calls the SDK's `setup_logging()`, which reads the variable and
    raises `logging.getLogger("anthropic")` to DEBUG (and installs a root StreamHandler). Hoist the
    pin above the import — the shape a linter or a reviewer "moving the side effect first" produces
    — and on a worker started with `ANTHROPIC_LOG=debug` the FIRST `_client()` in each prefork child
    pins INFO, the import then puts it back to DEBUG, and that child's first photograph writes its
    whole request body to `railway logs`. Every later call re-pins, so nothing in a long-lived
    child's log looks wrong.

    The in-process suite cannot see this: `anthropic` is already in `sys.modules` by the time any
    case runs, so `setup_logging()` never fires again and the swapped order stays green. A FRESH
    interpreter is the only honest oracle, and it is where the environment variable can be set at
    all."""
    import subprocess
    import sys
    from pathlib import Path

    # This interpreter, a literal program, no shell -- and it is the only way to reach a FRESH
    # import of the SDK, which is what the order under test is about.
    result = subprocess.run(
        [sys.executable, "-B", "-c", _ORDER_PROBE],
        cwd=Path(vision.__file__).resolve().parents[2],
        env={**os.environ, "ANTHROPIC_LOG": "debug", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=120, check=True,
    )
    assert result.stdout.strip() == str(logging.INFO), (
        f"the SDK logger is at {result.stdout.strip()} under ANTHROPIC_LOG=debug, not INFO — "
        f"the pin ran before the import\n{result.stderr}"
    )


@pytest.mark.parametrize(("start", "expected"), [
    (logging.NOTSET, logging.INFO),   # inherits the root's DEBUG: raise it
    (logging.DEBUG, logging.INFO),    # an operator turned the SDK itself up: raise it
    (logging.INFO, logging.INFO),     # already pinned: a second call changes nothing
    (logging.ERROR, logging.ERROR),   # someone quietened it deliberately: never lowered
])
def test_pinning_the_sdk_logger_is_idempotent_and_never_lowers_it(
    monkeypatch: pytest.MonkeyPatch, start: int, expected: int
) -> None:
    """The pin is applied on EVERY `_client()` and must therefore be safe to repeat: it raises a
    level below INFO and leaves anything at or above it alone, so it cannot accumulate state, and it
    cannot undo an operator who quietened the SDK on purpose."""
    sdk = logging.getLogger("anthropic")
    monkeypatch.setattr(sdk, "level", start)
    vision._silence_sdk_logging()
    assert sdk.level == expected
    vision._silence_sdk_logging()
    assert sdk.level == expected


#: Every form a real key reaches Settings in when a person pastes it. The last three are INVISIBLE
#: in Railway's variable editor: `str.strip()` leaves a Unicode FORMAT character (category `Cf`)
#: exactly where it was, and unlike a newline — which h11 REFUSES before any body is written — a
#: `Cf` character travels: httpx2 falls back from ascii to utf-8 and h11 accepts obs-text, so one
#: connection opens and the PHOTOGRAPH leaves with a credential the API cannot match.
PASTED_KEYS = ["sk-test", "sk-test\n", "  sk-test  ", "sk-test\r\n", "\tsk-test",
               "sk-test\u200b", "\ufeffsk-test", "sk-test\u200e"]


@pytest.mark.parametrize("configured", PASTED_KEYS)
def test_the_client_takes_its_key_from_settings_stripped_and_reaches_only_anthropic(
    monkeypatch: pytest.MonkeyPatch, configured: str
) -> None:
    """`_client()` is the one place a credential and a destination are chosen, and every other case
    here replaces it -- so without this the adapter's own constructor would never run under the
    100 % gate, and Global Constraints (h) and (i) would rest on a comment.

    Controller amendment **A-IDP-12 EXTENDED** (2026-09-14) and **EXTENDED AGAIN** (the same day):
    `_configured()` decides on the cleaned key and `_client()` must hand the SDK that SAME value.
    Fix round 1 left the SDK receiving the raw setting, so a key pasted with a trailing newline was
    "configured" and then failed every photograph -- httpx2 accepts the header at construction,
    httpcore2 opens TCP and then TLS, and h11 refuses only at header build, which the SDK maps to
    `APIConnectionError` and retries twice. Fix round 2 stripped whitespace and left the INVISIBLE
    class: `"sk-test\u200b".strip()` is unchanged, so a zero-width space, a BOM or a left-to-right
    mark survived and was SENT -- one connection, the photograph on the wire, a 401 the operator
    reads as a key that looks right in Railway.

    The assertion is the HEADER, which is the thing the defect was ever about, and reading it costs
    no socket (re-review Finding 4): the raw SDK builds `{"X-Api-Key": "sk-test\n"}` and this one
    must build `{"X-Api-Key": "sk-test"}` for every form above. `max_retries`, `timeout` and the base
    URL -- the single egress this sub-project adds -- are asserted on the same real object, so
    nothing can drift between two stand-ins."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", configured)
    client = vision._client()
    try:
        assert client.auth_headers == {"X-Api-Key": "sk-test"}, "the SDK must be given the key the guard accepted"
        assert client.api_key == "sk-test"
        assert client.max_retries == vision.SDK_RETRIES and client.timeout == vision.TIMEOUT_S
        assert str(client.base_url).startswith("https://api.anthropic.com")
    finally:
        client.close()


def test_a_usable_answer_is_recorded_with_the_model_that_actually_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_message(OK_BODY, model="claude-sonnet-5"))
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: client)
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "ok" and result["identifies_practice"] is True
    assert result["model"] == "claude-sonnet-5" and result["request_id"] == "req_abc123"
    assert result["regions"][0]["box"] == [10, 20, 300, 90]
    sent = client.sent[0]
    assert sent["model"] == vision.VISION_MODEL and sent["max_tokens"] == vision.MAX_TOKENS
    assert sent["betas"] == vision.BETAS and sent["fallbacks"] == "default"
    assert sent["output_config"]["format"]["schema"] == vision.VISION_SCHEMA


def test_the_prompt_carries_the_name_city_and_state_and_never_the_phone_or_street(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data minimisation (spec C.5 step 4): a third party is told what the practice is called and
    roughly where, because that is what makes a sign recognisable, and nothing else."""
    client = _Client(_message(OK_BODY))
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: client)
    vision.analyse(IMAGE, **PROMPT_FACTS)
    text = str(client.sent[0]["messages"])
    assert "Hill Country Animal Hospital" in text and "Cedar Park" in text and "TX" in text
    assert "555-0100" not in text and "Cypress Creek" not in text


@pytest.mark.parametrize(("answer", "code"), [
    (RuntimeError("connection reset"), "VISION_FAILED"),
    (_message("not json at all"), "VISION_FAILED"),
    # `regions` is PRESENT, so this case fails for the type it claims: without strict validation
    # pydantic's lax mode coerces "yes" -> True and records the answer as `ok` (review Minor 2).
    (_message('{"identifies_practice": "yes", "regions": []}'), "VISION_FAILED"),
    (_message('{"identifies_practice": true, "regions": [{"kind": "signage", "label": "l",'
              ' "box": ["10", "20", "300", "90"], "confidence": "high"}]}'), "VISION_FAILED"),
    (_message(OK_BODY, stop_reason="max_tokens"), "VISION_FAILED"),
    (_message("", stop_reason="refusal"), "VISION_REFUSED"),
])
def test_every_other_outcome_is_failed_with_its_own_code(
    monkeypatch: pytest.MonkeyPatch, answer: Any, code: str
) -> None:
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(answer))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "failed" and result["code"] == code


def test_the_refusal_fixture_uses_a_category_the_sdk_declares() -> None:
    """The fixture must exercise a value the API can actually send, and the pin must survive an SDK
    bump reshaping the field.

    Round 1's version read the SDK's ANNOTATION SHAPE (`get_args(get_args(...)[0])`, assuming
    `Optional[Literal[...]]`), which would have turned a flattened annotation into
    `assert 'general_harms' in ()` inside the refusal-ORDERING test; round 2 deleted it instead of
    making it robust, and nothing then noticed a fixture the API cannot produce — the original
    Minor 5 defect (`"image_safety"`) with its gate removed (re-review Finding 3).

    This asks the SDK's OWN TYPE instead of its annotation: `BetaRefusalStopDetails` validates
    `category` against whatever literal it declares, so a declared value constructs and an undeclared
    one raises `ValidationError`. No shape is assumed, the failure names the field, and it lives in
    its own test so the ordering case stays about ordering."""
    from anthropic.types.beta import BetaRefusalStopDetails

    details = BetaRefusalStopDetails.model_validate({"type": "refusal", "category": REFUSAL_CATEGORY})
    assert details.category == REFUSAL_CATEGORY
    with pytest.raises(ValidationError):  # the pin is real: an undeclared category is refused
        BetaRefusalStopDetails.model_validate({"type": "refusal", "category": "image_safety"})


def test_a_refusal_is_read_before_the_content_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stop_reason == "refusal"` is checked FIRST: reading `content[0].text` on a refusal is how a
    caller gets an IndexError instead of a recorded outcome.

    The category is one the pinned SDK can actually send (review Minor 5). It is pinned by VALUE in
    `REFUSAL_CATEGORY` and asserted through BEHAVIOUR -- what `analyse` records -- rather than by
    reading the SDK's annotation SHAPE: `get_args(get_args(...)[0])` assumed `Optional[Literal[...]]`
    and would have turned an SDK bump that flattened the field into `assert 'general_harms' in ()`
    inside the refusal-ordering case, an opaque failure in a test about something else
    (re-review Minor 6)."""
    refused = type("Message", (), {"content": [], "stop_reason": "refusal", "model": "claude-opus-5",
                                   "stop_details": type("D", (), {"category": REFUSAL_CATEGORY})(),
                                   "_request_id": "req_x"})()
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(refused))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["code"] == "VISION_REFUSED" and result["refusal_category"] == REFUSAL_CATEGORY


@pytest.mark.parametrize("answer", [
    _message("", stop_reason="refusal", model="claude-sonnet-5"),
    _message(OK_BODY, stop_reason="max_tokens", model="claude-sonnet-5"),
    _message("not json at all", model="claude-sonnet-5"),
])
def test_every_post_call_outcome_records_the_model_that_answered(
    monkeypatch: pytest.MonkeyPatch, answer: Any
) -> None:
    """`fallbacks="default"` may route the turn to another model, and the spec says `vision.model`
    is the model that ACTUALLY answered. The `ok` branch read it off the response from the start;
    the refusal, truncation and validation branches hard-coded the constant, so a refusal was
    audited against a model that may not have produced it (review Minor 1)."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(answer))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "failed" and result["model"] == "claude-sonnet-5"


@pytest.mark.parametrize(("unreadable", "recorded"), [
    # the answering model is there to read: record IT, never the constant
    (type("Message", (), {"_request_id": "req_y", "model": "claude-sonnet-5"})(), "claude-sonnet-5"),
    # nothing to read: the constant is the honest fallback
    (type("Message", (), {"_request_id": "req_y"})(), vision.VISION_MODEL),
])
def test_an_unreadable_answer_is_a_recorded_outcome_and_never_an_exception(
    monkeypatch: pytest.MonkeyPatch, unreadable: Any, recorded: str
) -> None:
    """"This module NEVER raises" must cover the ANSWER, not only the call (review Minor 3).

    The `try` used to end at `create(...)`, leaving `message.stop_reason`, `message.content` and the
    dict build outside it -- a response object missing `stop_reason` raised `AttributeError` straight
    out of `analyse`, which in the worker is a dead child instead of a written PROCESSING_FAILED.
    Every response type SDK 1.5.0 documents carries both attributes, so this is the contract's
    scope rather than a live defect; the guarantee is what is being held.

    Parametrised over the model BEING there and NOT being there, because the arm reads
    `getattr(message, "model", VISION_MODEL)` and fix round 1's single fixture carried no `model`
    at all -- so replacing that whole expression with the bare constant left all 27 tests green,
    and a fallback-routed turn whose answer the adapter could not read would have been audited
    against a model that did not produce it: Minor 1's defect surviving on the one arm nothing
    covered (re-review Minor 4)."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(unreadable))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "failed", "code": "VISION_FAILED", "model": recorded,
                      "request_id": "req_y"}


def test_an_unlocalised_answer_still_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    """`identifies_practice` true with no usable box: the photograph still reaches the seller's
    review, and `unlocalised` is recorded so the record explains itself (D-IDP-8)."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client",
                        lambda: _Client(_message('{"identifies_practice": true, "regions": []}')))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["status"] == "ok" and result["unlocalised"] is True


def test_the_adapter_never_logs_the_image_or_the_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Global Constraint (h). The request id and the exception class, and nothing else -- no base64,
    no response text, no key, no prompt."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-secret-value")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(RuntimeError("boom: sk-secret-value")))
    with caplog.at_level(logging.DEBUG):
        vision.analyse(b"\xff\xd8\xffPHOTOBYTES", **PROMPT_FACTS)
    logged = caplog.text
    assert "RuntimeError" in logged
    assert "sk-secret-value" not in logged and "PHOTOBYTES" not in logged and "boom" not in logged


def test_the_request_schema_uses_no_array_bound_structured_output_refuses():
    """QA, 2026-09-17, the first REAL vision call this pipeline has ever made: every one of the
    eleven ingested photographs came back `VISION_FAILED` with

        400 invalid_request_error — output_config.format.schema:
        For 'array' type, 'minItems' values other than 0 or 1 are not supported

    from `box`'s own `minItems: 4, maxItems: 4`. The module had been exercised against mocks
    alone -- no key was set in any environment until that morning -- so a schema the API will not
    accept passed every gate for eight days. It is NOT a consequence of moving to
    `claude-sonnet-5`: the bound is refused at schema validation, before a model is chosen.

    The constraint is not re-homed because it was never load-bearing here: `VisionRegion.box` is
    `tuple[float, float, float, float]` under `ConfigDict(strict=True)`, so a box of any other
    length is already refused by the parse -- which is the layer that module's own comment calls
    "the schema the record trusts"."""
    def bounds(node: object, path: str = "") -> list[str]:
        out: list[str] = []
        if isinstance(node, dict):
            for key in ("minItems", "maxItems"):
                if key in node and node[key] not in (0, 1):
                    out.append(f"{path}.{key}={node[key]}")
            for k, v in node.items():
                out.extend(bounds(v, f"{path}.{k}"))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                out.extend(bounds(v, f"{path}[{i}]"))
        return out

    assert bounds(vision.VISION_SCHEMA) == []
