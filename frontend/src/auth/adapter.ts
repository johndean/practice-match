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
 * `can('page.browse', null)`, got false, and sent the member to the `unavailable` gate — which at
 * the time rendered an empty column, since the card A8.4 fills did not exist yet.
 * `main.ts`'s load-before-mount hid it from every reload path.
 *
 * A-L14: After an interactive sign-in, the adapter re-reads the listings catalogue so the member
 * sees seeded practices instead of invented fixtures. If the read fails, it retries once; if the
 * retry also fails, it clears the store and rejects with an error message that the design's
 * sign-in card will display. The member stays on the gate and can retry by signing in again.
 */
import type { ApplicationsMe, Status } from './api';
import type { Me, MeStore } from './me';
import type { Practice, Markets } from '../listings/load';

/** The `/api/auth/*` client, narrowed to what the adapter uses — so a test can supply a fake
 *  object rather than mock the module (and so `src/auth/api.ts` stays free to grow). */
export interface AuthApi {
  signIn(email: string, password: string): Promise<Me>;
  signOut(): Promise<unknown>;
  signUp(email: string, password: string): Promise<Status>;
  verify(token: string): Promise<Status>;
  forgot(email: string): Promise<Status>;
  reset(token: string, password: string): Promise<Status>;
  acceptInvite(token: string, password: string): Promise<Status>;
  apply(kind: string, fields: Record<string, unknown>): Promise<{ id: string; status: string }>;
  answer(applicationId: string, answer: string): Promise<Status>;
  applicationsMe(): Promise<ApplicationsMe>;
  resendVerification(): Promise<Status>;
}

/** What `logic.js` sees as `this.props.auth`. */
export interface AuthAdapter {
  signIn(email: string, password: string): Promise<Me>;
  signOut(): Promise<void>;
  signUp(email: string, password: string): Promise<Status>;
  verify(token: string): Promise<Status>;
  forgot(email: string): Promise<Status>;
  reset(token: string, password: string): Promise<Status>;
  acceptInvite(token: string, password: string): Promise<Status>;
  apply(kind: string, fields: Record<string, unknown>): Promise<{ id: string; status: string }>;
  answer(applicationId: string, answer: string): Promise<Status>;
  applicationsMe(): Promise<ApplicationsMe>;
  resendVerification(): Promise<Status>;
}

/** The store, narrowed to the two writes the adapter performs. */
export type AuthStore = Pick<MeStore, 'set' | 'clear'>;

/** The listings loader, narrowed to what the adapter uses for re-reads on sign-in. */
export interface ListingsLoader {
  (fetchFn: typeof fetch, practices: Practice[], markets: Markets, url?: string,
   vets?: Record<string, number>, econK?: Record<string, number>): Promise<boolean>;
}

export function makeAuthAdapter(
  api: AuthApi,
  store: AuthStore,
  loadListings?: ListingsLoader,
  fetchFn?: typeof fetch,
  practices?: Practice[],
  markets?: Markets,
  // A-C26: the re-read must install the market figure maps too, or a member who signs in
  // interactively gets fresh practices on stale Browse layers (0.1.15, the B7/B8 + L8 seam).
  vets?: Record<string, number>,
  econK?: Record<string, number>
): AuthAdapter {
  return {
    /**
     * The ordering is the whole point: the store is written BEFORE this promise resolves, because
     * `logic.js`'s `.then` runs when it does and the very next `guard()` call reads the store.
     * The answer is still handed on — `logic.js` takes the header strings from it.
     *
     * A-L14: After the store write, re-read the listings catalogue so the member sees seeded
     * practices instead of fixtures. If the read fails, retry once; if the retry also fails, clear
     * the store and reject with an error message so the form's existing error handler keeps the
     * member on the gate and shows the message.
     */
    signIn: async (email, password) => {
      const me = await api.signIn(email, password);
      store.set(me);

      // A-L14: Re-read listings only when all required parameters are available (not in tests
      // that don't care about listings, and not before mount when the bootstrap provides them).
      if (loadListings && fetchFn && practices && markets) {
        const firstAttempt = await loadListings(fetchFn, practices, markets, undefined, vets, econK).catch(() => false);
        if (!firstAttempt) {
          // Retry once on failure.
          const secondAttempt = await loadListings(fetchFn, practices, markets, undefined, vets, econK).catch(() => false);
          if (!secondAttempt) {
            // Both failed: clear the store and reject so the form shows the error and keeps
            // the member on the gate.
            store.clear();
            throw new Error('Signed in, but the listings could not be loaded. Please try again.');
          }
        }
      }

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
    },
    // The rest of the account lifecycle: plain pass-throughs. Unlike signIn/signOut, none of
    // these has an opinion about the store — a sign-up, a reset, an application answer, none of
    // them changes who `useMe()` says the visitor is, so none of them touches it.
    signUp: (email, password) => api.signUp(email, password),
    verify: (token) => api.verify(token),
    forgot: (email) => api.forgot(email),
    reset: (token, password) => api.reset(token, password),
    acceptInvite: (token, password) => api.acceptInvite(token, password),
    apply: (kind, fields) => api.apply(kind, fields),
    answer: (applicationId, text) => api.answer(applicationId, text),
    applicationsMe: () => api.applicationsMe(),
    // A-S4.1: the "Send it again" button's other branch — used when the visitor reached the
    // check-email card by SIGNING IN rather than by signing up, so no password is in hand.
    resendVerification: () => api.resendVerification()
  };
}
