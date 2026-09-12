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
  growth: { label: "Population Growth (ACS)", short: "Projected growth (5 yrs)", unit: "pct", buckets: ["Declining", "0–5%", "5–15%", "> 15%"], stops: [0, 5, 15] },
  households: { label: "Households (ACS)", short: "Total households", unit: "count", buckets: ["< 10K", "10K–25K", "25K–45K", "> 45K"], stops: [10000, 25000, 45000] },
  econ: { label: "Average Practice Payroll (CBP)", short: "Avg. payroll per practice", unit: "usd", buckets: ["< $450K", "$450–650K", "$650–900K", "> $900K"], stops: [450000, 650000, 900000] },
  competition: { label: "Veterinary Establishments (CBP)", short: "Vet establishments", unit: "count", buckets: ["1–2", "3–5", "6–9", "10+"], stops: [3, 6, 10] }
};

// Rates and medians belong to the area → choropleth fill (one at a time: two
// translucent fills mix into a third colour that means nothing).
const FILL_KEYS = ["income", "growth", "econ", "households", "pets", "competition"];
// A24 (D-C35): each fill layer draws at the geography its figure is honest at, and the
// legend names it. `households` and `pets` joined income at the tract on 2026-09-12 and
// `competition` at the ZCTA (D-L1): they were graduated symbols at the listing point on the
// grounds that city-scale class breaks on small areas produce a picture with no information,
// which was true of the BREAKS and not of the geography - `AREA_LAYERS` below cuts them at
// the scale the map paints. `competition` is the one ZIP-area layer, and it is honest there
// rather than approximate: ZIP Code Business Patterns is published per ZIP code and exists
// at no other geography, so the ZCTA is where it was measured.
const AREA_LEVEL = { income: "140", growth: "160", econ: "050", households: "140", pets: "140", competition: "860" };
const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County", households: "Census tract", pets: "Census tract", competition: "ZIP Code Tabulation Area" };
// D-NS16 (John, 2026-09-10): a polygon with no usable figure is drawn in a neutral class
// and never omitted - a hole in a choropleth reads as a boundary, not as an absence. The
// colour is the design's own --border-subtle value at the same fillOpacity every other
// class uses, so this adds no style vocabulary. Grey means UNMEASURED and only that: a
// figure that WAS measured but whose margin spans a band is shown with its value (D-C36).
const NO_DATA_FILL = "#e6e6e6";
const NO_DATA_LABEL = "No data";
// A24 (D-L1): the CHOROPLETH's own class breaks, for the three layers whose figure is a
// COUNT and therefore means something different at a different geography. `VALUE_LAYERS`
// classes what the community cards carry (a city's households); these class what the map
// paints (a tract's). Measured over every US tract and every US ZIP area, not over Austin:
// households p25/p50/p75 = 1,054 / 1,446 / 1,897 across 85,381 tracts, pets the same times
// 0.57, competition p50/p75/p90 = 4 / 6 / 8 across 4,720 ZIP areas carrying a count. The
// design's own breaks put 100.0 % of tracts and 73.1 % of ZIP areas into ONE class.
// Income, growth and payroll are scale-invariant and are deliberately absent.
const AREA_LAYERS = {
  households: { buckets: ["< 1,000", "1,000–1,500", "1,500–2,000", "> 2,000"], stops: [1000, 1500, 2000] },
  pets: { buckets: ["< 600", "600–850", "850–1,100", "> 1,100"], stops: [600, 850, 1100] },
  competition: { buckets: ["3", "4–5", "6–9", "10+"], stops: [4, 6, 10] }
};
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

// A24 (D-C50 interim): the source line, composed for the surface that prints it. A layer
// whose line names a GEOGRAPHY carries the dataset alone (`dataset:`) and is given the basis
// by its caller - the map's own geography for the legend and the tip, the practice-area label
// for the snapshot strip, whose figures are per-listing and are not measured at either. A
// layer that names no geography (`growth`, `econ`, `pets`) keeps its own `source` sentence,
// which is true on both surfaces, and this returns it unchanged.
const metaSource = (k, basis) => {
  const m = LAYER_META[k] || {};
  return m.dataset ? m.dataset + " · " + basis : (m.source || "");
};

// One catalogue per market layer: what it is, where it comes from, and how to read it.
// "derived" marks metrics that are modelled rather than observed.
const LAYER_META = {
  income: {
    title: "Median household income",
    sub: "Household income by community · ACS 5-year",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    dataset: "U.S. Census ACS 5-year estimates (2023)",
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
    sub: "Veterinary establishments · ZIP Code Business Patterns, NAICS 541940",
    updated: "Updated: ZIP Code Business Patterns 2022",
    dataset: "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940",
    means: "Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.",
    why: "Competitive density helps you judge whether a market is underserved or already crowded."
  },
  growth: {
    title: "Population growth",
    sub: "Change · ACS population estimates",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    source: "U.S. Census ACS population estimates, 2015–2023 · community level",
    means: "Growth describes how fast an area's population changed. Past growth is not a forecast.",
    why: "Areas adding households may add pet owners, which matters more for a practice you intend to hold for years."
  },
  households: {
    title: "Households",
    sub: "Total households · ACS 5-year",
    updated: "Updated: ACS 2023 release (Jan 2025)",
    dataset: "U.S. Census ACS 5-year estimates (2023)",
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


// MS1: the FIRST number in the string and nothing after it, sign included. Stripping every
// character but digits and a dot loses a leading minus and glues on whatever number follows
// the figure — "-1.5% since 2018" became "1.52018", which the snapshot strip then reported as
// "+1.5%" and `bucket` classed as growth. Zero for a null or for a string carrying no number
// at all is the design’s own contract and is kept.
const num = (s) => { const m = s == null ? null : String(s).match(/[-+]?\d[\d,]*(?:\.\d+)?/); return m ? Number(m[0].replace(/,/g, "")) || 0 : 0; };

// SUBSTITUTIONS — the VIN icon set ships no heart or check glyph. Per the design system's
// iconography rule (no unicode glyphs as icons) these are closest-match filled silhouettes
// matched to the set's heavy/filled weight. Swap in authentic assets when VIN provides them.
class Component extends DCLogic {
  state = {
    screen: "gate", gate: "signin", auth: false, viewport: "desktop", mobileTab: "list",
    email: "", pw: "", formError: "", formNotice: "", gateToken: "",
    signup: { email: "", pw: "", error: "" }, forgot: { email: "", error: "" }, reset: { pw: "", pw2: "", error: "" }, invite: { pw: "", pw2: "", error: "" }, answer: { text: "", error: "", applicationId: "", note: "" },
    apply: { name: "", vin: "", grad: "", state: "", employer: "", intent: "", affirm: false, error: "" },
    f: { type: "Any", price: "Any", revenue: "Any", doctors: "Any", building: "Any" },
    loading: false, activeId: null, hoverId: null, detailId: "p1", detailDocs: false,
    interest: "closed", interestMsg: "", sent: [],
    lightbox: null, lightboxFocus: false,
    step: 1, wizErr: "", wizSubmitted: false, wizAssets: [], creating: false,
    w: { name: "", type: "Small animal", est: "", city: "", zip: "", anon: true, price: "", rev: "", revBand: false, docs: "", rooms: "", sqft: "", bldg: "Included", facility: "", desc: "", photos: 0, ownership: "Sole proprietor", hours: "", facilityType: "Standalone", docsLocked: true },
    areas: {"050":{"features":[{"geometry":{"coordinates":[[[-97.63921,30.07829],[-97.49268,30.20995],[-97.36949,30.41964],[-97.19891,30.33745],[-97.08183,30.25936],[-97.02446,30.05144],[-97.31582,29.78654],[-97.64937,30.06794],[-97.63921,30.07829]]],"type":"Polygon"},"id":"48021","properties":{"c":[30.10361,-97.31202],"geo_id":"48021","name":"Bastrop County"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89929,29.85781],[-97.8939,29.88373],[-97.79244,29.94518],[-97.7607,29.98812],[-97.65369,30.07156],[-97.31582,29.78654],[-97.5977,29.63074],[-97.60373,29.64179],[-97.6175,29.63355],[-97.61748,29.6451],[-97.62943,29.63978],[-97.63102,29.65347],[-97.65165,29.65396],[-97.65261,29.66784],[-97.6805,29.66362],[-97.6907,29.6731],[-97.69851,29.66699],[-97.70456,29.68262],[-97.72185,29.68209],[-97.73572,29.6912],[-97.74363,29.6975],[-97.73837,29.7129],[-97.76846,29.7191],[-97.7586,29.72505],[-97.78204,29.7477],[-97.78092,29.75926],[-97.80342,29.75365],[-97.80019,29.76593],[-97.81714,29.79038],[-97.82926,29.7796],[-97.83026,29.79553],[-97.84636,29.80865],[-97.83669,29.82691],[-97.84664,29.84167],[-97.87601,29.86056],[-97.89929,29.85781]]],"type":"Polygon"},"id":"48055","properties":{"c":[29.83683,-97.61992],"geo_id":"48055","name":"Caldwell County"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.29417,30.0468],[-98.17298,30.35631],[-97.70879,30.02345],[-97.7607,29.98812],[-97.79259,29.94506],[-97.8939,29.88373],[-97.89929,29.85781],[-97.87526,29.85821],[-97.94444,29.80699],[-97.99927,29.75244],[-98.03052,29.84854],[-98.2976,30.03799],[-98.29417,30.0468]]],"type":"Polygon"},"id":"48209","properties":{"c":[30.05789,-98.03116],"geo_id":"48209","name":"Hays County"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.15927,30.37665],[-98.09771,30.46763],[-98.09778,30.49806],[-98.11372,30.48558],[-98.12313,30.48704],[-98.04989,30.62416],[-98.0365,30.61173],[-98.01274,30.61677],[-98.00628,30.62752],[-97.9924,30.60949],[-97.95673,30.62825],[-97.91706,30.60487],[-97.9219,30.59096],[-97.91512,30.58057],[-97.92698,30.56765],[-97.90246,30.57133],[-97.86787,30.5465],[-97.87142,30.52271],[-97.85576,30.5074],[-97.86225,30.49731],[-97.84654,30.47341],[-97.81194,30.44707],[-97.77939,30.4384],[-97.77634,30.42977],[-97.75364,30.43329],[-97.7468,30.44935],[-97.68878,30.4614],[-97.68289,30.48007],[-97.65144,30.47489],[-97.60683,30.49031],[-97.59616,30.50148],[-97.56826,30.49972],[-97.54608,30.47542],[-97.52397,30.47218],[-97.51086,30.48526],[-97.45978,30.45832],[-97.43411,30.45972],[-97.41525,30.43834],[-97.39303,30.43877],[-97.38339,30.42415],[-97.36954,30.41956],[-97.49268,30.20995],[-97.64937,30.06794],[-97.65369,30.07156],[-97.70879,30.02345],[-98.17298,30.35631],[-98.15927,30.37665]]],"type":"Polygon"},"id":"48453","properties":{"c":[30.33438,-97.78196],"geo_id":"48453","name":"Travis County"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04989,30.62416],[-97.96286,30.78564],[-97.8281,30.90441],[-97.62405,30.87],[-97.26995,30.73536],[-97.15522,30.45734],[-97.33446,30.40284],[-97.37677,30.4192],[-97.39303,30.43877],[-97.41525,30.43834],[-97.43411,30.45972],[-97.45978,30.45832],[-97.51086,30.48526],[-97.52397,30.47218],[-97.54608,30.47542],[-97.56826,30.49972],[-97.59616,30.50148],[-97.60683,30.49031],[-97.65144,30.47489],[-97.68289,30.48007],[-97.68878,30.4614],[-97.7468,30.44935],[-97.75364,30.43329],[-97.77634,30.42977],[-97.77939,30.4384],[-97.81194,30.44707],[-97.84654,30.47341],[-97.86225,30.49731],[-97.85576,30.5074],[-97.87142,30.52271],[-97.86787,30.5465],[-97.90246,30.57133],[-97.92698,30.56765],[-97.91512,30.58057],[-97.9219,30.59096],[-97.91706,30.60487],[-97.95673,30.62825],[-97.9924,30.60949],[-98.00628,30.62752],[-98.01274,30.61677],[-98.0365,30.61173],[-98.04989,30.62416]]],"type":"Polygon"},"id":"48491","properties":{"c":[30.64752,-97.60042],"geo_id":"48491","name":"Williamson County"},"type":"Feature"}],"type":"FeatureCollection"},"140":{"features":[{"geometry":{"coordinates":[[[-97.49125,30.21211],[-97.41396,30.34436],[-97.38912,30.34178],[-97.39547,30.33081],[-97.37539,30.31102],[-97.35808,30.32238],[-97.32797,30.26551],[-97.33298,30.25625],[-97.32662,30.25475],[-97.33881,30.23824],[-97.32953,30.2332],[-97.33153,30.2258],[-97.34786,30.21647],[-97.34629,30.20175],[-97.35896,30.18756],[-97.34695,30.16976],[-97.37948,30.16167],[-97.38502,30.16505],[-97.37778,30.18204],[-97.39889,30.18698],[-97.39708,30.17172],[-97.44376,30.14257],[-97.45273,30.15258],[-97.42273,30.18663],[-97.47311,30.18361],[-97.48541,30.19011],[-97.48361,30.20612],[-97.49125,30.21211]]],"type":"Polygon"},"id":"48021950101","properties":{"c":[30.24228,-97.40417],"geo_id":"48021950101","name":"Census Tract 9501.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.37723,30.40709],[-97.36949,30.41964],[-97.19891,30.33745],[-97.13628,30.29567],[-97.19486,30.26942],[-97.17408,30.25134],[-97.18297,30.2427],[-97.21532,30.24282],[-97.25648,30.29321],[-97.29695,30.30481],[-97.29605,30.28828],[-97.32797,30.26551],[-97.35808,30.32238],[-97.34014,30.33425],[-97.35497,30.36894],[-97.34894,30.38064],[-97.38318,30.39684],[-97.37723,30.40709]]],"type":"Polygon"},"id":"48021950102","properties":{"c":[30.3245,-97.26798],"geo_id":"48021950102","name":"Census Tract 9501.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.37421,30.36376],[-97.37062,30.39092],[-97.34894,30.38064],[-97.35497,30.36894],[-97.34014,30.33425],[-97.36526,30.31766],[-97.37421,30.36376]]],"type":"Polygon"},"id":"48021950201","properties":{"c":[30.35254,-97.35899],"geo_id":"48021950201","name":"Census Tract 9502.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.40984,30.35139],[-97.38318,30.39684],[-97.37062,30.39092],[-97.37456,30.36065],[-97.36526,30.31766],[-97.37539,30.31102],[-97.39547,30.33081],[-97.38912,30.34178],[-97.40708,30.34099],[-97.41396,30.34436],[-97.40984,30.35139]]],"type":"Polygon"},"id":"48021950202","properties":{"c":[30.35455,-97.38443],"geo_id":"48021950202","name":"Census Tract 9502.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.52647,30.17919],[-97.49125,30.21211],[-97.48361,30.20612],[-97.48541,30.19011],[-97.47311,30.18361],[-97.42818,30.19076],[-97.4245,30.18212],[-97.45273,30.15258],[-97.44067,30.14237],[-97.39708,30.17172],[-97.40071,30.18615],[-97.38002,30.18328],[-97.38444,30.16397],[-97.34845,30.1678],[-97.34994,30.14815],[-97.37325,30.15263],[-97.35847,30.12558],[-97.33719,30.12217],[-97.32281,30.10996],[-97.41263,30.11147],[-97.52647,30.17919]]],"type":"Polygon"},"id":"48021950301","properties":{"c":[30.15311,-97.42835],"geo_id":"48021950301","name":"Census Tract 9503.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.43321,30.00357],[-97.42506,30.03245],[-97.37302,30.11105],[-97.35017,30.11128],[-97.3523,30.10188],[-97.33936,30.10213],[-97.33915,30.09308],[-97.34948,30.08911],[-97.34596,30.07644],[-97.3187,30.08079],[-97.29229,30.06406],[-97.28023,30.07297],[-97.26819,30.06298],[-97.2804,30.02549],[-97.31434,30.04509],[-97.3146,30.02302],[-97.32927,30.01171],[-97.32378,30.0034],[-97.33664,30.00554],[-97.33308,29.99175],[-97.35323,29.95465],[-97.42191,29.98234],[-97.43321,30.00357]]],"type":"Polygon"},"id":"48021950302","properties":{"c":[30.03372,-97.36175],"geo_id":"48021950302","name":"Census Tract 9503.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.568,30.14146],[-97.52923,30.17652],[-97.41263,30.11147],[-97.37311,30.10907],[-97.42506,30.03245],[-97.43321,30.00357],[-97.44124,30.02473],[-97.48966,30.06745],[-97.49272,30.08719],[-97.48056,30.091],[-97.49431,30.10737],[-97.50527,30.0975],[-97.53206,30.1266],[-97.568,30.14146]]],"type":"Polygon"},"id":"48021950303","properties":{"c":[30.10045,-97.46477],"geo_id":"48021950303","name":"Census Tract 9503.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.34266,30.11092],[-97.32281,30.10996],[-97.34239,30.1241],[-97.33137,30.15236],[-97.32067,30.13761],[-97.30612,30.14534],[-97.28275,30.14426],[-97.2849,30.13037],[-97.2782,30.11989],[-97.27125,30.12144],[-97.27432,30.0989],[-97.34266,30.11092]]],"type":"Polygon"},"id":"48021950401","properties":{"c":[30.12427,-97.30815],"geo_id":"48021950401","name":"Census Tract 9504.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.31183,30.07615],[-97.29544,30.08137],[-97.29083,30.1043],[-97.27432,30.0989],[-97.2769,30.07094],[-97.29229,30.06406],[-97.31183,30.07615]]],"type":"Polygon"},"id":"48021950402","properties":{"c":[30.08318,-97.28952],"geo_id":"48021950402","name":"Census Tract 9504.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.35017,30.11128],[-97.29083,30.1043],[-97.29544,30.08137],[-97.34596,30.07644],[-97.34948,30.08911],[-97.33915,30.09308],[-97.33936,30.10213],[-97.3523,30.10188],[-97.35017,30.11128]]],"type":"Polygon"},"id":"48021950403","properties":{"c":[30.09286,-97.32232],"geo_id":"48021950403","name":"Census Tract 9504.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.2827,30.03085],[-97.26719,30.05929],[-97.27951,30.07791],[-97.27125,30.12144],[-97.27659,30.1212],[-97.17434,30.17875],[-97.14327,30.21302],[-97.07353,30.22953],[-97.04821,30.13795],[-97.1307,30.13559],[-97.18441,30.11338],[-97.20069,30.08732],[-97.19766,30.07939],[-97.21919,30.06815],[-97.22846,30.04659],[-97.22259,30.0396],[-97.20254,30.05257],[-97.20263,30.03298],[-97.21075,30.02366],[-97.22893,30.02792],[-97.23377,30.01641],[-97.24778,30.01042],[-97.24588,30.02607],[-97.27378,30.02244],[-97.2827,30.03085]]],"type":"Polygon"},"id":"48021950503","properties":{"c":[30.13191,-97.17484],"geo_id":"48021950503","name":"Census Tract 9505.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.30356,30.14723],[-97.28256,30.17279],[-97.25307,30.1784],[-97.24172,30.16765],[-97.22374,30.17266],[-97.21815,30.17901],[-97.2309,30.19833],[-97.21288,30.20762],[-97.22039,30.23123],[-97.20964,30.24008],[-97.21532,30.24282],[-97.18297,30.2427],[-97.17408,30.25134],[-97.19486,30.26942],[-97.18669,30.27691],[-97.15577,30.28214],[-97.15454,30.29],[-97.13628,30.29567],[-97.08183,30.25936],[-97.07353,30.22953],[-97.14327,30.21302],[-97.17434,30.17875],[-97.2782,30.11989],[-97.28275,30.14426],[-97.30356,30.14723]]],"type":"Polygon"},"id":"48021950504","properties":{"c":[30.21711,-97.17727],"geo_id":"48021950504","name":"Census Tract 9505.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.32751,30.26615],[-97.29605,30.28828],[-97.29695,30.30481],[-97.24726,30.28614],[-97.22263,30.24772],[-97.20964,30.24008],[-97.22039,30.23123],[-97.21288,30.20762],[-97.2309,30.19833],[-97.21815,30.17901],[-97.24172,30.16765],[-97.25163,30.1782],[-97.2844,30.17178],[-97.30632,30.18471],[-97.29618,30.21457],[-97.3146,30.21305],[-97.32751,30.26615]]],"type":"Polygon"},"id":"48021950505","properties":{"c":[30.23321,-97.26829],"geo_id":"48021950505","name":"Census Tract 9505.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.37325,30.15263],[-97.3522,30.14716],[-97.34601,30.15422],[-97.34845,30.1678],[-97.35412,30.16743],[-97.34564,30.17151],[-97.35896,30.18756],[-97.34629,30.20175],[-97.34786,30.21647],[-97.33098,30.22719],[-97.33881,30.23824],[-97.32812,30.24756],[-97.32797,30.26551],[-97.3146,30.21305],[-97.29618,30.21457],[-97.30632,30.18471],[-97.28268,30.17494],[-97.31118,30.13775],[-97.32067,30.13761],[-97.33137,30.15236],[-97.34202,30.12249],[-97.35847,30.12558],[-97.37325,30.15263]]],"type":"Polygon"},"id":"48021950506","properties":{"c":[30.18045,-97.32759],"geo_id":"48021950506","name":"Census Tract 9505.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.45372,29.91704],[-97.41864,29.88991],[-97.39914,29.901],[-97.37526,29.93496],[-97.35123,29.94055],[-97.35262,29.96605],[-97.33936,29.9748],[-97.33664,30.00554],[-97.32378,30.0034],[-97.32927,30.01171],[-97.3146,30.02302],[-97.31434,30.04509],[-97.27378,30.02244],[-97.24588,30.02607],[-97.24778,30.01042],[-97.23377,30.01641],[-97.22893,30.02792],[-97.21217,30.02078],[-97.19029,30.02477],[-97.18952,30.01205],[-97.17572,30.00334],[-97.18492,29.98746],[-97.1674,29.99772],[-97.16734,29.98113],[-97.15967,29.98219],[-97.13458,29.99292],[-97.13536,30.00492],[-97.10718,29.97523],[-97.31582,29.78654],[-97.45993,29.90778],[-97.45372,29.91704]]],"type":"Polygon"},"id":"48021950601","properties":{"c":[29.92314,-97.27905],"geo_id":"48021950601","name":"Census Tract 9506.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.22846,30.04659],[-97.21919,30.06815],[-97.19766,30.07939],[-97.20069,30.08732],[-97.18441,30.11338],[-97.1307,30.13559],[-97.07932,30.13761],[-97.04821,30.13795],[-97.02446,30.05144],[-97.10718,29.97523],[-97.12418,29.98889],[-97.13507,30.01273],[-97.1767,30.04413],[-97.20313,30.0547],[-97.22259,30.0396],[-97.22846,30.04659]]],"type":"Polygon"},"id":"48021950602","properties":{"c":[30.06882,-97.11203],"geo_id":"48021950602","name":"Census Tract 9506.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.21412,30.02369],[-97.20263,30.03298],[-97.20313,30.0547],[-97.13507,30.01273],[-97.13458,29.99292],[-97.16734,29.98113],[-97.17132,29.9977],[-97.18434,29.98716],[-97.17572,30.00334],[-97.18952,30.01205],[-97.18819,30.02401],[-97.21412,30.02369]]],"type":"Polygon"},"id":"48021950700","properties":{"c":[30.01755,-97.17096],"geo_id":"48021950700","name":"Census Tract 9507"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.60975,30.10345],[-97.568,30.14146],[-97.53206,30.1266],[-97.51061,30.10743],[-97.51686,30.10126],[-97.55121,30.11549],[-97.55896,30.10642],[-97.57806,30.11601],[-97.60096,30.09584],[-97.60975,30.10345]]],"type":"Polygon"},"id":"48021950803","properties":{"c":[30.11864,-97.55978],"geo_id":"48021950803","name":"Census Tract 9508.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.60096,30.09584],[-97.57806,30.11601],[-97.55896,30.10642],[-97.55121,30.11549],[-97.51686,30.10126],[-97.51061,30.10743],[-97.50527,30.0975],[-97.49431,30.10737],[-97.48056,30.091],[-97.49272,30.08719],[-97.48966,30.06745],[-97.43398,30.0112],[-97.45069,29.96057],[-97.49594,29.98583],[-97.54055,30.02343],[-97.54239,30.04625],[-97.60096,30.09584]]],"type":"Polygon"},"id":"48021950804","properties":{"c":[30.04503,-97.50791],"geo_id":"48021950804","name":"Census Tract 9508.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63921,30.07829],[-97.60924,30.10249],[-97.54239,30.04625],[-97.53784,30.02115],[-97.55335,30.00724],[-97.56225,30.01198],[-97.57312,30.00291],[-97.64937,30.06794],[-97.63921,30.07829]]],"type":"Polygon"},"id":"48021950805","properties":{"c":[30.05202,-97.5903],"geo_id":"48021950805","name":"Census Tract 9508.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57173,30.00409],[-97.56225,30.01198],[-97.55335,30.00724],[-97.53784,30.02115],[-97.49594,29.98583],[-97.45069,29.96057],[-97.43321,30.00357],[-97.42191,29.98234],[-97.35323,29.95465],[-97.35123,29.94055],[-97.37526,29.93496],[-97.39914,29.901],[-97.41864,29.88991],[-97.4537,29.91831],[-97.45993,29.90778],[-97.57173,30.00409]]],"type":"Polygon"},"id":"48021950806","properties":{"c":[29.95444,-97.45351],"geo_id":"48021950806","name":"Census Tract 9508.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76422,29.88019],[-97.72031,29.8834],[-97.70948,29.86894],[-97.71448,29.86179],[-97.6708,29.8264],[-97.64714,29.83742],[-97.65838,29.85624],[-97.61624,29.85045],[-97.61928,29.87027],[-97.65504,29.89616],[-97.62875,29.91563],[-97.59608,29.927],[-97.57754,29.95752],[-97.54888,29.98278],[-97.3854,29.84493],[-97.3959,29.82783],[-97.47038,29.85502],[-97.52618,29.85259],[-97.6053,29.76627],[-97.61772,29.78531],[-97.64575,29.79609],[-97.65567,29.7836],[-97.68148,29.77554],[-97.69548,29.80347],[-97.71737,29.81873],[-97.73289,29.81989],[-97.72741,29.83143],[-97.75392,29.85727],[-97.76422,29.88019]]],"type":"Polygon"},"id":"48055960102","properties":{"c":[29.86824,-97.57558],"geo_id":"48055960102","name":"Census Tract 9601.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68921,30.03989],[-97.65369,30.07156],[-97.54888,29.98278],[-97.57754,29.95752],[-97.59608,29.927],[-97.65577,29.89631],[-97.67753,29.92358],[-97.67248,29.94062],[-97.68921,30.03989]]],"type":"Polygon"},"id":"48055960103","properties":{"c":[29.98365,-97.63255],"geo_id":"48055960103","name":"Census Tract 9601.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82291,29.93163],[-97.79244,29.94518],[-97.7607,29.98812],[-97.69008,30.03912],[-97.67248,29.94062],[-97.67753,29.92358],[-97.72618,29.91462],[-97.7347,29.90641],[-97.72696,29.88472],[-97.7441,29.88418],[-97.77977,29.90352],[-97.79775,29.92362],[-97.82291,29.93163]]],"type":"Polygon"},"id":"48055960104","properties":{"c":[29.95347,-97.73232],"geo_id":"48055960104","name":"Census Tract 9601.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70186,29.85482],[-97.66886,29.87221],[-97.66925,29.88434],[-97.65504,29.89616],[-97.61521,29.8652],[-97.61624,29.85045],[-97.65838,29.85624],[-97.64714,29.83742],[-97.6676,29.82653],[-97.70186,29.85482]]],"type":"Polygon"},"id":"48055960200","properties":{"c":[29.86143,-97.65669],"geo_id":"48055960200","name":"Census Tract 9602"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72696,29.88472],[-97.66943,29.88519],[-97.6675,29.87622],[-97.70186,29.85482],[-97.71448,29.86179],[-97.71079,29.87287],[-97.72696,29.88472]]],"type":"Polygon"},"id":"48055960300","properties":{"c":[29.87278,-97.69474],"geo_id":"48055960300","name":"Census Tract 9603"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7347,29.90641],[-97.72618,29.91462],[-97.67492,29.92436],[-97.67238,29.91174],[-97.65504,29.89616],[-97.66925,29.88434],[-97.72696,29.88472],[-97.7347,29.90641]]],"type":"Polygon"},"id":"48055960400","properties":{"c":[29.90029,-97.6953],"geo_id":"48055960400","name":"Census Tract 9604"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89929,29.85781],[-97.8939,29.88373],[-97.85752,29.9103],[-97.82569,29.87855],[-97.81522,29.87303],[-97.80773,29.8783],[-97.80267,29.87315],[-97.81158,29.86297],[-97.79966,29.85921],[-97.78682,29.83878],[-97.79657,29.83327],[-97.79934,29.80652],[-97.82185,29.82093],[-97.8348,29.81186],[-97.83439,29.79465],[-97.84636,29.80865],[-97.83669,29.82691],[-97.84664,29.84167],[-97.87601,29.86056],[-97.89929,29.85781]]],"type":"Polygon"},"id":"48055960501","properties":{"c":[29.85736,-97.84049],"geo_id":"48055960501","name":"Census Tract 9605.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84918,29.916],[-97.81752,29.93197],[-97.74849,29.88904],[-97.74315,29.88416],[-97.76422,29.88019],[-97.75392,29.85727],[-97.72741,29.83143],[-97.73289,29.81989],[-97.71737,29.81873],[-97.69548,29.80347],[-97.67936,29.76979],[-97.76336,29.71304],[-97.76833,29.72027],[-97.7586,29.72505],[-97.78204,29.7477],[-97.78092,29.75926],[-97.80342,29.75365],[-97.80019,29.76593],[-97.81714,29.79038],[-97.82765,29.77925],[-97.83237,29.7845],[-97.8348,29.81186],[-97.82185,29.82093],[-97.80372,29.80403],[-97.79628,29.83387],[-97.78682,29.83878],[-97.79966,29.85921],[-97.81158,29.86297],[-97.80267,29.87315],[-97.80773,29.8783],[-97.81522,29.87303],[-97.82569,29.87855],[-97.85752,29.9103],[-97.84918,29.916]]],"type":"Polygon"},"id":"48055960502","properties":{"c":[29.81854,-97.76821],"geo_id":"48055960502","name":"Census Tract 9605.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75429,29.71875],[-97.70563,29.74688],[-97.67936,29.76979],[-97.68148,29.77554],[-97.65567,29.7836],[-97.64575,29.79609],[-97.61772,29.78531],[-97.60367,29.76706],[-97.52618,29.85259],[-97.50265,29.85652],[-97.47038,29.85502],[-97.3959,29.82783],[-97.3854,29.84493],[-97.31582,29.78654],[-97.5977,29.63074],[-97.59545,29.6484],[-97.62918,29.6795],[-97.62423,29.68463],[-97.64348,29.71471],[-97.65578,29.71932],[-97.65588,29.70768],[-97.67932,29.71939],[-97.6796,29.68628],[-97.66521,29.66804],[-97.67347,29.6632],[-97.6907,29.6731],[-97.70223,29.66859],[-97.70456,29.68262],[-97.72185,29.68209],[-97.73572,29.6912],[-97.74363,29.6975],[-97.73677,29.71105],[-97.75429,29.71875]]],"type":"Polygon"},"id":"48055960600","properties":{"c":[29.75411,-97.53062],"geo_id":"48055960600","name":"Census Tract 9606"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68014,29.70678],[-97.67932,29.71939],[-97.65588,29.70768],[-97.65578,29.71932],[-97.64348,29.71471],[-97.62482,29.67644],[-97.6772,29.67954],[-97.68014,29.70678]]],"type":"Polygon"},"id":"48055960701","properties":{"c":[29.69611,-97.65552],"geo_id":"48055960701","name":"Census Tract 9607.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6772,29.67954],[-97.62482,29.67644],[-97.59924,29.6552],[-97.59579,29.63358],[-97.60373,29.64179],[-97.61846,29.63381],[-97.61748,29.6451],[-97.62943,29.63978],[-97.63102,29.65347],[-97.65165,29.65396],[-97.65261,29.66784],[-97.65865,29.66325],[-97.6772,29.67954]]],"type":"Polygon"},"id":"48055960702","properties":{"c":[29.66125,-97.63184],"geo_id":"48055960702","name":"Census Tract 9607.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.95584,29.87888],[-97.94716,29.88548],[-97.93411,29.88903],[-97.94635,29.87272],[-97.95584,29.87888]]],"type":"Polygon"},"id":"48209010100","properties":{"c":[29.88007,-97.94606],"geo_id":"48209010100","name":"Census Tract 101"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.95553,29.89018],[-97.94713,29.8983],[-97.9345,29.88896],[-97.9485,29.88434],[-97.95553,29.89018]]],"type":"Polygon"},"id":"48209010200","properties":{"c":[29.89016,-97.94576],"geo_id":"48209010200","name":"Census Tract 102"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.9356,29.88387],[-97.89615,29.87065],[-97.89677,29.85708],[-97.92173,29.85827],[-97.9356,29.88387]]],"type":"Polygon"},"id":"48209010302","properties":{"c":[29.87017,-97.91504],"geo_id":"48209010302","name":"Census Tract 103.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92182,29.88252],[-97.90946,29.89601],[-97.89017,29.90076],[-97.88112,29.89341],[-97.8939,29.88373],[-97.89615,29.87065],[-97.92182,29.88252]]],"type":"Polygon"},"id":"48209010305","properties":{"c":[29.88709,-97.90107],"geo_id":"48209010305","name":"Census Tract 103.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90946,29.89601],[-97.88026,29.94695],[-97.84918,29.916],[-97.88112,29.89341],[-97.89017,29.90076],[-97.90946,29.89601]]],"type":"Polygon"},"id":"48209010306","properties":{"c":[29.91557,-97.87914],"geo_id":"48209010306","name":"Census Tract 103.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.93581,29.88637],[-97.92635,29.89219],[-97.91225,29.89302],[-97.92182,29.88252],[-97.93581,29.88637]]],"type":"Polygon"},"id":"48209010307","properties":{"c":[29.88846,-97.92435],"geo_id":"48209010307","name":"Census Tract 103.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92494,29.89332],[-97.91887,29.89916],[-97.9126,29.89382],[-97.92467,29.8924],[-97.92494,29.89332]]],"type":"Polygon"},"id":"48209010308","properties":{"c":[29.89494,-97.91899],"geo_id":"48209010308","name":"Census Tract 103.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.91887,29.89916],[-97.90185,29.93312],[-97.88446,29.95047],[-97.88026,29.94695],[-97.90239,29.90422],[-97.91225,29.89302],[-97.91887,29.89916]]],"type":"Polygon"},"id":"48209010309","properties":{"c":[29.92125,-97.89987],"geo_id":"48209010309","name":"Census Tract 103.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.9531,29.85682],[-97.93168,29.87478],[-97.92173,29.85827],[-97.89677,29.85708],[-97.91374,29.84221],[-97.93614,29.86085],[-97.94064,29.84609],[-97.9531,29.85682]]],"type":"Polygon"},"id":"48209010401","properties":{"c":[29.85676,-97.92708],"geo_id":"48209010401","name":"Census Tract 104.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.01504,29.80106],[-97.9531,29.85682],[-97.94064,29.84609],[-97.93614,29.86085],[-97.91374,29.84221],[-97.88608,29.8621],[-97.87456,29.8595],[-97.94444,29.80699],[-97.99927,29.75244],[-98.01504,29.80106]]],"type":"Polygon"},"id":"48209010402","properties":{"c":[29.81487,-97.96149],"geo_id":"48209010402","name":"Census Tract 104.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.01866,29.81218],[-97.96162,29.86886],[-97.9352,29.8825],[-97.93168,29.87478],[-98.01504,29.80106],[-98.01866,29.81218]]],"type":"Polygon"},"id":"48209010500","properties":{"c":[29.8442,-97.97524],"geo_id":"48209010500","name":"Census Tract 105"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.9679,29.88078],[-97.96436,29.89616],[-97.9485,29.88434],[-97.95824,29.87124],[-97.9679,29.88078]]],"type":"Polygon"},"id":"48209010601","properties":{"c":[29.88454,-97.95965],"geo_id":"48209010601","name":"Census Tract 106.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.07078,29.87979],[-98.03517,29.8896],[-98.03851,29.87979],[-98.02643,29.88955],[-98.01047,29.87275],[-97.98799,29.87703],[-97.96232,29.86778],[-98.01866,29.81218],[-98.03052,29.84854],[-98.07078,29.87979]]],"type":"Polygon"},"id":"48209010602","properties":{"c":[29.85805,-98.01387],"geo_id":"48209010602","name":"Census Tract 106.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.14972,29.93446],[-98.08546,29.94026],[-98.05062,29.91675],[-97.96436,29.89616],[-97.96892,29.87988],[-97.95719,29.87368],[-97.96232,29.86778],[-97.98799,29.87703],[-98.01047,29.87275],[-98.02643,29.88955],[-98.03851,29.87979],[-98.03517,29.8896],[-98.07153,29.87773],[-98.14972,29.93446]]],"type":"Polygon"},"id":"48209010603","properties":{"c":[29.90432,-98.05378],"geo_id":"48209010603","name":"Census Tract 106.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.02255,29.98495],[-98.00741,29.98789],[-98.00393,29.99965],[-97.99639,29.99406],[-97.9657,30.01198],[-97.95414,30.0043],[-97.93747,30.01313],[-97.91873,29.98794],[-97.91884,29.97374],[-97.90397,29.97687],[-97.90656,29.94311],[-97.89551,29.93698],[-97.91161,29.9059],[-97.92593,29.89925],[-97.96108,29.94922],[-98.00141,29.98124],[-98.01086,29.97593],[-98.02255,29.98495]]],"type":"Polygon"},"id":"48209010702","properties":{"c":[29.9648,-97.94663],"geo_id":"48209010702","name":"Census Tract 107.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.96426,29.89663],[-97.95826,29.90933],[-97.94647,29.9134],[-97.94799,29.90771],[-97.93009,29.90571],[-97.92184,29.89659],[-97.9345,29.88896],[-97.94713,29.8983],[-97.95553,29.89018],[-97.96426,29.89663]]],"type":"Polygon"},"id":"48209010703","properties":{"c":[29.89972,-97.94416],"geo_id":"48209010703","name":"Census Tract 107.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04434,29.96106],[-98.03616,29.98755],[-98.01086,29.97593],[-98.00141,29.98124],[-97.96108,29.94922],[-97.93009,29.90571],[-97.94052,29.90404],[-97.95077,29.91294],[-97.96436,29.89616],[-98.00901,29.90873],[-98.00856,29.92856],[-98.04434,29.96106]]],"type":"Polygon"},"id":"48209010704","properties":{"c":[29.94005,-97.9915],"geo_id":"48209010704","name":"Census Tract 107.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.10059,30.08637],[-98.08831,30.11798],[-98.0875,30.19157],[-97.99739,30.19684],[-98.00878,30.15347],[-97.98599,30.14685],[-98.0114,30.13137],[-98.03197,30.13186],[-98.04112,30.1168],[-98.07641,30.11246],[-98.07902,30.09265],[-98.09228,30.08021],[-98.10059,30.08637]]],"type":"Polygon"},"id":"48209010806","properties":{"c":[30.15296,-98.04982],"geo_id":"48209010806","name":"Census Tract 108.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.27084,30.10674],[-98.23676,30.1935],[-98.1648,30.19763],[-98.14245,30.20678],[-98.0875,30.19157],[-98.08831,30.11798],[-98.09905,30.07794],[-98.13645,30.06938],[-98.17102,30.08121],[-98.17683,30.1044],[-98.18824,30.09946],[-98.1981,30.10599],[-98.21648,30.09652],[-98.27084,30.10674]]],"type":"Polygon"},"id":"48209010807","properties":{"c":[30.14221,-98.16738],"geo_id":"48209010807","name":"Census Tract 108.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.08795,30.20987],[-98.05813,30.2495],[-98.06603,30.27982],[-97.96934,30.21067],[-97.99739,30.19684],[-98.08057,30.1916],[-98.0875,30.19157],[-98.08795,30.20987]]],"type":"Polygon"},"id":"48209010809","properties":{"c":[30.22267,-98.03724],"geo_id":"48209010809","name":"Census Tract 108.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.19223,29.96871],[-98.16854,29.97725],[-98.17484,30.00677],[-98.15333,30.02073],[-98.13058,30.01938],[-98.0878,29.99206],[-98.09372,29.98134],[-98.09194,29.94122],[-98.15159,29.93432],[-98.19223,29.96871]]],"type":"Polygon"},"id":"48209010810","properties":{"c":[29.97479,-98.13628],"geo_id":"48209010810","name":"Census Tract 108.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.29417,30.0468],[-98.27084,30.10674],[-98.21648,30.09652],[-98.1981,30.10599],[-98.18824,30.09946],[-98.17683,30.1044],[-98.17102,30.08121],[-98.15974,30.07492],[-98.12524,30.06894],[-98.10756,30.08062],[-98.09042,30.07013],[-98.09807,30.04872],[-98.12185,30.03029],[-98.14087,30.03766],[-98.14039,30.04798],[-98.15456,30.05782],[-98.17032,30.05604],[-98.17099,30.04203],[-98.17968,30.03526],[-98.15333,30.02073],[-98.17484,30.00677],[-98.16854,29.97725],[-98.19661,29.96631],[-98.2976,30.03799],[-98.29417,30.0468]]],"type":"Polygon"},"id":"48209010811","properties":{"c":[30.04636,-98.20742],"geo_id":"48209010811","name":"Census Tract 108.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.10425,30.01162],[-98.10359,30.04144],[-98.09033,30.0689],[-98.09792,30.07993],[-98.07902,30.09265],[-98.07933,30.109],[-98.03156,30.12324],[-98.01461,30.08593],[-97.98993,30.06022],[-97.98862,30.04739],[-98.03112,30.0474],[-98.05173,30.00886],[-98.04311,30.0013],[-98.02792,30.00743],[-98.02468,29.99826],[-98.00687,29.99468],[-98.01428,29.98375],[-98.03759,29.9867],[-98.0448,29.95876],[-98.00856,29.92856],[-98.00901,29.90873],[-98.05062,29.91675],[-98.09194,29.94122],[-98.09372,29.98134],[-98.0878,29.99206],[-98.10096,29.99905],[-98.10425,30.01162]]],"type":"Polygon"},"id":"48209010812","properties":{"c":[30.02128,-98.05449],"geo_id":"48209010812","name":"Census Tract 108.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.17968,30.03526],[-98.17099,30.04203],[-98.17032,30.05604],[-98.15456,30.05782],[-98.14039,30.04798],[-98.14087,30.03766],[-98.12185,30.03029],[-98.13058,30.01938],[-98.1483,30.01824],[-98.17968,30.03526]]],"type":"Polygon"},"id":"48209010813","properties":{"c":[30.03663,-98.15272],"geo_id":"48209010813","name":"Census Tract 108.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.13002,30.02282],[-98.10163,30.04607],[-98.10129,29.99948],[-98.11721,30.00756],[-98.13002,30.02282]]],"type":"Polygon"},"id":"48209010814","properties":{"c":[30.02316,-98.11288],"geo_id":"48209010814","name":"Census Tract 108.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.97343,30.20853],[-97.92881,30.1817],[-97.92927,30.17502],[-97.95289,30.16177],[-97.96815,30.18288],[-97.97343,30.20853]]],"type":"Polygon"},"id":"48209010815","properties":{"c":[30.18467,-97.95325],"geo_id":"48209010815","name":"Census Tract 108.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.00898,30.15507],[-97.99739,30.19684],[-97.97343,30.20853],[-97.96815,30.18288],[-97.95289,30.16177],[-97.98599,30.14685],[-98.00898,30.15507]]],"type":"Polygon"},"id":"48209010816","properties":{"c":[30.17381,-97.98379],"geo_id":"48209010816","name":"Census Tract 108.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.23676,30.1935],[-98.20653,30.27132],[-98.19818,30.27449],[-98.17354,30.27234],[-98.16657,30.2562],[-98.09684,30.25982],[-98.05813,30.2495],[-98.08144,30.22316],[-98.0875,30.19157],[-98.14245,30.20678],[-98.1648,30.19763],[-98.23676,30.1935]]],"type":"Polygon"},"id":"48209010817","properties":{"c":[30.23037,-98.1535],"geo_id":"48209010817","name":"Census Tract 108.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.20653,30.27132],[-98.17298,30.35631],[-98.06603,30.27982],[-98.05765,30.25219],[-98.09684,30.25982],[-98.16657,30.2562],[-98.17354,30.27234],[-98.20653,30.27132]]],"type":"Polygon"},"id":"48209010818","properties":{"c":[30.29261,-98.13858],"geo_id":"48209010818","name":"Census Tract 108.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.05173,30.00886],[-98.02984,30.04794],[-97.96363,30.04384],[-97.91026,30.02802],[-97.8903,30.01099],[-97.88332,29.99161],[-97.87234,29.98809],[-97.87869,29.95086],[-97.89551,29.93698],[-97.90656,29.94311],[-97.90463,29.97875],[-97.91884,29.97374],[-97.91873,29.98794],[-97.93826,30.01343],[-97.95414,30.0043],[-97.9657,30.01198],[-97.99639,29.99406],[-98.00393,29.99965],[-98.0194,29.99515],[-98.03032,30.00784],[-98.04311,30.0013],[-98.05173,30.00886]]],"type":"Polygon"},"id":"48209010905","properties":{"c":[30.00882,-97.95525],"geo_id":"48209010905","name":"Census Tract 109.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89091,30.01318],[-97.8896,30.02776],[-97.86686,30.0282],[-97.87158,30.00532],[-97.88415,30.00471],[-97.89091,30.01318]]],"type":"Polygon"},"id":"48209010909","properties":{"c":[30.01695,-97.87948],"geo_id":"48209010909","name":"Census Tract 109.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87527,30.11311],[-97.85786,30.13064],[-97.83575,30.11478],[-97.84832,30.09955],[-97.87483,30.09768],[-97.87527,30.11311]]],"type":"Polygon"},"id":"48209010911","properties":{"c":[30.11266,-97.85748],"geo_id":"48209010911","name":"Census Tract 109.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.0099,30.13232],[-97.93093,30.17353],[-97.92881,30.1817],[-97.85786,30.13064],[-97.87512,30.1147],[-97.87483,30.09768],[-97.92632,30.09521],[-97.95515,30.1163],[-97.98533,30.11712],[-98.0099,30.13232]]],"type":"Polygon"},"id":"48209010912","properties":{"c":[30.13254,-97.92772],"geo_id":"48209010912","name":"Census Tract 109.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8879,30.03452],[-97.88106,30.04877],[-97.85732,30.05917],[-97.84832,30.09955],[-97.83575,30.11478],[-97.81326,30.09868],[-97.85794,30.01711],[-97.85949,30.02827],[-97.8896,30.02776],[-97.8879,30.03452]]],"type":"Polygon"},"id":"48209010913","properties":{"c":[30.06441,-97.84828],"geo_id":"48209010913","name":"Census Tract 109.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.03197,30.13186],[-98.0104,30.13192],[-97.98533,30.11712],[-97.95768,30.11724],[-97.92902,30.09572],[-97.87483,30.09768],[-97.87466,30.05031],[-97.88353,30.04628],[-97.89091,30.01318],[-97.91026,30.02802],[-97.98862,30.04739],[-97.99036,30.06133],[-98.01461,30.08593],[-98.03197,30.13186]]],"type":"Polygon"},"id":"48209010914","properties":{"c":[30.07587,-97.94625],"geo_id":"48209010914","name":"Census Tract 109.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87483,30.09768],[-97.84832,30.09955],[-97.85732,30.05917],[-97.86911,30.05034],[-97.87469,30.05022],[-97.87483,30.09768]]],"type":"Polygon"},"id":"48209010915","properties":{"c":[30.07933,-97.86355],"geo_id":"48209010915","name":"Census Tract 109.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85824,29.99114],[-97.85055,29.99814],[-97.85554,30.0038],[-97.83902,30.01675],[-97.77794,29.96264],[-97.79259,29.94506],[-97.81784,29.93443],[-97.83973,29.95525],[-97.83237,29.96942],[-97.85824,29.99114]]],"type":"Polygon"},"id":"48209010916","properties":{"c":[29.97321,-97.82016],"geo_id":"48209010916","name":"Census Tract 109.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87869,29.95086],[-97.87305,29.98424],[-97.81784,29.93443],[-97.84918,29.916],[-97.87816,29.94003],[-97.87869,29.95086]]],"type":"Polygon"},"id":"48209010917","properties":{"c":[29.94593,-97.85403],"geo_id":"48209010917","name":"Census Tract 109.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85886,29.99058],[-97.83237,29.96942],[-97.83973,29.95525],[-97.8692,29.9811],[-97.85886,29.99058]]],"type":"Polygon"},"id":"48209010918","properties":{"c":[29.97286,-97.84944],"geo_id":"48209010918","name":"Census Tract 109.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85558,30.02016],[-97.84536,30.03558],[-97.81285,30.03052],[-97.80524,30.03636],[-97.79028,30.02509],[-97.80526,30.02079],[-97.8202,29.99927],[-97.84029,30.01774],[-97.85558,30.02016]]],"type":"Polygon"},"id":"48209010919","properties":{"c":[30.02185,-97.82419],"geo_id":"48209010919","name":"Census Tract 109.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78312,30.03047],[-97.76911,30.03329],[-97.75148,30.05435],[-97.70879,30.02345],[-97.74814,29.99583],[-97.78312,30.03047]]],"type":"Polygon"},"id":"48209010920","properties":{"c":[30.02414,-97.74732],"geo_id":"48209010920","name":"Census Tract 109.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81936,30.00255],[-97.80526,30.02079],[-97.78607,30.02783],[-97.7492,29.99593],[-97.77794,29.96264],[-97.81936,30.00255]]],"type":"Polygon"},"id":"48209010921","properties":{"c":[29.99786,-97.78606],"geo_id":"48209010921","name":"Census Tract 109.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84536,30.03558],[-97.82383,30.07928],[-97.82099,30.07098],[-97.80641,30.07014],[-97.80524,30.03636],[-97.81285,30.03052],[-97.84536,30.03558]]],"type":"Polygon"},"id":"48209010922","properties":{"c":[30.05007,-97.82131],"geo_id":"48209010922","name":"Census Tract 109.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82383,30.07928],[-97.81326,30.09868],[-97.75148,30.05435],[-97.76911,30.03329],[-97.79028,30.02509],[-97.80524,30.03636],[-97.80547,30.06879],[-97.82099,30.07098],[-97.82383,30.07928]]],"type":"Polygon"},"id":"48209010923","properties":{"c":[30.05957,-97.78922],"geo_id":"48209010923","name":"Census Tract 109.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87234,29.98809],[-97.85693,30.00499],[-97.85055,29.99814],[-97.8692,29.9811],[-97.87234,29.98809]]],"type":"Polygon"},"id":"48209010924","properties":{"c":[29.99315,-97.86257],"geo_id":"48209010924","name":"Census Tract 109.24"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.88415,30.00471],[-97.87158,30.00532],[-97.86686,30.0282],[-97.85949,30.02827],[-97.85794,30.01711],[-97.83902,30.01675],[-97.87234,29.98809],[-97.88332,29.99161],[-97.88879,30.00668],[-97.88415,30.00471]]],"type":"Polygon"},"id":"48209010925","properties":{"c":[30.0081,-97.86493],"geo_id":"48209010925","name":"Census Tract 109.25"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76412,30.33084],[-97.75708,30.33743],[-97.74636,30.33042],[-97.74882,30.30472],[-97.75718,30.30897],[-97.7558,30.32501],[-97.76412,30.33084]]],"type":"Polygon"},"id":"48453000101","properties":{"c":[30.3233,-97.75318],"geo_id":"48453000101","name":"Census Tract 1.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78104,30.33242],[-97.76043,30.34102],[-97.76464,30.32957],[-97.7558,30.32501],[-97.75718,30.30897],[-97.77588,30.31361],[-97.78104,30.33242]]],"type":"Polygon"},"id":"48453000102","properties":{"c":[30.32584,-97.76707],"geo_id":"48453000102","name":"Census Tract 1.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74311,30.3052],[-97.73956,30.3186],[-97.73186,30.32226],[-97.73815,30.30274],[-97.74311,30.3052]]],"type":"Polygon"},"id":"48453000203","properties":{"c":[30.31265,-97.73666],"geo_id":"48453000203","name":"Census Tract 2.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74882,30.30472],[-97.74912,30.31888],[-97.73757,30.31346],[-97.74282,30.29543],[-97.74882,30.30472]]],"type":"Polygon"},"id":"48453000204","properties":{"c":[30.30715,-97.74446],"geo_id":"48453000204","name":"Census Tract 2.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73982,30.33485],[-97.72633,30.32596],[-97.73113,30.31826],[-97.73956,30.3186],[-97.73982,30.33485]]],"type":"Polygon"},"id":"48453000205","properties":{"c":[30.32617,-97.73431],"geo_id":"48453000205","name":"Census Tract 2.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74975,30.3345],[-97.73982,30.33485],[-97.74157,30.3154],[-97.74912,30.31888],[-97.74975,30.3345]]],"type":"Polygon"},"id":"48453000206","properties":{"c":[30.32615,-97.7435],"geo_id":"48453000206","name":"Census Tract 2.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7358,30.30639],[-97.73298,30.31084],[-97.71527,30.30201],[-97.72013,30.29428],[-97.7358,30.30639]]],"type":"Polygon"},"id":"48453000302","properties":{"c":[30.30257,-97.72646],"geo_id":"48453000302","name":"Census Tract 3.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72461,30.307],[-97.71853,30.31642],[-97.70943,30.31135],[-97.71527,30.30201],[-97.72461,30.307]]],"type":"Polygon"},"id":"48453000304","properties":{"c":[30.30941,-97.71692],"geo_id":"48453000304","name":"Census Tract 3.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73222,30.3165],[-97.72825,30.32295],[-97.71853,30.31642],[-97.72461,30.307],[-97.73222,30.3165]]],"type":"Polygon"},"id":"48453000305","properties":{"c":[30.31488,-97.72633],"geo_id":"48453000305","name":"Census Tract 3.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71527,30.30201],[-97.70921,30.30264],[-97.70715,30.2892],[-97.71972,30.29494],[-97.71527,30.30201]]],"type":"Polygon"},"id":"48453000307","properties":{"c":[30.29702,-97.7126],"geo_id":"48453000307","name":"Census Tract 3.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70038,30.29999],[-97.69888,30.30391],[-97.68591,30.30015],[-97.69857,30.28909],[-97.70038,30.29999]]],"type":"Polygon"},"id":"48453000308","properties":{"c":[30.29613,-97.69449],"geo_id":"48453000308","name":"Census Tract 3.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71242,30.30649],[-97.69888,30.30391],[-97.69857,30.28909],[-97.70631,30.28626],[-97.71242,30.30649]]],"type":"Polygon"},"id":"48453000309","properties":{"c":[30.29797,-97.70479],"geo_id":"48453000309","name":"Census Tract 3.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7343,30.28037],[-97.72728,30.29749],[-97.71356,30.29176],[-97.71843,30.28441],[-97.7343,30.28037]]],"type":"Polygon"},"id":"48453000401","properties":{"c":[30.28828,-97.72507],"geo_id":"48453000401","name":"Census Tract 4.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72899,30.28065],[-97.71356,30.29176],[-97.70394,30.28257],[-97.73005,30.27851],[-97.72899,30.28065]]],"type":"Polygon"},"id":"48453000402","properties":{"c":[30.28415,-97.71553],"geo_id":"48453000402","name":"Census Tract 4.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73815,30.30274],[-97.72728,30.29749],[-97.7341,30.28818],[-97.7421,30.2965],[-97.73815,30.30274]]],"type":"Polygon"},"id":"48453000500","properties":{"c":[30.29604,-97.7342],"geo_id":"48453000500","name":"Census Tract 5"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7421,30.2965],[-97.73474,30.29096],[-97.7343,30.28037],[-97.74189,30.28174],[-97.7421,30.2965]]],"type":"Polygon"},"id":"48453000601","properties":{"c":[30.28745,-97.73808],"geo_id":"48453000601","name":"Census Tract 6.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75331,30.28869],[-97.74911,30.29886],[-97.74392,30.29592],[-97.74442,30.29067],[-97.75331,30.28869]]],"type":"Polygon"},"id":"48453000605","properties":{"c":[30.2928,-97.74784],"geo_id":"48453000605","name":"Census Tract 6.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74754,30.29087],[-97.74282,30.29543],[-97.74155,30.28772],[-97.74783,30.28816],[-97.74754,30.29087]]],"type":"Polygon"},"id":"48453000606","properties":{"c":[30.29071,-97.74387],"geo_id":"48453000606","name":"Census Tract 6.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75331,30.28869],[-97.74468,30.28794],[-97.74518,30.28266],[-97.75091,30.28],[-97.75331,30.28869]]],"type":"Polygon"},"id":"48453000607","properties":{"c":[30.28572,-97.74945],"geo_id":"48453000607","name":"Census Tract 6.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74495,30.28526],[-97.74155,30.28772],[-97.74189,30.28174],[-97.74518,30.28266],[-97.74495,30.28526]]],"type":"Polygon"},"id":"48453000608","properties":{"c":[30.28498,-97.74332],"geo_id":"48453000608","name":"Census Tract 6.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75212,30.28361],[-97.73005,30.27851],[-97.7325,30.27185],[-97.75017,30.27649],[-97.75212,30.28361]]],"type":"Polygon"},"id":"48453000700","properties":{"c":[30.27772,-97.74107],"geo_id":"48453000700","name":"Census Tract 7"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70904,30.26539],[-97.69791,30.27356],[-97.69455,30.26239],[-97.69871,30.26066],[-97.70904,30.26539]]],"type":"Polygon"},"id":"48453000801","properties":{"c":[30.26692,-97.70146],"geo_id":"48453000801","name":"Census Tract 8.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71598,30.27436],[-97.70394,30.28257],[-97.69791,30.27356],[-97.71323,30.26319],[-97.71598,30.27436]]],"type":"Polygon"},"id":"48453000802","properties":{"c":[30.27359,-97.70788],"geo_id":"48453000802","name":"Census Tract 8.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7325,30.27185],[-97.73005,30.27851],[-97.7085,30.28183],[-97.711,30.27518],[-97.7325,30.27185]]],"type":"Polygon"},"id":"48453000803","properties":{"c":[30.27681,-97.72044],"geo_id":"48453000803","name":"Census Tract 8.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7325,30.27185],[-97.71598,30.27436],[-97.71468,30.26691],[-97.71797,30.26518],[-97.7325,30.27185]]],"type":"Polygon"},"id":"48453000804","properties":{"c":[30.27012,-97.72182],"geo_id":"48453000804","name":"Census Tract 8.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.733,30.27046],[-97.71468,30.26691],[-97.71323,30.26319],[-97.73437,30.26673],[-97.733,30.27046]]],"type":"Polygon"},"id":"48453000901","properties":{"c":[30.26554,-97.72372],"geo_id":"48453000901","name":"Census Tract 9.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73472,30.26579],[-97.71027,30.26477],[-97.69871,30.26066],[-97.70875,30.25173],[-97.73472,30.26579]]],"type":"Polygon"},"id":"48453000902","properties":{"c":[30.25921,-97.71601],"geo_id":"48453000902","name":"Census Tract 9.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73717,30.25914],[-97.73655,30.26121],[-97.70454,30.25193],[-97.72376,30.2466],[-97.73599,30.25061],[-97.73717,30.25914]]],"type":"Polygon"},"id":"48453001000","properties":{"c":[30.25307,-97.72566],"geo_id":"48453001000","name":"Census Tract 10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.752,30.27422],[-97.75017,30.27649],[-97.7325,30.27185],[-97.73472,30.26579],[-97.752,30.27422]]],"type":"Polygon"},"id":"48453001101","properties":{"c":[30.27114,-97.74242],"geo_id":"48453001101","name":"Census Tract 11.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75126,30.27054],[-97.74281,30.26807],[-97.74518,30.26165],[-97.75204,30.26419],[-97.75126,30.27054]]],"type":"Polygon"},"id":"48453001102","properties":{"c":[30.26631,-97.74759],"geo_id":"48453001102","name":"Census Tract 11.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74501,30.26212],[-97.73472,30.26579],[-97.73599,30.25061],[-97.74098,30.25479],[-97.74501,30.26212]]],"type":"Polygon"},"id":"48453001103","properties":{"c":[30.26083,-97.73976],"geo_id":"48453001103","name":"Census Tract 11.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77147,30.27381],[-97.76508,30.28384],[-97.75017,30.27649],[-97.75053,30.26636],[-97.77147,30.27381]]],"type":"Polygon"},"id":"48453001200","properties":{"c":[30.27376,-97.76012],"geo_id":"48453001200","name":"Census Tract 12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77906,30.25205],[-97.77282,30.25799],[-97.7647,30.2509],[-97.7731,30.2374],[-97.77906,30.25205]]],"type":"Polygon"},"id":"48453001304","properties":{"c":[30.2484,-97.7734],"geo_id":"48453001304","name":"Census Tract 13.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77566,30.23001],[-97.76898,30.24602],[-97.75962,30.24211],[-97.76947,30.22652],[-97.77566,30.23001]]],"type":"Polygon"},"id":"48453001307","properties":{"c":[30.23633,-97.76861],"geo_id":"48453001307","name":"Census Tract 13.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.766,30.23201],[-97.75962,30.24211],[-97.75352,30.23876],[-97.76396,30.22284],[-97.766,30.23201]]],"type":"Polygon"},"id":"48453001308","properties":{"c":[30.23274,-97.76175],"geo_id":"48453001308","name":"Census Tract 13.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77226,30.25934],[-97.76066,30.26753],[-97.7545,30.26498],[-97.76777,30.253],[-97.77226,30.25934]]],"type":"Polygon"},"id":"48453001309","properties":{"c":[30.26107,-97.76429],"geo_id":"48453001309","name":"Census Tract 13.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76777,30.253],[-97.76149,30.26199],[-97.75707,30.26061],[-97.76484,30.24918],[-97.76777,30.253]]],"type":"Polygon"},"id":"48453001310","properties":{"c":[30.2563,-97.76254],"geo_id":"48453001310","name":"Census Tract 13.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75459,30.26482],[-97.74518,30.26165],[-97.75188,30.24969],[-97.75684,30.25384],[-97.75459,30.26482]]],"type":"Polygon"},"id":"48453001311","properties":{"c":[30.25764,-97.75143],"geo_id":"48453001311","name":"Census Tract 13.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76898,30.24602],[-97.75707,30.26061],[-97.75491,30.25002],[-97.74865,30.25227],[-97.75352,30.23876],[-97.76898,30.24602]]],"type":"Polygon"},"id":"48453001312","properties":{"c":[30.2484,-97.75802],"geo_id":"48453001312","name":"Census Tract 13.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75217,30.24291],[-97.74865,30.25227],[-97.74518,30.26165],[-97.73954,30.25309],[-97.74744,30.23968],[-97.75217,30.24291]]],"type":"Polygon"},"id":"48453001401","properties":{"c":[30.24998,-97.74602],"geo_id":"48453001401","name":"Census Tract 14.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74744,30.23968],[-97.741,30.25178],[-97.73599,30.25061],[-97.74127,30.23377],[-97.74744,30.23968]]],"type":"Polygon"},"id":"48453001402","properties":{"c":[30.24357,-97.74056],"geo_id":"48453001402","name":"Census Tract 14.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74127,30.23377],[-97.73541,30.24789],[-97.73375,30.24762],[-97.72929,30.24321],[-97.74127,30.23377]]],"type":"Polygon"},"id":"48453001403","properties":{"c":[30.23991,-97.73507],"geo_id":"48453001403","name":"Census Tract 14.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75501,30.33623],[-97.74412,30.35988],[-97.7309,30.35615],[-97.73982,30.33485],[-97.75501,30.33623]]],"type":"Polygon"},"id":"48453001501","properties":{"c":[30.34659,-97.74329],"geo_id":"48453001501","name":"Census Tract 15.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72633,30.32596],[-97.71782,30.33941],[-97.70428,30.33283],[-97.71463,30.31502],[-97.72633,30.32596]]],"type":"Polygon"},"id":"48453001503","properties":{"c":[30.32727,-97.71575],"geo_id":"48453001503","name":"Census Tract 15.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73661,30.34674],[-97.7309,30.35615],[-97.71308,30.34684],[-97.71956,30.3367],[-97.73661,30.34674]]],"type":"Polygon"},"id":"48453001504","properties":{"c":[30.34656,-97.72509],"geo_id":"48453001504","name":"Census Tract 15.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73917,30.33872],[-97.73755,30.34542],[-97.71956,30.3367],[-97.72633,30.32596],[-97.73917,30.33872]]],"type":"Polygon"},"id":"48453001505","properties":{"c":[30.33641,-97.73042],"geo_id":"48453001505","name":"Census Tract 15.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78592,30.2975],[-97.76374,30.28588],[-97.7716,30.27364],[-97.78427,30.28431],[-97.78592,30.2975]]],"type":"Polygon"},"id":"48453001602","properties":{"c":[30.28554,-97.77589],"geo_id":"48453001602","name":"Census Tract 16.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76826,30.2967],[-97.75807,30.30043],[-97.75718,30.30897],[-97.74711,30.29948],[-97.75331,30.28869],[-97.76826,30.2967]]],"type":"Polygon"},"id":"48453001603","properties":{"c":[30.2984,-97.75647],"geo_id":"48453001603","name":"Census Tract 16.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78592,30.2975],[-97.77588,30.31361],[-97.76267,30.31048],[-97.77205,30.2906],[-97.78592,30.2975]]],"type":"Polygon"},"id":"48453001604","properties":{"c":[30.30287,-97.77324],"geo_id":"48453001604","name":"Census Tract 16.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77205,30.2906],[-97.76826,30.2967],[-97.75331,30.28869],[-97.75017,30.27649],[-97.77205,30.2906]]],"type":"Polygon"},"id":"48453001605","properties":{"c":[30.28676,-97.76056],"geo_id":"48453001605","name":"Census Tract 16.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7649,30.30534],[-97.76267,30.31048],[-97.75718,30.30897],[-97.75807,30.30043],[-97.7649,30.30534]]],"type":"Polygon"},"id":"48453001606","properties":{"c":[30.30568,-97.76081],"geo_id":"48453001606","name":"Census Tract 16.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81829,30.27704],[-97.8017,30.26825],[-97.78089,30.269],[-97.77714,30.27372],[-97.79992,30.28988],[-97.79021,30.29774],[-97.7716,30.27364],[-97.80444,30.24789],[-97.81829,30.27704]]],"type":"Polygon"},"id":"48453001910","properties":{"c":[30.27039,-97.79802],"geo_id":"48453001910","name":"Census Tract 19.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80444,30.24789],[-97.7716,30.27364],[-97.76066,30.26753],[-97.79572,30.25343],[-97.7898,30.24214],[-97.80444,30.24789]]],"type":"Polygon"},"id":"48453001911","properties":{"c":[30.25852,-97.78588],"geo_id":"48453001911","name":"Census Tract 19.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85525,30.31512],[-97.85022,30.34048],[-97.84267,30.32622],[-97.83064,30.32523],[-97.80569,30.35202],[-97.7883,30.34356],[-97.77607,30.32218],[-97.80636,30.3353],[-97.8266,30.3147],[-97.82822,30.29572],[-97.85525,30.31512]]],"type":"Polygon"},"id":"48453001912","properties":{"c":[30.3261,-97.82093],"geo_id":"48453001912","name":"Census Tract 19.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8266,30.3147],[-97.80636,30.3353],[-97.78074,30.32672],[-97.77566,30.31803],[-97.78594,30.29658],[-97.80123,30.30792],[-97.82584,30.30432],[-97.8266,30.3147]]],"type":"Polygon"},"id":"48453001913","properties":{"c":[30.31661,-97.79884],"geo_id":"48453001913","name":"Census Tract 19.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86872,30.25934],[-97.84838,30.27682],[-97.83677,30.27514],[-97.82488,30.26961],[-97.81072,30.24317],[-97.8231,30.23725],[-97.86872,30.25934]]],"type":"Polygon"},"id":"48453001914","properties":{"c":[30.25713,-97.83911],"geo_id":"48453001914","name":"Census Tract 19.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8663,30.25301],[-97.8231,30.23725],[-97.80249,30.24469],[-97.79656,30.23404],[-97.86478,30.23406],[-97.8663,30.25301]]],"type":"Polygon"},"id":"48453001915","properties":{"c":[30.24057,-97.8367],"geo_id":"48453001915","name":"Census Tract 19.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.93349,30.30537],[-97.91338,30.31076],[-97.89962,30.3061],[-97.8619,30.31816],[-97.83462,30.29592],[-97.85001,30.29149],[-97.85428,30.30465],[-97.86133,30.29674],[-97.86778,30.30679],[-97.88242,30.28659],[-97.89061,30.29568],[-97.9007,30.28926],[-97.89698,30.29693],[-97.90981,30.30709],[-97.92385,30.296],[-97.93349,30.30537]]],"type":"Polygon"},"id":"48453001916","properties":{"c":[30.30387,-97.87912],"geo_id":"48453001916","name":"Census Tract 19.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85184,30.28441],[-97.82822,30.29572],[-97.80249,30.24469],[-97.81033,30.23973],[-97.82488,30.26961],[-97.8431,30.27313],[-97.85184,30.28441]]],"type":"Polygon"},"id":"48453001917","properties":{"c":[30.27438,-97.82866],"geo_id":"48453001917","name":"Census Tract 19.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82827,30.295],[-97.82331,30.30555],[-97.80123,30.30792],[-97.79021,30.29774],[-97.81225,30.27434],[-97.82827,30.295]]],"type":"Polygon"},"id":"48453001918","properties":{"c":[30.29354,-97.81169],"geo_id":"48453001918","name":"Census Tract 19.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81134,30.2745],[-97.79775,30.28884],[-97.77714,30.27372],[-97.78559,30.26731],[-97.81134,30.2745]]],"type":"Polygon"},"id":"48453001919","properties":{"c":[30.27718,-97.79518],"geo_id":"48453001919","name":"Census Tract 19.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.91144,30.27698],[-97.90195,30.27992],[-97.89005,30.26272],[-97.86548,30.25451],[-97.86478,30.23406],[-97.89983,30.25276],[-97.91144,30.27698]]],"type":"Polygon"},"id":"48453001920","properties":{"c":[30.25581,-97.88748],"geo_id":"48453001920","name":"Census Tract 19.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92559,30.29637],[-97.90981,30.30709],[-97.89698,30.29693],[-97.9007,30.28926],[-97.89061,30.29568],[-97.88242,30.28659],[-97.86778,30.30679],[-97.86296,30.29752],[-97.85428,30.30465],[-97.85001,30.29149],[-97.84298,30.29214],[-97.85237,30.2819],[-97.84596,30.27574],[-97.86834,30.25667],[-97.87896,30.25669],[-97.89953,30.27864],[-97.9142,30.27544],[-97.92559,30.29637]]],"type":"Polygon"},"id":"48453001921","properties":{"c":[30.28304,-97.88171],"geo_id":"48453001921","name":"Census Tract 19.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80094,30.24526],[-97.7898,30.24214],[-97.79572,30.25343],[-97.78674,30.25685],[-97.78236,30.24365],[-97.79656,30.23404],[-97.80094,30.24526]]],"type":"Polygon"},"id":"48453001922","properties":{"c":[30.24532,-97.7919],"geo_id":"48453001922","name":"Census Tract 19.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78674,30.25685],[-97.78073,30.2626],[-97.76499,30.26477],[-97.78236,30.24365],[-97.78674,30.25685]]],"type":"Polygon"},"id":"48453001923","properties":{"c":[30.25635,-97.77916],"geo_id":"48453001923","name":"Census Tract 19.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79099,30.22576],[-97.78834,30.2299],[-97.77649,30.22758],[-97.78944,30.21646],[-97.79099,30.22576]]],"type":"Polygon"},"id":"48453002002","properties":{"c":[30.22309,-97.78488],"geo_id":"48453002002","name":"Census Tract 20.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78944,30.21646],[-97.77649,30.22758],[-97.76396,30.22284],[-97.77192,30.21028],[-97.78944,30.21646]]],"type":"Polygon"},"id":"48453002003","properties":{"c":[30.2192,-97.77458],"geo_id":"48453002003","name":"Census Tract 20.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79656,30.23404],[-97.78236,30.24365],[-97.78166,30.24261],[-97.78834,30.2299],[-97.79656,30.23404]]],"type":"Polygon"},"id":"48453002004","properties":{"c":[30.23612,-97.78819],"geo_id":"48453002004","name":"Census Tract 20.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78441,30.22827],[-97.77686,30.23911],[-97.7731,30.2374],[-97.77649,30.22758],[-97.78441,30.22827]]],"type":"Polygon"},"id":"48453002006","properties":{"c":[30.23253,-97.77814],"geo_id":"48453002006","name":"Census Tract 20.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78834,30.2299],[-97.78236,30.24365],[-97.77718,30.24692],[-97.77933,30.23534],[-97.78834,30.2299]]],"type":"Polygon"},"id":"48453002007","properties":{"c":[30.23719,-97.78169],"geo_id":"48453002007","name":"Census Tract 20.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70154,30.31581],[-97.69539,30.32147],[-97.68908,30.32149],[-97.69734,30.30634],[-97.70154,30.31581]]],"type":"Polygon"},"id":"48453002104","properties":{"c":[30.31475,-97.69658],"geo_id":"48453002104","name":"Census Tract 21.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71463,30.31502],[-97.71276,30.32044],[-97.69539,30.32147],[-97.70496,30.3131],[-97.69888,30.30391],[-97.71463,30.31502]]],"type":"Polygon"},"id":"48453002105","properties":{"c":[30.31492,-97.70561],"geo_id":"48453002105","name":"Census Tract 21.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69734,30.30634],[-97.6916,30.31565],[-97.68131,30.30458],[-97.6894,30.29968],[-97.69734,30.30634]]],"type":"Polygon"},"id":"48453002106","properties":{"c":[30.30672,-97.69029],"geo_id":"48453002106","name":"Census Tract 21.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69857,30.28909],[-97.69035,30.28991],[-97.67954,30.30732],[-97.66906,30.30899],[-97.68263,30.28586],[-97.69857,30.28909]]],"type":"Polygon"},"id":"48453002107","properties":{"c":[30.29565,-97.68287],"geo_id":"48453002107","name":"Census Tract 21.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67992,30.29007],[-97.66906,30.30899],[-97.66302,30.3161],[-97.66526,30.28562],[-97.67992,30.29007]]],"type":"Polygon"},"id":"48453002108","properties":{"c":[30.29738,-97.66898],"geo_id":"48453002108","name":"Census Tract 21.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70631,30.28626],[-97.69857,30.28909],[-97.69609,30.28373],[-97.66941,30.28631],[-97.69042,30.27356],[-97.70631,30.28626]]],"type":"Polygon"},"id":"48453002109","properties":{"c":[30.28151,-97.69062],"geo_id":"48453002109","name":"Census Tract 21.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69042,30.27356],[-97.66941,30.28631],[-97.66526,30.28562],[-97.67239,30.26369],[-97.68564,30.26493],[-97.69042,30.27356]]],"type":"Polygon"},"id":"48453002110","properties":{"c":[30.27411,-97.67723],"geo_id":"48453002110","name":"Census Tract 21.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70454,30.25193],[-97.69455,30.26239],[-97.69642,30.27388],[-97.66034,30.26139],[-97.68246,30.24629],[-97.70454,30.25193]]],"type":"Polygon"},"id":"48453002111","properties":{"c":[30.2573,-97.68596],"geo_id":"48453002111","name":"Census Tract 21.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68901,30.32042],[-97.68078,30.32309],[-97.67077,30.30853],[-97.68552,30.30657],[-97.68901,30.32042]]],"type":"Polygon"},"id":"48453002112","properties":{"c":[30.31393,-97.68266],"geo_id":"48453002112","name":"Census Tract 21.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68156,30.31573],[-97.67323,30.32572],[-97.66302,30.3161],[-97.67077,30.30853],[-97.68156,30.31573]]],"type":"Polygon"},"id":"48453002113","properties":{"c":[30.31711,-97.67244],"geo_id":"48453002113","name":"Census Tract 21.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67323,30.32572],[-97.644,30.32954],[-97.65073,30.30326],[-97.66084,30.30262],[-97.67323,30.32572]]],"type":"Polygon"},"id":"48453002201","properties":{"c":[30.31779,-97.65544],"geo_id":"48453002201","name":"Census Tract 22.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63727,30.27679],[-97.62795,30.29124],[-97.59996,30.27588],[-97.61182,30.257],[-97.63727,30.27679]]],"type":"Polygon"},"id":"48453002211","properties":{"c":[30.2743,-97.61925],"geo_id":"48453002211","name":"Census Tract 22.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64976,30.29107],[-97.64636,30.29937],[-97.62795,30.29124],[-97.63727,30.27679],[-97.64869,30.28108],[-97.64976,30.29107]]],"type":"Polygon"},"id":"48453002213","properties":{"c":[30.28815,-97.64044],"geo_id":"48453002213","name":"Census Tract 22.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67239,30.26369],[-97.66084,30.30262],[-97.64636,30.29937],[-97.64869,30.28108],[-97.63126,30.27114],[-97.64266,30.26248],[-97.67239,30.26369]]],"type":"Polygon"},"id":"48453002214","properties":{"c":[30.27838,-97.65438],"geo_id":"48453002214","name":"Census Tract 22.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61182,30.257],[-97.59625,30.28164],[-97.5546,30.25609],[-97.56098,30.24887],[-97.58303,30.24748],[-97.61182,30.257]]],"type":"Polygon"},"id":"48453002215","properties":{"c":[30.26134,-97.58467],"geo_id":"48453002215","name":"Census Tract 22.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6588,30.22676],[-97.62663,30.24832],[-97.62623,30.25511],[-97.64157,30.25713],[-97.63126,30.27114],[-97.58303,30.24748],[-97.56098,30.24887],[-97.5546,30.25609],[-97.52681,30.25136],[-97.5144,30.22684],[-97.49652,30.21614],[-97.49112,30.22428],[-97.48633,30.22053],[-97.52167,30.19776],[-97.52936,30.20428],[-97.51324,30.2105],[-97.51995,30.22934],[-97.52714,30.21879],[-97.54167,30.22525],[-97.5565,30.20773],[-97.57589,30.2143],[-97.58855,30.2061],[-97.59516,30.2085],[-97.5938,30.22786],[-97.63276,30.20747],[-97.65056,30.21357],[-97.6588,30.22676]]],"type":"Polygon"},"id":"48453002216","properties":{"c":[30.23147,-97.58206],"geo_id":"48453002216","name":"Census Tract 22.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.58004,30.34441],[-97.55325,30.34907],[-97.40939,30.35215],[-97.4257,30.3244],[-97.43707,30.31928],[-97.54027,30.34298],[-97.58004,30.34441]]],"type":"Polygon"},"id":"48453002217","properties":{"c":[30.33926,-97.47411],"geo_id":"48453002217","name":"Census Tract 22.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.55965,30.34142],[-97.54027,30.34298],[-97.45211,30.31991],[-97.4257,30.3244],[-97.45542,30.28295],[-97.50752,30.30775],[-97.5284,30.30081],[-97.55965,30.34142]]],"type":"Polygon"},"id":"48453002218","properties":{"c":[30.31519,-97.49154],"geo_id":"48453002218","name":"Census Tract 22.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62795,30.29124],[-97.59947,30.33747],[-97.5805,30.34429],[-97.55069,30.33514],[-97.5284,30.30081],[-97.50752,30.30775],[-97.45043,30.28232],[-97.48633,30.22053],[-97.49112,30.22428],[-97.49652,30.21614],[-97.51489,30.22736],[-97.52681,30.25136],[-97.5546,30.25609],[-97.5691,30.26906],[-97.62795,30.29124]]],"type":"Polygon"},"id":"48453002219","properties":{"c":[30.28453,-97.53755],"geo_id":"48453002219","name":"Census Tract 22.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65073,30.30326],[-97.644,30.32954],[-97.6185,30.33181],[-97.63158,30.30685],[-97.65073,30.30326]]],"type":"Polygon"},"id":"48453002220","properties":{"c":[30.31785,-97.63662],"geo_id":"48453002220","name":"Census Tract 22.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63038,30.30796],[-97.62493,30.32651],[-97.59947,30.33747],[-97.62084,30.30226],[-97.63038,30.30796]]],"type":"Polygon"},"id":"48453002221","properties":{"c":[30.32035,-97.61714],"geo_id":"48453002221","name":"Census Tract 22.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64375,30.30423],[-97.63038,30.30796],[-97.62084,30.30226],[-97.62795,30.29124],[-97.64636,30.29937],[-97.64375,30.30423]]],"type":"Polygon"},"id":"48453002222","properties":{"c":[30.30049,-97.63322],"geo_id":"48453002222","name":"Census Tract 22.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73599,30.25061],[-97.72376,30.2466],[-97.71351,30.25043],[-97.72285,30.2341],[-97.73599,30.25061]]],"type":"Polygon"},"id":"48453002304","properties":{"c":[30.24373,-97.72339],"geo_id":"48453002304","name":"Census Tract 23.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75129,30.21657],[-97.74127,30.23377],[-97.736,30.23166],[-97.73508,30.21535],[-97.75129,30.21657]]],"type":"Polygon"},"id":"48453002307","properties":{"c":[30.22308,-97.74099],"geo_id":"48453002307","name":"Census Tract 23.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69128,30.24518],[-97.65904,30.26188],[-97.62623,30.25511],[-97.63315,30.2399],[-97.6588,30.22676],[-97.63937,30.20329],[-97.68329,30.22229],[-97.69128,30.24518]]],"type":"Polygon"},"id":"48453002310","properties":{"c":[30.2399,-97.65889],"geo_id":"48453002310","name":"Census Tract 23.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.736,30.23166],[-97.7243,30.22566],[-97.71021,30.21498],[-97.73508,30.21535],[-97.736,30.23166]]],"type":"Polygon"},"id":"48453002313","properties":{"c":[30.22019,-97.72604],"geo_id":"48453002313","name":"Census Tract 23.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72778,30.22746],[-97.72285,30.2341],[-97.70339,30.22499],[-97.71021,30.21498],[-97.72778,30.22746]]],"type":"Polygon"},"id":"48453002314","properties":{"c":[30.22475,-97.71558],"geo_id":"48453002314","name":"Census Tract 23.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73689,30.23232],[-97.73295,30.2382],[-97.72733,30.23541],[-97.73102,30.22975],[-97.73689,30.23232]]],"type":"Polygon"},"id":"48453002315","properties":{"c":[30.23394,-97.73209],"geo_id":"48453002315","name":"Census Tract 23.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73295,30.2382],[-97.72929,30.24321],[-97.72285,30.2341],[-97.72778,30.22746],[-97.73295,30.2382]]],"type":"Polygon"},"id":"48453002316","properties":{"c":[30.23541,-97.72794],"geo_id":"48453002316","name":"Census Tract 23.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65162,30.19843],[-97.64564,30.20368],[-97.63773,30.20244],[-97.64669,30.19433],[-97.65162,30.19843]]],"type":"Polygon"},"id":"48453002319","properties":{"c":[30.19981,-97.64493],"geo_id":"48453002319","name":"Census Tract 23.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71083,30.21441],[-97.70339,30.22499],[-97.6967,30.22213],[-97.68519,30.23436],[-97.68329,30.22229],[-97.71083,30.21441]]],"type":"Polygon"},"id":"48453002320","properties":{"c":[30.22195,-97.69526],"geo_id":"48453002320","name":"Census Tract 23.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70339,30.22499],[-97.69268,30.24174],[-97.69108,30.24393],[-97.68519,30.23436],[-97.6967,30.22213],[-97.70339,30.22499]]],"type":"Polygon"},"id":"48453002321","properties":{"c":[30.23193,-97.69401],"geo_id":"48453002321","name":"Census Tract 23.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76384,30.22303],[-97.76021,30.22965],[-97.74746,30.2233],[-97.75142,30.21635],[-97.76384,30.22303]]],"type":"Polygon"},"id":"48453002322","properties":{"c":[30.22299,-97.75569],"geo_id":"48453002322","name":"Census Tract 23.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75636,30.23551],[-97.75243,30.24192],[-97.74127,30.23377],[-97.74746,30.2233],[-97.76021,30.22965],[-97.75636,30.23551]]],"type":"Polygon"},"id":"48453002323","properties":{"c":[30.23249,-97.75023],"geo_id":"48453002323","name":"Census Tract 23.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72285,30.2341],[-97.71955,30.2388],[-97.71504,30.23756],[-97.71744,30.23172],[-97.72285,30.2341]]],"type":"Polygon"},"id":"48453002324","properties":{"c":[30.23513,-97.71884],"geo_id":"48453002324","name":"Census Tract 23.24"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71744,30.23172],[-97.70213,30.23721],[-97.69732,30.23459],[-97.70339,30.22499],[-97.71744,30.23172]]],"type":"Polygon"},"id":"48453002325","properties":{"c":[30.23148,-97.70647],"geo_id":"48453002325","name":"Census Tract 23.25"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71955,30.2388],[-97.71351,30.25043],[-97.70004,30.24782],[-97.70839,30.24811],[-97.71955,30.2388]]],"type":"Polygon"},"id":"48453002326","properties":{"c":[30.24534,-97.71183],"geo_id":"48453002326","name":"Census Tract 23.26"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71711,30.23452],[-97.70839,30.24811],[-97.69128,30.24518],[-97.69732,30.23459],[-97.71711,30.23452]]],"type":"Polygon"},"id":"48453002327","properties":{"c":[30.241,-97.70397],"geo_id":"48453002327","name":"Census Tract 23.27"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77192,30.21028],[-97.76396,30.22284],[-97.75142,30.21635],[-97.76165,30.20168],[-97.77192,30.21028]]],"type":"Polygon"},"id":"48453002403","properties":{"c":[30.21203,-97.76229],"geo_id":"48453002403","name":"Census Tract 24.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83204,30.1172],[-97.82588,30.15562],[-97.82342,30.14831],[-97.7915,30.15282],[-97.81326,30.09868],[-97.83204,30.1172]]],"type":"Polygon"},"id":"48453002407","properties":{"c":[30.13021,-97.81482],"geo_id":"48453002407","name":"Census Tract 24.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80195,30.20152],[-97.79168,30.21551],[-97.78618,30.21473],[-97.79361,30.19933],[-97.80195,30.20152]]],"type":"Polygon"},"id":"48453002409","properties":{"c":[30.20754,-97.79356],"geo_id":"48453002409","name":"Census Tract 24.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79349,30.20072],[-97.78618,30.21473],[-97.77897,30.21193],[-97.78777,30.19719],[-97.79349,30.20072]]],"type":"Polygon"},"id":"48453002410","properties":{"c":[30.20576,-97.78666],"geo_id":"48453002410","name":"Census Tract 24.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76165,30.20168],[-97.75129,30.21657],[-97.73508,30.21535],[-97.74462,30.194],[-97.7563,30.1937],[-97.76165,30.20168]]],"type":"Polygon"},"id":"48453002411","properties":{"c":[30.20526,-97.74894],"geo_id":"48453002411","name":"Census Tract 24.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76135,30.1943],[-97.74462,30.194],[-97.74629,30.1815],[-97.75198,30.1831],[-97.76135,30.1943]]],"type":"Polygon"},"id":"48453002412","properties":{"c":[30.18942,-97.75149],"geo_id":"48453002412","name":"Census Tract 24.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74502,30.18975],[-97.74044,30.20685],[-97.73338,30.20348],[-97.74479,30.18394],[-97.74502,30.18975]]],"type":"Polygon"},"id":"48453002413","properties":{"c":[30.1971,-97.74028],"geo_id":"48453002413","name":"Census Tract 24.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77052,30.19054],[-97.76165,30.20168],[-97.74682,30.1797],[-97.75733,30.18576],[-97.77052,30.19054]]],"type":"Polygon"},"id":"48453002419","properties":{"c":[30.19114,-97.76079],"geo_id":"48453002419","name":"Census Tract 24.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79888,30.17492],[-97.78777,30.19719],[-97.77052,30.19054],[-97.78625,30.16698],[-97.78528,30.17295],[-97.79888,30.17492]]],"type":"Polygon"},"id":"48453002422","properties":{"c":[30.18343,-97.78482],"geo_id":"48453002422","name":"Census Tract 24.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.818,30.17802],[-97.81282,30.18558],[-97.79267,30.18388],[-97.79945,30.17256],[-97.818,30.17802]]],"type":"Polygon"},"id":"48453002423","properties":{"c":[30.17972,-97.80619],"geo_id":"48453002423","name":"Census Tract 24.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81282,30.18558],[-97.80195,30.20152],[-97.78777,30.19719],[-97.79267,30.18388],[-97.81282,30.18558]]],"type":"Polygon"},"id":"48453002424","properties":{"c":[30.19219,-97.79925],"geo_id":"48453002424","name":"Census Tract 24.24"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7698,30.17767],[-97.7522,30.17217],[-97.74682,30.1797],[-97.74108,30.17298],[-97.75077,30.1647],[-97.76821,30.16646],[-97.7698,30.17767]]],"type":"Polygon"},"id":"48453002430","properties":{"c":[30.17185,-97.75486],"geo_id":"48453002430","name":"Census Tract 24.30"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75577,30.10118],[-97.7294,30.14208],[-97.73617,30.15986],[-97.72984,30.15686],[-97.71962,30.18252],[-97.68427,30.19832],[-97.69691,30.14978],[-97.69388,30.09352],[-97.73451,30.09002],[-97.75577,30.10118]]],"type":"Polygon"},"id":"48453002432","properties":{"c":[30.13521,-97.71528],"geo_id":"48453002432","name":"Census Tract 24.32"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81326,30.09868],[-97.80687,30.11247],[-97.78231,30.11274],[-97.73451,30.09002],[-97.69388,30.09352],[-97.69008,30.03912],[-97.70879,30.02345],[-97.81326,30.09868]]],"type":"Polygon"},"id":"48453002434","properties":{"c":[30.07329,-97.74142],"geo_id":"48453002434","name":"Census Tract 24.34"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69691,30.14978],[-97.69299,30.16425],[-97.67083,30.15349],[-97.67416,30.14487],[-97.61078,30.10275],[-97.69008,30.03912],[-97.69691,30.14978]]],"type":"Polygon"},"id":"48453002436","properties":{"c":[30.10323,-97.66649],"geo_id":"48453002436","name":"Census Tract 24.36"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80038,30.15457],[-97.79891,30.1741],[-97.78528,30.17295],[-97.7915,30.15282],[-97.80038,30.15457]]],"type":"Polygon"},"id":"48453002437","properties":{"c":[30.16444,-97.79437],"geo_id":"48453002437","name":"Census Tract 24.37"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82588,30.15562],[-97.82,30.17389],[-97.79945,30.17256],[-97.80156,30.15214],[-97.82342,30.14831],[-97.82588,30.15562]]],"type":"Polygon"},"id":"48453002438","properties":{"c":[30.16206,-97.81262],"geo_id":"48453002438","name":"Census Tract 24.38"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76963,30.15935],[-97.76361,30.16917],[-97.75077,30.1647],[-97.74108,30.17298],[-97.73572,30.15558],[-97.76963,30.15935]]],"type":"Polygon"},"id":"48453002439","properties":{"c":[30.16292,-97.75113],"geo_id":"48453002439","name":"Census Tract 24.39"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76663,30.15828],[-97.75018,30.16053],[-97.73158,30.1505],[-97.7294,30.14208],[-97.74884,30.1134],[-97.76663,30.15828]]],"type":"Polygon"},"id":"48453002440","properties":{"c":[30.14176,-97.74817],"geo_id":"48453002440","name":"Census Tract 24.40"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77811,30.17941],[-97.77052,30.19054],[-97.75657,30.18518],[-97.7698,30.17767],[-97.7685,30.17053],[-97.77811,30.17941]]],"type":"Polygon"},"id":"48453002441","properties":{"c":[30.182,-97.76803],"geo_id":"48453002441","name":"Census Tract 24.41"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76278,30.17906],[-97.75657,30.18518],[-97.74682,30.1797],[-97.7522,30.17217],[-97.76278,30.17906]]],"type":"Polygon"},"id":"48453002442","properties":{"c":[30.17833,-97.75523],"geo_id":"48453002442","name":"Census Tract 24.42"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77712,30.19703],[-97.77192,30.21028],[-97.76165,30.20168],[-97.77052,30.19054],[-97.77712,30.19703]]],"type":"Polygon"},"id":"48453002443","properties":{"c":[30.19923,-97.77111],"geo_id":"48453002443","name":"Census Tract 24.43"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78568,30.20054],[-97.77867,30.21554],[-97.77204,30.2152],[-97.77885,30.19309],[-97.78568,30.20054]]],"type":"Polygon"},"id":"48453002444","properties":{"c":[30.20397,-97.7791],"geo_id":"48453002444","name":"Census Tract 24.44"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79591,30.14006],[-97.7915,30.15282],[-97.78126,30.14902],[-97.76963,30.15935],[-97.74884,30.1134],[-97.75626,30.1004],[-97.78529,30.11278],[-97.77535,30.12634],[-97.77796,30.14481],[-97.79591,30.14006]]],"type":"Polygon"},"id":"48453002445","properties":{"c":[30.12827,-97.76849],"geo_id":"48453002445","name":"Census Tract 24.45"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80435,30.11863],[-97.79603,30.13974],[-97.77796,30.14481],[-97.77362,30.13786],[-97.78181,30.11583],[-97.80687,30.11247],[-97.80435,30.11863]]],"type":"Polygon"},"id":"48453002446","properties":{"c":[30.12741,-97.78921],"geo_id":"48453002446","name":"Census Tract 24.46"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73508,30.21535],[-97.71234,30.21234],[-97.73226,30.19078],[-97.74044,30.20685],[-97.73508,30.21535]]],"type":"Polygon"},"id":"48453002447","properties":{"c":[30.2049,-97.72795],"geo_id":"48453002447","name":"Census Tract 24.47"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74629,30.1815],[-97.71234,30.21234],[-97.68329,30.22229],[-97.68427,30.19832],[-97.71333,30.18833],[-97.72984,30.15686],[-97.74629,30.1815]]],"type":"Polygon"},"id":"48453002448","properties":{"c":[30.19196,-97.71526],"geo_id":"48453002448","name":"Census Tract 24.48"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68918,30.17785],[-97.68775,30.183],[-97.65932,30.16736],[-97.64656,30.18062],[-97.61426,30.16522],[-97.62765,30.16374],[-97.65097,30.13383],[-97.69299,30.16425],[-97.68918,30.17785]]],"type":"Polygon"},"id":"48453002449","properties":{"c":[30.15966,-97.6563],"geo_id":"48453002449","name":"Census Tract 24.49"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65097,30.13383],[-97.62207,30.16485],[-97.568,30.14146],[-97.61078,30.10275],[-97.65097,30.13383]]],"type":"Polygon"},"id":"48453002450","properties":{"c":[30.13602,-97.61083],"geo_id":"48453002450","name":"Census Tract 24.50"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7915,30.15282],[-97.77811,30.17941],[-97.76408,30.16824],[-97.78126,30.14902],[-97.7915,30.15282]]],"type":"Polygon"},"id":"48453002451","properties":{"c":[30.16332,-97.7785],"geo_id":"48453002451","name":"Census Tract 24.51"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64669,30.19433],[-97.63821,30.20806],[-97.62275,30.2103],[-97.62525,30.19611],[-97.6098,30.18414],[-97.62312,30.16942],[-97.64656,30.18062],[-97.64669,30.19433]]],"type":"Polygon"},"id":"48453002452","properties":{"c":[30.18904,-97.63061],"geo_id":"48453002452","name":"Census Tract 24.52"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62328,30.19686],[-97.62275,30.2103],[-97.59648,30.22853],[-97.59081,30.20629],[-97.57589,30.2143],[-97.5565,30.20773],[-97.54167,30.22525],[-97.52714,30.21879],[-97.51995,30.22934],[-97.51324,30.2105],[-97.52878,30.20543],[-97.52372,30.19836],[-97.49125,30.21211],[-97.568,30.14146],[-97.62312,30.16942],[-97.60948,30.18621],[-97.62328,30.19686]]],"type":"Polygon"},"id":"48453002453","properties":{"c":[30.18777,-97.56873],"geo_id":"48453002453","name":"Census Tract 24.53"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76753,30.41225],[-97.75918,30.42929],[-97.74749,30.42229],[-97.74498,30.40788],[-97.76753,30.41225]]],"type":"Polygon"},"id":"48453002500","properties":{"c":[30.41664,-97.75514],"geo_id":"48453002500","name":"Census Tract 25"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79053,30.36186],[-97.7668,30.38512],[-97.75722,30.37157],[-97.76662,30.35965],[-97.79053,30.36186]]],"type":"Polygon"},"id":"48453030000","properties":{"c":[30.36986,-97.77395],"geo_id":"48453030000","name":"Census Tract 300"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7668,30.38512],[-97.74493,30.38961],[-97.7383,30.37999],[-97.7446,30.38324],[-97.75722,30.37157],[-97.7668,30.38512]]],"type":"Polygon"},"id":"48453030100","properties":{"c":[30.38252,-97.75519],"geo_id":"48453030100","name":"Census Tract 301"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75722,30.37157],[-97.7446,30.38324],[-97.73618,30.37868],[-97.74342,30.3613],[-97.75722,30.37157]]],"type":"Polygon"},"id":"48453030200","properties":{"c":[30.37283,-97.74632],"geo_id":"48453030200","name":"Census Tract 302"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80674,30.22121],[-97.80069,30.23275],[-97.78834,30.2299],[-97.79368,30.21358],[-97.80674,30.22121]]],"type":"Polygon"},"id":"48453030300","properties":{"c":[30.22385,-97.79725],"geo_id":"48453030300","name":"Census Tract 303"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81423,30.20935],[-97.80713,30.21901],[-97.79368,30.21358],[-97.80195,30.20152],[-97.81423,30.20935]]],"type":"Polygon"},"id":"48453030400","properties":{"c":[30.21077,-97.8053],"geo_id":"48453030400","name":"Census Tract 304"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84098,30.39537],[-97.82036,30.41583],[-97.7939,30.42009],[-97.77142,30.38276],[-97.79135,30.35929],[-97.80736,30.37965],[-97.84098,30.39537]]],"type":"Polygon"},"id":"48453030500","properties":{"c":[30.3935,-97.8026],"geo_id":"48453030500","name":"Census Tract 305"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77193,30.35169],[-97.76662,30.35965],[-97.74799,30.3516],[-97.75501,30.33623],[-97.76964,30.34132],[-97.77193,30.35169]]],"type":"Polygon"},"id":"48453030600","properties":{"c":[30.34827,-97.76101],"geo_id":"48453030600","name":"Census Tract 306"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79683,30.34999],[-97.78682,30.3628],[-97.76662,30.35965],[-97.77914,30.33262],[-97.79683,30.34999]]],"type":"Polygon"},"id":"48453030700","properties":{"c":[30.34942,-97.78104],"geo_id":"48453030700","name":"Census Tract 307"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76423,30.4093],[-97.74498,30.40788],[-97.74493,30.38961],[-97.75984,30.38825],[-97.75476,30.39486],[-97.76423,30.4093]]],"type":"Polygon"},"id":"48453030800","properties":{"c":[30.39884,-97.75297],"geo_id":"48453030800","name":"Census Tract 308"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83152,30.1931],[-97.81542,30.20728],[-97.80195,30.20152],[-97.81282,30.18558],[-97.83152,30.1931]]],"type":"Polygon"},"id":"48453030900","properties":{"c":[30.19573,-97.81655],"geo_id":"48453030900","name":"Census Tract 309"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83883,30.20086],[-97.8304,30.21388],[-97.81542,30.20728],[-97.83342,30.19096],[-97.84235,30.19534],[-97.83883,30.20086]]],"type":"Polygon"},"id":"48453031000","properties":{"c":[30.20274,-97.82939],"geo_id":"48453031000","name":"Census Tract 310"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.96757,30.21224],[-97.9358,30.23027],[-97.8883,30.2292],[-97.89977,30.20983],[-97.91756,30.20317],[-97.92881,30.1817],[-97.96757,30.21224]]],"type":"Polygon"},"id":"48453031100","properties":{"c":[30.21342,-97.92916],"geo_id":"48453031100","name":"Census Tract 311"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87628,30.2137],[-97.86448,30.23002],[-97.83659,30.22031],[-97.86116,30.20818],[-97.87628,30.2137]]],"type":"Polygon"},"id":"48453031200","properties":{"c":[30.21869,-97.85979],"geo_id":"48453031200","name":"Census Tract 312"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86957,30.19587],[-97.86116,30.20818],[-97.84304,30.19431],[-97.85981,30.1691],[-97.86095,30.18858],[-97.86957,30.19587]]],"type":"Polygon"},"id":"48453031300","properties":{"c":[30.19008,-97.85712],"geo_id":"48453031300","name":"Census Tract 313"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.96205,30.38246],[-97.94056,30.4009],[-97.95147,30.42036],[-97.94888,30.43249],[-97.93139,30.43724],[-97.91546,30.42951],[-97.89998,30.39424],[-97.9308,30.39735],[-97.94716,30.37432],[-97.96205,30.38246]]],"type":"Polygon"},"id":"48453031400","properties":{"c":[30.41036,-97.93048],"geo_id":"48453031400","name":"Census Tract 314"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.96975,30.3388],[-97.94056,30.38974],[-97.92888,30.39761],[-97.91094,30.39326],[-97.91679,30.3544],[-97.93405,30.33645],[-97.95579,30.34319],[-97.96435,30.32758],[-97.96975,30.3388]]],"type":"Polygon"},"id":"48453031500","properties":{"c":[30.36462,-97.93578],"geo_id":"48453031500","name":"Census Tract 315"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75208,30.42863],[-97.73588,30.43736],[-97.72888,30.4327],[-97.72918,30.41157],[-97.75208,30.42863]]],"type":"Polygon"},"id":"48453031600","properties":{"c":[30.42441,-97.73784],"geo_id":"48453031600","name":"Census Tract 316"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84304,30.19431],[-97.82535,30.19033],[-97.83399,30.17663],[-97.84975,30.18361],[-97.84304,30.19431]]],"type":"Polygon"},"id":"48453031700","properties":{"c":[30.18605,-97.83825],"geo_id":"48453031700","name":"Census Tract 317"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83524,30.17673],[-97.82535,30.19033],[-97.81282,30.18558],[-97.82,30.17389],[-97.83524,30.17673]]],"type":"Polygon"},"id":"48453031800","properties":{"c":[30.1808,-97.82453],"geo_id":"48453031800","name":"Census Tract 318"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85778,30.17109],[-97.84975,30.18361],[-97.82,30.17389],[-97.82588,30.15562],[-97.85778,30.17109]]],"type":"Polygon"},"id":"48453031900","properties":{"c":[30.17022,-97.83912],"geo_id":"48453031900","name":"Census Tract 319"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86478,30.23406],[-97.84255,30.23675],[-97.82472,30.23564],[-97.83659,30.22031],[-97.86478,30.23406]]],"type":"Polygon"},"id":"48453032000","properties":{"c":[30.23051,-97.84417],"geo_id":"48453032000","name":"Census Tract 320"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83659,30.22031],[-97.82472,30.23564],[-97.80069,30.23275],[-97.81542,30.20728],[-97.83659,30.22031]]],"type":"Polygon"},"id":"48453032100","properties":{"c":[30.22279,-97.81907],"geo_id":"48453032100","name":"Census Tract 321"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76369,30.36439],[-97.75722,30.37157],[-97.74927,30.36384],[-97.75662,30.35517],[-97.76662,30.35965],[-97.76369,30.36439]]],"type":"Polygon"},"id":"48453032200","properties":{"c":[30.36288,-97.75772],"geo_id":"48453032200","name":"Census Tract 322"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.755,30.35692],[-97.75054,30.36364],[-97.74342,30.3613],[-97.74799,30.3516],[-97.755,30.35692]]],"type":"Polygon"},"id":"48453032300","properties":{"c":[30.35762,-97.7498],"geo_id":"48453032300","name":"Census Tract 323"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74632,30.39405],[-97.74575,30.40034],[-97.72961,30.39438],[-97.73618,30.37868],[-97.74632,30.39405]]],"type":"Polygon"},"id":"48453032400","properties":{"c":[30.39077,-97.73872],"geo_id":"48453032400","name":"Census Tract 324"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7467,30.41907],[-97.72918,30.41157],[-97.72961,30.39438],[-97.74575,30.40034],[-97.7467,30.41907]]],"type":"Polygon"},"id":"48453032500","properties":{"c":[30.4065,-97.7371],"geo_id":"48453032500","name":"Census Tract 325"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7951,30.41721],[-97.78299,30.42828],[-97.76352,30.41868],[-97.76996,30.40766],[-97.7668,30.38512],[-97.77142,30.38276],[-97.7951,30.41721]]],"type":"Polygon"},"id":"48453032600","properties":{"c":[30.40925,-97.77851],"geo_id":"48453032600","name":"Census Tract 326"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78276,30.42884],[-97.76799,30.43257],[-97.75918,30.42929],[-97.77008,30.41739],[-97.78276,30.42884]]],"type":"Polygon"},"id":"48453032700","properties":{"c":[30.4261,-97.76979],"geo_id":"48453032700","name":"Census Tract 327"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76996,30.40766],[-97.75985,30.40621],[-97.76284,30.39858],[-97.75476,30.39486],[-97.7668,30.38512],[-97.76996,30.40766]]],"type":"Polygon"},"id":"48453032800","properties":{"c":[30.39773,-97.76388],"geo_id":"48453032800","name":"Census Tract 328"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86422,30.35781],[-97.84547,30.39454],[-97.80736,30.37965],[-97.79135,30.35929],[-97.83588,30.32392],[-97.85063,30.35129],[-97.86422,30.35781]]],"type":"Polygon"},"id":"48453032900","properties":{"c":[30.36109,-97.83024],"geo_id":"48453032900","name":"Census Tract 329"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92727,30.24628],[-97.90724,30.26013],[-97.87261,30.23394],[-97.89421,30.22994],[-97.92727,30.24628]]],"type":"Polygon"},"id":"48453033000","properties":{"c":[30.24268,-97.90128],"geo_id":"48453033000","name":"Census Tract 330"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.0036,30.37382],[-97.98959,30.37747],[-97.96472,30.39401],[-97.97022,30.37473],[-97.98135,30.3676],[-97.97889,30.35766],[-97.99532,30.35222],[-98.0036,30.37382]]],"type":"Polygon"},"id":"48453033100","properties":{"c":[30.37213,-97.98468],"geo_id":"48453033100","name":"Census Tract 331"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85786,30.13064],[-97.8471,30.14946],[-97.8332,30.14983],[-97.82828,30.1592],[-97.83299,30.1128],[-97.85786,30.13064]]],"type":"Polygon"},"id":"48453033200","properties":{"c":[30.13595,-97.83934],"geo_id":"48453033200","name":"Census Tract 332"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92886,30.1862],[-97.9252,30.1924],[-97.88939,30.17342],[-97.88078,30.1809],[-97.86174,30.17739],[-97.86201,30.14988],[-97.8471,30.14946],[-97.84661,30.14103],[-97.85786,30.13064],[-97.92886,30.1862]]],"type":"Polygon"},"id":"48453033300","properties":{"c":[30.16332,-97.88365],"geo_id":"48453033300","name":"Census Tract 333"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85095,30.21398],[-97.83659,30.22031],[-97.8304,30.21388],[-97.83744,30.20313],[-97.85095,30.21398]]],"type":"Polygon"},"id":"48453033400","properties":{"c":[30.21189,-97.84045],"geo_id":"48453033400","name":"Census Tract 334"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86116,30.20818],[-97.84812,30.21677],[-97.84888,30.2093],[-97.83744,30.20313],[-97.84304,30.19431],[-97.86116,30.20818]]],"type":"Polygon"},"id":"48453033500","properties":{"c":[30.20467,-97.84974],"geo_id":"48453033500","name":"Census Tract 335"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.98135,30.3676],[-97.97022,30.37473],[-97.96472,30.39401],[-97.95495,30.39381],[-97.96205,30.38246],[-97.94716,30.37432],[-97.96975,30.3388],[-97.98135,30.3676]]],"type":"Polygon"},"id":"48453033600","properties":{"c":[30.36658,-97.96521],"geo_id":"48453033600","name":"Census Tract 336"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80674,30.43759],[-97.80402,30.44716],[-97.77997,30.43873],[-97.79857,30.43836],[-97.80332,30.43069],[-97.80674,30.43759]]],"type":"Polygon"},"id":"48453033700","properties":{"c":[30.4398,-97.79645],"geo_id":"48453033700","name":"Census Tract 337"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8058,30.4313],[-97.79857,30.43836],[-97.77997,30.43873],[-97.77729,30.43195],[-97.80163,30.41968],[-97.8058,30.4313]]],"type":"Polygon"},"id":"48453033800","properties":{"c":[30.42935,-97.7931],"geo_id":"48453033800","name":"Census Tract 338"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89392,30.31491],[-97.8904,30.34238],[-97.86197,30.35427],[-97.85063,30.35129],[-97.84519,30.3404],[-97.85488,30.31422],[-97.87737,30.31644],[-97.89374,30.30799],[-97.89392,30.31491]]],"type":"Polygon"},"id":"48453033900","properties":{"c":[30.33228,-97.86979],"geo_id":"48453033900","name":"Census Tract 339"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.96435,30.32758],[-97.96168,30.33894],[-97.95109,30.3441],[-97.92469,30.326],[-97.88948,30.33913],[-97.89209,30.30986],[-97.89962,30.3061],[-97.91338,30.31076],[-97.93618,30.3051],[-97.96435,30.32758]]],"type":"Polygon"},"id":"48453034000","properties":{"c":[30.32349,-97.92527],"geo_id":"48453034000","name":"Census Tract 340"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75466,30.44022],[-97.7468,30.44935],[-97.72115,30.45584],[-97.72888,30.4327],[-97.75466,30.44022]]],"type":"Polygon"},"id":"48453034100","properties":{"c":[30.44441,-97.73605],"geo_id":"48453034100","name":"Census Tract 341"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76561,30.43241],[-97.74965,30.44117],[-97.73588,30.43736],[-97.75362,30.42651],[-97.76561,30.43241]]],"type":"Polygon"},"id":"48453034200","properties":{"c":[30.43364,-97.74863],"geo_id":"48453034200","name":"Census Tract 342"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83027,30.43668],[-97.82307,30.45344],[-97.80402,30.44716],[-97.80598,30.42305],[-97.79379,30.42007],[-97.81358,30.4229],[-97.81576,30.43949],[-97.83027,30.43668]]],"type":"Polygon"},"id":"48453034300","properties":{"c":[30.43675,-97.81372],"geo_id":"48453034300","name":"Census Tract 343"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84137,30.4328],[-97.83352,30.4427],[-97.82572,30.4556],[-97.82882,30.43407],[-97.84137,30.4328]]],"type":"Polygon"},"id":"48453034400","properties":{"c":[30.44098,-97.83157],"geo_id":"48453034400","name":"Census Tract 344"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83657,30.43042],[-97.82072,30.43951],[-97.81415,30.43691],[-97.81472,30.42466],[-97.83657,30.43042]]],"type":"Polygon"},"id":"48453034500","properties":{"c":[30.43256,-97.82156],"geo_id":"48453034500","name":"Census Tract 345"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85402,30.40378],[-97.84268,30.42878],[-97.80789,30.42129],[-97.8388,30.39505],[-97.85402,30.40378]]],"type":"Polygon"},"id":"48453034600","properties":{"c":[30.41353,-97.83459],"geo_id":"48453034600","name":"Census Tract 346"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89397,30.21919],[-97.8883,30.2292],[-97.86478,30.23406],[-97.88139,30.21025],[-97.88941,30.2087],[-97.89397,30.21919]]],"type":"Polygon"},"id":"48453034700","properties":{"c":[30.22248,-97.88088],"geo_id":"48453034700","name":"Census Tract 347"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90286,30.2093],[-97.89433,30.21829],[-97.88941,30.2087],[-97.87782,30.21706],[-97.86116,30.20818],[-97.86957,30.19587],[-97.90286,30.2093]]],"type":"Polygon"},"id":"48453034800","properties":{"c":[30.20601,-97.88112],"geo_id":"48453034800","name":"Census Tract 348"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.91448,30.38478],[-97.90935,30.39108],[-97.88226,30.38979],[-97.88839,30.3709],[-97.90866,30.35606],[-97.91448,30.38478]]],"type":"Polygon"},"id":"48453034900","properties":{"c":[30.37633,-97.90054],"geo_id":"48453034900","name":"Census Tract 349"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90936,30.3556],[-97.88839,30.3709],[-97.88226,30.38979],[-97.85402,30.40378],[-97.84547,30.39454],[-97.86315,30.35367],[-97.87442,30.34617],[-97.89691,30.3409],[-97.90936,30.3556]]],"type":"Polygon"},"id":"48453035000","properties":{"c":[30.36887,-97.87631],"geo_id":"48453035000","name":"Census Tract 350"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.93405,30.33645],[-97.91309,30.36298],[-97.89691,30.3409],[-97.91789,30.3266],[-97.93405,30.33645]]],"type":"Polygon"},"id":"48453035100","properties":{"c":[30.34041,-97.91689],"geo_id":"48453035100","name":"Census Tract 351"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.0914,30.4303],[-98.08299,30.43719],[-98.0857,30.44827],[-98.06829,30.42886],[-98.05064,30.43511],[-98.03458,30.45008],[-98.02378,30.47626],[-98.01216,30.48058],[-97.9994,30.45706],[-98.03185,30.43224],[-98.03667,30.41842],[-97.98676,30.41462],[-97.98411,30.40791],[-98.01479,30.38212],[-98.02174,30.36182],[-98.03938,30.35412],[-98.04239,30.38678],[-98.06989,30.42188],[-98.0914,30.4303]]],"type":"Polygon"},"id":"48453035200","properties":{"c":[30.41683,-98.03185],"geo_id":"48453035200","name":"Census Tract 352"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.12556,30.42619],[-98.09771,30.46763],[-98.09779,30.49744],[-98.08169,30.49568],[-98.09013,30.47015],[-98.05717,30.45879],[-98.05419,30.45091],[-98.06328,30.44199],[-98.05552,30.43306],[-98.06956,30.42941],[-98.0857,30.44827],[-98.08299,30.43719],[-98.09068,30.42786],[-98.06989,30.42188],[-98.03752,30.36963],[-98.06747,30.35647],[-98.0869,30.3943],[-98.12556,30.42619]]],"type":"Polygon"},"id":"48453035300","properties":{"c":[30.42201,-98.08188],"geo_id":"48453035300","name":"Census Tract 353"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.06747,30.35647],[-98.03878,30.36817],[-98.03938,30.35412],[-98.0307,30.35466],[-98.01485,30.37445],[-98.0036,30.37382],[-97.99394,30.35156],[-97.99759,30.32903],[-98.01211,30.32394],[-98.06747,30.35647]]],"type":"Polygon"},"id":"48453035400","properties":{"c":[30.34957,-98.0236],"geo_id":"48453035400","name":"Census Tract 354"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86353,30.48859],[-97.85922,30.4933],[-97.845,30.4693],[-97.8565,30.47057],[-97.86353,30.48859]]],"type":"Polygon"},"id":"48453035500","properties":{"c":[30.47918,-97.85434],"geo_id":"48453035500","name":"Census Tract 355"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92577,30.45327],[-97.91053,30.46551],[-97.885,30.5123],[-97.8594,30.51192],[-97.86411,30.48557],[-97.85476,30.46886],[-97.86253,30.45691],[-97.85865,30.4471],[-97.88232,30.42835],[-97.91109,30.42222],[-97.92577,30.45327]]],"type":"Polygon"},"id":"48453035600","properties":{"c":[30.46553,-97.88731],"geo_id":"48453035600","name":"Census Tract 356"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86253,30.45691],[-97.84627,30.4732],[-97.83201,30.46187],[-97.8426,30.46221],[-97.85804,30.4483],[-97.86253,30.45691]]],"type":"Polygon"},"id":"48453035700","properties":{"c":[30.46044,-97.85082],"geo_id":"48453035700","name":"Census Tract 357"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90829,30.42267],[-97.876,30.43202],[-97.8426,30.46221],[-97.82572,30.4556],[-97.85859,30.3969],[-97.90641,30.38758],[-97.89943,30.39524],[-97.90829,30.42267]]],"type":"Polygon"},"id":"48453035800","properties":{"c":[30.42117,-97.86895],"geo_id":"48453035800","name":"Census Tract 358"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04989,30.62416],[-98.0365,30.61173],[-98.01274,30.61677],[-98.00628,30.62752],[-97.9924,30.60949],[-97.95673,30.62825],[-97.91706,30.60487],[-97.9219,30.59096],[-97.91512,30.58057],[-97.92698,30.56765],[-97.90246,30.57133],[-97.88678,30.55584],[-97.89845,30.54864],[-97.91558,30.56301],[-97.91868,30.53668],[-97.92835,30.52745],[-97.9388,30.53465],[-97.94599,30.55881],[-97.96069,30.56529],[-97.9527,30.57126],[-97.95758,30.57674],[-98.05674,30.61138],[-98.04989,30.62416]]],"type":"Polygon"},"id":"48453035900","properties":{"c":[30.5887,-97.96033],"geo_id":"48453035900","name":"Census Tract 359"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.91807,30.55506],[-97.91558,30.56301],[-97.89845,30.54864],[-97.88678,30.55584],[-97.87365,30.54944],[-97.89595,30.52795],[-97.91807,30.55506]]],"type":"Polygon"},"id":"48453036000","properties":{"c":[30.54537,-97.89712],"geo_id":"48453036000","name":"Census Tract 360"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8954,30.52401],[-97.87365,30.54944],[-97.86787,30.5465],[-97.87142,30.52271],[-97.8594,30.51192],[-97.885,30.5123],[-97.8954,30.52401]]],"type":"Polygon"},"id":"48453036100","properties":{"c":[30.5286,-97.87955],"geo_id":"48453036100","name":"Census Tract 361"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92784,30.52789],[-97.91669,30.54686],[-97.8969,30.53584],[-97.8954,30.52401],[-97.91168,30.51115],[-97.92784,30.52789]]],"type":"Polygon"},"id":"48453036200","properties":{"c":[30.52901,-97.91177],"geo_id":"48453036200","name":"Census Tract 362"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.10126,30.52848],[-98.05674,30.61138],[-97.95758,30.57674],[-97.9527,30.57126],[-97.96069,30.56529],[-97.94599,30.55881],[-97.9388,30.53465],[-97.91168,30.51115],[-97.91642,30.50304],[-97.97954,30.50607],[-97.97902,30.49588],[-97.99727,30.50726],[-98.02987,30.50587],[-98.05325,30.52288],[-98.07284,30.51921],[-98.10126,30.52848]]],"type":"Polygon"},"id":"48453036300","properties":{"c":[30.5476,-98.01174],"geo_id":"48453036300","name":"Census Tract 363"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.12313,30.48704],[-98.10126,30.52848],[-98.07284,30.51921],[-98.05325,30.52288],[-98.02987,30.50587],[-97.99727,30.50726],[-97.97902,30.49588],[-97.97954,30.50607],[-97.9196,30.50286],[-97.93207,30.48261],[-97.96933,30.47077],[-97.9935,30.48238],[-98.00303,30.4739],[-98.01965,30.47999],[-98.03629,30.44768],[-98.05552,30.43306],[-98.06328,30.44199],[-98.05419,30.45091],[-98.05717,30.45879],[-98.09013,30.47015],[-98.08169,30.49568],[-98.10086,30.49746],[-98.11372,30.48558],[-98.12313,30.48704]]],"type":"Polygon"},"id":"48453036400","properties":{"c":[30.48906,-98.03249],"geo_id":"48453036400","name":"Census Tract 364"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.15927,30.37665],[-98.12799,30.42262],[-98.09399,30.40224],[-98.06119,30.34927],[-98.004,30.3181],[-97.96538,30.30996],[-97.99213,30.30772],[-98.01952,30.29082],[-98.08075,30.29067],[-98.17298,30.35631],[-98.15927,30.37665]]],"type":"Polygon"},"id":"48453036500","properties":{"c":[30.34401,-98.08889],"geo_id":"48453036500","name":"Census Tract 365"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.08,30.29205],[-98.06288,30.28582],[-98.01952,30.29082],[-97.99213,30.30772],[-97.94397,30.30818],[-97.91763,30.28918],[-97.90724,30.26013],[-97.92727,30.24628],[-97.91108,30.2345],[-97.93812,30.2296],[-97.96934,30.21067],[-98.08,30.29205]]],"type":"Polygon"},"id":"48453036600","properties":{"c":[30.2667,-97.977],"geo_id":"48453036600","name":"Census Tract 366"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.9241,30.19367],[-97.90751,30.20996],[-97.88017,30.19645],[-97.90013,30.18103],[-97.9241,30.19367]]],"type":"Polygon"},"id":"48453036700","properties":{"c":[30.19569,-97.90369],"geo_id":"48453036700","name":"Census Tract 367"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89895,30.18286],[-97.87478,30.1981],[-97.86554,30.1947],[-97.85846,30.17693],[-97.88078,30.1809],[-97.88939,30.17342],[-97.89895,30.18286]]],"type":"Polygon"},"id":"48453036800","properties":{"c":[30.18563,-97.87876],"geo_id":"48453036800","name":"Census Tract 368"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.0006,30.33244],[-97.99394,30.35156],[-97.97889,30.35766],[-97.97061,30.33616],[-98.0006,30.33244]]],"type":"Polygon"},"id":"48453036900","properties":{"c":[30.3428,-97.98577],"geo_id":"48453036900","name":"Census Tract 369"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.00654,30.32577],[-97.96975,30.3388],[-97.94536,30.30848],[-98.004,30.3181],[-98.01211,30.32394],[-98.00654,30.32577]]],"type":"Polygon"},"id":"48453037000","properties":{"c":[30.32167,-97.97585],"geo_id":"48453037000","name":"Census Tract 370"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86282,30.15624],[-97.85981,30.1691],[-97.8503,30.16949],[-97.85486,30.14848],[-97.86282,30.15624]]],"type":"Polygon"},"id":"48453037100","properties":{"c":[30.1588,-97.85682],"geo_id":"48453037100","name":"Census Tract 371"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85689,30.15267],[-97.8503,30.16949],[-97.832,30.16202],[-97.8332,30.14983],[-97.85689,30.15267]]],"type":"Polygon"},"id":"48453037200","properties":{"c":[30.1563,-97.8441],"geo_id":"48453037200","name":"Census Tract 372"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.00765,30.4503],[-97.99874,30.45879],[-98.00303,30.4739],[-97.99722,30.48173],[-97.97472,30.47618],[-97.97736,30.43277],[-97.99269,30.43474],[-98.00765,30.4503]]],"type":"Polygon"},"id":"48453037300","properties":{"c":[30.4573,-97.99042],"geo_id":"48453037300","name":"Census Tract 373"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.03706,30.4201],[-98.01189,30.44918],[-97.98716,30.43614],[-97.98988,30.41484],[-98.03706,30.4201]]],"type":"Polygon"},"id":"48453037400","properties":{"c":[30.4282,-98.01091],"geo_id":"48453037400","name":"Census Tract 374"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92726,30.48929],[-97.90581,30.51796],[-97.885,30.5123],[-97.91016,30.46929],[-97.92726,30.48929]]],"type":"Polygon"},"id":"48453037500","properties":{"c":[30.49895,-97.90552],"geo_id":"48453037500","name":"Census Tract 375"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.01581,30.37969],[-97.98503,30.40481],[-97.98966,30.43012],[-97.98716,30.43614],[-97.97736,30.43277],[-97.97642,30.47286],[-97.92726,30.48929],[-97.91905,30.48551],[-97.90964,30.4674],[-97.92476,30.45743],[-97.91998,30.43297],[-97.93866,30.43732],[-97.95187,30.42671],[-97.94083,30.40417],[-97.944,30.39466],[-97.96956,30.39366],[-98.00942,30.37112],[-98.01581,30.37969]]],"type":"Polygon"},"id":"48453037600","properties":{"c":[30.43335,-97.96023],"geo_id":"48453037600","name":"Census Tract 376"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71308,30.34684],[-97.69689,30.3445],[-97.70428,30.33283],[-97.71782,30.33941],[-97.71308,30.34684]]],"type":"Polygon"},"id":"48453040000","properties":{"c":[30.34191,-97.70732],"geo_id":"48453040000","name":"Census Tract 400"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71798,30.36553],[-97.71732,30.3656],[-97.70011,30.35765],[-97.71244,30.3478],[-97.71798,30.36553]]],"type":"Polygon"},"id":"48453040100","properties":{"c":[30.3572,-97.71031],"geo_id":"48453040100","name":"Census Tract 401"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69505,30.32187],[-97.68638,30.33262],[-97.67323,30.32572],[-97.68488,30.32186],[-97.69505,30.32187]]],"type":"Polygon"},"id":"48453040200","properties":{"c":[30.32616,-97.68501],"geo_id":"48453040200","name":"Census Tract 402"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70016,30.33932],[-97.68811,30.35826],[-97.676,30.35084],[-97.68638,30.33262],[-97.70016,30.33932]]],"type":"Polygon"},"id":"48453040300","properties":{"c":[30.34511,-97.68754],"geo_id":"48453040300","name":"Census Tract 403"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74342,30.3613],[-97.73618,30.37868],[-97.7263,30.37323],[-97.7309,30.35615],[-97.74342,30.3613]]],"type":"Polygon"},"id":"48453040400","properties":{"c":[30.3666,-97.73468],"geo_id":"48453040400","name":"Census Tract 404"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72934,30.36185],[-97.7263,30.37323],[-97.72043,30.37044],[-97.71308,30.34684],[-97.7309,30.35615],[-97.72934,30.36185]]],"type":"Polygon"},"id":"48453040500","properties":{"c":[30.36015,-97.72219],"geo_id":"48453040500","name":"Census Tract 405"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70833,30.36341],[-97.7055,30.36925],[-97.696,30.36487],[-97.70011,30.35765],[-97.70833,30.36341]]],"type":"Polygon"},"id":"48453040600","properties":{"c":[30.36341,-97.70264],"geo_id":"48453040600","name":"Census Tract 406"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72372,30.37274],[-97.71923,30.38196],[-97.7055,30.36925],[-97.7097,30.36202],[-97.72372,30.37274]]],"type":"Polygon"},"id":"48453040700","properties":{"c":[30.37178,-97.71483],"geo_id":"48453040700","name":"Census Tract 407"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71923,30.38196],[-97.71628,30.39328],[-97.6979,30.38271],[-97.7055,30.36925],[-97.71923,30.38196]]],"type":"Polygon"},"id":"48453040800","properties":{"c":[30.38096,-97.7086],"geo_id":"48453040800","name":"Census Tract 408"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70409,30.37148],[-97.6979,30.38271],[-97.68768,30.37954],[-97.696,30.36487],[-97.70409,30.37148]]],"type":"Polygon"},"id":"48453040900","properties":{"c":[30.3742,-97.69634],"geo_id":"48453040900","name":"Census Tract 409"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.696,30.36487],[-97.68638,30.38193],[-97.67616,30.37706],[-97.68811,30.35826],[-97.696,30.36487]]],"type":"Polygon"},"id":"48453041000","properties":{"c":[30.37011,-97.68688],"geo_id":"48453041000","name":"Census Tract 410"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68574,30.38304],[-97.68052,30.39512],[-97.67256,30.38838],[-97.67616,30.37706],[-97.68574,30.38304]]],"type":"Polygon"},"id":"48453041100","properties":{"c":[30.38508,-97.67919],"geo_id":"48453041100","name":"Census Tract 411"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69707,30.40828],[-97.69058,30.41331],[-97.67472,30.40799],[-97.67256,30.38838],[-97.69707,30.40828]]],"type":"Polygon"},"id":"48453041200","properties":{"c":[30.40227,-97.68305],"geo_id":"48453041200","name":"Census Tract 412"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73015,30.42597],[-97.72888,30.4327],[-97.71352,30.42486],[-97.72918,30.41157],[-97.73015,30.42597]]],"type":"Polygon"},"id":"48453041300","properties":{"c":[30.42158,-97.72371],"geo_id":"48453041300","name":"Census Tract 413"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72204,30.41163],[-97.71352,30.42486],[-97.70434,30.42057],[-97.71191,30.40997],[-97.72204,30.41163]]],"type":"Polygon"},"id":"48453041400","properties":{"c":[30.4164,-97.71283],"geo_id":"48453041400","name":"Census Tract 414"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67616,30.37706],[-97.66784,30.38789],[-97.66055,30.37528],[-97.66582,30.37246],[-97.67616,30.37706]]],"type":"Polygon"},"id":"48453041500","properties":{"c":[30.38015,-97.6688],"geo_id":"48453041500","name":"Census Tract 415"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68811,30.35826],[-97.67616,30.37706],[-97.66582,30.37246],[-97.676,30.35084],[-97.68811,30.35826]]],"type":"Polygon"},"id":"48453041600","properties":{"c":[30.36403,-97.67645],"geo_id":"48453041600","name":"Census Tract 416"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71047,30.38878],[-97.7083,30.39241],[-97.68904,30.39068],[-97.6979,30.38271],[-97.71047,30.38878]]],"type":"Polygon"},"id":"48453041700","properties":{"c":[30.38847,-97.7001],"geo_id":"48453041700","name":"Census Tract 417"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70487,30.39777],[-97.70035,30.40317],[-97.69502,30.39797],[-97.70163,30.38947],[-97.7083,30.39241],[-97.70487,30.39777]]],"type":"Polygon"},"id":"48453041800","properties":{"c":[30.39599,-97.70141],"geo_id":"48453041800","name":"Census Tract 418"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69857,30.40429],[-97.68052,30.39512],[-97.68768,30.37954],[-97.6979,30.38271],[-97.68904,30.39068],[-97.69881,30.39208],[-97.69857,30.40429]]],"type":"Polygon"},"id":"48453041900","properties":{"c":[30.39242,-97.69045],"geo_id":"48453041900","name":"Census Tract 419"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72796,30.43764],[-97.72072,30.45313],[-97.6985,30.44044],[-97.70434,30.42057],[-97.72796,30.43764]]],"type":"Polygon"},"id":"48453042000","properties":{"c":[30.43597,-97.71374],"geo_id":"48453042000","name":"Census Tract 420"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70434,30.42057],[-97.70192,30.42779],[-97.68855,30.4156],[-97.67159,30.42442],[-97.67472,30.40799],[-97.70434,30.42057]]],"type":"Polygon"},"id":"48453042100","properties":{"c":[30.41805,-97.68563],"geo_id":"48453042100","name":"Census Tract 421"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71108,30.41046],[-97.70434,30.42057],[-97.69058,30.41331],[-97.69774,30.40598],[-97.71108,30.41046]]],"type":"Polygon"},"id":"48453042200","properties":{"c":[30.41193,-97.70176],"geo_id":"48453042200","name":"Census Tract 422"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6866,30.4458],[-97.67639,30.45397],[-97.67497,30.43595],[-97.68413,30.43704],[-97.6866,30.4458]]],"type":"Polygon"},"id":"48453042300","properties":{"c":[30.44413,-97.6801],"geo_id":"48453042300","name":"Census Tract 423"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64534,30.35251],[-97.6131,30.36839],[-97.57614,30.41701],[-97.54608,30.40091],[-97.5414,30.40748],[-97.52001,30.3978],[-97.5385,30.3494],[-97.644,30.32954],[-97.64534,30.35251]]],"type":"Polygon"},"id":"48453042400","properties":{"c":[30.36978,-97.57934],"geo_id":"48453042400","name":"Census Tract 424"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57867,30.42019],[-97.5405,30.47864],[-97.52397,30.47218],[-97.51086,30.48526],[-97.46692,30.46519],[-97.47911,30.4395],[-97.49695,30.43294],[-97.52001,30.3978],[-97.5414,30.40748],[-97.54608,30.40091],[-97.57867,30.42019]]],"type":"Polygon"},"id":"48453042500","properties":{"c":[30.44204,-97.5241],"geo_id":"48453042500","name":"Census Tract 425"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65604,30.44892],[-97.64816,30.46084],[-97.63596,30.45548],[-97.63915,30.44744],[-97.65604,30.44892]]],"type":"Polygon"},"id":"48453042600","properties":{"c":[30.45249,-97.64595],"geo_id":"48453042600","name":"Census Tract 426"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64754,30.46136],[-97.64123,30.47233],[-97.62988,30.46701],[-97.63596,30.45548],[-97.64754,30.46136]]],"type":"Polygon"},"id":"48453042700","properties":{"c":[30.46379,-97.63907],"geo_id":"48453042700","name":"Census Tract 427"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63924,30.44868],[-97.62988,30.46701],[-97.61604,30.45915],[-97.62003,30.43949],[-97.63924,30.44868]]],"type":"Polygon"},"id":"48453042800","properties":{"c":[30.45314,-97.62668],"geo_id":"48453042800","name":"Census Tract 428"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68634,30.43546],[-97.67719,30.43505],[-97.66851,30.44059],[-97.67159,30.42442],[-97.68634,30.43546]]],"type":"Polygon"},"id":"48453042900","properties":{"c":[30.43235,-97.67632],"geo_id":"48453042900","name":"Census Tract 429"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72115,30.45584],[-97.69459,30.4615],[-97.6955,30.44981],[-97.68413,30.43704],[-97.71212,30.44529],[-97.72115,30.45584]]],"type":"Polygon"},"id":"48453043000","properties":{"c":[30.44905,-97.70181],"geo_id":"48453043000","name":"Census Tract 430"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70011,30.35765],[-97.69695,30.36316],[-97.68811,30.35826],[-97.6936,30.3497],[-97.70011,30.35765]]],"type":"Polygon"},"id":"48453043100","properties":{"c":[30.3568,-97.6946],"geo_id":"48453043100","name":"Census Tract 431"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70915,30.35081],[-97.70036,30.35731],[-97.6936,30.3497],[-97.69689,30.3445],[-97.70915,30.35081]]],"type":"Polygon"},"id":"48453043200","properties":{"c":[30.35059,-97.70064],"geo_id":"48453043200","name":"Census Tract 432"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70016,30.33932],[-97.68638,30.33262],[-97.69238,30.3261],[-97.70428,30.33283],[-97.70016,30.33932]]],"type":"Polygon"},"id":"48453043300","properties":{"c":[30.33294,-97.69566],"geo_id":"48453043300","name":"Census Tract 433"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70664,30.32436],[-97.70428,30.33283],[-97.69238,30.3261],[-97.69539,30.32147],[-97.70664,30.32436]]],"type":"Polygon"},"id":"48453043400","properties":{"c":[30.3263,-97.70029],"geo_id":"48453043400","name":"Census Tract 434"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67723,30.34692],[-97.6663,30.37196],[-97.64412,30.38393],[-97.64534,30.35251],[-97.66306,30.34191],[-97.67723,30.34692]]],"type":"Polygon"},"id":"48453043500","properties":{"c":[30.36216,-97.65901],"geo_id":"48453043500","name":"Census Tract 435"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68605,30.33311],[-97.67755,30.34582],[-97.66306,30.34191],[-97.64534,30.35251],[-97.644,30.32954],[-97.67323,30.32572],[-97.68605,30.33311]]],"type":"Polygon"},"id":"48453043600","properties":{"c":[30.3379,-97.66219],"geo_id":"48453043600","name":"Census Tract 436"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67269,30.39907],[-97.65905,30.39082],[-97.66039,30.3888],[-97.67256,30.38838],[-97.67269,30.39907]]],"type":"Polygon"},"id":"48453043700","properties":{"c":[30.39229,-97.66734],"geo_id":"48453043700","name":"Census Tract 437"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.66696,30.38749],[-97.65905,30.39082],[-97.64869,30.38691],[-97.66055,30.37528],[-97.66696,30.38749]]],"type":"Polygon"},"id":"48453043800","properties":{"c":[30.38379,-97.65827],"geo_id":"48453043800","name":"Census Tract 438"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67159,30.42442],[-97.6385,30.40375],[-97.64869,30.38691],[-97.65734,30.40216],[-97.67472,30.40799],[-97.67159,30.42442]]],"type":"Polygon"},"id":"48453043900","properties":{"c":[30.40721,-97.65726],"geo_id":"48453043900","name":"Census Tract 439"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67472,30.40799],[-97.65734,30.40216],[-97.65092,30.3882],[-97.67359,30.39929],[-97.67472,30.40799]]],"type":"Polygon"},"id":"48453044000","properties":{"c":[30.39862,-97.66314],"geo_id":"48453044000","name":"Census Tract 440"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.666,30.44186],[-97.66001,30.44962],[-97.63915,30.44744],[-97.64476,30.42879],[-97.666,30.44186]]],"type":"Polygon"},"id":"48453044100","properties":{"c":[30.4408,-97.65274],"geo_id":"48453044100","name":"Census Tract 441"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67159,30.42442],[-97.66851,30.44059],[-97.65283,30.43276],[-97.66092,30.4195],[-97.67159,30.42442]]],"type":"Polygon"},"id":"48453044200","properties":{"c":[30.43087,-97.66329],"geo_id":"48453044200","name":"Census Tract 442"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.66092,30.4195],[-97.6559,30.43145],[-97.64476,30.42879],[-97.63627,30.40268],[-97.66092,30.4195]]],"type":"Polygon"},"id":"48453044300","properties":{"c":[30.41827,-97.6485],"geo_id":"48453044300","name":"Census Tract 443"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64758,30.43634],[-97.63472,30.44059],[-97.62323,30.42993],[-97.64476,30.42879],[-97.64758,30.43634]]],"type":"Polygon"},"id":"48453044400","properties":{"c":[30.43389,-97.63548],"geo_id":"48453044400","name":"Census Tract 444"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64228,30.44411],[-97.63781,30.44762],[-97.6105,30.43495],[-97.61922,30.42145],[-97.62642,30.4249],[-97.624,30.43401],[-97.64228,30.44411]]],"type":"Polygon"},"id":"48453044500","properties":{"c":[30.43554,-97.62454],"geo_id":"48453044500","name":"Census Tract 445"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64565,30.41929],[-97.64476,30.42879],[-97.62642,30.4249],[-97.63546,30.40884],[-97.64565,30.41929]]],"type":"Polygon"},"id":"48453044600","properties":{"c":[30.42116,-97.63678],"geo_id":"48453044600","name":"Census Tract 446"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63601,30.4039],[-97.62642,30.4249],[-97.61922,30.42145],[-97.6284,30.40563],[-97.63601,30.4039]]],"type":"Polygon"},"id":"48453044700","properties":{"c":[30.4143,-97.6282],"geo_id":"48453044700","name":"Census Tract 447"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61619,30.42615],[-97.6105,30.43495],[-97.57588,30.41752],[-97.59587,30.3936],[-97.61143,30.40628],[-97.61619,30.42615]]],"type":"Polygon"},"id":"48453044800","properties":{"c":[30.4148,-97.59816],"geo_id":"48453044800","name":"Census Tract 448"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64856,30.38717],[-97.61922,30.42145],[-97.59587,30.3936],[-97.6131,30.36839],[-97.64856,30.38717]]],"type":"Polygon"},"id":"48453044900","properties":{"c":[30.39231,-97.62143],"geo_id":"48453044900","name":"Census Tract 449"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64781,30.36649],[-97.64412,30.38393],[-97.6145,30.36868],[-97.63905,30.35277],[-97.64534,30.35251],[-97.64781,30.36649]]],"type":"Polygon"},"id":"48453045000","properties":{"c":[30.36719,-97.63637],"geo_id":"48453045000","name":"Census Tract 450"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69975,30.43437],[-97.69595,30.44009],[-97.67902,30.42806],[-97.701,30.43077],[-97.69975,30.43437]]],"type":"Polygon"},"id":"48453045100","properties":{"c":[30.4331,-97.69243],"geo_id":"48453045100","name":"Census Tract 451"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.701,30.43077],[-97.67902,30.42806],[-97.6766,30.42686],[-97.68855,30.4156],[-97.701,30.43077]]],"type":"Polygon"},"id":"48453045200","properties":{"c":[30.42449,-97.68882],"geo_id":"48453045200","name":"Census Tract 452"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71932,30.39832],[-97.71599,30.40858],[-97.69774,30.40598],[-97.71047,30.38878],[-97.72174,30.3912],[-97.71932,30.39832]]],"type":"Polygon"},"id":"48453045300","properties":{"c":[30.39955,-97.71135],"geo_id":"48453045300","name":"Census Tract 453"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73618,30.37868],[-97.72918,30.41157],[-97.71664,30.40999],[-97.72391,30.3721],[-97.73618,30.37868]]],"type":"Polygon"},"id":"48453045400","properties":{"c":[30.39182,-97.72501],"geo_id":"48453045400","name":"Census Tract 454"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69535,30.45215],[-97.6947,30.46065],[-97.68143,30.45327],[-97.6866,30.4458],[-97.69535,30.45215]]],"type":"Polygon"},"id":"48453045500","properties":{"c":[30.45301,-97.68954],"geo_id":"48453045500","name":"Census Tract 455"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69459,30.4615],[-97.68289,30.48007],[-97.67424,30.48079],[-97.67917,30.45523],[-97.69459,30.4615]]],"type":"Polygon"},"id":"48453045600","properties":{"c":[30.46726,-97.68096],"geo_id":"48453045600","name":"Census Tract 456"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67734,30.45804],[-97.67191,30.47364],[-97.66631,30.45252],[-97.67497,30.43595],[-97.67734,30.45804]]],"type":"Polygon"},"id":"48453045700","properties":{"c":[30.45391,-97.67219],"geo_id":"48453045700","name":"Census Tract 457"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.51303,30.40888],[-97.49595,30.43394],[-97.47911,30.4395],[-97.46692,30.46519],[-97.45978,30.45832],[-97.43411,30.45972],[-97.41525,30.43834],[-97.39303,30.43877],[-97.38339,30.42415],[-97.36954,30.41956],[-97.40939,30.35215],[-97.50059,30.35067],[-97.48266,30.35657],[-97.46431,30.38466],[-97.51303,30.40888]]],"type":"Polygon"},"id":"48453045800","properties":{"c":[30.40444,-97.44038],"geo_id":"48453045800","name":"Census Tract 458"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.53678,30.3522],[-97.51303,30.40888],[-97.46431,30.38466],[-97.48266,30.35657],[-97.53678,30.3522]]],"type":"Polygon"},"id":"48453045900","properties":{"c":[30.37594,-97.50293],"geo_id":"48453045900","name":"Census Tract 459"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62452,30.48714],[-97.60683,30.49031],[-97.59616,30.50148],[-97.58118,30.50075],[-97.59166,30.47218],[-97.62452,30.48714]]],"type":"Polygon"},"id":"48453046000","properties":{"c":[30.48779,-97.59781],"geo_id":"48453046000","name":"Census Tract 460"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62788,30.48527],[-97.59364,30.47365],[-97.59363,30.46491],[-97.60206,30.4559],[-97.61604,30.45915],[-97.62788,30.48527]]],"type":"Polygon"},"id":"48453046100","properties":{"c":[30.47094,-97.60972],"geo_id":"48453046100","name":"Census Tract 461"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6439,30.47901],[-97.62801,30.48524],[-97.61604,30.45915],[-97.64123,30.47233],[-97.6439,30.47901]]],"type":"Polygon"},"id":"48453046200","properties":{"c":[30.47398,-97.63025],"geo_id":"48453046200","name":"Census Tract 462"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61843,30.4428],[-97.61604,30.45915],[-97.60206,30.4559],[-97.61393,30.4366],[-97.61843,30.4428]]],"type":"Polygon"},"id":"48453046300","properties":{"c":[30.44865,-97.61231],"geo_id":"48453046300","name":"Census Tract 463"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67376,30.4801],[-97.64348,30.47808],[-97.64143,30.47106],[-97.66265,30.46676],[-97.67376,30.4801]]],"type":"Polygon"},"id":"48453046400","properties":{"c":[30.47311,-97.65775],"geo_id":"48453046400","name":"Census Tract 464"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67021,30.46984],[-97.64421,30.46655],[-97.66851,30.44059],[-97.66631,30.45252],[-97.67021,30.46984]]],"type":"Polygon"},"id":"48453046500","properties":{"c":[30.4586,-97.65931],"geo_id":"48453046500","name":"Census Tract 465"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.58243,30.49391],[-97.58118,30.50075],[-97.56826,30.49972],[-97.54949,30.48025],[-97.58412,30.48478],[-97.58243,30.49391]]],"type":"Polygon"},"id":"48453046600","properties":{"c":[30.48964,-97.56886],"geo_id":"48453046600","name":"Census Tract 466"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.59166,30.47218],[-97.58412,30.48478],[-97.57034,30.47702],[-97.5747,30.46288],[-97.59166,30.47218]]],"type":"Polygon"},"id":"48453046700","properties":{"c":[30.47361,-97.5805],"geo_id":"48453046700","name":"Census Tract 467"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57902,30.48218],[-97.54608,30.47542],[-97.5405,30.47864],[-97.55684,30.45456],[-97.5747,30.46288],[-97.57034,30.47702],[-97.57902,30.48218]]],"type":"Polygon"},"id":"48453046800","properties":{"c":[30.47085,-97.56066],"geo_id":"48453046800","name":"Census Tract 468"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.5969,30.46408],[-97.59166,30.47218],[-97.55684,30.45456],[-97.57417,30.43658],[-97.60206,30.4559],[-97.5969,30.46408]]],"type":"Polygon"},"id":"48453046900","properties":{"c":[30.45379,-97.579],"geo_id":"48453046900","name":"Census Tract 469"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61393,30.4366],[-97.60206,30.4559],[-97.56894,30.43567],[-97.57918,30.41944],[-97.61393,30.4366]]],"type":"Polygon"},"id":"48453047000","properties":{"c":[30.43732,-97.59158],"geo_id":"48453047000","name":"Census Tract 470"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68529,30.19185],[-97.68204,30.22292],[-97.6419,30.20455],[-97.65162,30.19843],[-97.64576,30.18329],[-97.65932,30.16736],[-97.68775,30.183],[-97.68529,30.19185]]],"type":"Polygon"},"id":"48453980000","properties":{"c":[30.19464,-97.66668],"geo_id":"48453980000","name":"Census Tract 9800"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69997,30.69849],[-97.68451,30.71385],[-97.69163,30.7131],[-97.69445,30.72537],[-97.68224,30.73116],[-97.65433,30.70412],[-97.67239,30.70495],[-97.69707,30.69234],[-97.69997,30.69849]]],"type":"Polygon"},"id":"48491020106","properties":{"c":[30.71241,-97.67923],"geo_id":"48491020106","name":"Census Tract 201.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71711,30.68391],[-97.68694,30.68893],[-97.68801,30.6972],[-97.67239,30.70495],[-97.65017,30.70466],[-97.63574,30.69186],[-97.64015,30.68121],[-97.6558,30.69153],[-97.66945,30.66654],[-97.66989,30.67486],[-97.68013,30.66902],[-97.6909,30.67897],[-97.70134,30.67348],[-97.71711,30.68391]]],"type":"Polygon"},"id":"48491020108","properties":{"c":[30.6876,-97.67325],"geo_id":"48491020108","name":"Census Tract 201.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82752,30.7031],[-97.80321,30.71343],[-97.77888,30.70494],[-97.76195,30.71213],[-97.71776,30.68293],[-97.72672,30.66655],[-97.73633,30.67726],[-97.75792,30.66914],[-97.80943,30.68838],[-97.82752,30.7031]]],"type":"Polygon"},"id":"48491020109","properties":{"c":[30.69228,-97.76943],"geo_id":"48491020109","name":"Census Tract 201.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72672,30.66655],[-97.71776,30.68293],[-97.6795,30.64994],[-97.68356,30.64606],[-97.70431,30.66314],[-97.72672,30.66655]]],"type":"Polygon"},"id":"48491020111","properties":{"c":[30.66622,-97.70531],"geo_id":"48491020111","name":"Census Tract 201.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67817,30.65184],[-97.6558,30.69153],[-97.64015,30.68121],[-97.65229,30.67456],[-97.64862,30.66482],[-97.67817,30.65184]]],"type":"Polygon"},"id":"48491020113","properties":{"c":[30.67064,-97.65894],"geo_id":"48491020113","name":"Census Tract 201.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6998,30.67446],[-97.69193,30.67937],[-97.68013,30.66902],[-97.66989,30.67486],[-97.6795,30.64994],[-97.6998,30.67446]]],"type":"Polygon"},"id":"48491020114","properties":{"c":[30.66592,-97.68391],"geo_id":"48491020114","name":"Census Tract 201.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72987,30.69412],[-97.69787,30.71092],[-97.70173,30.71822],[-97.69598,30.72196],[-97.68451,30.71385],[-97.69997,30.69849],[-97.68773,30.69404],[-97.68694,30.68893],[-97.71776,30.68293],[-97.72987,30.69412]]],"type":"Polygon"},"id":"48491020115","properties":{"c":[30.69922,-97.70592],"geo_id":"48491020115","name":"Census Tract 201.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71997,30.71125],[-97.7073,30.73352],[-97.68224,30.73116],[-97.70173,30.71822],[-97.6991,30.70999],[-97.7152,30.70356],[-97.71997,30.71125]]],"type":"Polygon"},"id":"48491020116","properties":{"c":[30.72096,-97.70408],"geo_id":"48491020116","name":"Census Tract 201.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73598,30.7435],[-97.73414,30.75913],[-97.69212,30.73674],[-97.7073,30.73352],[-97.71059,30.72083],[-97.7245,30.71605],[-97.72174,30.72489],[-97.73598,30.7435]]],"type":"Polygon"},"id":"48491020117","properties":{"c":[30.73837,-97.71818],"geo_id":"48491020117","name":"Census Tract 201.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75595,30.71138],[-97.74146,30.72597],[-97.72057,30.71628],[-97.71729,30.69745],[-97.7302,30.69316],[-97.75595,30.71138]]],"type":"Polygon"},"id":"48491020118","properties":{"c":[30.70927,-97.73511],"geo_id":"48491020118","name":"Census Tract 201.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77284,30.72417],[-97.76733,30.7325],[-97.74108,30.73086],[-97.75786,30.70986],[-97.77284,30.72417]]],"type":"Polygon"},"id":"48491020119","properties":{"c":[30.7228,-97.75772],"geo_id":"48491020119","name":"Census Tract 201.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87785,30.66448],[-97.86933,30.66736],[-97.87188,30.67524],[-97.83522,30.68674],[-97.81178,30.67017],[-97.79705,30.63692],[-97.83293,30.63844],[-97.87549,30.6533],[-97.87785,30.66448]]],"type":"Polygon"},"id":"48491020120","properties":{"c":[30.66006,-97.8372],"geo_id":"48491020120","name":"Census Tract 201.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72418,30.66092],[-97.70431,30.66314],[-97.68356,30.64606],[-97.69157,30.63305],[-97.71045,30.63277],[-97.72418,30.66092]]],"type":"Polygon"},"id":"48491020121","properties":{"c":[30.64786,-97.70389],"geo_id":"48491020121","name":"Census Tract 201.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83522,30.68674],[-97.8231,30.69803],[-97.75792,30.66914],[-97.74935,30.6768],[-97.73064,30.67498],[-97.71045,30.63277],[-97.79705,30.63692],[-97.81178,30.67017],[-97.83522,30.68674]]],"type":"Polygon"},"id":"48491020122","properties":{"c":[30.65919,-97.76997],"geo_id":"48491020122","name":"Census Tract 201.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72284,30.63414],[-97.69157,30.63305],[-97.6898,30.62119],[-97.71157,30.60895],[-97.72284,30.63414]]],"type":"Polygon"},"id":"48491020123","properties":{"c":[30.62384,-97.70659],"geo_id":"48491020123","name":"Census Tract 201.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8278,30.63769],[-97.72284,30.63414],[-97.71157,30.60895],[-97.79938,30.59557],[-97.80943,30.5871],[-97.8278,30.63769]]],"type":"Polygon"},"id":"48491020124","properties":{"c":[30.61623,-97.77395],"geo_id":"48491020124","name":"Census Tract 201.24"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80313,30.8617],[-97.80035,30.89963],[-97.62528,30.87019],[-97.64238,30.84935],[-97.64311,30.82694],[-97.68179,30.81885],[-97.66543,30.7844],[-97.73,30.75757],[-97.74585,30.7636],[-97.76211,30.78509],[-97.80313,30.8617]]],"type":"Polygon"},"id":"48491020201","properties":{"c":[30.83482,-97.72265],"geo_id":"48491020201","name":"Census Tract 202.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80612,30.7506],[-97.78105,30.76998],[-97.7558,30.76454],[-97.7533,30.77286],[-97.73414,30.75913],[-97.73593,30.74268],[-97.72324,30.71894],[-97.73777,30.72048],[-97.74798,30.73417],[-97.77101,30.73134],[-97.7751,30.72217],[-97.80612,30.7506]]],"type":"Polygon"},"id":"48491020203","properties":{"c":[30.74639,-97.76354],"geo_id":"48491020203","name":"Census Tract 202.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.88031,30.66676],[-97.87662,30.75421],[-97.79632,30.77924],[-97.77672,30.76883],[-97.80612,30.7506],[-97.76228,30.71142],[-97.77888,30.70494],[-97.80523,30.71302],[-97.82752,30.7031],[-97.83522,30.68674],[-97.88031,30.66676]]],"type":"Polygon"},"id":"48491020205","properties":{"c":[30.72753,-97.83357],"geo_id":"48491020205","name":"Census Tract 202.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90318,30.83875],[-97.8281,30.90441],[-97.80035,30.89963],[-97.80266,30.85739],[-97.77266,30.81144],[-97.7533,30.77286],[-97.7558,30.76454],[-97.79632,30.77924],[-97.87662,30.75421],[-97.87761,30.77696],[-97.90318,30.83875]]],"type":"Polygon"},"id":"48491020206","properties":{"c":[30.82357,-97.83351],"geo_id":"48491020206","name":"Census Tract 202.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.93631,30.68962],[-97.92839,30.70597],[-97.93231,30.72484],[-97.91682,30.73077],[-97.91035,30.72456],[-97.91593,30.73606],[-97.89745,30.74079],[-97.89894,30.7247],[-97.87629,30.72591],[-97.87549,30.6533],[-97.93195,30.67469],[-97.93631,30.68962]]],"type":"Polygon"},"id":"48491020207","properties":{"c":[30.69697,-97.90376],"geo_id":"48491020207","name":"Census Tract 202.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.97436,30.76455],[-97.96286,30.78564],[-97.90297,30.83824],[-97.87717,30.77542],[-97.87629,30.72591],[-97.89894,30.7247],[-97.89745,30.74079],[-97.91593,30.73606],[-97.90947,30.72504],[-97.91682,30.73077],[-97.93231,30.72484],[-97.92839,30.70597],[-97.94008,30.68994],[-97.95264,30.70956],[-97.998,30.72021],[-97.97436,30.76455]]],"type":"Polygon"},"id":"48491020208","properties":{"c":[30.76108,-97.9289],"geo_id":"48491020208","name":"Census Tract 202.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80199,30.56875],[-97.78116,30.57717],[-97.75773,30.53909],[-97.70852,30.52568],[-97.74544,30.51918],[-97.77822,30.53645],[-97.78169,30.54562],[-97.79145,30.54264],[-97.80199,30.56875]]],"type":"Polygon"},"id":"48491020310","properties":{"c":[30.54596,-97.76729],"geo_id":"48491020310","name":"Census Tract 203.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80696,30.49236],[-97.78422,30.50425],[-97.78646,30.48126],[-97.76106,30.47751],[-97.79702,30.46816],[-97.80696,30.49236]]],"type":"Polygon"},"id":"48491020311","properties":{"c":[30.48531,-97.792],"geo_id":"48491020311","name":"Census Tract 203.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84414,30.55796],[-97.80283,30.57062],[-97.79559,30.55304],[-97.82041,30.55685],[-97.84179,30.54822],[-97.84414,30.55796]]],"type":"Polygon"},"id":"48491020319","properties":{"c":[30.55914,-97.819],"geo_id":"48491020319","name":"Census Tract 203.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85512,30.55219],[-97.84178,30.55314],[-97.8476,30.53628],[-97.85549,30.55164],[-97.85512,30.55219]]],"type":"Polygon"},"id":"48491020321","properties":{"c":[30.54886,-97.84737],"geo_id":"48491020321","name":"Census Tract 203.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86157,30.53814],[-97.84993,30.54167],[-97.84495,30.52981],[-97.85536,30.5271],[-97.86157,30.53814]]],"type":"Polygon"},"id":"48491020323","properties":{"c":[30.53435,-97.85321],"geo_id":"48491020323","name":"Census Tract 203.23"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8476,30.53628],[-97.84016,30.54416],[-97.8352,30.5329],[-97.84495,30.52981],[-97.8476,30.53628]]],"type":"Polygon"},"id":"48491020325","properties":{"c":[30.53666,-97.84183],"geo_id":"48491020325","name":"Census Tract 203.25"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86225,30.49731],[-97.8594,30.51192],[-97.85102,30.5145],[-97.83447,30.47785],[-97.84654,30.47341],[-97.86225,30.49731]]],"type":"Polygon"},"id":"48491020326","properties":{"c":[30.49227,-97.84818],"geo_id":"48491020326","name":"Census Tract 203.26"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84962,30.5149],[-97.84002,30.51773],[-97.84495,30.52981],[-97.8352,30.5329],[-97.82338,30.50958],[-97.84162,30.50435],[-97.84962,30.5149]]],"type":"Polygon"},"id":"48491020327","properties":{"c":[30.51683,-97.83671],"geo_id":"48491020327","name":"Census Tract 203.27"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92272,30.66487],[-97.91157,30.6681],[-97.8278,30.63769],[-97.81906,30.6119],[-97.85858,30.62151],[-97.87862,30.60742],[-97.88194,30.61526],[-97.8915,30.61284],[-97.89515,30.6057],[-97.9066,30.64643],[-97.92272,30.66487]]],"type":"Polygon"},"id":"48491020329","properties":{"c":[30.63445,-97.87283],"geo_id":"48491020329","name":"Census Tract 203.29"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04989,30.62416],[-97.998,30.72021],[-97.96356,30.71514],[-97.93631,30.68962],[-97.93195,30.67469],[-97.91157,30.6681],[-97.92272,30.66487],[-97.9066,30.64643],[-97.90296,30.61884],[-97.88879,30.6002],[-97.92008,30.59622],[-97.91706,30.60487],[-97.95673,30.62825],[-97.9924,30.60949],[-98.00628,30.62752],[-98.01274,30.61677],[-98.0365,30.61173],[-98.04989,30.62416]]],"type":"Polygon"},"id":"48491020330","properties":{"c":[30.65537,-97.97188],"geo_id":"48491020330","name":"Census Tract 203.30"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90013,30.56891],[-97.86151,30.58005],[-97.85286,30.57868],[-97.86812,30.56884],[-97.8628,30.56201],[-97.88412,30.55359],[-97.90013,30.56891]]],"type":"Polygon"},"id":"48491020331","properties":{"c":[30.56794,-97.87555],"geo_id":"48491020331","name":"Census Tract 203.31"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86556,30.57048],[-97.85286,30.57868],[-97.84414,30.55796],[-97.85775,30.55384],[-97.86556,30.57048]]],"type":"Polygon"},"id":"48491020332","properties":{"c":[30.5648,-97.85528],"geo_id":"48491020332","name":"Census Tract 203.32"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84632,30.47352],[-97.8274,30.47363],[-97.81768,30.46167],[-97.82572,30.4556],[-97.84632,30.47352]]],"type":"Polygon"},"id":"48491020333","properties":{"c":[30.46676,-97.83052],"geo_id":"48491020333","name":"Census Tract 203.33"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83776,30.47614],[-97.8034,30.47949],[-97.79702,30.46816],[-97.81768,30.46167],[-97.83776,30.47614]]],"type":"Polygon"},"id":"48491020334","properties":{"c":[30.47237,-97.81633],"geo_id":"48491020334","name":"Census Tract 203.34"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84962,30.5149],[-97.84162,30.50435],[-97.82003,30.50484],[-97.84025,30.4938],[-97.84962,30.5149]]],"type":"Polygon"},"id":"48491020335","properties":{"c":[30.50313,-97.83659],"geo_id":"48491020335","name":"Census Tract 203.35"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84025,30.4938],[-97.82003,30.50484],[-97.81648,30.50098],[-97.83251,30.48152],[-97.84025,30.4938]]],"type":"Polygon"},"id":"48491020336","properties":{"c":[30.49411,-97.83011],"geo_id":"48491020336","name":"Census Tract 203.36"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87086,30.52642],[-97.86884,30.547],[-97.85549,30.55164],[-97.84993,30.54167],[-97.86157,30.53814],[-97.85536,30.5271],[-97.87086,30.52642]]],"type":"Polygon"},"id":"48491020337","properties":{"c":[30.5371,-97.86196],"geo_id":"48491020337","name":"Census Tract 203.37"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.88412,30.55359],[-97.8628,30.56201],[-97.85455,30.5536],[-97.86448,30.54537],[-97.88412,30.55359]]],"type":"Polygon"},"id":"48491020338","properties":{"c":[30.55348,-97.86755],"geo_id":"48491020338","name":"Census Tract 203.38"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83099,30.58225],[-97.80458,30.59054],[-97.78489,30.57646],[-97.82461,30.56401],[-97.83099,30.58225]]],"type":"Polygon"},"id":"48491020339","properties":{"c":[30.57699,-97.81018],"geo_id":"48491020339","name":"Census Tract 203.39"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86111,30.60258],[-97.86042,30.62118],[-97.81906,30.6119],[-97.80943,30.5871],[-97.85286,30.57868],[-97.86111,30.60258]]],"type":"Polygon"},"id":"48491020340","properties":{"c":[30.59837,-97.83849],"geo_id":"48491020340","name":"Census Tract 203.40"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85286,30.57868],[-97.8357,30.58276],[-97.82461,30.56401],[-97.84414,30.55796],[-97.85286,30.57868]]],"type":"Polygon"},"id":"48491020341","properties":{"c":[30.57073,-97.83936],"geo_id":"48491020341","name":"Census Tract 203.41"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89515,30.6057],[-97.88194,30.61526],[-97.87862,30.60742],[-97.8612,30.62065],[-97.85954,30.59372],[-97.87493,30.59556],[-97.87937,30.5881],[-97.89515,30.6057]]],"type":"Polygon"},"id":"48491020342","properties":{"c":[30.60416,-97.87494],"geo_id":"48491020342","name":"Census Tract 203.42"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92698,30.56765],[-97.91512,30.58057],[-97.92008,30.59622],[-97.91064,30.59922],[-97.88879,30.6002],[-97.87204,30.57663],[-97.92698,30.56765]]],"type":"Polygon"},"id":"48491020343","properties":{"c":[30.58321,-97.90037],"geo_id":"48491020343","name":"Census Tract 203.43"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8755,30.59083],[-97.85954,30.59372],[-97.85366,30.58057],[-97.87204,30.57663],[-97.8755,30.59083]]],"type":"Polygon"},"id":"48491020344","properties":{"c":[30.58621,-97.86678],"geo_id":"48491020344","name":"Census Tract 203.44"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77585,30.53273],[-97.75247,30.52795],[-97.74544,30.51918],[-97.77681,30.50362],[-97.77585,30.53273]]],"type":"Polygon"},"id":"48491020345","properties":{"c":[30.52038,-97.76404],"geo_id":"48491020345","name":"Census Tract 203.45"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80068,30.54475],[-97.78169,30.54562],[-97.77175,30.53455],[-97.79634,30.53056],[-97.80068,30.54475]]],"type":"Polygon"},"id":"48491020346","properties":{"c":[30.53863,-97.78786],"geo_id":"48491020346","name":"Census Tract 203.46"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81827,30.50499],[-97.7957,30.50678],[-97.78998,30.52775],[-97.78045,30.53111],[-97.77453,30.52295],[-97.77681,30.50362],[-97.79195,30.50511],[-97.80819,30.48835],[-97.81827,30.50499]]],"type":"Polygon"},"id":"48491020347","properties":{"c":[30.51145,-97.79016],"geo_id":"48491020347","name":"Census Tract 203.47"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8157,30.52541],[-97.8058,30.52828],[-97.80914,30.53648],[-97.80001,30.54298],[-97.79634,30.53056],[-97.78045,30.53111],[-97.79432,30.5164],[-97.79668,30.52536],[-97.8157,30.52541]]],"type":"Polygon"},"id":"48491020348","properties":{"c":[30.52917,-97.79848],"geo_id":"48491020348","name":"Census Tract 203.48"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82612,30.52223],[-97.8091,30.52205],[-97.81461,30.51853],[-97.80823,30.50321],[-97.82236,30.50717],[-97.82612,30.52223]]],"type":"Polygon"},"id":"48491020349","properties":{"c":[30.51464,-97.81846],"geo_id":"48491020349","name":"Census Tract 203.49"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81461,30.51853],[-97.79668,30.52536],[-97.7957,30.50678],[-97.80823,30.50321],[-97.81461,30.51853]]],"type":"Polygon"},"id":"48491020350","properties":{"c":[30.51409,-97.80351],"geo_id":"48491020350","name":"Census Tract 203.50"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.84179,30.54822],[-97.80966,30.55681],[-97.79322,30.5472],[-97.80252,30.53764],[-97.8352,30.5329],[-97.84179,30.54822]]],"type":"Polygon"},"id":"48491020351","properties":{"c":[30.54545,-97.81815],"geo_id":"48491020351","name":"Census Tract 203.51"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.8352,30.5329],[-97.80914,30.53648],[-97.8058,30.52828],[-97.83008,30.52064],[-97.8352,30.5329]]],"type":"Polygon"},"id":"48491020352","properties":{"c":[30.53005,-97.82105],"geo_id":"48491020352","name":"Census Tract 203.52"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85536,30.5271],[-97.84495,30.52981],[-97.84002,30.51773],[-97.85102,30.5145],[-97.85536,30.5271]]],"type":"Polygon"},"id":"48491020353","properties":{"c":[30.52222,-97.84794],"geo_id":"48491020353","name":"Census Tract 203.53"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87114,30.52456],[-97.85536,30.5271],[-97.85102,30.5145],[-97.8594,30.51192],[-97.87114,30.52456]]],"type":"Polygon"},"id":"48491020354","properties":{"c":[30.51974,-97.86062],"geo_id":"48491020354","name":"Census Tract 203.54"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.83251,30.48152],[-97.81648,30.50098],[-97.80819,30.48835],[-97.8282,30.48117],[-97.83251,30.48152]]],"type":"Polygon"},"id":"48491020355","properties":{"c":[30.4903,-97.82001],"geo_id":"48491020355","name":"Census Tract 203.55"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82827,30.48233],[-97.80819,30.48835],[-97.8034,30.47949],[-97.81427,30.47517],[-97.82827,30.48233]]],"type":"Polygon"},"id":"48491020356","properties":{"c":[30.4812,-97.81397],"geo_id":"48491020356","name":"Census Tract 203.56"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81603,30.46224],[-97.79702,30.46816],[-97.79415,30.46124],[-97.80707,30.45576],[-97.81603,30.46224]]],"type":"Polygon"},"id":"48491020403","properties":{"c":[30.4618,-97.8044],"geo_id":"48491020403","name":"Census Tract 204.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82572,30.4556],[-97.81607,30.46222],[-97.80707,30.45576],[-97.81194,30.44707],[-97.82572,30.4556]]],"type":"Polygon"},"id":"48491020404","properties":{"c":[30.45518,-97.81605],"geo_id":"48491020404","name":"Census Tract 204.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.81098,30.4511],[-97.79415,30.46124],[-97.78896,30.44576],[-97.76606,30.43241],[-97.77634,30.42977],[-97.78878,30.44419],[-97.81098,30.4511]]],"type":"Polygon"},"id":"48491020405","properties":{"c":[30.44817,-97.79415],"geo_id":"48491020405","name":"Census Tract 204.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79067,30.44873],[-97.78524,30.45036],[-97.76213,30.45778],[-97.77735,30.4445],[-97.76436,30.44471],[-97.76973,30.4342],[-97.79067,30.44873]]],"type":"Polygon"},"id":"48491020406","properties":{"c":[30.44571,-97.77587],"geo_id":"48491020406","name":"Census Tract 204.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79702,30.46816],[-97.77941,30.4738],[-97.76053,30.47732],[-97.78041,30.4725],[-97.77642,30.45322],[-97.79067,30.44873],[-97.79702,30.46816]]],"type":"Polygon"},"id":"48491020408","properties":{"c":[30.46144,-97.78596],"geo_id":"48491020408","name":"Census Tract 204.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78007,30.47079],[-97.76053,30.47732],[-97.73826,30.47608],[-97.75556,30.47247],[-97.76213,30.45778],[-97.77642,30.45322],[-97.78007,30.47079]]],"type":"Polygon"},"id":"48491020409","properties":{"c":[30.46693,-97.76647],"geo_id":"48491020409","name":"Census Tract 204.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77735,30.4445],[-97.76406,30.45386],[-97.75364,30.43329],[-97.76973,30.4342],[-97.76547,30.44591],[-97.77735,30.4445]]],"type":"Polygon"},"id":"48491020410","properties":{"c":[30.44202,-97.76388],"geo_id":"48491020410","name":"Census Tract 204.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76932,30.45066],[-97.75556,30.47247],[-97.72052,30.47268],[-97.72115,30.45584],[-97.7468,30.44935],[-97.75452,30.43928],[-97.76406,30.45386],[-97.76932,30.45066]]],"type":"Polygon"},"id":"48491020411","properties":{"c":[30.46085,-97.74145],"geo_id":"48491020411","name":"Census Tract 204.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76053,30.47732],[-97.73379,30.48467],[-97.70301,30.51257],[-97.6862,30.50975],[-97.683,30.5024],[-97.72115,30.45584],[-97.72299,30.47499],[-97.76053,30.47732]]],"type":"Polygon"},"id":"48491020503","properties":{"c":[30.48958,-97.71351],"geo_id":"48491020503","name":"Census Tract 205.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7197,30.51904],[-97.70776,30.52222],[-97.70158,30.51267],[-97.71584,30.50745],[-97.7197,30.51904]]],"type":"Polygon"},"id":"48491020505","properties":{"c":[30.51586,-97.71108],"geo_id":"48491020505","name":"Census Tract 205.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.74077,30.50126],[-97.73814,30.50593],[-97.72168,30.49914],[-97.7257,30.49367],[-97.74077,30.50126]]],"type":"Polygon"},"id":"48491020507","properties":{"c":[30.49944,-97.73193],"geo_id":"48491020507","name":"Census Tract 205.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.78741,30.48462],[-97.78609,30.50152],[-97.77681,30.50362],[-97.76914,30.4842],[-97.75739,30.4877],[-97.74838,30.4807],[-97.78284,30.47891],[-97.78741,30.48462]]],"type":"Polygon"},"id":"48491020508","properties":{"c":[30.48786,-97.77428],"geo_id":"48491020508","name":"Census Tract 205.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77681,30.50362],[-97.75838,30.50869],[-97.73528,30.52177],[-97.73814,30.50593],[-97.76549,30.49614],[-97.77681,30.50362]]],"type":"Polygon"},"id":"48491020509","properties":{"c":[30.50825,-97.75396],"geo_id":"48491020509","name":"Census Tract 205.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69692,30.48939],[-97.683,30.5024],[-97.6768,30.48895],[-97.68697,30.4931],[-97.69692,30.48939]]],"type":"Polygon"},"id":"48491020511","properties":{"c":[30.49364,-97.68484],"geo_id":"48491020511","name":"Census Tract 205.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69585,30.48803],[-97.68697,30.4931],[-97.67424,30.48079],[-97.69062,30.47231],[-97.69585,30.48803]]],"type":"Polygon"},"id":"48491020512","properties":{"c":[30.48335,-97.68666],"geo_id":"48491020512","name":"Census Tract 205.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71992,30.45722],[-97.69692,30.48939],[-97.69062,30.47231],[-97.68289,30.48007],[-97.68878,30.4614],[-97.71992,30.45722]]],"type":"Polygon"},"id":"48491020513","properties":{"c":[30.46996,-97.69988],"geo_id":"48491020513","name":"Census Tract 205.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73401,30.51685],[-97.72655,30.52574],[-97.71449,30.52249],[-97.73062,30.51027],[-97.73401,30.51685]]],"type":"Polygon"},"id":"48491020514","properties":{"c":[30.5187,-97.7258],"geo_id":"48491020514","name":"Census Tract 205.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73636,30.51258],[-97.71713,30.51468],[-97.71584,30.50745],[-97.72168,30.49914],[-97.73814,30.50593],[-97.73636,30.51258]]],"type":"Polygon"},"id":"48491020515","properties":{"c":[30.5075,-97.72648],"geo_id":"48491020515","name":"Census Tract 205.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.77571,30.49806],[-97.752,30.50339],[-97.74904,30.48257],[-97.76914,30.4842],[-97.77571,30.49806]]],"type":"Polygon"},"id":"48491020516","properties":{"c":[30.49254,-97.76108],"geo_id":"48491020516","name":"Census Tract 205.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75205,30.49604],[-97.74333,30.50799],[-97.73672,30.49552],[-97.7257,30.49367],[-97.74838,30.4807],[-97.75205,30.49604]]],"type":"Polygon"},"id":"48491020517","properties":{"c":[30.49331,-97.74192],"geo_id":"48491020517","name":"Census Tract 205.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71935,30.53027],[-97.69222,30.53536],[-97.6862,30.50975],[-97.70158,30.51267],[-97.71935,30.53027]]],"type":"Polygon"},"id":"48491020602","properties":{"c":[30.524,-97.69943],"geo_id":"48491020602","name":"Census Tract 206.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.80123,30.59459],[-97.72086,30.60424],[-97.6898,30.62119],[-97.68666,30.60984],[-97.69267,30.55817],[-97.70352,30.55759],[-97.70578,30.57389],[-97.73885,30.58862],[-97.75844,30.57556],[-97.76137,30.56453],[-97.7506,30.54848],[-97.76045,30.54414],[-97.78072,30.57686],[-97.80458,30.59054],[-97.80123,30.59459]]],"type":"Polygon"},"id":"48491020604","properties":{"c":[30.58647,-97.73672],"geo_id":"48491020604","name":"Census Tract 206.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76045,30.54414],[-97.73477,30.55121],[-97.72253,30.53295],[-97.73366,30.53188],[-97.76045,30.54414]]],"type":"Polygon"},"id":"48491020606","properties":{"c":[30.54122,-97.74026],"geo_id":"48491020606","name":"Census Tract 206.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.73243,30.55188],[-97.69267,30.55817],[-97.69222,30.53536],[-97.72316,30.53114],[-97.73243,30.55188]]],"type":"Polygon"},"id":"48491020607","properties":{"c":[30.54481,-97.71065],"geo_id":"48491020607","name":"Census Tract 206.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.75597,30.55908],[-97.70649,30.57428],[-97.70429,30.57042],[-97.70352,30.55759],[-97.75244,30.54623],[-97.75597,30.55908]]],"type":"Polygon"},"id":"48491020608","properties":{"c":[30.56013,-97.72802],"geo_id":"48491020608","name":"Census Tract 206.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76137,30.56453],[-97.75844,30.57556],[-97.73885,30.58862],[-97.70649,30.57428],[-97.75597,30.55908],[-97.76137,30.56453]]],"type":"Polygon"},"id":"48491020609","properties":{"c":[30.57435,-97.7373],"geo_id":"48491020609","name":"Census Tract 206.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68657,30.51298],[-97.67075,30.51838],[-97.65394,30.51808],[-97.67808,30.50666],[-97.6768,30.48895],[-97.68657,30.51298]]],"type":"Polygon"},"id":"48491020701","properties":{"c":[30.50905,-97.67352],"geo_id":"48491020701","name":"Census Tract 207.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67704,30.5073],[-97.656,30.51415],[-97.65463,30.51219],[-97.6616,30.50981],[-97.6625,30.49669],[-97.67571,30.49353],[-97.67704,30.5073]]],"type":"Polygon"},"id":"48491020704","properties":{"c":[30.50322,-97.6681],"geo_id":"48491020704","name":"Census Tract 207.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63056,30.51492],[-97.61436,30.53098],[-97.61332,30.49711],[-97.621,30.49678],[-97.6205,30.5073],[-97.63056,30.51492]]],"type":"Polygon"},"id":"48491020706","properties":{"c":[30.513,-97.61877],"geo_id":"48491020706","name":"Census Tract 207.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6625,30.49669],[-97.65876,30.51203],[-97.64039,30.51278],[-97.64949,30.50458],[-97.64539,30.49631],[-97.6625,30.49669]]],"type":"Polygon"},"id":"48491020707","properties":{"c":[30.50546,-97.65218],"geo_id":"48491020707","name":"Census Tract 207.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67478,30.4899],[-97.65661,30.49622],[-97.65032,30.48587],[-97.67424,30.48079],[-97.67478,30.4899]]],"type":"Polygon"},"id":"48491020709","properties":{"c":[30.48886,-97.66454],"geo_id":"48491020709","name":"Census Tract 207.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67424,30.48079],[-97.63822,30.48917],[-97.62406,30.4878],[-97.65144,30.47489],[-97.67424,30.48079]]],"type":"Polygon"},"id":"48491020710","properties":{"c":[30.48285,-97.64724],"geo_id":"48491020710","name":"Census Tract 207.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64039,30.51278],[-97.62914,30.51541],[-97.621,30.49678],[-97.63352,30.49641],[-97.64039,30.51278]]],"type":"Polygon"},"id":"48491020711","properties":{"c":[30.50512,-97.62937],"geo_id":"48491020711","name":"Census Tract 207.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65661,30.49622],[-97.64539,30.49631],[-97.64949,30.50458],[-97.64041,30.51167],[-97.63244,30.49283],[-97.65032,30.48587],[-97.65661,30.49622]]],"type":"Polygon"},"id":"48491020712","properties":{"c":[30.49689,-97.64291],"geo_id":"48491020712","name":"Census Tract 207.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.63244,30.49283],[-97.63352,30.49641],[-97.60354,30.49718],[-97.62423,30.4873],[-97.63244,30.49283]]],"type":"Polygon"},"id":"48491020713","properties":{"c":[30.49308,-97.61983],"geo_id":"48491020713","name":"Census Tract 207.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.51544,30.62498],[-97.46279,30.63093],[-97.45572,30.64072],[-97.43903,30.64419],[-97.4167,30.60112],[-97.44656,30.59704],[-97.42806,30.55514],[-97.41081,30.53818],[-97.4254,30.47514],[-97.43922,30.47639],[-97.44461,30.46739],[-97.45913,30.47302],[-97.46692,30.46519],[-97.50135,30.47729],[-97.48303,30.5536],[-97.51544,30.62498]]],"type":"Polygon"},"id":"48491020808","properties":{"c":[30.55259,-97.45968],"geo_id":"48491020808","name":"Census Tract 208.08"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.5806,30.5007],[-97.56683,30.52632],[-97.54707,30.51924],[-97.55114,30.49403],[-97.5806,30.5007]]],"type":"Polygon"},"id":"48491020810","properties":{"c":[30.50962,-97.5617],"geo_id":"48491020810","name":"Census Tract 208.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.56683,30.52632],[-97.56371,30.53505],[-97.54329,30.53575],[-97.54351,30.51982],[-97.54849,30.50751],[-97.54707,30.51924],[-97.56683,30.52632]]],"type":"Polygon"},"id":"48491020811","properties":{"c":[30.52717,-97.55328],"geo_id":"48491020811","name":"Census Tract 208.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61647,30.58847],[-97.56328,30.60823],[-97.56342,30.62111],[-97.54713,30.58619],[-97.54469,30.55644],[-97.5567,30.56674],[-97.55899,30.55714],[-97.57134,30.56452],[-97.60593,30.56199],[-97.61647,30.58847]]],"type":"Polygon"},"id":"48491020812","properties":{"c":[30.58097,-97.57678],"geo_id":"48491020812","name":"Census Tract 208.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57166,30.63318],[-97.54553,30.63632],[-97.50833,30.63055],[-97.51571,30.62308],[-97.484,30.55389],[-97.5628,30.54018],[-97.55976,30.56651],[-97.54469,30.55644],[-97.54256,30.56862],[-97.57166,30.63318]]],"type":"Polygon"},"id":"48491020813","properties":{"c":[30.58795,-97.52902],"geo_id":"48491020813","name":"Census Tract 208.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61348,30.50821],[-97.60389,30.50932],[-97.60436,30.52886],[-97.58682,30.52945],[-97.59352,30.5005],[-97.61332,30.49711],[-97.61348,30.50821]]],"type":"Polygon"},"id":"48491020814","properties":{"c":[30.51315,-97.59976],"geo_id":"48491020814","name":"Census Tract 208.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61384,30.52934],[-97.60436,30.52886],[-97.60389,30.50932],[-97.61348,30.50821],[-97.61384,30.52934]]],"type":"Polygon"},"id":"48491020815","properties":{"c":[30.51905,-97.6088],"geo_id":"48491020815","name":"Census Tract 208.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61436,30.53098],[-97.61092,30.53246],[-97.5628,30.54018],[-97.5806,30.5007],[-97.58986,30.4974],[-97.58682,30.52945],[-97.61436,30.53098]]],"type":"Polygon"},"id":"48491020816","properties":{"c":[30.52221,-97.58259],"geo_id":"48491020816","name":"Census Tract 208.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.60593,30.56199],[-97.57134,30.56452],[-97.55899,30.55714],[-97.5628,30.54018],[-97.60125,30.53353],[-97.60593,30.56199]]],"type":"Polygon"},"id":"48491020817","properties":{"c":[30.54951,-97.58292],"geo_id":"48491020817","name":"Census Tract 208.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62534,30.56445],[-97.60944,30.57185],[-97.60125,30.53353],[-97.61395,30.53183],[-97.61449,30.55168],[-97.6228,30.55176],[-97.62534,30.56445]]],"type":"Polygon"},"id":"48491020818","properties":{"c":[30.55257,-97.61176],"geo_id":"48491020818","name":"Census Tract 208.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.56826,30.49972],[-97.55114,30.49403],[-97.54351,30.51982],[-97.52742,30.51229],[-97.5344,30.51687],[-97.53882,30.54435],[-97.48303,30.5536],[-97.50137,30.47792],[-97.51086,30.48526],[-97.52397,30.47218],[-97.55007,30.47648],[-97.55296,30.4903],[-97.56826,30.49972]]],"type":"Polygon"},"id":"48491020819","properties":{"c":[30.51331,-97.51799],"geo_id":"48491020819","name":"Census Tract 208.19"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.5628,30.54018],[-97.53882,30.54435],[-97.5344,30.51687],[-97.52742,30.51229],[-97.5459,30.52172],[-97.54329,30.53575],[-97.56371,30.53505],[-97.5628,30.54018]]],"type":"Polygon"},"id":"48491020820","properties":{"c":[30.53122,-97.54398],"geo_id":"48491020820","name":"Census Tract 208.20"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6461,30.59146],[-97.63506,30.5988],[-97.64565,30.62391],[-97.6282,30.63197],[-97.6038,30.61467],[-97.59518,30.59522],[-97.61647,30.58847],[-97.60944,30.57185],[-97.64012,30.55934],[-97.63797,30.57554],[-97.6461,30.59146]]],"type":"Polygon"},"id":"48491020821","properties":{"c":[30.5972,-97.62401],"geo_id":"48491020821","name":"Census Tract 208.21"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.66414,30.65445],[-97.63739,30.68461],[-97.61507,30.67777],[-97.59707,30.66647],[-97.59923,30.65133],[-97.57012,30.63638],[-97.56328,30.60823],[-97.59518,30.59522],[-97.6038,30.61467],[-97.6243,30.62554],[-97.6313,30.64179],[-97.65555,30.6358],[-97.65991,30.64492],[-97.64534,30.65154],[-97.66414,30.65445]]],"type":"Polygon"},"id":"48491020822","properties":{"c":[30.64111,-97.61038],"geo_id":"48491020822","name":"Census Tract 208.22"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.46692,30.46519],[-97.45913,30.47302],[-97.44461,30.46739],[-97.43922,30.47639],[-97.4254,30.47514],[-97.40562,30.54346],[-97.36099,30.53722],[-97.3742,30.55716],[-97.38948,30.61067],[-97.4035,30.60626],[-97.40862,30.61839],[-97.42221,30.6141],[-97.43903,30.64419],[-97.4288,30.65112],[-97.41852,30.64467],[-97.3991,30.66058],[-97.40362,30.66561],[-97.38613,30.66505],[-97.33923,30.70158],[-97.30153,30.69579],[-97.29835,30.70355],[-97.29238,30.69516],[-97.27315,30.69339],[-97.26051,30.70033],[-97.26234,30.69265],[-97.25241,30.69347],[-97.15522,30.45734],[-97.33446,30.40284],[-97.37677,30.4192],[-97.39303,30.43877],[-97.41525,30.43834],[-97.43411,30.45972],[-97.45978,30.45832],[-97.46692,30.46519]]],"type":"Polygon"},"id":"48491020900","properties":{"c":[30.54504,-97.3046],"geo_id":"48491020900","name":"Census Tract 209"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.43403,30.56599],[-97.40668,30.56759],[-97.40828,30.57807],[-97.38045,30.58667],[-97.36099,30.53722],[-97.41629,30.53915],[-97.4181,30.55195],[-97.43403,30.56599]]],"type":"Polygon"},"id":"48491021000","properties":{"c":[30.55932,-97.39568],"geo_id":"48491021000","name":"Census Tract 210"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.43552,30.56795],[-97.43028,30.57724],[-97.40663,30.57377],[-97.40601,30.56796],[-97.43552,30.56795]]],"type":"Polygon"},"id":"48491021100","properties":{"c":[30.57086,-97.42135],"geo_id":"48491021100","name":"Census Tract 211"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.44656,30.59704],[-97.43486,30.60059],[-97.42338,30.57523],[-97.43731,30.57502],[-97.44656,30.59704]]],"type":"Polygon"},"id":"48491021201","properties":{"c":[30.58692,-97.43517],"geo_id":"48491021201","name":"Census Tract 212.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.43291,30.59604],[-97.4167,30.60112],[-97.41564,30.57437],[-97.42338,30.57523],[-97.43291,30.59604]]],"type":"Polygon"},"id":"48491021202","properties":{"c":[30.58981,-97.4227],"geo_id":"48491021202","name":"Census Tract 212.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.41861,30.61524],[-97.40862,30.61839],[-97.4035,30.60626],[-97.38948,30.61067],[-97.38045,30.58667],[-97.41509,30.57307],[-97.41861,30.61524]]],"type":"Polygon"},"id":"48491021203","properties":{"c":[30.59546,-97.40327],"geo_id":"48491021203","name":"Census Tract 212.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.55494,30.7342],[-97.54084,30.77422],[-97.53272,30.77701],[-97.537,30.78723],[-97.52456,30.78367],[-97.51307,30.82771],[-97.26995,30.73536],[-97.25241,30.69347],[-97.26234,30.69265],[-97.26051,30.70033],[-97.27315,30.69339],[-97.29238,30.69516],[-97.29835,30.70355],[-97.30153,30.69579],[-97.33923,30.70158],[-97.38613,30.66505],[-97.40362,30.66561],[-97.3991,30.66058],[-97.41852,30.64467],[-97.4288,30.65112],[-97.46177,30.63136],[-97.4847,30.62716],[-97.50346,30.63804],[-97.52067,30.67418],[-97.54344,30.67706],[-97.54971,30.69916],[-97.53517,30.70388],[-97.53149,30.72918],[-97.55494,30.7342]]],"type":"Polygon"},"id":"48491021300","properties":{"c":[30.72489,-97.43285],"geo_id":"48491021300","name":"Census Tract 213"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69157,30.63305],[-97.6795,30.64994],[-97.66194,30.6568],[-97.67997,30.62277],[-97.6898,30.62119],[-97.69157,30.63305]]],"type":"Polygon"},"id":"48491021402","properties":{"c":[30.63808,-97.68001],"geo_id":"48491021402","name":"Census Tract 214.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65809,30.63501],[-97.6313,30.64179],[-97.62749,30.63268],[-97.64958,30.62002],[-97.65809,30.63501]]],"type":"Polygon"},"id":"48491021404","properties":{"c":[30.63182,-97.6438],"geo_id":"48491021404","name":"Census Tract 214.04"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67198,30.64513],[-97.65865,30.65478],[-97.64534,30.65154],[-97.66012,30.64431],[-97.63767,30.59432],[-97.6461,30.59146],[-97.67184,30.6333],[-97.67198,30.64513]]],"type":"Polygon"},"id":"48491021405","properties":{"c":[30.62339,-97.65484],"geo_id":"48491021405","name":"Census Tract 214.05"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.693,30.58294],[-97.6898,30.62119],[-97.67997,30.62277],[-97.67598,30.63326],[-97.65758,30.58801],[-97.69138,30.57738],[-97.693,30.58294]]],"type":"Polygon"},"id":"48491021406","properties":{"c":[30.60065,-97.67737],"geo_id":"48491021406","name":"Census Tract 214.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67598,30.63326],[-97.66897,30.63333],[-97.6461,30.59146],[-97.65832,30.58898],[-97.67598,30.63326]]],"type":"Polygon"},"id":"48491021407","properties":{"c":[30.60884,-97.6614],"geo_id":"48491021407","name":"Census Tract 214.07"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68934,30.5342],[-97.66838,30.5389],[-97.66789,30.53036],[-97.68636,30.52497],[-97.68934,30.5342]]],"type":"Polygon"},"id":"48491021502","properties":{"c":[30.53199,-97.6782],"geo_id":"48491021502","name":"Census Tract 215.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69222,30.53536],[-97.68636,30.52497],[-97.66789,30.53036],[-97.66775,30.51803],[-97.68712,30.51308],[-97.69222,30.53536]]],"type":"Polygon"},"id":"48491021503","properties":{"c":[30.5218,-97.67927],"geo_id":"48491021503","name":"Census Tract 215.03"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.64918,30.54484],[-97.64564,30.55863],[-97.62789,30.56302],[-97.62266,30.55162],[-97.61449,30.55168],[-97.64918,30.54484]]],"type":"Polygon"},"id":"48491021506","properties":{"c":[30.5525,-97.63348],"geo_id":"48491021506","name":"Census Tract 215.06"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67102,30.57392],[-97.66116,30.57826],[-97.66415,30.58593],[-97.6461,30.59146],[-97.63797,30.57554],[-97.66962,30.56577],[-97.67102,30.57392]]],"type":"Polygon"},"id":"48491021509","properties":{"c":[30.57858,-97.65449],"geo_id":"48491021509","name":"Census Tract 215.09"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69292,30.57727],[-97.66415,30.58593],[-97.66116,30.57826],[-97.67102,30.57392],[-97.66962,30.56577],[-97.69267,30.55817],[-97.69292,30.57727]]],"type":"Polygon"},"id":"48491021510","properties":{"c":[30.5723,-97.67943],"geo_id":"48491021510","name":"Census Tract 215.10"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.656,30.51415],[-97.63335,30.52441],[-97.63673,30.54712],[-97.61432,30.54668],[-97.61395,30.53183],[-97.62558,30.51789],[-97.656,30.51415]]],"type":"Polygon"},"id":"48491021511","properties":{"c":[30.53038,-97.62906],"geo_id":"48491021511","name":"Census Tract 215.11"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65569,30.52114],[-97.65022,30.54329],[-97.63673,30.54712],[-97.63335,30.52441],[-97.65569,30.52114]]],"type":"Polygon"},"id":"48491021512","properties":{"c":[30.53184,-97.64407],"geo_id":"48491021512","name":"Census Tract 215.12"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.69267,30.55817],[-97.68042,30.56164],[-97.66838,30.5389],[-97.69222,30.53536],[-97.69267,30.55817]]],"type":"Polygon"},"id":"48491021513","properties":{"c":[30.54671,-97.68366],"geo_id":"48491021513","name":"Census Tract 215.13"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.68042,30.56164],[-97.66795,30.56624],[-97.66659,30.56334],[-97.67657,30.55184],[-97.68042,30.56164]]],"type":"Polygon"},"id":"48491021514","properties":{"c":[30.55937,-97.67368],"geo_id":"48491021514","name":"Census Tract 215.14"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67555,30.55216],[-97.67046,30.55375],[-97.66482,30.56718],[-97.66045,30.54677],[-97.67555,30.55216]]],"type":"Polygon"},"id":"48491021515","properties":{"c":[30.55514,-97.66634],"geo_id":"48491021515","name":"Census Tract 215.15"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.67555,30.55216],[-97.66045,30.54677],[-97.66482,30.56718],[-97.63797,30.57554],[-97.65022,30.54329],[-97.66838,30.5389],[-97.67555,30.55216]]],"type":"Polygon"},"id":"48491021516","properties":{"c":[30.5569,-97.6548],"geo_id":"48491021516","name":"Census Tract 215.16"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.66789,30.53036],[-97.65219,30.532],[-97.65551,30.51785],[-97.66775,30.51803],[-97.66789,30.53036]]],"type":"Polygon"},"id":"48491021517","properties":{"c":[30.5251,-97.66064],"geo_id":"48491021517","name":"Census Tract 215.17"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.66838,30.5389],[-97.66297,30.5397],[-97.65022,30.54329],[-97.65219,30.532],[-97.66789,30.53036],[-97.66838,30.5389]]],"type":"Polygon"},"id":"48491021518","properties":{"c":[30.53653,-97.65928],"geo_id":"48491021518","name":"Census Tract 215.18"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.644,30.72371],[-97.5894,30.85681],[-97.51058,30.82655],[-97.52456,30.78367],[-97.537,30.78723],[-97.53272,30.77701],[-97.54084,30.77422],[-97.55494,30.7342],[-97.57217,30.74201],[-97.644,30.72371]]],"type":"Polygon"},"id":"48491021601","properties":{"c":[30.78917,-97.577],"geo_id":"48491021601","name":"Census Tract 216.01"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.65017,30.70466],[-97.64349,30.72358],[-97.59868,30.73738],[-97.59347,30.73213],[-97.57217,30.74201],[-97.53149,30.72918],[-97.53517,30.70388],[-97.54971,30.69916],[-97.54344,30.67706],[-97.52067,30.67418],[-97.50346,30.63804],[-97.4847,30.62716],[-97.57734,30.63958],[-97.59923,30.65133],[-97.59707,30.66647],[-97.63429,30.68093],[-97.65017,30.70466]]],"type":"Polygon"},"id":"48491021602","properties":{"c":[30.68663,-97.57438],"geo_id":"48491021602","name":"Census Tract 216.02"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.7295,30.758],[-97.66543,30.7844],[-97.68179,30.81885],[-97.64311,30.82694],[-97.63446,30.86567],[-97.62405,30.87],[-97.5894,30.85681],[-97.62109,30.79228],[-97.65173,30.70162],[-97.67208,30.72574],[-97.7295,30.758]]],"type":"Polygon"},"id":"48491021603","properties":{"c":[30.78776,-97.64942],"geo_id":"48491021603","name":"Census Tract 216.03"},"type":"Feature"}],"type":"FeatureCollection"},"160":{"features":[{"geometry":{"coordinates":[[[[-97.56438,30.28779],[-97.56467,30.30448],[-97.54422,30.29579],[-97.54893,30.28863],[-97.52759,30.28132],[-97.52798,30.27416],[-97.5416,30.2787],[-97.55185,30.2621],[-97.56958,30.27984],[-97.56438,30.28779]]],[[[-97.59593,30.16468],[-97.57007,30.16587],[-97.55744,30.15687],[-97.56748,30.14088],[-97.58705,30.15218],[-97.59334,30.14235],[-97.59895,30.14505],[-97.59593,30.16468]]],[[[-97.69422,30.46383],[-97.69374,30.46382],[-97.68931,30.46132],[-97.69221,30.46139],[-97.69422,30.46383]]],[[[-97.80307,30.09473],[-97.78181,30.09273],[-97.78153,30.08112],[-97.78758,30.07558],[-97.78888,30.08674],[-97.80262,30.08768],[-97.80307,30.09473]]],[[[-97.87958,30.3966],[-97.87751,30.39659],[-97.8768,30.39427],[-97.8785,30.39434],[-97.87958,30.3966]]],[[[-97.9382,30.33731],[-97.91584,30.36044],[-97.91295,30.39218],[-97.87998,30.40213],[-97.88441,30.41217],[-97.90262,30.40464],[-97.90219,30.41811],[-97.87392,30.42616],[-97.87876,30.43425],[-97.85585,30.44978],[-97.85219,30.45122],[-97.84954,30.44854],[-97.84638,30.45046],[-97.83668,30.44607],[-97.84555,30.45372],[-97.8504,30.45196],[-97.84409,30.45866],[-97.83832,30.46056],[-97.82588,30.45573],[-97.81062,30.46389],[-97.81515,30.47536],[-97.80346,30.47957],[-97.80545,30.49565],[-97.7899,30.50578],[-97.762,30.50629],[-97.74852,30.51665],[-97.74951,30.48616],[-97.76375,30.47915],[-97.73307,30.48386],[-97.72462,30.47376],[-97.7159,30.5074],[-97.70621,30.47914],[-97.69062,30.47231],[-97.69865,30.46485],[-97.69782,30.44021],[-97.6719,30.42457],[-97.66664,30.45394],[-97.67708,30.46659],[-97.67463,30.47036],[-97.66867,30.46963],[-97.66155,30.45016],[-97.66472,30.44386],[-97.64985,30.42949],[-97.66241,30.43328],[-97.66873,30.42334],[-97.65934,30.42735],[-97.6635,30.42072],[-97.64858,30.4096],[-97.64294,30.41804],[-97.63344,30.41344],[-97.638,30.40451],[-97.62643,30.40466],[-97.63259,30.39651],[-97.63973,30.40146],[-97.64692,30.38626],[-97.63322,30.37937],[-97.61313,30.40281],[-97.61556,30.38456],[-97.63901,30.35852],[-97.62529,30.35857],[-97.62851,30.36291],[-97.60705,30.38182],[-97.59234,30.37429],[-97.60926,30.36293],[-97.59802,30.35496],[-97.60226,30.34837],[-97.59353,30.35268],[-97.59311,30.34388],[-97.58845,30.35106],[-97.56037,30.3302],[-97.57903,30.28846],[-97.59595,30.28209],[-97.59083,30.27812],[-97.59884,30.26548],[-97.60468,30.26834],[-97.59996,30.27588],[-97.61972,30.29098],[-97.63443,30.29127],[-97.63595,30.27886],[-97.62839,30.28491],[-97.62247,30.27858],[-97.63441,30.25667],[-97.62595,30.25637],[-97.62451,30.25018],[-97.6311,30.23947],[-97.65725,30.22733],[-97.63934,30.20932],[-97.61435,30.21317],[-97.58745,30.2058],[-97.59796,30.18777],[-97.60343,30.18708],[-97.60054,30.19959],[-97.60969,30.20004],[-97.61663,30.18988],[-97.62456,30.19487],[-97.64196,30.18522],[-97.63514,30.18182],[-97.63402,30.17627],[-97.6188,30.18345],[-97.60786,30.17302],[-97.61606,30.1661],[-97.60415,30.16054],[-97.61058,30.15056],[-97.63323,30.1667],[-97.61327,30.14653],[-97.62203,30.14548],[-97.61819,30.13885],[-97.62912,30.13296],[-97.62376,30.13023],[-97.63176,30.13189],[-97.62591,30.12692],[-97.63488,30.13133],[-97.63632,30.1216],[-97.64902,30.13289],[-97.64298,30.14898],[-97.66248,30.16174],[-97.67566,30.15606],[-97.67603,30.16677],[-97.66152,30.16942],[-97.68144,30.17165],[-97.68782,30.18273],[-97.69731,30.1804],[-97.6932,30.18708],[-97.70094,30.19401],[-97.71206,30.19397],[-97.70298,30.1846],[-97.71762,30.1843],[-97.72384,30.16622],[-97.69672,30.15109],[-97.69595,30.13099],[-97.70592,30.13569],[-97.71618,30.11947],[-97.73509,30.12859],[-97.7294,30.14208],[-97.73528,30.15463],[-97.73697,30.13791],[-97.74973,30.14986],[-97.76554,30.12742],[-97.80106,30.1256],[-97.80591,30.11262],[-97.78515,30.1129],[-97.80602,30.11237],[-97.81275,30.09841],[-97.80802,30.11244],[-97.82498,30.1153],[-97.8115,30.11604],[-97.81047,30.13309],[-97.80839,30.13223],[-97.80129,30.13492],[-97.80358,30.12538],[-97.79844,30.13563],[-97.80438,30.1345],[-97.80708,30.13285],[-97.80156,30.14283],[-97.81019,30.1396],[-97.81777,30.14992],[-97.81964,30.17183],[-97.82826,30.14756],[-97.84218,30.14355],[-97.8485,30.14943],[-97.84669,30.14112],[-97.86208,30.14414],[-97.86313,30.13694],[-97.87396,30.15234],[-97.89039,30.14813],[-97.88956,30.17278],[-97.89649,30.17896],[-97.90714,30.17652],[-97.90502,30.1598],[-97.89324,30.15464],[-97.89296,30.14192],[-97.90096,30.14214],[-97.89579,30.13667],[-97.90233,30.13402],[-97.88624,30.1274],[-97.9285,30.12478],[-97.92908,30.15667],[-97.91762,30.15811],[-97.92886,30.1862],[-97.90929,30.20883],[-97.89779,30.206],[-97.89182,30.22327],[-97.89361,30.23108],[-97.91001,30.23468],[-97.90471,30.25487],[-97.91843,30.25259],[-97.9127,30.24977],[-97.91904,30.23939],[-97.92727,30.24628],[-97.90895,30.26008],[-97.91768,30.28931],[-97.90882,30.3097],[-97.89698,30.29693],[-97.9007,30.28926],[-97.89061,30.29568],[-97.88242,30.28659],[-97.88966,30.28353],[-97.88741,30.26571],[-97.84872,30.24959],[-97.83765,30.27391],[-97.85182,30.27165],[-97.85613,30.27819],[-97.83235,30.28857],[-97.83728,30.29869],[-97.81109,30.27257],[-97.80152,30.27528],[-97.78283,30.26624],[-97.77714,30.27372],[-97.79992,30.28988],[-97.79021,30.29456],[-97.796,30.30368],[-97.78841,30.30035],[-97.78117,30.31321],[-97.79112,30.33874],[-97.81491,30.3067],[-97.82464,30.3135],[-97.82157,30.30587],[-97.82821,30.30255],[-97.83169,30.3127],[-97.82487,30.3239],[-97.84484,30.3217],[-97.85369,30.33904],[-97.84824,30.34503],[-97.85779,30.35184],[-97.88542,30.34039],[-97.90854,30.31012],[-97.90835,30.33016],[-97.92742,30.32461],[-97.9382,30.33731]],[[-97.92894,30.33034],[-97.92816,30.33001],[-97.92556,30.334],[-97.92769,30.33431],[-97.92894,30.33034]],[[-97.92732,30.34041],[-97.90817,30.33622],[-97.8892,30.3465],[-97.86313,30.39428],[-97.88243,30.38816],[-97.896,30.39212],[-97.89034,30.3881],[-97.91204,30.38146],[-97.91068,30.36078],[-97.92732,30.34041]],[[-97.92009,30.24422],[-97.91904,30.2456],[-97.91985,30.24654],[-97.92113,30.24543],[-97.92009,30.24422]],[[-97.92105,30.24986],[-97.918,30.2472],[-97.9169,30.2488],[-97.92034,30.25059],[-97.92105,30.24986]],[[-97.92011,30.32713],[-97.91738,30.32793],[-97.91919,30.32976],[-97.92011,30.32713]],[[-97.91363,30.38108],[-97.9136,30.38068],[-97.91246,30.38146],[-97.91371,30.38166],[-97.91363,30.38108]],[[-97.90529,30.38971],[-97.88286,30.39654],[-97.87648,30.39278],[-97.85866,30.39698],[-97.85473,30.40429],[-97.86695,30.41371],[-97.87236,30.42446],[-97.87249,30.4262],[-97.87862,30.39858],[-97.90529,30.38971]],[[-97.88777,30.41899],[-97.88665,30.41914],[-97.88434,30.4209],[-97.88745,30.42205],[-97.88777,30.41899]],[[-97.87429,30.15352],[-97.86,30.1457],[-97.85998,30.15884],[-97.85018,30.15898],[-97.85324,30.17824],[-97.87453,30.17292],[-97.87429,30.15352]],[[-97.87083,30.42805],[-97.86875,30.41749],[-97.85967,30.42825],[-97.86328,30.43419],[-97.84459,30.43239],[-97.83352,30.4427],[-97.84468,30.44099],[-97.85424,30.45016],[-97.87132,30.43703],[-97.87083,30.42805]],[[-97.85615,30.35127],[-97.85329,30.34972],[-97.852,30.35075],[-97.85442,30.35217],[-97.85615,30.35127]],[[-97.84782,30.36063],[-97.81388,30.34558],[-97.80814,30.35356],[-97.81419,30.35994],[-97.81748,30.3544],[-97.84782,30.36063]],[[-97.83821,30.45515],[-97.83594,30.45877],[-97.83772,30.45989],[-97.84108,30.45375],[-97.83821,30.45515]],[[-97.83813,30.45351],[-97.82971,30.45099],[-97.82888,30.45616],[-97.8339,30.4575],[-97.83813,30.45351]],[[-97.83484,30.44884],[-97.83192,30.44652],[-97.83016,30.45007],[-97.83457,30.45128],[-97.83484,30.44884]],[[-97.83555,30.16746],[-97.832,30.16202],[-97.82422,30.17227],[-97.8356,30.16998],[-97.83555,30.16746]],[[-97.83476,30.36981],[-97.83108,30.36801],[-97.83293,30.37178],[-97.83476,30.36981]],[[-97.83442,30.32975],[-97.8321,30.32659],[-97.82824,30.3313],[-97.83344,30.33079],[-97.83442,30.32975]],[[-97.83299,30.14952],[-97.82934,30.15053],[-97.82938,30.15338],[-97.83268,30.15277],[-97.83299,30.14952]],[[-97.83243,30.44462],[-97.82667,30.4422],[-97.82339,30.4472],[-97.82938,30.45082],[-97.83243,30.44462]],[[-97.83159,30.44013],[-97.83137,30.4384],[-97.83014,30.43786],[-97.8297,30.44079],[-97.83159,30.44013]],[[-97.8303,30.36291],[-97.82871,30.3645],[-97.82182,30.36411],[-97.82948,30.36522],[-97.8303,30.36291]],[[-97.82996,30.22225],[-97.81886,30.21413],[-97.80632,30.22182],[-97.80739,30.24012],[-97.82996,30.22225]],[[-97.8249,30.3399],[-97.82377,30.33777],[-97.82083,30.33886],[-97.82423,30.3418],[-97.8249,30.3399]],[[-97.82251,30.32745],[-97.81594,30.32398],[-97.81118,30.33327],[-97.81534,30.33535],[-97.82251,30.32745]],[[-97.81795,30.26604],[-97.81712,30.26725],[-97.8147,30.26694],[-97.81796,30.26858],[-97.81795,30.26604]],[[-97.81741,30.40983],[-97.79883,30.39883],[-97.79382,30.42073],[-97.80478,30.42005],[-97.81741,30.40983]],[[-97.81678,30.26392],[-97.81546,30.26566],[-97.81652,30.26612],[-97.81734,30.26471],[-97.81678,30.26392]],[[-97.81579,30.26272],[-97.81373,30.26424],[-97.81252,30.26575],[-97.81467,30.26676],[-97.81579,30.26272]],[[-97.81508,30.23896],[-97.81476,30.2376],[-97.8126,30.23859],[-97.81326,30.24057],[-97.81508,30.23896]],[[-97.80998,30.34263],[-97.8048,30.34442],[-97.8025,30.34833],[-97.80522,30.34903],[-97.80998,30.34263]],[[-97.80953,30.41956],[-97.80642,30.4188],[-97.8061,30.42036],[-97.80834,30.42152],[-97.80953,30.41956]],[[-97.8069,30.37289],[-97.80538,30.37255],[-97.80579,30.37509],[-97.80733,30.37299],[-97.8069,30.37289]],[[-97.8055,30.27132],[-97.80384,30.2693],[-97.80169,30.2725],[-97.80244,30.27288],[-97.8055,30.27132]],[[-97.80518,30.37259],[-97.80473,30.37154],[-97.8038,30.3717],[-97.80435,30.3738],[-97.80518,30.37259]],[[-97.80277,30.36396],[-97.80025,30.36729],[-97.80134,30.3682],[-97.80358,30.36459],[-97.80277,30.36396]],[[-97.79952,30.12954],[-97.79744,30.12873],[-97.79681,30.13029],[-97.79902,30.13089],[-97.79952,30.12954]],[[-97.7924,30.40875],[-97.78834,30.40489],[-97.78215,30.40433],[-97.79232,30.41019],[-97.7924,30.40875]],[[-97.7913,30.29928],[-97.78895,30.29931],[-97.78845,30.29989],[-97.79016,30.30072],[-97.7913,30.29928]],[[-97.78971,30.45708],[-97.77475,30.4537],[-97.77654,30.46196],[-97.76667,30.46726],[-97.76198,30.44123],[-97.74276,30.44379],[-97.76394,30.47534],[-97.78041,30.4725],[-97.78971,30.45708]],[[-97.78483,30.42514],[-97.78262,30.42729],[-97.77939,30.42617],[-97.78299,30.42828],[-97.78483,30.42514]],[[-97.78501,30.3995],[-97.78343,30.3983],[-97.78309,30.39846],[-97.78373,30.40018],[-97.78501,30.3995]],[[-97.78314,30.16418],[-97.78426,30.16233],[-97.78195,30.16301],[-97.78218,30.16666],[-97.78314,30.16418]],[[-97.78344,30.39144],[-97.7819,30.39069],[-97.78108,30.39192],[-97.78266,30.39273],[-97.78344,30.39144]],[[-97.78126,30.15518],[-97.76456,30.14339],[-97.76068,30.16412],[-97.77955,30.17489],[-97.77382,30.159],[-97.78126,30.15518]],[[-97.78055,30.39276],[-97.77817,30.3926],[-97.77757,30.39632],[-97.78163,30.39329],[-97.78055,30.39276]],[[-97.78059,30.39766],[-97.77726,30.39738],[-97.77658,30.39576],[-97.77557,30.39732],[-97.78059,30.39766]],[[-97.77925,30.39034],[-97.77771,30.38942],[-97.7748,30.39029],[-97.77847,30.39141],[-97.77925,30.39034]],[[-97.77832,30.14386],[-97.7771,30.14139],[-97.77596,30.14119],[-97.7759,30.14458],[-97.77832,30.14386]],[[-97.77442,30.17483],[-97.76914,30.17432],[-97.76983,30.17871],[-97.77323,30.17822],[-97.77442,30.17483]],[[-97.75239,30.15783],[-97.74922,30.15621],[-97.7486,30.15729],[-97.75172,30.15886],[-97.75239,30.15783]],[[-97.7409,30.45688],[-97.7386,30.45763],[-97.73941,30.45945],[-97.74165,30.45872],[-97.7409,30.45688]],[[-97.73831,30.44627],[-97.73496,30.444],[-97.72704,30.44635],[-97.73023,30.45214],[-97.73831,30.44627]],[[-97.73576,30.15669],[-97.72882,30.15337],[-97.72816,30.15438],[-97.7359,30.15803],[-97.73576,30.15669]],[[-97.72472,30.15323],[-97.72233,30.15214],[-97.71969,30.15464],[-97.72293,30.15615],[-97.72472,30.15323]],[[-97.72185,30.13851],[-97.71872,30.137],[-97.71813,30.13796],[-97.72132,30.13932],[-97.72185,30.13851]],[[-97.71532,30.13542],[-97.71486,30.1352],[-97.71403,30.13651],[-97.71483,30.13692],[-97.71532,30.13542]],[[-97.71212,30.44529],[-97.70552,30.43964],[-97.7021,30.44087],[-97.70867,30.45061],[-97.71212,30.44529]],[[-97.68136,30.24096],[-97.66169,30.22526],[-97.6528,30.23456],[-97.6328,30.24092],[-97.62632,30.25487],[-97.66104,30.26231],[-97.68136,30.24096]],[[-97.67632,30.46647],[-97.67433,30.4654],[-97.67112,30.46894],[-97.67562,30.4684],[-97.67632,30.46647]],[[-97.67126,30.46379],[-97.66872,30.46254],[-97.6709,30.46814],[-97.67205,30.46632],[-97.67126,30.46379]],[[-97.67093,30.34529],[-97.65367,30.33746],[-97.65456,30.32972],[-97.62418,30.33176],[-97.61661,30.34354],[-97.64026,30.356],[-97.66872,30.35524],[-97.67093,30.34529]],[[-97.67027,30.32388],[-97.66236,30.3172],[-97.65718,30.32515],[-97.66519,30.32733],[-97.67027,30.32388]],[[-97.66646,30.44891],[-97.66555,30.44874],[-97.66501,30.44967],[-97.66615,30.45051],[-97.66646,30.44891]],[[-97.66568,30.45338],[-97.6628,30.45201],[-97.66505,30.45572],[-97.66568,30.45338]],[[-97.65792,30.16567],[-97.64368,30.15874],[-97.62944,30.17239],[-97.63964,30.17732],[-97.63783,30.18223],[-97.64615,30.18561],[-97.65792,30.16567]],[[-97.65234,30.32233],[-97.64444,30.32418],[-97.64403,30.32896],[-97.65,30.32782],[-97.65234,30.32233]],[[-97.64669,30.19433],[-97.64075,30.19961],[-97.64564,30.20368],[-97.65162,30.19843],[-97.64669,30.19433]],[[-97.64347,30.30751],[-97.6193,30.30465],[-97.60073,30.33478],[-97.64112,30.3292],[-97.62821,30.31596],[-97.63066,30.30786],[-97.64347,30.30751]],[[-97.64266,30.14947],[-97.62768,30.1424],[-97.62404,30.14644],[-97.63736,30.1578],[-97.64266,30.14947]],[[-97.62781,30.36286],[-97.62341,30.36146],[-97.62265,30.35884],[-97.61796,30.36252],[-97.62781,30.36286]],[[-97.62199,30.38909],[-97.62031,30.38829],[-97.61921,30.391],[-97.6204,30.39158],[-97.62199,30.38909]],[[-97.61061,30.34263],[-97.60714,30.34089],[-97.60231,30.34827],[-97.60586,30.35008],[-97.61061,30.34263]],[[-97.59196,30.30902],[-97.58324,30.3048],[-97.582,30.31371],[-97.58649,30.31762],[-97.59196,30.30902]]]],"type":"MultiPolygon"},"id":"4805000","properties":{"c":[30.29862,-97.75403],"geo_id":"4805000","name":"Austin"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.44492,30.80175],[-97.42204,30.80356],[-97.41918,30.79199],[-97.43358,30.78347],[-97.44601,30.79301],[-97.44492,30.80175]]],"type":"Polygon"},"id":"4805732","properties":{"c":[30.79518,-97.43238],"geo_id":"4805732","name":"Bartlett"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.88806,30.28673],[-97.88293,30.28386],[-97.8813,30.29566],[-97.87084,30.29716],[-97.86778,30.30679],[-97.86296,30.29752],[-97.85428,30.30465],[-97.85001,30.29149],[-97.84298,30.29214],[-97.86872,30.25934],[-97.88741,30.26571],[-97.88806,30.28673]]],"type":"Polygon"},"id":"4805750","properties":{"c":[30.28182,-97.86815],"geo_id":"4805750","name":"Barton Creek"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.35434,30.1224],[-97.35092,30.12132],[-97.34661,30.12147],[-97.35081,30.12054],[-97.35434,30.1224]]],[[[-97.41017,30.11101],[-97.3482,30.11289],[-97.33872,30.1224],[-97.32994,30.11442],[-97.33104,30.12704],[-97.309,30.13773],[-97.27889,30.11198],[-97.27782,30.09258],[-97.3034,30.09799],[-97.30577,30.0895],[-97.31755,30.09202],[-97.3131,30.10027],[-97.32013,30.10202],[-97.33925,30.09414],[-97.33936,30.10213],[-97.36417,30.10167],[-97.36422,30.11067],[-97.41017,30.11101]]]],"type":"MultiPolygon"},"id":"4805864","properties":{"c":[30.11133,-97.31766],"geo_id":"4805864","name":"Bastrop"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.95069,30.18755],[-97.94482,30.19315],[-97.92927,30.17502],[-97.93978,30.17298],[-97.95069,30.18755]]],"type":"Polygon"},"id":"4806242","properties":{"c":[30.18238,-97.94006],"geo_id":"4806242","name":"Bear Creek"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.00369,30.30685],[-97.9814,30.31474],[-98.00217,30.31759],[-97.99706,30.3281],[-97.97146,30.32098],[-97.95821,30.3298],[-97.93224,30.31457],[-97.92742,30.32461],[-97.92172,30.32393],[-97.93443,30.31159],[-97.93,30.30752],[-97.91375,30.31092],[-97.91307,30.31886],[-97.90882,30.3097],[-97.92573,30.30463],[-97.91763,30.28918],[-97.92442,30.28632],[-97.92909,30.29956],[-97.94158,30.297],[-97.94776,30.30569],[-97.95467,30.30325],[-97.95225,30.28904],[-97.96638,30.28929],[-97.98598,30.29117],[-98.00369,30.30685]],[[-98.0016,30.30547],[-97.99818,30.30356],[-97.9975,30.30497],[-97.99975,30.30588],[-98.00005,30.30676],[-98.0016,30.30547]],[[-97.99486,30.3038],[-97.98997,30.3014],[-97.98798,30.3046],[-97.99334,30.30704],[-97.99486,30.3038]]],"type":"Polygon"},"id":"4807156","properties":{"c":[30.30827,-97.96249],"geo_id":"4807156","name":"Bee Cave"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.00067,30.18775],[-97.9854,30.20261],[-97.96811,30.20344],[-97.97363,30.17681],[-97.99817,30.17647],[-98.00067,30.18775]]],"type":"Polygon"},"id":"4807486","properties":{"c":[30.18852,-97.9845],"geo_id":"4807486","name":"Belterra"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.05927,30.40714],[-98.04162,30.4275],[-98.035,30.42908],[-98.03792,30.41817],[-98.03117,30.41444],[-98.05031,30.39017],[-98.05927,30.40714]]],"type":"Polygon"},"id":"4810197","properties":{"c":[30.40882,-98.04515],"geo_id":"4810197","name":"Briarcliff"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76877,30.54169],[-97.71919,30.52976],[-97.71884,30.51929],[-97.7088,30.52564],[-97.70383,30.51887],[-97.71826,30.51792],[-97.72093,30.50029],[-97.73379,30.48467],[-97.76375,30.47915],[-97.74951,30.48616],[-97.75397,30.49604],[-97.74414,30.50594],[-97.74544,30.51918],[-97.76707,30.53217],[-97.76877,30.54169]]],"type":"Polygon"},"id":"4810897","properties":{"c":[30.51281,-97.73864],"geo_id":"4810897","name":"Brushy Creek"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.90007,30.10284],[-97.89143,30.10963],[-97.89161,30.09563],[-97.88716,30.10414],[-97.86414,30.1007],[-97.85799,30.11413],[-97.85769,30.10218],[-97.84303,30.10344],[-97.84874,30.08994],[-97.83988,30.0946],[-97.8409,30.08487],[-97.83808,30.09458],[-97.82338,30.08863],[-97.81374,30.09897],[-97.81087,30.08752],[-97.82286,30.07989],[-97.81636,30.07419],[-97.81953,30.06477],[-97.81296,30.06487],[-97.80916,30.05872],[-97.82965,30.06668],[-97.83689,30.05199],[-97.8286,30.04811],[-97.83656,30.0408],[-97.8666,30.04177],[-97.87394,30.05822],[-97.85964,30.0534],[-97.84651,30.07152],[-97.848,30.07684],[-97.85695,30.06866],[-97.86488,30.07663],[-97.85967,30.07679],[-97.85234,30.08825],[-97.8687,30.08099],[-97.87467,30.08548],[-97.874,30.06856],[-97.8775,30.0963],[-97.88885,30.09534],[-97.8999,30.0955],[-97.90007,30.10284]],[[-97.88585,30.09631],[-97.88268,30.09638],[-97.88275,30.0989],[-97.88535,30.09882],[-97.88585,30.09631]],[[-97.85694,30.07206],[-97.85144,30.07606],[-97.84912,30.08523],[-97.8519,30.08586],[-97.85694,30.07206]],[[-97.84395,30.07091],[-97.83642,30.07094],[-97.83643,30.07214],[-97.84194,30.07666],[-97.84395,30.07091]],[[-97.84356,30.05179],[-97.83909,30.05184],[-97.83465,30.06405],[-97.84278,30.06179],[-97.84356,30.05179]],[[-97.81959,30.06855],[-97.81826,30.06855],[-97.81831,30.07029],[-97.81954,30.0703],[-97.81959,30.06855]]],"type":"Polygon"},"id":"4811080","properties":{"c":[30.07586,-97.84879],"geo_id":"4811080","name":"Buda"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.31872,30.158],[-97.3146,30.21305],[-97.29223,30.21546],[-97.274,30.23192],[-97.25554,30.21627],[-97.27636,30.19778],[-97.27741,30.18467],[-97.26699,30.18181],[-97.26889,30.17456],[-97.2844,30.17178],[-97.31118,30.13775],[-97.31872,30.158]]],"type":"Polygon"},"id":"4812334","properties":{"c":[30.18848,-97.29332],"geo_id":"4812334","name":"Camp Swift"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57885,30.08571],[-97.51061,30.10743],[-97.50527,30.0975],[-97.4842,30.1157],[-97.44921,30.08605],[-97.48651,30.07986],[-97.48185,30.06257],[-97.49099,30.06371],[-97.49911,30.05401],[-97.53945,30.05796],[-97.54575,30.04913],[-97.58383,30.08128],[-97.57885,30.08571]]],"type":"Polygon"},"id":"4813432","properties":{"c":[30.08111,-97.51802],"geo_id":"4813432","name":"Cedar Creek"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.8426,30.46221],[-97.82567,30.4582],[-97.82124,30.46173],[-97.8333,30.47144],[-97.82619,30.47357],[-97.81062,30.46389],[-97.82588,30.45573],[-97.8426,30.46221]]],[[[-97.88839,30.50836],[-97.86504,30.5334],[-97.81774,30.54419],[-97.82041,30.55685],[-97.8074,30.53675],[-97.79366,30.54704],[-97.80068,30.54475],[-97.80056,30.55093],[-97.78309,30.55575],[-97.78704,30.55077],[-97.7788,30.53951],[-97.77768,30.54694],[-97.76346,30.55122],[-97.76825,30.53351],[-97.74544,30.51918],[-97.75888,30.50835],[-97.79588,30.50278],[-97.80623,30.49481],[-97.80346,30.47957],[-97.83212,30.47808],[-97.85947,30.44672],[-97.86352,30.45936],[-97.85539,30.47972],[-97.86411,30.48557],[-97.85704,30.49713],[-97.86264,30.51158],[-97.87676,30.51366],[-97.88022,30.50434],[-97.88839,30.50836]],[[-97.85195,30.48428],[-97.8517,30.47436],[-97.84586,30.47073],[-97.84585,30.48216],[-97.83462,30.47775],[-97.85073,30.49006],[-97.85195,30.48428]],[[-97.80673,30.52302],[-97.80329,30.51463],[-97.79714,30.51647],[-97.80181,30.52777],[-97.80673,30.52302]],[[-97.78969,30.54317],[-97.78479,30.54457],[-97.78467,30.5446],[-97.78941,30.54792],[-97.78969,30.54317]],[[-97.78625,30.50868],[-97.77935,30.51293],[-97.77711,30.5074],[-97.78043,30.5289],[-97.78681,30.52491],[-97.78625,30.50868]]]],"type":"MultiPolygon"},"id":"4813552","properties":{"c":[30.51082,-97.81939],"geo_id":"4813552","name":"Cedar Park"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.27087,30.16365],[-97.26127,30.17072],[-97.2668,30.17866],[-97.23186,30.16842],[-97.23084,30.19414],[-97.21815,30.17901],[-97.20553,30.18906],[-97.2092,30.16831],[-97.20113,30.16443],[-97.20574,30.14636],[-97.19947,30.14032],[-97.21326,30.13489],[-97.21359,30.14676],[-97.22558,30.15157],[-97.25138,30.14029],[-97.25044,30.13295],[-97.26975,30.14406],[-97.27087,30.16365]]],"type":"Polygon"},"id":"4814986","properties":{"c":[30.16106,-97.23495],"geo_id":"4814986","name":"Circle D-KC Estates"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.42514,30.44908],[-97.4236,30.45714],[-97.42283,30.44766],[-97.42018,30.44965],[-97.4103,30.44912],[-97.4081,30.456],[-97.39309,30.45581],[-97.40534,30.47357],[-97.42307,30.47318],[-97.40554,30.47546],[-97.39855,30.49889],[-97.40059,30.46831],[-97.37306,30.46002],[-97.38667,30.45357],[-97.38883,30.45937],[-97.38238,30.43011],[-97.39915,30.44213],[-97.39145,30.45075],[-97.41141,30.4448],[-97.42054,30.44926],[-97.42139,30.4473],[-97.42534,30.44782],[-97.42514,30.44908]]],"type":"Polygon"},"id":"4817312","properties":{"c":[30.45681,-97.39792],"geo_id":"4817312","name":"Coupland"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.7221,30.10989],[-97.71922,30.10889],[-97.72015,30.10728],[-97.72263,30.10902],[-97.7221,30.10989]]],[[[-97.73773,30.1145],[-97.73444,30.10608],[-97.73115,30.11138],[-97.7143,30.10379],[-97.72497,30.10526],[-97.70588,30.09596],[-97.70968,30.08981],[-97.71484,30.08866],[-97.71058,30.09548],[-97.74179,30.108],[-97.73773,30.1145]]],[[[-97.75908,30.05976],[-97.7494,30.05619],[-97.75678,30.06337],[-97.74843,30.07671],[-97.74003,30.07346],[-97.75172,30.0784],[-97.74628,30.08022],[-97.743,30.0888],[-97.75658,30.09078],[-97.75993,30.10217],[-97.74481,30.10946],[-97.74655,30.10051],[-97.71818,30.09625],[-97.73505,30.0856],[-97.72724,30.077],[-97.74344,30.07033],[-97.72283,30.06905],[-97.73348,30.0656],[-97.71253,30.05326],[-97.72058,30.04596],[-97.73444,30.03488],[-97.75908,30.05976]],[[-97.73604,30.063],[-97.73405,30.06135],[-97.73255,30.0627],[-97.73468,30.06447],[-97.73604,30.063]],[[-97.7277,30.05261],[-97.72574,30.052],[-97.72479,30.05284],[-97.72715,30.05485],[-97.7277,30.05261]]]],"type":"MultiPolygon"},"id":"4817612","properties":{"c":[30.07391,-97.7373],"geo_id":"4817612","name":"Creedmoor"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04447,30.14402],[-98.03186,30.14517],[-98.02806,30.11991],[-98.04436,30.12523],[-98.04447,30.14402]]],"type":"Polygon"},"id":"4821412","properties":{"c":[30.13298,-98.03728],"geo_id":"4821412","name":"Driftwood"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.98676,30.20727],[-97.9746,30.20797],[-97.97197,30.20233],[-97.98211,30.19899],[-97.98676,30.20727]],[[-97.98273,30.2013],[-97.98157,30.20175],[-97.98187,30.20328],[-97.98358,30.20242],[-97.98273,30.2013]]],[[[-98.00284,30.19634],[-97.99739,30.19684],[-97.99145,30.19954],[-97.9913,30.19531],[-98.00284,30.19634]]],[[[-98.00651,30.19631],[-98.00542,30.19631],[-98.00534,30.19101],[-98.00642,30.19099],[-98.00651,30.19631]]],[[[-98.00868,30.19641],[-98.00758,30.19634],[-98.0075,30.19097],[-98.00858,30.19094],[-98.00868,30.19641]]],[[[-98.05367,30.19517],[-98.0505,30.19866],[-98.0301,30.19491],[-98.04987,30.19217],[-98.05367,30.19517]]],[[[-98.06432,30.19769],[-98.05994,30.19766],[-98.0591,30.19524],[-98.06207,30.19406],[-98.06432,30.19769]]],[[[-98.06542,30.19265],[-98.06219,30.19399],[-98.06126,30.19282],[-98.06528,30.19036],[-98.06542,30.19265]]],[[[-98.1331,30.19528],[-98.12752,30.21901],[-98.1188,30.21896],[-98.12375,30.20543],[-98.11126,30.20167],[-98.1047,30.20871],[-98.09155,30.20626],[-98.09542,30.21876],[-98.08474,30.22193],[-98.08048,30.21514],[-98.08617,30.21241],[-98.06662,30.19853],[-98.08239,30.19713],[-98.06812,30.18785],[-98.08357,30.17809],[-98.06635,30.17768],[-98.07243,30.16896],[-98.06537,30.15966],[-98.08109,30.16188],[-98.08136,30.15325],[-98.08933,30.16492],[-98.08859,30.1886],[-98.10969,30.18836],[-98.10943,30.19613],[-98.11564,30.1876],[-98.13322,30.18903],[-98.1331,30.19528]],[[-98.11837,30.19745],[-98.11284,30.19594],[-98.10941,30.20032],[-98.11871,30.20063],[-98.11837,30.19745]],[[-98.08414,30.17163],[-98.08146,30.17144],[-98.08146,30.17349],[-98.08417,30.17346],[-98.08414,30.17163]],[[-98.083,30.20156],[-98.08005,30.20088],[-98.08007,30.20331],[-98.08306,30.20331],[-98.083,30.20156]],[[-98.12614,30.21136],[-98.1261,30.20573],[-98.12432,30.20551],[-98.12379,30.21133],[-98.12614,30.21136]]],[[[-98.17182,30.22056],[-98.16037,30.20898],[-98.14417,30.21185],[-98.14375,30.20654],[-98.1597,30.19916],[-98.17194,30.20392],[-98.17182,30.22056]]]],"type":"MultiPolygon"},"id":"4821424","properties":{"c":[30.19596,-98.09357],"geo_id":"4821424","name":"Dripping Springs"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.37044,30.32196],[-97.37004,30.32448],[-97.36756,30.32076],[-97.37022,30.32013],[-97.37044,30.32196]]],[[[-97.37728,30.31866],[-97.37319,30.32518],[-97.37154,30.32441],[-97.37407,30.31795],[-97.37728,30.31866]]],[[[-97.37864,30.3165],[-97.37847,30.31677],[-97.37563,30.31522],[-97.37628,30.31424],[-97.37864,30.3165]]],[[[-97.43729,30.3519],[-97.42341,30.35281],[-97.41132,30.37592],[-97.3966,30.38427],[-97.40147,30.36856],[-97.3838,30.36026],[-97.37257,30.36777],[-97.35712,30.34496],[-97.36925,30.32713],[-97.38348,30.34512],[-97.40708,30.34099],[-97.40284,30.34814],[-97.40984,30.35139],[-97.41668,30.3448],[-97.43729,30.3519]]]],"type":"MultiPolygon"},"id":"4823044","properties":{"c":[30.35396,-97.3901],"geo_id":"4823044","name":"Elgin"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79797,30.84492],[-97.7933,30.85084],[-97.77884,30.8426],[-97.78757,30.84324],[-97.78492,30.83682],[-97.79528,30.82954],[-97.79797,30.84492]]],"type":"Polygon"},"id":"4826136","properties":{"c":[30.84075,-97.79209],"geo_id":"4826136","name":"Florence"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.59798,30.18825],[-97.57866,30.21356],[-97.5565,30.20773],[-97.54078,30.22574],[-97.52714,30.21879],[-97.51788,30.22889],[-97.51324,30.2105],[-97.52878,30.20543],[-97.52372,30.19836],[-97.50143,30.20845],[-97.52923,30.17652],[-97.53535,30.17945],[-97.53586,30.17089],[-97.58129,30.17279],[-97.58777,30.18058],[-97.58285,30.18904],[-97.59798,30.18825]]],"type":"Polygon"},"id":"4828320","properties":{"c":[30.1961,-97.55145],"geo_id":"4828320","name":"Garfield"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.71293,30.67151],[-97.70914,30.6697],[-97.7089,30.66755],[-97.71103,30.66694],[-97.71293,30.67151]]],[[[-97.83272,30.69862],[-97.82752,30.7031],[-97.8168,30.69549],[-97.8054,30.69958],[-97.78985,30.68986],[-97.77741,30.69158],[-97.7679,30.67948],[-97.75299,30.68304],[-97.7645,30.69116],[-97.74167,30.68929],[-97.73676,30.69687],[-97.75139,30.70425],[-97.73462,30.7055],[-97.73161,30.71307],[-97.74206,30.71133],[-97.76151,30.72733],[-97.77004,30.71766],[-97.7751,30.72217],[-97.7635,30.73181],[-97.78416,30.72322],[-97.77895,30.72784],[-97.78531,30.73588],[-97.74482,30.74597],[-97.73722,30.74306],[-97.7243,30.75253],[-97.71964,30.74156],[-97.70234,30.74311],[-97.72066,30.7379],[-97.71701,30.73082],[-97.69599,30.73912],[-97.68423,30.7302],[-97.68196,30.73064],[-97.67337,30.72436],[-97.63896,30.73608],[-97.65594,30.69165],[-97.64702,30.6842],[-97.61475,30.67834],[-97.60974,30.67321],[-97.64596,30.68148],[-97.63188,30.66576],[-97.62943,30.64365],[-97.58517,30.64595],[-97.61569,30.64374],[-97.60104,30.61955],[-97.62834,30.61073],[-97.62588,30.60303],[-97.63876,30.59743],[-97.63325,30.59098],[-97.6461,30.59146],[-97.64182,30.58382],[-97.64108,30.58154],[-97.65943,30.58742],[-97.65645,30.59724],[-97.66544,30.59175],[-97.66425,30.60254],[-97.67582,30.59855],[-97.68471,30.60179],[-97.68348,30.59159],[-97.68803,30.59488],[-97.692,30.5859],[-97.67271,30.59106],[-97.66236,30.58162],[-97.69224,30.57077],[-97.69458,30.57725],[-97.69008,30.6043],[-97.7063,30.60325],[-97.71248,30.60766],[-97.76452,30.59692],[-97.77497,30.59555],[-97.78786,30.59515],[-97.79181,30.59439],[-97.79938,30.59557],[-97.80054,30.60822],[-97.80935,30.60818],[-97.79618,30.61406],[-97.79039,30.6143],[-97.78791,30.5953],[-97.71443,30.61145],[-97.73063,30.62386],[-97.74236,30.6178],[-97.75148,30.63137],[-97.76178,30.63207],[-97.77069,30.63322],[-97.76981,30.62031],[-97.77503,30.63396],[-97.71088,30.63343],[-97.72631,30.66233],[-97.73404,30.65943],[-97.74319,30.66832],[-97.75106,30.66019],[-97.75621,30.66672],[-97.76546,30.66154],[-97.77381,30.67017],[-97.78581,30.66857],[-97.80034,30.68214],[-97.79693,30.68646],[-97.82054,30.68762],[-97.83272,30.69862]],[[-97.77129,30.73125],[-97.76598,30.73293],[-97.7665,30.73414],[-97.77182,30.73252],[-97.77129,30.73125]],[[-97.74814,30.73843],[-97.74359,30.73991],[-97.74405,30.74276],[-97.74978,30.74188],[-97.74814,30.73843]],[[-97.74872,30.63069],[-97.74726,30.63014],[-97.74468,30.62997],[-97.74472,30.63097],[-97.74872,30.63069]],[[-97.74445,30.62999],[-97.74273,30.63011],[-97.74229,30.6302],[-97.74443,30.63098],[-97.74445,30.62999]],[[-97.74245,30.63092],[-97.74215,30.63024],[-97.7395,30.63122],[-97.73962,30.63165],[-97.74245,30.63092]],[[-97.74206,30.74162],[-97.73753,30.74212],[-97.73589,30.74257],[-97.74218,30.74259],[-97.74206,30.74162]],[[-97.7322,30.69015],[-97.72833,30.6918],[-97.73377,30.69177],[-97.7322,30.69015]],[[-97.72844,30.69545],[-97.72209,30.69313],[-97.71696,30.70204],[-97.72949,30.69807],[-97.72844,30.69545]],[[-97.72449,30.73074],[-97.72415,30.73083],[-97.72341,30.73074],[-97.7247,30.73091],[-97.72449,30.73074]],[[-97.72298,30.6573],[-97.7099,30.64464],[-97.69734,30.65328],[-97.71455,30.66179],[-97.72298,30.6573]],[[-97.71698,30.66453],[-97.70997,30.66263],[-97.70092,30.66953],[-97.71014,30.67836],[-97.71698,30.66453]],[[-97.71644,30.61795],[-97.71535,30.61486],[-97.71365,30.61843],[-97.71644,30.61795]],[[-97.71626,30.68361],[-97.69645,30.68138],[-97.69841,30.67324],[-97.6909,30.67897],[-97.68842,30.69418],[-97.69988,30.69725],[-97.67932,30.70492],[-97.6876,30.71049],[-97.68106,30.71739],[-97.67216,30.71387],[-97.6747,30.72531],[-97.70045,30.72258],[-97.694,30.71236],[-97.70291,30.69986],[-97.69882,30.69008],[-97.71626,30.68361]],[[-97.71651,30.64788],[-97.71061,30.63376],[-97.70806,30.63348],[-97.71599,30.64915],[-97.71651,30.64788]],[[-97.71516,30.62828],[-97.71269,30.62904],[-97.71301,30.6327],[-97.71578,30.63306],[-97.71516,30.62828]],[[-97.70806,30.60572],[-97.69784,30.60455],[-97.68918,30.60734],[-97.69868,30.60669],[-97.70198,30.61484],[-97.70806,30.60572]],[[-97.71017,30.63972],[-97.70824,30.63949],[-97.7052,30.63436],[-97.7074,30.64317],[-97.71017,30.63972]],[[-97.68434,30.69359],[-97.6728,30.68784],[-97.66615,30.70323],[-97.68288,30.69997],[-97.68434,30.69359]],[[-97.68429,30.66491],[-97.67243,30.66556],[-97.67103,30.66941],[-97.68346,30.66723],[-97.68429,30.66491]],[[-97.67556,30.60862],[-97.66726,30.61113],[-97.67059,30.61899],[-97.67772,30.61347],[-97.67556,30.60862]],[[-97.67445,30.60655],[-97.67162,30.60727],[-97.67143,30.60841],[-97.67479,30.60758],[-97.67445,30.60655]],[[-97.67216,30.6053],[-97.66902,30.60492],[-97.66895,30.60905],[-97.67126,30.60845],[-97.67216,30.6053]],[[-97.66807,30.60163],[-97.66431,30.60276],[-97.6654,30.6054],[-97.66962,30.60308],[-97.66807,30.60163]],[[-97.66746,30.60491],[-97.66548,30.60556],[-97.66606,30.607],[-97.66817,30.60643],[-97.66746,30.60491]],[[-97.66199,30.59863],[-97.65766,30.60056],[-97.66478,30.60568],[-97.66199,30.59863]],[[-97.66145,30.66013],[-97.65744,30.65963],[-97.65712,30.66613],[-97.66216,30.6646],[-97.66145,30.66013]],[[-97.66102,30.61992],[-97.65833,30.6223],[-97.65727,30.62558],[-97.66191,30.6214],[-97.66102,30.61992]],[[-97.65791,30.66951],[-97.65387,30.67075],[-97.64969,30.66748],[-97.6533,30.67646],[-97.65791,30.66951]],[[-97.65627,30.63059],[-97.65375,30.63186],[-97.65525,30.63589],[-97.65731,30.63264],[-97.65627,30.63059]],[[-97.65437,30.64428],[-97.65434,30.64304],[-97.65296,30.64304],[-97.65343,30.64521],[-97.65437,30.64428]],[[-97.65275,30.62246],[-97.64503,30.62226],[-97.64747,30.6283],[-97.64978,30.62766],[-97.65275,30.62246]],[[-97.64831,30.64311],[-97.64681,30.63946],[-97.64468,30.63965],[-97.64717,30.64459],[-97.64831,30.64311]],[[-97.64376,30.60697],[-97.63919,30.60838],[-97.64014,30.61065],[-97.64474,30.60923],[-97.64376,30.60697]],[[-97.63852,30.63666],[-97.63815,30.63448],[-97.62932,30.63618],[-97.63237,30.64124],[-97.63852,30.63666]],[[-97.6375,30.60439],[-97.63019,30.60665],[-97.63151,30.60973],[-97.63878,30.60742],[-97.6375,30.60439]],[[-97.63695,30.60307],[-97.63694,30.60304],[-97.63095,30.60523],[-97.63705,30.60331],[-97.63695,30.60307]],[[-97.73018,30.74616],[-97.73208,30.7445],[-97.72775,30.74038],[-97.72854,30.74226],[-97.73018,30.74616]]]],"type":"MultiPolygon"},"id":"4829336","properties":{"c":[30.66549,-97.6967],"geo_id":"4829336","name":"Georgetown"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.44977,30.71981],[-97.43411,30.72394],[-97.43406,30.71061],[-97.44652,30.71236],[-97.44977,30.71981]]],"type":"Polygon"},"id":"4830548","properties":{"c":[30.71796,-97.44106],"geo_id":"4830548","name":"Granger"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87548,30.11473],[-97.87546,30.12599],[-97.8654,30.12467],[-97.87717,30.10997],[-97.87548,30.11473]]],"type":"Polygon"},"id":"4832906","properties":{"c":[30.12157,-97.87237],"geo_id":"4832906","name":"Hays"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.62232,30.22054],[-97.58823,30.2755],[-97.56398,30.25808],[-97.56072,30.24903],[-97.57537,30.22546],[-97.56804,30.22196],[-97.57012,30.21308],[-97.5938,30.20727],[-97.59648,30.22853],[-97.62211,30.21039],[-97.62232,30.22054]]],"type":"Polygon"},"id":"4834856","properties":{"c":[30.23889,-97.5899],"geo_id":"4834856","name":"Hornsby Bend"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.95495,30.39381],[-97.94056,30.4009],[-97.95122,30.429],[-97.93459,30.43746],[-97.91546,30.42951],[-97.89943,30.39524],[-97.9308,30.39735],[-97.94164,30.38825],[-97.95495,30.39381]]],"type":"Polygon"},"id":"4835253","properties":{"c":[30.41396,-97.92802],"geo_id":"4835253","name":"Hudson Bend"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.50108,30.54525],[-97.49352,30.55224],[-97.48373,30.54976],[-97.48593,30.53766],[-97.50205,30.5398],[-97.50108,30.54525]]],[[[-97.51222,30.51806],[-97.50881,30.53641],[-97.50217,30.53553],[-97.50665,30.51368],[-97.51222,30.51806]]],[[[-97.51719,30.53751],[-97.51441,30.53466],[-97.51525,30.53016],[-97.51925,30.53069],[-97.51719,30.53751]]],[[[-97.53047,30.50827],[-97.5233,30.51037],[-97.52192,30.4948],[-97.53235,30.49697],[-97.53047,30.50827]]],[[[-97.54161,30.5973],[-97.53795,30.59847],[-97.53603,30.59389],[-97.53971,30.59274],[-97.54161,30.5973]]],[[[-97.57274,30.56779],[-97.56888,30.56902],[-97.5675,30.56577],[-97.57134,30.56452],[-97.57274,30.56779]]],[[[-97.58343,30.53659],[-97.5745,30.53846],[-97.57584,30.55507],[-97.56449,30.55789],[-97.56544,30.56375],[-97.55961,30.56564],[-97.55744,30.55084],[-97.55376,30.56929],[-97.56314,30.57437],[-97.54523,30.5756],[-97.54713,30.58619],[-97.53812,30.58003],[-97.53376,30.58827],[-97.52866,30.57619],[-97.54256,30.56862],[-97.52155,30.57605],[-97.52392,30.57045],[-97.51602,30.57003],[-97.51689,30.56379],[-97.53214,30.56482],[-97.52593,30.54675],[-97.51647,30.55263],[-97.51699,30.54762],[-97.53136,30.54519],[-97.52504,30.52194],[-97.53838,30.52118],[-97.54114,30.50312],[-97.54849,30.50751],[-97.55255,30.53163],[-97.55868,30.52928],[-97.56302,30.49878],[-97.57478,30.50096],[-97.56872,30.526],[-97.58188,30.52545],[-97.58343,30.53659]],[[-97.56121,30.54509],[-97.55859,30.54472],[-97.55832,30.54614],[-97.56099,30.54651],[-97.56121,30.54509]],[[-97.54863,30.55706],[-97.54469,30.55644],[-97.54448,30.55809],[-97.5484,30.55828],[-97.54863,30.55706]],[[-97.54491,30.55127],[-97.54194,30.54909],[-97.54036,30.55205],[-97.54462,30.55285],[-97.54491,30.55127]],[[-97.54406,30.55952],[-97.53463,30.55704],[-97.53384,30.56085],[-97.5436,30.56214],[-97.54406,30.55952]],[[-97.5433,30.56379],[-97.54054,30.56341],[-97.54025,30.56499],[-97.54303,30.56534],[-97.5433,30.56379]],[[-97.5227,30.5649],[-97.52002,30.56456],[-97.52238,30.56672],[-97.5227,30.5649]]]],"type":"MultiPolygon"},"id":"4835624","properties":{"c":[30.54094,-97.5441],"geo_id":"4835624","name":"Hutto"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6377,30.77115],[-97.6271,30.77602],[-97.61632,30.80653],[-97.62489,30.80438],[-97.62321,30.81185],[-97.63005,30.81396],[-97.61673,30.81816],[-97.62231,30.82293],[-97.61014,30.82252],[-97.623,30.84018],[-97.60978,30.84114],[-97.61196,30.84645],[-97.60973,30.84112],[-97.6146,30.83385],[-97.60157,30.83484],[-97.59695,30.85379],[-97.59022,30.85492],[-97.59751,30.83609],[-97.59084,30.82044],[-97.60942,30.81729],[-97.62342,30.76438],[-97.63508,30.75241],[-97.6309,30.76444],[-97.6377,30.77115]],[[-97.61859,30.80829],[-97.61608,30.80908],[-97.61678,30.81074],[-97.61929,30.80995],[-97.61859,30.80829]],[[-97.59743,30.82456],[-97.59604,30.82122],[-97.59497,30.82157],[-97.59636,30.82492],[-97.59743,30.82456]]],"type":"Polygon"},"id":"4837396","properties":{"c":[30.81072,-97.61375],"geo_id":"4837396","name":"Jarrell"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.96508,30.46815],[-97.95843,30.46488],[-97.95963,30.46313],[-97.95998,30.46473],[-97.96508,30.46815]]],[[[-97.96752,30.45125],[-97.94777,30.46953],[-97.941,30.46541],[-97.95366,30.456],[-97.93961,30.45005],[-97.93143,30.46396],[-97.93197,30.46346],[-97.93842,30.46565],[-97.94897,30.47274],[-97.947,30.47879],[-97.95502,30.47698],[-97.9541,30.48612],[-97.933,30.48387],[-97.92709,30.50266],[-97.91379,30.50682],[-97.91798,30.51522],[-97.91,30.52594],[-97.89476,30.5178],[-97.89475,30.51038],[-97.90454,30.50776],[-97.90986,30.51517],[-97.91249,30.50268],[-97.90014,30.50109],[-97.89993,30.49461],[-97.91466,30.49726],[-97.9196,30.48595],[-97.90007,30.48364],[-97.90324,30.47628],[-97.90471,30.48411],[-97.90917,30.47785],[-97.91702,30.48245],[-97.90964,30.4674],[-97.92568,30.45314],[-97.92076,30.43581],[-97.96752,30.45125]],[[-97.94546,30.47298],[-97.93352,30.4644],[-97.93132,30.46833],[-97.93465,30.47345],[-97.93349,30.46973],[-97.94546,30.47298]],[[-97.94288,30.47914],[-97.9387,30.47317],[-97.93833,30.47911],[-97.92543,30.47885],[-97.93442,30.48123],[-97.94288,30.47914]],[[-97.934,30.45767],[-97.93397,30.45431],[-97.92911,30.45317],[-97.92775,30.45569],[-97.934,30.45767]],[[-97.9321,30.46378],[-97.93105,30.46473],[-97.93208,30.46523],[-97.93308,30.46406],[-97.9321,30.46378]],[[-97.93192,30.44877],[-97.92869,30.44798],[-97.92934,30.45111],[-97.93237,30.45139],[-97.93192,30.44877]],[[-97.92802,30.45809],[-97.92801,30.46167],[-97.92235,30.46394],[-97.92733,30.46551],[-97.93187,30.45871],[-97.92802,30.45809]],[[-97.92558,30.46562],[-97.92075,30.46426],[-97.9203,30.46471],[-97.92043,30.4657],[-97.92558,30.46562]]]],"type":"MultiPolygon"},"id":"4838020","properties":{"c":[30.4758,-97.92934],"geo_id":"4838020","name":"Jonestown"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.82198,29.93797],[-97.8144,29.94373],[-97.81241,29.94206],[-97.82041,29.93303],[-97.82198,29.93797]]],[[[-97.82388,30.05024],[-97.81488,30.05861],[-97.81588,30.04892],[-97.80343,30.04655],[-97.82388,30.05024]]],[[[-97.84035,29.95599],[-97.83431,29.96136],[-97.83839,29.95526],[-97.8299,29.94598],[-97.8166,29.94767],[-97.82865,29.93199],[-97.82476,29.94031],[-97.84035,29.95599]]],[[[-97.86058,29.96383],[-97.85898,29.96257],[-97.86052,29.96114],[-97.86209,29.96244],[-97.86058,29.96383]]],[[[-97.92741,30.00273],[-97.92551,30.00522],[-97.92074,30.00516],[-97.92194,30.00101],[-97.92741,30.00273]]],[[[-97.97469,29.98498],[-97.96077,29.99693],[-97.95072,29.99511],[-97.93958,30.01304],[-97.93508,30.00663],[-97.92289,30.0128],[-97.91986,30.0119],[-97.92108,30.01978],[-97.90171,30.01287],[-97.90116,30.01109],[-97.90188,30.00785],[-97.90117,30.00476],[-97.89614,30.00736],[-97.90035,30.01424],[-97.89033,30.01509],[-97.88041,30.0555],[-97.86355,30.04052],[-97.82521,30.04614],[-97.83339,30.02534],[-97.82488,30.02253],[-97.83902,30.01675],[-97.82761,30.00549],[-97.84,29.99055],[-97.82311,29.9756],[-97.85077,29.95089],[-97.85857,29.95751],[-97.85229,29.96352],[-97.8603,29.96095],[-97.85495,29.96578],[-97.85793,29.97149],[-97.86912,29.96457],[-97.85975,29.95703],[-97.87552,29.94277],[-97.88574,29.954],[-97.87967,29.96167],[-97.89167,29.96328],[-97.88335,29.97522],[-97.89086,29.98159],[-97.90404,29.97465],[-97.89957,29.96148],[-97.91301,29.96512],[-97.9258,29.95362],[-97.93376,29.96031],[-97.94491,29.95547],[-97.97469,29.98498]],[[-97.92933,30.0008],[-97.92138,30.00101],[-97.91698,30.01141],[-97.92362,30.0124],[-97.92933,30.0008]],[[-97.92862,30],[-97.92412,29.98958],[-97.91121,29.99506],[-97.9213,30.0008],[-97.92862,30]],[[-97.92406,29.97801],[-97.91899,29.98244],[-97.91762,29.97514],[-97.90843,29.98318],[-97.92632,29.98707],[-97.92406,29.97801]],[[-97.91644,29.99945],[-97.90308,29.99372],[-97.89389,30.00062],[-97.89586,30.00656],[-97.90135,30.00422],[-97.91079,30.00604],[-97.91644,29.99945]],[[-97.91069,29.99059],[-97.90966,29.99109],[-97.908,29.99168],[-97.91193,29.99251],[-97.91069,29.99059]],[[-97.90989,30.00654],[-97.90154,30.00454],[-97.90212,30.00853],[-97.90143,30.01185],[-97.90228,30.01305],[-97.90989,30.00654]],[[-97.89753,29.98635],[-97.8919,29.98624],[-97.89354,29.99211],[-97.90044,29.98885],[-97.89753,29.98635]],[[-97.89576,29.98425],[-97.89462,29.98146],[-97.89254,29.98115],[-97.8919,29.98607],[-97.89576,29.98425]],[[-97.88146,29.97354],[-97.88067,29.97109],[-97.87873,29.96946],[-97.87824,29.97657],[-97.88146,29.97354]],[[-97.85886,29.99058],[-97.85411,29.98658],[-97.85101,29.99352],[-97.85299,29.99588],[-97.85886,29.99058]],[[-97.85213,30.01889],[-97.84792,30.01735],[-97.84677,30.01774],[-97.84903,30.02309],[-97.85213,30.01889]],[[-97.85091,30.00091],[-97.84448,30.00014],[-97.84058,30.00583],[-97.84521,30.00697],[-97.85091,30.00091]],[[-97.84221,29.99247],[-97.8407,29.99116],[-97.83851,29.99314],[-97.84018,29.99454],[-97.84221,29.99247]]]],"type":"MultiPolygon"},"id":"4839952","properties":{"c":[29.99348,-97.88379],"geo_id":"4839952","name":"Kyle"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.97799,30.41126],[-97.97479,30.41529],[-97.96477,30.41152],[-97.97334,30.3992],[-97.97799,30.41126]]],[[[-97.98954,30.42073],[-97.98753,30.42011],[-97.98731,30.41918],[-97.98896,30.41881],[-97.98954,30.42073]]],[[[-98.03706,30.4201],[-98.03185,30.43224],[-97.99755,30.45654],[-98.00728,30.4835],[-97.99952,30.49384],[-98.00247,30.50425],[-97.99168,30.50525],[-97.97972,30.49273],[-97.97375,30.50166],[-97.95909,30.49468],[-97.97167,30.47334],[-97.9634,30.47382],[-97.96715,30.46676],[-97.95963,30.46313],[-97.96752,30.45125],[-97.97553,30.46039],[-97.97848,30.45281],[-97.95484,30.44471],[-97.9536,30.43751],[-97.96825,30.42055],[-97.97731,30.43268],[-97.98591,30.41909],[-97.99121,30.4291],[-97.99596,30.42162],[-97.97996,30.40633],[-98.03706,30.4201]],[[-97.98976,30.4383],[-97.97961,30.43311],[-97.98649,30.44754],[-97.97913,30.44986],[-97.98677,30.45174],[-97.98976,30.4383]],[[-97.984,30.43214],[-97.9827,30.4306],[-97.98207,30.43067],[-97.98253,30.43249],[-97.984,30.43214]],[[-97.97906,30.46003],[-97.96839,30.46611],[-97.97004,30.47023],[-97.97544,30.4722],[-97.97906,30.46003]],[[-97.97102,30.4316],[-97.96728,30.42649],[-97.963,30.42948],[-97.9674,30.43406],[-97.97102,30.4316]],[[-97.99121,30.4291],[-97.99105,30.42904],[-97.98793,30.42775],[-97.99034,30.43047],[-97.99121,30.4291]]]],"type":"MultiPolygon"},"id":"4840264","properties":{"c":[30.45187,-97.99074],"geo_id":"4840264","name":"Lago Vista"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.04199,30.3464],[-98.02771,30.34355],[-98.03004,30.35444],[-98.01999,30.36065],[-98.02566,30.35407],[-98.01984,30.34574],[-98.01481,30.37048],[-97.96872,30.39418],[-97.96485,30.3807],[-97.94258,30.37977],[-97.95906,30.34037],[-97.94907,30.33608],[-97.96218,30.32757],[-97.98995,30.33416],[-97.98324,30.32213],[-97.99452,30.33094],[-98.00217,30.31759],[-98.04199,30.3464]],[[-98.02347,30.342],[-98.02068,30.34007],[-98.0178,30.34279],[-98.02038,30.34109],[-98.02347,30.342]],[[-98.0117,30.35248],[-98.00539,30.35383],[-98.01102,30.36204],[-98.00862,30.35666],[-98.0117,30.35248]],[[-98.00724,30.33494],[-97.97816,30.33967],[-97.97688,30.35143],[-97.98255,30.35732],[-97.9995,30.3426],[-98.00502,30.34747],[-98.00724,30.33494]],[[-98.00413,30.33081],[-98.0014,30.32966],[-97.99875,30.33149],[-98.00048,30.33239],[-98.00413,30.33081]],[[-97.99957,30.3298],[-97.99818,30.33044],[-97.99786,30.33072],[-97.99848,30.33128],[-97.99957,30.3298]],[[-97.96472,30.3744],[-97.96032,30.37264],[-97.95851,30.37359],[-97.96021,30.37812],[-97.96472,30.3744]],[[-97.95856,30.36789],[-97.95765,30.36669],[-97.95706,30.36877],[-97.95825,30.36871],[-97.95856,30.36789]]],"type":"Polygon"},"id":"4840984","properties":{"c":[30.35449,-97.98701],"geo_id":"4840984","name":"Lakeway"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.78078,30.56952],[-97.77998,30.56964],[-97.77956,30.56778],[-97.78042,30.56768],[-97.78078,30.56952]]],[[[-97.83822,30.5935],[-97.83503,30.59449],[-97.83457,30.5934],[-97.83772,30.59242],[-97.83822,30.5935]]],[[[-97.84349,30.62646],[-97.84202,30.62684],[-97.83874,30.62663],[-97.84285,30.62502],[-97.84349,30.62646]]],[[[-97.84452,30.62886],[-97.84341,30.62923],[-97.84277,30.62768],[-97.84386,30.62731],[-97.84452,30.62886]]],[[[-97.90967,30.62315],[-97.90842,30.62352],[-97.90795,30.62237],[-97.9092,30.62201],[-97.90967,30.62315]]],[[[-97.94529,30.56057],[-97.94232,30.57034],[-97.93279,30.57181],[-97.90572,30.55672],[-97.89436,30.54336],[-97.8794,30.55418],[-97.8934,30.56843],[-97.89578,30.56492],[-97.92782,30.58105],[-97.89827,30.56983],[-97.88653,30.57371],[-97.8926,30.58864],[-97.93615,30.60374],[-97.90631,30.62059],[-97.90338,30.62939],[-97.89364,30.60647],[-97.88194,30.61526],[-97.87501,30.59912],[-97.86538,30.60431],[-97.85725,30.62687],[-97.8581,30.61256],[-97.84682,30.61322],[-97.84329,30.60148],[-97.83372,30.59985],[-97.83254,30.61021],[-97.82263,30.60294],[-97.81838,30.60406],[-97.83046,30.63448],[-97.84491,30.6298],[-97.84755,30.636],[-97.83763,30.64093],[-97.82111,30.63756],[-97.82119,30.62853],[-97.82676,30.6317],[-97.82062,30.61602],[-97.8072,30.61951],[-97.80337,30.61005],[-97.80935,30.60818],[-97.80054,30.60822],[-97.8004,30.57091],[-97.79319,30.5901],[-97.78017,30.59168],[-97.79223,30.58285],[-97.78464,30.57661],[-97.78484,30.5798],[-97.77636,30.58251],[-97.78344,30.57659],[-97.76833,30.56624],[-97.80202,30.54997],[-97.80792,30.55653],[-97.83328,30.55607],[-97.84539,30.53795],[-97.86504,30.5334],[-97.88556,30.51146],[-97.91,30.52594],[-97.92261,30.51748],[-97.92821,30.52895],[-97.92064,30.5362],[-97.91593,30.54797],[-97.91589,30.5595],[-97.91804,30.54782],[-97.9287,30.55844],[-97.93368,30.54604],[-97.94529,30.56057]],[[-97.89269,30.56773],[-97.89229,30.56732],[-97.89026,30.56633],[-97.8916,30.56901],[-97.89269,30.56773]],[[-97.88664,30.5935],[-97.88348,30.59336],[-97.88549,30.5948],[-97.88664,30.5935]],[[-97.83791,30.59082],[-97.82931,30.59173],[-97.83265,30.59986],[-97.83939,30.59436],[-97.83791,30.59082]],[[-97.81023,30.59616],[-97.81037,30.59415],[-97.8074,30.59703],[-97.81178,30.59864],[-97.81023,30.59616]],[[-97.78464,30.57661],[-97.78891,30.57481],[-97.79766,30.56579],[-97.78433,30.57067],[-97.7826,30.56655],[-97.77758,30.56823],[-97.78464,30.57661]]]],"type":"MultiPolygon"},"id":"4842016","properties":{"c":[30.57341,-97.86181],"geo_id":"4842016","name":"Leander"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.84979,30.64548],[-97.85029,30.65775],[-97.8402,30.66086],[-97.85025,30.65773],[-97.84736,30.64508],[-97.84556,30.64454],[-97.84534,30.64633],[-97.84347,30.64592],[-97.82936,30.6379],[-97.83596,30.6515],[-97.82577,30.63784],[-97.82761,30.64988],[-97.82573,30.6378],[-97.82935,30.63787],[-97.83226,30.63835],[-97.84056,30.64255],[-97.8402,30.64027],[-97.8453,30.6463],[-97.84554,30.64451],[-97.84745,30.64492],[-97.84671,30.64334],[-97.85089,30.64216],[-97.84979,30.64548]]],[[[-97.86643,30.63457],[-97.86101,30.63623],[-97.85916,30.6316],[-97.86495,30.63104],[-97.86643,30.63457]]],[[[-97.87134,30.64338],[-97.87054,30.64361],[-97.87011,30.64258],[-97.87084,30.64234],[-97.87134,30.64338]]],[[[-97.88124,30.64022],[-97.87821,30.64119],[-97.87324,30.62938],[-97.87769,30.63075],[-97.88124,30.64022]]],[[[-97.94728,30.68111],[-97.89792,30.66918],[-97.87769,30.6554],[-97.87076,30.66022],[-97.86703,30.65212],[-97.86663,30.65275],[-97.85236,30.65712],[-97.85145,30.65479],[-97.86661,30.65273],[-97.86146,30.65179],[-97.85627,30.64553],[-97.86876,30.63936],[-97.8707,30.64433],[-97.87297,30.64726],[-97.88381,30.6438],[-97.89803,30.66085],[-97.9291,30.65921],[-97.93248,30.67414],[-97.94194,30.67065],[-97.94728,30.68111]],[[-97.87302,30.64797],[-97.86901,30.64928],[-97.86835,30.65045],[-97.87426,30.65091],[-97.87302,30.64797]],[[-97.86506,30.64707],[-97.86399,30.64911],[-97.86606,30.64972],[-97.86506,30.64707]]],[[[-97.97036,30.69913],[-97.96145,30.70673],[-97.95656,30.69481],[-97.9683,30.68908],[-97.97036,30.69913]]]],"type":"MultiPolygon"},"id":"4842664","properties":{"c":[30.66372,-97.9062],"geo_id":"4842664","name":"Liberty Hill"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.72869,29.88692],[-97.67492,29.92436],[-97.67309,29.89523],[-97.6576,29.89772],[-97.65242,29.87928],[-97.62464,29.87458],[-97.64824,29.87166],[-97.64685,29.86549],[-97.66216,29.86321],[-97.65361,29.8487],[-97.68174,29.8408],[-97.68158,29.85071],[-97.69564,29.84525],[-97.70956,29.8513],[-97.71604,29.86391],[-97.71073,29.8682],[-97.72869,29.88692]],[[-97.69703,29.85796],[-97.69145,29.85062],[-97.6824,29.85552],[-97.68635,29.86307],[-97.69703,29.85796]]],"type":"Polygon"},"id":"4843240","properties":{"c":[29.87849,-97.68308],"geo_id":"4843240","name":"Lockhart"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86471,30.3123],[-97.8619,30.31816],[-97.84372,30.3089],[-97.83235,30.28857],[-97.84718,30.28627],[-97.84298,30.29214],[-97.85001,30.29149],[-97.85428,30.30465],[-97.86296,30.29752],[-97.86471,30.3123]]],"type":"Polygon"},"id":"4844162","properties":{"c":[30.30225,-97.84975],"geo_id":"4844162","name":"Lost Creek"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70054,29.66898],[-97.68967,29.67662],[-97.66898,29.68152],[-97.66903,29.69172],[-97.65974,29.68829],[-97.64841,29.69704],[-97.66742,29.7276],[-97.66092,29.73454],[-97.6423,29.70221],[-97.64356,29.69149],[-97.62722,29.68541],[-97.63293,29.67838],[-97.62482,29.67644],[-97.63422,29.67768],[-97.58989,29.65252],[-97.59812,29.64546],[-97.59895,29.65351],[-97.63503,29.67322],[-97.64732,29.6577],[-97.65007,29.66502],[-97.65412,29.66063],[-97.65798,29.64595],[-97.68247,29.64919],[-97.65977,29.6563],[-97.65224,29.66696],[-97.65936,29.67014],[-97.65775,29.68152],[-97.70054,29.66898]]],"type":"Polygon"},"id":"4845096","properties":{"c":[29.68137,-97.64679],"geo_id":"4845096","name":"Luling"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.26728,30.28222],[-97.26054,30.29648],[-97.24913,30.30064],[-97.222,30.2852],[-97.23986,30.26395],[-97.24935,30.27422],[-97.25622,30.26807],[-97.26728,30.28222]]],"type":"Polygon"},"id":"4845564","properties":{"c":[30.28173,-97.24527],"geo_id":"4845564","name":"McDade"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.85786,30.13064],[-97.83312,30.14745],[-97.82313,30.14524],[-97.82197,30.1274],[-97.84,30.13147],[-97.84673,30.12266],[-97.85786,30.13064]]],"type":"Polygon"},"id":"4846308","properties":{"c":[30.13528,-97.83637],"geo_id":"4846308","name":"Manchaca"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.57459,30.34512],[-97.54574,30.37772],[-97.5313,30.37214],[-97.53508,30.3859],[-97.52041,30.38157],[-97.51368,30.36973],[-97.5045,30.38883],[-97.49835,30.38608],[-97.51074,30.36832],[-97.50124,30.36328],[-97.49724,30.36959],[-97.50332,30.37381],[-97.47863,30.36765],[-97.47342,30.37568],[-97.46716,30.36564],[-97.47399,30.36905],[-97.48953,30.35344],[-97.47373,30.35619],[-97.45636,30.34903],[-97.47547,30.35074],[-97.48138,30.33908],[-97.49031,30.34335],[-97.48559,30.35081],[-97.51461,30.34968],[-97.52298,30.33789],[-97.54405,30.34532],[-97.54998,30.33918],[-97.54195,30.33608],[-97.55695,30.32823],[-97.57459,30.34512]],[[-97.55323,30.35569],[-97.51869,30.3501],[-97.51216,30.36006],[-97.54249,30.37336],[-97.55323,30.35569]],[[-97.52797,30.34533],[-97.5228,30.34392],[-97.51911,30.34953],[-97.52516,30.34924],[-97.52797,30.34533]],[[-97.52531,30.37236],[-97.52381,30.37164],[-97.5231,30.37276],[-97.52457,30.37351],[-97.52531,30.37236]],[[-97.50035,30.35528],[-97.49845,30.35437],[-97.49767,30.35561],[-97.50014,30.35682],[-97.50035,30.35528]],[[-97.48507,30.3512],[-97.48303,30.35125],[-97.48294,30.35202],[-97.48431,30.35276],[-97.48507,30.3512]]],"type":"Polygon"},"id":"4846440","properties":{"c":[30.35618,-97.52279],"geo_id":"4846440","name":"Manor"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.86884,29.8631],[-97.86001,29.86756],[-97.85329,29.85275],[-97.81569,29.83392],[-97.80068,29.83823],[-97.81311,29.82885],[-97.82963,29.83896],[-97.8405,29.83108],[-97.86884,29.8631]],[[-97.86418,29.86256],[-97.86223,29.86058],[-97.86084,29.8617],[-97.8619,29.8628],[-97.86418,29.86256]]],"type":"Polygon"},"id":"4846848","properties":{"c":[29.8446,-97.83916],"geo_id":"4846848","name":"Martindale"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.89353,30.04337],[-97.88113,30.04733],[-97.88644,30.03473],[-97.90293,30.03424],[-97.89353,30.04337]]],"type":"Polygon"},"id":"4849600","properties":{"c":[30.03923,-97.89145],"geo_id":"4849600","name":"Mountain City"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.70394,30.06076],[-97.70882,30.06234],[-97.70292,30.06777],[-97.69429,30.06734],[-97.69372,30.09025],[-97.70049,30.09613],[-97.69322,30.10323],[-97.68592,30.09637],[-97.69318,30.08963],[-97.69178,30.06054],[-97.67059,30.06995],[-97.63015,30.05221],[-97.64379,30.04723],[-97.66442,30.065],[-97.67861,30.06453],[-97.69005,30.04711],[-97.67593,30.03512],[-97.67446,30.03052],[-97.68995,30.04629],[-97.68876,30.03602],[-97.67798,30.02983],[-97.71255,30.02061],[-97.69079,30.02859],[-97.69665,30.04395],[-97.69185,30.04838],[-97.701,30.04355],[-97.71265,30.05259],[-97.70394,30.06076]],[[-97.70068,30.0594],[-97.69675,30.05911],[-97.69335,30.06251],[-97.69771,30.06324],[-97.70068,30.0594]]],"type":"Polygon"},"id":"4850200","properties":{"c":[30.05761,-97.68515],"geo_id":"4850200","name":"Mustang Ridge"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.74902,30.02096],[-97.74584,30.02379],[-97.73371,30.01334],[-97.73738,30.01051],[-97.74902,30.02096]]],[[[-97.78378,29.99194],[-97.7671,30.01491],[-97.74814,29.99583],[-97.73014,30.01022],[-97.73335,30.01356],[-97.7456,30.02402],[-97.72931,30.03102],[-97.73929,30.0214],[-97.7326,30.01536],[-97.72261,30.02443],[-97.71788,30.02528],[-97.7125,29.99028],[-97.70349,29.99109],[-97.71294,29.98954],[-97.70826,29.96501],[-97.71882,30.0156],[-97.73425,30.00465],[-97.72905,29.98645],[-97.73541,30.0034],[-97.74577,29.99528],[-97.74128,29.97361],[-97.72905,29.97529],[-97.74223,29.973],[-97.74669,29.99561],[-97.75949,29.98621],[-97.7636,29.99085],[-97.77287,29.98256],[-97.78378,29.99194]],[[-97.75738,29.99027],[-97.75685,29.98973],[-97.74884,29.99466],[-97.7532,29.99402],[-97.75738,29.99027]],[[-97.73335,30.01356],[-97.72954,30.01043],[-97.71763,30.01912],[-97.72255,30.02339],[-97.73335,30.01356]]],[[[-97.78312,30.03047],[-97.78575,30.03249],[-97.76911,30.03329],[-97.7694,30.03429],[-97.76013,30.04306],[-97.75571,30.0356],[-97.7612,30.04112],[-97.76842,30.03414],[-97.7596,30.02604],[-97.74735,30.03489],[-97.74113,30.0312],[-97.75162,30.02908],[-97.74584,30.02379],[-97.75807,30.02492],[-97.75259,30.01999],[-97.75644,30.01677],[-97.76842,30.03294],[-97.77991,30.03247],[-97.78501,30.02783],[-97.77168,30.01608],[-97.76409,30.0193],[-97.77018,30.01389],[-97.78607,30.02783],[-97.78312,30.03047]]]],"type":"MultiPolygon"},"id":"4851492","properties":{"c":[30.00423,-97.75392],"geo_id":"4851492","name":"Niederwald"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.13615,30.22013],[-97.12953,30.21818],[-97.13262,30.2255],[-97.12011,30.22993],[-97.10473,30.20324],[-97.12431,30.20119],[-97.13615,30.22013]]],"type":"Polygon"},"id":"4854624","properties":{"c":[30.21392,-97.12116],"geo_id":"4854624","name":"Paige"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.50788,30.40648],[-97.50584,30.40994],[-97.50372,30.4089],[-97.50563,30.40539],[-97.50788,30.40648]]],[[[-97.51287,30.46946],[-97.5103,30.47053],[-97.50313,30.46942],[-97.50774,30.46569],[-97.51287,30.46946]]],[[[-97.53224,30.43778],[-97.52779,30.43333],[-97.53062,30.42905],[-97.53616,30.43172],[-97.53224,30.43778]]],[[[-97.54344,30.47942],[-97.54032,30.47901],[-97.54317,30.47935],[-97.54344,30.47942]]],[[[-97.54482,30.39131],[-97.53891,30.38856],[-97.54076,30.3814],[-97.54869,30.38518],[-97.54482,30.39131]]],[[[-97.55393,30.45891],[-97.54825,30.46629],[-97.5443,30.46443],[-97.54774,30.45394],[-97.55393,30.45891]]],[[[-97.66867,30.46963],[-97.6592,30.47896],[-97.65021,30.47497],[-97.63155,30.48708],[-97.60683,30.49031],[-97.60354,30.49718],[-97.5896,30.4787],[-97.58005,30.50039],[-97.57323,30.50019],[-97.57488,30.4836],[-97.54418,30.47954],[-97.58001,30.48405],[-97.56893,30.47184],[-97.5747,30.46288],[-97.55684,30.45456],[-97.55235,30.44735],[-97.534,30.46048],[-97.52818,30.45748],[-97.54352,30.43928],[-97.56135,30.44714],[-97.56877,30.43581],[-97.55374,30.43151],[-97.54285,30.41218],[-97.55057,30.41546],[-97.5565,30.40582],[-97.57617,30.41711],[-97.58567,30.40236],[-97.59391,30.40626],[-97.59374,30.42092],[-97.60921,30.41396],[-97.63745,30.42847],[-97.63731,30.4359],[-97.65197,30.43114],[-97.64592,30.44398],[-97.66867,30.46963]],[[-97.6095,30.42312],[-97.60056,30.42008],[-97.59395,30.4259],[-97.60406,30.43164],[-97.6095,30.42312]],[[-97.60775,30.45659],[-97.60743,30.45658],[-97.60739,30.4569],[-97.60772,30.45693],[-97.60775,30.45659]],[[-97.59743,30.42828],[-97.59401,30.42639],[-97.59442,30.43287],[-97.59743,30.42828]],[[-97.59111,30.44638],[-97.58967,30.44004],[-97.58725,30.43264],[-97.58029,30.44273],[-97.59111,30.44638]],[[-97.588,30.45036],[-97.57298,30.44901],[-97.57596,30.44464],[-97.57389,30.44165],[-97.57289,30.44897],[-97.56559,30.44342],[-97.56067,30.4489],[-97.57398,30.45762],[-97.588,30.45036]],[[-97.57501,30.41839],[-97.56676,30.41788],[-97.57442,30.42701],[-97.57867,30.42019],[-97.57501,30.41839]],[[-97.57006,30.45899],[-97.56799,30.458],[-97.56717,30.45929],[-97.56926,30.46027],[-97.57006,30.45899]],[[-97.56281,30.43038],[-97.57009,30.43387],[-97.5706,30.43306],[-97.56331,30.42956],[-97.56281,30.43038]]]],"type":"MultiPolygon"},"id":"4857176","properties":{"c":[30.4512,-97.60148],"geo_id":"4857176","name":"Pflugerville"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.01691,30.38056],[-98.00483,30.39251],[-97.98036,30.38344],[-98.00942,30.37112],[-98.01691,30.38056]]],"type":"Polygon"},"id":"4858586","properties":{"c":[30.38209,-98.00139],"geo_id":"4858586","name":"Point Venture"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.46814,29.96005],[-97.45746,29.96381],[-97.46054,29.97399],[-97.44889,29.97714],[-97.41988,29.96577],[-97.42188,29.95198],[-97.43194,29.95116],[-97.43641,29.93939],[-97.46814,29.96005]]],"type":"Polygon"},"id":"4861280","properties":{"c":[29.95996,-97.4428],"geo_id":"4861280","name":"Red Rock"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.79848,30.2731],[-97.78693,30.28293],[-97.77714,30.27372],[-97.78283,30.26624],[-97.79848,30.2731]]],"type":"Polygon"},"id":"4863008","properties":{"c":[30.27364,-97.78669],"geo_id":"4863008","name":"Rollingwood"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.35323,29.95465],[-97.33308,29.99175],[-97.27439,29.98822],[-97.27902,29.96319],[-97.27314,29.94993],[-97.2604,29.94795],[-97.26406,29.92139],[-97.2725,29.91715],[-97.28794,29.92487],[-97.29023,29.91188],[-97.30216,29.91352],[-97.3181,29.92003],[-97.31756,29.93063],[-97.35114,29.94116],[-97.35323,29.95465]]],"type":"Polygon"},"id":"4863164","properties":{"c":[29.95368,-97.30656],"geo_id":"4863164","name":"Rosanky"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.76498,30.55274],[-97.75499,30.56219],[-97.73208,30.56646],[-97.72989,30.5529],[-97.69901,30.55855],[-97.70296,30.57473],[-97.69458,30.57725],[-97.68122,30.56152],[-97.65209,30.5725],[-97.64459,30.57399],[-97.6546,30.58435],[-97.64399,30.58762],[-97.64052,30.58094],[-97.64182,30.58382],[-97.6461,30.59146],[-97.63858,30.59393],[-97.63204,30.57774],[-97.60186,30.59308],[-97.59348,30.58781],[-97.60241,30.57528],[-97.6099,30.57293],[-97.61464,30.58413],[-97.63266,30.57713],[-97.64985,30.57228],[-97.6457,30.56123],[-97.63323,30.56935],[-97.63068,30.56727],[-97.63464,30.56114],[-97.62789,30.56302],[-97.62492,30.55142],[-97.60895,30.56003],[-97.6091,30.55027],[-97.60153,30.54948],[-97.60766,30.54906],[-97.61384,30.52934],[-97.60125,30.52926],[-97.59005,30.50848],[-97.61332,30.5074],[-97.61524,30.48792],[-97.64687,30.4822],[-97.64598,30.4803],[-97.65021,30.47497],[-97.6592,30.47896],[-97.67591,30.46818],[-97.69202,30.4781],[-97.6895,30.49028],[-97.70396,30.48117],[-97.70822,30.5016],[-97.70175,30.51245],[-97.72093,30.50029],[-97.72412,30.50854],[-97.71826,30.51792],[-97.70383,30.51887],[-97.7088,30.52564],[-97.71884,30.51929],[-97.71802,30.52881],[-97.72242,30.52596],[-97.73166,30.54026],[-97.7164,30.555],[-97.74536,30.54846],[-97.75473,30.55915],[-97.76498,30.55274]],[[-97.7203,30.50842],[-97.71948,30.50655],[-97.71925,30.5063],[-97.71978,30.50919],[-97.7203,30.50842]],[[-97.67453,30.54703],[-97.67282,30.54278],[-97.66538,30.54667],[-97.67123,30.55259],[-97.67453,30.54703]],[[-97.6713,30.47326],[-97.66841,30.47328],[-97.66761,30.47359],[-97.67153,30.47399],[-97.6713,30.47326]],[[-97.65956,30.53807],[-97.65165,30.53831],[-97.65052,30.54287],[-97.6596,30.54053],[-97.65956,30.53807]],[[-97.65947,30.53193],[-97.65238,30.52871],[-97.65202,30.53543],[-97.65952,30.53531],[-97.65947,30.53193]],[[-97.65282,30.54814],[-97.64964,30.54458],[-97.64758,30.55037],[-97.65304,30.54896],[-97.65282,30.54814]],[[-97.65233,30.52791],[-97.64739,30.52099],[-97.64232,30.53623],[-97.64236,30.54597],[-97.65006,30.54298],[-97.65233,30.52791]],[[-97.64964,30.51474],[-97.64725,30.51544],[-97.64586,30.51144],[-97.64373,30.50896],[-97.64044,30.50719],[-97.64583,30.51862],[-97.64964,30.51474]],[[-97.64942,30.54395],[-97.64198,30.54638],[-97.64122,30.55169],[-97.647,30.55056],[-97.64942,30.54395]],[[-97.64545,30.48331],[-97.64358,30.48397],[-97.64273,30.48528],[-97.64646,30.48397],[-97.64545,30.48331]],[[-97.63934,30.54764],[-97.63316,30.55218],[-97.63366,30.55399],[-97.641,30.55163],[-97.63934,30.54764]],[[-97.63914,30.52614],[-97.63609,30.52598],[-97.63472,30.52992],[-97.63944,30.52827],[-97.63914,30.52614]],[[-97.6378,30.54121],[-97.63796,30.53556],[-97.63464,30.53557],[-97.63444,30.54622],[-97.6378,30.54121]],[[-97.63773,30.50462],[-97.63609,30.49748],[-97.63318,30.49655],[-97.63566,30.50271],[-97.63773,30.50462]],[[-97.63283,30.4963],[-97.62949,30.4888],[-97.63008,30.49244],[-97.63283,30.4963]],[[-97.6186,30.5376],[-97.61413,30.53761],[-97.61427,30.54029],[-97.61858,30.54003],[-97.6186,30.5376]],[[-97.61642,30.51056],[-97.61354,30.51063],[-97.61394,30.52398],[-97.61666,30.52394],[-97.61642,30.51056]],[[-97.61314,30.58089],[-97.60782,30.58257],[-97.60854,30.58434],[-97.61388,30.58263],[-97.61314,30.58089]],[[-97.61367,30.52625],[-97.61366,30.52551],[-97.60743,30.52546],[-97.60746,30.52695],[-97.61367,30.52625]],[[-97.61358,30.52179],[-97.61356,30.52095],[-97.6075,30.52092],[-97.60751,30.52243],[-97.61358,30.52179]],[[-97.61354,30.51864],[-97.61058,30.51861],[-97.60894,30.51788],[-97.60896,30.51938],[-97.61354,30.51864]],[[-97.60697,30.58646],[-97.6056,30.58327],[-97.60448,30.58362],[-97.60578,30.58676],[-97.60697,30.58646]]],"type":"Polygon"},"id":"4863500","properties":{"c":[30.52708,-97.66388],"geo_id":"4863500","name":"Round Rock"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82608,30.1487],[-97.81323,30.14795],[-97.81892,30.13584],[-97.82248,30.13579],[-97.82608,30.1487]]],"type":"Polygon"},"id":"4865552","properties":{"c":[30.14421,-97.81951],"geo_id":"4865552","name":"San Leanna"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.86296,29.92244],[-97.86157,29.92656],[-97.85675,29.91726],[-97.8588,29.9157],[-97.86296,29.92244]]],[[[-97.99394,29.89873],[-97.9909,29.90078],[-97.99012,29.89839],[-97.99414,29.896],[-97.99394,29.89873]]],[[[-98.00094,29.89543],[-97.99714,29.89689],[-97.99396,29.89979],[-97.99943,29.89067],[-98.00094,29.89543]]],[[[-98.00987,29.88434],[-97.99925,29.89017],[-97.99456,29.8948],[-98.00062,29.88399],[-98.00987,29.88434]]],[[[-98.01333,29.89354],[-98.00213,29.89553],[-98.00095,29.88995],[-98.00704,29.88865],[-98.01333,29.89354]]],[[[-98.019,29.84186],[-98.00679,29.84635],[-98.00296,29.86099],[-97.9889,29.84886],[-97.9735,29.85265],[-97.97517,29.86173],[-97.99246,29.86469],[-97.98636,29.87613],[-98.01021,29.87296],[-97.98121,29.88896],[-97.98877,29.90232],[-97.97725,29.88937],[-97.96713,29.89522],[-97.98124,29.89563],[-97.9781,29.89832],[-97.96819,29.90524],[-97.96454,29.89779],[-97.95245,29.9026],[-97.93952,29.91638],[-97.92295,29.8973],[-97.91005,29.91054],[-97.91261,29.90407],[-97.90599,29.90275],[-97.89072,29.9403],[-97.90375,29.94302],[-97.89979,29.96057],[-97.88305,29.95288],[-97.86238,29.92698],[-97.87586,29.91992],[-97.88355,29.92512],[-97.88123,29.91528],[-97.87242,29.91318],[-97.87653,29.90781],[-97.86384,29.90584],[-97.87189,29.91273],[-97.86907,29.91576],[-97.84195,29.89464],[-97.85478,29.89046],[-97.85314,29.87998],[-97.86635,29.88804],[-97.89137,29.88547],[-97.88867,29.87785],[-97.85078,29.8789],[-97.84214,29.86733],[-97.84695,29.86374],[-97.86148,29.87759],[-97.88302,29.86579],[-97.89464,29.88214],[-97.90444,29.87609],[-97.91421,29.87817],[-97.92173,29.85827],[-97.92837,29.85306],[-97.93386,29.8584],[-97.92119,29.83786],[-97.91318,29.84196],[-97.91209,29.84143],[-97.90729,29.83762],[-97.8761,29.86072],[-97.87379,29.85612],[-97.90319,29.83365],[-97.91312,29.84189],[-97.92121,29.83776],[-97.94213,29.82895],[-97.93557,29.82162],[-97.92935,29.82529],[-97.93501,29.82106],[-97.92362,29.81382],[-97.92838,29.81026],[-97.93292,29.81482],[-97.94444,29.80699],[-97.94637,29.81922],[-97.95939,29.82245],[-97.94311,29.82199],[-97.94661,29.83071],[-97.95884,29.82837],[-97.96331,29.82444],[-97.95712,29.81926],[-97.96679,29.8135],[-97.99076,29.82205],[-97.99652,29.81639],[-97.98039,29.8079],[-97.99452,29.80141],[-97.98662,29.77664],[-98.00214,29.7866],[-97.99492,29.80142],[-98.00549,29.80887],[-98.00057,29.80049],[-98.01164,29.80373],[-98.00669,29.80973],[-98.01207,29.81439],[-98.00028,29.81552],[-97.9903,29.83195],[-97.99696,29.82733],[-98.019,29.84186]],[[-98.0122,29.83929],[-98.01095,29.83966],[-98.01076,29.84149],[-98.01266,29.84085],[-98.0122,29.83929]],[[-98.0046,29.81162],[-98.00332,29.81278],[-98.00441,29.81372],[-98.00553,29.81275],[-98.0046,29.81162]],[[-97.99877,29.84394],[-97.99708,29.84454],[-97.99714,29.84487],[-97.99949,29.84508],[-97.99877,29.84394]],[[-97.9906,29.83244],[-97.97634,29.84324],[-97.98583,29.84616],[-97.9906,29.83244]],[[-97.99039,29.82973],[-97.98949,29.82909],[-97.98801,29.83006],[-97.98892,29.83076],[-97.99039,29.82973]],[[-97.98149,29.82454],[-97.97778,29.82789],[-97.98195,29.82475],[-97.98149,29.82454]],[[-97.97587,29.87515],[-97.97463,29.87219],[-97.9674,29.8762],[-97.97128,29.87944],[-97.97587,29.87515]],[[-97.96581,29.82655],[-97.96467,29.82559],[-97.96369,29.82647],[-97.96482,29.82744],[-97.96581,29.82655]],[[-97.96162,29.83057],[-97.96149,29.83036],[-97.95863,29.8329],[-97.9592,29.83334],[-97.96162,29.83057]],[[-97.96171,29.83856],[-97.95507,29.83395],[-97.95326,29.83556],[-97.95736,29.84235],[-97.96171,29.83856]],[[-97.95999,29.82905],[-97.95864,29.82994],[-97.95954,29.8307],[-97.96069,29.82965],[-97.95999,29.82905]],[[-97.94578,29.83326],[-97.94204,29.83415],[-97.94167,29.83795],[-97.94745,29.834],[-97.94578,29.83326]],[[-97.94074,29.84637],[-97.94005,29.85279],[-97.944,29.84931],[-97.94074,29.84637]],[[-97.9406,29.84424],[-97.93298,29.84781],[-97.93777,29.85476],[-97.93985,29.85251],[-97.9406,29.84424]],[[-97.93814,29.8379],[-97.93705,29.83728],[-97.93407,29.83942],[-97.93651,29.84184],[-97.93814,29.8379]],[[-97.93919,29.89992],[-97.93571,29.90094],[-97.93563,29.90211],[-97.9384,29.90227],[-97.93919,29.89992]],[[-97.93854,29.84273],[-97.93722,29.84141],[-97.93657,29.8419],[-97.93788,29.84324],[-97.93854,29.84273]],[[-97.91009,29.87933],[-97.90812,29.87863],[-97.90469,29.88185],[-97.90755,29.88353],[-97.91009,29.87933]],[[-97.90659,29.88485],[-97.89726,29.88182],[-97.87778,29.89616],[-97.89367,29.90381],[-97.88803,29.91126],[-97.90001,29.89984],[-97.90659,29.88485]]]],"type":"MultiPolygon"},"id":"4865600","properties":{"c":[29.87277,-97.9359],"geo_id":"4865600","name":"San Marcos"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.85025,30.65773],[-97.8428,30.65999],[-97.8402,30.66086],[-97.84361,30.68486],[-97.83522,30.68674],[-97.8182,30.67799],[-97.80714,30.66077],[-97.83672,30.65314],[-97.83646,30.64309],[-97.84736,30.64508],[-97.84749,30.6508],[-97.85025,30.65773]]],[[[-97.86084,30.65451],[-97.85024,30.65763],[-97.84753,30.65081],[-97.84954,30.65015],[-97.84747,30.64522],[-97.86084,30.65451]]]],"type":"MultiPolygon"},"id":"4865762","properties":{"c":[30.66425,-97.83281],"geo_id":"4865762","name":"Santa Rita Ranch"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.71654,30.68428],[-97.69882,30.69008],[-97.70291,30.69986],[-97.694,30.71236],[-97.6993,30.71979],[-97.68451,30.71385],[-97.68592,30.70623],[-97.67932,30.70492],[-97.69988,30.69725],[-97.68842,30.69418],[-97.6909,30.67897],[-97.69841,30.67324],[-97.69645,30.68138],[-97.71654,30.68428]]],"type":"Polygon"},"id":"4866806","properties":{"c":[30.69469,-97.69588],"geo_id":"4866806","name":"Serenada"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.87453,30.17292],[-97.85932,30.17846],[-97.85036,30.17325],[-97.86,30.1457],[-97.87429,30.15352],[-97.87453,30.17292]]],"type":"Polygon"},"id":"4867082","properties":{"c":[30.16451,-97.86307],"geo_id":"4867082","name":"Shady Hollow"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.17573,30.00958],[-97.17187,30.02334],[-97.16648,30.01406],[-97.16058,30.01683],[-97.16237,30.02346],[-97.16691,30.0194],[-97.16828,30.0373],[-97.16354,30.0357],[-97.14862,30.01883],[-97.14269,30.0232],[-97.14237,30.01251],[-97.13186,30.01323],[-97.12465,30.00936],[-97.1245,29.99344],[-97.13928,30.0073],[-97.14479,29.99232],[-97.16017,29.99802],[-97.16761,29.9932],[-97.17573,30.00958]],[[-97.16511,30.0235],[-97.1626,30.02422],[-97.16469,30.03156],[-97.16539,30.03157],[-97.16511,30.0235]],[[-97.16432,30.03165],[-97.16369,30.0297],[-97.16328,30.02969],[-97.16462,30.03349],[-97.16432,30.03165]],[[-97.15991,30.0182],[-97.16136,30.01275],[-97.1466,30.01549],[-97.15558,30.01417],[-97.15074,30.02055],[-97.15692,30.02682],[-97.15991,30.0182]],[[-97.14497,30.0143],[-97.14455,30.01249],[-97.14279,30.01251],[-97.14484,30.01456],[-97.14497,30.0143]],[[-97.1363,30.00734],[-97.13493,30.00737],[-97.13504,30.01178],[-97.13589,30.01184],[-97.1363,30.00734]]],"type":"Polygon"},"id":"4868456","properties":{"c":[30.00841,-97.15218],"geo_id":"4868456","name":"Smithville"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.6141,30.80494],[-97.60207,30.82194],[-97.59863,30.81518],[-97.58395,30.8167],[-97.57413,30.80337],[-97.60008,30.7952],[-97.6141,30.80494]]],"type":"Polygon"},"id":"4868762","properties":{"c":[30.80789,-97.59521],"geo_id":"4868762","name":"Sonterra"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92509,30.34213],[-97.91068,30.36078],[-97.91204,30.38146],[-97.90372,30.3798],[-97.88703,30.39337],[-97.88243,30.38816],[-97.86313,30.39428],[-97.8892,30.3465],[-97.90817,30.33622],[-97.92509,30.34213]]],"type":"Polygon"},"id":"4870154","properties":{"c":[30.36536,-97.89594],"geo_id":"4870154","name":"Steiner Ranch"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82813,30.22439],[-97.81059,30.23933],[-97.8031,30.2322],[-97.81661,30.21471],[-97.82813,30.22439]],[[-97.82698,30.22386],[-97.82488,30.22279],[-97.82296,30.22569],[-97.82508,30.22672],[-97.82698,30.22386]]],"type":"Polygon"},"id":"4871324","properties":{"c":[30.22576,-97.81579],"geo_id":"4871324","name":"Sunset Valley"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.51247,30.6011],[-97.48833,30.60393],[-97.48634,30.57806],[-97.49605,30.58176],[-97.48907,30.56509],[-97.46731,30.57228],[-97.44505,30.58017],[-97.45526,30.61748],[-97.42776,30.6146],[-97.43195,30.62104],[-97.43956,30.61759],[-97.43231,30.62162],[-97.43462,30.62572],[-97.43522,30.62756],[-97.42323,30.61606],[-97.43056,30.62901],[-97.40833,30.59448],[-97.38556,30.59637],[-97.383,30.586],[-97.38285,30.59495],[-97.37582,30.5945],[-97.3792,30.58404],[-97.36213,30.57887],[-97.37519,30.57423],[-97.37068,30.56303],[-97.3814,30.56073],[-97.38056,30.55022],[-97.40469,30.54818],[-97.40298,30.533],[-97.41921,30.53202],[-97.41952,30.5395],[-97.42117,30.53108],[-97.4174,30.5301],[-97.42607,30.53156],[-97.42289,30.54574],[-97.44196,30.54216],[-97.43548,30.56565],[-97.47397,30.55501],[-97.46905,30.54552],[-97.44765,30.54768],[-97.44801,30.52402],[-97.4606,30.52344],[-97.48603,30.53703],[-97.48165,30.55226],[-97.4844,30.55382],[-97.50379,30.59841],[-97.51043,30.59635],[-97.51247,30.6011]],[[-97.50567,30.59807],[-97.50396,30.59862],[-97.50514,30.60141],[-97.50692,30.60085],[-97.50567,30.59807]],[[-97.50371,30.59868],[-97.50199,30.59928],[-97.50282,30.60114],[-97.50455,30.60054],[-97.50371,30.59868]],[[-97.5033,30.59774],[-97.49969,30.58952],[-97.49176,30.60117],[-97.49229,30.60246],[-97.5033,30.59774]],[[-97.49621,30.58191],[-97.49295,30.58292],[-97.49307,30.58831],[-97.49839,30.58652],[-97.49621,30.58191]],[[-97.48903,30.56487],[-97.48532,30.55644],[-97.47769,30.55523],[-97.48063,30.56751],[-97.4812,30.56088],[-97.48903,30.56487]],[[-97.45161,30.60909],[-97.44656,30.59704],[-97.41911,30.60629],[-97.42189,30.61267],[-97.42515,30.61188],[-97.42621,30.61211],[-97.42739,30.61384],[-97.45161,30.60909]],[[-97.42605,30.61229],[-97.42202,30.6129],[-97.42274,30.61485],[-97.42703,30.61395],[-97.42605,30.61229]],[[-97.42128,30.54355],[-97.4155,30.54472],[-97.41632,30.5472],[-97.41919,30.54695],[-97.42128,30.54355]],[[-97.41618,30.53923],[-97.41082,30.53849],[-97.4082,30.53689],[-97.40879,30.54779],[-97.41592,30.54725],[-97.41501,30.54405],[-97.41618,30.53923]],[[-97.38192,30.57923],[-97.37784,30.58052],[-97.3782,30.58136],[-97.38229,30.58014],[-97.38192,30.57923]],[[-97.3816,30.57737],[-97.37709,30.57874],[-97.37748,30.57967],[-97.38177,30.57833],[-97.3816,30.57737]],[[-97.36749,30.57909],[-97.37031,30.57818],[-97.36987,30.57711],[-97.36712,30.57801],[-97.36749,30.57909]]],"type":"Polygon"},"id":"4871948","properties":{"c":[30.56951,-97.42967],"geo_id":"4871948","name":"Taylor"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.99677,30.34476],[-97.98255,30.35732],[-97.97688,30.35143],[-97.97816,30.33967],[-97.99677,30.34476]]],"type":"Polygon"},"id":"4872578","properties":{"c":[30.34652,-97.98642],"geo_id":"4872578","name":"The Hills"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.30388,30.59032],[-97.29156,30.59163],[-97.2917,30.57904],[-97.30297,30.58372],[-97.30388,30.59032]]],"type":"Polygon"},"id":"4872824","properties":{"c":[30.5881,-97.29775],"geo_id":"4872824","name":"Thrall"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.82952,29.96766],[-97.80876,29.97694],[-97.79461,29.96578],[-97.7943,29.97745],[-97.77912,29.96464],[-97.76559,29.97884],[-97.76671,29.96171],[-97.77673,29.96209],[-97.80345,29.94124],[-97.79881,29.94557],[-97.82952,29.96766]],[[-97.81723,29.96858],[-97.80455,29.95321],[-97.79884,29.95966],[-97.80903,29.97594],[-97.81723,29.96858]],[[-97.79768,29.94707],[-97.78793,29.95782],[-97.79459,29.96371],[-97.80364,29.95241],[-97.79768,29.94707]],[[-97.79368,29.96488],[-97.79142,29.96291],[-97.79105,29.96322],[-97.79268,29.96584],[-97.79368,29.96488]],[[-97.78571,29.96059],[-97.78324,29.96071],[-97.78523,29.96328],[-97.78555,29.96299],[-97.78571,29.96059]]],"type":"Polygon"},"id":"4874216","properties":{"c":[29.96273,-97.79528],"geo_id":"4874216","name":"Uhland"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.92353,30.45527],[-97.91255,30.46314],[-97.90125,30.46273],[-97.91297,30.45704],[-97.9044,30.44519],[-97.8932,30.45337],[-97.89229,30.43916],[-97.91058,30.43034],[-97.91069,30.44806],[-97.91888,30.44527],[-97.92353,30.45527]]],"type":"Polygon"},"id":"4875752","properties":{"c":[30.44543,-97.90797],"geo_id":"4875752","name":"Volente"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.51905,30.23507],[-97.50943,30.22521],[-97.51408,30.23773],[-97.50406,30.23582],[-97.51127,30.242],[-97.50118,30.23425],[-97.50593,30.22733],[-97.48976,30.24526],[-97.49544,30.23315],[-97.49014,30.23191],[-97.48813,30.22707],[-97.47383,30.24426],[-97.49014,30.21406],[-97.50831,30.21954],[-97.51366,30.21358],[-97.51905,30.23507]],[[-97.51591,30.22434],[-97.50905,30.2196],[-97.50821,30.22036],[-97.51534,30.22521],[-97.51591,30.22434]],[[-97.50724,30.22963],[-97.50599,30.23083],[-97.50676,30.23142],[-97.50796,30.23015],[-97.50724,30.22963]],[[-97.49932,30.22872],[-97.49708,30.22726],[-97.49465,30.22789],[-97.49808,30.23012],[-97.49932,30.22872]],[[-97.49762,30.21841],[-97.49585,30.2175],[-97.49512,30.21864],[-97.49678,30.21952],[-97.49762,30.21841]],[[-97.49693,30.23153],[-97.49348,30.22924],[-97.49288,30.22996],[-97.4963,30.23222],[-97.49693,30.23153]],[[-97.49354,30.22102],[-97.49168,30.23055],[-97.49232,30.2321],[-97.49449,30.21955],[-97.49354,30.22102]]],"type":"Polygon"},"id":"4876924","properties":{"c":[30.22595,-97.49943],"geo_id":"4876924","name":"Webberville"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.61425,30.67616],[-97.57857,30.69041],[-97.5849,30.67483],[-97.56906,30.6764],[-97.58355,30.67133],[-97.57477,30.66472],[-97.58047,30.65679],[-97.58795,30.6731],[-97.59552,30.66403],[-97.61425,30.67616]]],"type":"Polygon"},"id":"4877056","properties":{"c":[30.67579,-97.59136],"geo_id":"4877056","name":"Weir"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.67205,30.46632],[-97.6709,30.46814],[-97.66872,30.46254],[-97.67126,30.46379],[-97.67205,30.46632]]],[[[-97.69782,30.44021],[-97.6955,30.44981],[-97.6866,30.4458],[-97.67525,30.4614],[-97.66828,30.45799],[-97.6719,30.42457],[-97.69782,30.44021]]]],"type":"MultiPolygon"},"id":"4877196","properties":{"c":[30.44328,-97.67905],"geo_id":"4877196","name":"Wells Branch"},"type":"Feature"},{"geometry":{"coordinates":[[[[-97.82036,30.28344],[-97.82098,30.28259],[-97.82351,30.28387],[-97.82448,30.28571],[-97.82036,30.28344]]],[[[-97.80123,30.30792],[-97.79021,30.29774],[-97.79992,30.28988],[-97.78748,30.28342],[-97.79272,30.27368],[-97.80802,30.27234],[-97.82822,30.29572],[-97.82157,30.30587],[-97.80123,30.30792]],[[-97.81332,30.28282],[-97.81633,30.28589],[-97.81666,30.28296],[-97.81384,30.28163],[-97.81332,30.28282]],[[-97.79701,30.28283],[-97.80274,30.28515],[-97.80414,30.27876],[-97.8007,30.2756],[-97.79701,30.28283]]]],"type":"MultiPolygon"},"id":"4877632","properties":{"c":[30.29201,-97.80828],"geo_id":"4877632","name":"West Lake Hills"},"type":"Feature"},{"geometry":{"coordinates":[[[-98.13205,29.98173],[-98.10909,29.98631],[-98.10681,30.00152],[-98.12046,30.00169],[-98.11855,30.01127],[-98.09359,30.00368],[-98.06935,30.01636],[-98.0504,30.00877],[-98.05376,29.99935],[-98.04326,29.98707],[-98.06985,29.98385],[-98.09054,29.96481],[-98.07964,29.9394],[-98.09378,29.93974],[-98.09465,29.94162],[-98.09452,29.97411],[-98.11586,29.97392],[-98.11488,29.96505],[-98.11741,29.97174],[-98.12824,29.96973],[-98.13205,29.98173]],[[-98.07986,29.99198],[-98.06531,29.98704],[-98.06489,29.99466],[-98.0555,29.99709],[-98.05771,30.0084],[-98.07325,30.00924],[-98.07986,29.99198]]],"type":"Polygon"},"id":"4879624","properties":{"c":[29.98487,-98.09059],"geo_id":"4879624","name":"Wimberley"},"type":"Feature"},{"geometry":{"coordinates":[[[[-98.10537,30.01241],[-98.10405,30.01247],[-98.10382,30.00997],[-98.10544,30.00963],[-98.10537,30.01241]]],[[[-98.12189,30.03364],[-98.10141,30.03238],[-98.09866,30.02218],[-98.12062,30.01962],[-98.12189,30.03364]]]],"type":"MultiPolygon"},"id":"4880058","properties":{"c":[30.02663,-98.1115],"geo_id":"4880058","name":"Woodcreek"},"type":"Feature"},{"geometry":{"coordinates":[[[-97.5268,30.12703],[-97.50662,30.16303],[-97.44591,30.12992],[-97.44304,30.13468],[-97.41499,30.11264],[-97.45945,30.09874],[-97.46178,30.11457],[-97.48236,30.12502],[-97.49431,30.10737],[-97.50226,30.12599],[-97.50558,30.12091],[-97.5268,30.12703]]],"type":"Polygon"},"id":"4880350","properties":{"c":[30.12872,-97.47776],"geo_id":"4880350","name":"Wyldwood"},"type":"Feature"}],"type":"FeatureCollection"}},
    mdAreas: null,
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

  trackMenuDismiss() {
    const down = (e) => {
      if (this.state.giveMenu) {
        const give = this._giveMenuEl;
        if (!(give && e.target && give.contains(e.target))) this.setState({ giveMenu: false });
      }
      if (this.state.fMenu) {
        const fh = this._fMenuEls[this.state.fMenu];
        if (!(fh && e.target && fh.contains(e.target))) this.setState({ fMenu: null, fMenuAt: -1 });
      }
      if (!this.state.marketMenu) return;
      const host = this._marketMenuEl;
      if (host && e.target && host.contains(e.target)) return;
      this.setState({ marketMenu: false, marketMenuAt: -1 });
    };
    const key = (e) => {
      if (this.state.lightbox) {
        if (e.key === "Escape") { e.preventDefault(); this.closeLightbox(); }
        else if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); this.stepLightbox(e.key === "ArrowLeft" ? -1 : 1); }
        else if (e.key === "Tab") {
          const box = this._lightboxEl;
          const controls = box ? Array.from(box.querySelectorAll("button")) : [];
          if (controls.length) {
            const at = controls.indexOf(document.activeElement);
            if (e.shiftKey) { if (at <= 0) { e.preventDefault(); controls[controls.length - 1].focus(); } }
            else if (at === controls.length - 1) { e.preventDefault(); controls[0].focus(); }
          }
        }
        return;
      }
      if (e.key !== "Escape") return;
      if (this.state.giveMenu) {
        this.setState({ giveMenu: false });
        if (this._giveButtonEl) this._giveButtonEl.focus();
      }
      if (this.state.fMenu) this.setState({ fMenu: null, fMenuAt: -1 });
      if (!this.state.marketMenu) return;
      this.setState({ marketMenu: false, marketMenuAt: -1 });
    };
    const out = (e) => {
      // A19 (A-LB3, 2026-09-09): a focusout-based trap was tried here — deferring focus back
      // into the dialog whenever it left for a non-null relatedTarget outside it — and found
      // not to hold in real Chromium: a null relatedTarget also occurs at the edges of the
      // dialog's own tabbable set, which the arm cannot tell apart from a window blur. Tab is
      // instead handled deterministically in the shared keydown closure above (A19.9).
      // `relatedTarget` is where focus is GOING, and a null one is the browser leaving the
      // document altogether — a window blur, which dismisses neither menu.
      const to = e.relatedTarget;
      if (!to) return;
      if (this.state.giveMenu) {
        const give = this._giveMenuEl;
        if (!(give && give.contains(to))) this.setState({ giveMenu: false });
      }
      if (this.state.fMenu) {
        const fh = this._fMenuEls[this.state.fMenu];
        if (!(fh && fh.contains(to))) this.setState({ fMenu: null, fMenuAt: -1 });
      }
      if (!this.state.marketMenu) return;
      const host = this._marketMenuEl;
      if (host && host.contains(to)) return;
      this.setState({ marketMenu: false, marketMenuAt: -1 });
    };
    this._onDocDown = down;
    this._onDocKey = key;
    this._onDocOut = out;
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("keydown", key, true);
    document.addEventListener("focusout", out, true);
  }

  componentWillUnmount() {
    if (this._onResize) window.removeEventListener("resize", this._onResize);
    if (this._onDocDown) document.removeEventListener("pointerdown", this._onDocDown, true);
    if (this._onDocKey) document.removeEventListener("keydown", this._onDocKey, true);
    if (this._onDocOut) document.removeEventListener("focusout", this._onDocOut, true);
    if (this._offViewport) this._offViewport();
  }

  loadAreas(market, keep) {
    if (!this.props.market) return;
    const asked = market || "Austin, TX";
    const at = this.props.market.viewport ? this.props.market.viewport() : null;
    if (!keep) this.setState({ mdAreas: null });
    if (this.props.market.viewport && at === null) return;
    const mine = () => (this.state.market || "Austin, TX") === asked && (this.props.market.viewport ? this.props.market.viewport() : null) === at;
    this.props.market.boundaries(asked, at).then(
      (areas) => { if (mine()) this.setState({ mdAreas: areas }); },
      () => { if (mine()) this.setState({ mdAreas: {} }); }
    );
  }

  componentDidMount() {
    this.trackWidth();
    this.trackMenuDismiss();
    const start = this.props.startScreen;
    if (start && start !== "gate") this.setState({ screen: start, auth: true });
    if (this.props.startViewport === "mobile") this.setState({ viewport: "mobile" });
    if (this.props.startGate) this.setState({ screen: "gate", gate: this.props.startGate });
    const me = this.props.me;
    if (me && me.state === "active" && !["verify", "reset", "invite"].includes(this.state.gate)) this.setState({ auth: true, screen: (this.props.startScreen && this.props.startScreen !== "gate") ? this.props.startScreen : "browse", email: me.email, me: { name: me.name, role: me.role, initials: me.initials } });
    else if (me && (me.state === "pending" || me.state === "needs_review")) this.setState({ screen: "gate", gate: "pending" });
    else if (me && me.state === "declined") this.setState({ screen: "gate", gate: "rejected" });
    else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });
    else if (me && me.state === "unverified") this.setState({ screen: "gate", gate: "check-email", email: me.email });
    if (me && me.state === "needs_review" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current) this.setState({ screen: "gate", gate: "answer", answer: Object.assign({}, this.state.answer, { applicationId: r.current.id, note: r.current.info_request || "" }) }); }, () => {});
    if (me && me.state === "declined" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current && r.current.fields) { const f = r.current.fields; this.setState({ apply: Object.assign({}, this.state.apply, { name: f.name || "", vin: f.vin_member_id || "", grad: f.school_year || "", state: f.license_state || "", employer: f.employer || "", intent: f.intent || "", affirm: !!f.affirm }) }); } }, () => {});
    if (this.props.startNotice) this.setState({ screen: "gate", gate: "signin", formNotice: this.props.startNotice });
    if (this.props.startAnswerNote) this.setState({ answer: Object.assign({}, this.state.answer, { note: this.props.startAnswerNote }) });
    if (this.state.gate === "verify" && !this.state.gateToken) this.setState({ gate: "verify-expired" });
    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));
    if (this.props.listings && me && me.state === "active" && (me.roles || []).indexOf("seller") > -1) this.reloadListings();
    if (this.props.startMyListings) this.setState({ myListings: this.props.startMyListings });
    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));
    this.loadAreas(this.state.market);
    if (this.props.market && this.props.market.onViewport) this._offViewport = this.props.market.onViewport(() => this.loadAreas(this.state.market, true));
  }

  // Arrow-key movement inside the Give menu. Focus IS the highlight — vinfoundation.org has
  // no focus style of its own either — so this moves focus and nothing else. Wraps both ways.
  giveFocus = (i) => {
    const els = (this._giveItemEls || []).filter(Boolean);
    if (!els.length) return;
    els[((i % els.length) + els.length) % els.length].focus();
  };

  money(n) {
    if (n == null || n === "") return "—";
    if (n >= 1000000) return "$" + (n / 1000000).toFixed(n >= 10000000 ? 0 : 2).replace(/\.00$/, "") + "M";
    return "$" + Math.round(n / 1000) + "K";
  }

  go = (screen) => () => {
    if (screen !== "gate" && !this.state.auth) return this.setState({ screen: "gate", gate: "signin", userMenu: false, fMenu: null, fMenuAt: -1 });
    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false, lightbox: null, lightboxFocus: false, fMenu: null, fMenuAt: -1 });
    return this.props.listings.patch(this.state.editingId, this.state.step, this.state.w, true).then(
      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "", lightbox: null, lightboxFocus: false, fMenu: null, fMenuAt: -1 }),
      (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })
    );
  };

  setF = (key) => (e) => {
    const v = e && e.target ? e.target.value : e;
    this.setState((s) => ({ f: Object.assign({}, s.f, { [key]: v }), loading: true }));
    clearTimeout(this._t);
    this._t = setTimeout(() => this.setState({ loading: false }), 320);
  };

  // The metro choice. One implementation, called by the dropdown rows and still accepting a
  // change event the way setF does, so the transition below is the one the <select> had.
  setMarket = (e) => {
    const v = e && e.target ? e.target.value : e;
    this.loadAreas(v);
    this.setState({ market: v, activeId: null, hoverId: null, loading: true, marketMenu: false, marketMenuAt: -1 }, () => {
      clearTimeout(this._t);
      this._t = setTimeout(() => this.setState({ loading: false }), 320);
    });
    // The choice unmounts the row the pointer or the keyboard was on, so focus would land on
    // <body>. A native select leaves the user on the control; so does this one.
    const host = this._marketMenuEl;
    const trigger = host && host.querySelector('button[aria-haspopup="listbox"]');
    if (trigger) trigger.focus();
  };

  // Bringing a row into view. The panel scrolls at its max-height as soon as the market list
  // is longer than the design's four, so both the arrow keys and the panel's own mount need
  // this: one while the rows are already there, one at the moment they arrive. The row is
  // resolved through the field this component recorded, not across the document: the id is
  // one this component mints, and setMarket's own trigger lookup is scoped the same way.
  scrollMarketOption = (i) => {
    const host = this._marketMenuEl;
    const row = host && host.querySelector("#market-opt-" + i);
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
  };

  // Moving the keyboard highlight. The rows are all in the DOM while the menu is open, so the
  // one being highlighted is scrolled into view here rather than after a re-render.
  moveMarketHighlight = (i) => {
    this.setState({ marketMenuAt: i });
    this.scrollMarketOption(i);
  };

  // Opening a filter dropdown. ONE open path for the whole family: the trigger and the arrow
  // keys both come here, so the cross-menu invariant (final review m7) is written once rather
  // than once per instance. Writing `fMenu` is what closes whichever sibling was open —
  // Object.assign semantics — so inside the family there is nothing to forget; the four keys
  // below are the only edges that leave it.
  openFilterMenu = (key, at) => {
    this.setState({ fMenu: key, fMenuAt: at, navMenu: false, userMenu: false, giveMenu: false, marketMenu: false, marketMenuAt: -1 });
  };

  // The filter choice. It calls the design's own setF, so the state transition and the 320 ms
  // loading settle are the ones the <select>'s onChange had, to the byte.
  setFilter = (key, v) => {
    this.setF(key)(v);
    this.setState({ fMenu: null, fMenuAt: -1 });
    // The choice unmounts the row the pointer or the keyboard was on, so focus would land on
    // <body>. A native select leaves the user on the control; so does this one.
    const host = this._fMenuEls && this._fMenuEls[key];
    const trigger = host && host.querySelector('button[aria-haspopup="listbox"]');
    if (trigger) trigger.focus();
  };

  // Bringing a row into view, scoped to the dropdown that owns it. Both the arrow keys and the
  // panel's own mount need this: one while the rows are already there, one at the moment they
  // arrive. The row is resolved through the field this component recorded, not across the
  // document — the ids are ones this component mints, as scrollMarketOption's are.
  scrollFilterOption = (key, i) => {
    const host = this._fMenuEls && this._fMenuEls[key];
    const row = host && host.querySelector("#f-opt-" + key + "-" + i);
    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
  };

  // Moving the keyboard highlight. The rows are all in the DOM while the panel is open, so the
  // one being highlighted is scrolled into view here rather than after a re-render.
  moveFilterHighlight = (key, i) => {
    this.setState({ fMenuAt: i });
    this.scrollFilterOption(key, i);
  };

  // ---- Browse Practices: map, market layers, results -------------------------------------------------

  // A24 (spec 9.4): the design's own boundary fixture, given the design's own figures.
  // Each polygon takes the value of the NEAREST community centroid - the one line of
  // `mosaicCells` that survives ("spatial ASSIGNMENT of existing community data, not
  // interpolation, and not new data"), applied to real Census boundaries instead of grid
  // cells, with longitude scaled by cos(lat) exactly as the mosaic scaled it.
  //
  // The value is taken as it comes and is NOT put through `num()`: by this point it is
  // already a number, parsed once by `communities()`, and a second pass would be a second
  // chance to lose something. (The older reason - that `num` stripped a leading minus, so
  // `num(-5.1)` was `5.1` and a decline read as growth - stopped being true with A24.43,
  // which taught it to read the first signed number and nothing after it.)
  areaSet(layer) {
    const src = (this.state.areas || {})[AREA_LEVEL[layer]];
    if (!src) return { type: "FeatureCollection", features: [] };
    const comms = this.communities().filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng));
    return {
      type: "FeatureCollection",
      features: src.features.map((f) => {
        const p = f.properties;
        let best = null, bestD = Infinity;
        for (let i = 0; i < comms.length; i++) {
          const s = comms[i];
          const dLat = s.lat - p.c[0];
          const dLng = (s.lng - p.c[1]) * Math.cos((p.c[0] * Math.PI) / 180);
          const d = dLat * dLat + dLng * dLng;
          if (d < bestD) { bestD = d; best = s; }
        }
        // The design's own alias, verbatim from `marketVals`: `communities()` names
        // these two fields `hh` and `vets`, and a fill layer reads the same objects the
        // symbols and the Compare rows do.
        const raw = best ? (layer === "households" ? best.hh : layer === "competition" ? best.vets : best[layer]) : undefined;
        return {
          type: "Feature", id: p.geo_id, geometry: f.geometry,
          properties: {
            geo_id: p.geo_id, name: p.name,
            value: (raw === undefined || raw === null) ? null : raw,
            moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false
          }
        };
      })
    };
  }

  // The ONE door every polygon enters by, whichever side produced it (spec 2.2): the
  // colour is `bucket()`s and the label is `fmtMetric()`s, so the fill and the legend
  // cannot disagree. A value that is absent OR suppressed takes the no-data class; a value
  // that is present takes its band even when its margin spans one (D-C36).
  areaVals(fc, layer) {
    const feats = (fc && fc.features) || [];
    return {
      type: "FeatureCollection",
      features: feats.map((f) => {
        const p = f.properties;
        const shown = p.value !== null && p.value !== undefined && !p.suppressed;
        const b = shown ? this.bucket(layer, p.value, true) : null;
        return {
          type: "Feature", id: p.geo_id, geometry: f.geometry,
          properties: {
            geo_id: p.geo_id, name: p.name, value: p.value, moe: p.moe,
            suppressed: !!p.suppressed, suppressReason: p.suppress_reason || null,
            ambiguous: !!p.band_ambiguous,
            color: shown ? b.color : NO_DATA_FILL,
            label: shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL,
            tip: this.areaTip(p, layer, shown)
          }
        };
      })
    };
  }

  // The hover tip, built ONCE. Every honesty line is the wording the market-data contract
  // already mandates, so the map says what the docked panel says. `growth` and `econ` carry
  // no published margin (D-NS17) and say why rather than being greyed.
  areaTip(p, layer, shown) {
    const meta = LAYER_META[layer] || {};
    const absent = p.suppressed
      ? (p.suppress_reason === "source_flag" ? "Not published for this county"
        : p.suppress_reason === "source_threshold" ? "The Census does not publish a ZIP-level count for a category with fewer than three establishments, though they are counted in its all-industry total."
        : "Estimate too imprecise to show at this geography")
      : "No data for this area";
    const margin = (p.moe !== null && p.moe !== undefined)
      ? "± " + this.fmtMetric(layer, p.moe) + (p.band_ambiguous ? " — this margin spans two legend bands." : "")
      : (layer === "growth"
          ? "Derived from two ACS 5-year periods. No combined margin of error is published."
          : layer === "econ"
            ? "Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies."
            : layer === "competition"
              ? "Counted within this " + AREA_LABEL[layer] + ". ZIP Code Business Patterns is published per ZIP code, which is this dataset’s own authoritative geography. Establishments include corporate-owned and specialty locations."
              : layer === "pets"
                ? "Modelled estimate: households × 0.57. Not an observed count."
                : "");
    return '<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">' +
      '<div style="font-size:12.5px;font-weight:800;color:#003a70">' + p.name + "</div>" +
      '<div style="font-size:11px;color:#494949;margin-top:3px">' + (meta.title || "") + "</div>" +
      '<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">' + (shown ? this.fmtMetric(layer, p.value) + (layer === "competition" ? " veterinary practices" : "") : NO_DATA_LABEL) + "</div>" +
      '<div style="font-size:10.5px;color:#494949;margin-top:4px">' + (shown ? margin : absent) + "</div>" +
      '<div style="font-size:10px;color:#767676;margin-top:5px">' + metaSource(layer, AREA_LABEL[layer] || "") + "</div>" +
    "</div>";
  }

  communities() {
    const market = this.state.market || "Austin, TX";
    return P.filter((p) => p.market === market && p.status === "published").map((p) => {
      const hh = p.hh != null ? num(p.hh) : undefined;
      return {
        id: p.id, name: p.area, lat: p.lat, lng: p.lng, communityLabel: p.communityLabel,
        pop: p.pop != null ? num(p.pop) : undefined, hh: hh, income: p.income != null ? num(p.income) : undefined,
        growth: p.growth != null ? num(p.growth) : undefined,
        pets: hh !== undefined ? Math.round(hh * 0.57) : undefined,
        econ: ECON_K[p.id] != null ? ECON_K[p.id] * 1000 : undefined,
        vets: VETS[p.id]
      };
    });
  }

  bucket(metric, v, area) {
    // `area` asks for the CHOROPLETH's breaks. Everything else on the screen classes a
    // community-scale figure and must keep asking for the design's own (A24.25).
    const cfg = (area && AREA_LAYERS[metric]) || VALUE_LAYERS[metric];
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
    // Abbreviated from ten thousand, not from one: a Census tract holds about 1,400
    // households and "1K" is the same label for 1,000 and for 1,499. `toLocaleString` is
    // the design's own separator, the one `p.sqft` already uses.
    return v >= 10000 ? Math.round(v / 1000) + "K" : Math.round(v).toLocaleString();
  }

  marketVals(list) {
    const s = this.state;
    const market = s.market || "Austin, TX";
    const cfg = MARKETS[market];
    const comms = this.communities();
    const valueLayer = s.mdValue === undefined ? "income" : s.mdValue;
    const layers = Object.assign(
      { competition: true, households: false, pets: false },
      s.mdLayers || {}
    );
    const sel = s.mdSel ? P.filter((x) => x.id === s.mdSel)[0] : null;
    const pal = PALETTES[this.props.layerPalette] || PALETTES.distinct;
    const ramp = (k) => pal[k] || BRAND_RAMP;
    const tightColumn = !!s.mdStrip;
    const activeSymbols = SYMBOL_KEYS.filter(
      (k) => k !== valueLayer && layers[k] && !(s.mdOff || {})[k === "competition" ? "vets" : k]
    );
    const selComm = sel ? comms.filter((c) => c.id === sel.id)[0] : null;
    // Hoisted out of the returned object so the LEGEND can see how many polygons were
    // actually drawn (A24.32). One call, one collection, no second classification pass.
    const areaFc = this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer);
    // "asked, not yet answered" — A24.41 keeps the legend mounted across it.
    const areasPending = !!this.props.market && s.mdAreas === null;

    const lats = comms.map((c) => c.lat), lngs = comms.map((c) => c.lng);
    const pad = 0.12;
    const minLat = Math.min.apply(null, lats) - pad, maxLat = Math.max.apply(null, lats) + pad;
    const minLng = Math.min.apply(null, lngs) - pad, maxLng = Math.max.apply(null, lngs) + pad;

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
      { n: "4", title: "Population Growth", blurb: "Change", src: "Census ACS population estimates", metric: "growth", caption: "Growth", layerName: "Population Growth" },
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
      driveCenter: (sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng)) ? [sel.lat, sel.lng] : cfg.center,
      layers,
      valueLayer,
      areas: areaFc,
      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {
        const vals = {};
        ["income", "pets", "growth", "households", "econ", "competition"].forEach((k) => {
          const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];
          if (raw == null) return;
          const b = this.bucket(k, raw);
          vals[k] = { t: b.t, color: b.color, label: this.fmtMetric(k, raw) };
        });
        return {
          name: c.name, lat: c.lat, lng: c.lng, vets: c.vets, values: vals,
          metricName: valueLayer ? LAYER_META[valueLayer].title : "",
          sourceNote: valueLayer ? metaSource(valueLayer, AREA_LABEL[valueLayer] || "") : ""
        };
      }),
      practices: list.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng)).map((p) => ({
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
        const mapSource = valueLayer ? metaSource(valueLayer, AREA_LABEL[valueLayer] || "") : "";
        return {
          title: meta.title || "No layer active",
          sub: meta.sub || "Choose a layer to shade the map",
          sourceLine: mapSource ? "Source: " + mapSource : "",
          sourceShort: mapSource ? "Source: " + mapSource.split(" · ")[0] : "",
          updatedLine: meta.updated || "",
          means: meta.means || "",
          why: meta.why || "",
          hasRamp: !!valueLayer && (areaFc.features.length > 0 || areasPending),
          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1 && (areaFc.features.length > 0 || areasPending),
          geoLine: AREA_LABEL[valueLayer] || "",
          ramp: valueLayer
            ? ramp(valueLayer).map((c, i) => ({
                style: "flex: 1; height: 9px; background: " + c + ";",
                label: ((AREA_LAYERS[valueLayer] || cfg).buckets)[i]
              })).concat(FILL_KEYS.indexOf(valueLayer) > -1
                ? [{ style: "flex: 1; height: 9px; background: " + NO_DATA_FILL + ";", label: NO_DATA_LABEL }]
                : [])
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
        const bar = (k) => {
          const v = raw(k);
          if (v == null) return undefined;
          const b = this.bucket(k, num(v));
          return "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + b.t * 92) + "%; background: " + b.color + ";";
        };
        return {
          name: c.name,
          aStyle: bar(valueLayer),
          bStyle: bar(s.mdCompare)
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
      toggleLegend: () => this.setState({ mdLegendOff: s.mdLegendOff !== true, mdLayerMenu: false, mdCompareMenu: false }),

      legendBtnStyle: "display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 14px; font-family: var(--rf-display); font-size: 12.5px; font-weight: 500; white-space: nowrap; box-shadow: 0 2px 8px rgba(0,58,112,.14); color: " +
        (s.mdLegendOff !== true ? "var(--vf-navy)" : "var(--vf-text)") +
        "; background: var(--vf-white); border: 1px solid " +
        (s.mdLegendOff !== true ? "var(--vf-accent)" : "var(--border-subtle)") +
        "; border-radius: 6px; cursor: pointer;",
      insightOpen: (() => {
        const vw = s.vw || (typeof window !== "undefined" ? window.innerWidth : 1440);
        // map column ≈ viewport − results rail − open detail panel
        const mapW = vw - 470 - (s.mdSel ? 366 : 0);
        return !!valueLayer && !s.mdInsightOff && s.mdLegendOff !== true && !s.mdCompareOpen && mapW >= 810;
      })(),
      dismissInsight: () => this.setState({ mdInsightOff: true }),
      showDrive: !!(sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng)),
      recenterKey: s.mdRecenter || 0,
      resetView: () => this.setState({ mdSel: null, mdRecenter: (s.mdRecenter || 0) + 1 }),
      selectArea: (name) => this.setState({ mdArea: name }),
      snapshotCount: "6 indicators · Census-sourced",
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
      stripCards: (() => {
        // What the snapshot's own figures describe: `comms` is one row per LISTING, so the
        // basis is the practice-area label the API serves, and only where the whole metro
        // agrees on one. Otherwise the design's own words, which is what the reference path
        // and every approved state renders - the design's fixtures carry no label at all.
        const labels = comms.map((c) => c.communityLabel).filter(Boolean);
        const stripBasis = (labels.length === comms.length && labels.length > 0 && labels.every((l) => l === labels[0]))
          ? labels[0] : "community level";
        return ["income", "pets", "competition", "growth", "households", "econ"]
        .filter((k) => enabled(k === "competition" ? "vets" : k))
        .map((k) => {
          const meta = LAYER_META[k];
          const cfg = VALUE_LAYERS[k];
          const on = valueLayer === k;
          const vals = comms.map((c) => (k === "households" ? c.hh : k === "competition" ? c.vets : c[k]))
            .filter((raw) => raw != null)
            .map((raw) => ({ raw: num(raw), t: this.bucket(k, num(raw)).t }));
          const mid = vals.length ? vals.map((v) => v.raw).sort((a, b) => a - b)[Math.floor(vals.length / 2)] : undefined;
          return {
            title: meta.title,
            value: (mid !== undefined) ? this.fmtMetric(k, mid) : undefined,
            valueNote: "metro median",
            src: metaSource(k, stripBasis),
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
        });
      })()
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
      const tiles = [
        ["exterior", "Exterior — street view"],
        ["exterior2", "Exterior — side elevation"],
        ["exterior3", "Exterior — parking and signage"],
        ["lobby", "Reception and waiting"],
        ["exam", "Exam room"],
        ["treatment", "Treatment area"]
      ].map((v, i) => {
        const id = "ph-" + p.id + "-" + v[0];
        return { id, caption: (p.photoCaptions && p.photoCaptions[i]) || v[1], index: i + 1, placeholder: name + " — " + ((p.photoCaptions && p.photoCaptions[i]) || v[1]), src: SRC[id] || (p.photos && p.photos[i]) || "", hasSrc: !!(SRC[id] || (p.photos && p.photos[i])), noSrc: !(SRC[id] || (p.photos && p.photos[i])) };
      });
      const extra = ((p.photos && p.photos.length > tiles.length) ? p.photos.slice(tiles.length) : []).map((src, k) => {
        const i = tiles.length + k;
        const cap = (p.photoCaptions && p.photoCaptions[i]) || ("Photo " + (i + 1));
        return { id: "ph-" + p.id + "-extra" + (k + 1), caption: cap, index: i + 1, placeholder: name + " — " + cap, src: src || "", hasSrc: !!src, noSrc: !src };
      });
      return tiles.concat(extra);
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
    const tiles = views.map((v, i) => ({
      id: "ph-" + p.id + "-" + v[0],
      caption: (p.photoCaptions && p.photoCaptions[i]) || v[1],
      index: i + 1,
      placeholder: name + " — " + ((p.photoCaptions && p.photoCaptions[i]) || v[1]),
      src: (p.photos && p.photos[i]) || "", hasSrc: !!(p.photos && p.photos[i]), noSrc: !(p.photos && p.photos[i])
    }));
    const extra = ((p.photos && p.photos.length > views.length) ? p.photos.slice(views.length) : []).map((src, k) => {
      const i = views.length + k;
      const cap = (p.photoCaptions && p.photoCaptions[i]) || ("Photo " + (i + 1));
      return { id: "ph-" + p.id + "-extra" + (k + 1), caption: cap, index: i + 1, placeholder: name + " — " + cap, src: src || "", hasSrc: !!src, noSrc: !src };
    });
    return tiles.concat(extra);
  }

  heroSrc(p) {
    return (p.photos && p.photos[0]) || (p.id === "p2" ? "/assets/photos/round-rock-exterior-street.webp" : "");
  }

  // Thumbnail-safe variant: reads at small sizes where the wide street view does not.
  thumbSrc(p) {
    return (p.photos && (p.photos[1] || p.photos[0])) || (p.id === "p2" ? "/assets/photos/round-rock-exterior-parking.jpeg" : "");
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
    return p.name || NAMES[p.id] || p.area + " Veterinary";
  }

  stateOf(market) { return (market || "Austin, TX").split(", ")[1] || "TX"; }

  // A19 — the photo lightbox (John, 2026-09-09): one implementation of open, close and step,
  // shared by the render values and by the document `key` closure in `trackMenuDismiss`.
  // Every closure that runs AFTER a render reads `this.state`: the reference replaces the state
  // object on each setState and the app mutates it in place, so a captured `s` is stale on one.
  openLightbox = (pid, at, e) => {
    this._lightboxOpener = (e && e.currentTarget) || null;
    this.setState({ lightbox: { pid, at }, lightboxFocus: true, navMenu: false, userMenu: false, giveMenu: false });
  };
  closeLightbox = () => {
    const back = this._lightboxOpener;
    this._lightboxOpener = null;
    this.setState({ lightbox: null, lightboxFocus: false });
    if (back && back.focus) back.focus();
  };
  lightboxPhotos() {
    const lb = this.state.lightbox;
    const p = lb ? P.filter((x) => x.id === lb.pid)[0] : null;
    return p ? this.photoSet(p).filter((ph) => ph.hasSrc) : [];
  }
  stepLightbox = (d) => {
    const lb = this.state.lightbox;
    const photos = this.lightboxPhotos();
    const n = photos.length;
    if (!lb || n < 2) return;
    const i = Math.max(0, photos.map((ph) => ph.id).indexOf(lb.at));
    this.setState({ lightbox: { pid: lb.pid, at: photos[((i + d) % n + n) % n].id } });
  };
  lightboxVals() {
    const lb = this.state.lightbox;
    const photos = this.lightboxPhotos();
    const n = photos.length;
    const i = lb ? Math.max(0, photos.map((ph) => ph.id).indexOf(lb.at)) : 0;
    const cur = photos[i];
    return {
      open: !!(lb && cur),
      src: cur ? cur.src : "",
      caption: cur ? cur.caption : "",
      counter: cur ? (i + 1) + "/" + n : "",
      label: cur ? "Photograph " + (i + 1) + " of " + n : "",
      multiple: n > 1,
      prev: () => this.stepLightbox(-1),
      next: () => this.stepLightbox(1),
      close: this.closeLightbox,
      backdrop: (e) => { if (e.target === e.currentTarget) this.closeLightbox(); },
      ref: (el) => {
        this._lightboxEl = el || null;
        if (!el || !this.state.lightboxFocus) return;
        this.setState({ lightboxFocus: false });
        setTimeout(() => el.focus(), 0);
      }
    };
  }

  marketPanel(sel, selComm, comms, market) {
    const s = this.state;
    const c = selComm || comms[0] || { pop: undefined, hh: undefined, income: undefined, growth: undefined, pets: undefined, vets: undefined };
    const per10k = (c.hh && c.vets) ? (c.vets / (c.hh / 10000)) : undefined;
    const incomeNat = 75149; // ACS 2023 U.S. median household income
    const incomeIdx = c.income ? Math.round(((c.income - incomeNat) / incomeNat) * 100) : undefined;
    const compLevel = (per10k !== undefined && per10k < 1.4) ? "Low" : (per10k !== undefined && per10k < 2.2) ? "Moderate" : (per10k !== undefined) ? "High" : undefined;
    const compFill = (per10k !== undefined && per10k < 1.4) ? 1 : (per10k !== undefined && per10k < 2.2) ? 2 : (per10k !== undefined) ? 3 : 0;
    const score = (c.income === undefined || c.growth === undefined || per10k === undefined) ? undefined : Math.max(0, Math.min(100, Math.round(
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
          open: (e) => this.openLightbox(sel.id, cur ? cur.id : "", e),
          openLabel: "Expand photo: " + (cur ? cur.caption : ""),
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
      hasDemo: sel.id !== "p8" && sel.pop != null,
      noDemo: sel.id === "p8" || sel.pop == null,
      overviewTitle: "Market Overview",
      hasOverviewScope: !!sel.communityLabel,
      overviewScope: sel.communityLabel || "",
      isInsights: (s.mdTab || "insights") === "insights",
      isOther: (s.mdTab || "insights") !== "insights",
      otherTitle: ({ overview: "Overview", financials: "Financials", property: "Property", contact: "Contact" })[s.mdTab] || "Overview",
      goInsights: () => this.setState({ mdTab: "insights" }),
      overviewTiles: [
        { v: (c.pop !== undefined) ? this.fmtMetric("households", c.pop) : undefined, k: "Population", sub: (c.growth !== undefined) ? ((c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)" + (sel.growthScope ? " · " + sel.growthScope : "")) : undefined },
        { v: (c.hh !== undefined) ? this.fmtMetric("households", c.hh) : undefined, k: "Households", sub: "ACS 5-year" },
        { v: (c.income !== undefined) ? "$" + Math.round(c.income / 1000) + "K" : undefined, k: "Median Income", sub: (incomeIdx !== undefined) ? ((incomeIdx > 0 ? "+" : "") + incomeIdx + "% vs US") : undefined },
        { v: (c.pets !== undefined) ? this.fmtMetric("households", c.pets) : undefined, k: "Est. Pet Households", sub: "derived estimate" }
      ],
      compEstab: (c.vets !== undefined) ? String(c.vets) : undefined,
      compPer10k: (per10k !== undefined) ? per10k.toFixed(1) : undefined,
      compLevel: (compLevel !== undefined) ? compLevel + " Competition" : undefined,
      compBars: (per10k === undefined) ? [] : [1, 2, 3].map((i) => ({
        style: "flex: 1; height: 8px; border-radius: 2px; background: " + (i <= compFill ? "#4c9a6a" : "#dbe4ea") + ";"
      })),
      oppTiles: [
        { icon: "$", label: (incomeIdx !== undefined) ? (incomeIdx > 25 ? "High" : incomeIdx > 0 ? "Above avg." : "Median") : "", sub: "Affluence", on: (incomeIdx !== undefined) && incomeIdx > 0 },
        { icon: "↗", label: (c.growth !== undefined) ? (c.growth > 20 ? "Strong" : c.growth > 8 ? "Steady" : "Flat") : "", sub: "Population Growth", on: (c.growth !== undefined) && c.growth > 8 },
        { icon: "⌂", label: (c.econ !== undefined) ? (c.econ > 650000 ? "Strong" : c.econ > 450000 ? "Typical" : "Lean") : "", sub: "Sector Payroll", on: (c.econ !== undefined) && c.econ > 450000 },
        { icon: "", label: "", sub: "", on: false }
      ].slice(0, 3).map((t) => ({
        icon: t.icon, label: t.label, sub: t.sub,
        iconStyle: "font-family: var(--rf-display); font-size: 15px; font-weight: 800; color: " + tone(t.on) + ";",
        labelStyle: "font-family: var(--rf-display); font-size: 13px; font-weight: 500; color: " + tone(t.on) + "; margin-top: 4px;"
      })),
      score: (score !== undefined) ? String(score) : undefined,
      scoreLabel: score === undefined ? undefined : score >= 75 ? "Attractive" : score >= 55 ? "Balanced" : "Challenging",
      scoreRing: (score === undefined) ? undefined : "width: 46px; height: 46px; border-radius: 999px; display: grid; place-items: center; background: conic-gradient(#4c9a6a " +
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

  openDraft(id, d, err) {
    this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, creating: false, wizErr: err || "", editingId: id, wizAssets: (d && d.assets) || [], w: Object.assign({ name: "", type: "Small animal", est: "", city: "", zip: "", anon: true, price: "", rev: "", revBand: false, docs: "", rooms: "", sqft: "", bldg: "Included", facility: "", desc: "", photos: 0, ownership: "Sole proprietor", hours: "", facilityType: "Standalone", docsLocked: true }, (d && d.w) || {}) });
  }

  reloadListings() {
    return this.props.listings.list().then((rows) => this.setState({ myListings: rows }), () => this.setState({ myListings: [] }));
  }

  statusPill(status) {
    const map = {
      published: ["Published", "#ffffff", "#003a70", "#003a70"],
      in_review: ["In VIN Foundation review", "#003a70", "#deecf7", "#deecf7"],
      draft: ["Draft", "#494949", "#f5f5f5", "#d4dde5"],
      paused: ["Paused", "#003a70", "#ffffff", "#339dde"],
      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"],
      declined: ["Declined", "#494949", "#ffffff", "#494949"]
    };
    const m = map[status] || map.draft;
    return { label: m[0], style: "flex: none; font-size: 11.5px; font-weight: 500; padding: 5px 12px; border-radius: 999px; color: " + m[1] + "; background: " + m[2] + "; border: 1px solid " + m[3] + ";" };
  }

  setListingStatus(id, status) {
    if (this.props.listings) {
      const action = status === "paused" ? "pause" : status === "withdrawn" ? "withdraw" : "republish";
      this.props.listings.setStatus(id, action).then(
        () => this.reloadListings(),
        (e) => this.setState((st) => ({ myListings: (st.myListings || []).map((l) => (l.id === id ? Object.assign({}, l, { note: (e && e.message) || "That could not be changed." }) : l)) }))
      );
    }
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
        rows: s.adminListingRows !== undefined ? s.adminListingRows : (this.props.adminListings ? [] : [
          [cell("Mixed practice — Bastrop", "Submitted September 1"), cell("Dr. Susan Ortiz", "$860K asking · $1.2M revenue · 2 doctors · building leased"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],
          [cell("Specialty practice — Pflugerville", "Submitted August 30"), cell("Dr. Nathan Weiss", "$2.65M asking · $3.8M revenue · 6 doctors · unit available separately"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],
          [cell("Small animal practice — Cedar Park", "Published August 24"), cell("Dr. James Whitfield", "$1.45M asking · 34 views · 2 requests"), cell(null, null, "Published", "ok"), cell(null, null, null, null, [A("Unpublish"), A("Edit")])],
          [cell("Small animal practice — Buda", "Paused by seller August 12"), cell("Dr. Helen Park", "$1.1M asking · hidden from search"), cell(null, null, "Paused", "info"), cell(null, null, null, null, [A("Contact seller")])],
          [cell("Small animal practice — Temple", "Flagged by two members"), cell("Unverified seller", "Figures appear copied from a broker listing; contact details in the description."), cell(null, null, "Flagged", "bad"), cell(null, null, null, null, [A("Investigate", "primary"), A("Unpublish", "danger")])]
        ])
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
      listings: (s.myListings !== undefined ? s.myListings : (this.props.listings ? [] : s.sellerListings)).map((l) => {
        const pill = this.statusPill(l.status);
        const actions = [];
        const openWizard = () => {
          if (!this.props.listings) return this.setState({ sellerView: "wizard", step: 1 });
          return this.props.listings.get(l.id).then(
            (d) => this.openDraft(l.id, d, ""),
            (e) => this.openDraft(null, null, (e && e.message) || "That listing could not be opened.")
          );
        };
        if (l.status === "draft") actions.push({ label: "Continue", go: openWizard });
        else actions.push({ label: "Edit", go: openWizard });
        if (l.status === "published") {
          actions.push({ label: "Pause", go: () => this.setListingStatus(l.id, "paused") });
          actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: l.id || "p1" }) });
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
      1: { blurb: "Start with what the practice is. You can change any of this before you submit.", fields: [text("name", "Practice name (staff-facing only)", "Hill Country Animal Hospital", "Never shown to buyers until you approve a request."), sel("type", "Practice type", ["Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other"]), text("est", "Year established", "1998"), sel("ownership", "Current ownership", ["Sole proprietor", "Sole proprietor (LLC)", "Sole proprietor (S-corp)", "Two-doctor partnership", "Three-doctor LLC", "Four-doctor partnership", "Four-doctor LLC", "Five-doctor LLC", "Multi-doctor LLC", "Other"])], toggles: [] },
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
    const slots = this.photoSet({ id: "wiz", type: w.type, photos: [], name: w.name, area: w.city });
    const uploads = this.props.listings
      ? (s.wizAssets || []).map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)), describe: a.kind !== "Photo" || !s.editingId ? null : () => (a.source === "asset" ? this.props.listings.caption(s.editingId, a.id, this.props.listings.describe()) : this.props.listings.describe(s.editingId, a.position, this.props.listings.describe())).then((d) => this.setState({ wizAssets: d.assets, wizErr: "" }), (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })) }))
      : [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));

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
      addPhoto: () => {
        if (!this.props.listings) return this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) }));
        if (!s.editingId) return null;
        return this.props.listings.attach(s.editingId).then(
          (d) => (d ? this.setState({ wizAssets: d.assets, wizErr: "" }) : null),
          (e) => this.setState({ wizErr: (e && e.message) || "That file could not be uploaded." })
        );
      },
      error: !!s.wizErr, errorText: s.wizErr,
      progressLabel: "Step " + step + " of 8",
      barStyle: "height: 100%; width: " + Math.round((step / 8) * 100) + "%; background: var(--color-blue); transition: width 300ms var(--easing-out);",
      steps: names.map((n, i) => ({
        n: String(i + 1), label: n, go: () => (!this.props.listings || !s.editingId
          ? this.setState({ step: i + 1, wizErr: "" })
          : this.props.listings.patch(s.editingId, step, w, true).then(
              (d) => this.setState({ step: i + 1, wizErr: "", wizAssets: d.assets }),
              (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }))),
        style: "display: flex; align-items: center; gap: 11px; padding: 9px 10px; text-align: left; font-family: var(--rf-display); font-size: 13.5px; font-weight: " + (step === i + 1 ? "600" : "400") + "; color: " + (step === i + 1 ? "var(--color-navy)" : "var(--color-steel)") + "; background: " + (step === i + 1 ? "var(--rf-band)" : "transparent") + "; border: 0; border-radius: 6px; cursor: pointer;",
        dotStyle: "flex: none; width: 22px; height: 22px; border-radius: 999px; display: grid; place-items: center; font-size: 11px; font-weight: 700; color: " + (step > i + 1 ? "var(--color-white)" : step === i + 1 ? "var(--color-white)" : "var(--color-steel)") + "; background: " + (step > i + 1 ? "var(--vf-navy)" : step === i + 1 ? "var(--color-blue)" : "var(--color-off-white)") + "; border: 1px solid " + (step >= i + 1 ? "transparent" : "var(--border-subtle)") + ";"
      })),
      saveNote: "Saved automatically",
      nextLabel: step === 7 ? "Preview listing" : "Continue",
      backStyle: "font-family: var(--rf-display); height: 48px; padding: 0 20px; font-size: 14px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: " + (step === 1 ? "var(--border-subtle)" : "var(--color-navy)") + "; background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: " + (step === 1 ? "default" : "pointer") + ";",
      back: () => (!this.props.listings || !s.editingId
        ? this.setState({ step: Math.max(1, step - 1), wizErr: "" })
        : this.props.listings.patch(s.editingId, step, w, true).then(
            (d) => this.setState({ step: Math.max(1, step - 1), wizErr: "", wizAssets: d.assets }),
            (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }))),
      next: () => {
        if (step === 1 && (!w.name || !w.est)) return this.setState({ wizErr: "Practice name and year established are needed before you continue." });
        if (step === 2 && (!w.city || !w.zip)) return this.setState({ wizErr: "A city and ZIP code are needed to place your practice on the map." });
        if (step === 3 && (!w.price || (!w.rev && !w.revBand))) return this.setState({ wizErr: "Enter an asking price and either an exact revenue figure or choose the range option." });
        if (!this.props.listings || !s.editingId) return this.setState({ step: Math.min(8, step + 1), wizErr: "" });
        return this.props.listings.patch(s.editingId, step, w).then(
          (d) => this.setState({ step: Math.min(8, step + 1), wizErr: "", wizAssets: d.assets }),
          (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })
        );
      },
      previewTitle: (w.type || "Small animal") + " practice — " + (w.city || "Your community"),
      previewRows: [
        { k: "Practice type", v: w.type || "Small animal" },
        { k: "General location", v: (w.city || "\u2014") + (w.city && w.state ? ", " + w.state : "") },
        { k: "Established", v: w.est || "\u2014" },
        { k: "Asking price", v: w.price ? "$" + w.price : "\u2014" },
        { k: "Gross revenue", v: w.rev ? (w.revBand ? "Range shown to buyers" : "$" + w.rev) : "\u2014" },
        { k: "Doctors", v: w.docs || "\u2014" },
        { k: "Exam rooms", v: w.rooms || "\u2014" },
        { k: "Square feet", v: w.sqft || "\u2014" },
        { k: "Property", v: w.bldg === "Included" ? "Included in sale" : w.bldg === "Leased" ? "Leased" : "Available separately" },
        { k: "Photos attached", v: String(uploads.filter((u) => u.kind === "Photo").length) }
      ],
      previewNote: w.anon
        ? "Practice name and street address are hidden. Buyers see the community and an approximate map pin until you approve their request."
        : "Practice name and address are visible to every approved buyer. Turn on generalized location in step 7 if you are still operating.",
      submit: () => (this.props.listings && s.editingId
        ? this.props.listings.submit(s.editingId).then(() => this.reloadListings(), (e) => this.setState({ wizErr: (e && e.message) || "That could not be submitted." }))
        : Promise.resolve()) && this.setState({ wizSubmitted: true, sellerListings: [{ id: "s" + Date.now(), title: ((w.type || "Small animal") + " practice — " + (w.city || "New listing")), meta: (w.price ? "$" + w.price : "Price to be set") + " · " + (w.docs || "?") + " doctors", status: "in_review", note: "Submitted just now · awaiting VIN Foundation review" }].concat(this.state.sellerListings) })
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
      subtitle: p.area + ", " + this.stateOf(p.market) + " · Established " + p.est,
      listed: p.listed,
      statusLabel: "Accepting inquiries",
      priceLabel: this.money(p.price),
      priceNote: "Practice only. " + bldg.toLowerCase() + ".",
      morePhotos: "+6 more photos",
      photos: this.photoSet(p).map((ph) => ph.hasSrc ? Object.assign({}, ph, { open: (e) => this.openLightbox(p.id, ph.id, e), openLabel: "Expand photo: " + ph.caption }) : ph),
      photoHeroId: "ph-" + p.id + "-exterior",
      photoHeroHint: this.practiceName(p) + " — exterior, street view",
      canRequest: !sent,
      alreadySent: sent,
      sentLabel: unlocked ? "Seller accepted your request" : req && req.status === "declined" ? "Seller declined this request" : "Request sent — awaiting the seller",
      sentNote: unlocked ? "Financial packet and floor plans are now open to you." : req && req.status === "declined" ? "The seller is not engaging further on this listing." : "Sellers usually respond within a week.",
      disclosure: "This seller is still operating the practice. Street address, practice name and staff names stay hidden until they approve your request. " +
        (unlocked ? "You have been granted access to the full financial packet." : "Documents marked locked open only with seller approval."),
      hasDemo: p.id !== "p8" && p.pop != null,
      noDemo: p.id === "p8" || p.pop == null,
      demoScope: "Figures describe " + (p.communityLabel ? "the area " + p.communityLabel.charAt(0).toLowerCase() + p.communityLabel.slice(1) : "the community around the practice") + ", not the practice itself.",
      demo: [
        { k: "Population", v: p.pop, sub: p.communityLabel || "Community, 2023" },
        { k: "Growth", v: (() => { const g = (p.growth || "").split(" since "); return g[0]; })(), sub: (() => { const g = (p.growth || "").split(" since "); const y = g.length > 1 ? g[1] : ""; if (!p.growthScope) return y ? "Since " + y : ""; return y ? p.growthScope + " · since " + y : p.growthScope; })() },
        { k: "Median income", v: p.income, sub: p.incomeNote || "Household, 2023" },
        { k: "Households", v: (p.hh || "").replace(" households", ""), sub: p.communityLabel || "In the community" }
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
            { k: "General location", v: p.area + ", " + this.stateOf(p.market) },
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
      },
      "check-email": {
        kicker: "Almost there", title: "Check your email",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "We sent a verification link to " + (s.signup.email || s.email) + ". It is valid for 24 hours. Open it to confirm your address, then sign in to complete your access request.",
        meta: [{ k: "Sent to", v: s.signup.email || s.email }, { k: "Link valid for", v: "24 hours" }],
        primary: { label: "Send it again", go: () => { if (!this.props.auth) return; return (!s.signup.pw && this.props.me ? this.props.auth.resendVerification() : this.props.auth.signUp(s.signup.email || s.email, s.signup.pw)).catch(() => {}); } }
      },
      "verify-expired": {
        kicker: "Link expired", title: "This link is no longer valid",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "Verification links work once and expire after 24 hours. Request a new one with the same email and password.",
        meta: [],
        primary: { label: "Request a new link", go: () => this.setState({ gate: "signup" }) }
      },
      "reset-expired": {
        kicker: "Link expired", title: "This link is no longer valid",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "Reset links work once and expire after 1 hour.",
        meta: [],
        primary: { label: "Request a new link", go: () => this.setState({ gate: "forgot" }) }
      },
      unavailable: {
        kicker: "Access", title: "This page is not available to your account",
        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",
        body: "Your approved access does not include this page. If you think it should, write to the VIN Foundation from the address on your account.",
        meta: [],
        primary: { label: "Back to Browse Practices", go: () => this.setState({ screen: "browse" }) }
      }
    };

    return {
      isDesktop: s.viewport === "desktop",
      nav,
      navExpanded: !!s.auth && vw >= 1050,
      navCollapsed: !!s.auth && vw < 1050,
      navMenuOpen: !!s.navMenu,
      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false, fMenu: null, fMenuAt: -1, marketMenu: false, marketMenuAt: -1 }),
      subBrandStyle: "width: 1px; height: 30px; background: var(--rf-line); display: " + (vw < 1050 ? "none" : "block") + ";",
      subBrandTextStyle: "font-family: var(--rf-display); font-size: 15px; font-weight: 800; letter-spacing: -.005em; color: var(--color-blue); white-space: nowrap; display: " +
        (vw < 1050 ? "none" : "block") + ";",
      identityStyle: "line-height: 1.25; display: " + (vw < 1180 ? "none" : "block") + ";",
      me: Object.assign({ email: s.email }, s.me),
      userMenuOpen: !!s.userMenu,
      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, marketMenu: false, marketMenuAt: -1 }),
      // The Give control, measured on vinfoundation.org (John, 2026-09-08). The literals are
      // the live site's, not this design's tokens: #339dde is the idle pill, #07386f the
      // hover/open pill and the panel border and the row text, 10px the pill radius, 4.34px
      // the gap from the pill to the 3px underline, 28px the gap from the pill to the panel.
      giveMenuOpen: !!s.giveMenu,
      // `giveMenuAt: null` on every pointer open: the pending index below belongs to the
      // KEYBOARD, and a stale one would drag a mouse user into the list on the next open.
      // `marketMenu` too (final review m7): the invariant is that opening one menu closes
      // the others, and Browse renders this control and the metro listbox on one screen.
      toggleGiveMenu: () => this.setState({ giveMenu: !s.giveMenu, giveMenuAt: null, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1, fMenu: null, fMenuAt: -1 }),
      giveMenuRef: (el) => { this._giveMenuEl = el || null; },
      giveButtonRef: (el) => { this._giveButtonEl = el || null; },
      // The panel's own mount is the first moment its links exist, so it is where an arrow
      // key that OPENED the menu spends its pending index — the arrow itself cannot, having
      // seeded it while the sc-if was still unrendered. Same callback-ref idiom the compare
      // menu ships (md.compareMenuRef) and A13 reuses for marketPanelRef, and it fires on
      // mount on both targets, children before parent, so the row refs are already in.
      // Spent once: a re-render mounts the panel again and must not re-steal focus.
      givePanelRef: (el) => {
        const at = this.state.giveMenuAt;
        if (!el || at == null) return;
        this.setState({ giveMenuAt: null });
        this.giveFocus(at);
      },
      giveWrapStyle: "position: relative; display: flex; align-items: center;",
      giveButtonStyle: "display: flex; align-items: center; padding: 2px 22px; font-family: 'Montserrat', var(--rf-display); font-size: 18px; font-weight: 600; line-height: 24.3px; white-space: nowrap; color: #ffffff; background: " +
        (s.giveMenu ? "#07386f" : "#339dde") + "; border: 0; border-radius: 10px; cursor: pointer; transition: background .4s;",
      giveUnderlineStyle: "position: absolute; left: 0; right: 0; top: calc(100% + 4.34px); height: 3px; background: #339dde; transform-origin: center; transition: transform .3s cubic-bezier(.58,.3,.005,1); transform: scaleX(" +
        (s.giveMenu ? "1" : "var(--rf-give-underline, 0)") + ");",
      giveLinks: [
        { label: "Annual Fund", href: "https://vinfoundation.org/give/" },
        { label: "Cor Group", href: "https://vinfoundation.org/cor/" },
        { label: "Legacy Giving", href: "https://vinfoundation.org/legacy-giving/" },
        { label: "Dr. Sophia Yin Memorial Fund", href: "https://vinfoundation.org/resources/dr-sophia-yin-memorial-fund/" }
      ].map((g, i) => Object.assign({}, g, {
        rowStyle: "display: flex; align-items: center; padding: 8px 20px; border-left: 8px solid transparent; font-family: 'Montserrat', var(--rf-display); font-size: 14px; font-weight: 600; line-height: 21px; color: #07386f; background: none; white-space: nowrap; text-decoration: none;",
        ref: (el) => { const a = this._giveItemEls || (this._giveItemEls = []); a[i] = el || null; },
        keys: (e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); return this.giveFocus(i + 1); }
          if (e.key === "ArrowUp") { e.preventDefault(); return this.giveFocus(i - 1); }
          if (e.key === "Home") { e.preventDefault(); return this.giveFocus(0); }
          if (e.key === "End") { e.preventDefault(); return this.giveFocus(-1); }
        },
        pick: () => this.setState({ giveMenu: false })
      })),
      giveMenuKeys: (e) => {
        // Home and End, on the TRIGGER as well as inside the menu, and only while the menu
        // is open — exactly where marketMenuKeys has them (final review m6). With the menu
        // shut there is no list for an end to be an end of.
        if (s.giveMenu && (e.key === "Home" || e.key === "End")) {
          e.preventDefault();
          return this.giveFocus(e.key === "Home" ? 0 : -1);
        }
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
        e.preventDefault();
        const at = e.key === "ArrowDown" ? 0 : -1;
        if (s.giveMenu) return this.giveFocus(at);
        // Already-open: the panel is mounted, so focus moves here and now. Opening CANNOT do
        // that — the app's setState runs its callback synchronously (dc-logic.js) and Vue
        // has not rendered the panel yet, so the index is seeded and givePanelRef spends it.
        this.setState({ giveMenu: true, giveMenuAt: at, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1, fMenu: null, fMenuAt: -1 });
      },
      signOut: () => (this.props.listings && s.sellerView === "wizard" && s.editingId
          ? this.props.listings.patch(s.editingId, s.step, s.w, true).catch(() => {})
          : Promise.resolve()
        ).then(() => (this.props.auth ? this.props.auth.signOut().catch(() => {}) : Promise.resolve())).then(() => this.setState({
        userMenu: false, auth: false, screen: "gate", gate: "signin", pw: "",
        interest: "closed", activeId: null, hoverId: null, sellerView: "dash", wizSubmitted: false, formError: "",
        lightbox: null, lightboxFocus: false
      })),
      goHome: this.go("gate"),
      showGate: s.screen === "gate",
      gateSignin: s.screen === "gate" && s.gate === "signin",
      gateApply: s.screen === "gate" && s.gate === "apply",
      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected" || s.gate === "check-email" || s.gate === "verify-expired" || s.gate === "reset-expired" || s.gate === "unavailable"),
      status: statusMap[s.gate] || statusMap.pending,
      gatePoints: [
        { n: "1", title: "Approved members only", body: "The VIN Foundation reviews every applicant. Corporate groups and consolidators are not admitted." },
        { n: "2", title: "Sellers control what buyers can see", body: "The property is accurately mapped, but financial information, and floor plans are only shared with the seller’s approval." },
        { n: "3", title: "One clear next step", body: "Buyers express interest; sellers decide whether to engage. No brokers in the middle." }
      ],
      form: { email: s.email, pw: s.pw, error: !!(s.formError || s.formNotice), errorText: s.formError || s.formNotice },
      setEmail: (e) => this.setState({ email: e.target.value, formError: "" }),
      setPw: (e) => this.setState({ pw: e.target.value, formError: "" }),
      signIn: () => {
        if (!s.email || !s.pw) return this.setState({ formError: "Enter both your email and password." });
        if (!this.props.auth) return this.setState({ screen: "browse", formError: "", auth: true });
        return this.props.auth.signIn(s.email, s.pw).then(
          (me) => this.setState({ screen: "browse", formError: "", auth: true, email: me.email, me: { name: me.name, role: me.role, initials: me.initials } }),
          (e) => this.setState({ formError: (e && e.message) || "Sign-in failed.", auth: false, screen: "gate" })
        );
      },
      signedIn: !!s.auth,
      signedOut: !s.auth,
      goSignInScreen: () => this.setState({ screen: "gate", gate: "signin" }),
      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: (s.auth || !this.props.auth) ? "apply" : "signup" }); },
      // Reaching the sign-in card means signing in as SOMEBODY, so whoever is signed in now is on their way out — the
      // same rule on every card that leads here: a status card's "Sign in", and the account cards' "Back to sign in".
      goSignin: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", formNotice: "" }); if ((s.auth || this.props.me) && this.props.auth) return this.props.auth.signOut().then(show, show); show(); },
      goForgot: (e) => { if (e) e.preventDefault(); this.setState({ gate: "forgot", formError: "", formNotice: "" }); },
      goSignup: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signup", formError: "", formNotice: "" }); },
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
      gateSignup: s.screen === "gate" && s.gate === "signup",
      gateForgot: s.screen === "gate" && s.gate === "forgot",
      gateReset: s.screen === "gate" && s.gate === "reset",
      gateInvite: s.screen === "gate" && s.gate === "invite",
      gateAnswer: s.screen === "gate" && s.gate === "answer",
      signupForm: { email: s.signup.email, pw: s.signup.pw, error: !!s.signup.error, errorText: s.signup.error },
      setSignupEmail: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { email: e.target.value, error: "" }) })),
      setSignupPw: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { pw: e.target.value, error: "" }) })),
      submitSignup: () => {
        const f = s.signup;
        if (!f.email || !f.pw) return this.setState({ signup: Object.assign({}, f, { error: "Enter both your email and password." }) });
        if (!this.props.auth) return this.setState({ gate: "check-email" });
        return this.props.auth.signUp(f.email, f.pw).then(() => this.setState({ gate: "check-email", email: f.email }), (e) => this.setState({ signup: Object.assign({}, f, { error: (e && e.message) || "Sign-up failed." }) }));
      },
      forgotForm: { email: s.forgot.email, error: !!s.forgot.error, errorText: s.forgot.error },
      setForgotEmail: (e) => this.setState((st) => ({ forgot: Object.assign({}, st.forgot, { email: e.target.value, error: "" }) })),
      submitForgot: () => {
        const f = s.forgot;
        if (!f.email) return this.setState({ forgot: Object.assign({}, f, { error: "Enter your email." }) });
        const done = () => this.setState({ gate: "signin", formNotice: "If that address has an account, a reset link is on its way. It is valid for 1 hour." });
        if (!this.props.auth) return done();
        return this.props.auth.forgot(f.email).then(done, (e) => this.setState({ forgot: Object.assign({}, f, { error: (e && e.message) || "Request failed." }) }));
      },
      resetForm: { pw: s.reset.pw, pw2: s.reset.pw2, error: !!s.reset.error, errorText: s.reset.error },
      setResetPw: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw: e.target.value, error: "" }) })),
      setResetPw2: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw2: e.target.value, error: "" }) })),
      submitReset: () => {
        const f = s.reset;
        if (!f.pw || !f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "Enter your new password twice." }) });
        if (f.pw !== f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "The two passwords do not match." }) });
        const done = () => this.setState({ gate: "signin", gateToken: "", reset: { pw: "", pw2: "", error: "" }, formNotice: "Password updated. Sign in with your new password." });
        if (!this.props.auth) return done();
        return this.props.auth.reset(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "reset-expired", gateToken: "" }) : this.setState({ reset: Object.assign({}, f, { error: (e && e.message) || "Reset failed." }) }));
      },
      inviteForm: { pw: s.invite.pw, pw2: s.invite.pw2, error: !!s.invite.error, errorText: s.invite.error },
      setInvitePw: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw: e.target.value, error: "" }) })),
      setInvitePw2: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw2: e.target.value, error: "" }) })),
      submitInvite: () => {
        const f = s.invite;
        if (!f.pw || !f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "Enter your new password twice." }) });
        if (f.pw !== f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "The two passwords do not match." }) });
        const done = () => this.setState({ gate: "signin", gateToken: "", invite: { pw: "", pw2: "", error: "" }, formNotice: "Your password is set. Sign in with your email and the password you just chose." });
        if (!this.props.auth) return done();
        return this.props.auth.acceptInvite(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "signin", gateToken: "", formNotice: "This invitation link is no longer valid. Ask the VIN Foundation for a new one." }) : this.setState({ invite: Object.assign({}, f, { error: (e && e.message) || "Could not set the password." }) }));
      },
      answerForm: { text: s.answer.text, note: s.answer.note, error: !!s.answer.error, errorText: s.answer.error },
      setAnswer: (e) => this.setState((st) => ({ answer: Object.assign({}, st.answer, { text: e.target.value, error: "" }) })),
      submitAnswer: () => {
        const f = s.answer;
        if (!f.text) return this.setState({ answer: Object.assign({}, f, { error: "Write your answer first." }) });
        if (!this.props.auth) return this.setState({ gate: "pending" });
        return this.props.auth.answer(f.applicationId, f.text).then(() => this.setState({ gate: "pending" }), (e) => this.setState({ answer: Object.assign({}, f, { error: (e && e.message) || "Could not send your answer." }) }));
      },
      goSignOut: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", auth: false, formNotice: "" }); if (this.props.auth) return this.props.auth.signOut().then(show, show); show(); },
      submitApply: () => {
        const a = s.apply;
        if (!a.name || !a.grad || !a.intent) {
          return this.setState({ apply: Object.assign({}, a, { error: "Name, school and year, and a short note about your intent are required." }) });
        }
        if (!this.props.auth) return this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });
        return this.props.auth.apply("buyer", { name: a.name, vin_member_id: a.vin, school_year: a.grad, license_state: a.state, employer: a.employer, intent: a.intent, affirm: !!a.affirm }).then(() => this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" }), (e) => this.setState({ apply: Object.assign({}, a, { error: (e && e.message) || "Your request could not be sent." }) }));
      },
      resultCount: list.length,

      isBrowse: false,
      // The metro SELECT is a dropdown list in this design's own style, not the operating
      // system's popup: the same trigger + role="listbox" panel the Market data card uses.
      marketMenuOpen: !!s.marketMenu,
      // `giveMenu: false`: opening one menu closes the others, in every direction (final
      // review m7). The global pointerdown and focusout listeners covered a pointer and a
      // Tab; a pure-keyboard user could hold this listbox and the header's Give menu open
      // at once, and then shut both with one Escape.
      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, userMenu: false }),
      // On the TRIGGER, which is always rendered: a shut menu has no active descendant, and
      // null is what both renderers omit the attribute for (a string would spell a dead id).
      marketActiveId: s.marketMenu ? "market-opt-" + s.marketMenuAt : null,
      marketTriggerLabel: (s.market || "Austin, TX") + " metro",
      marketFieldStyle: "position: relative; display: flex; align-items: center; gap: 9px; height: 40px; padding: 0 8px 0 15px; min-width: 300px; background: var(--vf-neutral); border: 1px solid " +
        (s.marketMenu ? "var(--vf-accent)" : "var(--border-subtle)") + "; border-radius: 6px;",
      marketSelectStyle: "display: flex; align-items: center; gap: 8px; flex: 1; height: 36px; padding: 0; border: 0; outline: none; background: none; font-size: 14px; font-weight: 500; color: var(--vf-navy); cursor: pointer;",
      marketCaretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +
        (s.marketMenu ? "180deg" : "0deg") + ");",
      marketMenuRef: (el) => { this._marketMenuEl = el || null; },
      // The panel's own mount is when the option rows first exist, so it is where OPENING
      // scrolls the highlighted row into view — the arrow keys cannot, having seeded the
      // highlight while the panel was still unrendered. Same callback-ref idiom the compare
      // menu already ships (md.compareMenuRef), and it fires on mount on both targets.
      marketPanelRef: (el) => { if (el) this.scrollMarketOption(this.state.marketMenuAt); },
      marketMenuKeys: (e) => {
        const keys = Object.keys(MARKETS);
        // Math.max: a market MARKETS no longer holds (Seed Listings drops a metro with no
        // listings left) gives indexOf -1, and keys[-1] would reach setMarket as undefined.
        const cur = Math.max(0, keys.indexOf(s.market || "Austin, TX"));
        const at = s.marketMenuAt == null || s.marketMenuAt < 0 ? cur : s.marketMenuAt;
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur, fMenu: null, fMenuAt: -1, navMenu: false, userMenu: false, giveMenu: false });
          return this.moveMarketHighlight((at + (e.key === "ArrowDown" ? 1 : keys.length - 1)) % keys.length);
        }
        if (!s.marketMenu) return;
        if (e.key === "Home" || e.key === "End") {
          e.preventDefault();
          return this.moveMarketHighlight(e.key === "Home" ? 0 : keys.length - 1);
        }
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          return this.setMarket(keys[at]);
        }
      },
      marketOptions: Object.keys(MARKETS).map((m, i) => {
        const on = (s.market || "Austin, TX") === m;
        const hi = s.marketMenuAt === i;
        return {
          label: m + " metro", selected: on,
          go: () => this.setMarket(m),
          optId: "market-opt-" + i,
          rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +
            (on ? "800" : "500") + "; color: var(--vf-navy); background: " +
            (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",
          tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +
            (on ? "1" : "0") + ";"
        };
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
      toggleMore: () => this.setState({ moreFilters: !s.moreFilters, fMenu: null, fMenuAt: -1 }),
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
      ].map((fl) => {
        // Each additional filter is a dropdown list in this design's own style, not the
        // operating system's popup: the SAME trigger + role="listbox" panel A26.2 gives the
        // five on the toolbar, and the same state slot — the eight filter keys are disjoint,
        // so `fMenu` still names exactly one dropdown across both loops.
        //
        // The comment sits INSIDE the map body, not between the array rows and `].map(`:
        // `tests/seeds/test_hospitals_json.py`'s `_MORE_BLOCK` reads the three option arrays
        // out of the design and requires `      ]` to follow the last row directly, and it
        // fails loudly rather than silently testing nothing when it does not. A26.2 learned
        // that on its sibling `_BAR_BLOCK`.
        const cur = s.f[fl.key] || "Any";
        const open = s.fMenu === fl.key;
        // Math.max: a value `f` holds that this option list does not would give indexOf -1 and
        // index the array out of bounds — the guard marketMenuKeys carries for a dropped metro.
        const sel = Math.max(0, fl.options.findIndex((o) => o[0] === cur));
        const at = open && s.fMenuAt >= 0 ? s.fMenuAt : sel;
        return {
          // The popover's own caption, unchanged — and it is the trigger's accessible name
          // too: a <label> does not name a <button>, which takes its name from its own
          // contents first, so the same string is spelled again rather than a new one invented.
          label: fl.label,
          open,
          listId: "f-listbox-" + fl.key,
          // On the TRIGGER, which is always rendered: a shut dropdown has no active descendant,
          // and null is what both renderers omit the attribute for (a string would spell a dead
          // id). Keyed on fl.key as well, so a sibling never claims another's highlight.
          activeId: open ? "f-opt-" + fl.key + "-" + s.fMenuAt : null,
          // What the closed <select> displayed. `cur` keeps the design's own `|| "Any"` guard:
          // the state literal seeds the five TOOLBAR keys and none of these three.
          triggerLabel: fl.options[sel][1],
          toggle: () => (open ? this.setState({ fMenu: null, fMenuAt: -1 }) : this.openFilterMenu(fl.key, sel)),
          hostRef: (el) => { const m = this._fMenuEls || (this._fMenuEls = {}); m[fl.key] = el || null; },
          // The panel's own mount is when the option rows first exist, so it is where OPENING
          // scrolls the highlighted row into view — the arrow keys cannot, having seeded the
          // highlight while the panel was still unrendered (A13/A14 review round 1, C1).
          panelRef: (el) => { if (el) this.scrollFilterOption(fl.key, this.state.fMenuAt); },
          keys: (e) => {
            const n = fl.options.length;
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              if (!open) return this.openFilterMenu(fl.key, sel);
              return this.moveFilterHighlight(fl.key, (at + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
            }
            if (!open) return;
            if (e.key === "Home" || e.key === "End") {
              e.preventDefault();
              return this.moveFilterHighlight(fl.key, e.key === "Home" ? 0 : n - 1);
            }
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              return this.setFilter(fl.key, fl.options[at][0]);
            }
          },
          caretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +
            (open ? "180deg" : "0deg") + ");",
          options: fl.options.map((o, i) => {
            const on = o[0] === cur;
            const hi = open && s.fMenuAt === i;
            return {
              label: o[1], selected: on,
              go: () => this.setFilter(fl.key, o[0]),
              optId: "f-opt-" + fl.key + "-" + i,
              rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +
                (on ? "800" : "500") + "; color: var(--vf-navy); background: " +
                (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",
              tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +
                (on ? "1" : "0") + ";"
            };
          })
        };
      }),
      filters: [
        { key: "type", options: [["Any", "Practice type: Any"], ["Small animal", "Small animal"], ["Mixed", "Mixed"], ["Large animal", "Large animal"], ["Emergency", "Emergency"], ["Specialty", "Specialty"]] },
        { key: "price", options: [["Any", "Asking price: Any"], ["u500", "Under $500K"], ["500-1000", "$500K – $1M"], ["1000-2000", "$1M – $2M"], ["o2000", "$2M and up"]] },
        { key: "revenue", options: [["Any", "Gross revenue: Any"], ["u1000", "Under $1M"], ["1000-2500", "$1M – $2.5M"], ["o2500", "$2.5M and up"]] },
        { key: "doctors", options: [["Any", "Doctors: Any"], ["1", "1 or more"], ["2", "2 or more"], ["4", "4 or more"]] },
        { key: "building", options: [["Any", "Property: Any"], ["Included", "Building included"], ["Separate", "Building available separately"], ["Leased", "Building leased"]] }
      ].map((fl) => {
        // Each toolbar filter is a dropdown list in this design's own style, not the operating
        // system's popup: the same trigger + role="listbox" panel A13 gave the metro control
        // beside it. One .map() body, five instances, one state slot.
        //
        // The comment sits INSIDE the map body, not between the array rows and `].map(`:
        // `tests/seeds/test_hospitals_json.py`'s `_BAR_BLOCK` reads the five option arrays
        // out of the design and requires `      ]` to follow the last row directly, and it
        // fails loudly rather than silently testing nothing when it does not.
        const cur = s.f[fl.key];
        const open = s.fMenu === fl.key;
        // Math.max: a value `f` holds that this option list does not would give indexOf -1 and
        // index the array out of bounds — the guard marketMenuKeys carries for a dropped metro.
        const sel = Math.max(0, fl.options.findIndex((o) => o[0] === cur));
        const at = open && s.fMenuAt >= 0 ? s.fMenuAt : sel;
        return {
          // The accessible name, taken from the design's OWN first option — all five read
          // "<name>: Any" — rather than authoring five new strings. A <select> with no <label>
          // is named by nothing, and a <label> cannot name a <button>, so the trigger needs one.
          aria: fl.options[0][1].split(":")[0],
          open,
          listId: "f-listbox-" + fl.key,
          // On the TRIGGER, which is always rendered: a shut dropdown has no active descendant,
          // and null is what both renderers omit the attribute for (a string would spell a dead
          // id). Keyed on fl.key as well, so a sibling never claims another's highlight.
          activeId: open ? "f-opt-" + fl.key + "-" + s.fMenuAt : null,
          // What the closed <select> displayed: the current option's own label.
          triggerLabel: fl.options[sel][1],
          toggle: () => (open ? this.setState({ fMenu: null, fMenuAt: -1 }) : this.openFilterMenu(fl.key, sel)),
          hostRef: (el) => { const m = this._fMenuEls || (this._fMenuEls = {}); m[fl.key] = el || null; },
          // The panel's own mount is when the option rows first exist, so it is where OPENING
          // scrolls the highlighted row into view — the arrow keys cannot, having seeded the
          // highlight while the panel was still unrendered. Same callback-ref idiom the compare
          // menu ships (md.compareMenuRef) and A13 reuses for marketPanelRef.
          panelRef: (el) => { if (el) this.scrollFilterOption(fl.key, this.state.fMenuAt); },
          keys: (e) => {
            const n = fl.options.length;
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              if (!open) return this.openFilterMenu(fl.key, sel);
              return this.moveFilterHighlight(fl.key, (at + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
            }
            if (!open) return;
            if (e.key === "Home" || e.key === "End") {
              e.preventDefault();
              return this.moveFilterHighlight(fl.key, e.key === "Home" ? 0 : n - 1);
            }
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              return this.setFilter(fl.key, fl.options[at][0]);
            }
          },
          // The <select>'s own box, byte for byte, plus the three declarations a label and a
          // chevron need where the user agent used to draw its own arrow (V3:382's own trio).
          style: "display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: " +
            (cur === "Any" ? "var(--color-white)" : "var(--rf-band)") + "; border: 1px solid " +
            (cur === "Any" ? "var(--border-subtle)" : "var(--color-blue)") + "; border-radius: 6px; cursor: pointer;",
          caretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +
            (open ? "180deg" : "0deg") + ");",
          options: fl.options.map((o, i) => {
            const on = o[0] === cur;
            const hi = open && s.fMenuAt === i;
            return {
              label: o[1], selected: on,
              go: () => this.setFilter(fl.key, o[0]),
              optId: "f-opt-" + fl.key + "-" + i,
              rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +
                (on ? "800" : "500") + "; color: var(--vf-navy); background: " +
                (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",
              tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +
                (on ? "1" : "0") + ";"
            };
          })
        };
      }),
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
      lightbox: this.lightboxVals(),
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
      startWizard: () => {
        if (!this.props.listings) return this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, wizErr: "" });
        if (s.creating) return null;
        this.setState({ creating: true });
        return this.props.listings.create()
          .then((id) => this.props.listings.get(id).then((d) => this.openDraft(id, d, "")))
          .catch((e) => this.openDraft(null, null, (e && e.message) || "A new listing could not be started."));
      },
      exitWizard: () => {
        if (!this.props.listings || !s.editingId) return this.setState({ sellerView: "dash", wizSubmitted: false });
        return this.props.listings.patch(s.editingId, s.step, s.w, true)
          .then(() => this.reloadListings())
          .then(() => this.setState({ sellerView: "dash", wizSubmitted: false, wizErr: "" }), (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }));
      },
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

export { Component, MARKETS, P, VETS, ECON_K };
