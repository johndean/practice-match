// Serves the approved design bundles so Playwright can screenshot the reference(s).
// The bundle's runtime (support.js) re-fetches location.href to parse <x-dc>, so
// each root's index path must return the same bytes as its design file itself.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, resolve as resolvePath } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const PORT = Number(process.argv[2] || 5174);
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.jsx': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg',
  '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.json': 'application/json', '.md': 'text/plain'
};

// docs/design-reference/coming-soon serves the Coming Soon design (Task 11e); the
// Practice Match V3 handoff keeps serving from "/" as before. The first root whose
// prefix the request path starts with wins, so "/coming-soon" is listed first.
const ROOTS = [
  { prefix: '/coming-soon', dir: normalize(join(HERE, '../../docs/design-reference/coming-soon')), index: '/Coming Soon.dc.html' },
  { prefix: '', dir: normalize(join(HERE, '../../docs/design-reference/design_handoff_practice_match_v3')), index: '/Practice Match V3.dc.html' }
];

function resolve(pathname) {
  const root = ROOTS.find((r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`));
  const stripped = pathname.slice(root.prefix.length);
  const rel = stripped === '' || stripped === '/' ? root.index : stripped;
  const file = normalize(join(root.dir, rel));
  // The root's own index document is the only thing `?props=` may rewrite: it is the one file
  // that carries `data-props`, and it is the URL the runtime re-fetches (support.js's boot()).
  return { root, file, isIndex: file === normalize(join(root.dir, root.index)) };
}

// ---------------------------------------------------------------------------------------
// `?props=<json>` — the reference's only way into a prototype state (amendment A-I8,
// decision D-I8-3).
//
// A6.1/A6.2 take the jump bar and the "Prototype — access states" shortcuts out of the
// design, which is how `gate-pending`, `gate-declined` and every member screen used to be
// reached on the REFERENCE target. A static prototype has no session and no API, so the
// entry has to be a prop: this rewrites the served document's `data-props` DEFAULTS for the
// named keys, and the bundle's runtime reads them exactly as it reads the file's own
// (support.js `parseDataProps` → `propsMeta[k].default` → the Root element's props).
//
// It is a pure function of (document, query) on purpose, for two reasons:
//
//  * support.js re-fetches `location.href` after boot to re-read the template
//    (support.js:159). Same URL → same bytes, so the "each root's index path returns the
//    same bytes as its design file" invariant above becomes "…for the same query", and the
//    re-fetch can never see a different template than the initial parse did.
//  * it is unit-testable without a server; tests/reference-server.test.ts pins it directly.
//
// An UNKNOWN key is refused with 400, never ignored. A silently-dropped prop name would
// leave the harness capturing the wrong state — and since the oracle is generated from that
// same capture, a zero-tolerance pixel gate could not see it.
// ---------------------------------------------------------------------------------------
const PROPS_ATTR = /(<script type="text\/x-dc" data-dc-script[^>]*data-props=")([^"]*)(")/;
const unescapeAttr = (s) => s.replace(/&quot;/g, '"').replace(/&amp;/g, '&');
// `&` FIRST, then `"`: the other order would re-escape the ampersands the quote escaping
// just introduced and ship `&amp;quot;`, which decodes back to the literal text `&quot;`.
const escapeAttr = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

/**
 * @param {string} html the document as served
 * @param {string | undefined} query the raw query string, without the `?`
 * @returns {{ html: string } | { status: 400, reason: string }}
 */
export function injectProps(html, query) {
  const raw = new URLSearchParams(query || '').get('props');
  if (raw === null) return { html };
  let requested;
  try {
    requested = JSON.parse(raw);
  } catch {
    return { status: 400, reason: `?props= is not JSON: ${raw}` };
  }
  if (!requested || typeof requested !== 'object' || Array.isArray(requested)) {
    return { status: 400, reason: `?props= must be a JSON object, got ${raw}` };
  }
  const at = PROPS_ATTR.exec(html);
  if (!at) return { status: 400, reason: 'this document declares no data-props, so there is nothing to inject' };
  const declared = JSON.parse(unescapeAttr(at[2]));
  for (const key of Object.keys(requested)) {
    // `$preview` and friends are the design tool's own metadata, not props (support.js's
    // parseDataProps strips every `$`-prefixed key before it builds the defaults).
    if (key.startsWith('$') || !Object.prototype.hasOwnProperty.call(declared, key)) {
      return { status: 400, reason: `unknown prototype prop "${key}" — the design declares ${Object.keys(declared).filter((k) => !k.startsWith('$')).join(', ')}` };
    }
    declared[key].default = requested[key];
  }
  return { html: html.slice(0, at.index) + at[1] + escapeAttr(JSON.stringify(declared)) + at[3] + html.slice(at.index + at[0].length) };
}

export const server = createServer(async (req, res) => {
  // Reject a literal ".." path segment outright, before the WHATWG URL parser below gets a
  // chance to normalize it away: normalizing first would make a bare-prefix traversal attempt
  // like "/coming-soon/../Practice Match V2.dc.html" collapse straight to that file's own real,
  // legitimately-servable top-level path (200, not a leak — but not the loud rejection a
  // traversal probe should get either). Checked on the raw request path, so percent-encoded
  // attempts (e.g. "%2e%2e", not literally ".." until decoded) still reach the resolve()+
  // startsWith guard below, which independently blocks them once decoded.
  const rawPath = req.url.split('?')[0];
  if (rawPath.split('/').some((seg) => seg === '..')) { res.writeHead(403); return res.end(); }
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  // A bare "/coming-soon" (no trailing slash) is one path segment: the browser resolves this
  // page's relative asset URLs (./support.js, _ds/…, assets/…) against "/", not "/coming-soon/"
  // — i.e. against the OTHER root. Today the two design exports happen to ship byte-identical
  // copies of those shared paths, so it works by coincidence; redirect instead of relying on that.
  if (pathname === '/coming-soon') { res.writeHead(301, { Location: '/coming-soon/' }); return res.end(); }
  const { root, file, isIndex } = resolve(pathname);
  if (!file.startsWith(root.dir)) { res.writeHead(403); return res.end(); }
  try {
    let body = await readFile(file);
    if (isIndex) {
      const injected = injectProps(body.toString('utf8'), req.url.slice(rawPath.length + 1));
      if (injected.status) { res.writeHead(injected.status, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end(injected.reason); }
      body = Buffer.from(injected.html, 'utf8');
    }
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end();
  }
});

// Listen only when this file IS the entry point. `tests/reference-server.test.ts` imports it
// for `injectProps`, and an unconditional `listen()` would bind port 5174 for the whole
// vitest run — quietly adopted as "the reference server" by the next Playwright run's
// `reuseExistingServer` (the same pattern baseline-manifest.mjs uses for `writeManifest`).
if (process.argv[1] && fileURLToPath(import.meta.url) === resolvePath(process.argv[1])) {
  server.listen(PORT, () => {
    for (const r of ROOTS) console.log(`[reference-server] ${r.dir} on http://localhost:${PORT}${r.prefix || '/'}`);
  });
}
