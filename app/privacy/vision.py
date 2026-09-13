"""Visual identity signals, through the Anthropic Messages API (spec 2026-09-09 C.5 step 4).

Directive 4 step 4: this SUPPLEMENTS OCR and never replaces it. Three outcomes, and the difference
between two of them is load-bearing:

  unavailable  no key. Not a failure. The pipeline continues, the record says so, and the seller's
               review carries the OCR, regex and symbol regions. This is QA's state today.
  ok           a body that validated against VisionResult.
  failed       a key that did not produce one -- a transport error after the SDK's own retries, a
               refusal, a truncation, or a body the model refused to shape. PROCESSING_FAILED, and
               after three attempts REVIEW_REQUIRED. NEVER recorded as unavailable, because that
               would quietly downgrade a listing's protection to "we did not try".

"Blank" is the whole test, not "is None" -- controller amendment A-IDP-12, 2026-09-14, correcting
the spec's own literal at `2026-09-09-image-identifiability-protection-design.md` §C.5 step 4.
pydantic-settings produces `""`, not `None`, for a Railway variable that is PRESENT and empty, so an
identity check was inert: an empty key took the AVAILABLE path and failed every photograph into
PROCESSING_FAILED -> REVIEW_REQUIRED, and a whitespace-only key opened a TLS connection and SENT THE
PHOTOGRAPH with a junk credential. `key.strip()` decides, and unavailable is decided before a client
exists.

This module NEVER raises -- the call AND the answer: a response object that does not carry what the
SDK documents is a recorded VISION_FAILED, not an exception out of a worker child. Every outcome is
the dict the privacy row's `vision` column takes. It logs the SDK's request id and the exception
class and nothing else -- never the image, never the prompt, never the response text, never the key
-- and it holds the SDK to the same rule: `anthropic._base_client` dumps the whole request body at
DEBUG (its `exclude={"content"}` arm is pydantic v1 only and this project is v2), so one
`LOG_LEVEL=DEBUG` on the worker would have put the base64 photograph, the prompt and the practice's
name into `railway logs`. `_silence_sdk_logging()` pins that logger at INFO before any client is
built. `httpx2`/`httpcore2` are NOT pinned: measured, their DEBUG traces carry
`<Request [b'POST']>` and never the body.

D-IDP-1 is queued for John: whether to send at all, which model, and a monthly cap. With the key
absent -- which is every deployed environment today -- this module makes no request."""
from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

#: John may name another; `claude-sonnet-5` is the cost lever. One constant, one line.
VISION_MODEL = "claude-opus-5"
#: Shared with adaptive thinking, which is ON by default on Opus 5 and is why `effort: "low"`
#: is chosen: the spec's own estimate is ~800 output tokens including low-effort thinking,
#: ~2.5x headroom. A systematic truncation would read as VISION_FAILED on every photograph and
#: cannot be measured without a live call, so it is recorded beside D-IDP-1 rather than tuned
#: blind (review Minor 6).
MAX_TOKENS = 2048
TIMEOUT_S = 60.0
SDK_RETRIES = 2
BETAS = ["server-side-fallback-2026-07-01"]

VISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["identifies_practice", "regions"],
    "properties": {
        "identifies_practice": {"type": "boolean"},
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "label", "box", "confidence"],
                "properties": {
                    "kind": {"enum": ["logo", "signage", "uniform", "vehicle", "wall_graphic",
                                      "document", "business_card", "directory", "text", "other"]},
                    "label": {"type": "string"},
                    "box": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                    "confidence": {"enum": ["low", "medium", "high"]},
                },
            },
        },
    },
}

PROMPT = (
    "This photograph belongs to a veterinary practice listing. The practice is called {name} and is"
    " in {city}, {state}. Find every visible element that could let a reader identify this specific"
    " practice: signage, logos, branded uniforms, branded vehicles, wall graphics, documents,"
    " business cards, building directories, street or building numbers, and any other lettering."
    " Give each one a bounding box in the image's own pixel coordinates. Do not guess: report"
    " only what is visible."
)


class VisionRegion(BaseModel):
    # STRICT: pydantic's lax mode coerces "yes" -> True and ["1","2","3","4"] -> floats, so a body
    # the model shaped wrongly was recorded as `ok` with invented values (review Minor 2). Strict
    # mode still accepts a JSON int where a float is declared, which is what `box: [10, 20, 300, 90]`
    # is, so the schema the request asks for is exactly the schema the record trusts.
    model_config = ConfigDict(strict=True)

    kind: str
    label: str
    box: tuple[float, float, float, float]
    confidence: str


class VisionResult(BaseModel):
    model_config = ConfigDict(strict=True)

    identifies_practice: bool
    regions: list[VisionRegion]


def _configured() -> bool:
    """Whether a key is CONFIGURED, which is not whether the setting is non-None (A-IDP-12).

    A Railway variable that is present and empty reaches Settings as `""`, and a variable someone
    pasted a newline into reaches it as whitespace. Neither can authenticate; both must be the
    `unavailable` outcome rather than a per-photograph failure, and the whitespace one must not be
    allowed to open a connection. Every sibling secret in the tree already tests falsiness
    (`app/mail/tasks.py`, `app/census/client.py`); this adds `.strip()` on top of that, because
    `"   "` is truthy."""
    return bool((settings.anthropic_api_key or "").strip())


