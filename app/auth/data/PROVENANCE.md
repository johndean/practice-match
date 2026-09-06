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

**Required acknowledgement, verbatim:**

> Contains public sector information licensed under the Open Government Licence v3.0.

- **The list itself** is the National Cyber Security Centre's "Top 100,000 passwords"
  (derived from the Have I Been Pwned corpus), published by the NCSC as **Crown copyright**
  under the **Open Government Licence v3.0**
  (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), which
  permits copying, publishing and adapting it provided the source is acknowledged with the
  sentence above.
- **The SecLists repository** that redistributes it is **MIT** licensed
  (https://github.com/danielmiessler/SecLists/blob/master/LICENSE).

Neither licence requires attribution in the product UI — this list is never displayed, only
compared against — so the acknowledgement lives here rather than on a screen.
`tests/auth/test_passwords.py::test_provenance_carries_the_ogl_attribution_and_the_pinned_source`
keeps that sentence, the SHA-256 and the pinned commit in this file through any refresh.

## Refreshing it

Re-download from the raw URL above (pinning the new commit), update the SHA-256, line count
and entry count here **and** in `tests/auth/test_passwords.py`
(`LIST_SHA256`/`LIST_LINES`/`LIST_ENTRIES`/`LIST_COMMIT`), and re-run `poetry run pytest tests/auth`.
Those pins exist so that a silent swap of a security-critical list fails the suite. The OGL
acknowledgement above must survive any refresh — the list stays Crown copyright.

---

# `disposable_domains.txt` — provenance

The reviewer hint behind `app.auth.flags.compute`'s `disposable_domain` flag (spec §6). A flag is
**never** a decision: it is shown to the human reviewing an application and nothing in the code
path branches on one, so a stale or over-broad entry costs a reviewer a second glance, never an
applicant their account.

| | |
|---|---|
| Source | https://github.com/disposable-email-domains/disposable-email-domains — `disposable_email_blocklist.conf` |
| Raw URL | https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/main/disposable_email_blocklist.conf |
| Commit | `b4c9e0b23f1bc9c4799d957a1cbb99fe8e339301` (2026-09-06, "Add missing domains from sources (#1154)") |
| SHA-256 | `d3a8b8550c2edd25fe8fb9de07e30d9451dfb9ff5cfbd6bc8b984e3e26ce2389` |
| Size | 124 352 bytes · 8 737 lines · 8 737 domains loaded |
| Verified | 2026-09-07 — the vendored file is byte-identical to that raw URL on that commit |

## Licence and attribution

The list is dedicated to the public domain under **CC0 1.0 Universal**
(https://creativecommons.org/publicdomain/zero/1.0/): "You can copy, modify, distribute and use the
work, even for commercial purposes, all without asking permission." No attribution is required and
the list is never displayed, so — as with `top100k.txt` — the record lives here rather than on a
screen.

## Refreshing it

Re-download from the raw URL above (pinning the new commit), update the SHA-256, line count and
commit here **and** in `tests/api/test_applications.py`
(`LIST_SHA256`/`LIST_COMMIT`/`LIST_LINES`), and re-run `poetry run pytest tests/api/test_applications.py`.
Those pins exist so that a silent swap of the list fails the suite instead of passing quietly.
