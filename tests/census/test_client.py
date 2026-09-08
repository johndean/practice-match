"""CensusClient (spec §3): key gate, contact gate (A-C1 ¶4; controller amendments A-C3/A-C3b),
URL building, sentinel normalisation, 5xx/429/transport-error retry with backoff, per-dataset
concurrency, and the raw-body archive.

Round 1 of the A3 review (controller amendment A-C3b, 2026-09-09) closed at source here:
  C1 -- every raised/logged message that could carry a URL passes through `redact()`, the
        malformed-response `ValueError` included.
  M1 -- the archive key carries the `census/` prefix A-C2 ¶1 actually rules.
  M2 -- only a 2xx response is a success; the body is parsed and `validate_variables` passes
        BEFORE anything is archived; `follow_redirects=False` is explicit; a 3xx is an error.
  M3 -- `contact` is required; the constructor refuses `None`/empty with a `ValueError`.
  m1 -- `zip(header, row, strict=True)`; a ragged row is an error naming its index.
  m2 -- `MAX_RESPONSE_BYTES` (64 MiB), checked from `Content-Length` when present and against
        the streamed body otherwise.
  m3 -- the client owns its `httpx.Client` through `__enter__`/`__exit__`/`close()`.
  m4 -- the concurrency limit is enforced with a bounded semaphore, tested with real overlapping
        threads, not just bookkeeping; the swap on 429 and `request_count` are lock-protected.
  m5 -- URL building is private (`_build_url`/`_archive_key`); `fetch_table` takes the raw
        (get, for_, expected, in_, extra) parameters and never hands a keyed URL to a caller.
  m6 -- `httpx.TransportError` joins the bounded retry ladder; a 429's `Retry-After` is honoured
        up to a cap, and falls back to the exponential ladder when absent or non-numeric.

The archive is the generic `app/storage.py` `ObjectStore` -- there is no `put_immutable`.
`fetch_table` checks `exists(key)` and skips the `put` when the key is already archived.

`httpx.MockTransport` throughout; no live call is ever made (A-C3 (4))."""
import hashlib
import json
import threading
import time

import httpx
import pytest

from app.census import client as client_module
from app.census.client import (
    MAX_RESPONSE_BYTES,
    RETRY_AFTER_CAP,
    CensusClient,
    CensusHTTPError,
    VariableMissing,
    redact,
    require_contact,
    require_key,
)
from app.census.registry import Dataset

ACS = Dataset("acs5", "ACS", "2023/acs/acs5", "https://api.census.gov/data", "2019\u20132023", None, "Annual (Dec)",
              "cleared", "Public domain", None, "Source: …", None, None)
TABLE = [["NAME", "B01003_001E", "B01003_001M", "state", "county", "tract"],
         ["Tract 1", "4321", "-555555555", "48", "453", "000101"],
         ["Tract 2", "-666666666", "120", "48", "453", "000102"]]


class Archive:
    """A fake matching app/storage.py's `ObjectStore` surface -- `exists`/`put` only, since
    there is no `put_immutable` (controller amendment A-C3 (1))."""

    def __init__(self, existing: tuple[str, ...] = ()):
        self.puts: list[tuple[str, bytes, str]] = []
        self._existing = set(existing)

    def exists(self, key: str) -> bool:
        return key in self._existing

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.puts.append((key, data, content_type))


def make(handler, archive=None, sleeps=None, **kwargs):
    return CensusClient("KEY123", ACS, archive, transport=httpx.MockTransport(handler),
                        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
                        version="0.1.0", contact="contact@vinfoundation.org", **kwargs)


# --- require_key / require_contact -----------------------------------------------------------

def test_require_key_exits_naming_the_variable(capsys):
    """A-C4 ¶2 / M-1 (A3 and A4 reviews): exit code 2 -- "refused before anything was opened" --
    not 3, which the shared scheme now reserves for "database unreachable" (A-C3 ¶2's
    `SystemExit(3)` is superseded)."""
    with pytest.raises(SystemExit) as e:
        require_key(env={})
    assert e.value.code == 2 and "CENSUS_API_KEY" in capsys.readouterr().err
    assert require_key(env={"CENSUS_API_KEY": "k"}) == "k"


def test_require_contact_exits_naming_the_variable(capsys):
    with pytest.raises(SystemExit) as e:
        require_contact(env={})
    assert e.value.code == 2 and "CENSUS_CONTACT_EMAIL" in capsys.readouterr().err
    assert require_contact(env={"CENSUS_CONTACT_EMAIL": "contact@vinfoundation.org"}) == "contact@vinfoundation.org"


# --- redact -------------------------------------------------------------------------------------

