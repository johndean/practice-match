/**
 * `GET /api/admin/permissions` → the read-only Permissions tab (spec §4: the matrix is
 * "code-defined, exhaustively tested, read-only in Admin").
 *
 * One row per permission, in the design's `cell()` shape — `src/admin/users.ts` owns that
 * shape, ported verbatim from `logic.js`'s `adminVals()`, and this reuses it rather than
 * keeping a second copy. Nothing here computes a grid or a `headStyle`: the design has no
 * Permissions tab yet (spec §10 open item, "design deltas: … Permissions tab"), and an invented
 * column width would be exactly the faked UI CLAUDE.md rules out. The columns and the cells are
 * what the tab needs; the layout arrives with the ruling.
 */
import { cell, type Cell } from './users';

export const PERMISSION_COLUMNS = ['Permission', 'Meaning', 'Buyer', 'Seller', 'Staff', 'Admin'] as const;

// `anonymous` and `applicant` have no column: they hold `page.gate` and `account.self` and
// nothing else, and a reviewer reads this table to see what the four GRANTABLE roles reach.
const ROLE_COLUMNS = ['buyer', 'seller', 'staff', 'admin'] as const;

export interface PermissionRow { cells: Cell[] }

/**
 * `matrix` is permission → the roles that hold it, exactly as the endpoint answers.
 *
 * `meanings` is optional and empty by default: `app/auth/permissions.py` carries no
 * per-permission meaning prose — its three comments are provenance notes on why a row exists,
 * not descriptions of what the row lets somebody do — so the permission key IS the meaning
 * until that copy is ruled. Nothing is invented in the meantime.
 */
export function toPermissionRows(matrix: Record<string, readonly string[]>, meanings: Record<string, string> = {}): PermissionRow[] {
  // Sorted, so the table reads the same however the endpoint happens to serialise its dict.
  return Object.keys(matrix).sort().map((perm) => ({
    cells: [
      cell(perm),
      cell(meanings[perm] ?? perm),
      ...ROLE_COLUMNS.map((role) => cell(matrix[perm].includes(role) ? '✓' : '—'))
    ]
  }));
}
