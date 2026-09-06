// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.
// Do not restyle or restructure: every value here is design-approved.
import { DCLogic } from './dc-logic.js';

const P = [
  { id:"p1", area:"Cedar Park", type:"Small animal", price:1450000, rev:2100000, docs:3, rooms:5, sqft:4200, bldg:"Included", lat:30.5052, lng:-97.8203, est:1998, listed:"3 days ago", status:"published",
    pop:"81,900", growth:"+14.2% since 2015", income:"$118,400", hh:"27,600 households", note:"Owner retiring after 27 years; open to a six-month transition.", staff:"3 DVMs, 4 licensed technicians, 6 support staff", hours:"Mon–Fri 7:30–6, Sat 8–1", services:"Wellness, dentistry, soft-tissue surgery, in-house lab, digital radiography", facility:"Freestanding building on a 0.6-acre corner lot, remodeled 2019.", ownership:"Sole proprietor (S-corp)" },
  { id:"p2", area:"Round Rock", type:"Small animal", price:980000, rev:1450000, docs:2, rooms:4, sqft:3100, bldg:"Leased", lat:30.5083, lng:-97.6789, est:2006, listed:"1 week ago", status:"published",
    pop:"126,400", growth:"+21.8% since 2015", income:"$104,700", hh:"44,100 households", note:"Relocating out of state. Lease assignable through 2031.", staff:"2 DVMs, 3 technicians, 4 support staff", hours:"Mon–Sat 8–6", services:"Wellness, surgery, dentistry, boarding", facility:"End unit in a retail plaza with dedicated parking.", ownership:"Sole proprietor (LLC)" },
  { id:"p3", area:"South Austin", type:"Mixed", price:2350000, rev:3200000, docs:5, rooms:7, sqft:6800, bldg:"Included", lat:30.2270, lng:-97.8060, est:1989, listed:"2 weeks ago", status:"published",
    pop:"142,300", growth:"+11.6% since 2015", income:"$92,300", hh:"58,900 households", note:"Two-owner partnership; one partner retiring, one willing to stay two years.", staff:"5 DVMs, 7 technicians, 11 support staff", hours:"Mon–Fri 7–7, Sat 8–4", services:"Small animal wellness and surgery, equine ambulatory, in-house lab, ultrasound", facility:"Owned building with a separate large-animal barn and stocks.", ownership:"Two-doctor partnership" },
  { id:"p4", area:"Georgetown", type:"Small animal", price:610000, rev:890000, docs:1, rooms:3, sqft:2400, bldg:"Separate", lat:30.6333, lng:-97.6772, est:1994, listed:"3 weeks ago", status:"published",
    pop:"75,400", growth:"+38.5% since 2015", income:"$96,100", hh:"29,700 households", note:"Solo owner retiring; building available separately at appraised value.", staff:"1 DVM, 2 technicians, 2 support staff", hours:"Tue–Sat 8–5", services:"Wellness, dentistry, minor surgery, house calls", facility:"Converted residence, 1,900 sq ft clinical plus storage.", ownership:"Sole proprietor" },
  { id:"p5", area:"Kyle", type:"Mixed", price:1180000, rev:1720000, docs:2, rooms:4, sqft:3600, bldg:"Included", lat:29.9893, lng:-97.8770, est:2011, listed:"5 days ago", status:"published",
    pop:"57,200", growth:"+62.1% since 2015", income:"$88,900", hh:"18,300 households", note:"Growth corridor; owner moving to part-time relief work.", staff:"2 DVMs, 3 technicians, 3 support staff", hours:"Mon–Fri 8–6", services:"Small animal wellness and surgery, small ruminant field service", facility:"Metal building on 2 acres, room to expand.", ownership:"Sole proprietor (LLC)" },
  { id:"p6", area:"East Austin", type:"Emergency", price:3100000, rev:4600000, docs:7, rooms:9, sqft:8200, bldg:"Leased", lat:30.2620, lng:-97.7100, est:2015, listed:"4 days ago", status:"published",
    pop:"98,600", growth:"+9.4% since 2015", income:"$79,500", hh:"41,200 households", note:"Founding owners stepping back from overnight coverage.", staff:"7 DVMs, 12 technicians, 9 support staff", hours:"Nights, weekends, holidays", services:"Emergency and critical care, CT, 24-hour hospitalization", facility:"Purpose-built ER shell, lease through 2034.", ownership:"Three-doctor LLC" },
  { id:"p7", area:"Lakeway", type:"Small animal", price:1750000, rev:2400000, docs:3, rooms:6, sqft:5100, bldg:"Included", lat:30.3630, lng:-97.9780, est:2002, listed:"9 days ago", status:"published",
    pop:"19,800", growth:"+24.7% since 2015", income:"$147,200", hh:"7,900 households", note:"Owner retiring; strong client base, low staff turnover.", staff:"3 DVMs, 5 technicians, 5 support staff", hours:"Mon–Fri 8–6, Sat 9–1", services:"Wellness, dentistry, orthopedics, laser therapy, grooming", facility:"Owned building with lake-area frontage, remodeled 2021.", ownership:"Sole proprietor (S-corp)" },
  { id:"p8", area:"Dripping Springs", type:"Large animal", price:720000, rev:1050000, docs:2, rooms:2, sqft:2800, bldg:"Included", lat:30.1902, lng:-98.0867, est:1985, listed:"1 month ago", status:"published",
    pop:"5,600", growth:"+41.3% since 2015", income:"$121,800", hh:"2,100 households", note:"Equine and small ruminant practice; owner retiring in 2027.", staff:"2 DVMs, 2 technicians, 1 support staff", hours:"Mon–Fri 7–5, on call", services:"Equine ambulatory, reproduction, dentistry, small ruminant herd health", facility:"Barn, stocks, and office on 8 acres.", ownership:"Sole proprietor" },
  { id:"p9", area:"Pflugerville", type:"Specialty", price:2650000, rev:3800000, docs:6, rooms:8, sqft:7400, bldg:"Separate", lat:30.4394, lng:-97.6200, est:2018, listed:"6 days ago", status:"published",
    pop:"68,700", growth:"+29.9% since 2015", income:"$110,300", hh:"22,400 households", note:"Referral surgery and internal medicine; owner reducing clinical load.", staff:"6 DVMs, 9 technicians, 7 support staff", hours:"Mon–Fri 8–6", services:"Surgery, internal medicine, oncology consults, CT and endoscopy", facility:"Owned condo suite in a medical park; unit available separately.", ownership:"Four-doctor LLC" }
];

P.forEach((p) => { p.market = "Austin, TX"; });

const MARKETS = {
  "Austin, TX": { center: [30.31, -97.75], zoom: 10 },
  "Sacramento, CA": { center: [38.58, -121.42], zoom: 10 },
  "Orlando, FL": { center: [28.52, -81.36], zoom: 10 },
  "Atlanta, GA": { center: [33.79, -84.39], zoom: 10 }
};

[
  { id:"c1", market:"Sacramento, CA", area:"Roseville", type:"Small animal", price:1620000, rev:2250000, docs:3, rooms:6, sqft:4600, bldg:"Included", lat:38.7521, lng:-121.2880, est:1996, listed:"4 days ago",
    pop:"156,600", growth:"+18.4% since 2015", income:"$113,700", hh:"58,200 households", note:"Owner retiring after 29 years; associate may stay on.", staff:"3 DVMs, 5 technicians, 6 support staff", hours:"Mon–Fri 8–6, Sat 9–2", services:"Wellness, dentistry, soft-tissue surgery, ultrasound, in-house lab", facility:"Freestanding building near a retail corridor, remodeled 2020.", ownership:"Sole proprietor (S-corp)" },
  { id:"c2", market:"Sacramento, CA", area:"Elk Grove", type:"Small animal", price:890000, rev:1310000, docs:2, rooms:4, sqft:3000, bldg:"Leased", lat:38.4088, lng:-121.3716, est:2008, listed:"1 week ago",
    pop:"178,300", growth:"+16.9% since 2015", income:"$106,400", hh:"56,800 households", note:"Owner relocating for family; lease runs through 2030.", staff:"2 DVMs, 3 technicians, 4 support staff", hours:"Mon–Sat 8–6", services:"Wellness, surgery, dentistry, boarding", facility:"Suite in a neighborhood shopping center.", ownership:"Sole proprietor (LLC)" },
  { id:"c3", market:"Sacramento, CA", area:"Davis", type:"Mixed", price:2100000, rev:2950000, docs:4, rooms:6, sqft:6100, bldg:"Included", lat:38.5449, lng:-121.7405, est:1991, listed:"2 weeks ago",
    pop:"67,400", growth:"+3.8% since 2015", income:"$88,200", hh:"25,700 households", note:"Two-owner practice; both retiring within three years.", staff:"4 DVMs, 6 technicians, 8 support staff", hours:"Mon–Fri 7:30–6", services:"Small animal wellness and surgery, equine ambulatory, herd health", facility:"Owned building with a separate large-animal wing on 3 acres.", ownership:"Two-doctor partnership" },
  { id:"c4", market:"Sacramento, CA", area:"Folsom", type:"Specialty", price:2900000, rev:4100000, docs:6, rooms:8, sqft:7600, bldg:"Separate", lat:38.6780, lng:-121.1760, est:2014, listed:"6 days ago",
    pop:"84,900", growth:"+22.1% since 2015", income:"$135,800", hh:"31,400 households", note:"Referral surgery and internal medicine; founder reducing clinical load.", staff:"6 DVMs, 10 technicians, 7 support staff", hours:"Mon–Fri 8–6", services:"Surgery, internal medicine, CT, endoscopy, oncology consults", facility:"Owned suite in a medical park; unit available separately.", ownership:"Three-doctor LLC" },
  { id:"o1", market:"Orlando, FL", area:"Winter Park", type:"Small animal", price:1380000, rev:1980000, docs:3, rooms:5, sqft:3900, bldg:"Included", lat:28.6000, lng:-81.3392, est:1993, listed:"5 days ago",
    pop:"30,800", growth:"+7.6% since 2015", income:"$104,900", hh:"13,200 households", note:"Owner retiring; long-tenured staff willing to stay.", staff:"3 DVMs, 4 technicians, 5 support staff", hours:"Mon–Fri 7:30–6, Sat 8–12", services:"Wellness, dentistry, surgery, digital radiography", facility:"Renovated freestanding building close to the historic district.", ownership:"Sole proprietor (S-corp)" },
  { id:"o2", market:"Orlando, FL", area:"Lake Mary", type:"Small animal", price:760000, rev:1120000, docs:2, rooms:3, sqft:2700, bldg:"Leased", lat:28.7589, lng:-81.3178, est:2004, listed:"9 days ago",
    pop:"18,100", growth:"+12.3% since 2015", income:"$98,600", hh:"7,400 households", note:"Solo owner moving to relief work; lease assignable.", staff:"2 DVMs, 2 technicians, 3 support staff", hours:"Mon–Fri 8–5:30", services:"Wellness, dentistry, minor surgery", facility:"End suite in an office plaza with covered parking.", ownership:"Sole proprietor" },
  { id:"o3", market:"Orlando, FL", area:"Kissimmee", type:"Emergency", price:2750000, rev:4200000, docs:6, rooms:9, sqft:7800, bldg:"Leased", lat:28.2920, lng:-81.4076, est:2016, listed:"3 days ago",
    pop:"82,700", growth:"+24.5% since 2015", income:"$61,300", hh:"29,100 households", note:"Founding owners stepping back from overnight coverage.", staff:"6 DVMs, 11 technicians, 8 support staff", hours:"Nights, weekends, holidays", services:"Emergency and critical care, 24-hour hospitalization, ultrasound", facility:"Purpose-built ER, lease through 2033.", ownership:"Three-doctor LLC" },
  { id:"o4", market:"Orlando, FL", area:"Oviedo", type:"Mixed", price:1050000, rev:1560000, docs:2, rooms:4, sqft:3500, bldg:"Included", lat:28.6700, lng:-81.2081, est:2009, listed:"2 weeks ago",
    pop:"41,600", growth:"+19.2% since 2015", income:"$107,200", hh:"14,300 households", note:"Owner retiring in 2027; equine ambulatory route included.", staff:"2 DVMs, 3 technicians, 3 support staff", hours:"Mon–Fri 8–6, on call", services:"Small animal wellness and surgery, equine ambulatory", facility:"Metal building on 4 acres with room to expand.", ownership:"Sole proprietor (LLC)" },
  { id:"g1", market:"Atlanta, GA", area:"Marietta", type:"Small animal", price:1240000, rev:1840000, docs:3, rooms:5, sqft:4000, bldg:"Included", lat:33.9526, lng:-84.5499, est:1997, listed:"6 days ago",
    pop:"61,000", growth:"+8.9% since 2015", income:"$79,400", hh:"25,900 households", note:"Owner retiring after 25 years; six-month transition offered.", staff:"3 DVMs, 4 technicians, 5 support staff", hours:"Mon–Fri 7:30–6, Sat 8–1", services:"Wellness, dentistry, soft-tissue surgery, in-house lab", facility:"Freestanding brick building on a half-acre lot.", ownership:"Sole proprietor (S-corp)" },
  { id:"g2", market:"Atlanta, GA", area:"Decatur", type:"Small animal", price:940000, rev:1420000, docs:2, rooms:4, sqft:3200, bldg:"Separate", lat:33.7748, lng:-84.2963, est:2002, listed:"1 week ago",
    pop:"25,800", growth:"+14.6% since 2015", income:"$122,500", hh:"11,100 households", note:"Owner retiring; building available separately at appraised value.", staff:"2 DVMs, 3 technicians, 4 support staff", hours:"Mon–Sat 8–6", services:"Wellness, dentistry, surgery, behavior consults", facility:"Converted bungalow in a walkable neighborhood.", ownership:"Sole proprietor (LLC)" },
  { id:"g3", market:"Atlanta, GA", area:"Alpharetta", type:"Specialty", price:3200000, rev:4700000, docs:7, rooms:9, sqft:8400, bldg:"Separate", lat:34.0754, lng:-84.2941, est:2017, listed:"4 days ago",
    pop:"67,200", growth:"+16.2% since 2015", income:"$142,300", hh:"25,600 households", note:"Referral hospital; two of four owners exiting.", staff:"7 DVMs, 12 technicians, 9 support staff", hours:"Mon–Fri 8–6, Sat 9–1", services:"Surgery, internal medicine, cardiology, CT, rehabilitation", facility:"Owned suite in a medical park; unit available separately.", ownership:"Four-doctor LLC" },
  { id:"g4", market:"Atlanta, GA", area:"Peachtree City", type:"Large animal", price:680000, rev:1010000, docs:2, rooms:2, sqft:2600, bldg:"Included", lat:33.3968, lng:-84.5963, est:1988, listed:"3 weeks ago",
    pop:"38,200", growth:"+6.4% since 2015", income:"$118,900", hh:"14,700 households", note:"Equine practice; owner retiring, route and clients transfer.", staff:"2 DVMs, 2 technicians, 1 support staff", hours:"Mon–Fri 7–5, on call", services:"Equine ambulatory, reproduction, dentistry, lameness", facility:"Barn, stocks and office on 11 acres.", ownership:"Sole proprietor" }
].forEach((p) => { p.status = "published"; P.push(p); });