def _silence_sdk_logging() -> None:
    """Pin the SDK's own logger at INFO, before any client exists (Global Constraint (h)).

    `anthropic._base_client` emits `log.debug("Request options: %s", ...)` with NOTHING excluded on
    pydantic v2, and it propagates to the root logger `app.main._configure_logging` sets from
    `LOG_LEVEL`. Setting the level on the SDK's OWN logger beats the root's, so a DEBUG deploy still
    gets this module's warnings and the transport's connection trace and never the photograph.

    Idempotent and cheap: it raises a level that is below INFO and touches nothing else, so it can
    run on every call without accumulating handlers or overriding a deliberate WARNING/ERROR."""
    sdk = logging.getLogger("anthropic")
    if sdk.level == logging.NOTSET or sdk.level < logging.INFO:
        sdk.setLevel(logging.INFO)


def _client() -> Any:
    """The SDK client, built per call and never cached: a worker child may sit idle for hours and a
    connection pool held across that is a source of transport errors, not a saving. The key is
    passed EXPLICITLY from settings, so no ambient credential can satisfy an unset variable."""
    import anthropic  # lazy -- the api imports this module's siblings, never this

    _silence_sdk_logging()
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=SDK_RETRIES, timeout=TIMEOUT_S)


def _failed(code: str, request_id: str | None = None, *, model: str = VISION_MODEL, **extra: Any) -> dict[str, Any]:
    """`model` is the model that ANSWERED wherever there is an answer to read it off: `fallbacks`
    may route a turn elsewhere, and auditing a refusal against a model that did not produce it is
    the defect review Minor 1 names. The transport arm has no message and keeps the constant."""
    return {"status": "failed", "code": code, "model": model, "request_id": request_id, **extra}


def analyse(display: bytes, *, name: str | None, city: str | None, state: str | None) -> dict[str, Any]:
    """The privacy row's `vision` object. Never raises -- the call and the answer alike."""
    if not _configured():
        # Global Constraint (h): refused where it is USED, NAMING the variable and never its value.
        # `unavailable` is a status rather than a raised refusal, so this line is the only place an
        # operator reading a privacy row is told what to set (review Minor 8).
        log.info("[vision] ANTHROPIC_API_KEY is not set; vision skipped")
        return {"status": "unavailable"}
    # Bound before the `try` so the exception arm can still report the answer's own model and
    # request id when the failure came from READING a response rather than from fetching one.
    message: Any = None
    try:
        message = _client().beta.messages.create(
            model=VISION_MODEL,
            max_tokens=MAX_TOKENS,
            betas=BETAS,
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": VISION_SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/webp",
                                             "data": base64.b64encode(display).decode()}},
                {"type": "text", "text": PROMPT.format(name=name or "unnamed", city=city or "an unstated city",
                                                       state=state or "an unstated state")},
            ]}],
        )
        request_id = getattr(message, "_request_id", None)
        # The model that ACTUALLY answered: `fallbacks: "default"` may route to another.
        model = getattr(message, "model", VISION_MODEL)
        # BEFORE `content` is read: a refusal carries no text block, and reading it past the
        # validation call below would record VISION_FAILED for a turn the model declined.
        if message.stop_reason == "refusal":
            category = getattr(getattr(message, "stop_details", None), "category", None)
            log.warning("[vision] refused: %s", request_id)
            return _failed("VISION_REFUSED", request_id, model=model, refusal_category=category)
        if message.stop_reason == "max_tokens":
            log.warning("[vision] truncated: %s", request_id)
            return _failed("VISION_FAILED", request_id, model=model)
        body = next((block.text for block in message.content if getattr(block, "type", None) == "text"), "")
        try:
            parsed = VisionResult.model_validate_json(body)
        except ValidationError:
            # The response TEXT is never logged -- it is a model's description of a photograph.
            log.warning("[vision] body did not validate: %s", request_id)
            return _failed("VISION_FAILED", request_id, model=model)
    except Exception as exc:  # noqa: BLE001 — the SDK error classes are no stable catchable set; an escape would take the worker child down. Class name only
        log.warning("[vision] call failed: %s", type(exc).__name__)
        return _failed("VISION_FAILED", getattr(message, "_request_id", None),
                       model=getattr(message, "model", VISION_MODEL))
    return {
        "status": "ok",
        "model": model,
        "request_id": request_id,
        "identifies_practice": parsed.identifies_practice,
        "regions": [{"kind": r.kind, "label": r.label, "box": list(r.box), "confidence": r.confidence}
                    for r in parsed.regions],
        # `identifies_practice` with nothing to draw: the photograph still reaches the seller's
        # review and the manual mask is the tool (D-IDP-8).
        "unlocalised": parsed.identifies_practice and not parsed.regions,
    }
