import { describe, expect, it, vi } from 'vitest';
import { applyListings, centroid, LOAD_TIMEOUT_MS, loadListings, MARKET_ZOOM, toPractice, US_CENTER } from './load';
import type { ApiListing, Markets, Practice } from './load';

function row(over: Partial<ApiListing> = {}): ApiListing {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    slug: 'p1',
    name: null,
    market: 'Austin, TX',
    area: 'Cedar Park',
    type: 'Small animal',
    city: 'Cedar Park',
    state: 'TX',
    street: '1 Main St',
    zip: '78613',
    phone: '(512) 555-0100',
    hours: 'Mon–Fri 7:30–6',
    price: 1450000,
    rev: 2100000,
    docs: 3,
    rooms: 5,
    sqft: 4200,
    bldg: 'Included',
    est: 1998,
    listed: '3 days ago',
    listed_at: '2026-09-03T00:00:00+00:00',
    status: 'published',
    pop: null,
    growth: null,
    income: null,
    hh: null,
    note: 'Demo listing seeded by the VIN Foundation.',
    staff: '3 DVMs',
    services: 'Wellness',
    facility: 'Freestanding building',
    ownership: 'Sole proprietor',
    lat: 30.5052,
    lng: -97.8203,
    location_disclosed: true,
    photos: [],
    ...over
  };
}

describe('toPractice', () => {
  it('maps every field the design template reads, under the design’s own names', () => {
    expect(toPractice(row())).toEqual({
      id: '11111111-1111-1111-1111-111111111111',
      area: 'Cedar Park',
      type: 'Small animal',
      price: 1450000,
      rev: 2100000,
      docs: 3,
      rooms: 5,
      sqft: 4200,
      bldg: 'Included',
      lat: 30.5052,
      lng: -97.8203,
      est: 1998,
      listed: '3 days ago',
      status: 'published',
      pop: null,
      growth: null,
      income: null,
      hh: null,
      note: 'Demo listing seeded by the VIN Foundation.',
      staff: '3 DVMs',
      hours: 'Mon–Fri 7:30–6',
      services: 'Wellness',
      facility: 'Freestanding building',
      ownership: 'Sole proprietor',
      market: 'Austin, TX'
    });
  });

  // A-L5.1 (1): `slug` is null whenever the name is not disclosed — the slug is the name in
  // another spelling — so the design's `p.id` is the API's `id`, never its slug.
  it('keys off the API id, which is there whether or not the name is disclosed', () => {
    expect(toPractice(row({ id: 'abc-uuid', slug: null })).id).toBe('abc-uuid');
    expect(toPractice(row({ id: 'abc-uuid', slug: 'abc-animal-hospital' })).id).toBe('abc-uuid');
  });

  it('adds `name` only when the API sends one', () => {
    expect('name' in toPractice(row())).toBe(false);
    expect(toPractice(row({ name: 'ABC Animal Hospital' })).name).toBe('ABC Animal Hospital');
  });

  it('adds `photos` only when there is at least one', () => {
    expect('photos' in toPractice(row())).toBe(false);
    expect(toPractice(row({ photos: ['/api/listings/x/photos/1'] })).photos).toEqual(['/api/listings/x/photos/1']);
  });

  it('carries a withheld location through as null rather than inventing a point', () => {
    const p = toPractice(row({ location_disclosed: false, lat: null, lng: null }));
    expect(p.lat).toBeNull();
    expect(p.lng).toBeNull();
  });
});

describe('centroid', () => {
  it('averages the located practices of one market', () => {
    const practices = [
      toPractice(row({ id: 'a', market: 'M', lat: 10, lng: 20 })),
      toPractice(row({ id: 'b', market: 'M', lat: 20, lng: 40 })),
      toPractice(row({ id: 'c', market: 'other', lat: 90, lng: 90 }))
    ];
    expect(centroid(practices, 'M')).toEqual([15, 30]);
  });

  it('ignores practices whose location is withheld', () => {
    const practices = [
      toPractice(row({ id: 'a', market: 'M', lat: 10, lng: 20 })),
      toPractice(row({ id: 'b', market: 'M', location_disclosed: false, lat: null, lng: null }))
    ];
    expect(centroid(practices, 'M')).toEqual([10, 20]);
  });

  it('falls back to the centre of the United States when nothing in the market is located', () => {
    const practices = [toPractice(row({ id: 'a', market: 'M', location_disclosed: false, lat: null, lng: null }))];
    expect(centroid(practices, 'M')).toEqual(US_CENTER);
  });
});

