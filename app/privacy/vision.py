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

This module NEVER raises: every outcome is the dict the privacy row's `vision` column takes. It
logs the SDK's request id and the exception class and nothing else -- never the image, never the
prompt, never the response text, never the key.

D-IDP-1 is queued for John: whether to send at all, which model, and a monthly cap. With the key
absent -- which is every deployed environment today -- this module makes no request."""
from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger(__name__)

#: John may name another; `claude-sonnet-5` is the cost lever. One constant, one line.
VISION_MODEL = "claude-opus-5"
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
    kind: str
    label: str
    box: tuple[float, float, float, float]
    confidence: str


class VisionResult(BaseModel):
    identifies_practice: bool
    regions: list[VisionRegion]


def _client() -> Any:
    """The SDK client, built per call and never cached: a worker child may sit idle for hours and a
    connection pool held across that is a source of transport errors, not a saving. The key is
    passed EXPLICITLY from settings, so no ambient credential can satisfy an unset variable."""
    import anthropic  # lazy -- the api imports this module's siblings, never this

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=SDK_RETRIES, timeout=TIMEOUT_S)


def _failed(code: str, request_id: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "code": code, "model": VISION_MODEL, "request_id": request_id, **extra}


def analyse(display: bytes, *, name: str | None, city: str | None, state: str | None) -> dict[str, Any]:
    """The privacy row's `vision` object. Never raises."""
    if settings.anthropic_api_key is None:
        return {"status": "unavailable"}
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
    except Exception as exc:  # noqa: BLE001 — the SDK error classes are no stable catchable set; an escape would take the worker child down. Class name only
        log.warning("[vision] call failed: %s", type(exc).__name__)
        return _failed("VISION_FAILED")
    request_id = getattr(message, "_request_id", None)
    # BEFORE `content` is read: a refusal carries no text block and indexing it is an IndexError
    # instead of a recorded outcome.
    if message.stop_reason == "refusal":
        category = getattr(getattr(message, "stop_details", None), "category", None)
        log.warning("[vision] refused: %s", request_id)
        return _failed("VISION_REFUSED", request_id, refusal_category=category)
    if message.stop_reason == "max_tokens":
        log.warning("[vision] truncated: %s", request_id)
        return _failed("VISION_FAILED", request_id)
    body = next((block.text for block in message.content if getattr(block, "type", None) == "text"), "")
    try:
        parsed = VisionResult.model_validate_json(body)
    except ValidationError:
        # The response TEXT is never logged -- it is a model's description of a photograph.
        log.warning("[vision] body did not validate: %s", request_id)
        return _failed("VISION_FAILED", request_id)
    return {
        "status": "ok",
        # The model that ACTUALLY answered: `fallbacks: "default"` may route to another.
        "model": getattr(message, "model", VISION_MODEL),
        "request_id": request_id,
        "identifies_practice": parsed.identifies_practice,
        "regions": [{"kind": r.kind, "label": r.label, "box": list(r.box), "confidence": r.confidence}
                    for r in parsed.regions],
        # `identifies_practice` with nothing to draw: the photograph still reaches the seller's
        # review and the manual mask is the tool (D-IDP-8).
        "unlocalised": parsed.identifies_practice and not parsed.regions,
    }
