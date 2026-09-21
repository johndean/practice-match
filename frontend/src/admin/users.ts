/**
 * `GET /api/admin/users` → the approved design's Users table, and every decision on it back to
 * `POST /api/admin/users/{id}/decide` (Task I7's mapping, wired by Task A36 under D-C53: "all the
 * admin tabs must be factual and fully functional, zero-gaps, zero-fake data, everything must be
 * surfaced and wired to UX").
 *
 * The Map-engines M6 pattern: a pure mapping from the API payload to the rows the design's own
 * template already renders, so nothing about the screen's markup or its styles moves. The
 * `cell()` and `A()` shapes below — and the five pill tones — are COPIED VERBATIM from
 * `src/logic.js`'s `adminVals()`; `src/admin/users.test.ts` compares them against that file's
 * own output, so a drift on either side fails rather than silently restyling the table.
 *
 * The one thing `A()` does not carry over verbatim is `go: () => {}`: the design's is a
 * prototype no-op, and here it is the decision.
 *
 * **A ROW IS KEYED ON ITS OPEN APPLICATION WHERE IT HAS ONE, AND ON ITS OWN ACCOUNT STATE WHERE IT
 * HAS NONE** (the controller's ruling on fix round 1's review Important 1, 2026-09-13, closing the
 * gap rulings 4 and 8 left between them). `account.state` is not the whole story about what is
 * waiting on this tab: a SELLER applies from an account that is ALREADY `active` — `POST
 * /api/applications` says why, "moving it to `pending` would strip every role on the next request"
 * — and `POST …/decide` accepts `approve`, `decline` and `request_info` on that application. Keyed
 * on the account state alone, such a row showed the "Approved" pill and one "Suspend" button: a
 * seller applicant, told they were approved, with no way to decide them, over a badge that did not
 * count them. So `openStatus()` below is the one place that decision is made, and the pill, the
 * buttons and the provenance sentence all read it; `app/api/admin_users.py`'s `COUNTS_SQL` counts
 * the same union, so the badge and the rows cannot disagree about what "open" means.
 *
 * **REVOKE IS NOT RENDERED, and that is a ruling rather than an omission** (the controller's
 * ruling 6 on the audit's Users items, 2026-09-13). `users.revoke` is the one decision in
 * `permissions.REAUTH`, so the API refuses it without a fresh password step-up — and V3 draws no
 * step-up element at all. A `window.prompt` would take a password unmasked, and a button that
 * cannot complete its action is fake (D-C53), so `ACTIONS` below offers the four states' other
 * decisions and nothing else until John approves a re-authentication dialog. The API's own table
 * is mirrored whole regardless (`Action`, `LABEL`, `NOTE_REQUIRED`), because that mirror is what
 * `tests/test_docs.py` pins against `app/api/admin_users.py` — and it is what the button comes
 * back through the day the dialog lands. The design's OWN fourth row still shows Revoke on the
 * frozen `admin-users` capture: that row reaches the table through `DesignUserRow` below, which
 * carries the design's own labels and styles verbatim and never `ACTIONS` — the same split
 * `admin/listings.ts` records for its "Flagged"/Investigate row. The dialog itself is
 * `docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §3, family A41, whose own
 * stated dependency is this task's merge.
 */
import { csrfToken } from '../auth/api';
import { openNoteDrawer } from './noteDrawer';

export interface ActionButton { label: string; go: () => Promise<void>; style: string }

export interface Cell {
  hasMain: boolean; main: string;
  hasSub: boolean; sub: string;
  hasPill: boolean; pill: string; pillStyle: string;
  hasActions: boolean; actions: ActionButton[];
}

/** Verbatim from logic.js's `adminVals()`, `go` excepted (see the module note). */
export function A(label: string, tone: string | undefined, go: () => Promise<void>): ActionButton {
  return {
    label,
    go,
    style: 'font-family: var(--rf-display); font-size: 12px; font-weight: 500; letter-spacing: .03em; text-transform: uppercase; padding: 7px 12px; border-radius: 6px; cursor: pointer; border: 1px solid ' +
      (tone === 'primary' ? 'var(--color-blue)' : 'var(--border-subtle)') + '; color: ' +
      (tone === 'primary' ? 'var(--color-white)' : tone === 'danger' ? '#494949' : 'var(--color-navy)') + '; background: ' +
      (tone === 'primary' ? 'var(--color-blue)' : 'var(--color-white)') + ';'
  };
}

