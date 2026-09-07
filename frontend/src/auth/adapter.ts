/**
 * The prototype's `auth` adapter — the seam `logic.js`'s own Sign in and Sign out handlers call
 * through (design amendments A5.1 and A5.3).
 *
 * It exists as its own module, rather than inline in `app.setup.js`, for one reason: `app.setup.js`
 * is copied verbatim into `App.vue` by `npm run gen:app` and is therefore outside the coverage
 * gate, so logic written there has no unit tests. Review round 1's C1 was exactly that: the inline
 * adapter called `api.signIn` and handed the answer straight back WITHOUT writing it into the
 * store, so after an interactive sign-in through the design's own form `useMe().me.value` stayed
 * null while `logic.js` believed it was signed in — and the next `guard()` asked
 * `can('page.browse', null)`, got false, and sent the member to the empty `unavailable` gate.
 * `main.ts`'s load-before-mount hid it from every reload path.
 */
import type { Me, MeStore } from './me';

/** The `/api/auth/*` client, narrowed to what the adapter uses — so a test can supply a fake
 *  object rather than mock the module (and so `src/auth/api.ts` stays free to grow). */
export interface AuthApi {
  signIn(email: string, password: string): Promise<Me>;
  signOut(): Promise<unknown>;
}

/** What `logic.js` sees as `this.props.auth`. */
export interface AuthAdapter {
  signIn(email: string, password: string): Promise<Me>;
  signOut(): Promise<void>;
}

/** The store, narrowed to the two writes the adapter performs. */
export type AuthStore = Pick<MeStore, 'set' | 'clear'>;

export function makeAuthAdapter(api: AuthApi, store: AuthStore): AuthAdapter {
  return {
    /**
     * The ordering is the whole point: the store is written BEFORE this promise resolves, because
     * `logic.js`'s `.then` runs when it does and the very next `guard()` call reads the store.
     * The answer is still handed on — `logic.js` takes the header strings from it.
     */
    signIn: async (email, password) => {
      const me = await api.signIn(email, password);
      store.set(me);
      return me;
    },
    /**
     * `finally`, not `then`: A5.3 resets the prototype whatever the network did, so the store has
     * to agree. A populated store behind a signed-out screen is a stale principal the next
     * `guard()` would trust. The rejection is still propagated for a caller that wants to know;
     * A5.3's own `.catch` is what decides the prototype does not care.
     */
    signOut: async () => {
      try {
        await api.signOut();
      } finally {
        store.clear();
      }
    }
  };
}
