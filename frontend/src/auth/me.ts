import { ref, type Ref } from 'vue';
import * as api from './api';

/**
 * Exactly what `GET /api/me` answers — `app.api.auth.me_payload`. `role` and `initials` are the
 * design's persona strings, computed there from the matrix rather than stored, so the header and
 * the account menu render from this and nothing else.
 */
export interface Me {
  id: string;
  email: string;
  name: string;
  role: string;
  initials: string;
  state: string;
  roles: string[];
  affiliation_label: string | null;
}

export interface MeStore {
  /** Null until `/api/me` has answered, and null again for a signed-out visitor. */
  me: Ref<Me | null>;
  /**
   * `MARKET_DATA_PUBLIC`, from `GET /api/config` (A-I7.2). A property of the DEPLOYMENT, not of
   * the visitor, which is why `clear()` leaves it alone: it is what the Browse market column
   * passes to `can('market.read', me, { marketDataPublic })` for an anonymous visitor.
   */
  marketDataPublic: Ref<boolean>;
  /** Reads `/api/config` then `/api/me`; I8's `main.ts` awaits this once before mount. */
  load(): Promise<Me | null>;
  /** What `signIn` feeds it — the sign-in response IS the `/api/me` payload. */
  set(me: Me): void;
  /** What `signOut` calls. The flag is not the visitor's, so it survives. */
  clear(): void;
}

// Two module-level refs, deliberately not a Pinia store and not provide/inject: CLAUDE.md rules
// out adding a store to the design's port, and the whole state is one nullable object and a flag.
const current = ref<Me | null>(null);
const marketDataPublic = ref(false);

/**
 * `MARKET_DATA_PUBLIC`, or `false` when the API could not be asked.
 *
 * `=== true`, not the raw field: the ref is typed `Ref<boolean>`, and a 200 that omitted
 * `market_data_public` would otherwise store `undefined` in it — fail-closed in effect, but the
 * type would be lying and an `=== false` check in I8 would misread it.
 *
 * The catch is NARROW on purpose. Only the two failures the API contract can produce become
 * `false`: an `AuthError` (which `api.config` raises for every non-2xx) and the `TypeError`
 * `fetch` rejects with when the request never lands at all. Anything else is a bug in this code,
 * and a blanket catch would swallow it — leaving the flag quietly closed with no trace in dev.
 */
async function readMarketDataPublic(): Promise<boolean> {
  try {
    return (await api.config()).market_data_public === true;
  } catch (error) {
    if (error instanceof api.AuthError || error instanceof TypeError) return false;
    throw error;
  }
}

export function useMe(): MeStore {
  return {
    me: current,
    marketDataPublic,
    // The flag FIRST, so I8 can render the market column on the first paint, and fail-closed on
    // every load: a config outage must never hand an anonymous visitor market data.
    load: async () => {
      marketDataPublic.value = await readMarketDataPublic();
      return (current.value = await api.me());
    },
    set: (me) => { current.value = me; },
    clear: () => { current.value = null; }
  };
}
