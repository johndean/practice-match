import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 20, duration: '2m', thresholds: { http_req_duration: ['p(95)<400'], http_req_failed: ['rate==0'] } };
const BASE = __ENV.BASE_URL;
// Until Sub-project 2 ships its read endpoints (/api/layers, /api/map-config, /api/markets) only the
// health endpoint exists; the four-endpoint list and the member token return with SP2 (John, 2026-09-06).
export default function () {
  for (const p of ['/api/healthz']) {
    const r = http.get(`${BASE}${p}`);
    check(r, { 'status < 500': (x) => x.status < 500 });
  }
}
