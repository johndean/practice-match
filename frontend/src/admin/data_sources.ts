/**
 * `GET /api/admin/data-sources` → the approved design's Data Sources table (Task A38; ruling
 * D-C53, John, 2026-09-13: "all the admin tabs must be factual and fully functional, zero-gaps,
 * zero-fake data, everything must be surfaced and wired to UX").
 *
 * The tab CLAUDE.md calls legally load-bearing — "Blocked datasets never ship … The admin Data
 * Sources tab shows this gate; keep it" — had been 100 % fixture since the design was approved,
 * and two of its five literal rows were false about the running product: the basemap row said
 * OpenStreetMap / ODbL (the product loads Esri tiles; the Census registry holds CARTO) and the
 * pet-ownership row showed an "Unresolved" pill over a dataset `dataset_registry` records as
 * `blocked`. `app/api/admin_data_sources.py` had answered the truth since Task A9 and nothing
 * read it. This module is the read.
 *
 * The M6 pattern `frontend/src/admin/users.ts` established and `admin/listings.ts` repeated: a
 * pure mapping from the API payload to the rows the design's own template already renders, with
 * `cell()` and `A()` copied VERBATIM from `src/logic.js`'s `adminVals()` a THIRD time —
 * independently of both other copies, so a drift on any side fails on its own rather than one
 * copy silently covering for another.
 *
 * **`attribution_text` is served VERBATIM and is never composed here.** It is legally
 * load-bearing (Census spec §12; CLAUDE.md "Attribution stays visible"), and the whole reason it
 * is held in `dataset_registry` is that a terms change propagates in one UPDATE. This module
 * prints the column and nothing else — no prefix, no join, no fallback.
 *
 * **One action, because one action is backed (controller ruling 18, 2026-09-13).** The design's
 * own "Assign review" and "Open question" buttons called nothing and no route exists for either;
 * they are REMOVED from the design by amendments A38.4/A38.5 rather than left as no-ops here, so
 * the reference and the app agree about a table with no unbacked button on it. "View terms" is
 * kept and wired — it opens `license_url` — and rendered only where that column is non-null. The
 * real licence decision (`POST /api/admin/data-sources/{key}/license`: Clear or Block with a
 * note, behind REAUTH) exists on the server and has NO element in V3; composing one is the admin
 * spec's to approve, and it is recorded as a composition item in the A38 report rather than
 * invented here.
 *
 * **The badge is derived from this same payload, not from a second request.** The route answers
 * the WHOLE registry in one unpaginated list, so `notCleared` over the rows the tab is already
 * rendering is exact — the condition the Users and Listings badges cannot meet, which is why
 * those two need a server-side `counts` object and this one does not. The rule is the design's
 * own: its literal "2" is the two of its five fixture rows that are not Cleared.
 */

export interface ActionButton { label: string; go: () => Promise<void>; style: string }

export interface Cell {
  hasMain: boolean; main: string;
  hasSub: boolean; sub: string;
  hasPill: boolean; pill: string; pillStyle: string;
  hasActions: boolean; actions: ActionButton[];
}

/** Verbatim from logic.js's `adminVals()`, `go` excepted (the design's own is a prototype
 *  no-op; here it opens the terms page). */
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

/** Verbatim from logic.js's `adminVals()`. */
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

// ---------------------------------------------------------------------------------------
// JSON, on ONE LINE and double-quoted, exactly as `admin/users.ts` and `admin/listings.ts` write
// their own tables — `tests/test_docs.py::test_the_admin_data_sources_table_matches_the_registry`
// parses it out of this file and compares its keys with the CHECK constraint on
// `dataset_registry.license_status` (`migrations/017_census_registry.sql`). Unlike the other two
// tabs this is not a SUBSET: the column has exactly three values and the design draws all three.
// ---------------------------------------------------------------------------------------

/** `[label, tone]` per `dataset_registry.license_status` — the design's own three words and its
 *  own three tones, read off `adminVals()`'s `sets.data.rows` (`data_sources.test.ts` pins them
 *  against it). A value the column cannot hold would show its own key, muted: absent beats faked,
 *  `toDataSourceRows`'s fallback below. */
