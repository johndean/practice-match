# How the competition layer can be presented — options for the VIN Foundation (2026-09-05)

**Question asked:** How can Google present competitor data in Practice Match, would that mean changing the map, is it possible — and what are the factual alternatives?

**Short answer.** Two different things are called "competition":

1. **Density** — the layer the approved design draws today: one number per community ("N veterinary establishments") bucketed Low / Moderate / High. The spec sources that number from the Census Bureau (ZIP Code Business Patterns, NAICS 541940). It is official, public-domain, storable, annual.
2. **Literal competitors** — named practices as pins with address, status, rating. The design does not draw this today; spec §12 defers it.

Google can present **both** — but only on a **Google map**, and only **live** (nothing stored). Beside the approved Leaflet map, Google can lawfully present exactly one thing: a Google-rendered list (Places UI Kit). Everything else Google offers is barred next to Leaflet by the "no use with or near a non-Google map" clause. Switching the map engine is technically straightforward and carries costs, constraints and a design change; it is a product decision, written up as a greenfield plan: [`docs/superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md`](../superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md).

## The rules that decide everything (verbatim, checked 2026-09-05)

| Rule | Text | Effect |
|---|---|---|
| Terms §3.2.3(a) No Scraping | "Customer will not … (iii) copy and save business names, addresses, or user reviews" | No Google practice list in our database |
| Terms §3.2.3(c) No Creating Content | "(iv) use latitude/longitude values from the Places API as an input for point-in-polygon analysis" | No catchment counts computed from Google pins — counts come from Census or from Google's own Aggregate API |
| Terms §3.2.3(e) No Use With Non-Google Maps | "Customer will not use the Google Maps Core Services **with or near a non-Google Map in a Customer Application**. For example, Customer will not (i) display or use Places content on a non-Google Map" | Google content cannot sit beside Leaflet; a switch is app-wide, not one tab |
| SST §14.1–14.3 Places API | Use without a Google map allowed; "must not use … in conjunction with a non-Google map"; lat/lng cacheable 30 days | Lists without a map are fine; Leaflet is not |
| SST §15.1 Places UI Kit | "Customer may use Places UI Kit in Customer Applications with or without any map, including a non-Google Map. This clause will prevail over the No Use with Non-Google Maps clause" | The one Google surface allowed beside Leaflet |
| SST §13 Places Aggregate API | POI Count cacheable 30 days "solely for the purpose of calculating the Customer Value"; Customer Values must not substitute for the count | Counts are for live display (on a Google map) or for derived buckets; §3.2.3(e) still applies to the service |
| SST §3 / Places policies | `place_id` "exempt from the caching restrictions … store … indefinitely" | The only thing the 2017 file could contribute — and it is not needed |
| Maps JS policies | Google logo, "Map data ©" and Terms link are rendered by the API and must never be removed, hidden, obscured or modified | The map corners of the approved design change |
| Foundation spec (pixel gate) | Screens must match the approved design at `maxDiffPixels: 0`; map **tiles** are already excluded from comparison | A Google map is not pixel-identical to the Esri/Leaflet design: controls, logo and attribution differ. The design must be updated in Claude Design and baselines regenerated, or the map viewport masked |

## Options

Costs use Google's 0–100 K tier prices after the free monthly allowance (Essentials 10,000 · Pro 5,000 · Enterprise 1,000 events). "V1 scale" assumes ~3,000 member sessions and ~2,000 competition-layer views a month; "10×" is ten times that.

