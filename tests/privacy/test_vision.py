"""The vision adapter (spec 2026-09-09 C.5 step 4).

Directive 4 step 4: vision "MUST NOT replace OCR. It supplements OCR", and is used "where
available". So there are three outcomes and the difference between two of them is the whole point:
UNAVAILABLE (no key) is not a failure and the pipeline continues; FAILED (a key that did not
produce a usable answer) is a failure and the photograph goes to PROCESSING_FAILED. A failure is
never treated as unavailable, because that would quietly downgrade a listing's protection.

The seam is the ADAPTER's own client, not an httpx transport: the SDK is built on httpx2 and a v1
MockTransport cannot be handed to it."""
from __future__ import annotations

import logging
from typing import Any

import pytest

from app.privacy import vision

IMAGE = b"\x00" * 64
PROMPT_FACTS = {"name": "Hill Country Animal Hospital", "city": "Cedar Park", "state": "TX"}


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


def test_no_key_is_unavailable_and_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", None)
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result == {"status": "unavailable"}


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
    (_message('{"identifies_practice": "yes"}'), "VISION_FAILED"),
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
    caller gets an IndexError instead of a recorded outcome."""
    refused = type("Message", (), {"content": [], "stop_reason": "refusal", "model": "claude-opus-5",
                                   "stop_details": type("D", (), {"category": "image_safety"})(),
                                   "_request_id": "req_x"})()
    monkeypatch.setattr("app.privacy.vision.settings.anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.privacy.vision._client", lambda: _Client(refused))
    result = vision.analyse(IMAGE, **PROMPT_FACTS)
    assert result["code"] == "VISION_REFUSED" and result["refusal_category"] == "image_safety"


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
