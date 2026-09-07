# Account Screens Implementation Plan (Wave 2a Tasks I8b / I8c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the marketplace every account screen its API already serves — sign-up, check-your-email, verify, forgot and reset password, accept-invite, the applicant's answer, the "not available" gate — composed only from the existing V3 gate card, so the 28 approved states stay pixel for pixel.

**Architecture:** Every new screen is a new value of the prototype's `state.gate`, rendered by a new `<sc-if>` block appended in the gate's right column and built only from the existing form-card and status-card elements; outcomes whose only next step is signing in land on the existing sign-in card through its existing message box. All changes to the design file are ruled amendments (family **A8**, plus A7.3/A7.4 for the two sign-in touches John approved), applied by `npm run gen:design`, after which `logic.js` is re-ported and `App.vue` regenerated — the byte-identity, DOM and pixel gates keep holding. Routes map to gate states; the prototype talks to the API through the auth adapter I8a introduced; the test oracle reaches every new state on the reference through `?props=` and on the app through real routes, seeded accounts and seeded single-use tokens.

**Tech Stack:** Vue 3 + the ported prototype (`frontend/src/logic.js`, generated `App.vue`), vue-router, vitest, Playwright, FastAPI (`app/api/auth.py`, `app/api/applications.py` — unchanged), `scripts/seed_persona.py`, the D15 amendment engine (`frontend/tests/design-amendments.ts`).

**Spec:** `docs/superpowers/specs/2026-09-07-account-screens-design.md` (approved by John, 2026-09-08). **Executes in the identity worktree** (`.worktrees/feat-identity`, branch `feat/identity`) after main @ d56cecb has been merged back into it.

## Global Constraints (exact values — from the spec, CLAUDE.md and the identity plan)

- **The existing design does not change.** `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.rev2.dc.html` (pristine, SHA-256 `335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d`) is never touched; the amended `Practice Match V3.dc.html` equals pristine + `amendments()` byte for byte (`frontend/tests/design-amendments.test.ts`); `frontend/src/logic.js` and `frontend/src/App.vue` are never edited by hand (`frontend/tests/app-generated.test.ts`). Every new template block uses ONLY style strings that already appear in the pristine gate region (lines 148–260 of the pristine file): a test asserts it (Task S4). The 28 previously approved states keep their pixels and DOM — `frontend/tests/baseline-manifest.json` does not change in this plan, and every regenerated baseline of those 28 must be byte-identical (SHA-256 table in the report).
- **Copy is the spec's §3 table, verbatim.** No other words appear on the new screens. The two touches to `gate-signin` are exactly: footer line "Not approved yet? Request access · Forgot your password?" (A7.3) and sub-line "Use the email and password you registered with." (A7.4). The status cards' secondary "Sign in" keeps its label and signs the current user out first (§4.3).
- **TDD, no exceptions.** Every behaviour starts from a failing test that is run and watched fail: the amendment set/count and equality proof for design changes; `frontend/src/logic.test.ts` (real `Component`, a fake adapter OBJECT — never a module mock) for prototype behaviour; `api.test.ts`/`adapter.test.ts` for the client; `sync.test.ts`/`useStateRouteSync.test.ts` for routing; pytest for the seed script; Playwright for the states.
- **Gates every commit:** `cd frontend && npx vitest run --coverage` at 100/100/100/100 on every measured file; `npx vue-tsc --noEmit -p tsconfig.json`; `npm run build`; `npm run test:visual:baselines && npm run test:e2e` at `maxDiffPixels: 0`; `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`; `ruff`; `mypy --strict` (incl. `scripts/seed_persona.py`); `poetry run pytest tests/test_docs.py -q`.
- **Rate limits are budgets:** `SIGNIN_IP` 30/15 min (a run spends nine today), `SIGNUP_IP` 5/h, `SIGNUP_EMAIL` 3/day, `FORGOT_EMAIL` 3/h/email. Screenshot states use seeded accounts and seeded tokens, never a live sign-up; the live sign-up and forgot flows are exercised once per run with a throwaway address.
- **Seeded fixtures are test/QA only.** `scripts/seed_persona.py` refuses on production; raw fixture tokens are documented test constants, single-use, recreated on every run (the Playwright `api` web server seeds before serving).
- **Tokens never enter a URL the app writes** (spec S3): incoming `?token=` is read once, held in state, and the history entry replaced with the bare path.
- **Password strength is the server's** (zxcvbn ≥ 3, HIBP); the client checks only that two passwords match — default recorded for John.
- Conventional commits, explicit pathspecs, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; never `railway`, never deploy, never push (the controller pushes).

## Interfaces already on the branch (read these before starting)

- `frontend/src/auth/api.ts`: `signIn`, `signUp(email, password): Promise<Status>`, `verify(token): Promise<Status>`, `apply(kind, fields): Promise<{id, status}>`, `me`, `signOut`, `reauth`, `config`; `AuthError(code, message)`; `Status = { status: string }`.
- `frontend/src/auth/adapter.ts`: `AuthApi`, `AuthAdapter { signIn; signOut }`, `makeAuthAdapter(api, store)`; `app.setup.js` builds it and passes it as the `auth` prop; `me: useMe().me.value` is passed too.
- `frontend/src/router/sync.ts`: `RoutedState { screen; detailId?; adminTab?; gate?; auth? }`, `stateToRoute`, `routeToPatch`, `guard(state, patch, ctx?)`, `ROUTE_PERMS`.
- Prototype (design script = `logic.js`): state `gate`, `email`, `pw`, `formError`, `apply {name, vin, grad, state, employer, intent, affirm, error}`; `renderVals()` gate section: `gateSignin`, `gateApply`, `gateStatus`, `status = statusMap[s.gate] || statusMap.pending`, `form { email, pw, error, errorText }`, `setEmail`, `setPw`, `signIn`, `goSignInScreen`, `goApply`, `goSignin`, `applyFields`, `setIntent`, `toggleAffirm`, `submitApply`; `componentDidMount` reads `startScreen`, `startViewport`, `startGate`, `me`; `this.props.auth` is the adapter (absent in the reference).
- Harness (`frontend/tests/harness.ts`): `reach(page, { screen?, gate?, viewport?, persona? })`, `PERSONAS` (`design`, `buyer`, `seller`, `pending`, `declined`, `needsReview`), `signInAs`, `personaCredentials`, `personaSignIn/Out`, memo file with `PW_RUN_ID`; `reference-server.mjs` `injectProps(html, query)` for declared `data-props` keys (`startScreen`, `startGate`, `startViewport`, `me`, …).
- Backend (unchanged by this plan): `POST /api/auth/signup {email,password}` → 202 `{"status":"check_email"}` (unverified re-signup re-issues the link); `POST /api/auth/verify {token}` → 200 / 4xx; `POST /api/auth/password/forgot {email}` → 202; `POST /api/auth/password/reset {token,password}` → 200 `{"status":"reset"}` / 4xx; `POST /api/auth/accept-invite {token,password}` → 200 / 4xx; `POST /api/applications {kind, fields}` → 202 `{id, status}`; `POST /api/applications/{application_id}/answer {answer}` → 200 `{"status":"pending"}`; `GET /api/applications/me` → `{current, history}` with `current.{id, kind, status, info_request, answer, fields, decision_note, …}`. Errors: `{"error":{"code","message"}}`. `email_token(purpose ∈ verify|reset|invite, token_hash, expires_at, used_at)`; `app.auth.tokens.hash(raw)`.