/** Verbatim from logic.js's `adminVals()`. Shared with the Permissions tab's rows. */
export function cell(main: string | null, sub?: string | null, pill?: string | null, pillTone?: string | null, actions?: ActionButton[] | null): Cell {
  const tones: Record<string, string[]> = {
    ok: ['#ffffff', '#003a70', '#003a70'], warn: ['#003a70', '#deecf7', '#deecf7'],
    bad: ['#494949', '#ffffff', '#494949'], info: ['#003a70', '#ffffff', '#339dde'],
    mute: ['#494949', '#f5f5f5', '#d4dde5']
  };
  const t = tones[pillTone ?? ''] || tones.mute;
  return {
    hasMain: !!main, main: main || '', hasSub: !!sub, sub: sub || '',
    hasPill: !!pill, pill: pill || '',
    pillStyle: 'display: inline-block; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: ' + t[0] + '; background: ' + t[1] + '; border: 1px solid ' + t[2] + ';',
    hasActions: !!actions, actions: actions || []
  };
}

/** `app/api/admin_users.py`'s `TRANSITIONS` keys — the staff decisions, by their API names. */
export type Action = 'approve' | 'decline' | 'request_info' | 'suspend' | 'reinstate' | 'revoke';

// ---------------------------------------------------------------------------------------
// The next four constants are JSON, on ONE LINE each and double-quoted, because
// `tests/test_docs.py::test_the_admin_users_tables_match_the_api` parses them out of this file
// and compares them with `app/api/admin_users.py` (review Minor 3): `NOTE_REQUIRED` against its
// namesake, every action in `ACTIONS[state]` against `TRANSITIONS` (the design shows a legal
// SUBSET), and `PILLS`'s keys against `ACCOUNT_STATES`. A fifth note-required action added on
// the server would otherwise have this table POST a blank note and take a 422 at click time.
// `ROLE_LABELS` (Task A36) joins them, pinned against `app/auth/labels.py::role_label` — the one
// place the product names a VIN Foundation role, and the header's own account line already
// prints it.
// ---------------------------------------------------------------------------------------

/** The four `admin_users.decide` refuses with `NoteRequired` when the note is blank. */
export const NOTE_REQUIRED: readonly Action[] = ["decline", "request_info", "suspend", "revoke"];

/** `admin_users.MAX_NOTE` — the server's real bound on a decision note (ruling D-C60), read from
 *  ONE place and applied as the note drawer's own `maxlength` rather than retyped. Pinned by
 *  equality in `tests/test_docs.py`, the same single-line-double-quoted-JSON convention the four
 *  tables above already use. */
export const MAX_NOTE = 4000;

// The buttons the approved design shows, per state — a legal SUBSET of `TRANSITIONS`, not all of
// it: the API also allows `revoke` from `unverified`, `verified`, `pending`, `needs_review` and
// `declined`, which the design's review queue does not offer. A state with no entry here offers
// no button at all. `revoke` is in no entry AT ALL, from any state, for the ruled reason the
// module note gives: it needs a step-up V3 has no element for.
export const ACTIONS: Record<string, Action[]> = {"pending": ["approve", "decline", "request_info"], "needs_review": ["approve", "decline"], "active": ["suspend"], "suspended": ["reinstate"]};

// Every action the API names, labelled — including the one no state offers today, because this
// table mirrors `TRANSITIONS` and `LABEL[action]` is what renders the button when Revoke returns.
const LABEL: Record<Action, string> = {
  approve: 'Approve', decline: 'Decline', request_info: 'Request info',
  suspend: 'Suspend', reinstate: 'Reinstate', revoke: 'Revoke'
};

const TONE: Partial<Record<Action, string>> = { approve: 'primary', decline: 'danger', revoke: 'danger' };

// `[label, tone]` for every `ACCOUNT_STATES` entry, in that order. Five carry the design's own
// labels and tones (its Users rows show Pending, Needs review, Approved and Revoked); the other
// three have no ruled label, so they show the state key, muted — absent beats faked.
export const PILLS: Record<string, [string, string]> = {"unverified": ["unverified", "mute"], "verified": ["verified", "mute"], "pending": ["Pending", "warn"], "needs_review": ["Needs review", "bad"], "declined": ["declined", "mute"], "active": ["Approved", "ok"], "suspended": ["Suspended", "info"], "revoked": ["Revoked", "bad"]};

