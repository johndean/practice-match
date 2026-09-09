# Market data API — integration contract

**Audience:** Sub-project 2 (the buyer/seller frontend) wiring the map and Community Context
cards to real data, and whoever builds the admin **Data Sources** tab. **Status:** Census Phase B
is closed as of this document (Task B6); it describes what the phase actually shipped, not what
the plan first sketched. Two sections below say plainly what the phase left open — read those
before assuming a field exists.

This document is generated from, and kept honest against, the running code: `tests/api/
test_contract_doc.py` fails if a route below stops matching `app.api.market`/`app.api.
admin_data_sources`, or if this document stops naming the fixture field names the frontend reads.
It does not fail if the *prose* goes stale, so treat the route list and JSON shapes as the source
of truth and the surrounding sentences as commentary.

## Routes

| Method | Path | Guard |
|---|---|---|
| GET | `/api/layers` | `market.read` |
| GET | `/api/markets` | `market.read` |
| GET | `/api/markets/{cbsa}/communities` | `market.read` |
| GET | `/api/listings/{listing_id}/market` | `market.read` |
| GET | `/api/admin/data-sources` | `data_sources.read` (staff/admin) |
| POST | `/api/admin/data-sources/{dataset_key}/license` | `licence.decide` (admin, re-authenticated within 10 minutes) |

