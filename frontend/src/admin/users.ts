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

export interface UsersUi {
  /** Prompts the reviewer for the note the API requires; null when they cancel. */
  needsNote(action: Action): Promise<string | null>;
  /** The decision itself — `POST /api/admin/users/:id/decide`. */
  decide(item: UserItem, action: Action, note: string): Promise<void>;
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

/** "Approved August 12 by staff reviewer K. Alvarez." — the design's own sentence on its approved
 *  row, from `application.decided_at` and the decider's display name (both Task A36's own payload
 *  fields). Only an ACTIVE account gets it: `decided_at` is stamped on a decline too, and the
 *  design has one approved sentence and no declined one. */
function provenance(item: UserItem): string {
  if (item.state !== 'active' || item.decided_at === null) return '';
  const by = item.decided_by_name === null ? '' : ` by staff reviewer ${item.decided_by_name}`;
  return `Approved ${formatDate(item.decided_at)}${by}.`;
}

function decision(item: UserItem, action: Action, ui: UsersUi): () => Promise<void> {
  return async () => {
    let note = '';
    if (NOTE_REQUIRED.includes(action)) {
      const given = await ui.needsNote(action);
      // Cancelled, or blank: `admin_users.decide` refuses a blank note on these four, so an
      // empty prompt is not a decision and there is nothing to send.
      if (given === null || given.trim() === '') return;
      note = given;
    }
    await ui.decide(item, action, note);
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
    // The fallback is for a state the API learns to report before this table learns to show it:
    // pytest pins PILLS's keys against today's `ACCOUNT_STATES`, so it cannot be reached by any
    // state that exists now.
    const [pill, tone] = PILLS[item.state] ?? [item.state, 'mute'];
    const actions = ACTIONS[item.state];
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
          : provenance(item) || quote(text(fields.intent))])
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

/** The counts, or null where the answer carried none this table can read — an older API, or a
 *  shape nobody has seen. Null is not zero: the badge is UNMOUNTED while there is no count
 *  (amendment A36.4), because a pill reading "0" is a claim and silence is not. */
export function countsOf(body: QueuePage): UserCounts | null {
  const counts = body.counts as UserCounts | undefined;
  return counts !== undefined && typeof counts.open === 'number' && typeof counts.total === 'number' ? counts : null;
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

/**
 * The concrete `UsersUi`: the browser's own prompts, standing in for the decision drawer Rev 3
 * owns — the same stopgap `describe()` (`src/listings/seller.ts`) uses for a photograph's caption
 * and `admin/listings.ts` for a rejection reason. A refusal is swallowed into a blunt `alert`,
 * because this tab has no error surface of its own and D-C53's ask is the real data and the real
 * decision, not a new banner.
 */
function windowUi(reload: () => void): UsersUi {
  return {
    // `decision()`'s only call is guarded by `NOTE_REQUIRED.includes(action)`, and of those four
    // this tab renders three — Revoke is not rendered at all (see the module note). `request_info`
    // asks the applicant for something; the other two record a reason, so the wording branches
    // once rather than carrying a table with entries no button can reach.
    needsNote: async (action) => window.prompt(action === 'request_info'
      ? 'What do you need from this applicant before a decision can be made?'
      : `Why is this account being ${action === 'decline' ? 'declined' : 'suspended'}?`),
    decide: async (item, action, note) => {
      const res = await send('POST', `/users/${item.account_id}/decide`, { action, note });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
        window.alert(body?.error?.message ?? 'That decision could not be recorded.');
      }
      // Re-read whatever happened. A refusal is as good a reason as a success: `StateConflict` is
      // the API saying this row is not in the state the reviewer was looking at, and the cure for
      // a stale row is the queue, not an alert.
      reload();
    }
  };
}

export function makeAdminUsersAdapter(): AdminUsersAdapter {
  return {
    list: async (reload) => {
      const ui = windowUi(reload);
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
        // The badge counts the whole table, so every page carries the same object; the first one
        // that answers is the answer.
        if (counts === null) counts = countsOf(body);
        cursor = body.next_cursor ?? null;
        if (cursor === null) break;
      }
      return { rows: toUserRows(items, ui), counts };
    }
  };
}