def test_redact_strips_the_key_param_from_a_url():
    url = "https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=SUPERSECRET"
    out = redact(url)
    assert "SUPERSECRET" not in out and out.endswith("key=<redacted>")


# --- construction: contact required (M3) ---------------------------------------------------

def test_contact_is_required_and_never_defaults():
    with pytest.raises(ValueError):
        CensusClient("KEY123", ACS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=TABLE)))


def test_contact_cannot_be_an_empty_string():
    with pytest.raises(ValueError):
        CensusClient("KEY123", ACS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=TABLE)), contact="")


def test_a_client_missing_contact_never_names_the_api_key():
    with pytest.raises(ValueError) as e:
        CensusClient("KEY123", ACS, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=TABLE)))
    assert "KEY123" not in str(e.value)


# --- User-Agent / follow_redirects (M2, M3) -------------------------------------------------

def test_user_agent_embeds_exactly_the_version_and_contact():
    seen = {}

    def handler(r):
        seen["ua"] = r.headers["user-agent"]
        return httpx.Response(200, json=TABLE)

    c = make(handler)
    c.fetch_table(["NAME"], "us:1", [])
    assert seen["ua"] == "PracticeMatch/0.1.0 (contact@vinfoundation.org)"


def test_follow_redirects_is_explicitly_false():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    assert c._http.follow_redirects is False


# --- fetch_table: shape, sentinels, archiving (m5 signature; C1; M1; M2) --------------------

def test_fetch_normalises_sentinels_and_archives_the_raw_body():
    archive = Archive()
    c = make(lambda r: httpx.Response(200, json=TABLE), archive)
    rows = c.fetch_table(["NAME", "B01003_001E", "B01003_001M"], "tract:*", ["B01003_001E", "B01003_001M"], "state:48")
    assert rows[0] == {"NAME": "Tract 1", "B01003_001E": "4321", "B01003_001M": None, "state": "48", "county": "453", "tract": "000101"}
    assert rows[1]["B01003_001E"] is None and rows[1]["B01003_001M"] == "120"
    assert len(archive.puts) == 1 and json.loads(archive.puts[0][1]) == TABLE and archive.puts[0][2] == "application/json"
    assert "KEY123" not in archive.puts[0][0]
    # M1: the archive key carries the census/ prefix A-C2 ¶1 rules.
    assert archive.puts[0][0].startswith("census/raw/acs5/2019\u20132023/")


def test_archive_key_matches_the_documented_scheme():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c._build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48+county:453")
    assert url == "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01003_001E,B01003_001M&for=tract:*&in=state:48+county:453&key=KEY123"
    assert c._archive_key(url) == "census/raw/acs5/2019\u20132023/" + hashlib.sha256(url.replace("&key=KEY123", "").encode()).hexdigest() + ".json"


def test_build_url_omits_in_when_not_given():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c._build_url(["NAME"], "us:1")
    assert url == "https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123"


def test_build_url_supports_extra_params():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c._build_url(["NAME"], "county:*", "state:06", extra={"NAICS2017": "541940"})
    assert "NAICS2017=541940" in url and url.endswith("&key=KEY123")


def test_fetch_normalises_a_literal_json_null_to_none():
    """Spec §3 sentinels: `-666666666`, `-999999999`, `null` -- the third arrives as a literal
    JSON null in the raw body, not a string, which is a separate branch from the string
    sentinels above."""
    table = [["NAME", "B01003_001E"], ["Tract 3", None]]
    c = make(lambda r: httpx.Response(200, json=table))
    rows = c.fetch_table(["NAME", "B01003_001E"], "tract:*", [], "state:48")
    assert rows[0] == {"NAME": "Tract 3", "B01003_001E": None}


def test_fetch_skips_archiving_a_key_that_already_exists():
    """A-C3 (1): the archive is append-only BY CONVENTION -- `exists(key)` then `put`, never a
    second write for a key already there."""
    probe = make(lambda r: httpx.Response(200, json=TABLE))
    url = probe._build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48")
    archive = Archive(existing=(probe._archive_key(url),))
    c = make(lambda r: httpx.Response(200, json=TABLE), archive)
    rows = c.fetch_table(["NAME", "B01003_001E", "B01003_001M"], "tract:*", [], "state:48")
    assert archive.puts == [] and len(rows) == 2


def test_fetch_rejects_an_unexpected_response_shape_without_leaking_the_key():
    """C1: this is the exact path that leaked the API key -- a malformed body's error message
    must be redacted like every other raise in this module."""
    c = make(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ValueError) as e:
        c.fetch_table(["NAME"], "us:1", [])
    assert "KEY123" not in str(e.value)


