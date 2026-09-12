import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEBOUNCE_MS, PAD, bboxOf, current, grid, publish, reset, settled, subscribe } from './viewport';

/** The Browse map at 1440 x 940 (playwright.config's VIEWPORT): ~1020 x 740 CSS px of map beside
 *  the results rail, which at zoom 10 is 1.401 deg of longitude and, at New York's latitude,
 *  0.771 deg of latitude. Measured, not assumed — `frontend/tests/smoke.spec.ts`'s viewport probe
 *  reads the real element and this fixture is its arithmetic. */
const NY = { w: -74.2263, s: 40.1274, e: -72.8253, n: 40.8984, zoom: 10 };

beforeEach(() => reset());
afterEach(() => { reset(); vi.useRealTimers(); });

describe('the grid the viewport box is snapped to', () => {
  it('is one eighth of a 256 px basemap tile at the map own zoom', () => {
    // A tile is 360 / 2^zoom degrees of longitude; an eighth of it is 360 / 2^(zoom + 3).
    expect(grid(10)).toBeCloseTo(360 / 2 ** 13, 12);
    expect(grid(14)).toBeCloseTo(360 / 2 ** 17, 12);
    // 32 CSS px at every zoom, because both sides of the ratio halve together.
    expect(grid(11) * 2).toBeCloseTo(grid(10), 12);
  });

  it('takes a fractional zoom to the integer zoom the tiles are actually drawn at', () => {
    expect(grid(10.4)).toBe(grid(10));
    expect(grid(10.6)).toBe(grid(11));
  });
});

describe('bboxOf — padded, then snapped OUTWARD so the box never loses visible ground', () => {
  const parse = (s: string) => s.split(',').map(Number) as [number, number, number, number];

  it('pads by a fraction of the box own span on every side', () => {
    // The unsnapped arithmetic is visible through a box that is already grid-aligned at pad 0.
    const [w, s, e, n] = parse(bboxOf(NY, 0));
    const [pw, ps, pe, pn] = parse(bboxOf(NY, 0.3));
    expect(pw).toBeLessThan(w);
    expect(pe).toBeGreaterThan(e);
    expect(ps).toBeLessThan(s);
    expect(pn).toBeGreaterThan(n);
    // 1 + 2 x 0.3 of the span, to within the one grid cell the snap may add on each side.
    expect(pe - pw).toBeGreaterThanOrEqual((e - w) * 1.6 - 2 * grid(10));
    expect(pe - pw).toBeLessThanOrEqual((e - w) * 1.6 + 2 * grid(10));
  });

  it('CONTAINS the requested box — snapping may only ever enlarge it', () => {
    for (const pad of [0, 0.1, PAD]) {
      const [w, s, e, n] = parse(bboxOf(NY, pad));
      expect(w).toBeLessThanOrEqual(NY.w);
      expect(s).toBeLessThanOrEqual(NY.s);
      expect(e).toBeGreaterThanOrEqual(NY.e);
      expect(n).toBeGreaterThanOrEqual(NY.n);
    }
  });

  it('lands on multiples of the grid, so the SAME ground always asks the same question', () => {
    const g = grid(10);
    for (const v of parse(bboxOf(NY, PAD))) expect(Math.abs(v / g - Math.round(v / g))).toBeLessThan(1e-4);
  });

  it('is unmoved by sub-metre jitter — the cache-defeating case this rounding exists for', () => {
    // 1e-7 degrees is about 1 cm. Leaflet hands back a float that changes at this scale on every
    // single `moveend`, and without the snap every pan would be its own 24-hour cache entry.
    const jittered = { ...NY, w: NY.w + 1e-7, s: NY.s - 1e-7, e: NY.e + 1e-7, n: NY.n - 1e-7 };
    expect(bboxOf(jittered, PAD)).toBe(bboxOf(NY, PAD));
  });

  it('is unmoved by a pan SHORTER than one grid cell, and moves for one longer', () => {
    const g = grid(10);
    const nudge = (d: number) => ({ ...NY, w: NY.w + d, e: NY.e + d });
    // A box snapped strictly inside its cell survives a pan of a tenth of a cell...
    expect(bboxOf(nudge(g / 10), PAD)).toBe(bboxOf(NY, PAD));
    // ...and a pan of a whole cell moves it by exactly one cell on both edges.
    const before = bboxOf(NY, PAD).split(',').map(Number);
    const after = bboxOf(nudge(g), PAD).split(',').map(Number);
    expect(after[0] - before[0]).toBeCloseTo(g, 5);
    expect(after[2] - before[2]).toBeCloseTo(g, 5);
  });

  it('clamps to the ground the projection actually has, so a zoomed-out map still asks a legal box', () => {
    const world = { w: -400, s: -120, e: 400, n: 120, zoom: 1 };
    const [w, s, e, n] = parse(bboxOf(world, PAD));
    expect(w).toBe(-180);
    expect(e).toBe(180);
    expect(s).toBeGreaterThanOrEqual(-85.06);
    expect(n).toBeLessThanOrEqual(85.06);
  });

  it('writes six decimals, the precision the route own ST_AsGeoJSON serves', () => {
    for (const part of bboxOf(NY, PAD).split(',')) expect(part).toMatch(/^-?\d+(\.\d{1,6})?$/);
  });
});

