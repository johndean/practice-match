# Rev 3 design request — listing disclosure controls (Seller and VIN Admin)

**Ruling (John, 2026-09-08):** whether a listing's name is visible on the Browse cards "should be surfaced as an option for the Seller / VIN Admin to set what is visible/hidden or shown". Disclosure is per listing, set by the seller, overridable by the VIN Foundation admin, and enforced by the server — a hidden value never reaches a buyer's browser.

## What exists in the approved design (V3) today

- The listing wizard already carries one disclosure toggle: **"Show revenue as a range instead of an exact figure"** (help text: "Buyers see "$2M – $2.5M". The exact figure is released only when you accept a request."). That toggle is the pattern to reuse.
- The sign-in card's second point (amendment A10.2, John's wording) states the principle buyers are promised: *"Sellers control what buyers can see — The property is accurately mapped, but financial information, and floor plans are only shared with the seller's approval."*
- The data model carries `location_disclosed` (general location by default) and, from Seed Listings amendment A-L5, `name_disclosed` (anonymised card by default: area + type, the design's `practiceName` fallback).

## What Rev 3 must design

1. **Seller — wizard disclosure step.** Beside the revenue-range toggle, one switch per disclosable fact, same control, same help-text pattern:
   - Show the practice name on cards and the detail page (default off).
   - Show the exact location (default off — general location by default).
   - Show revenue as a range (existing).
   - Share floor plans and documents on request only (default on) — the wording the sign-in card promises.
   Each switch needs its off-state copy ("Buyers see: Cedar Park · Small animal") so the seller sees what a buyer sees.
2. **Seller dashboard.** The listing card in "My listings" shows the current disclosure state at a glance (a compact row of the switches' states) and links to the wizard step.
3. **VIN Admin — Listings tab.** The same switches per listing with an **admin override** state (set by the Foundation, shown to the seller as "set by the VIN Foundation"), plus who changed what and when (the audit row already exists server-side).
4. **States the visual oracle needs:** wizard step with all switches off / all on; a Browse card and detail with the name hidden (anonymised) and shown; the Admin Listings row with a Foundation override.

## Rules this inherits

- Compose from the approved design's existing controls (the toggle, the wizard step layout, the admin table); nothing invented.
- No copy beyond what is in this document without a ruling; the sign-in card's wording is the promise every label must be consistent with.
- Server-enforced: the API decides what a buyer's response contains; the UI only displays.
