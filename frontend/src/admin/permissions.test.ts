import { describe, expect, it } from 'vitest';
import { MATRIX } from '../auth/permissions';
import { PERMISSION_COLUMNS, toPermissionRows } from './permissions';

// `GET /api/admin/permissions` answers `{roles, matrix, reauth, audited}`; the matrix is
// permission → roles, and it is the ONLY input here — the tab is read-only (spec §4: "code-
// defined, exhaustively tested, read-only in Admin").
const MATRIX_IN: Record<string, readonly string[]> = {
  'page.admin': ['admin', 'staff'],
  'page.browse': ['admin', 'buyer', 'seller', 'staff'],
  'engine.activate': ['admin'],
  'page.seller': ['seller']
};

describe('toPermissionRows', () => {
  it('has the six columns the read-only tab shows', () => {
    expect(PERMISSION_COLUMNS).toEqual(['Permission', 'Meaning', 'Buyer', 'Seller', 'Staff', 'Admin']);
  });

  it('yields one row per permission, sorted, with a tick per role that holds it', () => {
    const rows = toPermissionRows(MATRIX_IN);
    expect(rows.map((r) => r.cells[0].main)).toEqual(['engine.activate', 'page.admin', 'page.browse', 'page.seller']);
    expect(rows.map((r) => r.cells.slice(2).map((c) => c.main))).toEqual([
      ['—', '—', '—', '✓'],      // engine.activate — admin only
      ['—', '—', '✓', '✓'],      // page.admin      — staff and admin
      ['✓', '✓', '✓', '✓'],      // page.browse     — every member
      ['—', '✓', '—', '—']       // page.seller     — sellers
    ]);
    expect(rows[0].cells).toHaveLength(PERMISSION_COLUMNS.length);
  });

  it('names the meaning by the permission itself unless one is supplied', () => {
    // `app/auth/permissions.py` carries no per-permission MEANING prose — its three comments are
    // provenance notes on why a row exists — so the key is the meaning until the Permissions
    // tab's copy is ruled (spec §10 open item: "design deltas: … Permissions tab"). Nothing is
    // invented here in the meantime.
    expect(toPermissionRows(MATRIX_IN)[1].cells[1].main).toBe('page.admin');
    expect(toPermissionRows(MATRIX_IN, { 'page.admin': 'Reach the VIN Foundation Admin screen.' })[1].cells[1].main)
      .toBe('Reach the VIN Foundation Admin screen.');
  });

  it('renders the whole real matrix — every permission, and no role column left blank by accident', () => {
    const rows = toPermissionRows(MATRIX);
    expect(rows).toHaveLength(Object.keys(MATRIX).length);
    expect(rows.map((r) => r.cells[0].main)).toEqual([...Object.keys(MATRIX)].sort());
    // `page.gate` is the one row every role holds — anonymous included, which has no column of
    // its own, so the four member columns are all ticked.
    const gate = rows.find((r) => r.cells[0].main === 'page.gate')!;
    expect(gate.cells.slice(2).map((c) => c.main)).toEqual(['✓', '✓', '✓', '✓']);
    // …and `listing.manage_own` is a seller's alone.
    const own = rows.find((r) => r.cells[0].main === 'listing.manage_own')!;
    expect(own.cells.slice(2).map((c) => c.main)).toEqual(['—', '✓', '—', '—']);
  });

  it('reuses the design\'s cell shape, with no pill and no actions', () => {
    expect(toPermissionRows(MATRIX_IN)[0].cells[0]).toMatchObject({ hasMain: true, hasSub: false, sub: '', hasPill: false, pill: '', hasActions: false, actions: [] });
  });
});
