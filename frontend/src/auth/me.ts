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
  /** Reads `/api/me` and stores the answer; I8's `main.ts` awaits this once before mount. */
  load(): Promise<Me | null>;
  /** What `signIn` feeds it — the sign-in response IS the `/api/me` payload. */
  set(me: Me): void;
  /** What `signOut` calls. */
  clear(): void;
}

// One module-level ref, deliberately not a Pinia store and not provide/inject: CLAUDE.md rules
// out adding a store to the design's port, and the whole state is one nullable object.
const current = ref<Me | null>(null);

export function useMe(): MeStore {
  return {
    me: current,
    load: async () => (current.value = await api.me()),
    set: (me) => { current.value = me; },
    clear: () => { current.value = null; }
  };
}
