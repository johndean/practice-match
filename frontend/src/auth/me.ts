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

export function useMe(): MeStore {
  return {
    me: current,
    marketDataPublic,
    // The flag FIRST, so I8 can render the market column on the first paint, and fail-closed on
    // every load: a config outage must never hand an anonymous visitor market data.
    load: async () => {
      marketDataPublic.value = await api.config().then((c) => c.market_data_public).catch(() => false);
      return (current.value = await api.me());
    },
    set: (me) => { current.value = me; },
    clear: () => { current.value = null; }
  };
}
