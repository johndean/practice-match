import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { type ChildProcess, spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { get } from 'node:http';
import { createServer } from 'node:net';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { injectProps } from './reference-server.mjs';

/** `injectProps` returns a discriminated union (a rewritten document, or a refusal). Narrowed
 *  to one optional-field shape here so each case can assert the field it is about without a
 *  type guard per line; the cases that read `.html` are the ones that assert no `status`. */
type Injected = { html?: string; status?: number; reason?: string };
const inject = (html: string, query?: string): Injected => injectProps(html, query) as Injected;

/** A GET issued with an explicit raw `path`, bypassing the client-side URL normalization
 *  `fetch()` (and every browser) applies before a request ever reaches the wire — necessary
 *  to actually exercise the server's own traversal guard: a `fetch()` for a literal "/a/../b"
 *  URL never sends the ".." at all, it resolves and sends "/b" directly. */
function rawGet(port: number, path: string): Promise<{ status: number }> {
  return new Promise((resolvePromise, reject) => {
    get({ host: 'localhost', port, path }, (res) => {
      res.resume();
      res.on('end', () => resolvePromise({ status: res.statusCode ?? 0 }));
    }).on('error', reject);
  });
}

const SCRIPT = join(fileURLToPath(new URL('.', import.meta.url)), 'reference-server.mjs');

/** An OS-assigned free port, so this test never collides with a dev server the working
 *  tree (or another test run) might already have bound to one of the fixed ports the
 *  config file uses (5173-5175, 4174). */
async function ephemeralPort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const probe = createServer();
    probe.on('error', reject);
    probe.listen(0, () => {
      const address = probe.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      probe.close(() => resolvePort(port));
    });
  });
}

async function waitUntilUp(base: string, deadline: number): Promise<void> {
  while (Date.now() < deadline) {
    try {
      await fetch(base);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 50));
    }
  }
  throw new Error(`reference-server never came up at ${base}`);
}

