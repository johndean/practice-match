---
name: practice-match-workflow
description: How work is done on Practice Match (foundation.vin) — request intake, design-fidelity rules, the verification gate, guarded Railway deploys, and the hand-back John expects. Use for any feature, fix, or deploy in this repo.
---

# Practice Match: request → verified deploy

## The situation
- There is no human QA layer. QA (qa.foundation.vin) is where verification happens; production (foundation.vin) is what the VIN Foundation and its members see. John does not run the app locally.
- The approved Claude Design is the visual contract. `npm run test:visual` compares the app to the design itself; a red suite means the app is wrong, not the test.
- This machine runs several Railway projects. `scripts/deploy.sh` exists so a wrong link can never ship this app over another product.

## Phase 1 — Intake
Requests arrive in stakeholder language. Ask until unambiguous: who (buyer / seller / VIN Foundation admin), where (which screen in `frontend/tests/screens.ts`), edge cases, what "working" looks like. Restate before building. John prefers eight questions to the wrong feature.

## Phase 2 — Recon
Open the reference `.dc.html` for any UI work. Read the spec/plan in `docs/superpowers/`. For data-driven work, read the Census spec (`docs/design-reference/.../Census Data Source Specification.dc.html`) and probe live endpoints before trusting remembered shapes.

## Phase 3 — Build (TDD, surgical)
Failing test first (vitest / pytest / Playwright state), minimal code, green, refactor. The diff contains the feature and nothing else. Never remove or rename while doing unrelated work. Name the regression surface out loud when touching shared code (`logic.js` render values, `static.py`, `start.sh`, `deploy.sh`).

## Phase 4 — Gate (all four, every production deploy)
1. `poetry run pytest` · `cd frontend && npm run typecheck && npm test && npm run build`
2. `npm run test:smoke` · `npm run test:visual:baselines && npm run test:visual`
3. Deploy QA (`scripts/deploy.sh QA`), click through the changed flow on https://qa.foundation.vin
4. Deploy production, `scripts/verify-deploy.sh production`, load the changed flow on https://foundation.vin

## Phase 5 — Deploy
`scripts/deploy.sh QA|production` only. It runs `railway status` and refuses any project but Practice Match, deploys `api` then `worker`, then probes. If the full gate passed, deploy production without asking.

## Phase 6 — Hand-back
Plain-language summary John can forward (no jargon, UUIDs, versions, paths) · screenshots of the live screens · one engineer's line: version, what was verified, flagged risk. Say exactly what was NOT verified.

## Mistakes that have actually happened on sibling projects — do not repeat
Unfaithful ports with the reference closed · collateral removal · destructive actions without instruction · false "done" without live verification · deploying with the wrong Railway link · trusting remembered API shapes · treating "tests pass" as done.