// Veterinary establishment counts per community — Census County Business Patterns,
// NAICS 541940 (Veterinary Services), 2023 release. Keyed by listing id.
const VETS = {
  p1: 7, p2: 5, p3: 12, p4: 4, p5: 3, p6: 9, p7: 2, p8: 1, p9: 6,
  c1: 8, c2: 6, c3: 5, c4: 4, o1: 6, o2: 3, o3: 11, o4: 2, g1: 9, g2: 7, g3: 6, g4: 3
};

// Annual payroll per veterinary establishment, $K — Census CBP PAYANN ÷ ESTAB
// (NAICS 541940). Sample figures for the prototype, keyed by listing id.
const ECON_K = {
  p1: 685, p2: 548, p3: 742, p4: 402, p5: 466, p6: 1120, p7: 806, p8: 358, p9: 968,
  c1: 724, c2: 594, c3: 651, c4: 1015, o1: 662, o2: 498, o3: 1078, o4: 512, g1: 618, g2: 705, g3: 995, g4: 386
};

const BRAND_RAMP = ["#deecf7", "#9dc9e9", "#339dde", "#003a70"];
// PALETTES — one hue per layer, no duplicates. Selectable via the layerPalette prop
// so the Foundation can pick the set that reads best on the gray basemap.
const PALETTES = {
  distinct: {
    income:     ["#e6f2e8", "#c2e0cd", "#a8d5b5", "#4c9a6a", "#1b6b3a"],  /* green, 5 classes */
    pets:       ["#fdf0dc", "#f6c886", "#e89331", "#b3630f"],  /* orange  */
    competition:["#e9e2f6", "#c3b0e6", "#9a7ed4", "#7856be"],  /* purple  */
    growth:     ["#efe6dd", "#d2b696", "#a3764a", "#5f3a1e"],  /* brown   */
    households: ["#e4eff8", "#a9cfe9", "#5aa2d0", "#1f6fa8"],  /* blue    */
    econ:       ["#fce8ef", "#f2b8cd", "#dd7ba1", "#b0446e"]   /* rose    */
  },
  cool: {
    income:     ["#e4eff8", "#c6dff1", "#a9cfe9", "#5aa2d0", "#1f6fa8"],
    pets:       ["#e0f2f1", "#a3ddd8", "#4bb3ab", "#127c74"],
    competition:["#e9e2f6", "#c3b0e6", "#9a7ed4", "#7856be"],
    growth:     ["#e6f2e8", "#a8d5b5", "#4c9a6a", "#1b6b3a"],
    households: ["#e5e9f5", "#b3bde3", "#7183c9", "#3b4c9c"],
    econ:       ["#ddeef4", "#a6d3e2", "#5aa8c4", "#1d7391"]
  },
  colorblind: {
    /* Okabe–Ito derived: distinguishable under deuteranopia and protanopia. */
    income:     ["#e3f0f4", "#c6e2e9", "#a8d3dd", "#5aa7b8", "#0f6b7d"],
    pets:       ["#fdefe0", "#f7ce9e", "#e69f41", "#b06d0d"],
    competition:["#efe6f3", "#cdb2dd", "#a377bd", "#7a4a94"],
    growth:     ["#e8f1e3", "#bcd9ad", "#84b96c", "#4a8b32"],
    households: ["#e4e9f6", "#b0bde6", "#6d84cd", "#33509e"],
    econ:       ["#fce9e6", "#f4bdb3", "#e2857a", "#b0453a"]
  }
};

const VALUE_LAYERS = {
  income: { label: "Median Household Income (ACS)", short: "Median household income", unit: "usd", buckets: ["< $50K", "$50–75K", "$75–100K", "$100–150K", "> $150K"], stops: [50000, 75000, 100000, 150000] },
  pets: { label: "Estimated Pet Households", short: "Est. pet households", unit: "count", buckets: ["< 10K", "10K–25K", "25K–40K", "> 40K"], stops: [10000, 25000, 40000] },
  growth: { label: "Population Growth Since 2015 (ACS)", short: "Projected growth (5 yrs)", unit: "pct", buckets: ["< 10%", "10–20%", "20–35%", "> 35%"], stops: [10, 20, 35] },
  households: { label: "Households (ACS)", short: "Total households", unit: "count", buckets: ["< 10K", "10K–25K", "25K–45K", "> 45K"], stops: [10000, 25000, 45000] },
  econ: { label: "Average Practice Payroll (CBP)", short: "Avg. payroll per practice", unit: "usd", buckets: ["< $450K", "$450–650K", "$650–900K", "> $900K"], stops: [450000, 650000, 900000] },
  competition: { label: "Veterinary Establishments (CBP)", short: "Vet establishments", unit: "count", buckets: ["1–2", "3–5", "6–9", "10+"], stops: [3, 6, 10] }
};

// Rates and medians belong to the area → choropleth fill (one at a time: two
// translucent fills mix into a third colour that means nothing).
const FILL_KEYS = ["income", "growth", "econ"];
// Counts → graduated symbols, sized by value. These stack freely, because size and
// position are a different visual channel from the fill beneath them.
const SYMBOL_KEYS = ["pets", "households", "competition"];
const SYMBOL_STYLE = {
  pets: { color: "rgba(232,147,49,.85)", label: "Est. pet households" },
  households: { color: "rgba(31,111,168,.85)", label: "Households" },
  competition: { color: "rgba(120,86,190,.85)", label: "Vet establishments" }
};

// Graduated-size key. Pixel values mirror the renderer's 11 + t·22 sizing at t = 0, .5, 1.
const SYMBOL_SCALE = {
  pets: [{ px: 6, label: "10K" }, { px: 9, label: "25K" }, { px: 13, label: "40K+" }],
  households: [{ px: 6, label: "10K" }, { px: 9, label: "25K" }, { px: 13, label: "45K+" }],
  competition: [{ px: 6, label: "2" }, { px: 9, label: "8" }, { px: 13, label: "14+" }]
};

// One catalogue per market layer: what it is, where it comes from, and how to read it.
// "derived" marks metrics that are modelled rather than observed.
const LAYER_META = {
  income: {
    title: "Median household income",
    sub: "Household income by community · ACS 5-year",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    source: "U.S. Census ACS 5-year estimates (2023) · community level",
    means: "Higher-income areas may support stronger demand, but income alone does not indicate practice performance.",
    why: "Household income can correlate with pet care spending and service mix, helping you identify attractive markets to explore further."
  },
  pets: {
    title: "Pet ownership (estimated)",
    sub: "Estimated pet households · derived from ACS households",
    updated: "Updated: derived Jan 2025 from ACS 2023",
    source: "Derived estimate from ACS household counts (2023) · not an observed count",
    means: "This is a modelled estimate of how many households in an area keep pets, not a measured figure.",
    why: "Pet-household concentration is a rough proxy for the size of the potential client base near a practice."
  },
  competition: {
    title: "Veterinary competition",
    sub: "Veterinary establishments · CBP, NAICS 541940",
    updated: "Updated: CBP 2023 release (Nov 2024)",
    source: "U.S. Census County Business Patterns (2023), NAICS 541940 · community level",
    means: "Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.",
    why: "Competitive density helps you judge whether a market is underserved or already crowded."
  },
  growth: {
    title: "Population growth",
    sub: "Change since 2015 · ACS population estimates",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    source: "U.S. Census ACS population estimates, 2015–2023 · community level",
    means: "Growth describes how fast an area's population changed. Past growth is not a forecast.",
    why: "Areas adding households may add pet owners, which matters more for a practice you intend to hold for years."
  },
  households: {
    title: "Households",
    sub: "Total households · ACS 5-year",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    source: "U.S. Census ACS 5-year estimates (2023) · community level",
    means: "The count of occupied housing units in each community — the denominator behind most other figures here.",
    why: "Household counts give scale: two areas can share an income level and differ tenfold in size."
  },
  econ: {
    title: "Average practice payroll",
    sub: "Derived · total CBP payroll ÷ establishments",
    updated: "Updated: derived from CBP 2023 (Nov 2024)",
    source: "Derived from Census CBP payroll and establishment counts (2023) · market level, not practice level",
    means: "A derived market-level indicator of how large the typical veterinary employer in an area is. It is not revenue, and not any individual practice's figures.",
    why: "Typical employer scale hints at the staffing model a market supports, which is context for a practice's own numbers."
  }
};


const num = (s) => (s == null ? 0 : Number(String(s).replace(/[^0-9.]/g, "")) || 0);

// SUBSTITUTIONS — the VIN icon set ships no heart or check glyph. Per the design system's
// iconography rule (no unicode glyphs as icons) these are closest-match filled silhouettes
// matched to the set's heavy/filled weight. Swap in authentic assets when VIN provides them.
class Component extends DCLogic {
  state = {
    screen: "gate", gate: "signin", auth: false, viewport: "desktop", mobileTab: "list",
    email: "r.mendes@example.com", pw: "············", formError: "",
    apply: { name: "Rachel Mendes, DVM", vin: "", grad: "", state: "TX", employer: "", intent: "", affirm: true, error: "" },
    f: { type: "Any", price: "Any", revenue: "Any", doctors: "Any", building: "Any" },
    loading: false, activeId: null, hoverId: null, detailId: "p1", detailDocs: false,
    interest: "closed", interestMsg: "", sent: [],
    step: 1, wizErr: "", wizSubmitted: false,
    w: { name: "", type: "Small animal", est: "", city: "", zip: "", anon: true, price: "", rev: "", revBand: false, docs: "", rooms: "", sqft: "", bldg: "Included", facility: "", desc: "", photos: 0, ownership: "Sole proprietor", hours: "", facilityType: "Standalone", docsLocked: true },
    adminTab: "users", sellerView: "dash",
    sellerListings: [
      { id: "s1", title: "Small animal practice — Cedar Park", meta: "$1.45M · 3 doctors · 4,200 sq ft", status: "published", note: "Live since August 24 · 34 views, 2 requests" },
      { id: "s2", title: "Mixed practice — Bastrop", meta: "$860K · 2 doctors · 3,000 sq ft", status: "in_review", note: "Submitted September 1 · awaiting VIN Foundation review" },
      { id: "s3", title: "Untitled listing", meta: "Draft started August 30", status: "draft", note: "Financial and property sections still empty" },
      { id: "s4", title: "Small animal practice — Buda", meta: "$1.1M · 2 doctors · 3,400 sq ft", status: "paused", note: "Paused by you on August 12 · hidden from search" }
    ],
    requests: [
      { id: "r1", pid: "p1", buyer: "Dr. Rachel Mendes", status: "pending", when: "Aug 29", msg: "Interested in a phased transition; I have SBA pre-qualification." },
      { id: "r2", pid: "p7", buyer: "Dr. Rachel Mendes", status: "accepted", when: "Aug 21", msg: "Would like to see the last three years of production by doctor.", reply: "Happy to share. Financial packet unlocked — call me next week." },
      { id: "r3", pid: "p6", buyer: "Dr. Rachel Mendes", status: "declined", when: "Aug 14", msg: "Do you expect the overnight team to stay through a sale?", reply: "Under contract with another buyer. Thank you for reaching out." }
    ],
    me: { name: "Dr. Rachel Mendes", role: "Approved buyer · StartUp Club", initials: "RM" }
  };

  trackWidth() {
    const set = () => this.setState({ vw: window.innerWidth });
    set();
    this._onResize = set;
    window.addEventListener("resize", set);
  }

  componentWillUnmount() {
    if (this._onResize) window.removeEventListener("resize", this._onResize);
  }

  componentDidMount() {
    this.trackWidth();
    const start = this.props.startScreen;
    if (start && start !== "gate") this.setState({ screen: start, auth: true });
    if (this.props.startViewport === "mobile") this.setState({ viewport: "mobile" });
  }

  money(n) {
    if (n == null || n === "") return "—";
    if (n >= 1000000) return "$" + (n / 1000000).toFixed(n >= 10000000 ? 0 : 2).replace(/\.00$/, "") + "M";
    return "$" + Math.round(n / 1000) + "K";
  }

  go = (screen) => () => {
    if (screen !== "gate" && !this.state.auth) return this.setState({ screen: "gate", gate: "signin", userMenu: false });
    this.setState({ screen, interest: "closed", userMenu: false });
  };

  jumpTo = (screen) => () => this.setState({ screen, auth: screen !== "gate", interest: "closed", userMenu: false, gate: "signin" });

  setF = (key) => (e) => {
    const v = e && e.target ? e.target.value : e;
    this.setState((s) => ({ f: Object.assign({}, s.f, { [key]: v }), loading: true }));
    clearTimeout(this._t);
    this._t = setTimeout(() => this.setState({ loading: false }), 320);
  };

  // ---- Browse Practices: map, market layers, results -------------------------------------------------

  communities() {
    const market = this.state.market || "Austin, TX";
    return P.filter((p) => p.market === market && p.status === "published").map((p) => {
      const hh = num(p.hh);
      return {
        id: p.id, name: p.area, lat: p.lat, lng: p.lng,
        pop: num(p.pop), hh: hh, income: num(p.income),
        growth: parseFloat(String(p.growth).replace(/[^0-9.\-]/g, "")) || 0,
        pets: Math.round(hh * 0.57),
        econ: (ECON_K[p.id] || 0) * 1000,
        vets: VETS[p.id] || 0
      };
    });
  }

  bucket(metric, v) {
    const cfg = VALUE_LAYERS[metric];
    const pal = PALETTES[this.props.layerPalette] || PALETTES.distinct;
    const ramp = pal[metric === "vets" ? "competition" : metric] || BRAND_RAMP;
    let i = 0;
    while (i < cfg.stops.length && v >= cfg.stops[i]) i++;
    return { color: ramp[i], t: i / (ramp.length - 1) };
  }

  fmtMetric(metric, v) {
    const u = VALUE_LAYERS[metric].unit;
    if (u === "usd") return "$" + Math.round(v / 1000) + "K";
    if (u === "pct") return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
    return v >= 1000 ? Math.round(v / 1000) + "K" : String(v);
  }

