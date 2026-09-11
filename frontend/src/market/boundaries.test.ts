import { describe, expect, it, vi } from 'vitest';
import { FILL_LAYERS, makeMarketAdapter } from './boundaries';

const MARKETS = [{ cbsa_geoid: '12420', name: 'Austin, TX', center: [30.31, -97.75], zoom: 10 }];
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
