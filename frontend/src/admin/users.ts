/**
 * `GET /api/admin/users` → the approved design's Users table.
 *
 * The Map-engines M6 pattern: a pure mapping from the API payload to the rows the design's own
 * template already renders, so nothing about the screen's markup or its styles moves. The
 * `cell()` and `A()` shapes below — and the five pill tones — are COPIED VERBATIM from
 * `src/logic.js`'s `adminVals()`; `src/admin/users.test.ts` compares them against that file's
 * own output, so a drift on either side fails rather than silently restyling the table.
 *
 * The one thing `A()` does not carry over verbatim is `go: () => {}`: the design's is a
 * prototype no-op, and here it is the decision.
 */
import { REAUTH, type Permission } from '../auth/permissions';

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
// The next three constants are JSON, on ONE LINE each and double-quoted, because
// `tests/test_docs.py::test_the_admin_users_tables_match_the_api` parses them out of this file
// and compares them with `app/api/admin_users.py` (review Minor 3): `NOTE_REQUIRED` against its
// namesake, every action in `ACTIONS[state]` against `TRANSITIONS` (the design shows a legal
// SUBSET), and `PILLS`'s keys against `ACCOUNT_STATES`. A fifth note-required action added on
// the server would otherwise have this table POST a blank note and take a 422 at click time.
// ---------------------------------------------------------------------------------------

/** The four `admin_users.decide` refuses with `NoteRequired` when the note is blank. */
export const NOTE_REQUIRED: readonly Action[] = ["decline", "request_info", "suspend", "revoke"];

// Which permission each decision is made under. Revoke has its own (`users.revoke`) precisely
// because it — and only it — is in `permissions.REAUTH`, so which button needs a step-up is
// DERIVED from the generated matrix rather than listed here a second time.
const PERM_OF: Record<Action, Permission> = {
  approve: 'users.decide', decline: 'users.decide', request_info: 'users.decide',
  suspend: 'users.decide', reinstate: 'users.decide', revoke: 'users.revoke'
};

// The buttons the approved design shows, per state — a legal SUBSET of `TRANSITIONS`, not all of
// it: the API also allows `revoke` from `unverified`, `verified`, `pending`, `needs_review` and
// `declined`, which the design's review queue does not offer. A state with no entry here offers
// no button at all.
export const ACTIONS: Record<string, Action[]> = {"pending": ["approve", "decline", "request_info"], "needs_review": ["approve", "decline"], "active": ["suspend", "revoke"], "suspended": ["reinstate", "revoke"]};

const LABEL: Record<Action, string> = {
  approve: 'Approve', decline: 'Decline', request_info: 'Request info',
  suspend: 'Suspend', reinstate: 'Reinstate', revoke: 'Revoke'
};

const TONE: Partial<Record<Action, string>> = { approve: 'primary', decline: 'danger', revoke: 'danger' };

// `[label, tone]` for every `ACCOUNT_STATES` entry, in that order. Five carry the design's own
// labels and tones (its Users rows show Pending, Needs review, Approved and Revoked); the other
// three have no ruled label, so they show the state key, muted — absent beats faked.
export const PILLS: Record<string, [string, string]> = {"unverified": ["unverified", "mute"], "verified": ["verified", "mute"], "pending": ["Pending", "warn"], "needs_review": ["Needs review", "bad"], "declined": ["declined", "mute"], "active": ["Approved", "ok"], "suspended": ["Suspended", "info"], "revoked": ["Revoked", "bad"]};

// The design's admin Users table shows one flagged applicant, and this is its sentence. A flag
// with no approved copy is named by the flag itself rather than by prose nobody has ruled —
// `app/auth/flags.py` is free to add hints, and a hint is never a decision.
const FLAG_TEXT: Record<string, string> = { employer_keyword: 'employer appears to be a consolidator.' };

/**
 * One row of `GET /api/admin/users`'s `items`, narrowed to what the table reads. The payload
 * carries more (`created_at`, `roles`, `grants`, `application_id`, …); a structural interface
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
}

export interface UsersUi {
  /** Prompts the reviewer for the note the API requires; null when they cancel. */
  needsNote(action: Action): Promise<string | null>;
  /** Re-authenticates, then runs `post`. Only Revoke reaches it (`permissions.REAUTH`). */
  reauthThen(post: () => Promise<void>): Promise<void>;
  /** The decision itself — `POST /api/admin/users/:id/decide`, wired in Task I8. */
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
    const post = () => ui.decide(item, action, note);
    await (REAUTH.includes(PERM_OF[action]) ? ui.reauthThen(post) : post());
  };
}

/**
 * Exactly the shape of `sets.<tab>.rows` in `adminVals()` — an array of cell arrays. The design's
 * own `set.rows.map((cells, i) => ({ cells, style }))` is what wraps them with the grid
 * (`grid-template-columns`) and the last row's `border-bottom: 0`, so returning anything else
 * would lose `style` and re-flow the table at `maxDiffPixels: 0` (review Important 3).
 *
 * There is no "Seller" kicker: the V3 Admin Users tab has no such element and neither does its
 * `cell()`, so rendering one would mean editing a screen that must stay byte-identical to V2.
 * How a seller application is distinguished on that tab is a Rev 3 design item.
 */
export function toUserRows(items: UserItem[], ui: UsersUi): Cell[][] {
  return items.map((item) => {
    const fields = item.fields ?? {};
    // The fallback is for a state the API learns to report before this table learns to show it:
    // pytest pins PILLS's keys against today's `ACCOUNT_STATES`, so it cannot be reached by any
    // state that exists now.
    const [pill, tone] = PILLS[item.state] ?? [item.state, 'mute'];
    const actions = ACTIONS[item.state];
    const flagged = item.flags.length > 0;
    return [
      cell(item.name, join([text(fields.school_year), licence(text(fields.license_state))])),
      cell(
        join([text(fields.employer), item.affiliation_label ?? '']),
        flagged
          ? `Affiliation flagged: ${item.flags.map((flag) => FLAG_TEXT[flag] ?? flag).join(' ')}`
          : quote(text(fields.intent))
      ),
      cell(null, null, pill, tone),
      cell(null, null, null, null, actions ? actions.map((action) => A(LABEL[action], TONE[action], decision(item, action, ui))) : null)
    ];
  });
}
