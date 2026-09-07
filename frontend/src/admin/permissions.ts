/**
 * `GET /api/admin/permissions` → the read-only Permissions tab (spec §4: the matrix is
 * "code-defined, exhaustively tested, read-only in Admin").
 *
 * One row per permission, in the design's `cell()` shape and in the shape of `sets.<tab>.rows` —
 * an array of cell arrays, which `adminVals()`'s own `set.rows.map((cells, i) => ({ cells,
 * style }))` wraps with the grid. `src/admin/users.ts` owns `cell()`, ported verbatim from
 * `logic.js`, and this reuses it rather than keeping a second copy.
 *
 * Nothing here computes a grid or a `headStyle`: the design has no Permissions tab yet (spec §10
 * open item, "design deltas: … Permissions tab"), and an invented column width would be exactly
 * the faked UI CLAUDE.md rules out. The columns and the cells are what the tab needs; the layout
 * arrives with the ruling.
 */
import { ROLES } from '../auth/permissions';
import { cell, type Cell } from './users';

/**
 * Derived from the generated `ROLES`, in `ROLES` order, so a role added to the matrix gets a
 * column without anyone remembering to add one (A-I7.2 / review M6). All six, not just the four
 * grantable ones: the rows a reviewer most wants to audit are what `anonymous` and `applicant`
 * reach, and without their columns `page.gate` read as a members-only row with four ticks.
 */
export const PERMISSION_COLUMNS: readonly string[] = ['Permission', 'Meaning', ...ROLES.map((role) => role[0].toUpperCase() + role.slice(1))];

/**
 * `matrix` is permission → the roles that hold it, exactly as the endpoint answers.
 *
 * `meanings` is optional and empty by default, and a permission without one gets an EMPTY Meaning
 * cell — never a second copy of its own name (review M6). `app/auth/permissions.py` carries no
 * per-permission meaning prose (its three comments are provenance notes on why a row exists), so
 * the column stands empty until that copy is ruled. Absent beats faked.
 */
export function toPermissionRows(matrix: Record<string, readonly string[]>, meanings: Record<string, string> = {}): Cell[][] {
  // Sorted, so the table reads the same however the endpoint happens to serialise its dict.
  return Object.keys(matrix).sort().map((perm) => [
    cell(perm),
    cell(meanings[perm] ?? null),
    ...ROLES.map((role) => cell(matrix[perm].includes(role) ? '✓' : '—'))
  ]);
}
