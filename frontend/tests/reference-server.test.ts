import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { type ChildProcess, spawn } from 'node:child_process';
import { get } from 'node:http';
import { createServer } from 'node:net';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
    expect(await res.text()).toContain('Practice Match — internal working title');
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
});