// The two roles a row NAMES, in `app/auth/labels.py::role_label`'s own words — the label the
// header already prints over this very screen. `buyer` and `seller` are deliberately absent: the
// Status pill says what a buyer's account is, and repeating it under the applicant's name would
// state one fact twice. Admin wins over staff where an account holds both, exactly as
// `role_label` orders them.
export const ROLE_LABELS: Record<string, string> = {"admin": "VIN Foundation admin", "staff": "VIN Foundation staff"};

// The design's admin Users table shows one flagged applicant, and this is its sentence. A flag
// with no approved copy is named by the flag itself rather than by prose nobody has ruled —
// `app/auth/flags.py` is free to add hints, and a hint is never a decision.
const FLAG_TEXT: Record<string, string> = { employer_keyword: 'employer appears to be a consolidator.' };

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** A deterministic "August 12" from an ISO timestamp — never `Date#toLocaleDateString`, which
 *  reads the RUNTIME's locale — and UTC, so the reviewer's own browser offset cannot move the day
 *  the API actually stamped. `admin/listings.ts` carries its own copy of this for the Listings
 *  tab's "Submitted September 1"; the two tabs' modules deliberately share nothing but `logic.js`,
 *  and folding the two into one date helper belongs to the ONE-VOCABULARY sweep, not here. */
function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** One live grant, as `GET /api/admin/users` serves it. `granted_by_name` is Task A36's own
 *  addition: `granted_by` is an account id, and an id cannot tell an admin how another admin came
 *  to hold the role, which is the whole point `_grants`'s docstring makes. */
export interface Grant { role: string; granted_by_name: string | null; granted_at: string }

/**
 * One row of `GET /api/admin/users`'s `items`, narrowed to what the table reads. The payload
 * carries more (`created_at`, `application_id`, `last_sign_in_at`, …); a structural interface
 * means the real item is assignable without restating it.
 */
export interface UserItem {
  account_id: string;
  email: string;
  state: string;
  name: string | null;
  affiliation_label: string | null;
  kind: string | null;
  fields: Record<string, unknown> | null;
  flags: string[];
  roles: string[];
  grants: Grant[];
  decided_at: string | null;
  decided_by_name: string | null;
  /** The LATEST application's own status, or null where the account has none — `pending`,
   *  `needs_review`, `approved` or `declined`. The two OPEN ones outrank `state` (module note). */
  application_status: string | null;
  /** The read-back ruling D-C60 asks for, all three from the SAME latest application `LIST_SQL`
   *  already joins: the real words behind a decline, the question a request-info round asked, and
   *  the applicant's own reply. `admin/listings.ts`'s own `decline_reason` is the precedent this
   *  follows rather than a new idiom. */
  decision_note: string | null;
  info_request: string | null;
  answer: string | null;
}

/**
 * One of the DESIGN's own `sets.users.rows` fixtures, as `frontend/tests/design-admin-users.mjs`
 * serves them — `admin/listings.ts`'s `DesignListingRow` applied to `admin-users`, the second of
 * the thirteen frozen screens to be wired.
 *
 * The design's four rows are NOT reproducible by feeding a real payload through the derivation
 * below, and one of them says so outright: Dr. Rachel Mendes's sub-line reads "Approved August 12
 * by staff reviewer K. Alvarez." while her fixture carries no decision at all, and Dr. Alan Cho's
 * NEEDS-REVIEW row offers "Request info", which `TRANSITIONS` allows from `pending` only. So the
 * fixture carries every one of the design's own WORDS AND STYLES directly, read straight off
 * `adminVals()`'s own computed cells — `pillStyle` and each action's `style` included — rather
 * than tone NAMES this module would have to re-derive: the `.mjs` fixture files touch only
 * `logic.js` (never a TypeScript module, on either side of the D6 stub), and a style string copied
 * verbatim off the design's own computed output can never drift from it.
 */
export interface DesignUserRow {
  account_id: string; applicant: string; applicantSub: string; affiliation: string; intent: string;
  pill: string; pillStyle: string; actions: { label: string; style: string }[];
}

/** The outcome of one `decide` POST — a discriminated result rather than a thrown error or an
 *  internal `alert`, so the CALLER decides what a refusal means (ruling D-C60): `decision()`'s
 *  direct, no-note path alerts, and the note drawer shows the message in its own error slot and
 *  keeps what was typed, never losing it to a refusal. */
export type DecideOutcome = { ok: true } | { ok: false; message: string };