describe('publish / subscribe — one notification per settled view', () => {
  it('starts with no viewport at all, which is how the adapter knows not to ask yet', () => {
    expect(current()).toBeNull();
  });

  it('notifies once, DEBOUNCE_MS after the last of a burst of moves', () => {
    vi.useFakeTimers();
    const cb = vi.fn();
    subscribe(cb);
    for (let i = 1; i <= 12; i++) publish({ ...NY, w: NY.w + i * grid(10), e: NY.e + i * grid(10) });
    expect(cb).not.toHaveBeenCalled();
    vi.advanceTimersByTime(DEBOUNCE_MS - 1);
    expect(cb).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('is Leaflet own zoom-transition settle, not a number of our own', () => {
    // leaflet-src.js:4827 `setTimeout(bind(this._onZoomTransitionEnd, this), 250)` and
    // leaflet.css:198 `transition: transform 0.25s` — the map is still moving until then.
    expect(DEBOUNCE_MS).toBe(250);
  });

  it('says nothing when the SNAPPED box has not changed, however many moves land', () => {
    vi.useFakeTimers();
    publish(NY);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    const cb = vi.fn();
    subscribe(cb);
    publish({ ...NY, w: NY.w + 1e-7 });
    publish({ ...NY, n: NY.n - 1e-7 });
    vi.advanceTimersByTime(DEBOUNCE_MS * 4);
    expect(cb).not.toHaveBeenCalled();
  });

  it('cancels a pending notification when the map comes back to the box it started on', () => {
    vi.useFakeTimers();
    publish(NY);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    const cb = vi.fn();
    subscribe(cb);
    publish({ ...NY, w: NY.w + grid(10) * 4, e: NY.e + grid(10) * 4 });
    vi.advanceTimersByTime(DEBOUNCE_MS - 10);
    publish(NY);
    vi.advanceTimersByTime(DEBOUNCE_MS * 4);
    expect(cb).not.toHaveBeenCalled();
    expect(current()).toEqual(NY);
  });

  it('publishing null clears the viewport and tells the adapter the map has gone', () => {
    vi.useFakeTimers();
    publish(NY);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    const cb = vi.fn();
    subscribe(cb);
    publish(null);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    expect(current()).toBeNull();
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('unsubscribing stops the callback, and a second unsubscribe is harmless', () => {
    vi.useFakeTimers();
    const cb = vi.fn();
    const off = subscribe(cb);
    off();
    off();
    publish(NY);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    expect(cb).not.toHaveBeenCalled();
  });

  it('notifies every subscriber, and one that throws does not rob the others', () => {
    vi.useFakeTimers();
    const boom = vi.fn(() => { throw new Error('no'); });
    const after = vi.fn();
    subscribe(boom);
    subscribe(after);
    publish(NY);
    expect(() => vi.advanceTimersByTime(DEBOUNCE_MS)).not.toThrow();
    expect(boom).toHaveBeenCalledTimes(1);
    expect(after).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------------------------
// THE SETTLED VIEW (fix round 1, finding 1 — reproduced by the reviewer).
//
// `publish()` advanced `settled` when a request was ISSUED while the adapter's own `viewport()`
// answered from the LIVE view, so one box could be both "already asked — suppressed" and "stale —
// discarded": zoom one step away, let the in-flight answer land (discarded against the live box),
// zoom straight back inside 250 ms (suppressed, because the key is where `settled` already is) and
// the map keeps a view nothing is drawn for and nothing will re-request. Overshoot-and-correct is
// a common gesture and a warm cache makes the window easy to hit.
//
// The fix is one sentence: the module keeps the settled VIEW, and that — not the live one — is
// what the adapter answers for.
// ---------------------------------------------------------------------------------------------
describe('settled() — the view the adapter answers for', () => {
  const box1 = { w: -74.3, s: 40.1, e: -72.9, n: 40.9, zoom: 10 };
  const box2 = { ...box1, zoom: 11 };

  it('is null until a view has actually settled, however much has been published', () => {
    vi.useFakeTimers();
    publish(box1);
    expect(settled(), 'a view mid-debounce is not settled').toBeNull();
    vi.advanceTimersByTime(DEBOUNCE_MS);
    expect(settled()).toEqual(box1);
  });

  it('does NOT move while a later view is still inside the debounce', () => {
    vi.useFakeTimers();
    publish(box1);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    publish(box2);
    expect(current(), 'the live view is the debounce input and moves at once').toEqual(box2);
    expect(settled(), 'the settled view moved before the debounce fired').toEqual(box1);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    expect(settled()).toEqual(box2);
  });

  it('a zoom away and straight back inside the debounce leaves the FIRST view settled', () => {
    vi.useFakeTimers();
    publish(box1);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    const cb = vi.fn();
    subscribe(cb);
    publish(box2);                       // away
    publish(box1);                       // …and straight back, inside the window
    vi.advanceTimersByTime(DEBOUNCE_MS * 4);
    expect(cb, 'the round trip re-asked for ground already asked for').not.toHaveBeenCalled();
    expect(settled(), 'the view on screen is not the view the adapter answers for').toEqual(box1);
  });

  it('publish(null) clears the settled view AT ONCE, not after the debounce', () => {
    vi.useFakeTimers();
    publish(box1);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    publish(null);
    expect(settled(), 'a torn-down map left a box behind for the debounce window').toBeNull();
    expect(current()).toBeNull();
  });

  it('publish(null) clears a pending timer, so a view mid-debounce cannot settle after the map has gone', () => {
    vi.useFakeTimers();
    publish(box1);
    vi.advanceTimersByTime(DEBOUNCE_MS);
    publish(box2);                       // pending
    publish(null);
    vi.advanceTimersByTime(DEBOUNCE_MS * 4);
    expect(settled()).toBeNull();
  });
});
