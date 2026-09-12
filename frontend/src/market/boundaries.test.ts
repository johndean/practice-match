import { afterEach, describe, expect, it, vi } from 'vitest';
import { FILL_LAYERS, makeMarketAdapter } from './boundaries';
import { DEBOUNCE_MS, PAD, bboxOf, publish, reset } from '../map/viewport';

const MARKETS = [
  { cbsa_geoid: '12420', name: 'Austin, TX', center: [30.31, -97.75], zoom: 10 },
  { cbsa_geoid: '35620', name: 'New York, NY', center: [40.5129, -73.5258], zoom: 10 }
];
const collection = (layer: string) => ({
  type: 'FeatureCollection', layer, state: 'enabled',
  features: [{ type: 'Feature', id: '78704', properties: { geo_id: '78704', name: 'ZCTA5 78704', value: 92150, moe: 6420, suppressed: false, suppress_reason: null, band_ambiguous: false }, geometry: { type: 'Polygon', coordinates: [] } }]
});

function fakeFetch(handler: (url: string) => { ok?: boolean; status?: number; body?: unknown }) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const r = handler(url);
    return { ok: r.ok ?? true, status: r.status ?? 200, json: async () => r.body } as unknown as Response;
  });
}

// The Browse map over New York at zoom 10, the case the bbox wiring exists for: 5,935 tracts for
// the whole metro envelope against 3,706 for this box. Both are served since the caps were
// re-measured for Census tracts (`MAX_FEATURES = 12000`, `MAX_BODY_BYTES = 6_000_000`); the box is
// what keeps the answer the size of the screen.
const NY = { w: -74.2263, s: 40.1274, e: -72.8253, n: 40.8984, zoom: 10 };
const seeViewport = (v = NY) => { publish(v); vi.advanceTimersByTime(DEBOUNCE_MS); };
const refusal = (code: string) => ({ ok: false, status: 422, body: { error: { code, message: `${code} here` } } });
const boundaryUrls = (f: { mock: { calls: unknown[][] } }) => f.mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/boundaries'));
const bboxesAsked = (f: { mock: { calls: unknown[][] } }) =>
  [...new Set(boundaryUrls(f).map((u) => new URL(u, 'http://x').searchParams.get('bbox')))];

afterEach(() => { reset(); vi.useRealTimers(); });