export interface UsersUi {
  /** The decision itself — `POST /api/admin/users/:id/decide`. */
  decide(item: UserItem, action: Action, note: string): Promise<DecideOutcome>;
  /** For a NOTE_REQUIRED decision: opens the note surface and owns the whole exchange — submit,
   *  and on a refusal, retry or cancel — calling `submit` (never `decide` directly) for every
   *  attempt, so what this method records and what actually happened can never disagree. Resolves
   *  once the surface closes, however it closes; never rejects. */
  decideWithNote(item: UserItem, action: Action, submit: (note: string) => Promise<DecideOutcome>): Promise<void>;
}

const text = (value: unknown): string => (typeof value === 'string' ? value : '');
const join = (parts: string[]): string => parts.filter(Boolean).join(' · ');

/** "TX license" / "TX, NM licenses" — both spellings the approved design shows. */
function licence(states: string): string {
  if (!states) return '';
  return `${states} ${states.includes(',') ? 'licenses' : 'license'}`;
}

/** The design's curly quotes around the applicant's own words, and nothing around silence. */
const quote = (intent: string): string => (intent ? `“${intent}”` : '');

/**
 * "VIN Foundation admin · granted by Dr. Rachel Mendes August 12" — the controller's ruling 7 on
 * John's binding condition (2026-09-06: every account and every role is surfaced in the admin
 * controls, admins included). The design has no roles column, so the fact is stated in the
 * Applicant cell's own ` · ` idiom, which is where the design already puts what qualifies a name.
 *
 * The grant's own row supplies the date and the granter; where the payload names no granter the
 * line says when and not by whom, rather than printing a uuid.
 */
function roleLine(item: UserItem): string {
  const role = ['admin', 'staff'].find((r) => item.roles.includes(r));
  if (role === undefined) return '';
  const grant = item.grants.find((g) => g.role === role);
  if (grant === undefined) return ROLE_LABELS[role];
  return join([ROLE_LABELS[role], grant.granted_by_name
    ? `granted by ${grant.granted_by_name} ${formatDate(grant.granted_at)}`
    : `granted ${formatDate(grant.granted_at)}`]);
}

// The last two of the cross-language JSON literals (see the block above `NOTE_REQUIRED`): both are
// pinned by equality against `app/api/admin_users.py` in `tests/test_docs.py`, so a third waiting
// status or a widened state machine fails on both sides at once instead of leaving the badge and
// the rows describing different sets (fix round 2, re-review Minor 2).

/** `OPEN_STATUSES` in `app/api/admin_users.py` — the two an application is still waiting in. */
export const OPEN_STATUSES: readonly string[] = ["pending", "needs_review"];

/** The account states `decide` will act on an APPLICATION from — `app/api/admin_users.py`'s own
 *  `DECIDABLE_STATES`, which is `TRANSITIONS`' union over `APPLICATION_ACTIONS` plus the `active`
 *  a seller application is decided from and to. */
export const DECIDABLE_STATES: readonly string[] = ["active", "pending", "needs_review"];

/** The status of the row's OWN open application, or null where nothing is open — the one place the
 *  module note's rule is decided, so the pill, the buttons and the provenance sentence cannot
 *  disagree with each other about which fact a row is about.
 *
 *  It governs the row only from a state the API will DECIDE that application from (fix round 2,
 *  re-review Important 2, the controller's ruling narrowing fix round 1's union). `suspend` and
 *  `revoke` are ACCOUNT actions — neither is in `APPLICATION_ACTIONS` — so `decide` never closes
 *  the application row, and a suspended or revoked account keeps a STALE open one for ever. Keyed
 *  on it, such a row offered Approve / Decline / Request info, each of which the API refuses with
 *  409 STATE, and hid Reinstate, the one action it accepts: three fake buttons and no way out,
 *  which is the sentence D-C53 is made of. `COUNTS_SQL` narrows to the same set, so the badge
 *  still counts exactly the rows this table renders as decidable. */
function openStatus(item: UserItem): string | null {
  return item.application_status !== null
    && OPEN_STATUSES.includes(item.application_status)
    && DECIDABLE_STATES.includes(item.state)
    ? item.application_status
    : null;
}