  marketVals(list) {
    const s = this.state;
    const market = s.market || "Austin, TX";
    const cfg = MARKETS[market];
    const comms = this.communities();
    const valueLayer = s.mdValue === undefined ? "income" : s.mdValue;
    const layers = Object.assign(
      { practices: true, drive5: true, drive10: true, competition: true, households: false, pets: false },
      s.mdLayers || {}
    );
    const sel = s.mdSel ? P.filter((x) => x.id === s.mdSel)[0] : null;
    const pal = PALETTES[this.props.layerPalette] || PALETTES.distinct;
    const ramp = (k) => pal[k] || BRAND_RAMP;
    const tightColumn = !!s.mdStrip;
    const activeSymbols = SYMBOL_KEYS.filter(
      (k) => layers[k] && !(s.mdOff || {})[k === "competition" ? "vets" : k]
    );
    const selComm = sel ? comms.filter((c) => c.id === sel.id)[0] : null;

    const lats = comms.map((c) => c.lat), lngs = comms.map((c) => c.lng);
    const pad = 0.12;
    const minLat = Math.min.apply(null, lats) - pad, maxLat = Math.max.apply(null, lats) + pad;
    const minLng = Math.min.apply(null, lngs) - pad, maxLng = Math.max.apply(null, lngs) + pad;

    const layerRow = (key, label, on, color, toggle) => ({
      label, on,
      toggle,
      boxStyle: "flex: none; width: 17px; height: 17px; border-radius: 3px; display: grid; place-items: center; border: 1.5px solid " +
        (on ? color : "#c4ccd6") + "; background: " + (on ? color : "var(--vf-white)") + ";",
      tickStyle: "display: block; opacity: " + (on ? "1" : "0") + ";",
      textStyle: "font-size: 13px; font-weight: " + (on ? "500" : "400") + "; color: " + (on ? "var(--vf-navy)" : "var(--vf-text)") + ";"
    });

    const radioRow = (key, label, on, color, toggle) => ({
      label, on, toggle,
      boxStyle: "flex: none; width: 15px; height: 15px; border-radius: 999px; display: grid; place-items: center; border: 1.5px solid " +
        (on ? "var(--vf-navy)" : "#c3d4e2") + "; background: var(--vf-white);",
      dotStyle: "width: 7px; height: 7px; border-radius: 999px; background: var(--vf-navy); opacity: " + (on ? "1" : "0") + ";",
      swatchStyle: "flex: none; width: 12px; height: 12px; border-radius: 2px; background: " + (color || "transparent") +
        "; opacity: " + (color ? (on ? "1" : ".4") : "0") + ";",
      labelStyle: "font-size: 12.5px; font-weight: " + (on ? "500" : "400") + "; color: " + (on ? "var(--vf-navy)" : "var(--vf-text)") + ";"
    });

    const setValue = (k) => () => this.setState({ mdValue: s.mdValue === k ? null : k });
    const setLayer = (k) => () => this.setState({ mdLayers: Object.assign({}, layers, { [k]: !layers[k] }) });

    // A footer card is the SOURCE switch for its dataset: off means the dataset
    // is not in play at all, so its row leaves the Data Layers widget.
    const off = s.mdOff || {};
    const enabled = (k) => !off[k];
    const setSource = (k) => () => {
      const next = Object.assign({}, off, { [k]: !off[k] });
      const patch = { mdOff: next };
      if (next[k]) {
        if (s.mdValue === k) patch.mdValue = null;
        if (k === "vets") patch.mdLayers = Object.assign({}, layers, { competition: false });
      }
      this.setState(patch);
    };

    const cards = [
      { n: "1", title: "Demographics", blurb: "Population, households, income", src: "Census ACS 5-year", metric: "income", caption: "Median household income", layerName: "Median Household Income" },
      { n: "2", title: "Pet Ownership (Est.)", blurb: "Estimated pet households", src: "derived from ACS households", metric: "pets", caption: "Est. pet households", layerName: "Pet Ownership (est.)" },
      { n: "3", title: "Veterinary Competition", blurb: "Veterinary establishments", src: "Census CBP, NAICS 541940", metric: "vets", caption: "Number of vet establishments", layerName: "Veterinary Competition" },
      { n: "4", title: "Population Growth", blurb: "Change since 2015", src: "Census ACS population estimates", metric: "growth", caption: "Growth since 2015", layerName: "Population Growth" },
      { n: "5", title: "Households", blurb: "Occupied housing units", src: "Census ACS 5-year", metric: "households", caption: "Total households", layerName: "Households" },
      { n: "6", title: "Avg. Practice Payroll", blurb: "Typical practice size proxy", help: "Total industry payroll ÷ number of practices — a proxy for how large the typical practice is. Not revenue, and not any one practice's figures.", src: "Census CBP payroll ÷ establishments", metric: "econ", caption: "Avg. payroll per practice", layerName: "Average Practice Profile" }
    ].map((c) => Object.assign({}, c, { on: enabled(c.metric) }));

    return {
      isMarket: s.screen === "browse",
      activeId: s.mdSel || null,
      resizeKey: s.screen + s.viewport + market + (s.mdSel || "") ,
      selectFromMap: (id) => this.setState({ mdSel: id, mdTab: "insights", mdPhoto: 0 }),
      openSpec: (e) => { if (e) e.preventDefault(); },
      stripOpen: !!s.mdStrip,
      toggleStrip: () => this.setState({ mdStrip: !s.mdStrip }),
      stripToggleLabel: s.mdStrip ? "Collapse" : "Expand all six layers",
      stripCaretStyle: "flex: none; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 4px; background: var(--vf-neutral); transform: rotate(" +
        (s.mdStrip ? "0deg" : "-90deg") + "); transition: transform 150ms var(--easing-out);",
      basemap: s.mdBasemap || "map",
      setBasemap: (k) => this.setState({ mdBasemap: k }),
      railStyle: (() => {
        const vw = s.vw || (typeof window !== "undefined" ? window.innerWidth : 1440);
        // Panel open on a narrow viewport: the detail replaces the list rather than
        // squeezing the map below the width its own overlay chrome needs.
        const hide = !!sel && vw < 1320;
        return "flex: 1 1 470px; max-width: 470px; min-width: 320px; overflow-y: auto; border-left: 1px solid #e6e6e6; background: var(--vf-white); display: " +
          (hide ? "none" : "block") + ";";
      })(),
      mapCenter: cfg.center,
      mapZoom: cfg.zoom,
      driveCenter: sel ? [sel.lat, sel.lng] : cfg.center,
      layers,
      valueLayer,
      communities: comms.map((c) => {
        const vals = {};
        ["income", "pets", "growth", "households", "econ", "competition"].forEach((k) => {
          const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];
          const b = this.bucket(k, raw);
          vals[k] = { t: b.t, color: b.color, label: this.fmtMetric(k, raw) };
        });
        return {
          name: c.name, lat: c.lat, lng: c.lng, vets: c.vets, values: vals,
          metricName: valueLayer ? LAYER_META[valueLayer].title : "",
          sourceNote: valueLayer ? LAYER_META[valueLayer].source : ""
        };
      }),
      practices: list.map((p) => ({
        id: p.id, lat: p.lat, lng: p.lng,
        priceLabel: this.money(p.price),
        name: this.practiceName(p),
        photoSrc: this.thumbSrc(p),
        meta: p.docs + (p.docs === 1 ? " doctor" : " doctors") + " · " + this.money(p.rev) + " revenue"
      })),
      activeLayer: valueLayer,
      active: (() => {
        const meta = LAYER_META[valueLayer] || {};
        const cfg = valueLayer ? VALUE_LAYERS[valueLayer] : null;
        return {
          title: meta.title || "No layer active",
          sub: meta.sub || "Choose a layer to shade the map",
          sourceLine: meta.source ? "Source: " + meta.source : "",
          sourceShort: meta.source ? "Source: " + meta.source.split(" · ")[0] : "",
          updatedLine: meta.updated || "",
          means: meta.means || "",
          why: meta.why || "",
          hasRamp: !!valueLayer,
          ramp: valueLayer
            ? ramp(valueLayer).map((c, i) => ({
                style: "flex: 1; height: 9px; background: " + c + ";",
                label: cfg.buckets[i]
              }))
            : []
        };
      })(),
      activeCountLabel: (() => {
        const n = ["income", "pets", "competition", "growth", "households", "econ"]
          .filter((k) => enabled(k === "competition" ? "vets" : k)).length;
        return n + " of 6";
      })(),

      // The layer SELECT in the Market layer card — switching layers happens here, not
      // buried in a drawer. It lists exactly the datasets enabled under Layers.
      activeLayerKey: valueLayer || "none",
      activeLayerLabel: valueLayer ? LAYER_META[valueLayer].title : "No shading — practices only",
      layerMenuOpen: !!s.mdLayerMenu,
      toggleLayerMenu: () => this.setState({ mdLayerMenu: !s.mdLayerMenu }),
      layerSelectStyle: "display: flex; align-items: center; gap: 8px; width: 100%; height: 40px; padding: 0 11px; font-family: var(--rf-display); font-size: 14px; font-weight: 500; color: var(--vf-navy); background: var(--vf-white); border: 1px solid " +
        (s.mdLayerMenu ? "var(--vf-accent)" : "var(--border-subtle)") + "; border-radius: 6px; cursor: pointer;",
      layerMenuCaretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +
        (s.mdLayerMenu ? "180deg" : "0deg") + ");",
      layerOptions: [{ v: "none", label: "No shading — practices only" }].concat(
        ["income", "pets", "competition", "growth", "households", "econ"]
          .filter((k) => enabled(k === "competition" ? "vets" : k))
          .map((k) => ({ v: k, label: LAYER_META[k].title }))
      ).map((o) => {
        const on = (valueLayer || "none") === o.v;
        return {
          label: o.label,
          selected: on,
          go: () => this.setState({
            mdValue: o.v === "none" ? null : o.v,
            mdLayerMenu: false,
            mdInsightOff: false
          }),
          rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +
            (on ? "800" : "500") + "; color: var(--vf-navy); background: " +
            (on ? "var(--vf-accent-bg)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",
          chipStyle: "flex: none; width: 20px; height: 20px; border-radius: 4px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid rgba(0,58,112,.12);",
          chips: (o.v === "none" ? ["var(--vf-neutral)", "var(--vf-neutral)"] : ramp(o.v)).map((c) => ({
            style: "flex: 1; background: " + c + ";"
          })),
          tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +
            (on ? "1" : "0") + ";"
        };
      }),

      // Compare — optional second metric, shown as paired bars rather than a second fill.
      compareOpen: !!s.mdCompareOpen,
      toggleCompare: () => this.setState({ mdCompareOpen: !s.mdCompareOpen }),
      compareNote: s.mdCompareOpen ? "close" : s.mdCompare ? "1 metric" : "(optional)",
      compareClosed: !s.mdCompareOpen,
      compareStyle: "display: flex; align-items: center; gap: 10px; width: 100%; margin-top: 8px; padding: 12px 14px; text-align: left; background: var(--vf-white); border: 1px solid " +
        (s.mdCompareOpen ? "var(--vf-accent)" : "var(--border-subtle)") +
        "; border-radius: 8px; box-shadow: 0 3px 12px rgba(0,58,112,.1); cursor: pointer;",
      comparePlusStyle: "flex: none; display: block; opacity: .7;",
      compareMenuOpen: !!s.mdCompareMenu,
      compareCaretStyle: "flex: none; opacity: .5; transition: transform .15s; transform: rotate(" + (s.mdCompareMenu ? "180deg" : "0deg") + ");",
      compareTriggerLabel: s.mdCompare && s.mdCompare !== valueLayer ? LAYER_META[s.mdCompare].title : "Choose a metric…",
      toggleCompareMenu: () => this.setState((st) => ({ mdCompareMenu: !st.mdCompareMenu })),
      compareMenuRef: (el) => {
        if (!el || !el.parentElement) return;
        const host = el.parentElement.closest(".rf-scroll");
        if (!host) return;
        requestAnimationFrame(() => {
          const over = el.getBoundingClientRect().bottom - host.getBoundingClientRect().bottom;
          if (over > 0) host.scrollTop += over + 10;
        });
      },
      compareOptions: [{ v: "none", label: "Choose a metric…" }].concat(
        ["income", "pets", "competition", "growth", "households", "econ"]
          .filter((k) => k !== valueLayer && enabled(k === "competition" ? "vets" : k))
          .map((k) => ({ v: k, label: LAYER_META[k].title }))
      ).map((o) => {
        const on = o.v === "none" ? !s.mdCompare || s.mdCompare === valueLayer : s.mdCompare === o.v;
        return {
          label: o.label,
          selected: on,
          go: () => this.setState({ mdCompare: o.v === "none" ? null : o.v, mdCompareMenu: false }),
          rowStyle: "display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 8px; text-align: left; font-size: 12.5px; font-weight: " +
            (on ? "700" : "500") + "; color: var(--vf-navy); background: " + (on ? "var(--vf-accent-bg)" : "none") +
            "; border: 0; border-radius: 6px; cursor: pointer;",
          chipStyle: "flex: none; width: 20px; height: 20px; border-radius: 4px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid rgba(0,58,112,.12);",
          chips: (o.v === "none" ? ["var(--vf-white)", "var(--vf-white)"] : ramp(o.v)).map((c) => ({ style: "flex: 1; background: " + c + ";" })),
          tickStyle: "flex: none; display: block; opacity: " + (on ? "1" : "0") + ";"
        };
      }),
      hasCompare: !!s.mdCompare && !!valueLayer && s.mdCompare !== valueLayer,
      compareLabelA: valueLayer ? LAYER_META[valueLayer].title : "",
      compareLabelB: s.mdCompare ? LAYER_META[s.mdCompare].title : "",
      compareKeyA: "flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); background: linear-gradient(to right, " + (valueLayer ? ramp(valueLayer).join(", ") : "transparent, transparent") + ");",
      compareKeyB: "flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); background: linear-gradient(to right, " + (s.mdCompare ? ramp(s.mdCompare).join(", ") : "transparent, transparent") + ");",
      compareRows: (!s.mdCompare || !valueLayer || s.mdCompare === valueLayer) ? [] : comms.slice(0, 6).map((c) => {
        const raw = (k) => (k === "households" ? c.hh : k === "competition" ? c.vets : c[k]);
        const ta = this.bucket(valueLayer, num(raw(valueLayer))).t;
        const tb = this.bucket(s.mdCompare, num(raw(s.mdCompare))).t;
        const fillA = this.bucket(valueLayer, num(raw(valueLayer))).color;
        const fillB = this.bucket(s.mdCompare, num(raw(s.mdCompare))).color;
        return {
          name: c.name,
          aStyle: "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + ta * 92) + "%; background: " + fillA + ";",
          bStyle: "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + tb * 92) + "%; background: " + fillB + ";"
        };
      }),

      layerChoices: ["income", "pets", "competition", "growth", "households", "econ"].map((k) => {
        const srcKey = k === "competition" ? "vets" : k;
        const on = enabled(srcKey);
        return {
          title: LAYER_META[k].title,
          sub: LAYER_META[k].sub,
          // Enable/disable the dataset. Turning off the layer currently shading the map
          // hands shading to the next enabled one, so the map is never left in a state
          // the dropdown cannot describe.
          go: () => {
            const nextOff = Object.assign({}, s.mdOff || {}, { [srcKey]: on });
            const stillOn = ["income", "pets", "competition", "growth", "households", "econ"]
              .filter((x) => !nextOff[x === "competition" ? "vets" : x]);
            const nextValue = stillOn.indexOf(valueLayer) > -1 ? valueLayer : (stillOn[0] || null);
            this.setState({ mdOff: nextOff, mdValue: nextValue, mdInsightOff: false });
          },
          rowStyle: "display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 8px; text-align: left; background: none; border: 0; border-radius: 6px; cursor: pointer;",
          chips: ramp(k).map((c) => ({
            style: "flex: 1; background: " + c + "; opacity: " + (on ? "1" : ".35") + ";"
          })),
          swatchStyle: "flex: none; width: 28px; height: 28px; border-radius: 5px; overflow: hidden; display: flex; flex-direction: column; border: 1px solid rgba(0,58,112,.12);",
          titleStyle: "display: block; font-family: var(--rf-display); font-size: 12.5px; font-weight: 500; color: var(--vf-navy);",
          isOn: on,
          radioStyle: "flex: none; width: 17px; height: 17px; border-radius: 4px; display: grid; place-items: center; border: 1.5px solid " +
            (on ? "var(--vf-accent)" : "#c3d4e2") + "; background: " + (on ? "var(--vf-accent)" : "var(--vf-white)") + ";",
          dotStyle: "display: block; opacity: " + (on ? "1" : "0") + ";"
        };
      }),
      layersOpen: !!s.mdLayersOpen,
      toggleLayers: () => this.setState({ mdLayersOpen: !s.mdLayersOpen }),
      layersBtnStyle: "display: flex; align-items: center; gap: 9px; width: 100%; height: 40px; padding: 0 12px; font-family: var(--rf-display); font-size: 13.5px; font-weight: 500; color: var(--vf-white); background: var(--vf-accent); border: 0; border-radius: 8px; cursor: pointer; box-shadow: 0 4px 14px rgba(0,58,112,.22);",
      layersCaretStyle: "flex: none; filter: brightness(0) invert(1); opacity: .8; transform: rotate(" +
        (s.mdLayersOpen ? "0deg" : "180deg") + "); transition: transform 150ms var(--easing-out);",
      legendOpen: s.mdLegendOff !== true,
      legendExpanded: s.mdLegendOff !== true,
      legendToggleLabel: s.mdLegendOff === true ? "Expand market layer panel" : "Collapse market layer panel",
      legendCaretStyle: "display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +
        (s.mdLegendOff === true ? "180deg" : "0deg") + ");",
      toggleLegend: () => this.setState({ mdLegendOff: s.mdLegendOff !== true }),

      legendBtnStyle: "display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 14px; font-family: var(--rf-display); font-size: 12.5px; font-weight: 500; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,58,112,.14); color: " +
        (s.mdLegendOff !== true ? "var(--vf-navy)" : "var(--vf-text)") +
        "; background: var(--vf-white); border: 1px solid " +
        (s.mdLegendOff !== true ? "var(--vf-accent)" : "var(--border-subtle)") +
        "; border-radius: 6px; cursor: pointer;",
      insightOpen: (() => {
        const vw = s.vw || (typeof window !== "undefined" ? window.innerWidth : 1440);
        // map column ≈ viewport − results rail − open detail panel
        const mapW = vw - 470 - (s.mdSel ? 366 : 0);
        return !!valueLayer && !s.mdInsightOff && s.mdLegendOff !== true && mapW >= 810;
      })(),
      dismissInsight: () => this.setState({ mdInsightOff: true }),
      showDrive: !!sel,
      recenterKey: s.mdRecenter || 0,
      resetView: () => this.setState({ mdSel: null, mdRecenter: (s.mdRecenter || 0) + 1 }),
      selectArea: (name) => this.setState({ mdArea: name }),
      snapshotCount: "6 indicators · Census-sourced",
      // GROUP 1 — retained for the legacy panel; the compact control above is canonical.
      layerHelp: "Area shading: rates and medians shade the whole community, so only one can show at a time — two fills blend into a colour that means nothing. Overlays: counts drawn as sized circles, which stack freely on each other and on the shading.",
      fillRows: [radioRow("none", "No shading", !valueLayer, null, () => this.setState({ mdValue: null }))].concat(
        enabled("income") ? [radioRow("income", "Median Household Income", valueLayer === "income", ramp("income")[3], setValue("income"))] : [],
        enabled("growth") ? [radioRow("growth", "Population Growth", valueLayer === "growth", ramp("growth")[3], setValue("growth"))] : [],
        enabled("econ") ? [radioRow("econ", "Average Practice Payroll", valueLayer === "econ", ramp("econ")[3], setValue("econ"))] : []
      ),
      // GROUP 2 — everything that can coexist with a fill and with each other.
      overlayRows: [
        layerRow("practices", "Practice Listings", !!layers.practices, "#003a70", setLayer("practices")),
        layerRow("drive5", "5–10 min drive time", !!layers.drive5, "#003a70", setLayer("drive5")),
        layerRow("drive10", "10–20 min drive time", !!layers.drive10, "#339dde", setLayer("drive10"))
      ].concat(
        enabled("households") ? [layerRow("households", "Households", !!layers.households, ramp("households")[3], setLayer("households"))] : [],
        enabled("pets") ? [layerRow("pets", "Estimated Pet Households", !!layers.pets, ramp("pets")[3], setLayer("pets"))] : [],
        enabled("vets") ? [layerRow("competition", "Veterinary Establishments", !!layers.competition, ramp("competition")[3], setLayer("competition"))] : []
      ),
      symbols: activeSymbols,
      symbolColors: SYMBOL_KEYS.reduce((o, k) => { o[k] = ramp(k)[3]; return o; }, {}),
      hiddenLayers: ["pets", "income", "growth", "vets", "households", "econ"].filter((k) => off[k]).length,
      hasHiddenLayers: ["pets", "income", "growth", "vets", "households", "econ"].some((k) => off[k]),
      // Legend yields before the controls panel does: below a short map column the symbol
      // rows fold away and the key shows the fill ramp only.
      legendBoxStyle: "flex: 0 1 auto; width: 276px; pointer-events: auto; overflow: hidden; padding: 10px 12px 11px; " +
        "background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 6px; box-shadow: 0 2px 8px rgba(0,58,112,.16);",
      // Every mark on the map gets a key: the fill ramp with its real class breaks, plus
      // a hue + graduated-size row for each active count layer.
      hasLegend: !!valueLayer || activeSymbols.length > 0,
      legend: {
        hasFill: !!valueLayer,
        title: valueLayer ? VALUE_LAYERS[valueLayer].label : "",
        swatches: valueLayer
          ? ramp(valueLayer).map((c, i) => ({
              style: "flex: 1; height: 10px; background: " + c + ";",
              label: VALUE_LAYERS[valueLayer].buckets[i]
            }))
          : [],
        hasSymbols: activeSymbols.length > 0 && !tightColumn,
        symbolWrapStyle: "margin-top: " + (valueLayer ? "10px" : "0") +
          "; padding-top: " + (valueLayer ? "9px" : "0") +
          "; border-top: " + (valueLayer ? "1px solid #e6e6e6" : "0") + ";",
        symbols: activeSymbols.map((k) => {
          const hue = ramp(k)[3];
          return {
            label: SYMBOL_STYLE[k].label,
            swatchStyle: "flex: none; width: 10px; height: 10px; border-radius: 999px; background: " + hue + ";",
            sizes: SYMBOL_SCALE[k].map((row) => ({
              label: row.label,
              dotStyle: "display: block; width: " + row.px + "px; height: " + row.px +
                "px; border-radius: 999px; background: " + hue + "; opacity: .85;"
            }))
          };
        })
      },
      mdHeadline: list.length + (list.length === 1 ? " practice available" : " practices available"),
      mdSubline: market + " metro · within 20 miles",
      mdResults: list.map((p) => {
        const c = comms.filter((x) => x.id === p.id)[0];
        return {
          eyebrow: p.type.toUpperCase(),
          photoId: "ph-" + p.id + "-exterior",
          photoHint: "Exterior",
          photoSrc: this.heroSrc(p),
          hasPhotoSrc: !!this.heroSrc(p),
          noPhotoSrc: !this.heroSrc(p),
          name: this.practiceName(p),
          place: p.area + ", " + this.stateOf(market),
          priceLabel: this.money(p.price),
          revLabel: this.money(p.rev),
          ebitdaLabel: this.money(Math.round(p.rev * 0.19)),
          docs: String(p.docs),
          sqft: p.sqft.toLocaleString(),
          meta: [
            { value: this.money(p.rev), unit: "revenue" },
            { value: String(p.docs), unit: p.docs === 1 ? "doctor" : "doctors" },
            { value: p.sqft.toLocaleString(), unit: "sq ft" }
          ].map((mm, mi) => Object.assign({}, mm, {
            // A thin rule separates items; it sits inside each item so it survives wrapping.
            wrapStyle: "display: inline-flex; align-items: center; flex: none;" +
              (mi > 0 ? " padding-left: 10px; border-left: 1px solid #e6e6e6;" : "")
          })),
          saved: (s.mdSaved || []).indexOf(p.id) > -1,
          heartIconStyle: "display: block; filter: " + ((s.mdSaved || []).indexOf(p.id) > -1 ? "none" : "brightness(0) invert(.78)") + ";",
          heartStyle: "position: absolute; left: 8px; bottom: 8px; width: 26px; height: 26px; border-radius: 999px; display: grid; place-items: center; border: 0; cursor: pointer; background: var(--vf-white); box-shadow: 0 1px 4px rgba(0,58,112,.25); color: " +
            ((s.mdSaved || []).indexOf(p.id) > -1 ? "var(--vf-navy)" : "#8d99a6") + "; font-size: 13px; line-height: 1;",
          toggleSave: (e) => {
            e.stopPropagation();
            const saved = s.mdSaved || [];
            this.setState({ mdSaved: saved.indexOf(p.id) > -1 ? saved.filter((x) => x !== p.id) : saved.concat([p.id]) });
          },
          select: () => this.setState({ mdSel: p.id, mdTab: "insights", mdPhoto: 0 }),
          cardStyle: "display: flex; gap: 13px; padding: 12px; border: 1.5px solid " +
            (s.mdSel === p.id ? "var(--vf-accent)" : "#e6e6e6") + "; background: " +
            (s.mdSel === p.id ? "#f2f8fd" : "var(--vf-white)") +
            "; border-radius: 8px; cursor: pointer; box-shadow: " +
            (s.mdSel === p.id ? "0 2px 8px rgba(51,157,222,.16)" : "none") +
            "; transition: border-color 150ms linear, background 150ms linear, box-shadow 150ms linear;"
        };
      }),
      showingLabel: "Showing 1–" + Math.min(5, list.length) + " of " + list.length + " practices",
      pager: [
        { label: "‹", aria: "Previous page", page: 0 },
        { label: "1", aria: "Page 1", page: 1 },
        { label: "2", aria: "Page 2", page: 2 },
        { label: "›", aria: "Next page", page: 0 }
      ].map((p) => ({
        label: p.label, aria: p.aria,
        go: () => this.setState({ mdPage: p.page || s.mdPage || 1 }),
        style: "width: 28px; height: 28px; display: grid; place-items: center; font-size: 12px; font-weight: 500; border-radius: 5px; cursor: pointer; border: 1px solid " +
          ((s.mdPage || 1) === p.page ? "var(--vf-accent)" : "var(--border-subtle)") + "; background: " +
          ((s.mdPage || 1) === p.page ? "var(--vf-accent)" : "var(--vf-white)") + "; color: " +
          ((s.mdPage || 1) === p.page ? "var(--vf-white)" : "var(--vf-navy)") + ";"
      })),
      hasSel: !!sel,
      panel: sel ? this.marketPanel(sel, selComm, comms, market) : null,
      closePanel: () => this.setState({ mdSel: null }),
      stripCards: ["income", "pets", "competition", "growth", "households", "econ"]
        .filter((k) => enabled(k === "competition" ? "vets" : k))
        .map((k) => {
          const meta = LAYER_META[k];
          const cfg = VALUE_LAYERS[k];
          const on = valueLayer === k;
          const vals = comms.map((c) => {
            const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];
            return { raw: num(raw), t: this.bucket(k, num(raw)).t };
          });
          const mid = vals.map((v) => v.raw).sort((a, b) => a - b)[Math.floor(vals.length / 2)] || 0;
          return {
            title: meta.title,
            value: this.fmtMetric(k, mid),
            valueNote: "metro median",
            src: meta.source,
            bars: vals.slice(0, 7).map((v) => ({
              style: "flex: 1; height: " + Math.max(4, Math.round(6 + v.t * 24)) +
                "px; border-radius: 2px 2px 0 0; background: " + ramp(k)[Math.min(3, Math.round(v.t * 3))] + ";"
            })),
            activate: () => this.setState({ mdValue: k, mdInsightOff: false, mdLegendOff: false }),
            linkLabel: on ? "Showing on map" : "View on map \u2192",
            linkStyle: "flex: none; margin-top: auto; padding-top: 9px; text-align: left; font-family: var(--rf-display); font-size: 11.5px; font-weight: 500; background: none; border: 0; cursor: pointer; color: " +
              (on ? "var(--vf-navy)" : "var(--vf-accent)") + ";",
            cardStyle: "display: flex; flex-direction: column; height: 100%; padding: 13px 14px; background: var(--vf-white); border: 1px solid " +
              (on ? "var(--vf-accent)" : "#e6e6e6") + "; border-radius: 8px;"
          };
        })
    };
  }

  // One photo set per hospital: every slot id is namespaced to the listing,
  // so a photo dropped for a hospital appears everywhere that hospital shows
  // and never bleeds into another location.
  photoSet(p) {
    // Real photographs supplied for a specific practice, keyed by slot id.
    const SRC = {
      "ph-p2-exterior": "/assets/photos/round-rock-exterior-street.webp",
      "ph-p2-exterior2": "/assets/photos/round-rock-exterior-side.webp",
      "ph-p2-exterior3": "/assets/photos/round-rock-exterior-parking.jpeg"
    };
    if (p.id === "p2") {
      const name = this.practiceName(p);
      return [
        ["exterior", "Exterior — street view"],
        ["exterior2", "Exterior — side elevation"],
        ["exterior3", "Exterior — parking and signage"],
        ["lobby", "Reception and waiting"],
        ["exam", "Exam room"],
        ["treatment", "Treatment area"]
      ].map((v, i) => {
        const id = "ph-" + p.id + "-" + v[0];
        return { id, caption: v[1], index: i + 1, placeholder: name + " — " + v[1], src: SRC[id] || "", hasSrc: !!SRC[id], noSrc: !SRC[id] };
      });
    }
    const equine = p.type === "Large animal";
    const views = equine
      ? [["exterior", "Exterior — street view"], ["barn", "Barn and stocks"], ["office", "Office and pharmacy"], ["truck", "Ambulatory vehicle"], ["lab", "Lab and storage"], ["grounds", "Grounds and turnout"]]
      : p.type === "Emergency"
        ? [["exterior", "Exterior — entrance"], ["triage", "Triage and intake"], ["treatment", "Treatment floor"], ["icu", "ICU and hospitalization"], ["surgery", "Surgery suite"], ["imaging", "Imaging room"]]
        : p.type === "Specialty"
          ? [["exterior", "Exterior — building"], ["lobby", "Reception and waiting"], ["consult", "Consult room"], ["surgery", "Surgery suite"], ["imaging", "CT and imaging"], ["recovery", "Recovery ward"]]
          : [["exterior", "Exterior — street view"], ["lobby", "Reception and waiting"], ["exam", "Exam room"], ["treatment", "Treatment area"], ["surgery", "Surgery suite"], ["kennel", "Boarding and runs"]];
    const name = this.practiceName(p);
    return views.map((v, i) => ({
      id: "ph-" + p.id + "-" + v[0],
      caption: v[1],
      index: i + 1,
      placeholder: name + " — " + v[1],
      src: "", hasSrc: false, noSrc: true
    }));
  }

  heroSrc(p) {
    return p.id === "p2" ? "/assets/photos/round-rock-exterior-street.webp" : "";
  }

  // Thumbnail-safe variant: reads at small sizes where the wide street view does not.
  thumbSrc(p) {
    return p.id === "p2" ? "/assets/photos/round-rock-exterior-parking.jpeg" : "";
  }

  practiceName(p) {
    const NAMES = {
      p1: "Cedar Park Animal Hospital", p2: "Round Rock Veterinary Clinic", p3: "South Austin Pet Hospital",
      p4: "Georgetown Animal Care", p5: "Kyle Family Veterinary", p6: "East Austin Emergency Vet",
      p7: "Lakeway Animal Clinic", p8: "Dripping Springs Equine", p9: "Pflugerville Veterinary Specialists",
      c1: "Roseville Animal Hospital", c2: "Elk Grove Pet Clinic", c3: "Davis Mixed Animal Practice", c4: "Folsom Veterinary Specialists",
      o1: "Winter Park Animal Hospital", o2: "Lake Mary Pet Clinic", o3: "Kissimmee Emergency Vet", o4: "Oviedo Mixed Practice",
      g1: "Marietta Animal Hospital", g2: "Decatur Veterinary Clinic", g3: "Alpharetta Veterinary Specialists", g4: "Peachtree Equine"
    };
    return NAMES[p.id] || p.area + " Veterinary";
  }

  stateOf(market) { return (market || "Austin, TX").split(", ")[1] || "TX"; }

  marketPanel(sel, selComm, comms, market) {
    const s = this.state;
    const c = selComm || comms[0] || { pop: 0, hh: 0, income: 0, growth: 0, pets: 0, vets: 0 };
    const per10k = c.hh ? (c.vets / (c.hh / 10000)) : 0;
    const incomeNat = 75149; // ACS 2023 U.S. median household income
    const incomeIdx = Math.round(((c.income - incomeNat) / incomeNat) * 100);
    const compLevel = per10k < 1.4 ? "Low" : per10k < 2.2 ? "Moderate" : "High";
    const compFill = per10k < 1.4 ? 1 : per10k < 2.2 ? 2 : 3;
    const score = Math.max(0, Math.min(100, Math.round(
      40 * Math.min(c.income / 140000, 1) + 35 * Math.min(c.growth / 40, 1) + 25 * Math.max(0, 1 - per10k / 3)
    )));
    const tone = (v) => (v ? "var(--vf-navy)" : "#8d99a6");

    return {
      name: this.practiceName(sel),
      place: sel.area + ", " + this.stateOf(market),
      priceLabel: this.money(sel.price),
      photos: (() => {
        const withPhoto = this.photoSet(sel).filter((ph) => ph.hasSrc);
        const n = withPhoto.length;
        const i = n ? ((s.mdPhoto || 0) % n + n) % n : 0;
        const cur = withPhoto[i];
        return {
          count: n,
          hasAny: n > 0,
          isEmpty: n === 0,
          multiple: n > 1,
          counter: n ? (i + 1) + "/" + n : "",
          currentSrc: cur ? cur.src : "",
          currentId: cur ? cur.id : "ph-" + sel.id + "-exterior",
          currentCaption: cur ? cur.caption : "",
          emptyId: "ph-" + sel.id + "-exterior",
          emptyHint: this.practiceName(sel) + " — exterior, street view",
          prev: () => this.setState({ mdPhoto: i - 1 }),
          next: () => this.setState({ mdPhoto: i + 1 }),
          dots: withPhoto.map((ph, j) => ({
            style: "width: " + (j === i ? "16px" : "6px") + "; height: 6px; border-radius: 999px; background: " +
              (j === i ? "var(--vf-navy)" : "rgba(255,255,255,.85)") + ";"
          }))
        };
      })(),
      tabs: [
        { key: "overview", label: "Overview" },
        { key: "insights", label: "Insights" },
        { key: "financials", label: "Financials" },
        { key: "property", label: "Property" },
        { key: "contact", label: "Contact" }
      ].map((t) => ({
        label: t.label,
        go: () => this.setState({ mdTab: t.key }),
        style: "font-family: var(--rf-display); flex: 1 1 auto; min-width: 0; font-size: 12px; font-weight: 500; padding: 10px 0; text-align: center; background: none; border: 0; cursor: pointer; white-space: nowrap; color: " +
          ((s.mdTab || "insights") === t.key ? "var(--vf-navy)" : "var(--vf-text)") + "; border-bottom: 2px solid " +
          ((s.mdTab || "insights") === t.key ? "var(--vf-accent)" : "transparent") + ";"
      })),
      isInsights: (s.mdTab || "insights") === "insights",
      isOther: (s.mdTab || "insights") !== "insights",
      otherTitle: ({ overview: "Overview", financials: "Financials", property: "Property", contact: "Contact" })[s.mdTab] || "Overview",
      goInsights: () => this.setState({ mdTab: "insights" }),
      overviewTiles: [
        { v: this.fmtMetric("households", c.pop), k: "Population", sub: (c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)" },
        { v: this.fmtMetric("households", c.hh), k: "Households", sub: "ACS 5-year" },
        { v: "$" + Math.round(c.income / 1000) + "K", k: "Median Income", sub: (incomeIdx > 0 ? "+" : "") + incomeIdx + "% vs US" },
        { v: this.fmtMetric("households", c.pets), k: "Est. Pet Households", sub: "derived estimate" }
      ],
      compEstab: String(c.vets),
      compPer10k: per10k.toFixed(1),
      compLevel: compLevel + " Competition",
      compBars: [1, 2, 3].map((i) => ({
        style: "flex: 1; height: 8px; border-radius: 2px; background: " + (i <= compFill ? "#4c9a6a" : "#dbe4ea") + ";"
      })),
      oppTiles: [
        { icon: "$", label: incomeIdx > 25 ? "High" : incomeIdx > 0 ? "Above avg." : "Median", sub: "Affluence", on: incomeIdx > 0 },
        { icon: "↗", label: c.growth > 20 ? "Strong" : c.growth > 8 ? "Steady" : "Flat", sub: "Population Growth", on: c.growth > 8 },
        { icon: "⌂", label: c.econ > 650000 ? "Strong" : c.econ > 450000 ? "Typical" : "Lean", sub: "Sector Payroll", on: c.econ > 450000 },
        { icon: "", label: "", sub: "", on: false }
      ].slice(0, 3).map((t) => ({
        icon: t.icon, label: t.label, sub: t.sub,
        iconStyle: "font-family: var(--rf-display); font-size: 15px; font-weight: 800; color: " + tone(t.on) + ";",
        labelStyle: "font-family: var(--rf-display); font-size: 13px; font-weight: 500; color: " + tone(t.on) + "; margin-top: 4px;"
      })),
      score: String(score),
      scoreLabel: score >= 75 ? "Attractive" : score >= 55 ? "Balanced" : "Challenging",
      scoreRing: "width: 46px; height: 46px; border-radius: 999px; display: grid; place-items: center; background: conic-gradient(#4c9a6a " +
        score + "%, #e6ecf1 0); font-family: var(--rf-display);",
      openListing: () => this.setState({ screen: "detail", detailId: sel.id })
    };
  }

  marketTotal() {
    const market = this.state.market || "Austin, TX";
    return P.filter((p) => p.market === market && p.status === "published").length;
  }

  activeFilterCount() {
    const f = this.state.f;
    return Object.keys(f).filter((k) => f[k] !== "Any").length;
  }

  filtered() {
    const f = this.state.f;
    const market = this.state.market || "Austin, TX";
    return P.filter((p) => {
      if (p.status !== "published") return false;
      if (p.market !== market) return false;
      if (f.type !== "Any" && p.type !== f.type) return false;
      if (f.doctors !== "Any" && p.docs < Number(f.doctors)) return false;
      if (f.building !== "Any" && p.bldg !== f.building) return false;
      if (f.price !== "Any") {
        const pr = p.price / 1000;
        if (f.price === "u500" && pr >= 500) return false;
        if (f.price === "500-1000" && (pr < 500 || pr > 1000)) return false;
        if (f.price === "1000-2000" && (pr < 1000 || pr > 2000)) return false;
        if (f.price === "o2000" && pr < 2000) return false;
      }
      if (f.est && f.est !== "Any") {
        if (f.est === "pre1995" && p.est >= 1995) return false;
        if (f.est === "1995-2010" && (p.est < 1995 || p.est > 2010)) return false;
        if (f.est === "post2010" && p.est <= 2010) return false;
      }
      if (f.ownership && f.ownership !== "Any") {
        const solo = /Sole proprietor/.test(p.ownership);
        if (f.ownership === "Sole" && !solo) return false;
        if (f.ownership === "Multi" && solo) return false;
      }
      if (f.sqft && f.sqft !== "Any") {
        if (f.sqft === "u3000" && p.sqft >= 3000) return false;
        if (f.sqft === "3000-5000" && (p.sqft < 3000 || p.sqft > 5000)) return false;
        if (f.sqft === "o5000" && p.sqft < 5000) return false;
      }
      if (f.revenue !== "Any") {
        const rv = p.rev / 1000;
        if (f.revenue === "u1000" && rv >= 1000) return false;
        if (f.revenue === "1000-2500" && (rv < 1000 || rv > 2500)) return false;
        if (f.revenue === "o2500" && rv < 2500) return false;
      }
      return true;
    });
  }

  statusPill(status) {
    const map = {
      published: ["Published", "#ffffff", "#003a70", "#003a70"],
      in_review: ["In VIN Foundation review", "#003a70", "#deecf7", "#deecf7"],
      draft: ["Draft", "#494949", "#f5f5f5", "#d4dde5"],
      paused: ["Paused", "#003a70", "#ffffff", "#339dde"],
      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"]
    };
    const m = map[status] || map.draft;
    return { label: m[0], style: "flex: none; font-size: 11.5px; font-weight: 500; padding: 5px 12px; border-radius: 999px; color: " + m[1] + "; background: " + m[2] + "; border: 1px solid " + m[3] + ";" };
  }

  setListingStatus(id, status) {
    this.setState((s) => ({ sellerListings: s.sellerListings.map((l) => (l.id === id ? Object.assign({}, l, { status, note: status === "paused" ? "Paused by you just now · hidden from search" : status === "withdrawn" ? "Withdrawn just now · no longer visible to buyers" : status === "published" ? "Live again · visible in search" : l.note }) : l)) }));
  }

  mobileVals(list) {
    const s = this.state;
    const tab = s.screen === "detail" ? "detail" : s.mobileTab;
    const peek = P.filter((x) => x.id === s.activeId)[0];
    const chip = (label, on) => ({
      label,
      style: "flex: none; font-size: 12px; font-weight: 500; padding: 6px 11px; border-radius: 999px; white-space: nowrap; color: " +
        (on ? "var(--color-navy)" : "var(--color-steel)") + "; background: " + (on ? "var(--rf-band)" : "var(--color-off-white)") +
        "; border: 1px solid " + (on ? "var(--color-blue)" : "var(--border-subtle)") + ";"
    });
    return {
      isList: tab === "list", isMap: tab === "map", isDetail: tab === "detail",
      zoom: 9,
      chips: [
        chip(s.f.type === "Any" ? "Any type" : s.f.type, s.f.type !== "Any"),
        chip(s.f.price === "Any" ? "Any price" : "Price set", s.f.price !== "Any"),
        chip(s.f.doctors === "Any" ? "Any size" : s.f.doctors + "+ doctors", s.f.doctors !== "Any"),
        chip("Property", s.f.building !== "Any")
      ],
      // Callout only on the phone: the map's own callout carries the practice, and tapping
      // a selected pin again opens the detail screen. No peek card competing for the
      // bottom of the screen with the market-data button.
      selectMarker: (id) => (s.activeId === id
        ? this.setState({ screen: "detail", detailId: id })
        : this.setState({ activeId: id })),
      sheetOpen: !!s.mobSheet,
      openSheet: () => this.setState({ mobSheet: true }),
      closeSheet: () => this.setState({ mobSheet: false }),
      layerLabel: s.mdValue === null ? "Market data" : (LAYER_META[s.mdValue === undefined ? "income" : s.mdValue] || {}).title || "Market data",
      resizeKey: s.screen + s.viewport + (s.mobSheet ? "-sheet" : "") + (s.mobileTab || ""),
      rowStyle: "display: flex; align-items: center; gap: 11px; width: 100%; min-height: 46px; padding: 12px 4px; text-align: left; font-size: 13.5px; font-weight: 500; color: var(--vf-navy); background: none; border: 0; border-bottom: 1px solid var(--rf-line); cursor: pointer;",
      datasetRowStyle: "display: flex; align-items: center; gap: 11px; width: 100%; min-height: 46px; padding: 12px 4px; text-align: left; background: none; border: 0; border-bottom: 1px solid var(--rf-line); cursor: pointer;",
      basemaps: [
        { key: "map", label: "Map" },
        { key: "satellite", label: "Satellite" }
      ].map((b) => ({
        label: b.label,
        go: () => this.setState({ mdBasemap: b.key }),
        style: "flex: 1; height: 46px; font-family: var(--rf-display); font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; color: " +
          ((s.mdBasemap || "map") === b.key ? "var(--vf-white)" : "var(--vf-navy)") + "; background: " +
          ((s.mdBasemap || "map") === b.key ? "var(--vf-navy)" : "var(--vf-white)") + "; border: 1px solid " +
          ((s.mdBasemap || "map") === b.key ? "var(--vf-navy)" : "var(--border-subtle)") + ";"
      })),
      toggle: [
        { key: "list", label: "List" },
        { key: "map", label: "Map" }
      ].map((t) => ({
        label: t.label,
        go: () => this.setState({ mobileTab: t.key, screen: "browse" }),
        style: "font-family: var(--rf-display); font-size: 12.5px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; padding: 8px 20px; border: 0; border-radius: 999px; cursor: pointer; color: " +
          (tab === t.key ? "var(--color-white)" : "var(--color-navy)") + "; background: " + (tab === t.key ? "var(--color-navy)" : "transparent") + ";"
      })),
      backLabel: tab === "detail" ? "Back to results" : "Filters",
      backStyle: "font-family: var(--rf-display); font-size: 12.5px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; padding: 9px 14px; border: 1px solid var(--border-subtle); border-radius: 999px; background: var(--color-white); color: var(--color-navy); cursor: pointer;",
      back: () => this.setState({ screen: "browse", mobileTab: "list" })
    };
  }

  adminVals() {
    const s = this.state;
    const tab = s.adminTab;
    const A = (label, tone) => ({
      label,
      go: () => {},
      style: "font-family: var(--rf-display); font-size: 12px; font-weight: 500; letter-spacing: .03em; text-transform: uppercase; padding: 7px 12px; border-radius: 6px; cursor: pointer; border: 1px solid " +
        (tone === "primary" ? "var(--color-blue)" : "var(--border-subtle)") + "; color: " +
        (tone === "primary" ? "var(--color-white)" : tone === "danger" ? "#494949" : "var(--color-navy)") + "; background: " +
        (tone === "primary" ? "var(--color-blue)" : "var(--color-white)") + ";"
    });
    const cell = (main, sub, pill, pillTone, actions) => {
      const tones = {
        ok: ["#ffffff", "#003a70", "#003a70"], warn: ["#003a70", "#deecf7", "#deecf7"],
        bad: ["#494949", "#ffffff", "#494949"], info: ["#003a70", "#ffffff", "#339dde"],
        mute: ["#494949", "#f5f5f5", "#d4dde5"]
      };
      const t = tones[pillTone] || tones.mute;
      return {
        hasMain: !!main, main: main || "", hasSub: !!sub, sub: sub || "",
        hasPill: !!pill, pill: pill || "",
        pillStyle: "display: inline-block; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: " + t[0] + "; background: " + t[1] + "; border: 1px solid " + t[2] + ";",
        hasActions: !!actions, actions: actions || []
      };
    };

    const sets = {
      users: {
        columns: ["Applicant", "Affiliation and intent", "Status", "Decision"],
        grid: "1.1fr 1.5fr .7fr 1fr",
        footnote: "Approval is a human decision. VIN membership is recorded but does not by itself grant access — the eligibility rule is an open question for the VIN Foundation. Revoking access hides all listings from that member immediately.",
        rows: [
          [cell("Dr. Priya Raghavan", "Texas A&M, 2016 · TX license"), cell("Associate, two-doctor practice", "\u201CLooking to buy within 18 months in Central Texas.\u201D"), cell(null, null, "Pending", "warn"), cell(null, null, null, null, [A("Approve", "primary"), A("Decline", "danger")])],
          [cell("Dr. Marcus Bell", "Colorado State, 2009 · TX, NM licenses"), cell("Owner, one practice", "\u201CSelling in 2027; want to see what listings look like.\u201D"), cell(null, null, "Pending", "warn"), cell(null, null, null, null, [A("Approve", "primary"), A("Decline", "danger")])],
          [cell("Dr. Alan Cho", "Ohio State, 2004 · TX license"), cell("Regional medical director, 14-hospital group", "Affiliation flagged: employer appears to be a consolidator."), cell(null, null, "Needs review", "bad"), cell(null, null, null, null, [A("Request info"), A("Decline", "danger")])],
          [cell("Dr. Rachel Mendes", "Texas A&M, 2014 · TX license"), cell("Relief veterinarian · StartUp Club", "Approved August 12 by staff reviewer K. Alvarez."), cell(null, null, "Approved", "ok"), cell(null, null, null, null, [A("Suspend"), A("Revoke", "danger")])]
        ]
      },
      listings: {
        columns: ["Listing", "Seller and figures", "Status", "Action"],
        grid: "1.2fr 1.4fr .8fr .9fr",
        footnote: "Listings stay invisible to buyers until a reviewer publishes them. Unpublishing is immediate and reversible; withdrawn listings keep their history for reporting but no longer appear in search.",
        rows: [
          [cell("Mixed practice — Bastrop", "Submitted September 1"), cell("Dr. Susan Ortiz", "$860K asking · $1.2M revenue · 2 doctors · building leased"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],
          [cell("Specialty practice — Pflugerville", "Submitted August 30"), cell("Dr. Nathan Weiss", "$2.65M asking · $3.8M revenue · 6 doctors · unit available separately"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],
          [cell("Small animal practice — Cedar Park", "Published August 24"), cell("Dr. James Whitfield", "$1.45M asking · 34 views · 2 requests"), cell(null, null, "Published", "ok"), cell(null, null, null, null, [A("Unpublish"), A("Edit")])],
          [cell("Small animal practice — Buda", "Paused by seller August 12"), cell("Dr. Helen Park", "$1.1M asking · hidden from search"), cell(null, null, "Paused", "info"), cell(null, null, null, null, [A("Contact seller")])],
          [cell("Small animal practice — Temple", "Flagged by two members"), cell("Unverified seller", "Figures appear copied from a broker listing; contact details in the description."), cell(null, null, "Flagged", "bad"), cell(null, null, null, null, [A("Investigate", "primary"), A("Unpublish", "danger")])]
        ]
      },
      activity: {
        columns: ["Request", "Practice", "Status", "Age"],
        grid: "1.2fr 1.3fr .8fr .8fr",
        footnote: "Staff can see that a request exists and whether it was answered. Message contents are visible only in an abuse investigation, and every such view is logged.",
        rows: [
          [cell("Dr. Rachel Mendes", "Asked for a phased transition plan"), cell("Small animal — Cedar Park", "Dr. James Whitfield"), cell(null, null, "Awaiting seller", "warn"), cell("6 days", "Reminder sent")],
          [cell("Dr. Rachel Mendes", "Asked for production by doctor"), cell("Small animal — Lakeway", "Dr. Ann Kessler"), cell(null, null, "Engaged", "ok"), cell("14 days", "Packet released")],
          [cell("Dr. Owen Sandoval", "Asked about overnight staffing"), cell("Emergency — East Austin", "Bright Star ER LLC"), cell(null, null, "Declined", "bad"), cell("21 days", "Under contract elsewhere")],
          [cell("Dr. Lisa Guerra", "Three requests in one day"), cell("Multiple listings", "Volume pattern flagged automatically"), cell(null, null, "Review", "info"), cell("2 days", "No action yet")]
        ]
      },
      data: {
        columns: ["Dataset", "Source and license", "Status", "Action"],
        grid: "1.1fr 1.6fr .8fr .8fr",
        footnote: "No dataset reaches production until its license is recorded here. Anything marked unresolved is excluded from listings and from the map until the VIN Foundation clears it.",
        rows: [
          [cell("Population, households, median income", "Refreshed annually"), cell("U.S. Census Bureau — ACS 5-year estimates", "Public domain. Attribution requested. Ingested via the Census API."), cell(null, null, "Cleared", "ok"), cell(null, null, null, null, [A("View terms")])],
          [cell("Base map and tiles", "Live tiles"), cell("OpenStreetMap contributors", "Open Database License. Attribution required and displayed on the map."), cell(null, null, "Cleared", "ok"), cell(null, null, null, null, [A("View terms")])],
          [cell("Address to coordinates", "On listing creation"), cell("Census Geocoder", "Public domain. No commercial restriction identified."), cell(null, null, "Cleared", "ok"), cell(null, null, null, null, [A("View terms")])],
          [cell("Pet ownership estimates", "Last checked June 2026"), cell("Industry survey (commercial)", "License unresolved — redistribution terms unclear. Excluded from listings pending review."), cell(null, null, "Unresolved", "bad"), cell(null, null, null, null, [A("Assign review", "primary")])],
          [cell("Veterinary practice locations", "Prior VetVision work"), cell("Mixed provenance", "Collection method not documented. Not ingested; needs a documented source before any competition view is built."), cell(null, null, "Blocked", "bad"), cell(null, null, null, null, [A("Open question")])]
        ]
      }
    };

    const set = sets[tab] || sets.users;
    return {
      tabs: [
        { key: "users", label: "Users", count: "3" },
        { key: "listings", label: "Listings", count: "3" },
        { key: "activity", label: "Requests", count: "2" },
        { key: "data", label: "Data Sources", count: "2" }
      ].map((t) => ({
        label: t.label, count: t.count,
        go: () => this.setState({ adminTab: t.key }),
        style: "font-family: var(--rf-display); display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 500; letter-spacing: .02em; padding: 12px 18px; border: 0; border-radius: 8px 8px 0 0; cursor: pointer; color: " +
          (tab === t.key ? "var(--color-navy)" : "#494949") + "; background: " + (tab === t.key ? "var(--color-white)" : "transparent") + ";",
        countStyle: "font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; color: var(--color-white); background: " + (tab === t.key ? "var(--color-blue)" : "#339dde") + ";"
      })),
      columns: set.columns,
      footnote: set.footnote,
      headStyle: "display: grid; grid-template-columns: " + set.grid + "; gap: 20px; padding: 13px 20px; background: var(--color-off-white); border-bottom: 1px solid var(--rf-line);",
      rows: set.rows.map((cells, i) => ({
        cells,
        style: "display: grid; grid-template-columns: " + set.grid + "; gap: 20px; align-items: center; padding: 16px 20px; border-bottom: " + (i === set.rows.length - 1 ? "0" : "1px solid var(--rf-line)") + ";"
      }))
    };
  }

  sellerVals() {
    const s = this.state;
    const isWizard = s.sellerView === "wizard";
    const inbox = s.requests.filter((r) => r.pid === "p1" || r.pid === "p7" || r.pid === "p6");
    return {
      isDash: !isWizard, isWizard: isWizard,
      heading: isWizard ? "Create a Listing" : "My Practice Listings",
      sub: isWizard ? "Eight short steps. Nothing is visible to buyers until you submit and the VIN Foundation approves." : "Publish, pause or withdraw a listing, and answer the buyers who ask about it.",
      listings: s.sellerListings.map((l) => {
        const pill = this.statusPill(l.status);
        const actions = [];
        if (l.status === "draft") actions.push({ label: "Continue", go: () => this.setState({ sellerView: "wizard", step: 1 }) });
        else actions.push({ label: "Edit", go: () => this.setState({ sellerView: "wizard", step: 1 }) });
        if (l.status === "published") {
          actions.push({ label: "Pause", go: () => this.setListingStatus(l.id, "paused") });
          actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: "p1" }) });
        }
        if (l.status === "paused") actions.push({ label: "Republish", go: () => this.setListingStatus(l.id, "published") });
        if (l.status !== "withdrawn" && l.status !== "draft") actions.push({ label: "Withdraw", go: () => this.setListingStatus(l.id, "withdrawn") });
        return { title: l.title, meta: l.meta, note: l.note, status: pill.label, pillStyle: pill.style, actions };
      }),
      inboxEmpty: inbox.length === 0,
      inbox: inbox.map((r) => {
        const p = P.filter((x) => x.id === r.pid)[0] || P[0];
        const label = r.status === "pending" ? "New" : r.status === "accepted" ? "Engaged" : "Declined";
        const tone = r.status === "pending" ? ["#003a70", "#deecf7", "#deecf7"] : r.status === "accepted" ? ["#ffffff", "#003a70", "#003a70"] : ["#494949", "#ffffff", "#494949"];
        return {
          buyer: r.buyer, meta: "Approved buyer · Texas license · asked about " + p.area,
          msg: "\u201C" + r.msg + "\u201D",
          statusLabel: label,
          pillStyle: "flex: none; font-size: 11.5px; font-weight: 500; padding: 5px 12px; border-radius: 999px; color: " + tone[0] + "; background: " + tone[1] + "; border: 1px solid " + tone[2] + ";",
          isPending: r.status === "pending", isResolved: r.status !== "pending",
          resolvedNote: r.status === "accepted" ? "You released the financial packet and floor plan to this buyer." : "You declined this request. The buyer was told you are not engaging further.",
          accept: () => this.setState((st) => ({ requests: st.requests.map((x) => (x.id === r.id ? Object.assign({}, x, { status: "accepted", reply: "Happy to share more. Financial packet unlocked." }) : x)) })),
          decline: () => this.setState((st) => ({ requests: st.requests.map((x) => (x.id === r.id ? Object.assign({}, x, { status: "declined", reply: "Not engaging further at this time. Thank you for reaching out." }) : x)) }))
        };
      })
    };
  }

  setW = (key) => (e) => {
    const v = e && e.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e;
    this.setState((s) => ({ w: Object.assign({}, s.w, { [key]: v }), wizErr: "" }));
  };

  wizardVals() {
    const s = this.state;
    const w = s.w;
    const step = s.step;
    const names = ["Practice basics", "Location and privacy", "Financials", "Practice details", "Property", "Photos and documents", "Disclosure settings", "Preview and submit"];
    const text = (key, label, hint, help) => ({ isText: true, isSelect: false, isArea: false, label, hint: hint || "", value: w[key], set: this.setW(key), hasHelp: !!help, help: help || "", wrapStyle: "display: flex; flex-direction: column; gap: 6px;" });
    const sel = (key, label, options, help) => ({ isText: false, isSelect: true, isArea: false, label, hint: "", value: w[key], set: this.setW(key), options: options.map((o) => ({ v: o, label: o })), hasHelp: !!help, help: help || "", wrapStyle: "display: flex; flex-direction: column; gap: 6px;" });
    const area = (key, label, hint) => ({ isText: false, isSelect: false, isArea: true, label, hint: hint || "", value: w[key], set: this.setW(key), hasHelp: false, help: "", wrapStyle: "display: flex; flex-direction: column; gap: 6px; grid-column: span 2;" });

    const byStep = {
      1: { blurb: "Start with what the practice is. You can change any of this before you submit.", fields: [text("name", "Practice name (staff-facing only)", "Hill Country Animal Hospital", "Never shown to buyers until you approve a request."), sel("type", "Practice type", ["Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other"]), text("est", "Year established", "1998"), sel("ownership", "Current ownership", ["Sole proprietor", "Two-doctor partnership", "Multi-doctor LLC", "Other"])], toggles: [] },
      2: { blurb: "Buyers search by location. You choose how precisely yours is shown.", fields: [text("city", "City or community", "Cedar Park"), text("zip", "ZIP code", "78613", "Used to place your practice on the map and to attach community data.")], toggles: [{ key: "anon", label: "Show only the community, not the street address", help: "Recommended while you are still operating. Buyers see \u201CCedar Park, TX\u201D and an approximate map pin." }] },
      3: { blurb: "Two numbers get a buyer to a decision. Everything else can wait for a conversation.", fields: [text("price", "Asking price", "1,450,000"), text("rev", "Gross revenue, most recent year", "2,100,000")], toggles: [{ key: "revBand", label: "Show revenue as a range instead of an exact figure", help: "Buyers see \u201C$2M \u2013 $2.5M\u201D. The exact figure is released only when you accept a request." }] },
      4: { blurb: "The practical picture: who works there and what you do.", fields: [text("docs", "Doctors (full-time equivalent)", "3"), text("rooms", "Exam rooms", "5"), text("sqft", "Approximate square feet", "4,200"), text("hours", "Hours", "Mon\u2013Fri 7:30\u20136, Sat 8\u20131"), area("desc", "Services offered", "Wellness, dentistry, soft-tissue surgery, in-house lab, digital radiography")], toggles: [] },
      5: { blurb: "Real estate is usually the second question a buyer asks.", fields: [sel("bldg", "Building status", ["Included", "Available separately", "Leased"]), sel("facilityType", "Facility type", ["Standalone", "Strip or plaza", "Medical park", "Other"]), area("facility", "Facility description", "Freestanding building on a 0.6-acre corner lot, remodeled 2019.")], toggles: [] },
      6: { blurb: "Photos do more than any other field to bring the right buyer to you.", fields: [], toggles: [] },
      7: { blurb: "You decide what an approved buyer sees before you have spoken to them.", fields: [], toggles: [
        { key: "anon", label: "Keep practice name and address hidden until I approve a buyer", help: "Your listing shows the practice type, community and figures you released." },
        { key: "revBand", label: "Release revenue as a range until I approve a buyer", help: "Exact revenue, tax returns and production reports stay locked." },
        { key: "docsLocked", label: "Keep floor plans and financial packet locked", help: "Buyers see the document titles and can ask for access." }
      ] }
    };

    const cfg = byStep[step] || byStep[1];
    const uploads = [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));

    return {
      isForm: !s.wizSubmitted && step <= 7,
      isPreview: !s.wizSubmitted && step === 8,
      isDone: s.wizSubmitted,
      title: names[step - 1],
      blurb: cfg.blurb,
      fields: cfg.fields,
      hasToggles: cfg.toggles.length > 0,
      toggles: cfg.toggles.map((t) => ({ label: t.label, help: t.help, on: !!w[t.key], toggle: this.setW(t.key) })),
      hasUpload: step === 6,
      uploads,
      addPhoto: () => this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) })),
      error: !!s.wizErr, errorText: s.wizErr,
      progressLabel: "Step " + step + " of 8",
      barStyle: "height: 100%; width: " + Math.round((step / 8) * 100) + "%; background: var(--color-blue); transition: width 300ms var(--easing-out);",
      steps: names.map((n, i) => ({
        n: String(i + 1), label: n, go: () => this.setState({ step: i + 1, wizErr: "" }),
        style: "display: flex; align-items: center; gap: 11px; padding: 9px 10px; text-align: left; font-family: var(--rf-display); font-size: 13.5px; font-weight: " + (step === i + 1 ? "600" : "400") + "; color: " + (step === i + 1 ? "var(--color-navy)" : "var(--color-steel)") + "; background: " + (step === i + 1 ? "var(--rf-band)" : "transparent") + "; border: 0; border-radius: 6px; cursor: pointer;",
        dotStyle: "flex: none; width: 22px; height: 22px; border-radius: 999px; display: grid; place-items: center; font-size: 11px; font-weight: 700; color: " + (step > i + 1 ? "var(--color-white)" : step === i + 1 ? "var(--color-white)" : "var(--color-steel)") + "; background: " + (step > i + 1 ? "var(--vf-navy)" : step === i + 1 ? "var(--color-blue)" : "var(--color-off-white)") + "; border: 1px solid " + (step >= i + 1 ? "transparent" : "var(--border-subtle)") + ";"
      })),
      saveNote: "Saved automatically",
      nextLabel: step === 7 ? "Preview listing" : "Continue",
      backStyle: "font-family: var(--rf-display); height: 48px; padding: 0 20px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: " + (step === 1 ? "var(--border-subtle)" : "var(--color-navy)") + "; background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: " + (step === 1 ? "default" : "pointer") + ";",
      back: () => this.setState({ step: Math.max(1, step - 1), wizErr: "" }),
      next: () => {
        if (step === 1 && (!w.name || !w.est)) return this.setState({ wizErr: "Practice name and year established are needed before you continue." });
        if (step === 2 && (!w.city || !w.zip)) return this.setState({ wizErr: "A city and ZIP code are needed to place your practice on the map." });
        if (step === 3 && (!w.price || (!w.rev && !w.revBand))) return this.setState({ wizErr: "Enter an asking price and either an exact revenue figure or choose the range option." });
        this.setState({ step: Math.min(8, step + 1), wizErr: "" });
      },
      previewTitle: (w.type || "Small animal") + " practice — " + (w.city || "Your community"),
      previewRows: [
        { k: "Practice type", v: w.type || "Small animal" },
        { k: "General location", v: (w.city || "\u2014") + (w.city ? ", TX" : "") },
        { k: "Established", v: w.est || "\u2014" },
        { k: "Asking price", v: w.price ? "$" + w.price : "\u2014" },
        { k: "Gross revenue", v: w.rev ? (w.revBand ? "Range shown to buyers" : "$" + w.rev) : "\u2014" },
        { k: "Doctors", v: w.docs || "\u2014" },
        { k: "Exam rooms", v: w.rooms || "\u2014" },
        { k: "Square feet", v: w.sqft || "\u2014" },
        { k: "Property", v: w.bldg === "Included" ? "Included in sale" : w.bldg === "Leased" ? "Leased" : "Available separately" },
        { k: "Photos attached", v: String(uploads.length) }
      ],
      previewNote: w.anon
        ? "Practice name and street address are hidden. Buyers see the community and an approximate map pin until you approve their request."
        : "Practice name and address are visible to every approved buyer. Turn on generalized location in step 7 if you are still operating.",
      submit: () => this.setState({ wizSubmitted: true, sellerListings: [{ id: "s" + Date.now(), title: ((w.type || "Small animal") + " practice — " + (w.city || "New listing")), meta: (w.price ? "$" + w.price : "Price to be set") + " · " + (w.docs || "?") + " doctors", status: "in_review", note: "Submitted just now · awaiting VIN Foundation review" }].concat(this.state.sellerListings) })
    };
  }

  detail() {
    const s = this.state;
    const p = P.filter((x) => x.id === s.detailId)[0] || P[0];
    const sent = s.sent.indexOf(p.id) > -1 || s.requests.some((r) => r.pid === p.id);
    const req = s.requests.filter((r) => r.pid === p.id)[0];
    const unlocked = req && req.status === "accepted";
    const bldg = p.bldg === "Included" ? "Included in sale" : p.bldg === "Separate" ? "Available separately" : "Leased — assignable";
    const docIcon = (open) =>
      "flex: none; width: 30px; height: 30px; border-radius: 6px; display: grid; place-items: center; color: " +
      (open ? "var(--color-blue)" : "var(--color-steel)") + "; background: " + (open ? "var(--rf-band)" : "var(--color-off-white)") + ";";
    const pill = (open) =>
      "flex: none; font-size: 11.5px; font-weight: 500; padding: 4px 11px; border-radius: 999px; color: " +
      (open ? "#003a70" : "var(--color-steel)") + "; background: " + (open ? "#deecf7" : "var(--color-off-white)") +
      "; border: 1px solid " + (open ? "#339dde" : "var(--border-subtle)") + ";";
    return {
      title: p.type + " practice — " + p.area,
      subtitle: p.area + ", TX · Established " + p.est,
      listed: p.listed,
      statusLabel: "Accepting inquiries",
      priceLabel: this.money(p.price),
      priceNote: "Practice only. " + bldg.toLowerCase() + ".",
      morePhotos: "+6 more photos",
      photos: this.photoSet(p),
      photoHeroId: "ph-" + p.id + "-exterior",
      photoHeroHint: this.practiceName(p) + " — exterior, street view",
      canRequest: !sent,
      alreadySent: sent,
      sentLabel: unlocked ? "Seller accepted your request" : req && req.status === "declined" ? "Seller declined this request" : "Request sent — awaiting the seller",
      sentNote: unlocked ? "Financial packet and floor plans are now open to you." : req && req.status === "declined" ? "The seller is not engaging further on this listing." : "Sellers usually respond within a week.",
      disclosure: "This seller is still operating the practice. Street address, practice name and staff names stay hidden until they approve your request. " +
        (unlocked ? "You have been granted access to the full financial packet." : "Documents marked locked open only with seller approval."),
      hasDemo: p.id !== "p8",
      noDemo: p.id === "p8",
      demo: [
        { k: "Population", v: p.pop, sub: "Community, 2023" },
        { k: "Growth", v: p.growth.replace(" since 2015", ""), sub: "Since 2015" },
        { k: "Median income", v: p.income, sub: "Household, 2023" },
        { k: "Households", v: p.hh.replace(" households", ""), sub: "In the community" }
      ],
      keyFacts: [
        { k: "Gross revenue", v: this.money(p.rev) + " (seller-stated)" },
        { k: "Doctors", v: p.docs + " full-time equivalent" },
        { k: "Exam rooms", v: String(p.rooms) },
        { k: "Square feet", v: p.sqft.toLocaleString() },
        { k: "Property", v: bldg }
      ],
      docs: [
        { name: "Exterior and interior photos", meta: "9 images · seller-provided", pill: "Open to approved members", pillStyle: pill(true), iconStyle: docIcon(true), isOpen: true, isLocked: false },
        { name: "Floor plan", meta: "PDF · 1 page", pill: unlocked ? "Open to you" : "Locked — seller approval", pillStyle: pill(unlocked), iconStyle: docIcon(unlocked), isOpen: !!unlocked, isLocked: !unlocked },
        { name: "Three-year financial summary", meta: "PDF · seller-prepared, unverified", pill: unlocked ? "Open to you" : "Locked — seller approval", pillStyle: pill(unlocked), iconStyle: docIcon(unlocked), isOpen: !!unlocked, isLocked: !unlocked },
        { name: "Equipment list", meta: "Spreadsheet · seller-provided", pill: unlocked ? "Open to you" : "Locked — seller approval", pillStyle: pill(unlocked), iconStyle: docIcon(unlocked), isOpen: !!unlocked, isLocked: !unlocked }
      ],
      sections: [
        {
          title: "Overview", hasProse: true, prose: p.note, hasNote: false, note: "",
          rows: [
            { k: "Practice type", v: p.type },
            { k: "General location", v: p.area + ", TX" },
            { k: "Established", v: String(p.est) },
            { k: "Ownership structure", v: p.ownership }
          ]
        },
        {
          title: "Financial Snapshot", hasProse: false, prose: "",
          hasNote: true, note: "All figures on this listing are provided by the seller and have not been reviewed or verified by the VIN Foundation. Ask for the financial packet before relying on any number here.",
          rows: [
            { k: "Asking price", v: this.money(p.price) },
            { k: "Gross revenue (most recent year)", v: this.money(p.rev) },
            { k: "Revenue disclosure", v: "Exact figure released" },
            { k: "Real estate", v: bldg }
          ]
        },
        {
          title: "The Practice", hasProse: true, prose: p.services + ".", hasNote: false, note: "",
          rows: [
            { k: "Doctors", v: p.docs + " FTE" },
            { k: "Support team", v: p.staff },
            { k: "Exam rooms", v: String(p.rooms) },
            { k: "Hours", v: p.hours }
          ]
        },
        {
          title: "Property", hasProse: true, prose: p.facility, hasNote: false, note: "",
          rows: [
            { k: "Building status", v: bldg },
            { k: "Facility type", v: p.bldg === "Leased" ? "Leased suite" : "Standalone building" },
            { k: "Approximate square feet", v: p.sqft.toLocaleString() },
            { k: "Parking", v: "On-site" }
          ]
        }
      ]
    };
  }

  renderVals() {
    const s = this.state;
    const list = this.filtered();
    const vw = s.vw || (typeof window !== "undefined" ? window.innerWidth : 1440);
    const nav = [
      { key: "browse", label: "Browse Practices" },
      { key: "requests", label: "My Requests" },
      { key: "seller", label: "List a Practice" },
      { key: "admin", label: "VIN Foundation Admin" }
    ].map((n) => ({
      label: n.label,
      go: this.go(n.key),
      goMenu: () => { this.setState({ navMenu: false }); this.go(n.key)(); },
      menuStyle: "display: block; width: 100%; padding: 11px 15px; text-align: left; font-family: var(--rf-display); font-size: 13.5px; font-weight: 500; background: none; border: 0; cursor: pointer; white-space: nowrap; color: " +
        (s.screen === n.key ? "var(--color-blue)" : "var(--color-navy)") + ";",
      style: "font-family: var(--rf-display); flex: none; white-space: nowrap; font-size: 15px; font-weight: 500; color: " +
        (s.screen === n.key ? "var(--color-blue)" : "var(--color-navy)") +
        "; background: none; border: 0; padding: 4px 0; cursor: pointer; border-bottom: 2px solid " +
        (s.screen === n.key ? "var(--color-blue)" : "transparent") + ";"
    }));

    const jumps = ["gate", "browse", "detail", "requests", "seller", "admin"].map((k) => ({
      label: k === "gate" ? "Access" : k === "detail" ? "Listing" : k.charAt(0).toUpperCase() + k.slice(1),
      go: this.jumpTo(k),
      style: "font-size: 11px; font-weight: 500; color: #fff; background: rgba(255,255,255," +
        (s.screen === k ? ".3" : ".1") + "); border: 1px solid rgba(255,255,255,.16); border-radius: 3px; padding: 3px 8px; cursor: pointer;"
    }));

    const statusMap = {
      pending: {
        kicker: "Application received", title: "Your request is under review",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "VIN Foundation staff review each request by hand, usually within two business days. You will get an email the moment a decision is made. Nothing else is needed from you right now.",
        meta: [{ k: "Submitted", v: "September 2, 2026" }, { k: "Reviewer", v: "VIN Foundation staff" }, { k: "Typical decision time", v: "1–2 business days" }],
        primary: { label: "Return to sign in", go: () => this.setState({ gate: "signin" }) }
      },
      rejected: {
        kicker: "Decision", title: "Access was not granted",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "Your request could not be approved as submitted. The most common reason is an affiliation the VIN Foundation could not confirm. You may reply with additional information and ask for a second review.",
        meta: [{ k: "Reviewed", v: "August 30, 2026" }, { k: "Reason given", v: "Affiliation not verified" }, { k: "Appeal window", v: "Open" }],
        primary: { label: "Reply with more information", go: () => this.setState({ gate: "apply" }) }
      }
    };

    return {
      showPrototypeBar: this.props.prototypeBar !== false,
      isDesktop: s.viewport === "desktop",
      viewportLabel: s.viewport === "desktop" ? "Mobile view" : "Desktop view",
      toggleViewport: () => this.setState({ viewport: s.viewport === "desktop" ? "mobile" : "desktop" }),
      nav, jumps,
      navExpanded: !!s.auth && vw >= 1050,
      navCollapsed: !!s.auth && vw < 1050,
      navMenuOpen: !!s.navMenu,
      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false }),
      subBrandStyle: "width: 1px; height: 30px; background: var(--rf-line); display: " + (vw < 1050 ? "none" : "block") + ";",
      subBrandTextStyle: "font-family: var(--rf-display); font-size: 15px; font-weight: 800; letter-spacing: -.005em; color: var(--color-blue); white-space: nowrap; display: " +
        (vw < 1050 ? "none" : "block") + ";",
      identityStyle: "line-height: 1.25; display: " + (vw < 1180 ? "none" : "block") + ";",
      me: Object.assign({ email: s.email }, s.me),
      userMenuOpen: !!s.userMenu,
      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu }),
      signOut: () => this.setState({
        userMenu: false, auth: false, screen: "gate", gate: "signin", pw: "············",
        interest: "closed", activeId: null, hoverId: null, sellerView: "dash", wizSubmitted: false, formError: ""
      }),
      goHome: this.go("gate"),
      showGate: s.screen === "gate",
      gateSignin: s.screen === "gate" && s.gate === "signin",
      gateApply: s.screen === "gate" && s.gate === "apply",
      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected"),
      status: statusMap[s.gate] || statusMap.pending,
      gatePoints: [
        { n: "1", title: "Approved members only", body: "The VIN Foundation reviews every applicant. Corporate groups and consolidators are not admitted." },
        { n: "2", title: "Sellers control disclosure", body: "General location by default. Financial packets and floor plans open only when the seller says yes." },
        { n: "3", title: "One clear next step", body: "Buyers express interest; sellers decide whether to engage. No brokers in the middle." }
      ],
      form: { email: s.email, pw: s.pw, error: !!s.formError, errorText: s.formError },
      setEmail: (e) => this.setState({ email: e.target.value, formError: "" }),
      setPw: (e) => this.setState({ pw: e.target.value, formError: "" }),
      signIn: () => {
        if (!s.email || !s.pw) return this.setState({ formError: "Enter both your VIN username and password." });
        this.setState({ screen: "browse", formError: "", auth: true });
      },
      signedIn: !!s.auth,
      signedOut: !s.auth,
      goSignInScreen: () => this.setState({ screen: "gate", gate: "signin" }),
      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: "apply" }); },
      goSignin: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signin", screen: "gate" }); },
      gateStates: [
        { label: "Pending approval", go: () => this.setState({ gate: "pending" }) },
        { label: "Request declined", go: () => this.setState({ gate: "rejected" }) },
        { label: "Approved — enter", go: () => this.setState({ screen: "browse", auth: true }) }
      ],
      apply: s.apply,
      applyFields: [
        { key: "name", label: "Full name and credentials", hint: "Jane Doe, DVM" },
        { key: "vin", label: "VIN member ID (if you have one)", hint: "Optional" },
        { key: "grad", label: "Veterinary school and graduation year", hint: "Texas A&M, 2014" },
        { key: "state", label: "License state", hint: "TX" },
        { key: "employer", label: "Current practice or employer", hint: "Where you work now" }
      ].map((a) => ({
        label: a.label, hint: a.hint, value: s.apply[a.key],
        set: (e) => this.setState((st) => ({ apply: Object.assign({}, st.apply, { [a.key]: e.target.value, error: "" }) }))
      })),
      setIntent: (e) => this.setState((st) => ({ apply: Object.assign({}, st.apply, { intent: e.target.value, error: "" }) })),
      toggleAffirm: () => this.setState((st) => ({ apply: Object.assign({}, st.apply, { affirm: !st.apply.affirm }) })),
      submitApply: () => {
        const a = s.apply;
        if (!a.name || !a.grad || !a.intent) {
          return this.setState({ apply: Object.assign({}, a, { error: "Name, school and year, and a short note about your intent are required." }) });
        }
        this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });
      },
      resultCount: list.length,

      isBrowse: false,
      market: s.market || "Austin, TX",
      marketOptions: Object.keys(MARKETS).map((m) => ({ v: m, label: m + " metro" })),
      setMarket: (e) => this.setState({ market: e.target.value, activeId: null, hoverId: null, loading: true }, () => {
        clearTimeout(this._t);
        this._t = setTimeout(() => this.setState({ loading: false }), 320);
      }),
      marketLabel: (s.market || "Austin, TX") + " metro · within 40 miles",
      emptyNote: this.marketTotal() + " practices are listed in the " + (s.market || "Austin, TX") + " metro. Widening the price or revenue range usually brings results back.",
      mapCenter: MARKETS[s.market || "Austin, TX"].center,
      mapZoom: MARKETS[s.market || "Austin, TX"].zoom,
      place: s.place == null ? "Austin, TX metro" : s.place,
      setPlace: (e) => this.setState({ place: e.target.value }),
      loading: s.loading,
      skeletons: [1, 2, 3],
      showResults: !s.loading && list.length > 0,
      isEmpty: !s.loading && list.length === 0,
      resultHeadline: list.length + (list.length === 1 ? " practice available" : " practices available"),
      filterSummary: this.activeFilterCount() === 0 ? "No filters applied" : this.activeFilterCount() + " filter" + (this.activeFilterCount() === 1 ? "" : "s") + " applied",
      clearStyle: "font-family: var(--rf-display); height: 40px; padding: 0 14px; font-size: 13px; font-weight: 500; color: " +
        (this.activeFilterCount() ? "var(--color-blue)" : "var(--border-subtle)") +
        "; background: none; border: 0; border-radius: 6px; cursor: " + (this.activeFilterCount() ? "pointer" : "default") + ";",
      clearFilters: () => this.setState({ f: { type: "Any", price: "Any", revenue: "Any", doctors: "Any", building: "Any", est: "Any", ownership: "Any", sqft: "Any" } }),
      moreOpen: !!s.moreFilters,
      toggleMore: () => this.setState({ moreFilters: !s.moreFilters }),
      moreCount: ["est", "ownership", "sqft"].filter((k) => s.f[k] && s.f[k] !== "Any").length,
      hasMoreCount: ["est", "ownership", "sqft"].some((k) => s.f[k] && s.f[k] !== "Any"),
      moreBtnStyle: "display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 15px; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; color: var(--vf-navy); background: " +
        (s.moreFilters ? "var(--vf-accent-bg)" : "var(--vf-white)") + "; border: 1px solid " +
        (s.moreFilters || ["est", "ownership", "sqft"].some((k) => s.f[k] && s.f[k] !== "Any") ? "var(--vf-accent)" : "var(--border-subtle)") + ";",
      moreCaretStyle: "opacity: .45; transition: transform 150ms var(--easing-out);" + (s.moreFilters ? " transform: rotate(180deg);" : ""),
      moreFilters: [
        { key: "est", label: "Year established", options: [["Any", "Any year"], ["pre1995", "Before 1995"], ["1995-2010", "1995 – 2010"], ["post2010", "After 2010"]] },
        { key: "ownership", label: "Ownership structure", options: [["Any", "Any structure"], ["Sole", "Sole proprietor"], ["Multi", "Partnership or multi-doctor"]] },
        { key: "sqft", label: "Facility size", options: [["Any", "Any size"], ["u3000", "Under 3,000 sq ft"], ["3000-5000", "3,000 – 5,000 sq ft"], ["o5000", "Over 5,000 sq ft"]] }
      ].map((fl) => ({
        label: fl.label,
        value: s.f[fl.key] || "Any",
        set: this.setF(fl.key),
        options: fl.options.map((o) => ({ v: o[0], label: o[1] }))
      })),
      filters: [
        { key: "type", options: [["Any", "Practice type: Any"], ["Small animal", "Small animal"], ["Mixed", "Mixed"], ["Large animal", "Large animal"], ["Emergency", "Emergency"], ["Specialty", "Specialty"]] },
        { key: "price", options: [["Any", "Asking price: Any"], ["u500", "Under $500K"], ["500-1000", "$500K – $1M"], ["1000-2000", "$1M – $2M"], ["o2000", "$2M and up"]] },
        { key: "revenue", options: [["Any", "Gross revenue: Any"], ["u1000", "Under $1M"], ["1000-2500", "$1M – $2.5M"], ["o2500", "$2.5M and up"]] },
        { key: "doctors", options: [["Any", "Doctors: Any"], ["1", "1 or more"], ["2", "2 or more"], ["4", "4 or more"]] },
        { key: "building", options: [["Any", "Property: Any"], ["Included", "Building included"], ["Separate", "Building available separately"], ["Leased", "Building leased"]] }
      ].map((fl) => ({
        value: s.f[fl.key],
        set: this.setF(fl.key),
        options: fl.options.map((o) => ({ v: o[0], label: o[1] })),
        style: "height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: " +
          (s.f[fl.key] === "Any" ? "var(--color-white)" : "var(--rf-band)") + "; border: 1px solid " +
          (s.f[fl.key] === "Any" ? "var(--border-subtle)" : "var(--color-blue)") + "; border-radius: 6px; cursor: pointer;"
      })),
      results: list.map((p) => ({
        area: p.area, type: p.type, docs: p.docs, rooms: p.rooms, listed: p.listed,
        priceLabel: this.money(p.price),
        revLabel: this.money(p.rev),
        sqftLabel: p.sqft.toLocaleString(),
        bldgLabel: p.bldg === "Included" ? "Building included in sale" : p.bldg === "Separate" ? "Building available separately" : "Building leased",
        photoLabel: "Exterior",
        photoId: "ph-" + p.id + "-exterior",
        photoSrc: this.heroSrc(p),
        hasPhotoSrc: !!this.heroSrc(p),
        noPhotoSrc: !this.heroSrc(p),
        // Open the practice detail (John's ruling, 2026-09-07; C13 left no peek card to select into).
        open: () => this.setState({ screen: "detail", detailId: p.id }),
        hover: () => this.setState({ hoverId: p.id }),
        unhover: () => this.setState({ hoverId: null }),
        cardStyle: "background: var(--color-white); border: 1px solid " +
          (s.hoverId === p.id || s.activeId === p.id ? "var(--color-blue)" : "var(--rf-line)") +
          "; border-radius: 10px; box-shadow: " + (s.hoverId === p.id ? "var(--shadow-lg)" : "var(--shadow-sm)") +
          "; cursor: pointer; transition: box-shadow 300ms var(--easing-out), transform 300ms var(--easing-out), border-color 150ms linear; animation: rf-fade-up 300ms var(--easing-out) both;"
      })),
      markers: list.map((p) => ({ id: p.id, lat: p.lat, lng: p.lng, priceLabel: this.money(p.price) })),
      activeId: s.activeId, hoverId: s.hoverId,
      resizeKey: s.screen + s.viewport,

      isDetail: s.screen === "detail",
      backToBrowse: () => this.setState({ screen: "browse" }),
      d: this.detail(),
      interestOpen: s.interest !== "closed",
      interestMsg: s.interestMsg,
      setInterestMsg: (e) => this.setState({ interestMsg: e.target.value }),
      openInterest: () => this.setState({ interest: "form", interestMsg: "" }),
      closeInterest: () => this.setState({ interest: "closed" }),
      goRequests: () => this.setState({ screen: "requests", interest: "closed" }),
      sendInterest: () => {
        if (!s.interestMsg.trim()) return this.setState({ interest: "error" });
        const p = P.filter((x) => x.id === s.detailId)[0];
        this.setState({
          interest: "sent",
          sent: s.sent.concat([s.detailId]),
          requests: [{ id: "n" + Date.now(), pid: s.detailId, buyer: s.me.name, status: "pending", when: "Today", msg: s.interestMsg }].concat(s.requests)
        });
      },
      modal: {
        isForm: s.interest === "form" || s.interest === "error",
        isSent: s.interest === "sent",
        error: s.interest === "error",
        title: s.interest === "sent" ? "Request sent" : "Request information",
        sub: s.interest === "sent" ? "The seller has been notified." : (this.detail().subtitle || ""),
        shared: [
          { k: "Shared with seller", v: s.me.name },
          { k: "License state", v: "Texas" },
          { k: "VIN Foundation status", v: "Approved buyer" }
        ]
      },

      isRequests: s.screen === "requests",
      noRequests: s.requests.length === 0,
      goBrowseBtn: this.go("browse"),
      reqList: s.requests.map((r) => {
        const p = P.filter((x) => x.id === r.pid)[0] || P[0];
        const label = r.status === "pending" ? "Awaiting seller" : r.status === "accepted" ? "Seller engaged" : "Declined";
        const tone = r.status === "pending" ? ["#003a70", "#deecf7", "#deecf7"] : r.status === "accepted" ? ["#ffffff", "#003a70", "#003a70"] : ["#494949", "#ffffff", "#494949"];
        return {
          title: p.type + " practice — " + p.area,
          meta: this.money(p.price) + " · " + p.docs + " doctors · " + p.sqft.toLocaleString() + " sq ft",
          msg: "\u201C" + r.msg + "\u201D",
          reply: r.reply || "", hasReply: !!r.reply,
          statusLabel: label, when: r.when,
          hint: r.status === "pending" ? "The seller has not responded yet. Nothing further is disclosed until they do." :
                r.status === "accepted" ? "Financial packet and floor plan are open to you on this listing." :
                "This seller is not engaging further. The listing may already be under contract.",
          pillStyle: "display: inline-block; font-size: 11.5px; font-weight: 500; padding: 5px 12px; border-radius: 999px; color: " + tone[0] + "; background: " + tone[1] + "; border: 1px solid " + tone[2] + ";",
          open: () => this.setState({ screen: "detail", detailId: p.id })
        };
      }),

      isSeller: s.screen === "seller",
      startWizard: () => this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, wizErr: "" }),
      exitWizard: () => this.setState({ sellerView: "dash", wizSubmitted: false }),
      seller: this.sellerVals(),
      wiz: this.wizardVals(),
      isAdmin: s.screen === "admin",
      admin: this.adminVals(),
      isMobile: s.viewport === "mobile",
      mob: this.mobileVals(list),
      md: this.marketVals(list)
    };
  }
}

export { Component };