describe('reference-server.mjs', () => {
  let proc: ChildProcess;
  let port: number;
  let base: string;

  beforeAll(async () => {
    port = await ephemeralPort();
    base = `http://localhost:${port}`;
    proc = spawn(process.execPath, [SCRIPT, String(port)], { stdio: ['ignore', 'pipe', 'pipe'] });
    await waitUntilUp(base, Date.now() + 10_000);
  });

  afterAll(() => {
    proc.kill();
  });

  it('redirects a bare "/coming-soon" (no trailing slash) to "/coming-soon/" — relative asset URLs on the page resolve against the wrong root otherwise', async () => {
    const res = await fetch(`${base}/coming-soon`, { redirect: 'manual' });
    expect(res.status).toBe(301);
    expect(res.headers.get('location')).toBe('/coming-soon/');
  });

  it('serves the Coming Soon design at "/coming-soon/"', async () => {
    const res = await fetch(`${base}/coming-soon/`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('<title>VIN Foundation — Coming Soon</title>');
  });

  it('keeps serving the Practice Match V3 marketplace design at "/"', async () => {
    const res = await fetch(`${base}/`);
    expect(res.status).toBe(200);
    const served = await res.text();
    // The gate's own hero heading. It used to be the jump bar's "Practice Match — internal
    // working title" strip, which amendment A6.1 removed from the design — a marker inside the
    // prototype scaffolding could only ever have been temporary.
    expect(served).toContain('Veterinary Practice Transitions');
    expect(served).toContain('<script type="text/x-dc" data-dc-script');
  });

  it('rejects a traversal attempt through the coming-soon prefix rather than silently serving the marketplace file', async () => {
    // A raw literal ".." on the wire — a normal browser/fetch request would resolve this
    // client-side to "/Practice Match V3.dc.html" and never send the ".." at all.
    const res = await rawGet(port, '/coming-soon/../Practice%20Match%20V3.dc.html');
    expect([403, 404]).toContain(res.status);
  });

  it('still rejects the percent-encoded-slash bypass of the URL parser\'s own dot-segment normalization', async () => {
    const res = await rawGet(port, '/coming-soon/..%2fdesign_handoff_practice_match_v3%2fPractice%20Match%20V3.dc.html');
    expect([403, 404]).toContain(res.status);
  });

  // The wire half of the injection: the pure function is pinned above, this proves the
  // server actually applies it to the root document and refuses a bad query with a status
  // rather than a rewritten page (A-I8 / D-I8-3).
  it('applies ?props= to the design served at "/" and leaves the file itself alone', async () => {
    const query = `props=${encodeURIComponent(JSON.stringify({ startScreen: 'admin' }))}`;
    const res = await fetch(`${base}/?${query}`);
    expect(res.status).toBe(200);
    const served = await res.text();
    expect(served).toContain('&quot;startScreen&quot;:{&quot;editor&quot;:&quot;enum&quot;');
    expect(declaredProps(served).startScreen.default).toBe('admin');
    expect(served, 'the design file on disk must not have been rewritten').not.toBe(DESIGN);
    expect(await (await fetch(`${base}/`)).text(), 'a request without ?props= still serves the file verbatim').toBe(DESIGN);
  });

  // M2: the runtime re-fetches `location.href` after boot, so the URL that carries an OBJECT
  // value has to answer identically the second time too — otherwise `updateHtml` would hand React
  // a different template than the one it mounted.
  it('answers the same bytes on a second request for a ?props= URL carrying an object', async () => {
    const query = `props=${encodeURIComponent(JSON.stringify({ me: { email: 'seller@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer and seller · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer', 'seller'] } }))}`;
    const first = await (await fetch(`${base}/?${query}`)).text();
    const second = await (await fetch(`${base}/?${query}`)).text();
    expect(second).toBe(first);
    expect(declaredProps(first).me.default).toMatchObject({ email: 'seller@practice-match.test' });
  });

  it('answers 400 for an unknown prop name instead of serving a page that looks right', async () => {
    const res = await fetch(`${base}/?props=${encodeURIComponent(JSON.stringify({ startScren: 'admin' }))}`);
    expect(res.status).toBe(400);
  });

  it('ignores ?props= on a non-index asset, which has no data-props to rewrite', async () => {
    const res = await fetch(`${base}/support.js?props=${encodeURIComponent(JSON.stringify({ startScreen: 'admin' }))}`);
    expect(res.status).toBe(200);
    expect(await res.text()).toContain('dc-runtime');
  });
});

// ---------------------------------------------------------------------------------------
// `?props=` injection (amendment A-I8, decision D-I8-3).
//
// The prototype affordances that used to reach `gate-pending`, `gate-declined` and the
// member screens on the REFERENCE — the jump bar and the "Prototype — access states"
// shortcuts — leave the design in A6.1/A6.2. A static prototype has no other way in, so the
// server rewrites the served design's `data-props` DEFAULTS for the keys named in
// `?props=<json>`, and the runtime reads them exactly as it reads the file's own
// (support.js's `parseDataProps` → `propsMeta[k].default` → the Root's props).
//
// Two invariants make that safe rather than clever:
//
//  * SAME URL, SAME BYTES. support.js re-fetches `location.href` after boot to re-read the
//    template (`boot()`, support.js:159), so the injection has to be a pure function of the
//    request path AND query — which it is: it is applied on the way out, per request, and a
//    request with no `?props=` is byte-identical to the file.
//  * UNKNOWN KEYS ARE REFUSED. A typo'd prop name that was silently ignored would leave the
//    harness screenshotting the wrong state and the oracle would be generated FROM that,
//    which is the one failure mode a zero-tolerance pixel gate cannot see. 400, loudly.
// ---------------------------------------------------------------------------------------
const DESIGN = readFileSync(
  join(fileURLToPath(new URL('.', import.meta.url)), '..', '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html'),
  'utf8'
);

/** The decoded `data-props` JSON of a served document — what the runtime will read. */
function declaredProps(html: string): Record<string, { default?: unknown }> {
  const attr = /<script type="text\/x-dc" data-dc-script[^>]*data-props="([^"]*)"/.exec(html)!;
  return JSON.parse(attr[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&')) as Record<string, { default?: unknown }>;
}

describe('injectProps (A-I8 / D-I8-3)', () => {
  it('returns the document untouched, byte for byte, when there is no ?props= at all', () => {
    expect(inject(DESIGN, '').html).toBe(DESIGN);
    expect(inject(DESIGN, undefined).html).toBe(DESIGN);
    expect(inject(DESIGN, 'theme=dark').html).toBe(DESIGN);
  });

  it('rewrites only the named keys\' defaults and leaves every other entry as the design has it', () => {
    const before = declaredProps(DESIGN);
    const { html } = inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startScreen: 'admin', startGate: 'pending' }))}`);
    const after = declaredProps(html!);
    expect(after.startScreen.default).toBe('admin');
    expect(after.startGate.default).toBe('pending');
    expect(after.startViewport.default).toBe(before.startViewport.default);
    expect(after.layerPalette.default).toBe(before.layerPalette.default);
    expect(after.prototypeBar.default).toBe(before.prototypeBar.default);
    expect(Object.keys(after), 'no entry may be added or dropped').toEqual(Object.keys(before));
  });

  it('changes nothing outside the data-props attribute', () => {
    const { html } = inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startViewport: 'mobile' }))}`);
    const strip = (s: string) => s.replace(/ data-props="[^"]*"/, ' data-props="…"');
    expect(strip(html!)).toBe(strip(DESIGN));
  });

  it('is idempotent for the same query, so the runtime\'s re-fetch of location.href gets the same bytes', () => {
    const query = `props=${encodeURIComponent(JSON.stringify({ startScreen: 'browse', startGate: '', startViewport: 'mobile' }))}`;
    expect(inject(DESIGN, query).html).toBe(inject(DESIGN, query).html);
  });

  it('re-escapes the attribute so the document still parses and the runtime still reads it', () => {
    const { html } = inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startGate: 'rejected' }))}`);
    // `"` may not survive raw inside a double-quoted attribute, and `&` may not survive raw
    // at all — a bare `&quot;` in the JSON would be re-decoded as a quote on the next read.
    const attr = / data-props="([^"]*)"/.exec(html!)![1];
    expect(attr).not.toMatch(/(?<!&(?:quot|amp);)"/);
    expect(declaredProps(html!).startGate.default).toBe('rejected');
  });

  // M2 (review round 1). A5.7's `me` is an OBJECT, and it is the value the reference's whole
  // header identity comes from — but every case here injected a string, so JSON round-tripping an
  // object through an HTML attribute (nested quotes, the `·` in the role label) was untested.
  it('injects an object value and round-trips it, nested quotes and non-ASCII included', () => {
    const me = { email: 'buyer@practice-match.test', name: 'Dr. Rachel Mendes', role: 'Approved buyer · StartUp Club', initials: 'RM', state: 'active', roles: ['buyer'] };
    const { html } = inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ me }))}`);
    expect(declaredProps(html!).me.default).toEqual(me);
    // The attribute must still be a well-formed, single-quoted-out HTML attribute value.
    const attr = / data-props="([^"]*)"/.exec(html!)![1];
    expect(attr).not.toMatch(/(?<!&(?:quot|amp);)"/);
    expect(attr).toContain('StartUp Club');
    // …and `null` back again, which is how a gate state says "nobody is signed in".
    expect(declaredProps(inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ me: null }))}`).html!).me.default).toBeNull();
  });

  it('refuses an unknown prop name rather than silently screenshotting the wrong state', () => {
    expect(inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startScren: 'admin' }))}`)).toMatchObject({ status: 400 });
    expect(inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startScreen: 'admin', nope: 1 }))}`)).toMatchObject({ status: 400 });
  });

  it('refuses the $-prefixed editor metadata, which is not a prop', () => {
    expect(inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ $preview: { width: 1 } }))}`)).toMatchObject({ status: 400 });
  });

  it('refuses a ?props= that is not a JSON object', () => {
    expect(inject(DESIGN, 'props=not-json')).toMatchObject({ status: 400 });
    expect(inject(DESIGN, `props=${encodeURIComponent('[1,2]')}`)).toMatchObject({ status: 400 });
    expect(inject(DESIGN, `props=${encodeURIComponent('"a string"')}`)).toMatchObject({ status: 400 });
    expect(inject(DESIGN, `props=${encodeURIComponent('null')}`)).toMatchObject({ status: 400 });
  });

  it('refuses ?props= on a document that declares none, instead of quietly ignoring it', () => {
    expect(inject('<html><body>no dc script here</body></html>', 'props=%7B%7D')).toMatchObject({ status: 400 });
  });

  it('names the offending key in the refusal, so a harness typo is readable', () => {
    const refusal = inject(DESIGN, `props=${encodeURIComponent(JSON.stringify({ startScren: 'admin' }))}`);
    expect(refusal.reason).toContain('startScren');
  });
});

