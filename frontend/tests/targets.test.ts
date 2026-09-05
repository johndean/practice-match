import { describe, expect, it } from 'vitest';
import { resolveTargets } from './targets';

describe('resolveTargets', () => {
  it('runs against localhost with both servers when PW_APP_URL is unset', () => {
    const t = resolveTargets({}, { app: 5173, ref: 4174 });
    expect(t.baseURL).toBe('http://localhost:5173');
    expect(t.webServer.map((w) => w.url)).toEqual(['http://localhost:5173', 'http://localhost:4174/']);
  });
  it('runs against the live deployment and starts only the reference server when PW_APP_URL is set', () => {
    const t = resolveTargets({ PW_APP_URL: 'https://qa.foundation.vin' }, { app: 5173, ref: 4174 });
    expect(t.baseURL).toBe('https://qa.foundation.vin');
    expect(t.webServer).toHaveLength(1);
    expect(t.webServer[0].url).toBe('http://localhost:4174/');
  });
});
