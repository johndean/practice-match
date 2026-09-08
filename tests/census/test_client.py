"""CensusClient (spec §3): key gate, contact gate (A-C1 ¶4; controller amendment A-C3), URL
building, sentinel normalisation, 5xx/429 retry with backoff, per-dataset concurrency, and the
raw-body archive.

The archive is the generic app/storage.py `ObjectStore` (controller amendments A-C2/A-C3) --
there is no `put_immutable`. `fetch_table` checks `exists(key)` and skips the `put` when the key
is already archived, which is what makes the archive immutable BY CONVENTION (the caller's
discipline, per app/storage.py's own docstring) rather than by a storage-layer guarantee.

`httpx.MockTransport` throughout; no live call is ever made (A-C3 (4))."""
import hashlib
import json

import httpx
import pytest

from app.census.client import CensusClient, CensusHTTPError, VariableMissing, redact, require_contact, require_key
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


def make(handler, archive=None, sleeps=None):
    return CensusClient("KEY123", ACS, archive, transport=httpx.MockTransport(handler),
                        sleep=(sleeps.append if sleeps is not None else (lambda s: None)), version="0.1.0", contact="john@vetvision.org")


def test_require_key_exits_naming_the_variable(capsys):
    with pytest.raises(SystemExit) as e:
        require_key(env={})
    assert e.value.code == 3 and "CENSUS_API_KEY" in capsys.readouterr().err
    assert require_key(env={"CENSUS_API_KEY": "k"}) == "k"


def test_require_contact_exits_naming_the_variable(capsys):
    with pytest.raises(SystemExit) as e:
        require_contact(env={})
    assert e.value.code == 3 and "CENSUS_CONTACT_EMAIL" in capsys.readouterr().err
    assert require_contact(env={"CENSUS_CONTACT_EMAIL": "contact@vinfoundation.org"}) == "contact@vinfoundation.org"


def test_build_url_matches_spec_shape():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48+county:453")
    assert url == "https://api.census.gov/data/2023/acs/acs5?get=NAME,B01003_001E,B01003_001M&for=tract:*&in=state:48+county:453&key=KEY123"
    assert c.archive_key(url) == "raw/acs5/2019\u20132023/" + hashlib.sha256(url.replace("&key=KEY123", "").encode()).hexdigest() + ".json"


def test_build_url_omits_in_when_not_given():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c.build_url(["NAME"], "us:1")
    assert url == "https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123"


def test_build_url_supports_extra_params():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c.build_url(["NAME"], "county:*", "state:06", extra={"NAICS2017": "541940"})
    assert "NAICS2017=541940" in url and url.endswith("&key=KEY123")


def test_fetch_normalises_sentinels_and_archives_the_raw_body():
    seen = {}

    def handler(r):
        seen["ua"] = r.headers["user-agent"]
        return httpx.Response(200, json=TABLE)

    archive = Archive()
    c = make(handler, archive)
    rows = c.fetch_table(c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48"))
    assert rows[0] == {"NAME": "Tract 1", "B01003_001E": "4321", "B01003_001M": None, "state": "48", "county": "453", "tract": "000101"}
    assert rows[1]["B01003_001E"] is None and rows[1]["B01003_001M"] == "120"
    assert seen["ua"] == "PracticeMatch/0.1.0 (john@vetvision.org)"
    assert len(archive.puts) == 1 and json.loads(archive.puts[0][1]) == TABLE and archive.puts[0][2] == "application/json"
    assert "KEY123" not in archive.puts[0][0]


def test_fetch_normalises_a_literal_json_null_to_none():
    """Spec §3 sentinels: `-666666666`, `-999999999`, `null` -- the third arrives as a literal
    JSON null in the raw body, not a string, which is a separate branch from the string
    sentinels above."""
    table = [["NAME", "B01003_001E"], ["Tract 3", None]]
    c = make(lambda r: httpx.Response(200, json=table))
    rows = c.fetch_table(c.build_url(["NAME", "B01003_001E"], "tract:*", "state:48"))
    assert rows[0] == {"NAME": "Tract 3", "B01003_001E": None}


def test_fetch_skips_archiving_a_key_that_already_exists():
    """A-C3 (1): the archive is append-only BY CONVENTION -- `exists(key)` then `put`, never a
    second write for a key already there."""
    c = make(lambda r: httpx.Response(200, json=TABLE))
    url = c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48")
    archive = Archive(existing=(c.archive_key(url),))
    c2 = make(lambda r: httpx.Response(200, json=TABLE), archive)
    rows = c2.fetch_table(url)
    assert archive.puts == [] and len(rows) == 2


def test_fetch_rejects_an_unexpected_response_shape():
    c = make(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ValueError):
        c.fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")


def test_retries_5xx_three_times_with_backoff_then_raises():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(503)

    sleeps = []
    c = make(handler, sleeps=sleeps)
    with pytest.raises(CensusHTTPError) as e:
        c.fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert len(calls) == 4 and e.value.status == 503
    assert "KEY123" not in str(e.value) and "KEY123" not in e.value.url     # red-team C6: key never in errors/logs
    assert len(sleeps) == 3 and sleeps[0] < sleeps[1] < sleeps[2]


def test_recovers_after_transient_500():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 3 else httpx.Response(200, json=TABLE)

    rows = make(handler).fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert len(calls) == 3 and len(rows) == 2


def test_does_not_retry_4xx():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(400, text="unknown variable")

    with pytest.raises(CensusHTTPError) as e:
        make(handler).fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NOPE&for=us:1&key=KEY123")
    assert len(calls) == 1 and e.value.status == 400


def test_429_halves_concurrency_and_retries():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=TABLE)

    c = make(handler)
    assert c.concurrency == 4
    c.fetch_table("https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=KEY123")
    assert c.concurrency == 2 and len(calls) == 2


def test_validate_variables_aborts_on_missing_column():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    rows = c.fetch_table(c.build_url(["NAME", "B01003_001E", "B01003_001M"], "tract:*", "state:48"))
    c.validate_variables(rows, ["B01003_001E", "B01003_001M"])
    with pytest.raises(VariableMissing) as e:
        c.validate_variables(rows, ["B01003_001E", "B19013_001E"])
    assert e.value.missing == ["B19013_001E"]


def test_validate_variables_treats_no_rows_as_missing_everything():
    with pytest.raises(VariableMissing) as e:
        CensusClient.validate_variables([], ["NAME"])
    assert e.value.missing == ["NAME"]


def test_timeouts_are_the_spec_values():
    c = make(lambda r: httpx.Response(200, json=TABLE))
    assert c.timeout.connect == 15.0 and c.timeout.read == 45.0


def test_redact_strips_the_key_param_from_a_url():
    url = "https://api.census.gov/data/2023/acs/acs5?get=NAME&for=us:1&key=SUPERSECRET"
    out = redact(url)
    assert "SUPERSECRET" not in out and out.endswith("key=<redacted>")
