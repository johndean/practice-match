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
import socket
from typing import Any, NoReturn, get_args

import pytest

from app.privacy import vision

IMAGE = b"\x00" * 64
#: Distinctive bytes, so a base64 fragment of THIS is searchable in a log capture.
PHOTOGRAPH = b"\x89PNG\r\n\x1a\nPHOTOBYTES-DO-NOT-LOG-ME" * 8
PROMPT_FACTS = {"name": "Hill Country Animal Hospital", "city": "Cedar Park", "state": "TX"}
#: One of the five `BetaRefusalStopDetails.category` values the pinned SDK declares (Minor 5).
REFUSAL_CATEGORY = "general_harms"


def _banned_connect(self: socket.socket, address: object) -> NoReturn:
    raise AssertionError(f"the test suite must never open a socket: {address!r}")


def _banned_getaddrinfo(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError(f"the test suite must never resolve a name: {args!r}")


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

    Blank is UNAVAILABLE: no client is built, no socket is opened, nothing is sent."""
    built: list[object] = []
    attempted: list[object] = []
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", key)
    monkeypatch.setattr("app.privacy.vision._client", lambda: built.append(object()))
    monkeypatch.setattr(socket.socket, "connect", lambda self, address: attempted.append(address))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: attempted.append(a))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "unavailable"}
    assert built == [], "a blank key must not reach the SDK client constructor"
    assert attempted == [], "a blank key must not open a socket or resolve a name"


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
    assert "Hill Country Animal Hospital" not in caplog.text


def test_the_sdk_never_logs_the_photograph_the_prompt_or_the_practice_at_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global Constraint (h), through the SDK rather than through this module's own lines.

    `anthropic._base_client` emits `log.debug("Request options: %s", model_dump(options, ...))`, and
    its `exclude={"content"}` arm applies to pydantic v1 only -- this project is on v2, so NOTHING is
    excluded. `app.main._configure_logging` puts `settings.log_level` on the root logger and the SDK
    logger propagates to it, so a single `LOG_LEVEL=DEBUG` on the worker put the base64 photograph,
    the whole prompt and the practice's name into `railway logs` -- three times over, once per SDK
    retry -- which is precisely the un-redacted hospital photograph this sub-project exists to
    protect.

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
    monkeypatch.setattr("app.privacy.vision._client", lambda: (vision._silence_sdk_logging(), client)[1])
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
    assert base64.b64encode(PHOTOGRAPH).decode()[:40] not in blob, "the photograph reached the log"
    assert "could let a reader identify" not in blob, "the prompt reached the log"
    assert "Hill Country Animal Hospital" not in blob, "the practice name reached the log"
    assert "sk-test" not in blob


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


def test_the_client_takes_its_key_from_settings_and_reaches_only_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_client()` is the one place a credential and a destination are chosen, and every other case
    here replaces it -- so without this the adapter's own constructor would never run under the
    100 % gate, and Global Constraints (h) and (i) would rest on a comment.

    Constructing the SDK client opens no connection and sends nothing: this asserts what the
    adapter CONFIGURED, not what it called. The key comes from SETTINGS, never `os.environ`, so an
    ambient `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`, an `ant auth login` profile or a workload
    identity cannot stand in for an unset Railway variable; and the base URL is the single egress
    this sub-project adds."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    client = vision._client()
    try:
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


def test_a_refusal_is_read_before_the_content_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stop_reason == "refusal"` is checked FIRST: reading `content[0].text` on a refusal is how a
    caller gets an IndexError instead of a recorded outcome.

    The category is one the pinned SDK can actually send, asserted against the SDK's own literal
    rather than chosen (review Minor 5: the first fixture used `"image_safety"`, which
    `BetaRefusalStopDetails.category` does not declare -- the adapter records whatever it is handed,
    so nothing was wrong, but the case exercised a value the API cannot produce)."""
    from anthropic.types.beta import BetaRefusalStopDetails

    assert REFUSAL_CATEGORY in get_args(get_args(BetaRefusalStopDetails.model_fields["category"].annotation)[0])
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


def test_an_unreadable_answer_is_a_recorded_outcome_and_never_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"This module NEVER raises" must cover the ANSWER, not only the call (review Minor 3).

    The `try` used to end at `create(...)`, leaving `message.stop_reason`, `message.content` and the
    dict build outside it -- a response object missing `stop_reason` raised `AttributeError` straight
    out of `analyse`, which in the worker is a dead child instead of a written PROCESSING_FAILED.
    Every response type SDK 1.5.0 documents carries both attributes, so this is the contract's
    scope rather than a live defect; the guarantee is what is being held."""
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client",
                        lambda: _Client(type("Message", (), {"_request_id": "req_y"})()))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "failed", "code": "VISION_FAILED", "model": vision.VISION_MODEL,
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