## File map

| File | Responsibility |
|---|---|
| `frontend/src/auth/api.ts` (+test) | `forgot`, `reset`, `acceptInvite`, `answer`, `applicationsMe` |
| `frontend/src/auth/adapter.ts` (+test) | the full adapter the prototype calls |
| `frontend/src/app.setup.js` | passes the full adapter |
| `frontend/src/router/sync.ts`, `routes.ts` (+tests) | five routes ↔ gate states; `gateToken` |
| `frontend/tests/design-amendments.ts` (+test), `LOCAL_AMENDMENTS.md`, the amended design, `logic.js`, `App.vue` | A7.3, A7.4, A8.1–A8.9 |
| `frontend/src/logic.test.ts` | characterisation of every new gate behaviour |
| `scripts/seed_persona.py` (+tests) | `unverified@`, `verified@`, `invited@`; `declined@`'s fields; `needs-review@`'s `info_request`; fixture tokens |
| `frontend/tests/harness.ts` (+test), `reference-server.mjs` (+test), `screens.ts`, `smoke.spec.ts`, `signin-form.spec.ts` | reaching and proving the 15 new states |
| `CLAUDE.md`, `docs/RUNBOOK-identity.md`, `tests/test_docs.py` | counts, the re-send path in the UI, pins |

---

### Task S1: API client and adapter surface

**Files:**
- Modify: `frontend/src/auth/api.ts`, `frontend/src/auth/api.test.ts`, `frontend/src/auth/adapter.ts`, `frontend/src/auth/adapter.test.ts`, `frontend/src/app.setup.js`

**Interfaces:**
- Consumes: `payload()` / `post()` helpers already in `api.ts`; `Status`, `AuthError`.
- Produces: `api.forgot(email): Promise<Status>` → `POST /api/auth/password/forgot`; `api.reset(token, password): Promise<Status>` → `POST /api/auth/password/reset`; `api.acceptInvite(token, password): Promise<Status>` → `POST /api/auth/accept-invite`; `api.answer(applicationId, answer): Promise<Status>` → `POST /api/applications/{applicationId}/answer`; `api.applicationsMe(): Promise<ApplicationsMe>` → `GET /api/applications/me`, `ApplicationsMe = { current: ApplicationRow | null; history: ApplicationRow[] }`, `ApplicationRow = { id: string; kind: string; status: string; info_request: string | null; answer: string | null; fields: Record<string, unknown>; decision_note: string | null }`. `AuthAdapter` gains `signUp(email, pw)`, `verify(token)`, `forgot(email)`, `reset(token, pw)`, `acceptInvite(token, pw)`, `apply(kind, fields)`, `answer(id, text)`, `applicationsMe()` — pass-throughs to `api` (only `signIn` writes the store, only `signOut` clears it). `app.setup.js` passes `makeAuthAdapter(api, useMe())` unchanged in shape.

