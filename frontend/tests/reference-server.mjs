// Serves the approved design bundle so Playwright can screenshot the reference.
// The bundle's runtime (support.js) re-fetches location.href to parse <x-dc>, so
// "/" must return the same bytes as the design file itself.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const ROOT = normalize(join(HERE, '../../docs/design-reference/design_handoff_practice_match_v2'));
const PORT = Number(process.argv[2] || 5174);
const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.jsx': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg',
  '.webp': 'image/webp', '.woff': 'font/woff', '.ttf': 'font/ttf', '.json': 'application/json', '.md': 'text/plain'
};

createServer(async (req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  const rel = pathname === '/' ? '/Practice Match V2.dc.html' : pathname;
  const file = normalize(join(ROOT, rel));
  if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': MIME[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404); res.end();
  }
}).listen(PORT, () => console.log(`[reference-server] ${ROOT} on http://localhost:${PORT}`));