describe('applyListings', () => {
  it('replaces the fixture practices in place, so every reader inside logic.js sees them', () => {
    const practices: Practice[] = [toPractice(row({ id: 'old' }))];
    const original = practices;
    applyListings([row({ id: 'new' })], practices, { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } });
    expect(practices).toBe(original);
    expect(practices.map((p) => p.id)).toEqual(['new']);
  });

  it('keeps a known market’s centre and zoom exactly as the design set them', () => {
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    applyListings([row({ lat: 40, lng: -80 })], [], markets);
    expect(markets['Austin, TX']).toEqual({ center: [30.31, -97.75], zoom: 10 });
  });

  it('derives a centre for a market the design does not know', () => {
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    applyListings(
      [row({ id: 'd1', market: 'Dallas, TX', lat: 32.99, lng: -96.83 }), row({ id: 'a1' })],
      [],
      markets
    );
    expect(markets['Dallas, TX']).toEqual({ center: [32.99, -96.83], zoom: MARKET_ZOOM });
  });

  it('drops a market that no longer has a listing', () => {
    const markets: Markets = {
      'Austin, TX': { center: [30.31, -97.75], zoom: 10 },
      'Orlando, FL': { center: [28.52, -81.36], zoom: 10 }
    };
    applyListings([row()], [], markets);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });
});

describe('loadListings', () => {
  const ok = (items: ApiListing[]) =>
    vi.fn(async () => new Response(JSON.stringify({ items, next_cursor: null }), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    })) as unknown as typeof fetch;

  it('replaces the fixtures on a 200 and reports that it did', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    await expect(loadListings(ok([row({ id: 'seeded' })]), practices, markets)).resolves.toBe(true);
    expect(practices.map((p) => p.id)).toEqual(['seeded']);
  });

  it('leaves the fixtures alone when the API refuses (the signed-out gate)', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    const refused = vi.fn(async () => new Response('', { status: 401 })) as unknown as typeof fetch;
    await expect(loadListings(refused, practices, markets)).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });

  it('leaves the fixtures alone when the request throws', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const boom = vi.fn(async () => { throw new TypeError('network down'); }) as unknown as typeof fetch;
    await expect(loadListings(boom, practices, {})).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
  });

  it('leaves the fixtures alone when the body is not JSON', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const junk = vi.fn(async () => new Response('<html>', { status: 200 })) as unknown as typeof fetch;
    await expect(loadListings(junk, practices, {})).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
  });

  it('asks for the whole catalogue in one page, sends the session cookie and sets a deadline', async () => {
    const spy = ok([]);
    await loadListings(spy, [], {});
    expect(spy).toHaveBeenCalledWith('/api/listings?limit=200', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: expect.any(AbortSignal)
    });
  });

  it('asks the caller’s URL when one is given', async () => {
    const spy = ok([]);
    await loadListings(spy, [], {}, '/api/listings?limit=200&market=Austin%2C+TX');
    expect(spy).toHaveBeenCalledWith('/api/listings?limit=200&market=Austin%2C+TX', expect.anything());
  });

  it('asks for a LOAD_TIMEOUT_MS deadline and gives up when it fires', async () => {
    // Pre-flight I5: main.ts awaits this before bootstrap(), so a request that never settles is
    // a blank page, not the sign-in gate.
    //
    // The abort is driven through a spied `AbortSignal.timeout` rather than by advancing fake
    // timers: `AbortSignal.timeout` is implemented natively in Node and is not guaranteed to
    // observe vitest's fake clock, so a timer-driven version of this test could hang forever on
    // some Node builds. The spy pins BOTH halves of the contract — the deadline that was asked
    // for, and what happens when it fires — with no clock involved at all.
    const controller = new AbortController();
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal);
    try {
      const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
      const hangs = vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('The operation was aborted.', 'TimeoutError'))
            );
          })
      ) as unknown as typeof fetch;

      const pending = loadListings(hangs, practices, {});
      expect(timeoutSpy).toHaveBeenCalledWith(LOAD_TIMEOUT_MS);
      controller.abort(new DOMException('The operation was aborted.', 'TimeoutError'));

      await expect(pending).resolves.toBe(false);
      expect(practices.map((p) => p.id)).toEqual(['fixture']);
    } finally {
      timeoutSpy.mockRestore();
    }
  });
});

// -----------------------------------------------------------------------------------------
// Spec D6, in unit form. The Playwright `app` project runs against a stub of /api/listings that
// returns the DESIGN's own fixture practices in API shape; if that round trip is not the exact
// identity, the zero-tolerance pixel gate is about to fail and the fix belongs here, never in
// the tolerance.
// -----------------------------------------------------------------------------------------
describe('the design-fixture stub round-trips exactly (spec D6)', () => {
  it('every design practice survives toApiShape → toPractice unchanged', async () => {
    const { P } = await import('../logic.js');
    const { toApiShape } = await import('../../tests/design-listings.mjs');
    for (const [i, p] of (P as unknown as Practice[]).entries()) {
      expect(toPractice(toApiShape(p, i) as ApiListing)).toEqual(p);
    }
  });

  it('the design’s market centres survive applyListings unchanged', async () => {
    const { MARKETS, P } = await import('../logic.js');
    const { toApiShape } = await import('../../tests/design-listings.mjs');
    const before = JSON.parse(JSON.stringify(MARKETS));
    const practices = P as unknown as Practice[];
    applyListings((practices.map(toApiShape) as unknown) as ApiListing[], practices, MARKETS as unknown as Markets);
    expect(MARKETS).toEqual(before);
  });
});
