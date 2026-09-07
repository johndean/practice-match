import { describe, expect, it } from 'vitest';
import { can, effectiveRoles } from './can';
import type { Me } from './me';

const me = (roles: string[], state = 'active'): Me => ({ id: '1', email: 'a@b.co', name: 'A', role: 'x', initials: 'A', state, roles, affiliation_label: null });

describe('can() mirrors the server matrix', () => {
  it('anonymous sees the gate only, plus market.read when the public flag is on', () => {
    expect(can('page.gate', null)).toBe(true);
    expect(can('page.browse', null)).toBe(false);
    expect(can('market.read', null)).toBe(false);
    expect(can('market.read', null, { marketDataPublic: true })).toBe(true);
  });
  it('a non-active account is an applicant regardless of grants', () => {
    expect(can('page.browse', me(['buyer'], 'suspended'))).toBe(false);
    expect(can('account.self', me([], 'pending'))).toBe(true);
  });
  it('roles unlock exactly the table', () => {
    expect(can('seller.apply', me(['buyer']))).toBe(true);
    expect(can('seller.apply', me(['seller']))).toBe(false);
    expect(can('users.decide', me(['staff']))).toBe(true);
    expect(can('engine.activate', me(['staff']))).toBe(false);
    expect(can('engine.activate', me(['admin']))).toBe(true);
  });

  // MARKET_DATA_PUBLIC widens `market.read` for ANONYMOUS visitors only — it is the one arm of
  // `app.auth.permissions.allowed` that is not the matrix, and `applicant` is deliberately not
  // in it. A member's answer is the matrix either way, flag or no flag.
  it('the public market flag changes nothing for anyone who is signed in', () => {
    expect(can('market.read', me(['buyer']), { marketDataPublic: true })).toBe(true);
    expect(can('market.read', me([], 'pending'), { marketDataPublic: true })).toBe(false);
  });

  // `effective_roles` (app/auth/permissions.py): an account may be `active` and hold no grant at
  // all — verified, approved, and waiting for a role. It is an applicant, not a member.
  it('an active account with no grants is an applicant', () => {
    expect(effectiveRoles(me([]))).toEqual(['applicant']);
    expect(effectiveRoles(me(['buyer']))).toEqual(['buyer', 'applicant']);
    expect(effectiveRoles(null)).toEqual(['anonymous']);
    expect(can('page.browse', me([]))).toBe(false);
    expect(can('account.self', me([]))).toBe(true);
  });
});
