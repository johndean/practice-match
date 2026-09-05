import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 20, duration: '2m', thresholds: { http_req_duration: ['p(95)<400'], http_req_failed: ['rate==0'] } };
const BASE = __ENV.BASE_URL; const H = { headers: { Authorization: `Bearer ${__ENV.MEMBER_TOKEN}` } };
export default function () {
  for (const p of ['/api/healthz', '/api/layers', '/api/map-config', '/api/markets']) {
    const r = http.get(`${BASE}${p}`, H);
    check(r, { 'status < 500': (x) => x.status < 500 });
  }
}
