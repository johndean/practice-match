/**
 * The prototype's `perms` adapter — the seam `logic.js`'s header nav asks the permission matrix
 * through (amendment A40; D-C53, John: "all the admin tabs must be factual and fully functional,
 * zero-gaps, zero-fake data, everything must be surfaced and wired to UX").
 *
 * ONE source for the matrix, not two. The table itself is `src/auth/permissions.ts`, GENERATED from
 * `app/auth/permissions.py` by `npm run gen:permissions`, and `can()` is the one reader of it; this
 * adapter only carries the answer across the prop seam into the verbatim-ported prototype, which
 * has no imports of its own. A role test written inline in `logic.js` would be a second copy of the
 * matrix and would go stale the first time the server's changed (`componentDidMount`'s own
 * `r === "staff" || r === "admin"` was exactly that, and A40.4 retires it).
 *
 * A FACTORY over the store, not a snapshot of the answer: `signIn` writes `useMe()` before its
 * promise resolves and `renderVals()` runs again in the same breath, so an answer captured at boot
 * would show a member who has just signed in the doors of whoever was there before them.
 *
 * It exists as its own module, rather than inline in `app.setup.js`, for the reason `auth.ts`
 * records: that file is copied verbatim into `App.vue` by `npm run gen:app` and is therefore
 * outside the coverage gate, so logic written there has no unit tests.
 */
import { can } from './can';
import { useMe, type MeStore } from './me';
import type { Permission } from './permissions';

/** What `logic.js` sees as `this.props.perms`. */
export interface PermsAdapter {
  /** `perm` is typed loosely because the caller is untyped JavaScript: `can()` THROWS for a
   *  permission the matrix does not hold, which is the loud failure `can.ts` chose deliberately
   *  (the Playwright `pageerror` gate fails on it) rather than a silently hidden element. */
  allowed(perm: string): boolean;
}

export function makePermsAdapter(store: Pick<MeStore, 'me'> = useMe()): PermsAdapter {
  return { allowed: (perm) => can(perm as Permission, store.me.value) };
}