def test_fetch_rejects_a_ragged_row_naming_its_index_without_leaking_the_key():
    """m1: `zip(..., strict=True)` -- a row shorter (or longer) than the header must abort
    rather than silently produce a partial record."""
    table = [["NAME", "B01003_001E"], ["Tract 1", "100"], ["Tract 2"]]
    c = make(lambda r: httpx.Response(200, json=table))
    with pytest.raises(ValueError) as e:
        c.fetch_table(["NAME", "B01003_001E"], "tract:*", [], "state:48")
    assert "row 2" in str(e.value)
    assert "KEY123" not in str(e.value)


def test_fetch_validates_variables_before_archiving_and_archives_nothing_on_failure():
    """M2: `validate_variables` must pass BEFORE anything is archived -- an archive written
    ahead of validation would be an unrecoverable orphan (the archive is append-only)."""
    archive = Archive()
    c = make(lambda r: httpx.Response(200, json=TABLE), archive)
    with pytest.raises(VariableMissing):
        c.fetch_table(["NAME", "B01003_001E", "B01003_001M"], "tract:*", ["B01003_001E", "B19013_001E"], "state:48")
    assert archive.puts == []


def test_fetch_succeeds_and_archives_when_the_expected_variables_are_present():
    archive = Archive()
    c = make(lambda r: httpx.Response(200, json=TABLE), archive)
    rows = c.fetch_table(["NAME", "B01003_001E", "B01003_001M"], "tract:*", ["B01003_001E", "B01003_001M"], "state:48")
    assert len(rows) == 2 and len(archive.puts) == 1


# --- 2xx-only success / 3xx is an error (M2) ------------------------------------------------

def test_a_3xx_response_is_an_error_not_a_success():
    c = make(lambda r: httpx.Response(302, headers={"Location": "https://example.org/elsewhere"}))
    with pytest.raises(CensusHTTPError) as e:
        c.fetch_table(["NAME"], "us:1", [])
    assert e.value.status == 302


# --- retry ladder: 5xx, 429, 4xx, transport errors, Retry-After (m6) -------------------------

def test_retries_5xx_three_times_with_backoff_then_raises():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(503)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    with pytest.raises(CensusHTTPError) as e:
        c.fetch_table(["NAME"], "us:1", [])
    assert len(calls) == 4 and e.value.status == 503
    assert "KEY123" not in str(e.value) and "KEY123" not in e.value.url     # red-team C6: key never in errors/logs
    assert len(sleeps) == 3 and sleeps[0] < sleeps[1] < sleeps[2]


def test_recovers_after_transient_500():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 3 else httpx.Response(200, json=TABLE)

    rows = make(handler).fetch_table(["NAME"], "us:1", [])
    assert len(calls) == 3 and len(rows) == 2


def test_does_not_retry_4xx():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(400, text="unknown variable")

    with pytest.raises(CensusHTTPError) as e:
        make(handler).fetch_table(["NOPE"], "us:1", [])
    assert len(calls) == 1 and e.value.status == 400


def test_429_halves_concurrency_and_retries():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=TABLE)

    c = make(handler)
    assert c.concurrency == 4
    c.fetch_table(["NAME"], "us:1", [])
    assert c.concurrency == 2 and len(calls) == 2


def test_concurrency_floor_never_goes_below_one():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429) if len(calls) <= 2 else httpx.Response(200, json=TABLE)

    c = make(handler, concurrency=1)
    c.fetch_table(["NAME"], "us:1", [])
    assert c.concurrency == 1 and len(calls) == 3


def test_transport_errors_join_the_retry_ladder_and_recover():
    calls = []

    def handler(r):
        calls.append(1)
        if len(calls) < 2:
            raise httpx.ReadTimeout("boom", request=r)
        return httpx.Response(200, json=TABLE)

    rows = make(handler).fetch_table(["NAME"], "us:1", [])
    assert len(calls) == 2 and len(rows) == 2


def test_transport_errors_exhaust_the_bounded_ladder_and_raise():
    calls = []

    def handler(r):
        calls.append(1)
        raise httpx.ConnectError("boom", request=r)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    with pytest.raises(httpx.ConnectError):
        c.fetch_table(["NAME"], "us:1", [])
    assert len(calls) == 4 and len(sleeps) == 3


def test_429_honours_a_small_retry_after_verbatim():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "2"}) if len(calls) == 1 else httpx.Response(200, json=TABLE)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    c.fetch_table(["NAME"], "us:1", [])
    assert sleeps == [2.0]


def test_429_caps_a_large_retry_after():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "9999"}) if len(calls) == 1 else httpx.Response(200, json=TABLE)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    c.fetch_table(["NAME"], "us:1", [])
    assert sleeps == [RETRY_AFTER_CAP]