describe('the viewport bbox (2026-09-12)', () => {
  it('sends no bbox at all when no map has published one — the pre-map boot and the reference path', async () => {
    const f = ok();
    await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX', null);
    expect(bboxesAsked(f)).toEqual([null]);
  });

  it('viewport() is the PADDED, snapped box the map is looking at, and null when there is no map', () => {
    vi.useFakeTimers();
    const adapter = makeMarketAdapter(ok() as unknown as typeof fetch);
    expect(adapter.viewport()).toBeNull();
    seeViewport();
    expect(adapter.viewport()).toBe(bboxOf(NY, PAD));
    publish(null);
    expect(adapter.viewport()).toBeNull();
  });

  it('asks every layer for the SAME box, so the three collections describe one view', async () => {
    vi.useFakeTimers();
    const f = ok();
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport();
    const at = adapter.viewport();
    await adapter.boundaries('New York, NY', at);
    expect(boundaryUrls(f)).toHaveLength(FILL_LAYERS.length);
    expect(bboxesAsked(f)).toEqual([at]);
  });

  it('onViewport fires once per settled view and the handle unsubscribes', () => {
    vi.useFakeTimers();
    const adapter = makeMarketAdapter(ok() as unknown as typeof fetch);
    const cb = vi.fn();
    const off = adapter.onViewport(cb);
    seeViewport();
    expect(cb).toHaveBeenCalledTimes(1);
    off();
    seeViewport({ ...NY, w: NY.w - 1, e: NY.e - 1 });
    expect(cb).toHaveBeenCalledTimes(1);
  });

  // The route's own refusal says "Zoom in or pass a smaller bbox." Passing a smaller bbox is
  // honouring that contract, not working around it: the padding is 0.3 of the viewport on every
  // side, and dropping it is the difference between 4,811 New York tracts and 3,706.
  it('retries ONCE unpadded when the padded box is AREA_TOO_LARGE, and draws that answer', async () => {
    vi.useFakeTimers();
    let padded: string | null = null;
    const f = fakeFetch((url) => {
      if (!url.includes('/boundaries')) return { body: MARKETS };
      const bbox = new URL(url, 'http://x').searchParams.get('bbox');
      return bbox === padded ? refusal('AREA_TOO_LARGE') : { body: collection('income') };
    });
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport();
    padded = adapter.viewport();
    await expect(adapter.boundaries('New York, NY', padded)).resolves.toHaveProperty('income');
    expect(bboxesAsked(f)).toEqual([padded, bboxOf(NY, 0)]);
    expect(boundaryUrls(f)).toHaveLength(FILL_LAYERS.length * 2);   // every layer refused, every layer re-asked
  });

  it('does NOT retry when the narrower box is refused too — the map is left empty, not looping', async () => {
    vi.useFakeTimers();
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('AREA_TOO_LARGE') : { body: MARKETS }));
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport();
    await expect(adapter.boundaries('New York, NY', adapter.viewport())).rejects.toThrow(/AREA_TOO_LARGE/);
    expect(bboxesAsked(f)).toHaveLength(2);             // the padded box and the bare one, and no more
  });

  // A box wider than the route's `MAX_BBOX_DEG` is a view of MORE than one metro, so the honest
  // next question is the metro itself — which is the request the adapter made before this change,
  // and is what keeps a zoomed-out small metro shaded rather than losing its colour.
  it('falls back to the whole metro when the viewport is too large in DEGREES, not to a blank map', async () => {
    vi.useFakeTimers();
    const f = fakeFetch((url) => {
      if (!url.includes('/boundaries')) return { body: MARKETS };
      return new URL(url, 'http://x').searchParams.get('bbox') === null ? { body: collection('income') } : refusal('BBOX_TOO_LARGE');
    });
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport({ w: -160, s: -60, e: 160, n: 60, zoom: 2 });
    await expect(adapter.boundaries('Austin, TX', adapter.viewport())).resolves.toHaveProperty('income');
    expect(bboxesAsked(f)).toEqual([adapter.viewport(), null]);
  });

  it('and when the whole metro is refused too, it stops — the map is left empty, not looping', async () => {
    vi.useFakeTimers();
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('BBOX_TOO_LARGE') : { body: MARKETS }));
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport({ w: -160, s: -60, e: 160, n: 60, zoom: 2 });
    await expect(adapter.boundaries('New York, NY', adapter.viewport())).rejects.toThrow(/BBOX_TOO_LARGE/);
    expect(boundaryUrls(f)).toHaveLength(FILL_LAYERS.length * 2);
  });

  it('does NOT retry a refusal no box can fix at all — a bad layer, a 401, a 404', async () => {
    vi.useFakeTimers();
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('BAD_LAYER') : { body: MARKETS }));
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport();
    await expect(adapter.boundaries('New York, NY', adapter.viewport())).rejects.toThrow(/BAD_LAYER/);
    expect(boundaryUrls(f)).toHaveLength(FILL_LAYERS.length);
  });

  it('does NOT retry when there was no padding to drop — a request that carried no bbox', async () => {
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('AREA_TOO_LARGE') : { body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX', null)).rejects.toThrow(/AREA_TOO_LARGE/);
    expect(boundaryUrls(f)).toHaveLength(FILL_LAYERS.length);
  });

  it('names the refusal code in the rejection, so a log says which cap was hit', async () => {
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('BAD_BBOX') : { body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX', '1,2,3,4')).rejects.toThrow(/BAD_BBOX/);
  });

  it('a refusal whose body is not the route envelope still rejects, naming the status', async () => {
    const f = fakeFetch((url) => (url.includes('/boundaries') ? { ok: false, status: 500, body: 'gateway said no' } : { body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX', null)).rejects.toThrow(/500/);
  });
});

const ok = () => fakeFetch((url) => ({ body: url.includes('/boundaries') ? collection(new URL(url, 'http://x').searchParams.get('layer') ?? 'income') : MARKETS }));

describe('the market adapter (spec §8.3)', () => {
  it('names every shaded layer, so selecting one fetches it', () => {
    // D-L1 (2026-09-12): households, pets and competition painted nothing on QA, and one reason
    // was this list — the app asks for exactly what it names here, so a layer absent from it can
    // never be drawn however well the API serves it.
    expect([...FILL_LAYERS]).toEqual(['income', 'growth', 'econ', 'households', 'pets', 'competition']);
  });

  it('resolves the metro by NAME through /api/markets, then reads one collection per fill layer', async () => {
    const seen: string[] = [];
    const f = fakeFetch((url) => { seen.push(url); return { body: url.includes('/boundaries') ? collection(new URL(url, 'http://x').searchParams.get('layer') ?? 'income') : MARKETS }; });
    const out = await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
    expect(seen[0]).toContain('/api/markets');
    expect(seen.filter((u) => u.includes('/boundaries'))).toHaveLength(FILL_LAYERS.length);
    for (const layer of FILL_LAYERS) expect(seen.some((u) => u.includes(`/api/markets/12420/boundaries?layer=${layer}`))).toBe(true);
    expect(Object.keys(out).sort()).toEqual([...FILL_LAYERS].sort());
    expect(out.income.features[0].properties.value).toBe(92150);
  });

  it('reads /api/markets ONCE, however many times boundaries is asked for', async () => {
    const f = ok();
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    await adapter.boundaries('Austin, TX');
    await adapter.boundaries('Austin, TX');
    expect((f.mock.calls as unknown[][]).filter(([u]) => String(u).endsWith('/api/markets'))).toHaveLength(1);
  });

  it('rejects when the metro is not in the catalogue, rather than guessing a geoid', async () => {
    const f = fakeFetch(() => ({ body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Nowhere, ZZ')).rejects.toThrow(/Nowhere, ZZ/);
  });

  it('a refused catalogue does not poison the adapter for ever — the next call retries it', async () => {
    let first = true;
    const f = fakeFetch((url) => {
      if (url.endsWith('/api/markets')) { const refuse = first; first = false; return refuse ? { ok: false, status: 503 } : { body: MARKETS }; }
      return { body: collection('income') };
    });
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    await expect(adapter.boundaries('Austin, TX')).rejects.toThrow();
    await expect(adapter.boundaries('Austin, TX')).resolves.toHaveProperty('income');
  });

  it('rejects on a refused CATALOGUE — there is no metro to ask about and no partial answer to give', async () => {
    await expect(makeMarketAdapter(fakeFetch(() => ({ ok: false, status: 401 })) as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow();
  });

  it('one layer refused, or absent, or rubbish, costs that layer and NOT the other five', async () => {
    // The national `zbp` load was still running when competition was built, and a layer whose
    // data is not there yet must not take the map down with it: `Promise.all` rejects on the
    // first refusal, which would have emptied `mdAreas` and blanked every layer at once —
    // exactly the failure this whole task is fixing, one level up. A layer that could not be
    // read is simply ABSENT from the answer, which the design's own `|| { features: [] }` draws
    // as no polygons and A24.32's legend declines to put a ramp over.
    for (const bad of [{ ok: false, status: 422 }, { ok: false, status: 404 }, { body: { type: 'FeatureCollection' } }]) {
      const f = fakeFetch((url) => {
        if (!url.includes('/boundaries')) return { body: MARKETS };
        return url.includes('layer=competition') ? bad : { body: collection(new URL(url, 'http://x').searchParams.get('layer') ?? 'income') };
      });
      const out = await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
      expect(Object.keys(out).sort()).toEqual(['econ', 'growth', 'households', 'income', 'pets']);
      expect(out.income.features[0].properties.value).toBe(92150);
    }
  });

  it('every layer refused rejects, so the console is told which cap or code was hit', async () => {
    // The other side of the same rule: a PARTIAL answer resolves, because one layer's absence is
    // not the map's, but an answer with NOTHING in it rejects. The app draws the same unshaded
    // map either way — `loadAreas` sets `mdAreas: {}` from both arms — and the rejection is what
    // carries the route's own code to the log.
    const f = fakeFetch((url) => (url.includes('/boundaries') ? { ok: false, status: 503 } : { body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/503/);
  });

  it('every layer answering rubbish rejects too, naming the layer — no rejection, but nothing usable', async () => {
    const f = fakeFetch((url) => ({ body: url.includes('/boundaries') ? { type: 'FeatureCollection' } : MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/features/);
  });

  it('a catalogue that is not an array rejects rather than reading `find` off it', async () => {
    const f = fakeFetch((url) => ({ body: url.endsWith('/api/markets') ? { error: 'nope' } : collection('income') }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/catalogue/);
  });

  it('sends the session cookie and bounds every request with a deadline', async () => {
    const f = ok();
    await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
    for (const [, init] of f.mock.calls as unknown as [string, RequestInit][]) {
      expect(init.credentials).toBe('same-origin');
      expect(init.signal).toBeInstanceOf(AbortSignal);
    }
  });

  it('defaults to the global fetch, which is how app.setup.js builds it', async () => {
    const f = ok();
    const saved = globalThis.fetch;
    globalThis.fetch = f as unknown as typeof fetch;
    try {
      await expect(makeMarketAdapter().boundaries('Austin, TX')).resolves.toHaveProperty('econ');
    } finally { globalThis.fetch = saved; }
  });
});

// ---------------------------------------------------------------------------------------------
// Fix round 1, finding 1 — the adapter answers for the SETTLED view.
//
// `logic.js`'s guard is right and is untouched: it compares the token it was handed at issue
// against the token the adapter reports at arrival. It was being handed the LIVE view, which moves
// the instant a wheel notch does, so an answer could be discarded for a view the member was
// already back on — and the module's own "already asked" suppression then made sure nothing ever
// re-requested it. One view, one token, and both boxes of the retry cut from it.
// ---------------------------------------------------------------------------------------------
describe('the settled view is what the adapter answers for (fix round 1)', () => {
  const box1 = { w: -74.3, s: 40.1, e: -72.9, n: 40.9, zoom: 10 };
  const box2 = { ...box1, zoom: 11 };

  it("a zoom away and straight back inside the debounce keeps the answer that was in flight", async () => {
    vi.useFakeTimers();
    const f = ok();
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    const asked = vi.fn();
    adapter.onViewport(asked);

    seeViewport(box1);                               // 1. box1 settles; logic.js would ask now
    expect(asked).toHaveBeenCalledTimes(1);
    const at = adapter.viewport();                   //    the token the request carries
    const inFlight = adapter.boundaries('New York, NY', at);

    publish(box2);                                   // 2. one notch away, timer pending
    // 3. the answer lands HERE. `mine()` compares the adapter's CURRENT answer against `at`.
    expect(adapter.viewport(), 'the in-flight answer would be discarded for a view still on screen').toBe(at);
    await inFlight;

    publish(box1);                                   // 4. straight back, inside the window
    vi.advanceTimersByTime(DEBOUNCE_MS * 4);
    // 5. …and nothing was re-asked, because nothing needed to be: box1 was never abandoned.
    expect(asked).toHaveBeenCalledTimes(1);
    expect(adapter.viewport()).toBe(at);
    expect(bboxesAsked(f)).toEqual([at]);
  });

  // NOT a duplicate of `logic.test.ts`'s "DISCARDS an answer for a box the member has already
  // panned off": that one drives a stub adapter and pins `logic.js`'s guard. This pins the TOKEN
  // the real adapter reports, which is the half that was wrong.
  it('a real pan still discards the answer for the box the member left', () => {
    vi.useFakeTimers();
    const adapter = makeMarketAdapter(ok() as unknown as typeof fetch);
    seeViewport(box1);
    const at = adapter.viewport();
    seeViewport(box2);                               // a pan that SETTLES is a real move
    expect(adapter.viewport()).not.toBe(at);
  });

  it('the unpadded retry is cut from the settled view, not the live one', async () => {
    vi.useFakeTimers();
    let padded: string | null = null;
    const f = fakeFetch((url) => {
      if (!url.includes('/boundaries')) return { body: MARKETS };
      const bbox = new URL(url, 'http://x').searchParams.get('bbox');
      return bbox === padded ? refusal('AREA_TOO_LARGE') : { body: collection('income') };
    });
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport(box1);
    padded = adapter.viewport();
    publish(box2);                                   // the live view moves; the settled one has not
    await expect(adapter.boundaries('New York, NY', padded)).resolves.toHaveProperty('income');
    expect(bboxesAsked(f), 'the retry asked for ground the member is not being answered for')
      .toEqual([padded, bboxOf(box1, 0)]);
  });

  it('a torn-down map leaves NO box: viewport() is null the moment publish(null) lands', () => {
    vi.useFakeTimers();
    const adapter = makeMarketAdapter(ok() as unknown as typeof fetch);
    seeViewport(box1);
    expect(adapter.viewport()).not.toBeNull();
    publish(null);
    expect(adapter.viewport()).toBeNull();
  });
});
