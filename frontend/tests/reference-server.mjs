// Serves the approved design bundles so Playwright can screenshot the reference(s).
// The bundle's runtime (support.js) re-fetches location.href to parse <x-dc>, so
// each root's index path must return the same bytes as its design file itself.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const PORT = Number(process.argv[2] || 5174);
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.jsx': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg',
  '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.json': 'application/json', '.md': 'text/plain'
};

// docs/design-reference/coming-soon serves the Coming Soon design (Task 11e); the
// Practice Match V2 handoff keeps serving from "/" as before. The first root whose
// prefix the request path starts with wins, so "/coming-soon" is listed first.
const ROOTS = [
  { prefix: '/coming-soon', dir: normalize(join(HERE, '../../docs/design-reference/coming-soon')), index: '/Coming Soon.dc.html' },
  { prefix: '', dir: normalize(join(HERE, '../../docs/design-reference/design_handoff_practice_match_v2')), index: '/Practice Match V2.dc.html' }
];

function resolve(pathname) {
  const root = ROOTS.find((r) => pathname === r.prefix || pathname.startsWith(`${r.prefix}/`));
  const stripped = pathname.slice(root.prefix.length);
  const rel = stripped === '' || stripped === '/' ? root.index : stripped;
  return { root, file: normalize(join(root.dir, rel)) };
}

createServer(async (req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const { root, file } = resolve(pathname);
  if (!file.startsWith(root.dir)) { res.writeHead(403); return res.end(); }
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end();
  }
}).listen(PORT, () => {
  for (const r of ROOTS) console.log(`[reference-server] ${r.dir} on http://localhost:${PORT}${r.prefix || '/'}`);
});
