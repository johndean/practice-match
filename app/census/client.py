"""Census Data API client (spec §3). Synchronous -- it runs inside Celery tasks.

Rules encoded here: explicit vintage in every URL (the dataset's `api_dataset_id`), a key
required to build a request, 15 s connect / 45 s read, three retries with exponential backoff
and jitter on 5xx and 429 only (never other 4xx), a descriptive `User-Agent`, at most four
concurrent requests per dataset (halved on 429, floor 1), every raw response body archived
once, and Census sentinels normalised to `None` at parse time.

Archive (controller amendments A-C2/A-C3): `ObjectStore` (`app/storage.py`) has no
`put_immutable` -- `put` always writes. This module keeps the archive immutable BY CONVENTION:
`fetch_table` checks `exists(key)` first and skips the `put` for a key already there, so a
retried or re-run load never overwrites what an earlier run recorded.

`require_key`/`require_contact` are the two hard-failure gates (`SystemExit(3)`, naming the
missing variable) -- called ONLY at the ingest task and CLI entry points that are built in later
tasks (A5-A9, `scripts/census_load.py`), never here and never at import, so a service that does
not need Census settings can still boot without them (see `app/config.py`'s `census_api_key`/
`census_contact_email` comment). `CensusClient` itself never validates either value: it takes
whatever `api_key`/`contact` its caller already resolved.

The `User-Agent` never falls back to a default or a developer's own address (A-C1 ¶4;
controller amendment A-C3 (2)): it embeds exactly the `contact` its caller passed, which in
production is always `require_contact()`'s return value -- the VIN Foundation's designated
technical contact.
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
from urllib.parse import urlencode

import httpx

from app.census.registry import Dataset
from app.storage import ObjectStore
from app.version import VERSION

SENTINELS = {"-666666666", "-999999999", "-555555555", "-333333333", "-222222222", "-888888888", "", "null"}
RETRY_STATUSES = {429, *range(500, 600)}
MAX_RETRIES = 3


def require_key(env: Mapping[str, str] = os.environ) -> str:
    key = env.get("CENSUS_API_KEY")
    if not key:
        print("[census] CENSUS_API_KEY is not set — the ingest cannot start (spec §3: never fall back to unkeyed calls)", file=sys.stderr)
        raise SystemExit(3)
    return key


def require_contact(env: Mapping[str, str] = os.environ) -> str:
    contact = env.get("CENSUS_CONTACT_EMAIL")
    if not contact:
        print(
            "[census] CENSUS_CONTACT_EMAIL is not set — the ingest cannot start "
            "(spec §3 User-Agent; A-C1 ¶4: the VIN Foundation's designated technical contact, never a developer's own)",
            file=sys.stderr,
        )
        raise SystemExit(3)
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
        self.api_key, self.dataset, self.archive, self._sleep = api_key, dataset, archive, sleep
        self.timeout = httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0)
        ua = f"PracticeMatch/{version} ({contact})"
        self._http = httpx.Client(timeout=self.timeout, headers={"User-Agent": ua}, transport=transport)
        self.concurrency = concurrency
        self._gate = threading.BoundedSemaphore(concurrency)
        self.request_count = 0

    # ---- URLs ---------------------------------------------------------------
    def build_url(self, get: list[str], for_: str, in_: str | None = None, extra: dict[str, str] | None = None) -> str:
        params = [("get", ",".join(get)), ("for", for_)]
        if in_:
            params.append(("in", in_))
        for k, v in (extra or {}).items():
            params.append((k, v))
        params.append(("key", self.api_key))
        # Census expects ':' '*' '+' and ',' unescaped in these parameters.
        query = urlencode(params, safe=":*+,")
        return f"{self.dataset.base_url}/{self.dataset.api_dataset_id}?{query}"

    def archive_key(self, url: str) -> str:
        public = re.sub(r"[?&]key=[^&]+", "", url)
        return f"raw/{self.dataset.dataset_key}/{self.dataset.vintage}/{hashlib.sha256(public.encode()).hexdigest()}.json"

    # ---- fetching -------------------------------------------------------------
    def _get(self, url: str) -> httpx.Response:
        attempt = 0
        while True:
            with self._gate:
                self.request_count += 1
                resp = self._http.get(url)
            if resp.status_code < 400:
                return resp
            if resp.status_code == 429:
                self.concurrency = max(1, self.concurrency // 2)
                self._gate = threading.BoundedSemaphore(self.concurrency)
            if resp.status_code not in RETRY_STATUSES or attempt == MAX_RETRIES:
                raise CensusHTTPError(resp.status_code, url)
            self._sleep((2**attempt) + random.uniform(0, 0.5))
            attempt += 1

    def fetch_table(self, url: str) -> list[dict[str, str | None]]:
        resp = self._get(url)
        body = resp.content
        if self.archive is not None:
            key = self.archive_key(url)
            if not self.archive.exists(key):   # append-only by convention (A-C3): never re-write an archived key
                self.archive.put(key, body, "application/json")
        table = json.loads(body)
        if not table or not isinstance(table[0], list):
            raise ValueError(f"unexpected Census response shape from {url}")
        header = table[0]
        return [{h: normalise(v) for h, v in zip(header, row)} for row in table[1:]]

    @staticmethod
    def validate_variables(rows: list[dict[str, str | None]], expected: list[str]) -> None:
        present = set(rows[0].keys()) if rows else set()
        missing = [v for v in expected if v not in present]
        if missing:
            raise VariableMissing(missing)
