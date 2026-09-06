# Seed Listings — Design

**Status:** requested by John Dean 2026-09-06 ("add the seeding of NEW data and the removal of existing listings … with new information using these hospital names and photos"). Sub-project "Seed listings" (the first step of Wave 2b). Decisions below apply as defaults unless John changes them.

## 1. What changes for the member

qa.foundation.vin stops showing the design's twenty-one anonymised fixture practices (nine in the Austin market, the rest across the design's other markets) and shows **eighteen seeded demo hospitals** across Texas, California, New York, Colorado, Florida and Georgia, each at a real, mapable street address with a fake `555` phone number, opening hours and photographs John supplied. Browse Practices (V3), the map pins, the results rail and the detail screen read them from the API. Production is unaffected (Coming Soon).

## 2. Source data

John's table of 2026-09-06 is the seed, verbatim, committed as `seeds/hospitals.json`:

| Seed hospital | City / State | Address | Phone (fake) | Hours |
|---|---|---|---|---|
| 6666 Dallas Veterinary Specialist Hospital | Dallas, TX | 17727 Dallas Pkwy, Suite 150, Dallas, TX 75287 | (214) 555-0101 | Mon–Fri 8 AM–5 PM |
| 5555 New York Veterinary Specialist Hospital | New York, NY | 510 E 62nd St, New York, NY 10065 | (212) 555-0102 | 24/7 |
| 4444 Denver Veterinary Specialist Hospital | Denver, CO | 9770 E Alameda Ave, Denver, CO 80247 | (303) 555-0103 | 24/7 |
| 3333 Santa Barbara Veterinary Specialist Hospital | Santa Barbara, CA | 414 E Carrillo St, Santa Barbara, CA 93101 | (805) 555-0104 | 24/7 |
| 2222 Pet Hospital | Houston, TX | 8042 Katy Freeway, Houston, TX 77024 | (713) 555-0105 | 24/7 emergency |
| 1111 Pet Hospital | Los Angeles, CA | 6565 Santa Monica Blvd, Los Angeles, CA 90038 | (323) 555-0106 | 24/7 |
| 789 Lake Tahoe Pet Hospital | South Lake Tahoe, CA | 921 Emerald Bay Rd, South Lake Tahoe, CA 96150 | (530) 555-0107 | Mon–Sat 8 AM–6 PM |
| 456 Pet ER Hospital | Los Angeles, CA | 2500 N San Fernando Rd, Los Angeles, CA 90065 | (323) 555-0108 | 24/7 |
| 123 Route 66 Animal Hospital | Los Angeles, CA | 4641 Colorado Blvd, Los Angeles, CA 90039 | (818) 555-0109 | 24/7 |
| YZ Rural Animal Hospital | Sacramento, CA | 8299 E Stockton Blvd, Sacramento, CA 95828 | (916) 555-0110 | 24/7 |
| VWX Veterinary Hospital | Orlando, FL | 11011 Lake Underhill Rd, Orlando, FL 32825 | (407) 555-0111 | 24/7 |
| STU Veterinary Specialist Center | Orlando, FL | 2080 Principal Row, Orlando, FL 32837 | (407) 555-0112 | Mon–Thu 8 AM–6 PM |
| PQR Veterinary Hospital | Sacramento, CA | 9801 Old Winery Place, Sacramento, CA 95827 | (916) 555-0113 | 6 AM–12 AM |
| MNO Pet Hospital | Sacramento, CA | 1917 P Street, Sacramento, CA 95811 | (916) 555-0114 | Mon–Fri 8 AM–6 PM; Sat 9 AM–5 PM |
| JKL Animal Critical Care & ER Hospital | Atlanta, GA | 1700 Century Cir NE, Atlanta, GA 30345 | (404) 555-0115 | 24/7 |
| GHI Veterinary Hospital | Austin, TX | 7501 N Capital of Texas Hwy, Building A, Austin, TX 78731 | (512) 555-0116 | 24/7 emergency |
| DEF Veterinary Hospital | Austin, TX | 4434 Frontier Trail, Austin, TX 78745 | (512) 555-0117 | 24/7 |
| ABC Animal Hospital | Houston, TX | 6730 Airline Dr, Houston, TX 77076 | (713) 555-0118 | Mon/Tue/Thu/Fri 7:30 AM–6 PM; Sat 7:30 AM–5 PM |

Photographs: `/Users/johndean/Downloads/VIN FOUNDATION/Hospital images/ALL HOSPITAL SEED DATA/<slug>_individual_images/` (18 curated folders, 195 files, 71 MB; the per-hospital folders beside it hold the originals and zips and are not used).

## 3. Decisions