/** "Approved August 12 by staff reviewer K. Alvarez." — the design's own sentence on its approved
 *  row, from `application.decided_at` and the decider's display name (both Task A36's own payload
 *  fields). The design has ONE provenance sentence and it says "Approved", so it is gated on the
 *  application really having been APPROVED (fix round 2, re-review Important 1).
 *
 *  That term is what the earlier two could not be: `decide` stamps `decided_at=now()` on every
 *  application decision, a decline included, and a SELLER application is decided from `active` to
 *  `active` — so a declined seller application on an approved buyer satisfied "state is active",
 *  "a decision date exists" and "nothing is open" at once, and the row named the colleague who
 *  DECLINED it as the approver, on the decline's own date. `approved` is never open, so the
 *  `openStatus` term of fix round 1 is implied by this one and retired with it.
 *
 *  The state term STAYS beside it: a suspended account whose approved application still carries
 *  its stamp would otherwise print "Approved …" under a "Suspended" pill.
 *
 *  Nothing is invented for a decline. The design carries a `declined` PILL (its own muted
 *  account-state tone) and NO declined sub-line at all, and on this row the pill and the single
 *  Suspend button are the ACCOUNT's — which really is an approved buyer, ruled in fix round 1 and
 *  not re-opened here — so silence is the treatment and the applicant's own words come back,
 *  exactly as they do while the application is open. A ruled "Declined … by …" sentence is a
 *  composition item for the admin spec, not a thing this fix may write. */
function provenance(item: UserItem): string {
  if (item.state !== 'active' || item.application_status !== 'approved' || item.decided_at === null) return '';
  const by = item.decided_by_name === null ? '' : ` by staff reviewer ${item.decided_by_name}`;
  return `Approved ${formatDate(item.decided_at)}${by}.`;
}

/** Ruling D-C60 (John, 2026-09-21): the read-back a reviewer is owed beside the pill —
 *  `admin/listings.ts`'s own `decline_reason` line (`statusLine`'s comment: "the one thing its
 *  seller is owed and the one thing the reviewer needs to see beside the pill"), applied to the
 *  Users tab's own two facts. A genuinely DECLINED applicant (the account's own terminal state,
 *  never the "declined while the account stays active" seller shape fix round 2 already silences)
 *  reads the real reason instead of the design's own intent quote; an open request-info round
 *  reads the question that was asked, and the applicant's own reply once there is one — the
 *  "broken working loop" the spec names, closed the same way the reason is: real words, or
 *  nothing invented. The design's own fixtures carry none of the three fields, so this returns ''
 *  for every approved state and every pixel is kept. */
function outcome(item: UserItem): string {
  if (item.state === 'declined' && item.decision_note) return `Declined: ${item.decision_note}`;
  if (openStatus(item) === 'needs_review' && item.info_request) {
    return item.answer ? `Asked: ${item.info_request} · Answered: ${quote(item.answer)}` : `Asked: ${item.info_request}`;
  }
  return '';
}

function decision(item: UserItem, action: Action, ui: UsersUi): () => Promise<void> {
  return async () => {
    // No note needed (`approve`, `reinstate`): the direct path, and this is the ONE place that
    // alerts a refusal — the note surface below has its own error slot and would otherwise show
    // the same message twice, once inline and once in a browser alert.
    if (!NOTE_REQUIRED.includes(action)) {
      const result = await ui.decide(item, action, '');
      if (!result.ok) window.alert(result.message);
      return;
    }
    // The whole exchange — submit, retry-on-refusal with the note kept, or cancel — lives inside
    // `decideWithNote` (ruling D-C60); this passes it the ONE way a submit ever reaches the API.
    await ui.decideWithNote(item, action, (note) => ui.decide(item, action, note));
  };
}

/**
 * Exactly the shape of `sets.<tab>.rows` in `adminVals()` — an array of cell arrays. The design's
 * own `set.rows.map((cells, i) => ({ cells, style }))` is what wraps them with the grid
 * (`grid-template-columns`) and the last row's `border-bottom: 0`, so returning anything else
 * would lose `style` and re-flow the table at `maxDiffPixels: 0` (review Important 3).
 *
 * `admin-users` IS one of the thirteen frozen screens, so this function IS reached by the pixel
 * oracle — through the `DesignUserRow` arm, which is where every one of its captured pixels comes
 * from (see that interface's note).
 */
