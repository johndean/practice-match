import { MATRIX, type Permission } from './permissions';
import type { Me } from './me';

/**
 * `app.auth.permissions.effective_roles`, in TypeScript.
 *
 * Three rules, in order, and the order is the point: nobody signed in is `anonymous`; a
 * non-`active` account is an `applicant` whatever it has been granted (a suspended buyer is not
 * a buyer); and an `active` account carries `applicant` alongside its grants, so `account.self`
 * holds for every member as well as for the person still waiting.
 */
export function effectiveRoles(me: Me | null): string[] {
  if (!me) return ['anonymous'];
  if (me.state !== 'active') return ['applicant'];
  return me.roles.length ? [...me.roles, 'applicant'] : ['applicant'];
}

/** Defensive twin of app/auth/permissions.py — the server is the authority; this only hides what the API would refuse. */
export function can(perm: Permission, me: Me | null, opts: { marketDataPublic?: boolean } = {}): boolean {
  const roles = effectiveRoles(me);
  // The one arm that is not the matrix (`allowed()`'s MARKET_DATA_PUBLIC branch): it widens
  // `market.read` for ANONYMOUS visitors only. `applicant` is deliberately not in it.
  if (perm === 'market.read' && opts.marketDataPublic && roles.includes('anonymous')) return true;
  return (MATRIX[perm] as readonly string[]).some((r) => roles.includes(r));
}
