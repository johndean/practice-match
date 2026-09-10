import { describe, expect, it, vi } from 'vitest';
import { applyListings, centroid, LOAD_TIMEOUT_MS, loadListings, MAX_PAGES, MARKET_ZOOM, toPractice, US_CENTER } from './load';
import type { ApiListing, Markets, Practice } from './load';

function row(over: Partial<ApiListing> = {}): ApiListing {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    slug: 'p1',
    name: null,
    name_disclosed: false,
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
    vets: null,
    econ_k: null,
    community_label: null,
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
    // A-L10: an empty slot arrives as `null` and stays AT ITS POSITION — compacting it here would
    // caption every later photograph with the subject of the slot before it.
    expect(toPractice(row({ photos: ['/api/listings/x/photos/1', null, '/api/listings/x/photos/3'] })).photos)
      .toEqual(['/api/listings/x/photos/1', null, '/api/listings/x/photos/3']);
  });

  // A-L11: a photograph carries its OWN description, and the design's fixed slot caption is the
  // fallback (amendment A15). Added only when the API actually sent one, exactly as `name` and
  // `photos` are — the D6 design-fixture stub sends an empty list, so no fixture practice gains
  // the key and no approved state moves.
  it('adds `photoCaptions` only when the API sends at least one', () => {
    expect('photoCaptions' in toPractice(row())).toBe(false);
    expect('photoCaptions' in toPractice(row({ photo_captions: [] }))).toBe(false);
    const described = toPractice(row({
      photos: ['/api/listings/x/photos/1', '/api/listings/x/photos/2'],
      photo_captions: ['Exterior — front entrance', null]
    }));
    expect(described.photoCaptions).toEqual(['Exterior — front entrance', null]);
    // Positional, like `photos` and for the same reason: position `n` describes position `n`.
    expect(described.photoCaptions).toHaveLength(described.photos!.length);
  });

  it('tolerates a row from a server that predates photo_captions', () => {
    const { photo_captions: _dropped, ...older } = row({ photo_captions: ['x'] });
    expect('photoCaptions' in toPractice(older as ApiListing)).toBe(false);
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

  // M3 (review round 1): the fallback must be a COPY. Returning the exported constant would put
  // one shared array on every unlocatable market's `center`, so a map engine normalising a
  // LatLng in place would corrupt US_CENTER itself and every other market that borrowed it.
  it('returns a copy of US_CENTER, never the exported constant itself', () => {
    const practices = [toPractice(row({ id: 'a', market: 'M', location_disclosed: false, lat: null, lng: null }))];
    const a = centroid(practices, 'M');
    const b = centroid(practices, 'M');
    expect(a).not.toBe(US_CENTER);
    expect(a).not.toBe(b);
    a[0] = 0;
    expect(US_CENTER).toEqual([39.8283, -98.5795]);
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

  // B8: market-data maps VETS and ECON_K are installed from the API rows
  it('installs VETS and ECON_K from the API rows into the maps', async () => {
    const { VETS, ECON_K } = await import('../logic.js');
    const vetsMap = VETS as Record<string, number>;
    const econMap = ECON_K as Record<string, number>;

    applyListings(
      [
        row({ id: 'api-1', vets: 7, econ_k: 685 }),
        row({ id: 'api-2', vets: 3, econ_k: 450 })
      ],
      [],
      {},
      vetsMap,
      econMap
    );

    expect(vetsMap['api-1']).toBe(7);
    expect(vetsMap['api-2']).toBe(3);
    expect(econMap['api-1']).toBe(685);
    expect(econMap['api-2']).toBe(450);
  });

  // B8: null values don't install keys
  it('does not install keys when vets or econ_k are null', async () => {
    const { VETS, ECON_K } = await import('../logic.js');
    const vetsMap = VETS as Record<string, number>;
    const econMap = ECON_K as Record<string, number>;

    applyListings(
      [
        row({ id: 'api-null', vets: null, econ_k: null })
      ],
      [],
      {},
      vetsMap,
      econMap
    );

    expect('api-null' in vetsMap).toBe(false);
    expect('api-null' in econMap).toBe(false);
  });

  // B10 (D-C32): the label reaches the design under its own camel-case name, and a row that
  // carries none leaves the key ABSENT — `p.communityLabel || "…"` is how the design falls back
  // to its own wording, and a present-but-undefined key is a difference the D6 round-trip sees.
  it('carries community_label as communityLabel, and omits the key when the API sent none', () => {
    expect(toPractice(row({ community_label: 'Within 10 minutes of the practice' })).communityLabel)
      .toBe('Within 10 minutes of the practice');
    expect('communityLabel' in toPractice(row({ community_label: null }))).toBe(false);
  });

  // B10: the CLEAR runs before the INSTALL. It used to run after, so a row whose id is one of the
  // design's own — which is exactly what the D6 stub sends — had its figures installed and then
  // deleted, and the panel had no establishment count for any design fixture.
  it('keeps a figure a row carries under a design-fixture id', async () => {
    const { VETS, ECON_K } = await import('../logic.js');
    const vetsMap = VETS as Record<string, number>;
    const econMap = ECON_K as Record<string, number>;

    applyListings([row({ id: 'p1', vets: 8, econ_k: 612 })], [], {}, vetsMap, econMap);

    expect(vetsMap['p1']).toBe(8);
    expect(econMap['p1']).toBe(612);
  });

  // B8: fixture keys are removed when API data is installed
  it('clears fixture keys from VETS and ECON_K when the API replaces P', async () => {
    const { VETS, ECON_K } = await import('../logic.js');
    const vetsMap = VETS as Record<string, number>;
    const econMap = ECON_K as Record<string, number>;

    // Before calling applyListings, add a fixture key to verify it gets removed
    vetsMap['fixture-test'] = 999;
    econMap['fixture-test'] = 888;

    applyListings(
      [row({ id: 'api-new', vets: 5, econ_k: 500 })],
      [],
      {},
      vetsMap,
      econMap
    );

    // The fixture keys should be gone after applyListings (even if they weren't in the original fixture list)
    // and the API key should be there
    expect(vetsMap['api-new']).toBe(5);
    expect(econMap['api-new']).toBe(500);
    // The known fixture keys should be removed
    expect('p1' in vetsMap).toBe(false);
    expect('p1' in econMap).toBe(false);
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

  // ---------------------------------------------------------------------------------------
  // C1 / I2 (review round 1, ruled A-L6.2 (1)): an empty or malformed 200 NEVER installs.
  //
  // The design cannot render an empty catalogue: `detail()` reads `P[0]` and `renderVals()`
  // reads `MARKETS[s.market || "Austin, TX"].center`, both on every render — so emptying the
  // prototype's arrays is a blank APP, not an empty Browse. The brief's "a 200 always wins,
  // empty list included" is withdrawn. Between deploy and seed, and in any unseeded
  // environment, the member sees the design's fixtures: the pre-L6 behaviour.
  // ---------------------------------------------------------------------------------------
  it('an empty catalogue leaves the fixtures in place and reports false', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    await expect(loadListings(ok([]), practices, markets)).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });

  it.each([
    ['an envelope with no items at all', '{}'],
    ['a null items field', '{"items":null}'],
    ['an items field that is not an array', '{"items":{"0":{}}}']
  ])('leaves the fixtures in place when a 200 carries %s', async (_label, body) => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    const odd = vi.fn(async () => new Response(body, { status: 200, headers: { 'content-type': 'application/json' } })) as unknown as typeof fetch;
    await expect(loadListings(odd, practices, markets)).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });

  // ---------------------------------------------------------------------------------------
  // M2 (review round 1): `next_cursor` is followed until it is null. `?limit=200` is the
  // endpoint's own MAX_LIMIT, so a catalogue of 201 would otherwise truncate in silence.
  // ---------------------------------------------------------------------------------------
  const paged = (pages: Array<{ items: ApiListing[]; next_cursor: string | null }>) => {
    let i = 0;
    return vi.fn(async () => new Response(JSON.stringify(pages[i++]), {
      status: 200, headers: { 'content-type': 'application/json' }
    })) as unknown as typeof fetch;
  };

  it('asks for one page only when next_cursor is null', async () => {
    const spy = ok([row({ id: 'only' })]);
    await expect(loadListings(spy, [], {})).resolves.toBe(true);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('follows next_cursor until it is null and installs every page in order', async () => {
    const practices: Practice[] = [];
    const fetchFn = paged([
      { items: [row({ id: 'a' }), row({ id: 'b' })], next_cursor: 'cur sor/1' },
      { items: [row({ id: 'c' })], next_cursor: null }
    ]);
    await expect(loadListings(fetchFn, practices, {})).resolves.toBe(true);
    expect(practices.map((p) => p.id)).toEqual(['a', 'b', 'c']);
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(fetchFn).toHaveBeenNthCalledWith(1, '/api/listings?limit=200', expect.anything());
    expect(fetchFn).toHaveBeenNthCalledWith(2, '/api/listings?limit=200&cursor=cur%20sor%2F1', expect.anything());
  });

  it('adds the cursor with a `?` when the caller’s URL carries no query of its own', async () => {
    const fetchFn = paged([
      { items: [row({ id: 'a' })], next_cursor: 'c1' },
      { items: [row({ id: 'b' })], next_cursor: null }
    ]);
    await loadListings(fetchFn, [], {}, '/api/listings');
    expect(fetchFn).toHaveBeenNthCalledWith(2, '/api/listings?cursor=c1', expect.anything());
  });

  // A `while` that trusts the server to stop is a boot that a server can hang for ever:
  // `AbortSignal.timeout` bounds each REQUEST, not the loop, and `main.ts` awaits the loop
  // before it mounts. MAX_PAGES × 200 is far past any catalogue this product will hold.
  it('gives up after MAX_PAGES rather than following a cursor for ever', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const forever = vi.fn(async () => new Response(JSON.stringify({ items: [row({ id: 'x' })], next_cursor: 'again' }), {
      status: 200, headers: { 'content-type': 'application/json' }
    })) as unknown as typeof fetch;
    await expect(loadListings(forever, practices, {})).resolves.toBe(true);
    expect(forever).toHaveBeenCalledTimes(MAX_PAGES);
    expect(practices).toHaveLength(MAX_PAGES);
  });

  // I2: a malformed ROW still throws out of `loadListings` (nothing can validate every field
  // cheaply) — but `applyListings` maps before it clears, so the fixtures survive that too, and
  // `main.ts` catches so the app still mounts.
  it('leaves the fixtures in place when a row inside the page is malformed', async () => {
    const practices: Practice[] = [toPractice(row({ id: 'fixture' }))];
    const junkRow = vi.fn(async () => new Response('{"items":[null],"next_cursor":null}', {
      status: 200, headers: { 'content-type': 'application/json' }
    })) as unknown as typeof fetch;
    await expect(loadListings(junkRow, practices, {})).rejects.toThrow();
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
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

  // B10: the stub sends `vets` and `econ_k` too. B7 added both fields to the endpoint and this
  // stub kept answering `null` for each, so the app under test installed nothing and cleared the
  // design's own fixture keys — the docked panel's Competitive Landscape row then went blank
  // against a reference that shows "8 Veterinary Establishments", and the pixel gate said so.
  it('every design market-data figure survives toApiShape → applyListings unchanged', async () => {
    const { ECON_K, MARKETS, P, VETS } = await import('../logic.js');
    const { toApiShape } = await import('../../tests/design-listings.mjs');
    const vetsBefore = JSON.parse(JSON.stringify(VETS));
    const econBefore = JSON.parse(JSON.stringify(ECON_K));
    const practices = P as unknown as Practice[];
    applyListings(
      (practices.map(toApiShape) as unknown) as ApiListing[],
      practices,
      MARKETS as unknown as Markets,
      VETS as unknown as Record<string, number>,
      ECON_K as unknown as Record<string, number>
    );
    expect(VETS).toEqual(vetsBefore);
    expect(ECON_K).toEqual(econBefore);
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
