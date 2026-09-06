# `top100k.txt` — provenance

The offline fallback for the HIBP screen (`app/auth/passwords.py`, decision A4): when the
Have I Been Pwned range API is unreachable or `HIBP_ENABLED=false`, this list is the whole
breach screen. It is vendored rather than fetched at runtime so a degraded network cannot
also degrade it to nothing.

| | |
|---|---|
| Source | https://github.com/danielmiessler/SecLists — `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt` |
| Raw URL | https://raw.githubusercontent.com/danielmiessler/SecLists/1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56/Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt |
| Commit | `1a7bb9127eca9e6ff2fc0301c597fe6e16a0cb56` (2025-11-19, "fix(wordlist): Removed duplicate lines from NCSC 100k passwords wordlist") |
| SHA-256 | `c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0` |
| Size | 835 538 bytes · 99 840 lines (one blank) · 99 839 distinct passwords loaded |
| Verified | 2026-09-06 — the vendored file is byte-identical to that commit's blob |

## Licence and attribution

- **The list itself** is the National Cyber Security Centre's "Top 100,000 passwords"
  (derived from the Have I Been Pwned corpus), published by the NCSC as **Crown copyright**
  under the **Open Government Licence v3.0**
  (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), which
  permits copying, publishing and adapting it provided the source is acknowledged.
  Acknowledgement: *Contains public sector information licensed under the Open Government
  Licence v3.0 — NCSC "Top 100,000 passwords".*
- **The SecLists repository** that redistributes it is **MIT** licensed
  (https://github.com/danielmiessler/SecLists/blob/master/LICENSE).

Neither licence requires attribution in the product UI — this list is never displayed, only
compared against — so the acknowledgement lives here rather than on a screen.

## Refreshing it

Re-download from the raw URL above (pinning the new commit), update the SHA-256, line count
and entry count here **and** in `tests/auth/test_passwords.py`
(`LIST_SHA256`/`LIST_LINES`/`LIST_ENTRIES`), and re-run `poetry run pytest tests/auth`. Those
pins exist so that a silent swap of a security-critical list fails the suite.