def test_429_without_retry_after_falls_back_to_the_backoff_ladder():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=TABLE)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    c.fetch_table(["NAME"], "us:1", [])
    assert 1.0 <= sleeps[0] < 1.5


def test_429_with_a_non_numeric_retry_after_falls_back_to_the_backoff_ladder():
    calls = []

    def handler(r):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        return httpx.Response(200, json=TABLE)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    c.fetch_table(["NAME"], "us:1", [])
    assert 1.0 <= sleeps[0] < 1.5


# --- concurrency: real enforcement, not bookkeeping (m4) -------------------------------------

def test_concurrency_gate_actually_serialises_overlapping_calls():
    """m4: the bounded semaphore must genuinely gate concurrent requests. With concurrency=1,
    two overlapping fetches on real threads must never both be in flight."""
    peak = []
    current = 0
    state_lock = threading.Lock()

    def handler(r):
        nonlocal current
        with state_lock:
            current += 1
            peak.append(current)
        time.sleep(0.05)
        with state_lock:
            current -= 1
        return httpx.Response(200, json=TABLE)

    c = make(handler, concurrency=1)
    threads = [threading.Thread(target=c.fetch_table, args=(["NAME"], "us:1", [])) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(2)
    assert max(peak) == 1


def test_request_count_is_accurate_under_concurrent_calls():
    """m4: `request_count += 1` must not lose updates under real concurrency."""

    def handler(r):
        return httpx.Response(200, json=TABLE)

    c = make(handler, concurrency=4)
    threads = [threading.Thread(target=c.fetch_table, args=(["NAME"], "us:1", [])) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(2)
    assert c.request_count == 8


# --- response size bound (m2) ----------------------------------------------------------------

def test_rejects_a_response_that_declares_an_oversized_content_length():
    def handler(r):
        # A real 64 MiB body is wasteful to construct for a unit test -- the DECLARED
        # Content-Length alone must reject the response before any of it is read.
        return httpx.Response(200, json=TABLE, headers={"content-length": str(MAX_RESPONSE_BYTES + 1)})

    c = make(handler)
    with pytest.raises(ValueError) as e:
        c.fetch_table(["NAME"], "us:1", [])
    assert "KEY123" not in str(e.value)


def test_rejects_a_streamed_body_that_exceeds_the_bound_without_a_content_length_header(monkeypatch):
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", 10)

    def gen():
        yield b"0123456789"
        yield b"more than the bound"

    c = make(lambda r: httpx.Response(200, content=gen()))
    with pytest.raises(ValueError) as e:
        c.fetch_table(["NAME"], "us:1", [])
    assert "KEY123" not in str(e.value)


def test_a_non_numeric_content_length_is_ignored_and_the_streamed_total_still_governs():
    """A malformed `Content-Length` (not an int) must not crash the bound check -- it falls
    through to the streamed-total check, which still applies."""
    c = make(lambda r: httpx.Response(200, json=TABLE, headers={"content-length": "not-a-number"}))
    rows = c.fetch_table(["NAME"], "us:1", [])
    assert len(rows) == 2


def test_accepts_a_response_within_the_bound(monkeypatch):
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", 10_000)
    rows = make(lambda r: httpx.Response(200, json=TABLE)).fetch_table(["NAME"], "us:1", [])
    assert len(rows) == 2


# --- validate_variables ------------------------------------------------------------------------

def test_validate_variables_aborts_on_missing_column():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    rows = c.fetch_table(["NAME", "B01003_001E", "B01003_001M"], "tract:*", [], "state:48")
    CensusClient.validate_variables(rows, ["B01003_001E", "B01003_001M"])
    with pytest.raises(VariableMissing) as e:
        CensusClient.validate_variables(rows, ["B01003_001E", "B19013_001E"])
    assert e.value.missing == ["B19013_001E"]


def test_validate_variables_treats_no_rows_as_missing_everything():
    with pytest.raises(VariableMissing) as e:
        CensusClient.validate_variables([], ["NAME"])
    assert e.value.missing == ["NAME"]


# --- timeouts ------------------------------------------------------------------------------------

def test_timeouts_are_the_spec_values():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    assert c.timeout.connect == 15.0 and c.timeout.read == 45.0


# --- context manager (m3) -----------------------------------------------------------------------

def test_client_is_a_context_manager_that_closes_its_http_client():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    assert c._http.is_closed is False
    with c as ctx:
        assert ctx is c
        assert c._http.is_closed is False
    assert c._http.is_closed is True


def test_close_can_be_called_directly():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    c.close()
    assert c._http.is_closed is True
