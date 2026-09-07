import { describe, expect, it } from 'vitest';
import { MATRIX, ROLES } from '../auth/permissions';
import { PERMISSION_COLUMNS, toPermissionRows } from './permissions';

// `GET /api/admin/permissions` answers `{roles, matrix, reauth, audited}`; the matrix is
// permission → roles, and it is the only required input — the tab is read-only (spec §4:
// "code-defined, exhaustively tested, read-only in Admin").
const MATRIX_IN: Record<string, readonly string[]> = {
  'page.admin': ['admin', 'staff'],
  'page.browse': ['admin', 'buyer', 'seller', 'staff'],
  'engine.activate': ['admin'],
  'page.seller': ['seller'],
  'page.gate': ['admin', 'anonymous', 'applicant', 'buyer', 'seller', 'staff']
};

describe('toPermissionRows', () => {
  it('derives a column per generated role, in ROLES order (A-I7.2 / review M6)', () => {
    // Not the four grantable roles: the two rows a reviewer most wants to audit are what
    // `anonymous` and `applicant` reach, and with no column for them `page.gate` looked like a
    // members-only row with four ticks.
    expect(PERMISSION_COLUMNS).toEqual(['Permission', 'Meaning', 'Anonymous', 'Applicant', 'Buyer', 'Seller', 'Staff', 'Admin']);
    expect(PERMISSION_COLUMNS.slice(2)).toHaveLength(ROLES.length);
    expect(PERMISSION_COLUMNS.slice(2).map((c) => c.toLowerCase())).toEqual([...ROLES]);
  });

  it('yields one row per permission, sorted, with a tick per role that holds it', () => {
    const rows = toPermissionRows(MATRIX_IN);
    expect(rows.map((r) => r[0].main)).toEqual(['engine.activate', 'page.admin', 'page.browse', 'page.gate', 'page.seller']);
    expect(rows.map((r) => r.slice(2).map((c) => c.main))).toEqual([
      ['—', '—', '—', '—', '—', '✓'],      // engine.activate — admin only
      ['—', '—', '—', '—', '✓', '✓'],      // page.admin      — staff and admin
      ['—', '—', '✓', '✓', '✓', '✓'],      // page.browse     — every member, no applicant
      ['✓', '✓', '✓', '✓', '✓', '✓'],      // page.gate       — everyone, anonymous included
      ['—', '—', '—', '✓', '—', '—']       // page.seller     — sellers
    ]);
    expect(rows[0]).toHaveLength(PERMISSION_COLUMNS.length);
  });

  it('leaves the Meaning cell EMPTY until a meaning exists, never a copy of the name', () => {
    // `app/auth/permissions.py` carries no per-permission meaning prose — its three comments are
    // provenance notes on why a row exists — and duplicating the key down two columns was the
    // interim the review rejected. Absent beats faked (A-I7.2 / review M6); the copy arrives with
    // the Permissions-tab design delta (spec §10 open item).
    expect(toPermissionRows(MATRIX_IN)[1][1]).toMatchObject({ hasMain: false, main: '' });
    expect(toPermissionRows(MATRIX_IN, { 'page.admin': 'Reach the VIN Foundation Admin screen.' })[1][1])
      .toMatchObject({ hasMain: true, main: 'Reach the VIN Foundation Admin screen.' });
  });

  it('renders the whole real matrix — every permission, every role column', () => {
    const rows = toPermissionRows(MATRIX);
    expect(rows).toHaveLength(Object.keys(MATRIX).length);
    expect(rows.map((r) => r[0].main)).toEqual([...Object.keys(MATRIX)].sort());
    const gate = rows.find((r) => r[0].main === 'page.gate')!;
    expect(gate.slice(2).map((c) => c.main)).toEqual(['✓', '✓', '✓', '✓', '✓', '✓']);
    const own = rows.find((r) => r[0].main === 'listing.manage_own')!;
    expect(own.slice(2).map((c) => c.main)).toEqual(['—', '—', '—', '✓', '—', '—']);
  });

  it('returns the design\'s row shape — an array of cells, with no pill and no actions', () => {
    const [row] = toPermissionRows(MATRIX_IN);
    expect(Array.isArray(row)).toBe(true);
    expect(row[0]).toMatchObject({ hasMain: true, hasSub: false, sub: '', hasPill: false, pill: '', hasActions: false, actions: [] });
  });
});
