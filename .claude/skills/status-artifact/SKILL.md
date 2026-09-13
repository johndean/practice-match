---
name: status-artifact
description: Use when updating the Practice Match programme artifact's status section (the page John opens to see what is live), including after a release, a merge, a ruling, or a stakeholder request to "update the artifact"
---

# Status artifact

## Overview
The status section is a **visual board John scans**, not a report he reads. Its shape is fixed: the five cards below, in this order, every time. New facts change the *contents* of the slots; they never replace a card with prose.

Baseline failure this skill exists for (2026-09-13): a status rewrite replaced the stage board and release nodes with eight paragraphs of measured prose. Every fact was true; John could not tell what was live. "I need a simple visual of what is going on and what is now live to check."

## The section IS these five cards, in this order

1. **Hero — "Live now: <version> on QA and on production."** When the two differ, the h2 names both: "Live now: 0.1.24 on QA · 0.1.23 on production." — same three tiles, same rail. Three tiles: QA (version · sha · mode · db/redis), Production (same), CI on the release commit (`4 / 4`). Below them the **release nodes** row: one `rnode` per release/stream — `done` (✓), `active` (in progress), `blocked` (waiting on John), each with `rstate`, `rfrac` ("0.1.24 · 1 / 4") and a one-line `rblurb`.
2. **"What is live to check."** A numbered grid of at most six checks, each: **where to click**, **the exact words or numbers to expect**, and, for the first four, an embedded screenshot (JPEG ≤ 200 KB, `sips -Z 1000` then `-s format jpeg -s formatOptions 72`, base64 data URI).
3. **"Where each one really is."** The `ol.board` of `li.brow` rows, one per task: `tid` (release or stream), `bname` (task — one line, what it changes for a member), `bdots` with SEVEN dots titled Brief · Built · Reviewed · Merged · CI green · QA · Production (`past` = done, `now` = in progress and pulsing, none = not yet), `bfill` width = done/6, `blabel` (state words: "Live on QA + production since …", "Implementing now", "Briefed", "WAITING ON YOU: …"). Row class, by rule: `done` = the Production dot is `past`; `live` = any dot is `now`, OR the latest `past` dot is QA with nothing in progress (on QA, production pending — label says so); `next` = only Brief is `past`; `wait` = blocked on John or on an external party. `bfill` width = past-dots ÷ 7 × 100, integer-truncated, so six of seven never renders as a full bar. Dots are contiguous from Brief: a stage cannot be `past` while an earlier one is not. Label templates: `done` → "Live on QA + production since <time UTC>"; QA-only → "On QA since <time UTC> · production pending"; `live` with a `now` dot → "<Stage> now (started <time UTC>)"; `next` → "Briefed" or "Briefed · starts when <task> merges"; `wait` → "WAITING ON <who>: <one clause>". The <date> in the empty "Waiting on you" line is the day the last ruling was recorded in the ledger.
4. **"Waiting on you."** Only decisions John alone can make, each with the recommendation. If none, the card stays and says one line: "Nothing — the last decisions landed <date>." No paragraph explaining why.
5. **"Issues, and their state."** A two-column table: what was found (one sentence) → state in colour: `--ok` Fixed in <release>, `--accent` Fixing now (<task>) or Scheduled (<task>). No issue appears without a state.

Nothing else. History, corrections, costs and rulings live in the ledger (`.superpowers/sdd/<plan>/progress.md`) and in the release notes; the artifact links to nothing and quotes nothing longer than one sentence.

## How to update
1. Read the CSS class vocabulary from the artifact head (`.brow`, `.bdot.past/.now`, `.bfill`, `.rnode.done/.active/.blocked`, `.rstate`, `.rfrac`, `.rblurb`, `.tid`, `.board`, `.card`, `.card-h`, `.eyebrow`, `.lead`, `.mono`, `.table-wrap`, `ul.plain`) — do not invent classes.
2. Regenerate the section with a script like `compose_status_example.py` (this directory; it built the 2026-09-13 06:45 UTC board): edit the data at the top, run it, it splices the single `<section class="status" data-doc="status">…</section>`.
3. Every number on the board is one you measured (`/api/healthz`, `gh run view`, the browser) or one a reviewer reproduced. The eyebrow of the hero names when and from what.
4. Publish to the SAME file path (`/tmp/pm-artifact-v4.html`) so the URL holds; label the version.

## Quick reference
| Slot | Source of truth |
|---|---|
| Versions, shas, modes | `curl /api/healthz` on both hosts |
| CI 4 / 4 | `gh run view <id> --json jobs` on the release sha |
| Board dots | the ledger's task lines (DONE / review / merged / CI / QA / production) |
| Check items | the release brief's QA click-through, with the values you saw |
| Screenshots | the workspace `screenshots/qa-<version>-*.png` |

## Tested
Baseline (2026-09-13, no skill): the board and nodes were replaced by prose. With the skill, a fresh agent under a six-fact, time-pressure update kept the five cards, folded a 900-word review story into one issue row, and asked for the four rules above — which were then added.

## Common mistakes
- Replacing a card with paragraphs because "there is a lot to say" — say it in the ledger; the card keeps its shape.
- A dot marked `past` for a stage nobody ran (e.g. QA before the browser check) — a dot is a measurement.
- An issue row with no state, or a state with no task name.
- Embedding PNGs (600 KB each) — convert to JPEG first; the page must stay under 16 MB.

## The header strip (slot 0)
Above the section, the page header carries `<div class="strip">` with three spans: **QA** (sha · version · mode · when verified), **Production** (same), **one sentence on how they relate** ("Both on the same code — 0.1.24 in progress"). It goes stale silently because it is outside the status section — update it in the same edit, and the header's "updated <date> WITA" stamp with it.

## An unreleased version is never a bare number
The stakeholder read "0.1.24 in progress" as QA being on 0.1.24. A version that is not on a host is always written "next (0.1.24) · being built · not deployed" — in the strip, the rail node and the board `tid` — and the hero's h2 names only versions measured from `/api/healthz`.