export function toUserRows(items: (UserItem | DesignUserRow)[], ui: UsersUi): Cell[][] {
  return items.map((item) => {
    if ('applicant' in item) {
      return [
        cell(item.applicant, item.applicantSub),
        cell(item.affiliation, item.intent),
        { ...cell(null, null, item.pill), pillStyle: item.pillStyle },
        cell(null, null, null, null, item.actions.map((a) => ({ label: a.label, style: a.style, go: () => Promise.resolve() })))
      ];
    }
    const fields = item.fields ?? {};
    // The row's own key: its open application where it has one, else its account state (module
    // note). `PILLS` and `ACTIONS` are indexed by names pytest pins against the API's own
    // `ACCOUNT_STATES` and `TRANSITIONS`, and `OPEN_STATUSES`'s two members are in both tables —
    // `pending` and `needs_review` name an account state and an application status alike, which is
    // what lets one lookup serve both and is why no second table is introduced here.
    //
    // The fallback is for a state the API learns to report before this table learns to show it:
    // pytest pins PILLS's keys against today's `ACCOUNT_STATES`, so it cannot be reached by any
    // state that exists now.
    const key = openStatus(item) ?? item.state;
    const [pill, tone] = PILLS[key] ?? [key, 'mute'];
    const actions = ACTIONS[key];
    const flagged = item.flags.length > 0;
    return [
      // The applicant, then what qualifies the name: the design's own school/licence pair, the VIN
      // membership the footnote says is RECORDED and does not by itself grant access (ruling 6 —
      // an id nobody can see is a fact nobody can check), and the VIN Foundation role where there
      // is one (ruling 7).
      cell(item.name, join([
        text(fields.school_year), licence(text(fields.license_state)),
        text(fields.vin_member_id) && `VIN member ${text(fields.vin_member_id)}`, roleLine(item)
      ])),
      cell(
        join([text(fields.employer), item.affiliation_label ?? '']),
        // "Seller applicant" LEADS the sub-line (ruling 8): spec §6 asks that a seller application
        // be distinguishable on this tab and V3 draws no kicker, so the fact is stated in the
        // design's own ` · ` idiom rather than in an element it has none of. Then the ONE sentence
        // the design gives this cell: a reviewer's flag outranks everything (an approved account
        // keeps its affiliation hint), then the decision that closed the application, then the
        // applicant's own words.
        join([item.kind === 'seller' ? 'Seller applicant' : '', flagged
          ? `Affiliation flagged: ${item.flags.map((flag) => FLAG_TEXT[flag] ?? flag).join(' ')}`
          : provenance(item) || outcome(item) || quote(text(fields.intent))])
      ),
      cell(null, null, pill, tone),
      cell(null, null, null, null, actions ? actions.map((action) => A(LABEL[action], TONE[action], decision(item, action, ui))) : null)
    ];
  });
}

/** One page of the review queue, and far past what any real queue holds — `admin/listings.ts`'s
 *  own `PAGE_LIMIT`/`MAX_PAGES` shape and reason: a server that answers with the cursor it was
 *  given would otherwise spin for ever. 200 is `admin_users.MAX_LIST`, so a page is never short
 *  of what was asked for. */
const PAGE_LIMIT = 200;
const MAX_PAGES = 20;

interface QueuePage { items?: unknown; next_cursor?: string | null; counts?: unknown }

/** The Users tab's badge, as `GET /api/admin/users` serves it beside `items`. */
export interface UserCounts { open: number; total: number }

/** The counts, or null where the answer carried none this table can read — an older API, a shape
 *  nobody has seen, or the explicit `counts: null` the route serves on every page past the first
 *  (the count describes the whole table, so a paging caller already holds it). Null is not zero:
 *  the badge is UNMOUNTED while there is no count (amendment A36.4), because a pill reading "0" is
 *  a claim and silence is not.
 *
 *  `!= null`, not `!== undefined`: JSON `null` passes an undefined test and `null.open` THROWS —
 *  inside `list()`, which would fire A36.2's rejection arm and empty a tab that had just been read
 *  successfully (fix round 2, re-review Minor 1). Only call order kept it unreached. */