| # | Presentation | What the member sees | Currency & provenance label | Legal basis | Design impact | Cost (V1 / 10×) | Verdict |
|---|---|---|---|---|---|---|---|
| A | **Leaflet + Census density** (as planned: D11) | Community dot sized by establishment count; Low/Moderate/High; "Source: U.S. Census Bureau, ZIP Code Business Patterns, 2022" | Annual, official; the §5 proxy caveat | Public domain | None | $0 / $0 | **Baseline — ship** |
| B | **Leaflet + Overture Places pins** (Census plan D16, Task C2) | Named practice pins with address, website, phone, operating status, confidence; "Overture Maps, release 2026-08" | Monthly; per-record `sources[]` and `confidence` | CDLA-Permissive-2.0 / Apache-2.0 — storable, renderable on any map, countable | Adds a points layer (design addition) | $0 / $0 | **Recommended for literal competitors** on the approved map |
| C | **Leaflet + Places UI Kit list panel** | A Google-rendered "Veterinary practices near this listing" list: name, rating, open now, photos, address; tapping opens Google's details card | Live; Google's data and attribution inside the component | SST §15.1 (explicit carve-out) | A side panel, not map content; Google styling with CSS tokens; **no pins on our map**, no counts from it | Places UI Kit SKU, 10,000 free/month; ~$0 / est. $40–140 | **Viable add-on** if live Google detail is wanted without changing the map |
| D | **Leaflet + "Open in Google Maps" link** | `https://www.google.com/maps/search/?api=1&query=veterinarian+near+<address>` opens Google Maps in a new tab | Live, Google's own product | Maps URLs need no key; consumer Maps terms; not a Core Service in our app | One link on the panel | $0 / $0 | **Add now** — zero risk, gives members Google's live view in one click |
| E | **Leaflet + Google Aggregate freshness bucket** (Census plan D17, Task C1) | Nothing new on screen except "live: High (diverges from Census)" | Monthly bucket derived from a Google count | SST §13 Customer Values — **but** §3.2.3(e) "with or near a non-Google Map" applies to the service itself; counsel must read it narrowly | None | Aggregate $10/1k after 5,000 free; ~$0 / $350 | Counsel-gated; superseded by F if the map switches |
| F | **Switch the app's map to Google Maps** (greenfield plan) | Styled Google basemap + Google satellite; live pins for `veterinary_care` (name, address, status, optional rating) in every band; a live Google count beside the Census count; Census bubbles unchanged | Live Google content, Google attribution; Census layers keep their labels | Lawful in full: Places on a Google map, Aggregate count on a Google map; **nothing stored**; no mixing with Leaflet anywhere | **Design change**: Google logo, attribution, controls, cartography; Claude Design reference updated; pixel baselines regenerated; the Esri/CARTO basemap licence question and the satellite licence item both disappear | Dynamic Maps $7/1k after 10,000; Nearby Search $32/1k (Pro) or $35/1k (with ratings) after 5,000; Aggregate $10/1k after 5,000 — ≈ $0 / ≈ $1,800 a month | **Possible.** A product decision for the VIN Foundation: live Google content and imagery in exchange for the approved Leaflet look and a per-view bill |
| G | Google Maps Embed API iframe (free) | A Google map iframe showing "veterinarians near X" | Live | Same no-mixing clause: it is a Google map inside the app | Only inside F | free | Not viable beside Leaflet |

What no option changes: the **displayed density count** stays Census-sourced (spec §5) unless the VIN Foundation amends the spec; Google pins can never be *counted into* a metric (§3.2.3(c)(iv)); Google content is never written to our database in any option.

## Is switching the map possible?

Yes. The Maps JavaScript API does everything the design's Leaflet components do (circles, HTML markers via `AdvancedMarkerElement`, GeoJSON overlays, fit-to-bounds) and adds satellite/hybrid imagery and cloud-based styling on a Map ID. What it demands: one engine across the whole application (§3.2.3(e)); the Google logo and attribution untouched; nothing from Google persisted; browser key restricted by referrer and API; quotas and a billing budget so a traffic spike cannot run up the bill; the visual gate re-baselined against an updated design (the map viewport is masked until then). The greenfield plan sequences this **before** Foundation Task 1 (Leaflet vendoring) or as an amendment to it, and lists the exact deltas to the Foundation and Census plans.

## Recommendation

Ship **A** as planned. Add **D** immediately (free, factual, no exposure). If the VIN Foundation wants literal competitors on the approved Leaflet design, approve **B** (Overture; Foursquare OS Places as the fallback source). If it wants Google's live names and ratings *inside* the product, choose between **C** (list beside the existing map, modest cost, no design change) and **F** (Google map everywhere; live pins and imagery; design change and usage-based cost). **E** only matters if the map stays Leaflet and counsel accepts the narrow reading.

## Decisions requested

- [ ] **Map engine (G0):** keep Leaflet (approved design) or switch to Google Maps (greenfield plan).
- [ ] **Literal competitors on Leaflet:** approve Overture Maps Places as the source (Census plan D16).
- [ ] **Google beside Leaflet:** approve the "Open in Google Maps" link (D) and, optionally, the Places UI Kit list (C).

## Sources

Google Maps Platform Terms · Service Specific Terms (§3, §13, §14, §15) · Places API policies · Maps JavaScript API policies · Places UI Kit overview · Places API (New) pricing and data-field tiers · Nearby Search (New) and Text Search (New) references · Places Aggregate API overview, `computeInsights` reference and policies · Google Maps URLs · Overture Maps places schema and guides · Foursquare OS Places · OpenStreetMap taginfo. URLs are listed in the Census plan appendix.
