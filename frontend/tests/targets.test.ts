import { describe, expect, it } from 'vitest';
import { resolveTargets } from './targets';

describe('resolveTargets', () => {
  const ports = { app: 5173, ref: 4174, cs: 4175 };
  it('runs against localhost with all three servers when PW_APP_URL is unset', () => {
    const t = resolveTargets({}, ports);
    expect(t.baseURL).toBe('http://localhost:5173');
    expect(t.csBaseURL).toBe('http://localhost:4175');
    expect(t.webServer.map((w) => w.url)).toEqual(['http://localhost:5173', 'http://localhost:4174/', 'http://localhost:4175']);
    expect(t.webServer[2].cwd).toBe('../../coming-soon');
  });
  it('runs the app against the live deployment but keeps the reference and coming-soon servers local when PW_APP_URL is set', () => {
    const t = resolveTargets({ PW_APP_URL: 'https://qa.foundation.vin' }, ports);
    expect(t.baseURL).toBe('https://qa.foundation.vin');
    expect(t.csBaseURL).toBe('http://localhost:4175');
    expect(t.webServer.map((w) => w.url)).toEqual(['http://localhost:4174/', 'http://localhost:4175']);
  });
});
