import { describe, expect, it } from 'vitest';
import { BLANK_GIF, PERSONA_DEFAULT_PASSWORD, PERSONA_EMAIL, personaCredentials, personaSession } from './harness';

// The stubbed basemap tile must be TRANSPARENT, not merely blank-looking (controller ruling
// 2026-09-07). MarketMapV3.jsx:190 adds the Esri label tile layer with `pane: "shadowPane"`
// — z-index 500, above the community mosaic's overlay pane at 400 — so an opaque stub paints
// a solid square over every mosaic cell and `npm run test:visual` then compares two unshaded
// maps at zero tolerance while proving nothing about C5/C7.
//
// Two commonly-pasted "1×1 blank GIF" strings differ by ONE character and both survive a
// naive check: `…AAIBRAA7` paints colour index 0 (the transparent one) and `…AAIBTAA7`
// paints index 1 (opaque white) while still DECLARING transparency in its Graphic Control
// Extension. Round 1's test asserted only the declaration, so the second string passed it
// and re-blinded the mosaic (review L1). So this file asserts three independent things: the
// exact bytes, the GCE's transparent-colour flag, and — the one a typo cannot fake — that
// the single pixel's LZW code IS the index the GCE nominates as transparent. The end-to-end
// half of the guard lives in visual.spec.ts, which samples the rendered map for the design's
// own ramp colours.

/** The canonical 1×1 fully transparent GIF. Any change to the constant must be deliberate. */
const KNOWN_GOOD = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

interface Gif {
  /** The Graphic Control Extension's packed flags and nominated transparent index. */
  gce: { flags: number; transparentIndex: number } | null;
  /** The colour-table index the image's first (and here only) pixel actually paints. */
  painted: number | null;
}

/** The first LZW code after the clear code — i.e. what the first pixel is painted with. */
function firstPaintedCode(bytes: number[], minCodeSize: number): number | null {
  const width = minCodeSize + 1;
  const clear = 1 << minCodeSize;
  let bit = 0;
  const read = (): number | null => {
    let v = 0;
    for (let n = 0; n < width; n++, bit++) {
      const byte = bytes[bit >> 3];
      if (byte === undefined) return null;
      v |= ((byte >> (bit & 7)) & 1) << n; // GIF packs LZW codes least-significant bit first
    }
    return v;
  };
  const first = read();
  return first === clear ? read() : first;
}

/** Walks the GIF's real block structure, so a future swap has to survive the same check. */
function parseGif(gif: Buffer): Gif {
  expect(gif.subarray(0, 6).toString('latin1')).toBe('GIF89a'); // GIF87a has no GCE at all
  const packed = gif[10];
  // Logical screen descriptor is 7 bytes after the 6-byte header; a global colour table, when
  // present (bit 7), follows it with 2^(N+1) three-byte entries where N is the low 3 bits.
  let i = 13 + (packed & 0x80 ? 3 * (1 << ((packed & 0x07) + 1)) : 0);
  let gce: Gif['gce'] = null;
  while (i < gif.length) {
    const block = gif[i];
    if (block === 0x3b) break;                                  // trailer
    if (block === 0x21) {                                       // extension
      // <introducer><label><blockSize><packed><delay lo><delay hi><transparent index>
      if (gif[i + 1] === 0xf9) gce = { flags: gif[i + 3], transparentIndex: gif[i + 6] };
      i += 3 + gif[i + 2];
      while (gif[i] !== 0x00) i += gif[i] + 1;                  // remaining data sub-blocks
      i += 1;
      continue;
    }
    if (block === 0x2c) {                                       // image descriptor
      const local = gif[i + 9];
      let j = i + 10 + (local & 0x80 ? 3 * (1 << ((local & 0x07) + 1)) : 0);
      const minCodeSize = gif[j];
      j += 1;
      const data: number[] = [];
      while (gif[j] !== 0x00) {
        for (let k = 1; k <= gif[j]; k++) data.push(gif[j + k]);
        j += gif[j] + 1;
      }
      return { gce, painted: firstPaintedCode(data, minCodeSize) };
    }
    break;
  }
  return { gce, painted: null };
}