export function countsOf(body: QueuePage): UserCounts | null {
  const counts = body.counts as UserCounts | null | undefined;
  return counts != null && typeof counts.open === 'number' && typeof counts.total === 'number' ? counts : null;
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  return fetch(`/api/admin${path}`, {
    method, credentials: 'same-origin', headers,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

/** What `logic.js` sees as `this.props.adminUsers`. `reload` is the ADMIN-GATE seam (A40.3): the
 *  table's own buttons re-enter `loadAdmin()` after a decision, so a reviewer sees the queue they
 *  have just changed rather than the one they clicked on. */
export interface AdminUsersAdapter {
  list(reload: () => void): Promise<{ rows: Cell[][]; counts: UserCounts | null }>;
}

/** `decision()`'s only call into `decideWithNote` is guarded by `NOTE_REQUIRED.includes(action)`,
 *  and this table's keys ARE `NOTE_REQUIRED` — of the four, this tab renders three; Revoke is not
 *  rendered at all (see the module note), kept here regardless so the drawer already has the
 *  right words the day it returns. Typed over exactly those four actions, never `Partial<Record
 *  <Action, …>>`, so indexing it needs no fallback for an action `decideWithNote` cannot be called
 *  with — a fallback here would be untestable dead code, not a safety net. `request_info` asks the
 *  applicant for something; the other two record a reason. */
const DRAWER_LABEL: Record<'decline' | 'request_info' | 'suspend' | 'revoke', string> = {
  decline: 'Why is this account being declined?',
  request_info: 'What do you need from this applicant before a decision can be made?',
  suspend: 'Why is this account being suspended?',
  revoke: 'Why is this account being revoked?'
};

/** One `POST /api/admin/users/:id/decide`, as a `DecideOutcome` rather than a thrown error or an
 *  internal alert — the shared plumbing both `drawerUi.decide` paths (direct, and through the note
 *  drawer's own `submit`) go through, so the two can never disagree about what a refusal means. */
async function postDecision(item: UserItem, action: Action, note: string): Promise<DecideOutcome> {
  const res = await send('POST', `/users/${item.account_id}/decide`, { action, note });
  if (res.ok) return { ok: true };
  const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
  return { ok: false, message: body?.error?.message ?? 'That decision could not be recorded.' };
}

/**
 * The concrete `UsersUi`: the real decision drawer ruling D-C60 asks for
 * (`frontend/src/admin/noteDrawer.ts`, composed from the interest modal's and the applicant-answer
 * card's own elements), replacing the one-line `window.prompt` this tab used to stand in with —
 * `admin/listings.ts`'s own stopgap for a rejection reason is untouched; this family's scope is
 * the Users tab alone.
 */
function drawerUi(reload: () => void): UsersUi {
  return {
    decide: async (item, action, note) => {
      const result = await postDecision(item, action, note);
      // Re-read whatever happened, exactly as before this ruling: a refusal is as good a reason
      // as a success — `StateConflict` is the API saying this row is not in the state the
      // reviewer was looking at, and the cure for a stale row is the queue. The drawer's own DOM
      // sits outside the table this repaints, so a retry in progress is untouched by it.
      reload();
      return result;
    },
    decideWithNote: (item, action, submit) => openNoteDrawer({
      title: LABEL[action],
      subtitle: item.name || item.email,
      // `decision()` calls this only for a `NOTE_REQUIRED` action, which is exactly `DRAWER_LABEL`'s
      // key set — asserted rather than widened with a fallback (see that table's own note).
      label: DRAWER_LABEL[action as keyof typeof DRAWER_LABEL],
      submitLabel: LABEL[action],
      maxLength: MAX_NOTE,
      submit
    })
  };
}

export function makeAdminUsersAdapter(): AdminUsersAdapter {
  return {
    list: async (reload) => {
      const ui = drawerUi(reload);
      // Real accounts are `UserItem`-shaped; the pixel oracle's harness answers this very endpoint
      // with `DesignUserRow`-shaped ones instead (the interface note explains why). `toUserRows`
      // reads either.
      const items: (UserItem | DesignUserRow)[] = [];
      let counts: UserCounts | null = null;
      let cursor: string | null = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const query = `/users?limit=${PAGE_LIMIT}${cursor === null ? '' : `&cursor=${encodeURIComponent(cursor)}`}`;
        const res = await send('GET', query);
        if (!res.ok) throw new Error('the account queue could not be read');
        const body = (await res.json()) as QueuePage;
        if (!Array.isArray(body.items)) throw new Error('the account queue answered no items');
        items.push(...(body.items as (UserItem | DesignUserRow)[]));
        // The badge counts the whole table, so only the FIRST page carries it and every page after
        // it serves `counts: null` (the route's own M-1 economy). The first page that answers is
        // the answer, and a later page never takes it away: whatever this holds is kept.
        if (counts === null) counts = countsOf(body);
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return { rows: toUserRows(items, ui), counts };
    }
  };
}