- **D1 — Placement and order.** A plan of its own (`docs/superpowers/plans/2026-09-06-practice-match-seed-listings.md`), executed after Browse V3 merges (it rewrites the Browse rail, pins and detail) and after Wave 2a Task I4 merges (it needs `require`), and before the rest of Wave 2b. It defines the `listing` table that Wave 2b and the Census plan's Phase B build on: `id uuid`, `slug`, `name`, `street`, `city`, `state`, `zip`, `phone`, `hours`, `status`, `location_disclosed`, `geom geography(Point,4326)`, the design's card and detail fields (`area`, `type`, `price`, `rev`, `docs`, `rooms`, `sqft`, `bldg`, `est`, `listed_at`, `note`, `staff`, `services`, `facility`, `ownership`, `market`), `photos jsonb`, `source` (`seed` | `seller`), timestamps. Migrations start at `015` (identity uses `010`–`014`; the Census plan's Phase B stays at `060`+).
- **D2 — Geocoding.** Addresses are geocoded once, offline, by the implementer through the **U.S. Census Bureau Geocoder** (public domain, no key, no Google), and the coordinates are committed in `seeds/hospitals.json` with the geocoder's match tier as provenance. A test asserts every point lies inside its state's bounding box and within 25 km of its city's centroid. No Google Places or Google Geocoding content is stored (standing rule).
- **D3 — Photos.** `scripts/prepare_photos.py` reads the curated folders, keeps up to **four** photographs per hospital in folder order, converts each to WebP at ≤ 1600 px on the long edge and ≤ 250 KB, strips metadata, and writes `seeds/hospitals/photos/<slug>/1.webp … 4.webp` plus an inventory (`seeds/hospitals/photos/index.json` with SHA-256s). The outputs are committed (≈ 15 MB; the repository is public — John supplied these photographs for the demo hospitals). They are served by the API, not bundled into the frontend, through `GET /api/listings/{id}/photos/{n}` (`listing.read`), so an unpublished or anonymised listing's photographs are never public.
- **D4 — Fields John's table does not carry.** `type` is derived from the name ("Specialist" → Specialty; "ER" / "Critical Care" / "24/7 emergency" hours → Emergency; otherwise Small animal); `price`, `rev`, `docs`, `rooms`, `sqft`, `bldg`, `est`, `staff`, `services`, `facility`, `ownership` are plausible demo values set per hospital in `seeds/hospitals.json` (visible, editable by John at any time, marked `"demo": true`); `note` reads "Demo listing seeded by the VIN Foundation." Community figures (`pop`, `growth`, `income`, `hh`) are left null until the Census plan supplies them; the UI shows its existing empty state for them.
- **D5 — Names follow the design.** The design anonymises listings on cards (area and type, no name). The hospital name is stored and shown wherever the V3 design has a title slot (the detail screen and the Admin Listings tab in Wave 2b); cards keep the design's anonymised layout. **→ John:** say "show names on cards" to change the design instead.
- **D6 — The pixel gate stays honest.** The visual, DOM-oracle and smoke gates run against a stubbed `/api/listings` that returns the design's own fixture practices, so every pixel still matches the V3 design file; QA runs against the seeded eighteen. The frontend loads listings from the API at start-up and replaces the generated `P`/market arrays **keeping their field names** (the CLAUDE.md launch-removal note); the fixture arrays remain in the generated file until Wave 2a's `convert-dc.mjs --launch` strips them.
- **D7 — Removal of the existing listings.** `scripts/seed_listings.py` is idempotent (upsert by `slug`) and `--reset` deletes every `source='seed'` row first; on QA the eighteen replace the design fixtures entirely. It runs inside the api container (`railway ssh`, John's ed25519 key) or as the `seed` role of `scripts/start.sh`; never on production without John's go.
- **D8 — Access.** `GET /api/listings` (published only, paginated, `?market=`) and `GET /api/listings/{id}` are guarded by `listing.read` (members and above; anonymous receives the generic 401 and the frontend shows the sign-in gate, as the identity design intends). Map pins use the listing's geocoded point because seeds set `location_disclosed=true`; sellers' listings in Wave 2b default to false (Census plan D8).
- **D9 — Quality.** Test-first everything: schema contract test, geocode bounds test, photo pipeline test (dimensions, size, count, inventory hashes), seed idempotency test on a scratch database, endpoint tests (401 anonymous, 200 member, unpublished hidden, pagination), frontend tests (listings replace `P` keeping field names; the design-fixture stub for the gates), perf budgets for `/api/listings` in `tests/perf/test_api_latency.py`, 100 % lines and branches backend and frontend, zero-regression on the thirteen unchanged screens (the Browse V3 hash manifest is the authority).

## 4. Out of scope

The seller wizard, publishing workflow, requests/messaging, Admin Listings tab (Wave 2b); market data per listing (Census plan); production seeding.