describe('the stubbed basemap tile', () => {
  it('is a 1×1 GIF', () => {
    expect(BLANK_GIF.readUInt16LE(6)).toBe(1);
    expect(BLANK_GIF.readUInt16LE(8)).toBe(1);
  });

  it('is exactly the known-good transparent GIF, byte for byte', () => {
    expect(BLANK_GIF.toString('base64')).toBe(KNOWN_GOOD);
  });

  it('declares a transparent colour, so the label tiles cannot hide the mosaic', () => {
    const { gce } = parseGif(BLANK_GIF);
    expect(gce, 'the tile stub carries no Graphic Control Extension — it is opaque').not.toBeNull();
    expect(gce!.flags & 0x01, 'the GCE does not set the transparent-colour flag').toBe(1);
  });

  it('paints the index it nominates as transparent, not merely declares one', () => {
    const { gce, painted } = parseGif(BLANK_GIF);
    expect(painted, 'the tile paints no decodable colour index').not.toBeNull();
    expect(painted, 'the tile declares transparency but PAINTS another index — it renders opaque').toBe(gce!.transparentIndex);
  });

  it('rejects the opaque constant this replaced', () => {
    expect(parseGif(Buffer.from('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==', 'base64')).gce).toBeNull();
  });

  it('rejects the one-character twin that declares transparency but paints white', () => {
    // The shipped string with R→T: the GCE still says "index 0 is transparent", but the
    // pixel is painted with index 1 (#ffffff). Round 1's assertions all passed on this.
    const twin = parseGif(Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7', 'base64'));
    expect(twin.gce!.flags & 0x01).toBe(1);
    expect(twin.painted).not.toBe(twin.gce!.transparentIndex);
  });
});

// ---------------------------------------------------------------------------------------
// Amendment A-I7. `signInAsPersona` itself needs a browser, so the two decisions inside it
// are pulled out as pure functions and pinned here: WHICH credential is presented, and how
// often the sign-in is actually spent.
//
// The second one is not a nicety. `app/auth/limits.py`'s `SIGNIN_IP = (30, 900)` is counted
// on EVERY attempt per IP — `app/api/auth.py` calls `limits.hit` before it checks the
// credential — so a suite that signed in once per screen state would answer 429 after the
// thirtieth and the run would fail somewhere unrelated to whatever it was testing. One
// sign-in per worker process, its cookies memoised and re-added to each new context, is the
// whole budget the `app` project spends.
// ---------------------------------------------------------------------------------------
describe('the design persona credentials (A-I7)', () => {
  it('are the seeded persona and the password scripts/seed_persona.py writes by default', () => {
    expect(PERSONA_EMAIL).toBe('design@practice-match.test');
    expect(PERSONA_DEFAULT_PASSWORD).toBe('design-persona-quiet-lantern-42');
    expect(personaCredentials({})).toEqual({ email: PERSONA_EMAIL, password: PERSONA_DEFAULT_PASSWORD });
  });

  it('take PERSONA_PASSWORD from the environment whenever it is set, exactly as seed_persona.py does', () => {
    expect(personaCredentials({ PERSONA_PASSWORD: 'whatever-railway-holds' })).toEqual({
      email: PERSONA_EMAIL,
      password: 'whatever-railway-holds'
    });
  });
});

describe('personaSession spends one sign-in per worker process (A-I7)', () => {
  const jar = (held: string[]) => {
    const added: string[][] = [];
    return { added, cookies: () => Promise.resolve(held), addCookies: (c: string[]) => { added.push(c); return Promise.resolve(); } };
  };

  it('signs in on the first call and memoises the cookies the context ended up holding', async () => {
    const j = jar(['pm_session', 'pm_csrf']);
    let signIns = 0;
    const memo = await personaSession<string>(null, j, () => { signIns += 1; return Promise.resolve(); });
    expect(memo).toEqual(['pm_session', 'pm_csrf']);
    expect(signIns).toBe(1);
    expect(j.added, 'nothing is re-added on the call that did the signing in').toEqual([]);
  });

  it('re-adds the memo on every later call instead of spending another attempt against SIGNIN_IP', async () => {
    const j = jar([]);
    let signIns = 0;
    const memo = await personaSession<string>(['pm_session', 'pm_csrf'], j, () => { signIns += 1; return Promise.resolve(); });
    expect(memo).toEqual(['pm_session', 'pm_csrf']);
    expect(signIns, 'a second sign-in spends one of SIGNIN_IP\'s 30 attempts per 900 s for nothing').toBe(0);
    expect(j.added).toEqual([['pm_session', 'pm_csrf']]);
  });
});