**Mounted only while `SITE_MODE=app`.** All six routes live inside `app/main.py`'s `if
settings.site_mode == "app":` block, the same gate `admin_users_router`/`listings_router` sit
behind. Production runs `coming_soon` until launch (`CLAUDE.md`), so on production today every one
of these paths 404s through `not_found_router`, exactly like every other member or admin surface —
this is not a bug to route around, it is the same launch gate the rest of the app uses.

**The permission model widens rather than bypasses.** `market.read` is granted to an `active`
account holding `buyer`/`seller`/`staff`/`admin`, or an `api_token` carrying one of those roles.
`MARKET_DATA_PUBLIC=true` does **not** remove the `Depends(require("market.read"))` on any route —
it widens who satisfies it: `app.auth.permissions.allowed` additionally grants `market.read` to
`anonymous` while the flag is set (spec §15; Task I9a). The four `market.py` routes resolve this
dependency **once, at import time**, into a module-level constant (`REQUIRE_MARKET_READ`) rather
than re-wrapping it per route — `tests/auth/test_permissions.py` walks every mounted route and
resolves its guard by object identity, so a fresh `require(...)` call per route would read as
unguarded. `MARKET_DATA_PUBLIC` stays `false` in every environment today (John's ruling, A-C13
(3)); `GET /api/config` publishes the flag's current value unconditionally so the frontend's own
`can('market.read', …)` check can honour the same rule without a second, drifting copy of it.

`/api/admin/*` above uses `data_sources.read` (staff or admin) for both routes, plus
`licence.decide` (admin only, and in `permissions.REAUTH` — an `api_token` can never satisfy it)
on `/license` alone.

## `GET /api/layers`

Every layer, in a fixed order, regardless of licence status — a blocked or disabled layer is
still LISTED (so the UI can render it as unavailable), just never carries data:

```json
[
  { "key": "income", "label": "Median Household Income", "dataset_key": "acs5",
    "source_label": "Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023",
    "vintage": "2019–2023", "geo_level": "place|catchment", "state": "enabled",
    "is_derived": false, "caveat": null },
  { "key": "pets", "label": "Pet Ownership (est.)", "dataset_key": "acs5", "state": "enabled",
    "is_derived": true, "caveat": "Derived estimate: households × 0.57 (national placeholder rate until a licensed regional rate is cleared)." },
  { "key": "growth", "label": "Population Growth", "dataset_key": "acs5_prior",
    "vintage": "2014–2018 → 2019–2023", "geo_level": "place", "state": "enabled", "is_derived": true,
    "caveat": "Change between two ACS 5-year periods, measured for the listing's city/CDP." },
  { "key": "households", "label": "Households", "dataset_key": "acs5", "state": "enabled", "is_derived": false, "caveat": null },
  { "key": "econ", "label": "Average Practice Payroll", "dataset_key": "cbp", "geo_level": "county",
    "state": "enabled", "is_derived": true,
    "caveat": "Payroll per establishment (NAICS 541940), not revenue; county level." },
  { "key": "competition", "label": "Veterinary Competition", "dataset_key": "zbp", "geo_level": "zcta",
    "state": "blocked", "blocked_reason": "Counsel declined the terms.", "is_derived": false,
    "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. ZIP-code counts aggregated to the community." },
  { "key": "practices", "label": "Practice Listings", "dataset_key": null, "state": "enabled", "is_derived": false, "caveat": null },
  { "key": "drive_10", "label": "5–10 min drive time", "dataset_key": null, "state": "enabled", "is_derived": true, "caveat": "Straight-line 8 km approximation of drive time." },
  { "key": "drive_20", "label": "10–20 min drive time", "dataset_key": null, "state": "enabled", "is_derived": true, "caveat": "Straight-line 16 km approximation of drive time." }
]
```

**`state` is three-valued, never a bare boolean** (`enabled` / `disabled` / `blocked`, plus
`blocked_reason` only when `blocked`) — `dataset_registry.license_status`'s `cleared` /
`unresolved` / `blocked` (migration `017`'s own CHECK constraint), mapped straight across. "Off
because a member turned a layer off" and "off because the licence is not cleared" are different
facts the frontend and the admin surface both need to tell apart (A-C14 (4)); "off because it is
not yet cleared" (`disabled`) is not the same as "off because the licence was refused"
(`blocked`) — the first can still change, the second is a standing decision until an admin revisits
it. `practices`/`drive_10`/`drive_20` carry no `dataset_key` at all and are always `enabled`.

A licence decision on `/api/admin/data-sources/{key}/license` is reflected here within 60 seconds
(spec §11): `app.census.gate`'s Redis counter is bumped on every decision and rides inside the
market-payload cache key below, so a stale answer cannot outlive the decision by more than the
gate's own TTL.

## `GET /api/markets`

```json
[ { "cbsa_geoid": "12420", "name": "Austin, TX", "center": [30.31, -97.75], "zoom": 10 } ]
```

One row per CBSA that has at least one **published** listing (`listing.status = 'published'`),
named with the design's short form (`short_market_name`: `"Austin-Round Rock-San Marcos, TX Metro
Area"` → `"Austin, TX"`).

## `GET /api/markets/{cbsa}/communities?band=place|drive_10|drive_20` (default `place`)

```json
{
  "band": "place", "vintage": "2019–2023",
  "attribution": ["Source: U.S. Census Bureau, American Community Survey 5-Year Estimates, 2019–2023", "…"],
  "communities": [
    { "listing_id": "…", "name": "Cedar Park city", "geo_precision": "rooftop",
      "location": "place_centroid", "lat": 30.55, "lng": -97.80,
      "pop": 81900, "hh": 27600, "income": 118400, "growth": 14.2, "pets": 15732, "econ": 685000, "vets": 7,
      "competition": { "count": 7, "geo_level": "zcta", "zctas": 2, "per_10k_households": 2.54, "level": "High" },
      "suppressed": [] }
  ]
}
```

Restricted to **published** listings only (`WHERE l.status = 'published'` in the query itself, not
a post-filter). `location` is `"disclosed_point"` (the listing's own geocoded point) only when the
seller has disclosed location AND a point exists; otherwise `"place_centroid"`, and `lat`/`lng`
follow whichever one is used.

**Fixture field names, numeric and un-formatted** — see the mapping table below for where each one
comes from. A field is simply **absent** from a community object, rather than `null`, whenever its
underlying dataset is not licence-cleared, its `market_metric` row does not exist yet, or (Phase C
only) the layer has been turned off. A field whose `market_metric` row is `suppressed` (too
imprecise at this geography — a data-quality decision, independent of licensing) instead has its
NAME listed in `suppressed` and carries no numeric key at all: `"hh" not in community` and `"hh" in
community["suppressed"]`, never a fabricated value and never a bare `null`.

`competition` is assembled from **two separate** `market_metric` rows (`establishments` and
`vets_per_10k_households`) after the fact, because either can be suppressed independently of the
other; a community always carries `count`/`geo_level`/`zctas` when the establishment count exists,
and only carries `per_10k_households`/`level` when the ratio row is *also* present and unsuppressed.
`level` (`Low` / `Moderate` / `High`, thresholds `< 1.4` / `< 2.2` / else) is computed here at
serialisation time from `metrics.competition_level`, never stored — it is a presentation band on a
measurement, not a measurement itself (A-C15 (7)).

## `GET /api/listings/{listing_id}/market?band=drive_10|drive_20|place` (default `drive_10`)

```json
{
  "listing_id": "…", "band": "drive_10", "geo_precision": "tract", "vintage": "2019–2023",
  "computed_at": "2026-09-10T02:00:00+00:00",
  "metrics": {
    "population":                { "value": 44800, "unit": "count", "is_derived": false, "formula_version": null, "moe": 2140, "suppressed": false, "suppress_reason": null, "source_dataset": "acs5", "vintage": "2019–2023", "geo_level": "catchment", "inputs": {"acs5": "2019–2023"} },
    "households":                { "…": "…" },
    "median_hh_income":          { "…": "…", "unit": "usd", "is_derived": true, "approximate": true },
    "population_growth_pct":     { "…": "…", "unit": "pct", "is_derived": true, "geo_level": "place", "inputs": {"acs5": "2019–2023", "acs5_prior": "2014–2018", "geo_level": "place"} },
    "pet_households_est":        { "…": "…", "is_derived": true, "assumed_rate": 0.57 },
    "establishments":            { "value": 7, "unit": "count", "source_dataset": "zbp", "vintage": "2022", "geo_level": "zcta" },
    "vets_per_10k_households":   { "…": "…", "unit": "ratio", "inputs": {"zbp": "2022", "geo_level": "zcta", "zctas": 2, "acs5": "2019–2023"} },
    "revenue_per_establishment": { "…": "…", "unit": "usd", "is_derived": true, "label": "Avg. payroll per practice", "source_dataset": "cbp", "geo_level": "county" },
    "income_index_vs_us":        { "…": "…", "unit": "pct", "is_derived": true }
  },
  "attribution": ["…"]
}
```

**`opportunity_score` never appears — not null, not a flag, absent from `metrics` entirely.** It
is computed and stored by the materialisation and stays there, unpublished, until the VIN
Foundation signs off on its weights (A-C1 (9), A-C14 (5)); every serialiser in `app/api/market.py`
skips the row outright. Do not build a frontend that reads for the key's presence as a "is the
score ready" check — it is not a readiness signal, it is a standing decision.

**`suppressed` and `approximate` are never the same fact and are never both true on one entry.**
`suppressed: true` means the value is too imprecise to show at all — `value` is `null` and
`suppress_reason` names why (`no_moe`: the estimate arrived with no margin of error and is treated
as unmeasured, never as certain; `high_moe`: a margin that IS present but too wide;
`input_suppressed`: a derived figure whose own input was suppressed). `approximate: true` (present
only on `median_hh_income` at a catchment band) means the value SHOWN is itself an approximation
(a household-weighted average of tract medians, which has no combined margin of error by
construction, A-C21 (5)) — it is never suppressed, because there is a real value to show, just one
carrying its own caveat. The same metric can be suppressed at one band and approximate at another.

**Cache.** A hit returns the identical payload with header `x-cache: hit`; a miss computes it,
writes it, and returns it with `x-cache: miss`. The key is

```
listing:{listing_id}:market:{band}:v{listing_version}:g{gate_version}
```

TTL 86400 s (24 h). **The `{band}` segment is a correction beyond the plan's original sketch**
(which wrote the key as `listing:{id}:market:v{n}` with no band in it, A-C23 (3)) — `band` is a
query parameter this same route answers, and without it in the key a member requesting one band
would be served whichever band happened to be cached first. `{listing_version}` is
`listing:{id}:market:version`, bumped on every `materialize_listing` call (nanosecond resolution,
so two materialisations inside one wall-clock second cannot collide on the same key). `{gate_version}`
is `app.census.gate`'s global counter, bumped by any admin licence decision — this is what makes a
just-blocked layer disappear from an already-cached panel within the 60 s the licence gate promises,
without a per-dataset cache-busting scheme.

**404 semantics — two different codes, and they mean different things:**

* `NOT_FOUND` — the id is not a valid UUID, names no listing at all, **or names a listing that
  exists but is not `published`**. The last case is deliberate: a market panel is never served for
  an unpublished listing, whether or not it happens to still carry `market_metric` rows from
  before it was withdrawn — the same posture `GET /api/markets/{cbsa}/communities` already takes
  in its own SQL (`WHERE l.status = 'published'`). Nothing is enqueued.
* `NO_MARKET_DATA` — the listing exists, IS published, and has no `market_metric` rows for the
  requested band yet. One `census.backfill_listing` task is enqueued for it, deduplicated for 10
  minutes by a `backfill:{listing_id}` Redis key (`SET NX`) so repeated polling from a buyer's
  browser cannot flood the queue.

(A-C23 (2): earlier, the publication check and the backfill-dedupe check were compounded into one
`if`, which only ever gated whether to enqueue a backfill — it never gated whether to SERVE a
panel that already had rows, so an existing, unpublished, previously-materialised listing would
have had its panel served in full. The two checks are now separate, and the publication check
happens before `market_metric` is even queried.)

## Licence gates — every one of them, including the two this task closed

A `market_metric` row's `source_dataset` names the ONE dataset it is stamped with, and the generic
rule is simple: hidden unless that dataset's `license_status` is `cleared`. Three figures fold in a
SECOND dataset the generic rule cannot see, and each needs its own explicit check:

| Figure | Stamped `source_dataset` | Also gated on | Why |
|---|---|---|---|
| `population_growth_pct` (`growth`) | `acs5` | `acs5_prior` | The formula diffs two ACS vintages; the row can only carry one dataset key, and it is not the baseline's. |
| `vets_per_10k_households` | `zbp` or `cbp` (whichever produced the establishment count) | `acs5` | The ratio always divides by a household estimate, regardless of which dataset produced the count. |
| `establishments` (`vets`), **only when its own `source_dataset` is `cbp`** | `cbp` | `acs5` | The `cbp` fallback (no usable ZBP data) apportions the county establishment count by household share; the primary `zbp` path counts ZIP-code establishments alone and folds in no household data, so it needs no extra gate. |

The last two rows are this task's own fix (A-C23 (1)): before it, withdrawing the household
dataset's (`acs5`) licence left the vets-per-household ratio and the CBP-apportioned fallback
count visible, while growth correctly vanished under the equivalent check that already existed for
it — a licence hole of exactly growth's shape, on a rule this programme treats as legally
load-bearing. Both are implemented as one shared check (`_extra_cleared` in `app/api/market.py`),
used by `GET /api/markets/{cbsa}/communities` and `GET /api/listings/{id}/market` alike.

## `GET /api/admin/data-sources` and `POST /api/admin/data-sources/{dataset_key}/license`

```json
[
  { "dataset_key": "zbp", "display_name": "ZIP Code Business Patterns",
    "api_dataset_id": "2022/cbp", "vintage": "2022", "refresh_cadence": "Annual (Apr)",
    "license_status": "cleared", "license_name": "Public domain",
    "license_url": "https://www.census.gov/data/developers/about/terms-of-service.html",
    "attribution_text": "Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022",
    "last_verified_at": "2026-09-01T00:00:00+00:00", "drift_flagged": false, "notes": null,
    "active_vintage": "2022", "active_vintage_note": "…",
    "last_run": { "status": "succeeded", "finished_at": "2026-09-01T00:05:00+00:00", "rows_written": 41200 } }
]
```

Every registered dataset, blocked and unresolved ones included and marked as such — this is the
console behind `CLAUDE.md`'s "Blocked datasets never ship." Reading it is not a decision and
writes no audit row.

```
POST /api/admin/data-sources/{dataset_key}/license
{ "status": "cleared" | "unresolved" | "blocked", "name"?: string, "url"?: "https://…", "notes"?: string }
→ { "dataset_key": "…", "license_status": "…" }
```

Only `status` is required — every other field `COALESCE`s onto what is already recorded, so
blocking a source does not mean retyping its licence name and URL. `url`, if given, must be
`https://` (`422 BAD_FIELD` otherwise — the drift sweep re-fetches it quarterly and hashes what
comes back, and clear text lets anything on the path rewrite the page that comparison relies on).
Unknown `dataset_key` is `404 NOT_FOUND`.

**Two ledgers, and they record different things.** `audit_log` (`app.auth.audit`) records WHO
changed the gate, from what to what, for the standing "who did this" trail every admin action
gets. `license_audit_log` is the LICENCE ledger the quarterly drift sweep also writes into
(`app.census.license`); a human decision lands a row there too, with `changed = false` (a decision
is not evidence that the published terms moved) and `url` set to the literal string `"operator
decision"` when none was supplied, since the column is `NOT NULL` and a decision made without a
fetch still has to say what it was.

**`last_verified_at` has two authors and `drift_flagged` is never derived from it.** The quarterly
sweep sets `last_verified_at` only on a check that actually read a body — a dataset with no
`license_audit_log` row, or whose only check failed or 404ed, reads `null`. A human decision here
is the second author: an admin who has just read the terms is treated as a verification event too,
without fetching anything, and the two are told apart afterward only in the ledger (a decision row
carries no `content_sha256` and no `http_status`). `drift_flagged` is a completely separate column:
a later sweep that finds the terms unchanged since a flagged drift REFRESHES `last_verified_at` and
leaves the flag standing; only a decision made here clears it. Do not build a UI that infers
"verified, no drift" from a recent `last_verified_at` alone.

`attribution_text` is returned verbatim and composed nowhere in the frontend — it is legally
load-bearing (spec §12), and the point of holding it in the database is that a terms change is one
`UPDATE`, not a redeploy.

## Fixture → field mapping (`logic.js` → this API)

The seven field names the design's own fixtures (`communities()`, `VETS`, `ECON_K`) already use,
carried straight across as plain numerics — Sub-project 2 does not need to invent new field names,
only a new source for the same seven:

| Field | Comes from | Notes |
|---|---|---|
| `pop` | `communities[].pop` | ACS population estimate, `place` band by default. |
| `hh` | `communities[].hh` | ACS households. |
| `income` | `communities[].income` | ACS median household income. |
| `growth` | `communities[].growth` | Derived: two ACS vintages compared. Vintage statement: `ACS 2014–2018 → 2019–2023`. Gated on `acs5_prior` (see the licence-gates table above), not merely on the `acs5` stamp the row carries. |
| `pets` | `communities[].pets` | Derived: households × 0.57, a national placeholder rate — not a licensed pet-ownership figure (that dataset is `blocked`; see `CLAUDE.md`). |
| `econ` | `communities[].econ` | CBP payroll ÷ establishments, **county** level, already in **dollars** (not thousands — `ECON_K`'s own `×1000` scaling is no longer needed once real data replaces the fixture). |
| `vets` | `communities[].vets` | The `establishments` figure: ZBP ZIP-code count aggregated to the community, or the labelled county-CBP fallback when ZBP has nothing usable. |

`GET /api/listings/{id}/market`'s `metrics.*.value` carries the same underlying numbers,
unformatted, for the detail page's market report; `metrics.income_index_vs_us`,
`metrics.vets_per_10k_households` and the still-unpublished `opportunity_score` (with its
`components`) are the three figures the design's `marketPanel()` fixture (`incomeNat = 75149`,
`per10k`, `score`) sketched without a real source.

## Copy rules (spec §8/§12/§14) the frontend must honour when wiring this up

* Every figure shown carries its dataset and vintage — `attribution[]` at the response level,
  `metrics[].vintage`/`source_dataset` per figure.
* `is_derived: true` → render as "derived estimate", never presented as a raw Census number.
* `median_hh_income.approximate: true` → render "approximate" beside the value.
* `suppressed: true` → render "Estimate too imprecise to show at this geography", never a blank or
  a zero.
* `geo_precision != "rooftop"` → render "approximate community data" near the map pin.
* `opportunity_score`, on the day it is approved for publication, always renders with its three
  `components` and never immediately beside the asking price (spec §14) — there is nothing to wire
  today, since the key never arrives.

## Design-vs-spec copy conflicts

John's ruling (A-C1 (11)): the four conflicts the plan's pre-flight found between the approved V3
design's hard-coded copy and the Census spec's wording **resolve to the spec's wording** — "Growth
since 2015" becomes the vintage statement above; "5–10 min drive time" / "10–20 min drive time"
keep their labels but the caveat carries the "straight-line approximation" language (already in
`GET /api/layers`'s `caveat` above); the competition card's caveat carries the proxy sentence
(also already in `/api/layers`); and the econ layer is "Average Practice Payroll" /
"Avg. payroll per practice" (`revenue_per_establishment`'s `label`). **The API supplies all three
strings already** (`/api/layers`, `/api/listings/{id}/market`'s `label`); updating the rendered
design template itself is a separate, John-ruled task with its own screenshots (plan Task B6 note,
A-C0 paragraph 12) — this document is not that task, and no such change is in this release.

## Where this differs from the plan's original sketch

The plan's illustrative JSON (the "API contract" section written before any of Phase B was built)
is superseded in three ways the phase settled on while building it, all recorded above and none of
them cosmetic:

1. **`enabled: true` (boolean) → `state: "enabled" | "disabled" | "blocked"` (+ `blocked_reason`).**
   A boolean cannot distinguish "off because a member turned it off" from "off because the licence
   is not cleared" — the admin surface and the licence gate both need that distinction (A-C14 (4)).
2. **`opportunity_score` was sketched inline in the panel payload; it never ships.** A-C1 (9) /
   A-C14 (5): computed and stored, withheld from every response until the VIN Foundation signs off
   on its weights.
3. **The cache key gained a `{band}` segment** the sketch never had (A-C23 (3), above).

## Verification (QA) — corrected, and not yet run under this task

The plan's own Phase B exit checklist named the wrong dataset for one of its two licence-flip
checks: it said to flip `cbp` and expect **both** `vets` and `econ` to vanish, but `vets`
(`establishments`) gates primarily on **`zbp`** (the ZIP-code business dataset) — `cbp` only
matters to it on the county-apportioned fallback path. Flipping `cbp` alone correctly hides `econ`
and, on its own, should leave `vets` untouched (proof the fallback did not silently activate).
Corrected checklist, to be run on QA once real listings exist there (Sub-project 2) and only on
John's word, per A-C13 (1) — **this task did not execute it; nothing below has been run live**:

1. Geocode a real listing (`census.geocode_listing`); confirm `practice_location`,
   `practice_catchment` and `market_metric` rows exist.
2. `GET /api/listings/{id}/market` returns the panel with `attribution`; `GET /api/markets/12420/
   communities` returns the listing's community with the seven fixture field names.
3. Flip `zbp` to `unresolved`; confirm `vets` and the `competition` object vanish from both
   endpoints within 60 s, and reappear when `zbp` is cleared again.
4. Flip `cbp` to `unresolved`; confirm `econ` (`revenue_per_establishment`) vanishes and
   reappears, and that `vets`/`competition` are unaffected (the ZBP path is untouched by this
   flip).
5. Flip `acs5` to `unresolved` (this task's own fix): confirm `pop`/`hh`/`income`/`growth`/`pets`
   vanish (the generic gate), **and** that `vets_per_10k_households`
   (`competition.per_10k_households`/`level`) also vanishes even though `zbp`/`cbp` remain
   cleared — the licence hole this task closed.

`DEPLOY.md`'s "Census Phase A exit (QA)" section already documents loading and activating the
reference datasets themselves (TIGER, ACS, CBP, ZBP, QWI, BDS) on the worker over `railway ssh`;
that runbook was written in Phase A and is not repeated here.

## Known gaps — stated plainly, not glossed over

Phase B is closed, but two things it was meant to reach are not done, and one publication decision
is still pending:

* **The Browse map's own fixture feed is unfixed.** `frontend/src/logic.js`'s `VETS` and `ECON_K`
  are keyed by design-fixture ids (`p1`…`g4`), so every one of the eighteen seeded QA listings
  still shades bottom-bucket on all six Browse market layers (A-C0 paragraph 18). Closing this
  needs a change to `logic.js`'s byte-locked footer export, which is queued for John as **D-C14**
  (A-C14 (6)): may Phase B's successor change that export and re-pin `app-generated.test.ts`, or
  does the feed become its own task? Unanswered as of this document — no Phase B task touched it.
* **`GET /api/listings`'s Community Context strings are still hard-coded null.** John ruled
  (2026-09-08, Q2 / A-C1 (2)) that `app/api/listings.py::serialise` would format `pop`/`growth`/
  `income`/`hh` itself from `market_metric` at the `place` band, in the design's existing string
  spelling (`"81,900"`, `"+14.2% since 2015"`, …) — but no task in Phase B's file list ever
  implemented it, and the code today still reads `"pop": None, "growth": None, "income": None,
  "hh": None` unconditionally, with the comment "the community figures stay null until the Census
  plan supplies them." A-C15 (12) escalated this as the second unassigned scope beside D-C14, and
  it is unresolved as of this document — the two new market/community endpoints exist and carry
  real data, but nothing feeds it into the buyer-facing detail page's own Community Context card
  yet.
* **`opportunity_score` is computed, stored, and withheld** until the VIN Foundation signs off on
  its weights (A-C1 (9)) — not a defect, a standing decision this document is not the place to
  revisit.
* **The basemap licence (Esri vs. CARTO) is one open decision**, recorded in the Census plan
  (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md`, "Basemap licence — one
  decision record") and referenced, not restated, here.
* **Phase C is entirely deferred by design**, each item with its own stated trigger in the plan's
  "Phase C — Deferred by design" table: tract-level choropleth tiles, true routing-engine
  isochrones, a satellite basemap, a licensed pet-ownership rate, an AIES revenue benchmark,
  block-group geography, auto-extending `market_state` to new listing states, individual
  competitor locations (Overture/Foursquare/VIN's own directory), the Google Places Aggregate
  freshness signal (Task C1), tract-level growth, and population-weighted catchment apportionment.
  None of it is in this release; none of the routes above hint at it beyond the fields the plan
  already reserved (e.g. `competition.freshness`, which this API does not emit).