- [ ] **Step 1: Failing tests** — `api.test.ts` (the file's `vi.stubGlobal('fetch', …)` pattern): each new function posts the exact path and JSON body with `credentials: 'same-origin'` and returns the parsed body; a 4xx throws `AuthError` with the server's code; `applicationsMe()` GETs and returns `{current, history}`. `adapter.test.ts`: every new adapter method calls the same-named `api` function with the same arguments and returns its result; none touches the store (assert `set`/`clear` not called).
- [ ] **Step 2: RED** — `cd frontend && npx vitest run src/auth` → FAIL (`api.forgot is not a function`, …).
- [ ] **Step 3: Implement** — `api.ts`:
  ```ts
  export interface ApplicationRow { id: string; kind: string; status: string; info_request: string | null; answer: string | null; fields: Record<string, unknown>; decision_note: string | null }
  export interface ApplicationsMe { current: ApplicationRow | null; history: ApplicationRow[] }
  export async function forgot(email: string): Promise<Status> { return post('/api/auth/password/forgot', { email }); }
  export async function reset(token: string, password: string): Promise<Status> { return post('/api/auth/password/reset', { token, password }); }
  export async function acceptInvite(token: string, password: string): Promise<Status> { return post('/api/auth/accept-invite', { token, password }); }
  export async function answer(applicationId: string, answer: string): Promise<Status> { return post(`/api/applications/${encodeURIComponent(applicationId)}/answer`, { answer }); }
  export async function applicationsMe(): Promise<ApplicationsMe> { return payload(await fetch('/api/applications/me', { credentials: 'same-origin' })); }
  ```
  (use the file's existing `post`/`payload` helpers by their real names — read them first). `adapter.ts`: extend `AuthApi`/`AuthAdapter` with the eight methods; `makeAuthAdapter` forwards them.
- [ ] **Step 4: GREEN** — `npx vitest run src/auth` → pass; `npx vitest run --coverage` 100/100/100/100; `npx vue-tsc --noEmit -p tsconfig.json`.
- [ ] **Step 5: Commit** — `feat(auth-ui): the auth client and adapter cover the whole account lifecycle`.

---

### Task S2: Routes for the account pages

**Files:**
- Modify: `frontend/src/router/routes.ts`, `frontend/src/router/sync.ts`, `frontend/src/router/sync.test.ts`, `frontend/src/router/useStateRouteSync.ts` (A-S2), `frontend/src/router/useStateRouteSync.test.ts`, `frontend/tests/smoke.spec.ts` (the `ROUTES` list of the signed-out render test)

**Interfaces:**
- Produces: routes `/signup`, `/forgot`, `/verify`, `/reset`, `/accept-invite`; `RoutedState` gains `gateToken?: string`; `routeToPatch` maps `/signup → { screen: 'gate', gate: 'signup' }`, `/forgot → gate 'forgot'`, `/verify?token=T → { screen: 'gate', gate: 'verify', gateToken: 'T' }`, `/reset?token=T → gate 'reset'`, `/accept-invite?token=T → gate 'invite'` (no token → the same gate value with `gateToken: ''`); `stateToRoute` maps those gate values back to the bare paths (never a token) and every other gate value to `/`; `guard` is unchanged (`gate` screens are public).

**Controller amendment A-S2 (2026-09-08; the implementer's NEEDS_CONTEXT, ruled the same hour).** As written, the task produced a defect: `useStateRouteSync`'s own URL-settling `router.replace(loc)` fires `router.afterEach → apply()` a second time, which re-parses the now-bare `/verify` and overwrites the just-captured `gateToken` with `''`. Ruling — fix the root, keep the contract: `useStateRouteSync.ts` joins the task; a `settling` flag (closure-local to each `useStateRouteSync(c, router)` instance, beside `pending`) is set immediately before that replace, consumed by the `afterEach` it causes, and cleared in the replace's `.finally` as well so it can never leak into a later real navigation; `routeToPatch`'s "no token → `gateToken: ''`" contract is unchanged for a genuine bare visit. Proofs with the REAL `Component` and router: `/verify?token=T` keeps `gateToken === 'T'` after the run quiesces and the URL is `/verify`; a bare `/verify` yields `''`; an external `router.push('/browse')` after a settle still applies; the legacy `?tab=` settle test still passes. Landed in `715c29d`. Fix rounds (review + re-review): the flag became a shared `settleWith()` helper wrapping BOTH self-caused sites (`apply()`'s settle and the state→route watcher's own replace/push); an overlapping second self-caused navigation is deferred, not dropped — the in-flight one's `.finally` re-checks `stateToRoute(c.state)` against the current route and settles once more if they differ (bounded, no livelock) — and the `.finally` clear is falsified by a stub-router test confined to its own describe. `ca1627b`, `5d39372`. (Alongside, from the parity run against QA: the sign-in form test's 401 console filter matched `/401 \(Unauthorized\)/`, which HTTP/2 never produces; `harness.ts` now exports `isExpectedSignInFailure401` matching `/status of 401\b/`, proven for both transports — `5e10065`.)

- [ ] **Step 1: Failing tests** — `sync.test.ts`: one `it` per route both ways, the token captured from `query.token` (string only), `stateToRoute({ screen: 'gate', gate: 'reset', gateToken: 'T' })` → `{ path: '/reset', query: {} }`; the fixed-point property (routing the produced state lands on the bare path with no second navigation). `useStateRouteSync.test.ts`: visiting `/verify?token=T` signed out puts `gate: 'verify'`, `gateToken: 'T'` on the real `Component`'s state and settles the URL to `/verify`.
- [ ] **Step 2: RED** — `npx vitest run src/router` → FAIL.
- [ ] **Step 3: Implement** — `routes.ts`: add the five `{ path, component: App }` entries before the catch-all. `sync.ts`:
  ```ts
  const GATE_ROUTES: Record<string, string> = { '/signup': 'signup', '/forgot': 'forgot', '/verify': 'verify', '/reset': 'reset', '/accept-invite': 'invite' };
  const GATE_PATHS: Record<string, string> = Object.fromEntries(Object.entries(GATE_ROUTES).map(([p, g]) => [g, p]));
  // in routeToPatch, before the final `return { screen: 'gate' }`:
  if (to.path in GATE_ROUTES) return { screen: 'gate', gate: GATE_ROUTES[to.path], gateToken: typeof to.query.token === 'string' ? to.query.token : '' };
  // in stateToRoute's default arm:
  default: return { path: (s.screen === 'gate' && s.gate && GATE_PATHS[s.gate]) || '/', query: {} };
  ```
  `smoke.spec.ts` `ROUTES`: add the five paths to the signed-out render list (each renders the gate frame; the assertion stays "Approved members only" visible — the left panel is on every gate state).
- [ ] **Step 4: GREEN** — `npx vitest run src/router`, coverage, vue-tsc; `npx playwright test --config=tests/playwright.config.ts --project=app smoke.spec.ts`.
- [ ] **Step 5: Commit** — `feat(router): the five account pages route to gate states; tokens are read once and never written back`.

---

### Task S3: Seeded accounts and fixture tokens

**Files:**
- Modify: `scripts/seed_persona.py`, `tests/api/test_seed_persona.py` (create if the seed's tests live elsewhere — find `seed_persona` in `tests/` first and extend that file), `tests/test_docs.py`

**Interfaces:**
- Produces (test/QA only, refused on production): accounts `unverified@practice-match.test` (state `unverified`, display name "Unverified Applicant"), `verified@practice-match.test` (`verified`, "Verified Applicant"), `invited@practice-match.test` (`verified`, no usable password — a random hash, "Invited Staff"), all with the documented persona password except `invited@`; `needs-review@`'s open application row gets `info_request = "Which practice do you work at now, and in what role?"`; `declined@`'s declined application row carries `fields = {"name": "Declined Applicant, DVM", "school_year": "Texas A&M, 2012", "license_state": "TX", "employer": "Hill Country Veterinary Clinic", "intent": "Exploring ownership within two years.", "affirm": true}`. Fixture tokens: `FIXTURE_TOKENS = {"verify": ("unverified@practice-match.test", "fixture-verify-{n:02d}"), "reset": ("verified@practice-match.test", "fixture-reset-{n:02d}"), "invite": ("invited@practice-match.test", "fixture-invite-{n:02d}")}` for `n` in 1..12 — each run DELETES that account's existing `email_token` rows of that purpose and inserts twelve fresh ones (`token_hash = tokens.hash(raw)`, `expires_at = now() + 24 h` for verify, `+ 1 h` reset, `+ 7 d` invite); the raw values are constants the harness mirrors (`FIXTURE_TOKEN_PREFIX = "fixture-"`, twelve per purpose). Console line names what was seeded, never a token value beyond the documented pattern.

- [ ] **Step 1: Failing tests** — run the script against the test database (the existing seed test's fixture) and assert: the three accounts exist with the stated states; `invited@` cannot sign in with the persona password (`POST /api/auth/signin` → 401); `needs-review@`'s open row has the `info_request`; `declined@`'s row has the fields; exactly twelve unused `email_token` rows per purpose for the right account, each consumable once through the real endpoint (`verify` with `fixture-verify-01` → 200, again → 4xx); running the seed twice leaves exactly twelve per purpose (old rows deleted); production refusal unchanged. `tests/test_docs.py`: the harness constants (Task S5) equal the script's — pin now against the script's `FIXTURE_TOKENS` pattern and the three new emails (the harness half of the pin lands in S5; write the test to read both files so S5's RED is this test).
- [ ] **Step 2: RED** — `poetry run pytest tests/ -k seed -q` → FAIL.
- [ ] **Step 3: Implement** in `scripts/seed_persona.py` (mypy --strict; reuse the module's `hashed` password, `audit.write`, and the account upsert shape already there; `invited@` uses `P.hash_password(secrets.token_urlsafe(24))`).
- [ ] **Step 4: GREEN** — the seed tests; `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`; ruff; `mypy scripts/seed_persona.py --strict`.
- [ ] **Step 5: Commit** — `feat(seed): three more state accounts and twelve single-use fixture tokens per purpose for the oracle`.

---

### Task S4: The screens — design amendments A7.3, A7.4, A8.1–A8.9, and the prototype's behaviour

**Files:**
- Modify: `frontend/tests/design-amendments.ts`, `frontend/tests/design-amendments.test.ts`, `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` (REGENERATED by `npm run gen:design`), `frontend/src/logic.js` (re-ported), `frontend/src/App.vue` + `frontend/src/generated/pseudo.css` (`npm run gen:app`), `frontend/src/logic.test.ts`, `frontend/src/app.setup.js` (declares `startNotice`)

**Interfaces:**
- Consumes: the adapter (S1) as `this.props.auth`; `state.gateToken` (S2); `this.props.me`.
- Produces: gate values `signup`, `check-email`, `verify-expired`, `forgot`, `reset`, `reset-expired`, `invite`, `answer`, `unavailable` (plus the existing `signin`, `apply`, `pending`, `rejected`, `verify` as a transient landing value); `state.formNotice`; `state.signup {email, pw, error}`, `state.forgot {email, error}`, `state.reset {pw, pw2, error}`, `state.invite {pw, pw2, error}`, `state.answer {text, error, applicationId, note}`; `renderVals()` flags `gateSignup`, `gateCheckEmail`, `gateForgot`, `gateReset`, `gateInvite`, `gateAnswer`; values `signupForm`, `forgotForm`, `resetForm`, `inviteForm`, `answerForm` (each `{ …fields, error: bool, errorText }` with setters and a submit); `statusMap` entries `check-email`, `verify-expired`, `reset-expired`, `unavailable`; prototype prop `startNotice` (string, default `""`) for the reference's five notice states.

**The amendments (each a literal `find` → `replace`, `count: 1`, dated 2026-09-08, ruling "account screens composed from the V3 gate card — John, 2026-09-08 ('approved')"). Anchors are quoted from `logic.js` / the pristine template; none contains an asset path. Template blocks reuse existing style strings VERBATIM — copy each `style="…"` from the pristine gate region (lines 148–260); `design-amendments.test.ts` asserts every `style` value inside the A8 blocks occurs in that region of the pristine file.**

- **A7.3 — the sign-in footer.** find `Not approved yet? <a href="#apply" onClick="{{ goApply }}">Request access</a></div>` → `Not approved yet? <a href="#apply" onClick="{{ goApply }}">Request access</a> · <a href="#forgot" onClick="{{ goForgot }}">Forgot your password?</a></div>`.
- **A7.4 — the sign-in sub-line.** find `>Use your VIN credentials.</div>` → `>Use the email and password you registered with.</div>`.
- **A8.1 — the notice slot and the sign-out-first rule (script).** find `      form: { email: s.email, pw: s.pw, error: !!s.formError, errorText: s.formError },` → `      form: { email: s.email, pw: s.pw, error: !!(s.formError || s.formNotice), errorText: s.formError || s.formNotice },`; find `      goSignin: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signin", screen: "gate" }); },` → 
  ```
        goSignin: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", formNotice: "" }); if (s.auth && this.props.auth) return this.props.auth.signOut().then(show, show); show(); },
        goForgot: (e) => { if (e) e.preventDefault(); this.setState({ gate: "forgot", formError: "", formNotice: "" }); },
        goSignup: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signup", formError: "", formNotice: "" }); },
  ```
  and find `      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: "apply" }); },` → `      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: (s.auth || !this.props.auth) ? "apply" : "signup" }); },` (an anonymous visitor on the app starts with sign-up; a signed-in verified account, and the reference with no adapter, get the application form as before).
- **A8.2 — initial state.** find `    email: "", pw: "", formError: "",` → `    email: "", pw: "", formError: "", formNotice: "", gateToken: "",\n    signup: { email: "", pw: "", error: "" }, forgot: { email: "", error: "" }, reset: { pw: "", pw2: "", error: "" }, invite: { pw: "", pw2: "", error: "" }, answer: { text: "", error: "", applicationId: "", note: "" },` (this is the post-A6.3a line).
- **A8.3 — bootstrap.** find `    else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });\n  }` → 
  ```
      else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });
      else if (me && me.state === "unverified") this.setState({ screen: "gate", gate: "check-email", email: me.email });
      if (me && me.state === "needs_review" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current) this.setState({ screen: "gate", gate: "answer", answer: Object.assign({}, this.state.answer, { applicationId: r.current.id, note: r.current.info_request || "" }) }); }, () => {});
      if (me && me.state === "declined" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current && r.current.fields) { const f = r.current.fields; this.setState({ apply: Object.assign({}, this.state.apply, { name: f.name || "", vin: f.vin_member_id || "", grad: f.school_year || "", state: f.license_state || "", employer: f.employer || "", intent: f.intent || "", affirm: !!f.affirm }) }); } }, () => {});
      if (this.props.startNotice) this.setState({ screen: "gate", gate: "signin", formNotice: this.props.startNotice });
      if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));
    }
  ```
  (`needs_review` keeps A5.4's `gate: "pending"` as the synchronous default and switches to `answer` when the application arrives; the reference — no adapter — shows pending, and the oracle drives `answer` through `startGate`.) **Rider from the S2 review (2026-09-08):** a token-bearing gate value wins over the active-account redirect — when `this.state.gate` is `verify`, `reset` or `invite` on mount, the `active` branch does NOT set `screen: "browse"` (an approved member following a reset or invitation link must still see that page); express it as a guard on the `active` branch (`&& !["verify", "reset", "invite"].includes(this.state.gate)`) and prove it in `logic.test.ts` with `props.me` active and `gate: 'reset'`.
- **A8.4 — the status cards.** find `      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected"),` → `      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected" || s.gate === "check-email" || s.gate === "verify-expired" || s.gate === "reset-expired" || s.gate === "unavailable"),`; and find the two lines `        primary: { label: "Reply with more information", go: () => this.setState({ gate: "apply" }) }\n      }\n    };` → 
  ```
          primary: { label: "Reply with more information", go: () => this.setState({ gate: "apply" }) }
        },
        "check-email": {
          kicker: "Almost there", title: "Check your email",
          headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
          body: "We sent a verification link to " + (s.signup.email || s.email) + ". It is valid for 24 hours. Open it to confirm your address, then sign in to complete your access request.",
          meta: [{ k: "Sent to", v: s.signup.email || s.email }, { k: "Link valid for", v: "24 hours" }],
          primary: { label: "Send it again", go: () => { if (!this.props.auth) return; this.props.auth.signUp(s.signup.email || s.email, s.signup.pw).catch(() => {}); } }
        },
        "verify-expired": {
          kicker: "Link expired", title: "This link is no longer valid",
          headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
          body: "Verification links work once and expire after 24 hours. Request a new one with the same email and password.",
          meta: [],
          primary: { label: "Request a new link", go: () => this.setState({ gate: "signup" }) }
        },
        "reset-expired": {
          kicker: "Link expired", title: "This link is no longer valid",
          headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
          body: "Reset links work once and expire after 1 hour.",
          meta: [],
          primary: { label: "Request a new link", go: () => this.setState({ gate: "forgot" }) }
        },
        unavailable: {
          kicker: "Access", title: "This page is not available to your account",
          headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
          body: "Your approved access does not include this page. If you think it should, write to the VIN Foundation from the address on your account.",
          meta: [],
          primary: { label: "Back to Browse Practices", go: () => this.setState({ screen: "browse" }) }
        }
      };
  ```
  ("Send it again" re-posts the sign-up; when the visitor arrived by signing in as an unverified account, `s.signup.pw` is empty — the API's uniform 202 still answers, but no new link is issued without the password; the card's body already tells them to use the same email and password, and the `signup` gate is one click away via "Sign in" → "Request access". Record this limit in the characterisation test's name.)
- **A8.5 — form values (script).** find `      submitApply: () => {` → the following block placed BEFORE it (the anchor line is kept at the end of the replacement):
  ```
        gateSignup: s.screen === "gate" && s.gate === "signup",
        gateCheckEmail: s.screen === "gate" && s.gate === "check-email",
        gateForgot: s.screen === "gate" && s.gate === "forgot",
        gateReset: s.screen === "gate" && s.gate === "reset",
        gateInvite: s.screen === "gate" && s.gate === "invite",
        gateAnswer: s.screen === "gate" && s.gate === "answer",
        signupForm: { email: s.signup.email, pw: s.signup.pw, error: !!s.signup.error, errorText: s.signup.error },
        setSignupEmail: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { email: e.target.value, error: "" }) })),
        setSignupPw: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { pw: e.target.value, error: "" }) })),
        submitSignup: () => {
          const f = s.signup;
          if (!f.email || !f.pw) return this.setState({ signup: Object.assign({}, f, { error: "Enter both your email and password." }) });
          if (!this.props.auth) return this.setState({ gate: "check-email" });
          return this.props.auth.signUp(f.email, f.pw).then(() => this.setState({ gate: "check-email", email: f.email }), (e) => this.setState({ signup: Object.assign({}, f, { error: (e && e.message) || "Sign-up failed." }) }));
        },
        forgotForm: { email: s.forgot.email, error: !!s.forgot.error, errorText: s.forgot.error },
        setForgotEmail: (e) => this.setState((st) => ({ forgot: Object.assign({}, st.forgot, { email: e.target.value, error: "" }) })),
        submitForgot: () => {
          const f = s.forgot;
          if (!f.email) return this.setState({ forgot: Object.assign({}, f, { error: "Enter your email." }) });
          const done = () => this.setState({ gate: "signin", formNotice: "If that address has an account, a reset link is on its way. It is valid for 1 hour." });
          if (!this.props.auth) return done();
          return this.props.auth.forgot(f.email).then(done, (e) => this.setState({ forgot: Object.assign({}, f, { error: (e && e.message) || "Request failed." }) }));
        },
        resetForm: { pw: s.reset.pw, pw2: s.reset.pw2, error: !!s.reset.error, errorText: s.reset.error },
        setResetPw: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw: e.target.value, error: "" }) })),
        setResetPw2: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw2: e.target.value, error: "" }) })),
        submitReset: () => {
          const f = s.reset;
          if (!f.pw || !f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "Enter your new password twice." }) });
          if (f.pw !== f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "The two passwords do not match." }) });
          const done = () => this.setState({ gate: "signin", gateToken: "", formNotice: "Password updated. Sign in with your new password." });
          if (!this.props.auth) return done();
          return this.props.auth.reset(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "reset-expired", gateToken: "" }) : this.setState({ reset: Object.assign({}, f, { error: (e && e.message) || "Reset failed." }) }));
        },
        inviteForm: { pw: s.invite.pw, pw2: s.invite.pw2, error: !!s.invite.error, errorText: s.invite.error },
        setInvitePw: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw: e.target.value, error: "" }) })),
        setInvitePw2: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw2: e.target.value, error: "" }) })),
        submitInvite: () => {
          const f = s.invite;
          if (!f.pw || !f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "Enter your new password twice." }) });
          if (f.pw !== f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "The two passwords do not match." }) });
          const done = () => this.setState({ gate: "signin", gateToken: "", formNotice: "Your password is set. Sign in with your email and the password you just chose." });
          if (!this.props.auth) return done();
          return this.props.auth.acceptInvite(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "signin", gateToken: "", formNotice: "This invitation link is no longer valid. Ask the VIN Foundation for a new one." }) : this.setState({ invite: Object.assign({}, f, { error: (e && e.message) || "Could not set the password." }) }));
        },
        answerForm: { text: s.answer.text, note: s.answer.note, error: !!s.answer.error, errorText: s.answer.error },
        setAnswer: (e) => this.setState((st) => ({ answer: Object.assign({}, st.answer, { text: e.target.value, error: "" }) })),
        submitAnswer: () => {
          const f = s.answer;
          if (!f.text) return this.setState({ answer: Object.assign({}, f, { error: "Write your answer first." }) });
          if (!this.props.auth) return this.setState({ gate: "pending" });
          return this.props.auth.answer(f.applicationId, f.text).then(() => this.setState({ gate: "pending" }), (e) => this.setState({ answer: Object.assign({}, f, { error: (e && e.message) || "Could not send your answer." }) }));
        },
        goSignOut: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", auth: false, formNotice: "" }); if (this.props.auth) return this.props.auth.signOut().then(show, show); show(); },
        submitApply: () => {
  ```
  Read `app/api/auth.py` for the exact 4xx `code` the consume path returns for a used/expired token before writing `"TOKEN_INVALID"` — use the server's real code; STOP if the reset and invite paths use different codes and say so.
- **A8.6 — `submitApply` posts the application when an adapter is present.** find `        this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });\n      },` → 
  ```
          if (!this.props.auth) return this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });
          return this.props.auth.apply("buyer", { name: a.name, vin_member_id: a.vin, school_year: a.grad, license_state: a.state, employer: a.employer, intent: a.intent, affirm: !!a.affirm }).then(() => this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" }), (e) => this.setState({ apply: Object.assign({}, a, { error: (e && e.message) || "Your request could not be sent." }) }));
        },
  ```
- **A8.7 — the template blocks.** find `            </sc-if>\n          </div>\n        </div>\n\n        <div style="background: var(--color-navy); color: var(--color-white); padding: 30px 34px;">` (the `gateStatus` block's close, the right column's and grid's closes, and the footer band — count 1) → the same text with six new `<sc-if>` blocks inserted between the first `</sc-if>` and `</div>`: `gateSignup` (form card: title "Request Access", sub "Start with the email and password you will sign in with.", label "Email" + input bound to `{{ signupForm.email }}`/`{{ setSignupEmail }}`, label "Password" + `type="password"` input bound to `{{ signupForm.pw }}`/`{{ setSignupPw }}` with `placeholder="At least 12 characters"`, the error box on `{{ signupForm.error }}`/`{{ signupForm.errorText }}`, primary button `{{ submitSignup }}` "Create account", footer "Already have an account? <a href="#signin" onClick="{{ goSignin }}">Sign in</a>"); `gateForgot` (title "Reset your password", sub "We will email you a link.", one Email field, error box, "Send reset link" → `{{ submitForgot }}`, footer "Back to sign in" → `{{ goSignin }}`); `gateReset` (title "Choose a new password", sub "At least 12 characters. Your other sessions will be signed out.", "New password" + "Confirm password" (`type="password"`), error box, "Save password" → `{{ submitReset }}`, footer "Back to sign in"); `gateInvite` (title "Set your password", sub "You have been invited to the Practice Match team. Staff passwords are at least 14 characters.", the two password fields, error box, "Save password" → `{{ submitInvite }}`, footer "Back to sign in"); `gateAnswer` (title "More information requested", sub `{{ answerForm.note }}`, a text area bound to `{{ answerForm.text }}`/`{{ setAnswer }}` with `rows="4"` and label "Your answer", error box, "Re-submit request" → `{{ submitAnswer }}`, footer "<a href="#signout" onClick="{{ goSignOut }}">Sign out</a>"). Each block copies the sign-in / apply card's markup element for element — the card shell, the header band `<div>`s, `<label>`/`<span>`/`<input>`, the error `<div>`, the `<button>`, the footer `<div>` — changing only bindings and text. The `gateCheckEmail`/`verify-expired`/`reset-expired`/`unavailable` states need NO template: they render through the existing `gateStatus` block (A8.4).
- **A8.8 — `startGate` grows and `startNotice` joins `data-props`.** In the escaped JSON: `startGate.options` → `["signin","apply","pending","rejected","signup","check-email","verify-expired","forgot","reset","reset-expired","invite","answer","unavailable"]`; add `startNotice` after `me`: `{"editor":"text","default":"","tsType":"string","section":"Prototype","label":"Sign-in notice on load"}` (same escaping as its neighbours; count 1 each). `app.setup.js` declares `startNotice: { type: String, default: '' }`.
- **A8.9 — `startGate` may need a token for the reference.** No change: the reference's `reset`/`invite` forms render without a token (the token is only used on submit, which the reference never reaches).

**Controller amendment A-S4 (2026-09-08; the implementer's NEEDS_CONTEXT — three seams between tasks, ruled the same hour).** (1) The sign-in card's "Request access" now starts an anonymous visitor at sign-up (A8.1c, per the spec), so the oracle reaches `gate-apply` on the app as the seeded `verified@` account (its bootstrap lands on Request Access) — `PERSONAS` gains `verified` here rather than in S5, and `appPlan`'s `click` field is removed as dead (S5 re-adds a click for `gate-reapply` with its own test). (2) A token-less `/verify` visit issues NO request: with `gateToken` empty the bootstrap goes straight to `verify-expired`; only a present token is POSTed. (3) `GET /api/applications/me` returns the applicant's own `fields` (`_mine_row` in `app/api/applications.py`; `tests/api/test_applications.py` RED first) so the declined re-apply pre-fill is real. Also recorded: the "no new style" test asserts each inserted style against the amended design's gate card AND the pristine card with A1's two ruled declarations stripped (a pristine-verbatim 20 px title otherwise fails A1's own uppercase/tracking rule); `tests/test_docs.py`'s persona pin merges `STATE_PERSONAS` and `IDENTITY_STATE_PERSONAS` (seven personas). Landed in `6597447` + `58ca3e8`; the sign-in budget is ten of thirty per run before S5. **A-S4.1 (2026-09-08; the S4 review rulings):** `goSignin` signs out whenever an account is loaded — the guard is `(s.auth || this.props.me) && this.props.auth` (applicants never have `auth` set; `goSignOut`, which never had the `s.auth` guard, is unchanged); `submitReset`/`submitInvite` empty their sub-objects on success so no password outlives its request; `gateCheckEmail` is removed as dead (the card renders through `gateStatus`); `POST /api/auth/verify/resend` (session, `unverified` only, uniform 202, `SIGNUP_EMAIL`-bounded, the outbox row is its trace) backs "Send it again" when the account is loaded and no password is in hand, `signUp(email, pw)` otherwise; `LOCAL_AMENDMENTS.md` rows quote each amendment's `ruling` verbatim (pinned); `referenceUrl` sends `startNotice` (empty until S5). Landed in `ef2a513` + `5a8d7bf`.

- [ ] **Step 1: Failing tests** — `design-amendments.test.ts`: the pinned id set grows by A7.3, A7.4, A8.1–A8.8 (list them in the order `amendments()` returns them); the "no new style string" test (every `style="…"` inside the text A8.7 inserts is a substring of the pristine gate region); the pristine SHA unchanged; the amended == pristine + amendments proof. `logic.test.ts` (real `Component`, fake adapter object with `vi.fn()` methods that resolve/reject as each test needs): `goApply` on an anonymous app → `signup`; `submitSignup` → adapter `signUp(email, pw)` → `check-email` with `email` set; failure → `signup.error` = message; `check-email`'s primary re-posts; `submitForgot` → notice on the sign-in card; `submitReset` mismatch → client error, success → notice, token error → `reset-expired`; `submitInvite` success → notice, token error → notice text; `submitAnswer` → adapter `answer(id, text)` → `pending`; `goSignin` while signed in → `signOut` then the sign-in card; `componentDidMount` with `me.state = 'unverified'` → `check-email`; `needs_review` → `applicationsMe` → `answer` with the note; `declined` → `apply` fields pre-filled; `startNotice` → sign-in card with the notice; `gate: 'verify'` + token → `verify(token)` → notice / `verify-expired`; `submitApply` with adapter → `apply('buyer', {...})` mapped fields → `pending`; without an adapter every one of these falls back to the fixture transition (existing tests stay green).
- [ ] **Step 2: RED** — `npx vitest run tests/design-amendments.test.ts src/logic.test.ts` → FAIL (ids missing; `renderVals().submitSignup` undefined).
- [ ] **Step 3: Implement** — add the amendments to `design-amendments.ts` in numeric order and to `amendments()`; `npm run gen:design`; re-port `logic.js` (the byte-identity test dictates the bytes — copy the amended script block with the header/footer/asset-rewrite normalisations); `npm run gen:app`; `app.setup.js` `startNotice`; `LOCAL_AMENDMENTS.md` rows in order.
- [ ] **Step 4: GREEN** — `npx vitest run --coverage` (100/100/100/100), `vue-tsc`, `npm run build`; `npm run test:visual:baselines && npm run test:e2e` — the 28 existing states must be byte-identical to before this task (SHA-256 table in the report) except `gate-signin` (A7.3/A7.4 by ruling) — `baseline-manifest.json` is unchanged (gate-signin is not one of the thirteen).
- [ ] **Step 5: Commit** — `feat(auth-ui): the account screens, composed from the V3 gate card by amendment (A7.3, A7.4, A8.1–A8.8)`.

---

### Task S5: The oracle reaches every new state on both targets

**Files:**
- Modify: `frontend/tests/harness.ts`, `frontend/tests/harness.test.ts`, `frontend/tests/reference-server.mjs` (only if `injectProps` needs `startNotice` — it accepts declared keys, so likely nothing), `frontend/tests/reference-server.test.ts`, `frontend/tests/screens.ts`, `frontend/tests/smoke.spec.ts`, `frontend/tests/signin-form.spec.ts`, `tests/test_docs.py` (the S3 pin's harness half)

**Interfaces:**
- Produces: `PERSONAS` gains `unverified`, `verified`, `invited` (the last has no password — `personaCredentials('invited')` throws; it is used only through tokens); `FIXTURE_TOKENS = { verify: 'fixture-verify-', reset: 'fixture-reset-', invite: 'fixture-invite-' }` and `nextFixtureToken(kind): string` — a per-run counter (memoised in the run-scoped memo file next to the persona cookies, keyed by `PW_RUN_ID`) returning `fixture-<kind>-01` … `-12`, throwing past twelve; `reach()` gains `notice?: string` and the new `gate` values: on the reference `?props=` carries `startGate`/`startNotice`; on the app: `signup`, `forgot` → `page.goto('/signup' | '/forgot')`; `verify-expired` → `page.goto('/verify?token=fixture-verify-expired')` (a token no seed created → the real 4xx); `reset`, `invite` → `page.goto('/reset?token=' + nextFixtureToken('reset'))` / `'/accept-invite?token=' + nextFixtureToken('invite')` (the form renders; the token is consumed only when the flow tests submit); `reset-expired` → `/reset?token=bogus` then submit two matching passwords (the real 4xx); `check-email` → `signInAs(page, 'unverified')` then `/`; `answer` → `signInAs(page, 'needsReview')` then `/`; `unavailable` → `signInAs(page, 'buyer')` then `/admin`; `reapply` → `signInAs(page, 'declined')` then `/`, click "Reply with more information"; the five notice states → on the app, drive the real flow that produces the notice (verified: `/verify?token=` + `nextFixtureToken('verify')`; reset-sent: `/forgot` + submit a throwaway address; password-updated: `/reset?token=` + fixture + submit; invite-set: `/accept-invite?token=` + fixture + submit; invite-expired: `/accept-invite?token=bogus` + submit), on the reference `startNotice` with the same text.

- [ ] **Step 1: Failing tests** — `harness.test.ts`: `nextFixtureToken` sequence, per-run persistence, exhaustion; `reach` plan for each new target on both drivers (pure `plan` helper, as the existing tests do it); `personaCredentials('invited')` throws. `tests/test_docs.py`: the harness constants equal the seed's (S3's pin, now reading both halves). (S3 landed that pin as `@pytest.mark.xfail(strict=True, …)` so the branch stayed green; adding the harness constants makes it XPASS-strict — that IS this task's RED for the pin — and removing the marker is the GREEN.) `screens.ts`: the 15 states of spec §6 added — `gate-signup`, `gate-check-email`, `gate-verify-expired`, `gate-forgot`, `gate-reset`, `gate-reset-expired`, `gate-invite`, `gate-answer`, `gate-unavailable`, `gate-reapply`, `gate-signin-verified`, `gate-signin-reset-sent`, `gate-signin-password-updated`, `gate-signin-invite-set`, `gate-signin-invite-expired`. `signin-form.spec.ts`: the end-to-end flows once each — sign-up with a throwaway `e2e-<runid>@example.org` → check-email card; forgot with the same address → notice; verify a fixture token → notice, then the same token again → `verify-expired`; reset with a fixture token → notice, then sign in as `verified@` with the NEW password (then reset it back? No — the seed recreates the account's password every run; assert the sign-in, do not restore); accept-invite with a fixture token → notice, sign in as `invited@` with the chosen password; answer as `needs-review@` → pending card and `GET /api/applications/me` shows the answer; re-apply as `declined@` → pending card and a second application row; a buyer deep-linking `/admin` → the unavailable card with its two buttons.
- [ ] **Step 2: RED** — `npx vitest run tests/harness.test.ts`; `poetry run pytest tests/test_docs.py -q`; `npx playwright test --config=tests/playwright.config.ts --project=reference` (the new states fail until `reach` knows them).
- [ ] **Step 3: Implement** — harness, screens, flows.
- [ ] **Step 4: GREEN** — `npm run test:visual:baselines && npm run test:e2e` (43 states on both targets at 0 px; the 28 old ones byte-identical to Task S4's — table in the report); `npx playwright test --project=app signin-form.spec.ts`; coverage; vue-tsc; the sign-in budget arithmetic in the memo docstring updated (state the count).
- [ ] **Step 5: Commit** — `test(oracle): the fifteen account-screen states on both targets, driven by seeded accounts and fixture tokens`.

---

**Controller amendment A-S5 (2026-09-08; the implementer's NEEDS_CONTEXT — five seams measured against the real `Component`, ruled the same hour).** (1) **`gate-answer`.** The applicant's note is a rendered `<div>` fed only by `applicationsMe()`, which the reference (no adapter) never calls, so the two targets differ by one line of text and the card's height; and `startGate` runs before the `me` branch, whose `needs_review` maps to `pending`. Ruling — the same mechanism as A8.8b, not a fixture and not a demotion: a ruled prototype prop **A9.1** `startAnswerNote` (string, default `""`, section Prototype) declared in the design's `data-props` JSON (A9.1a) and written into the answer card's note by `componentDidMount` when set (A9.1b); `app.setup.js` declares it for the parity gate and the app never passes it (D-I8-2). The `ruling` text every row quotes: "A-S5 (2026-09-08): the reference reaches the applicant-answer card's note through a declared prototype prop, `startAnswerNote`, exactly as `startNotice` reaches the sign-in notices; the app never passes it." `referenceUrl` sends `me: null` for `answer` (the gate header is driven by `s.auth`, false for every applicant on both targets — no pixel moves) and, per the implementer's own finding, `{ startScreen: 'browse', startGate: 'unavailable', me: null }` for `unavailable`; both are per-gate exceptions with their own `plan` tests. S5's file list therefore widens to the amendment machinery — `design-amendments.ts` (+ its count/id pins), `LOCAL_AMENDMENTS.md`, the regenerated design file, `logic.js` and `app.setup.js` via `gen:design`/`gen:app`, and a `logic.test.ts` characterisation (RED first: the reference `Component` given `startAnswerNote` renders the note; without it, nothing) — and the 28 approved states stay byte-identical (a default-empty prop renders nothing). Fifteen approved states, 43 in all: the count John approved stands. (2) **`gate-reapply`.** The design's six re-apply inputs are real inputs: the state's `steps` `fill()` the seeded `DECLINED_FIELDS` and check the affirmation on BOTH targets (idempotent on the app, which is already pre-filled), so the approved state proves the filled form renders identically; the pre-fill itself is proven where it belongs, in `account-flows.spec.ts`, which asserts the seeded values BEFORE typing anything. `DECLINED_FIELDS` becomes a documented harness constant and joins the S3 pin against `scripts/seed_persona.py`. No prop, no fixture. (3) **`verified@` and the reset state.** `POST /api/auth/password/reset` rotates the password AND revokes every session, and `verified@` is also `gate-apply`'s screenshot persona (A-S4). Ruling — option (a): a documented `PERSONA_RESET_PASSWORD` constant (built the way `PERSONA_DEFAULT_PASSWORD` is, so gitleaks stays clean), a run-scoped `rotated` flag in the persona memo file (keyed by `PW_RUN_ID`, so a restarted worker agrees), `personaCredentials('verified')` returning the rotated password once the flag is set, and `forgetPersonaSession('verified')` after every reset submit; the seed restores the account next run. Pure helpers, unit-tested. Sixteen sign-ins of `SIGNIN_IP`'s thirty per FIXED fifteen-minute window (`bucket_key` indexes the window, so the count resets at the quarter-hour, not on a sliding clock) — the docstring states the arithmetic; a 429 during a re-run means wait for the boundary, never loosen a limit. (4) **Console errors from the three deliberate 400s.** `prepare()` lives in `visual.spec.ts`/`dom.spec.ts`, which S5 does not touch. Ruling — the per-`Page` registry in `harness.ts`, armed by the state's own `steps` (`expectApiStatus(page, 400)`): one status per arming, consumed by exactly one matching console error (`isExpectedApiFailure(status)`, the `/status of NNN\b/` form of `isExpectedSignInFailure401`, proven for both transports); on the app target the armed error MUST have been observed by the time the card is visible (an unobserved allowance fails — it is never dead); on the reference nothing is armed and nothing is allowed. Unit tests: arm/consume, unarmed error still throws, unobserved arming throws. (5) **`FORGOT_IP`.** `gate-signin-reset-sent` spends three of ten per hour per run (visual, dom, the flow), each with a distinct throwaway address (`FORGOT_EMAIL` safe). Accepted and documented beside the sign-in budget — three local runs an hour; CI's Redis is fresh per run. The limits are security controls and are not moved for tests. (6) `tests/test_docs.py`: growing `PERSONAS` to nine (`unverified`, `invited`) breaks two existing pins (`len == 7`; the seeded-map that omits the `INVITED_*` triple) — in scope, RED first, extended faithfully (nine; merge the triple). Commits, each green alone: A9.1 with its characterisation; the oracle states with regenerated snapshots and the pins; the live flows with the `testMatch` pin. Queued for John's vet on the artifact: A9.1 (a design-file change by the mechanism he accepted for `startNotice`), the re-apply fill, and the three-runs-an-hour forgot budget.

---

### Task S6: Docs and drift

**Files:**
- Modify: `CLAUDE.md` (the approved-state counts: 28 → 43 in "Layout" and "Source of truth"), `docs/RUNBOOK-identity.md` (§8 re-send: the check-email card's "Send it again"; the reset and invite pages the emails now open), `docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md` (Task I8's I8b/I8c paragraphs point here and are marked done when this plan completes), `tests/test_docs.py` (pins: the counts in CLAUDE.md match `SCREENS.length`; the runbook names `/signup`, `/forgot`, `/verify`, `/reset`, `/accept-invite`)

- [ ] **Step 1: Failing tests** — the two pins.
- [ ] **Step 2: RED** — `poetry run pytest tests/test_docs.py -q`.
- [ ] **Step 3: Docs.**
- [ ] **Step 4: GREEN** — `tests/test_docs.py`; `frontend/tests/cross-plan-deltas.test.ts`.
- [ ] **Step 5: Commit** — `docs: the account screens in CLAUDE.md, the runbook and the identity plan`.

---

## Self-review (writing-plans)

- **Spec coverage:** §3 rows 1–8 → S4 (A8.4/A8.5/A8.7) + S2 (routes) + S1 (client); "Re-apply needs no new screen" → A8.3 (pre-fill) + A8.6 (post); §4.1 → A7.3; §4.2 → A7.4; §4.3 → A8.1 `goSignin` + `goSignOut`; §5 wiring → S1/S2/S4; §6 oracle + fixtures → S3/S5; §7 out of scope untouched; §8 acceptance → S5's flows.
- **Placeholders:** none — every amendment carries its anchor and text; the one discovered value (`TOKEN_INVALID`) is named as "read the server's real code, STOP if reset and invite differ".
- **Type consistency:** `gateToken` (S2) is read by A8.3/A8.5; `startNotice` (A8.8) is declared in `app.setup.js` and driven by `reach` (S5); adapter method names (S1) match every `this.props.auth.*` call in S4; persona keys (`unverified`, `verified`, `invited`, `needsReview`, `declined`, `buyer`) match S3's emails through the `tests/test_docs.py` pin.
