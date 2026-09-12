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

// The Browse map over New York at zoom 10, the case the bbox wiring exists for: 5,935 tracts
// whole-metro against the route's `MAX_FEATURES = 4000`, 3,706 for this box.
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
    expect(boundaryUrls(f)).toHaveLength(3);
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
    expect(boundaryUrls(f)).toHaveLength(6);            // three refused, three re-asked
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
    expect(boundaryUrls(f)).toHaveLength(6);
  });

  it('does NOT retry a refusal no box can fix at all — a bad layer, a 401, a 404', async () => {
    vi.useFakeTimers();
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('BAD_LAYER') : { body: MARKETS }));
    const adapter = makeMarketAdapter(f as unknown as typeof fetch);
    seeViewport();
    await expect(adapter.boundaries('New York, NY', adapter.viewport())).rejects.toThrow(/BAD_LAYER/);
    expect(boundaryUrls(f)).toHaveLength(3);
  });

  it('does NOT retry when there was no padding to drop — a request that carried no bbox', async () => {
    const f = fakeFetch((url) => (url.includes('/boundaries') ? refusal('AREA_TOO_LARGE') : { body: MARKETS }));
    await expect(makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX', null)).rejects.toThrow(/AREA_TOO_LARGE/);
    expect(boundaryUrls(f)).toHaveLength(3);
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
  it('names the three fill layers and nothing else', () => {
    expect([...FILL_LAYERS]).toEqual(['income', 'growth', 'econ']);
  });

  it('resolves the metro by NAME through /api/markets, then reads one collection per fill layer', async () => {
    const seen: string[] = [];
    const f = fakeFetch((url) => { seen.push(url); return { body: url.includes('/boundaries') ? collection(new URL(url, 'http://x').searchParams.get('layer') ?? 'income') : MARKETS }; });
    const out = await makeMarketAdapter(f as unknown as typeof fetch).boundaries('Austin, TX');
    expect(seen[0]).toContain('/api/markets');
    expect(seen.filter((u) => u.includes('/boundaries'))).toHaveLength(3);
    for (const layer of FILL_LAYERS) expect(seen.some((u) => u.includes(`/api/markets/12420/boundaries?layer=${layer}`))).toBe(true);
    expect(Object.keys(out).sort()).toEqual(['econ', 'growth', 'income']);
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

  it('rejects on a refused catalogue, a refused layer and an unparseable body — every path has an arm', async () => {
    await expect(makeMarketAdapter(fakeFetch(() => ({ ok: false, status: 401 })) as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow();
    const refusedLayer = fakeFetch((url) => (url.includes('/boundaries') ? { ok: false, status: 422 } : { body: MARKETS }));
    await expect(makeMarketAdapter(refusedLayer as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow();
    const rubbish = fakeFetch((url) => ({ body: url.includes('/boundaries') ? { type: 'FeatureCollection' } : MARKETS }));
    await expect(makeMarketAdapter(rubbish as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/features/);
  });

  it('an ABSENT route (404, the deploy-order case) rejects like any other refusal', async () => {
    const missing = fakeFetch((url) => (url.includes('/boundaries') ? { ok: false, status: 404 } : { body: MARKETS }));
    await expect(makeMarketAdapter(missing as unknown as typeof fetch).boundaries('Austin, TX')).rejects.toThrow(/404/);
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