export const PILLS: Record<string, [string, string]> = { "cleared": ["Cleared", "ok"], "unresolved": ["Unresolved", "bad"], "blocked": ["Blocked", "bad"] };

/** Values `dataset_registry.vintage` and `active_vintage.vintage` hold where the dataset HAS no
 *  vintage — placeholders and machine identifiers, never something anyone declared (review F10).
 *  `vintage` is NOT NULL, so without this the tab printed "Declared vintage n/a" on a blocked row
 *  and "Declared vintage Current_Current", the Census Geocoder's own benchmark identifier, on
 *  another. Pinned against `app.census.registry.PLACEHOLDER_VINTAGES` by pytest, so one table
 *  governs the renderer and the pin. */
export const PLACEHOLDER_VINTAGES: string[] = ["n/a", "live", "TBD", "Current_Current", "latest", "latest quarter", "monthly release"];

/** A vintage, or null where the column holds a placeholder instead of one. */
function realVintage(v: string | null): string | null {
  return v !== null && !PLACEHOLDER_VINTAGES.includes(v) ? v : null;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "June 2026" from an ISO timestamp. The design's own date vocabulary ON THIS TAB — its
 *  pet-ownership fixture row reads "Last checked June 2026" — so nothing finer is invented here.
 *  UTC, and never `Date#toLocaleDateString`, for the reason `admin/listings.ts` records: that
 *  reads the RUNTIME's locale and the reviewer's own browser offset would otherwise move the
 *  month the API actually stamped. */
function formatMonth(iso: string): string {
  const d = new Date(iso);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** Thousands separators without `toLocaleString`, the same rule and the same one-liner
 *  `src/listings/seller.ts` uses (A-SL23 (6) m1). */
function grouped(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** The newest `ingest_run` for this dataset, as one clause — or null where there has never been
 *  one. A run that did not SUCCEED is never reported as a load: "Loaded June 2026 (0 rows)" for a
 *  failed run is the kind of sentence this tab exists to prevent. */
function loadNote(run: IngestRun | null): string | null {
  if (run === null) return null;
  // `finished_at` is null while a run is still going; the status is then the whole story.
  const when = run.finished_at === null ? '' : ` ${formatMonth(run.finished_at)}`;
  if (run.status === 'succeeded') return `Loaded${when} (${grouped(run.rows_written ?? 0)} rows)`;
  return `Last load ${run.status}${when}`;
}

export interface IngestRun { status: string; finished_at: string | null; rows_written: number | null }

/**
 * One row of `GET /api/admin/data-sources` (`app/api/admin_data_sources.py::_row`), narrowed to
 * what the table reads. A structural interface, so the real payload is assignable without
 * restating the one field this tab does not print.
 *
 * **`api_dataset_id` is deliberately NOT rendered** (fix round 1, review M6). D-C53's rule is that
 * everything must be SURFACED, and every other served field now is — `vintage` and
 * `active_vintage_note` joined the Dataset sub-line in the same round. This one is an IDENTIFIER,
 * not information: it is the dataset's path on the provider's own API (`2023/acs/acs5`,
 * `Canvas/World_Light_Gray_Base + Canvas/World_Light_Gray_Reference`), the string the loader puts
 * in a URL. A reviewer of the licence gate never acts on it, it is the longest value the row
 * carries, and the Source column's own height budget is measured and tight
 * (`tests/census/test_registry.py::test_every_registry_note_fits_the_design_s_source_column`). It
 * is recorded here rather than left to be noticed as an omission.
 */
export interface DataSourceItem {
  dataset_key: string; display_name: string; refresh_cadence: string;
  license_status: string; license_name: string | null; license_url: string | null;
  attribution_text: string; last_verified_at: string | null; drift_flagged: boolean;
  notes: string | null; vintage: string | null;
  active_vintage: string | null; active_vintage_note: string | null; last_run: IngestRun | null;
}

/**
 * One of the DESIGN's own `sets.data.rows` fixtures, as
 * `frontend/tests/design-admin-data-sources.mjs` serves them — `design-admin-listings.mjs`'s
 * precedent (A-SL2, re-ruled A-SL23 (2)) applied to `admin-data-sources`, one of the thirteen
 * frozen screens.
 *
 * Those five rows are NOT reproducible by feeding registry columns through the derivation above:
 * the design's hand-set prose ("Refreshed annually", "Public domain. Attribution requested.
 * Ingested via the Census API.") is not any column's value. So the fixture carries the design's
 * own WORDS AND STYLES directly, read straight off `adminVals()`'s computed cells — `pillStyle`
 * and each action's `style` included, rather than tone NAMES this module would have to re-derive:
 * the `.mjs` fixture files touch only `logic.js`, never a TypeScript module, and a style string
 * copied verbatim off the design's own output cannot drift from it.
 *
 * `license_status` rides along so `notCleared` counts a fixture row exactly as it counts a real
 * one — the badge is one rule, not two.
 */
export interface DesignDataSourceRow {
  dataset_key: string; license_status: string;
  dataset: string; datasetSub: string;
  source: string; sourceSub: string;
  pill: string; pillStyle: string;
  actions: { label: string; style: string }[];
}

/** The badge: rows the VIN Foundation has not cleared (the controller's ruling, and the design's
 *  own arithmetic — its literal "2" is the two of five fixture rows that are not Cleared). Reads
 *  a design fixture and a registry row alike. */
export function notCleared(items: { license_status: string }[]): number {
  return items.filter((i) => i.license_status !== 'cleared').length;
}

/** `window.open`, isolated so the button's own promise shape stays the `ActionButton` contract's.
 *  `noopener` because the terms page is a third party's and must never reach `window.opener`. */
function openTerms(url: string): () => Promise<void> {
  return async () => { window.open(url, '_blank', 'noopener'); };
}

/**
 * Exactly the shape of `sets.<tab>.rows` in `adminVals()` — an array of cell arrays, because
 * `set.rows.map((cells, i) => ({ cells, style }))` is what wraps them with the grid and returning
 * anything else would lose `style` and re-flow the table at `maxDiffPixels: 0`.
 * `admin-data-sources` IS one of the thirteen frozen screens, so this function IS reached by the
 * pixel oracle — through the `DesignDataSourceRow` arm, which is where every one of its captured
 * pixels comes from.
 */
export function toDataSourceRows(items: (DataSourceItem | DesignDataSourceRow)[]): Cell[][] {
  return items.map((item) => {
    if ('dataset' in item) {
      return [
        cell(item.dataset, item.datasetSub),
        cell(item.source, item.sourceSub),
        { ...cell(null, null, item.pill), pillStyle: item.pillStyle },
        cell(null, null, null, null, item.actions.length
          ? item.actions.map((a) => ({ label: a.label, style: a.style, go: () => Promise.resolve() }))
          : null)
      ];
    }
    const [pill, tone] = PILLS[item.license_status] ?? [item.license_status, 'mute'];
    const dataset = [item.refresh_cadence];
    const loaded = loadNote(item.last_run);
    if (loaded !== null) dataset.push(loaded);
    // Fix round 2 (review F1/F10, controller ruling D-C51 "one fact per string"): ONE vintage
    // clause, and only where there is a vintage to name. Fix round 1 pushed `Declared vintage <v>`
    // on every row — `dataset_registry.vintage` is NOT NULL — which on a loaded row put the
    // Dataset sub-line on a third line in the 258 px column: the I1 defect one column over, made
    // by the fix for it. The LIVE vintage is what the app is allowed to read, so it is what the
    // tab names; the declared one is added only where it DIFFERS, which is the one state that
    // carries information (an activation that has not happened). Where they agree it is the same
    // fact printed twice, and where there is no live vintage there is nothing to name.
    //
    // Both halves lead with the same capitalised noun phrase (review Minor 6): the pair is joined
    // by the very ` · ` the clause list itself is joined with, so `Declared 2023 · live 2022` read
    // as two unrelated clauses, one of them lower-case and naming no noun. The 78-character cap
    // has the characters — this row composes to 47.
    //
    // The operator's activation note (A-C7 (6)) rides in the design's OWN parenthesis, the one this
    // sub-line already uses for "Loaded June 2026 (4,200 rows)", beside the vintage it explains.
    // `app/api/admin_data_sources.py`'s own docstring says this tab is its only intended reader.
    // `active_vintage.vintage` is NOT NULL so the last arm cannot be reached through the CLI, but
    // a written note is never dropped on the one surface that shows it.
    const declared = realVintage(item.vintage);
    const live = realVintage(item.active_vintage);
    const note = item.active_vintage_note ? ` (${item.active_vintage_note})` : '';
    if (live !== null) {
      dataset.push((declared !== null && declared !== live ? `Declared vintage ${declared} · Live vintage ${live}` : `Live vintage ${live}`) + note);
    } else if (item.active_vintage_note) {
      dataset.push(item.active_vintage_note);
    }
    // Always stated, both ways round: "never" is what a null means here, and a console that
    // simply omitted the line would read as "recently verified" to anyone skimming.
    dataset.push(`Terms verified ${item.last_verified_at === null ? 'never' : formatMonth(item.last_verified_at)}`);

    // `||`, not `??` (review F9): `LicenseDecision.name` carries no `min_length`, so
    // `COALESCE('', license_name)` can blank the column, and `??` kept the empty string and
    // printed a dangling " · <notes>" while `test_registry.py`'s pin composed "Licence not
    // recorded" for the same row. The renderer and the cross-language pin agree about one string.
    const source = [item.license_name || 'Licence not recorded'];
    if (item.notes) source.push(item.notes);
    // `drift_flagged` is its own field and is never derived from `last_verified_at` (the two are
    // independent; `app/api/admin_data_sources.py` records why). No new pill — the design has
    // three and this is not a fourth status.
    if (item.drift_flagged) source.push('Terms drift flagged');

    return [
      cell(item.display_name, dataset.join(' · ')),
      cell(item.attribution_text, source.join(' · ')),
      cell(null, null, pill, tone),
      cell(null, null, null, null, item.license_url === null ? null : [A('View terms', undefined, openTerms(item.license_url))])
    ];
  });
}

/** What `logic.js` sees as `this.props.adminDataSources`. The badge travels WITH the rows: they
 *  are one answer to one request, and a count that could disagree with the table under it is the
 *  defect this task removed ("Data Sources 2" over a five-row fixture). */
export interface AdminDataSourcesAdapter {
  list(): Promise<{ rows: Cell[][]; count: string }>;
}

export function makeAdminDataSourcesAdapter(): AdminDataSourcesAdapter {
  return {
    list: async () => {
      // NO `X-CSRF-Token` and NO `Content-Type`: this is a read, and both siblings gate those on
      // `method !== 'GET'` (`admin/listings.ts`'s `send`, `auth/api.ts`) for the reason the latter
      // records — `check_origin_and_csrf` returns early on GET/HEAD/OPTIONS, which is also where an
      // empty value would be refused. Fix round 1, review M4: this module sent both, which
      // contradicted its own "copied verbatim from the M6 pattern" claim.
      const res = await fetch('/api/admin/data-sources', { method: 'GET', credentials: 'same-origin' });
      if (!res.ok) throw new Error('the dataset registry could not be read');
      // The route answers the WHOLE registry as a bare array, ordered by key — no envelope and no
      // cursor (`list_data_sources`). Real production rows are `DataSourceItem`-shaped; the pixel
      // oracle's harness answers this same endpoint with `DesignDataSourceRow`-shaped ones.
      const body = (await res.json()) as unknown;
      if (!Array.isArray(body)) throw new Error('the dataset registry answered no rows');
      const items = body as (DataSourceItem | DesignDataSourceRow)[];
      return { rows: toDataSourceRows(items), count: String(notCleared(items)) };
    }
  };
}
