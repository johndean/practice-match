"""Census Data API client (spec §3). Synchronous -- it runs inside Celery tasks.

Rules encoded here: explicit vintage in every URL (the dataset's `api_dataset_id`), a key
required to build a request, 15 s connect / 45 s read, retries with exponential backoff and
jitter on 5xx, 429 and transport errors (never other 4xx), a descriptive `User-Agent`, at most
four concurrent requests per dataset (halved on 429, floor 1, enforced by a real bounded
semaphore), a bounded response size, every raw response body archived once, and Census sentinels
normalised to `None` at parse time.

Round 1 of the A3 review (controller amendment A-C3b, 2026-09-09) closed at source here:
  - Every raised/logged message that could carry a URL passes through `redact()` -- the
    malformed-response and ragged-row errors included (C1/m1).
  - The archive key carries the `census/` prefix A-C2 ¶1 actually rules: `ObjectStore`
    (`app/storage.py`) has no `put_immutable` -- `fetch_table` checks `exists(key)` first and
    skips the `put` for a key already there, so a retried or re-run load never overwrites what
    an earlier run recorded (M1).
  - Only a 2xx response is a success; a 3xx is an error, `follow_redirects=False` is explicit on
    the client, and the body is parsed AND `validate_variables`-checked before anything is
    archived, so a body that fails either check can never occupy an archive key (M2).
  - `contact` is required: the constructor refuses `None`/empty with a `ValueError` naming no
    secret. The `User-Agent` never falls back to a default or a developer's own address (A-C1
    ¶4): it embeds exactly the `contact` its caller passed -- in production always
    `require_contact()`'s return value, the VIN Foundation's designated technical contact (M3).
  - The response body is read through a size bound (`MAX_RESPONSE_BYTES`), checked against a
    declared `Content-Length` up front and against the actually streamed total either way, so a
    truncated, mis-routed or hostile response is never parsed unbounded (m2).
  - The client owns its `httpx.Client` through `__enter__`/`__exit__`/`close()` (m3).
  - The per-dataset concurrency limit is a real `threading.BoundedSemaphore`, not bookkeeping;
    the 429-triggered halving and `request_count` are both lock-protected against concurrent
    callers (m4).
  - URL building is private (`_build_url`/`_archive_key`): `fetch_table` takes the raw
    `(get, for_, expected, in_, extra)` parameters and builds + discards the keyed URL entirely
    inside the client, so nothing public or logged ever carries it -- a keyed URL is therefore
    never a value a caller could pass as a Celery task argument (m5).
  - `httpx.TransportError` (a connection reset, a timeout below the client's own) joins the same
    bounded retry ladder as a 5xx, and a 429's `Retry-After` header is honoured up to
    `RETRY_AFTER_CAP`, falling back to the exponential ladder when it is absent or not a number
    (m6).

`require_key`/`require_contact` are the two hard-failure gates (`SystemExit(2)` -- A-C4 ¶2's
shared exit-code scheme, superseding A-C3 ¶2's `SystemExit(3)` -- naming the missing variable)
-- called ONLY at the ingest task and CLI entry points that are built in later
tasks (A5-A9, `scripts/census_load.py`), never here and never at import, so a service that does
not need Census settings can still boot without them (see `app/config.py`'s `census_api_key`/
`census_contact_email` comment). `CensusClient` itself never validates the key: it takes whatever
`api_key` its caller already resolved.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Self
from urllib.parse import quote, urlencode

import httpx

from app.census.registry import Dataset
from app.storage import ObjectStore
from app.version import VERSION

SENTINELS = {"-666666666", "-999999999", "-555555555", "-333333333", "-222222222", "-888888888", "", "null"}
RETRY_STATUSES = {429, *range(500, 600)}
MAX_RETRIES = 3
#: m2: a truncated, mis-routed or hostile response must not be parsed unbounded. A whole-state
#: ACS tract pull is a few MB; 64 MiB is generous headroom, not a realistic ceiling.
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
#: m6: a 429's `Retry-After` is honoured, but never past this many seconds -- an operator-facing
#: load must not be able to stall indefinitely on a server-named delay.
RETRY_AFTER_CAP = 30.0


def require_key(env: Mapping[str, str] = os.environ) -> str:
    """SystemExit(2): "refused before anything was opened" (A-C4 ¶2's shared exit-code scheme,
    which supersedes A-C3 ¶2's `SystemExit(3)` -- 3 now means "database unreachable")."""
    key = env.get("CENSUS_API_KEY")
    if not key:
        print("[census] CENSUS_API_KEY is not set — the ingest cannot start (spec §3: never fall back to unkeyed calls)", file=sys.stderr)
        raise SystemExit(2)
    return key


def require_contact(env: Mapping[str, str] = os.environ) -> str:
    """SystemExit(2) -- see `require_key`'s docstring; the two gates share one exit code."""
    contact = env.get("CENSUS_CONTACT_EMAIL")
    if not contact:
        print(
            "[census] CENSUS_CONTACT_EMAIL is not set — the ingest cannot start "
            "(spec §3 User-Agent; A-C1 ¶4: the VIN Foundation's designated technical contact, never a developer's own)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return contact


def redact(url: str) -> str:
    """Strips `key=...` from a URL wherever it is logged or raised (red-team C6)."""
    return re.sub(r"([?&]key=)[^&]+", r"\1<redacted>", url)


class CensusHTTPError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} from {redact(url)}")   # never leak the key into logs (red-team C6)
        self.status, self.url = status, redact(url)


class VariableMissing(Exception):
    def __init__(self, missing: list[str]):
        super().__init__(f"response lacks expected variables: {missing}")
        self.missing = missing


def normalise(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s in SENTINELS else s


def _bounded_body(resp: httpx.Response, url: str) -> bytes:
    """m2: reject past `MAX_RESPONSE_BYTES` from a declared `Content-Length` up front when the
    server sends one, and against the actually streamed total either way -- a false or absent
    header must never be trusted alone."""
    content_length = resp.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > MAX_RESPONSE_BYTES:
            raise ValueError(f"Census response declares {declared} bytes, over the {MAX_RESPONSE_BYTES}-byte limit, from {redact(url)}")
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise ValueError(f"Census response exceeds {MAX_RESPONSE_BYTES} bytes from {redact(url)}")
        chunks.append(chunk)
    return b"".join(chunks)


class CensusClient:
    def __init__(
        self,
        api_key: str,
        dataset: Dataset,
        archive: ObjectStore | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        version: str = VERSION,
        contact: str | None = None,
        concurrency: int = 4,
    ) -> None:
        if not contact:
            raise ValueError(
                "CensusClient requires `contact` for its User-Agent (A-C1 ¶4): the VIN Foundation's "
                "designated technical contact, never a default or a developer's own address"
            )
        self.api_key, self.dataset, self.archive, self._sleep = api_key, dataset, archive, sleep
        self.contact = contact
        self.timeout = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0)
        ua = f"PracticeMatch/{version} ({contact})"
        # follow_redirects=False (M2): a keyed URL's query string must never be handed to a
        # host a redirect names, and a followed 3xx would otherwise reach the parser as if it
        # were the real answer.
        self._http = httpx.Client(timeout=self.timeout, headers={"User-Agent": ua}, transport=transport, follow_redirects=False)
        self.concurrency = concurrency
        self._gate = threading.BoundedSemaphore(concurrency)
        self._lock = threading.Lock()   # m4: guards the concurrency/_gate swap and request_count
        self.request_count = 0

    # ---- URLs (m5: private -- a keyed URL is never a public value) ----------------------------
    def _build_url(self, get: list[str], for_: str, in_: str | None = None, extra: dict[str, str] | None = None) -> str:
        params = [("get", ",".join(get)), ("for", for_)]
        if in_:
            params.append(("in", in_))
        for k, v in (extra or {}).items():
            params.append((k, v))
        params.append(("key", self.api_key))
        # Census expects ':' '*' '+' and ',' unescaped in these parameters; `quote_via=quote`
        # (rather than urlencode's default `quote_plus`) so a literal space -- CBP's `zip code`
        # geography label (A-C6) -- reaches the wire as `%20`, never `+`.
        query = urlencode(params, safe=":*+,", quote_via=quote)
        return f"{self.dataset.base_url}/{self.dataset.api_dataset_id}?{query}"

    def _archive_key(self, url: str) -> str:
        public = re.sub(r"[?&]key=[^&]+", "", url)
        # M1: `census/` (A-C2 ¶1) -- app/storage.py's own docstring already documents this as
        # the Census archive's prefix.
        return f"census/raw/{self.dataset.dataset_key}/{self.dataset.vintage}/{hashlib.sha256(public.encode()).hexdigest()}.json"

    # ---- fetching -----------------------------------------------------------------------------
    def _get(self, url: str) -> bytes:
        attempt = 0
        while True:
            transport_delay: float | None = None
            with self._gate:
                with self._lock:
                    self.request_count += 1
                try:
                    with self._http.stream("GET", url) as resp:
                        status = resp.status_code
                        if 200 <= status < 300:   # M2: only 2xx is a success -- a 3xx is an error
                            return _bounded_body(resp, url)
                        retry_after = resp.headers.get("retry-after")
                except httpx.TransportError:   # m6: joins the same bounded retry ladder as a 5xx
                    if attempt == MAX_RETRIES:
                        raise
                    # The backoff sleep itself happens AFTER this `with self._gate:` block exits
                    # (below) -- a flapping connection must not hold a concurrency slot for the
                    # whole backoff window (fix-round re-review).
                    transport_delay = (2**attempt) + random.uniform(0, 0.5)
            if transport_delay is not None:
                self._sleep(transport_delay)
                attempt += 1
                continue
            if status == 429:
                with self._lock:
                    self.concurrency = max(1, self.concurrency // 2)
                    self._gate = threading.BoundedSemaphore(self.concurrency)
            if status not in RETRY_STATUSES or attempt == MAX_RETRIES:
                raise CensusHTTPError(status, url)
            delay = (2**attempt) + random.uniform(0, 0.5)
            if status == 429 and retry_after:   # m6: honour Retry-After, capped, else the ladder
                try:
                    # max(0.0, …) first: a negative or NaN Retry-After must never reach `sleep`
                    # (a bare `float(retry_after)` parses both without raising).
                    delay = min(max(0.0, float(retry_after)), RETRY_AFTER_CAP)
                except ValueError:
                    pass
            self._sleep(delay)
            attempt += 1

    def fetch_table(
        self,
        get: list[str],
        for_: str,
        expected: list[str],
        in_: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> list[dict[str, str | None]]:
        """Fetches, parses and validates one Census table; archives the raw body only after
        both the shape and `expected` variables check out (M2) -- the archive is append-only, so
        a body that failed validation must never occupy a key forever."""
        url = self._build_url(get, for_, in_, extra)
        body = self._get(url)
        table = json.loads(body)
        if not table or not isinstance(table[0], list):
            raise ValueError(f"unexpected Census response shape from {redact(url)}")
        header = table[0]
        rows: list[dict[str, str | None]] = []
        for i, row in enumerate(table[1:], start=1):
            try:
                rows.append({h: normalise(v) for h, v in zip(header, row, strict=True)})
            except ValueError as exc:
                raise ValueError(f"row {i} does not match the header length ({redact(url)})") from exc
        self.validate_variables(rows, expected)
        if self.archive is not None:
            key = self._archive_key(url)
            if not self.archive.exists(key):   # append-only by convention (A-C3): never re-write an archived key
                self.archive.put(key, body, "application/json")
        return rows

    @staticmethod
    def validate_variables(rows: list[dict[str, str | None]], expected: list[str]) -> None:
        present = set(rows[0].keys()) if rows else set()
        missing = [v for v in expected if v not in present]
        if missing:
            raise VariableMissing(missing)

    # ---- lifecycle (m3) -------------------------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()
