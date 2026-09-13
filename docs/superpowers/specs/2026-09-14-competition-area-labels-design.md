# Veterinary competition — the area, named on every surface it appears on

**Status:** design for John's approval (2026-09-14). Rulings **D-C55**, **D-C56**, **D-C57** and **D-C58**, made today on `.superpowers/sdd/2026-09-11-neighbourhood-shading/competition-radius-brainstorm.md`. Written against `main` at `bf730ef` (0.1.25 merged, not yet released to QA).

**What this spec covers:** approach A of the brainstorm, as ruled — every surface that shows a competition figure or its area says which area it is, in the D-C51 vocabulary, and the map itself names the ~5-mile ring for the first time. **What it does not cover:** approach B (a radius chooser), approach C (state premises registers), approach D (counting the marketplace's own listings) — see §11.

**Source of truth for every element below:** `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` plus the ruled amendments. Nothing here introduces a token, size, weight or colour the design does not already carry. Every change is a literal edit in `frontend/tests/design-amendments.ts` under one family id (§8), with one `LOCAL_AMENDMENTS.md` row per entry and an oracle for each ruled string (§9).

---

## 1. The ruling, and the question that produced it

The stakeholder's question, verbatim:

> "Under the demographic metrics, one of the options is veterinary competition, and it looks like it's the number of practices in a given area, but the area is not defined. Will that be a map function that will show how many practices are within a defined radius?"

John's rulings of 2026-09-14, as relayed:

| Ruling | What it says |
|---|---|
| **D-C55** | Forward §1 of the brainstorm as written — the answer to the stakeholder is "not today, and the number on the map is not a radius count at all", with both numbers explained. |
| **D-C56** | **D-C44 stands.** No ring toggle, no 5/10-mile chooser. Approach B is not built. |
| **D-C57** | The map itself names the ~5-mile ring, with **ONE legend row** in the Market data card while a practice is selected — plus approach A's label fixes: the "What this means" card names the ZIP area; the selected practice's competition figure is captioned as an area-apportioned estimate in the D-C51 vocabulary; the paid-employee universe and the withheld-ZIP floor are stated once. |
| **D-C58** | State premises registers are a **research spike with no screen** — not part of this spec beyond one sentence in §11. |

D-C51 is the vocabulary this obeys, in John's own words of 2026-09-13: *"WE MUST COMMUNICATE THE EXACT DESCRIPTION OF THE NUMBER SO USERS UNDERSTAND THE DIFFERENCES AND THEY ARE MEASURING DIFFERENT THINGS BECAUSE RIGHT NOW THEY ARE ALL LABELED THE SAME SO THE LOGIC WOULD BE THEY ARE SAME."* Every caption names **statistic · geography · basis**, and one fact is written once per surface that needs it.

## 2. The rules this change obeys

1. **Reference open first, port verbatim, absent beats faked.** Every new element is an element V3 already carries, in the declarations V3 gives it, in the place V3's own idiom would put it. No new state key, no new listener, no new render value except the one composed caption of §5.1. The single place where two existing declarations are combined rather than one element copied is the ring swatch, named as a deviation in §4 and put to John in §13.1.
2. **One fact, one string, per surface.** `metaSource`'s own rule (`frontend/src/logic.js:173-178`): a surface that already states a fact does not restate it, and a surface that states it nowhere gains it. This is why the panel's sub-line names the dataset and the strip card's does not — the strip card has a `src` line and the panel has none (§5).
3. **Same fact, same words, on every surface that carries it.** A34.7/A34.8's own rule: the three-kinds paragraph is byte-identical on the panel footnote and the strip footnote, "because the same three kinds of figure appear on both surfaces and two wordings of one fact is how they come to disagree." The two new competition sentences follow it (§6).
4. **A ruled string gets an oracle.** A copy change nothing photographs is the D-C40 / A26-F2 gap. One approved state is appended (§9).
5. **No new API field** unless the design cannot state the fact itself (§7).
6. **The frozen thirteen do not move.** None of them is a Browse capture (§9).

---

## 3. The six surfaces, current string → new string

Every current string below was read from the amended design (`Practice Match V3.dc.html`) and from `frontend/src/logic.js`, which is generated from it. Citations are `V3:<line>` against the amended file at `bf730ef`; they are re-taken by `npm run remap:citations` when the entries are inserted.

| # | Surface | Element | Today | After |
|---|---|---|---|---|
| S1 | Browse map **legend** (Market data card) | `md.active.geoLine`, `sourceLine`, `updatedLine` — V3:502–506 | "ZIP Code Tabulation Area" / "Source: U.S. Census ZIP Code Business Patterns (2022), NAICS 541940" / "Updated: ZIP Code Business Patterns 2022" | **unchanged**, plus ONE new ring key row (§4) |
| S2 | Map **hover tip** on one shaded ZCTA | `areaTip` — V3:2396–2397 | "Counted within this ZIP Code Tabulation Area. ZIP Code Business Patterns is published per ZIP code, which is this dataset’s own authoritative geography. Establishments include corporate-owned and specialty locations." | **unchanged** |
| S3 | "Market data layers" **drawer row** (desktop and phone sheet) | `LAYER_META.competition.sub` — V3:1950 | "Veterinary establishments by ZIP Code Tabulation Area · ZIP Code Business Patterns, NAICS 541940" | **unchanged** (A33.3 already gave it the grammar) |
| S4 | **"What this means"** card | `LAYER_META.competition.means` — V3:1953, rendered at V3:603 (desktop) and V3:1663 (phone sheet) | "Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services." | **new string** (§6.1) |
| S5 | **Market snapshot strip**, competition card | `stripCards[].valueNote` — V3:2862–2866; markup V3:910 | AREA: "median of 503 ZIP areas". LOCATION: "Within about 5 miles of the practice" (fallback "community level") | AREA **unchanged**. LOCATION: **"Within about 5 miles of the practice · estimated"** (§5.2) |
| S6 | Docked panel, **"Competitive Landscape"** block | heading V3:806, A34.6's sub-line V3:807–809, tiles V3:810–833, footnote V3:864 | sub-line = `md.panel.overviewScope`, i.e. "Within about 5 miles of the practice" and nothing about the basis; the tiles read "{{ compEstab }} / Veterinary Establishments", "{{ compPer10k }} / per 10k households", "{{ compLevel }}" | sub-line becomes **"Within about 5 miles of the practice · estimated from ZIP Code Business Patterns 2022"** (§5.1); tiles unchanged; footnote gains the two sentences of §6.2 |

**Two further places the word appears and why neither moves.** `VALUE_LAYERS.competition.label` — "Veterinary Establishments (ZBP)" (V3:1863) — is rendered **nowhere**: A34.11 deleted `md.legend` and A34.12 deleted `active.sub`, and A34.23 corrected this literal for the reader of the source rather than for a screen. And the layer-menu option is the bare title "Veterinary competition" (`LAYER_META.competition.title`, V3:1949) — left alone deliberately, as the brainstorm recommended: it is the title element for all six layers, the legend directly beneath it names the geography, and a six-row change for one layer's complaint is not surgical.

**S2's "Counted within this…" sentence is not widened.** Its subject is the polygon under the cursor, and the paid-employee universe is a property of the dataset, not of that polygon; stating it in the tip would be the second wording of a fact §6.1 states once, on the card whose whole purpose is that prose. The tip already carries the OTHER exclusion ("corporate-owned and specialty locations") and, for a withheld polygon, `THRESHOLD_RULE` — both pinned across the API and the design by `tests/census/test_design_shading_labels.py`.

---

## 4. The new legend row — the map names its ring

**The gap, exactly.** `MarketMapV3.jsx:214` draws `radius: 8000, color: "#003a70", weight: 1.5, dashArray: "4 4", fill: false, interactive: false` around the selected practice. It has no tooltip, no label and no legend row, so the map has never said what it is or how wide it is. That is the one surface the stakeholder's "the area is not defined" lands on squarely.

**Composed from.** The Market data card's **own compare-key row**, V3:561–563:

```html
<div style="display: flex; gap: 12px; margin-top: 9px; font-size: 10px; color: var(--vf-text);">
  <span style="display: inline-flex; align-items: center; gap: 5px;"><span style="{{ md.compareKeyA }}"></span>{{ md.compareLabelA }}</span>
  <span style="display: inline-flex; align-items: center; gap: 5px;"><span style="{{ md.compareKeyB }}"></span>{{ md.compareLabelB }}</span>
</div>
```

with `compareKeyA`'s own swatch declarations (`frontend/src/logic.js:912`):

```
flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); background: linear-gradient(to right, …);
```

**The row, as it will read:**

```html
<sc-if value="{{ md.showDrive }}" hint-placeholder-val="{{ false }}">
  <div style="display: flex; gap: 12px; margin-top: 11px; font-size: 10px; color: var(--vf-text);">
    <span style="display: inline-flex; align-items: center; gap: 5px;"><span style="flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px dashed var(--vf-navy);"></span>About 5 miles around the selected practice</span>
  </div>
</sc-if>
```

Inserted **after** the `md.active.hasGeo` block's own closing `</sc-if>` (V3:504) and **before** the source line (V3:505), so the card reads: classes → geography → ring → provenance. `margin-top` is **11 px**, the legend's own rhythm (V3:503, V3:505), not the compare key's 9 px: both values exist in this card and the row sits among the legend's lines, not among Compare's.

**The gate is `md.showDrive` — the same term the map itself takes.** V3:460 hands the map `show-drive="{{ md.showDrive }}"`, and `md.showDrive` (V3:2731) is

```js
showDrive: !!(sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng)),
```

which is A25.6's "no point, no ring" term verbatim. So the row is drawn **exactly when the ring is drawn, by construction** — it cannot claim a ring the map did not paint, and it needs no new state key, no new render value and no new gate. Closing the panel sets `mdSel: null` (`closePanel`, `frontend/src/logic.js:1054`) and a metro change sets `mdSel: null` (A30), so in both directions `sel` goes null, `showDrive` goes false, the ring goes and the row goes with it.

**The swatch: a decision John should confirm.** There is **no dashed-line glyph anywhere in the design** — no legend swatch, no key, no icon. What does exist is (a) the compare key's 26 × 9 box with a **1 px solid** border, quoted above, and (b) the design's own `1px dashed var(--border-subtle)` border on three empty-state boxes (V3:855, V3:1050, V3:1345). The row above takes (a)'s box and (b)'s dashed border treatment, in the ring's own colour — `#003a70` **is** `--vf-navy` (V3:29), so the swatch names no colour the design does not already own, and an unfilled dashed outline is what the ring actually is.

The alternative, which the brief named: a **filled square in the ring colour**. It is rejected here because a solid `--vf-navy` block in a legend whose other swatches are choropleth classes reads as a sixth class in a colour no ramp carries. **Recorded as the one composition deviation for John:** the dashed swatch is composed from two existing declarations rather than copied from one existing glyph, because no glyph exists. If he prefers the filled square, it is a one-value change to this entry and nothing else in the spec moves.

**The phone frame gets no row, and that is measured, not a scope cut.** V3:1524 passes the phone map `show-drive="{{ md.showDrive }}"` — the same binding — but **no phone control ever writes `mdSel`**: `mob.selectMarker` (V3:3252–3254) writes `activeId` and, on a second tap, opens the detail. `sel` is `P.filter((x) => x.id === s.mdSel)[0]`, so `showDrive` is false on every phone path and the ring is never drawn there. A row added to the phone sheet's legend (V3:1591–1595) would be markup that can never render — dead code under the bundle's own rule (A2.3, A28.5–A28.9). If the phone frame ever gains a docked selection, the row follows it in the same edit.

**"About 5 miles around the selected practice" — and why it is not `BAND_LABEL`'s sentence.** The served `BAND_LABEL` is "Within about 5 miles of the practice" (`app/census/serve.py:197`), and that is what captions a **figure**. This row captions a **glyph** on a map carrying many pins, so it names the distance and says which practice the circle belongs to. It is not a new vocabulary: the panel footnote has said "a straight-line area of about 5 miles around the practice" since A21.4d/A27.4 (V3:864). The two are kept in step by a pin, not by hope — §10 adds a case to `tests/census/test_band_distance.py`, the module that already holds `BANDS["drive_10"]`, `BAND_LABEL`, `MarketMapView.vue`'s ring and `MarketMapV3.jsx`'s ring to one number.

**No "· straight-line" suffix.** The brainstorm proposed "About 5 miles around the selected practice · straight-line". It is dropped: the ring is only drawn while a practice is selected, which is the same condition that opens the docked panel, whose footnote states the straight-line basis in the design's own words. The one gap is the panel's other tabs and its `noDemo` branch, where the footnote is not rendered — recorded here, not papered over, and not worth a second wording of one fact.

**Width, measured.** The card is `width: 300px` with `padding: 13px 15px 14px` (V3:467) → 270 px of content. Swatch 26 px + gap 5 px = 31 px; the label is 41 characters at 10 px ≈ 197 px. 228 px of 270 px: **one line**, with room.

---

## 5. The captions for the selected practice's figure, measured

The brief's target caption is *"N veterinary establishments · about 5 miles around the practice · estimated from ZIP Code Business Patterns 2022"* — statistic · geography · basis. Neither surface prints it as one string, because on both surfaces the statistic is already an element and on one the basis is already a line. Splitting it is rule 2, not a compromise.

### 5.1 The docked panel — "Competitive Landscape"

**Where the caption cannot go.** The panel is `width: 366px` (V3:729) with `padding: 16px` (V3:790) → 334 px of content. The Competitive Landscape grid is `1fr 1fr 1fr` with `gap: 6px` (V3:810) → each tile is **107.3 px**; tile padding is 10 px each side (V3:811) and the first two tiles carry a 15 px icon with an 8 px gap, so the text column is **≈ 64 px**. At the tile sub-line's 9.5 px that is about twelve characters. A caption cannot be a tile sub-line here, and nothing in this spec tries to make it one.

**Where it goes.** A34.6's own sub-line under the heading (V3:807–809), which is the block's established scope line and runs the full 334 px. It reads `md.panel.overviewScope` today — the same binding as the Market Overview sub-line at V3:794 — and becomes `md.panel.compScope`:

> **`Within about 5 miles of the practice · estimated from ZIP Code Business Patterns 2022`**

composed as `sel.communityLabel + " · estimated from ZIP Code Business Patterns 2022"`, behind A34.6's own `hasOverviewScope` gate (`!!sel.communityLabel`, V3:3091) unchanged. 83 characters at 12.5 px in 334 px → two lines. The tile beneath supplies the statistic ("Veterinary Establishments", V3:815) and the value; the sub-line supplies geography and basis. The panel names the **dataset** because the panel has no source line of any kind — `metaSource`'s own rule applied one surface over.

**Why the gate is not widened.** `hasOverviewScope` is false wherever the API served no `community_label` — the design's own fixtures (so the reference and every approved state keep their pixels) and, on QA, the one place-band listing of twenty-nine. That listing keeps today's behaviour: a figure with no scope line. Widening the gate to adapter presence (A16.1/A33.1c's idiom) would print the basis with no geography and is the alternative if John wants the basis stated unconditionally; it is **not** recommended, because it would re-base `browse-market-panel` for a case one listing hits, and because A27.6/D-C42 already settled that this card states its geography where it has one and says nothing where it does not.

### 5.2 The snapshot strip — the LOCATION card

The strip card is `minmax(232px, 1fr)` (V3:904) with `padding: 13px 14px` → **204 px** of content at the card's minimum. The caption is the `{{ c.valueNote }}` span (V3:910), on the value's baseline row with `gap: 7px`, at 10.5 px; beside a two-digit value it has ≈ 170 px, about 34 characters a line. Today's "Within about 5 miles of the practice" (35 characters) is already two lines.

The card **already** carries the dataset, on its own `src` line (V3:917): "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940". So the caption gains one word and nothing else:

> **`Within about 5 miles of the practice · estimated`**

47 characters → still two lines at 34 characters a line, so the card's height should not move; the pixel diff is the proof, not this paragraph. This is A27.1/A33.1b's own shape — income's caption reads "… · approximate" beside a median that is derived the same way — and the qualifier is a single word for the same reason: "apportioned by area" is the method, and the method is stated once, in prose (§6.2).

**The fallback reads "community level · estimated".** `locBasis` is `sel.communityLabel || "community level"` (V3:2819), so a place-band listing — and every design fixture, and therefore the approved state — takes the design's fallback word with the new qualifier appended. That fallback word is a known open item (brainstorm §3-A item A7: "the surrounding city or town", or leave) and is **out of scope here**: this spec does not rule on it, and changing it would move a string this spec is not about.

---

## 6. Said once: the paid-employee universe and the withheld-ZIP floor

Two facts are stated nowhere in the product today. They are split by what they are properties **of**, which is what decides where each is said once.

### 6.1 The paid-employee universe → the "What this means" card

It is a property of the **dataset**, and the card is the layer's prose. `LAYER_META.competition.means` (V3:1953) also names no area at all, which is D-C57's other label fix, so one string carries both corrections:

**Today**

> Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.

**After**

> **Establishment counts show how many veterinary businesses operate in each ZIP Code Tabulation Area. The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure. They say nothing about size, quality or overlap in services.**

The card is 360 px wide with `padding: 16px 18px 14px` (V3:592) → 324 px, at 13.5 px / line-height 1.5: roughly three lines becoming six, about 60 px taller. The card is `position: absolute; left: 16px; bottom: 22px; z-index: 590` and grows upward, beneath the Market data card's `z-index: 600` container — so a taller card cannot cover the legend — it passes **under** it if the two ever meet, which the appended state's capture is where to check, the legend container running `top: 16px; bottom: 72px` in the same 16 px column. The growth is only ever visible while **competition** is the active layer (`insightOpen` renders `md.active.means` for the layer in force, `frontend/src/logic.js:974-978`). §9 appends the approved state that photographs it.

The geography phrase in this string is pinned against `app.api.market.SHADING["competition"]["label"]`, which is the A33.3 mechanism, so a layer that moves geography again fails on both sides at once.

### 6.2 The withheld-ZIP floor and the apportionment → both footnotes, byte for byte

These are properties of the **practice's own figure**, which appears on two surfaces — the docked panel and the strip's LOCATION card — and on neither is the "What this means" card guaranteed to be open (it is dismissible, it needs competition to be the active layer, and it needs a map at least 810 px wide). So the sentences go where the figure is, in the same words on both, which is A34.7/A34.8's own rule for exactly this situation:

> **A practice’s competition figure apportions each ZIP area’s published count to the part of that ZIP within about 5 miles of the practice. A ZIP whose count the Census withheld adds nothing to it, so the figure is a floor rather than an exact count.**

(Curly apostrophes, U+2019, as the design's prose uses throughout.)

Appended at the **end** of each paragraph, so every existing sentence is carried forward byte for byte — including A24.20's growth caveat and A27.4's straight-line sentence, which is the fix-round-3 lesson AMEND-GUARD exists to enforce:

- the docked panel's footnote, V3:864 (ends "… payroll is the county’s.");
- the snapshot strip's footnote, V3:922 (ends "… not the tract.").

They also correct, for competition, the generalisation the strip footnote makes: "A practice’s figure is derived from the tracts within about 5 miles of it" is true of four layers and not of this one, whose units are ZIP areas.

**"Said once" means one wording, not one location.** That is A34.8's own recorded holding, and it is the reading applied here.

---

## 7. The API side — no new field

**Recommendation: no new payload field, and no new route.**

- **The ring radius** is already one number in four places, held together by `tests/census/test_band_distance.py`: `app/census/catchment.BANDS["drive_10"] = 8000`, `app/census/serve.BAND_LABEL`, `frontend/src/components/MarketMapView.vue`'s ring and `MarketMapV3.jsx`'s ring. The design states "about 5 miles" from that authority and the new legend row joins the same pin (§10). Nothing needs serving.
- **The apportionment method** is a constant of the pipeline (`euclidean_buffer_v1`, `materialize._competition`), not a per-listing fact, so a served `competition_note` would carry the same sentence for every listing in the country. The design states it, in the footnotes, once. This is the opposite call from `income_note` (A27.1), and deliberately: that one varies per listing, because the median's own band varies.
- **The paid-employee universe** is likewise constant. It is added to the API's **existing** competition caveat rather than as a new field, so an integrator reading `/api/layers` and a buyer reading the card get one wording:

  ```python
  # app/api/market.py, beside THRESHOLD_RULE
  EMPLOYER_UNIVERSE = (
      "The Census counts business locations with paid employees, so a practice with "
      "no paid staff is not in this figure."
  )
  ```

  appended to `LAYERS[competition]["caveat"]` (today: `app/api/market.py:321`) and pinned into the design exactly once, in `THRESHOLD_RULE`'s own shape (§10). It is a substring of §6.1's `means`, so the design states it once and both sides read one sentence.

`docs/integrations/market-data-api.md` gains the new caveat text; `tests/api/test_contract_doc.py` keeps it honest against the router.

---

## 8. The amendment family: **A48**

### 8.1 Why A48

Read on `main` at `bf730ef` and on every in-flight branch:

| Id | State |
|---|---|
| A1–A35 | on `main` (A20 reserved by the image-identifiability plan, A29 used on `feat/sort-control`) |
| **A36** | `feat/admin-users`, in flight |
| **A37** | reserved, unwritten — the admin Requests tab (named in `LOCAL_AMENDMENTS.md`'s A40.3 row and in CLAUDE.md) |
| **A38** | `feat/admin-data-sources`, in flight |
| **A39** | `feat/admin-listings`, in flight |
| **A40** | shipped in 0.1.23; **A40.1/A40.2 reserved and unwritten**, ids may not be reused |
| **A41–A47** | reserved by `docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §9 — Settings + re-auth (A41), licence decision (A42), Requests build (A43), user detail (A44), listing detail (A45), permissions matrix (A46), seller application (A47) |
| **A48** | **free — this family** |

`feat/snap-metro` carries **A31.14**, which is a reserved sub-id inside an existing family and takes no family number of its own; its branch is still at `bf730ef` (nothing written). Ids are reserved across unmerged branches and across approved specs, which is why A41–A47 are not available even though no code carries them yet: the admin spec is John's to approve and re-using its numbers would collide the moment it is.

### 8.2 The entries

Seven literal edits. Every `find`/`replace` is stated as intent here; the implementer writes the bytes.

| Entry | File / site | What it does | Chaining |
|---|---|---|---|
| **A48.1** | script, `LAYER_META.competition.means` — V3:1953 | Replaces the `means` string with §6.1's. The line is **pristine** (`Practice Match V3.rev2.dc.html:1716`), so nothing is consumed. | — |
| **A48.2** | template, the Market data card's legend — insert between V3:504 and V3:505 | Adds the ring key row of §4, gated on `md.showDrive`. `find` is the two-line pair (`hasGeo`'s closing `</sc-if>` + the `sourceLine` div) so the anchor is unambiguous; `replace` re-emits both with the row between them. | — (both lines carried forward byte for byte) |
| **A48.3** | script, `marketPanel` — beside `overviewScope` at V3:3092 | Adds `compScope: sel.communityLabel ? sel.communityLabel + " · estimated from ZIP Code Business Patterns 2022" : ""`. `hasOverviewScope` (V3:3091) is reused unchanged as the gate. | — |
| **A48.4** | template, the Competitive Landscape sub-line — V3:806–809 | Re-binds that one sub-line from `{{ md.panel.overviewScope }}` to `{{ md.panel.compScope }}`. The `find` **must** span the "Competitive Landscape" heading, because V3:794 and V3:808 are byte-identical lines and a one-line `find` would be ambiguous — A34.6's own anchor, for the same reason. | **Consumes A34.6** |
| **A48.5** | template, the docked panel's footnote — V3:864 | Appends §6.2's two sentences to the paragraph; every existing sentence carried forward byte for byte. | **Consumes A34.7** |
| **A48.6** | template, the snapshot strip's footnote — V3:922 | Appends the same two sentences, byte for byte. | **Consumes A34.8** |
| **A48.7** | script, `stripCards[].valueNote` — V3:2865 | Inserts a `k === "competition" ? locBasis + " · estimated"` arm before the `income` arm; the `find` is A34.16's own introduced line, re-emitted unchanged after the new arm. | **Consumes A34.16** |

**No entry for the "Veterinary Establishments" tile label, the layer-menu option, the map tip or the drawer row** — §3 records why each is left as it is. **No entry in `MarketMapV3.jsx`:** the ring's own declarations do not change (D-C44/A28 stands; D-C56 confirms it), only the card that now names it.

**A48.2, A48.5 and A48.6 add lines to the bundle**, so every `V3:<line>` citation below them in `LOCAL_AMENDMENTS.md` is re-mapped in the same commit with `npm run remap:citations` (Task HOUSEKEEPING-C). Citations in this spec are pre-insertion line numbers.

### 8.3 The `LOCAL_AMENDMENTS.md` rows

One row per entry, in the ledger's four columns (`Id | Date | John's ruling | What changes`), with John's ruling quoted as D-C57 in his relayed words and the consumption token spelled out on the row of the entry whose `find` takes the text. Sketch of the two that carry the most:

> **A48.2** | 2026-09-14 | D-C57 (John, 2026-09-14): the map itself names the ~5-mile ring, with one legend row in the Market data card while a practice is selected. | One template insertion — the Market data card's legend gains a key row between its geography line (V3:503) and its source line (V3:505), composed from the card's OWN compare-key row (V3:561–563) and `compareKeyA`'s 26 × 9 swatch box, with the box's `1px solid rgba(0,58,112,.14)` border becoming `1px dashed var(--vf-navy)` — the ring's own colour (`--vf-navy` is `#003a70`, V3:29) and the design's own dashed-border treatment (V3:855, V3:1050, V3:1345); there is no dashed glyph in the design to copy, which is recorded as the family's one composition deviation. The gate is `md.showDrive` (V3:2731) — the SAME value V3:460 hands the map as `show-drive`, i.e. A25.6's "no point, no ring" term — so the row is drawn exactly when the ring is drawn and cannot claim one the map did not paint; `closePanel` and A30's `mdSel: null` both take it away with the ring. No new state key, no new render value, no new listener. Root cause: `MarketMapV3.jsx:214` draws the ring `interactive: false` with no tooltip and no legend row, so the map had never named the area a buyer was being shown. The phone sheet's legend gets no row: V3:1524 passes the same binding, but `mob.selectMarker` (V3:3252) writes `activeId` and never `mdSel`, so `showDrive` is false on every phone path and the markup could never render — dead code under the bundle's own rule. Re-bases `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip-location`; none of the thirteen frozen hashes is a Browse capture.

> **A48.5** | 2026-09-14 | D-C57 (John, 2026-09-14): the paid-employee universe and the withheld-ZIP floor are stated once. | One template literal — the docked panel's footnote (V3:864), **Consumes A34.7**. TWO sentences APPENDED and no rewrite: the practice's competition figure is an area-apportioned estimate, and a ZIP the Census withheld adds nothing to it, so it is a floor. Every existing sentence is carried forward byte for byte, A24.20's growth caveat and A27.4's straight-line sentence included — the fix-round-3 lesson AMEND-GUARD exists for. The same two sentences appear on the strip footnote (A48.6) byte for byte, which is A34.7/A34.8's own rule: the same figure appears on both surfaces and two wordings of one fact is how they come to disagree. Re-bases `browse-market-panel` and `browse-panel-lightbox`.

---

## 9. The oracle plan

**Re-bases, by entry.** Measured the A33 way — baselines regenerated from the pre-change design and from this one, PNG hashes diffed — not reasoned:

| Entry | Approved states expected to move | Why |
|---|---|---|
| A48.1 (`means`) | **none of the 55 today** — see the appended state below | The card renders the ACTIVE layer's prose, and no approved state has competition active |
| A48.2 (ring row) | `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip-location` | the only three states with a selection; all three render the Market data card, and the lightbox scrim is `rgba(0,58,112,.55)` so the card shows through it (A28's own note) |
| A48.3 / A48.4 (panel sub-line) | **none** | gated on `hasOverviewScope`, and no design fixture carries a `communityLabel` |
| A48.5 (panel footnote) | `browse-market-panel`, `browse-panel-lightbox` | already moving |
| A48.6 (strip footnote) | `browse-market-strip`, `browse-market-strip-location` | **`browse-market-strip` is a re-base the brief did not name** — it exists to photograph this footnote (D-C40) and scrolls to it |
| A48.7 (strip caption) | `browse-market-strip-location` | already moving |

**Four approved states re-base — `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip`, `browse-market-strip-location` — and one is appended.** `browse` does not move (no selection, competition not active, no footnote in frame); neither do `browse-layer-menu`, `browse-compare-open`, `browse-legend-collapsed`, `browse-layers-open`, `browse-layer-households`, `browse-metro-menu`, `browse-filter-menu`, `browse-more-filters`, `browse-more-filters-menu`, `header-1100`, `header-1000`, `mobile-map` or `mobile-sheet`.

**One approved state is appended.** A48.1 is a ruled copy change that nothing photographs — the D-C40 / A26-F2 gap — so `screens.ts` gains:

```
browse-insight-competition — browse(p); open the "Active market layer" listbox; choose
"Veterinary competition"; wait for the "What this means" card's own new sentence; settle.
```

in `browse-layer-households`'s own shape (`frontend/tests/screens.ts:493–501`), which is the existing precedent for a state that selects a layer. Appending a Browse state moves no frozen hash, as `screens.ts:489` already records.

**The frozen thirteen do not move, and the proof is that none of them is a Browse capture.** `frontend/tests/baseline-manifest.json` holds `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`. Every entry in §8.2 edits the Browse screen's Market data card, docked panel or snapshot strip, or a `LAYER_META` string only those surfaces read. The manifest is checked after the re-base, not assumed — A18's own discipline.

**`STRIP_FOOTNOTE` in `screens.ts` is a waiter for the strip footnote's text** and is updated in the same commit as A48.6, or `browse-market-strip` hangs rather than fails.

---

## 10. Tests

**Unit — `frontend/src/logic.test.ts`, one characterisation case per entry** (the house rule: prove a gate can fail by perturbing what it guards):

1. `LAYER_META.competition.means` is §6.1's string exactly, and names `AREA_LABEL.competition`.
2. `md.showDrive` is true with a selected fixture carrying a finite point and false with `mdSel: null`, with a non-finite point, and after `closePanel` — the row's gate, characterised at the value the markup binds (the row's presence itself is the DOM oracle's and the smoke's job).
3. `marketPanel(...).compScope` is `"<label> · estimated from ZIP Code Business Patterns 2022"` with a `communityLabel`, `""` without; `hasOverviewScope` is unchanged in both.
4. `stripCards` competition `valueNote` is `"Within about 5 miles of the practice · estimated"` with a label, `"community level · estimated"` without, and unchanged in AREA mode; the other five layers' captions are byte-identical to today (the copy-paste catch A33.3's own test taught).
**Design-text — beside `frontend/tests/design-amendments.test.ts`** (the footnotes are template literals, not `logic.js`, so this is asserted against the amended design file rather than in `logic.test.ts`):

5. §6.2's two sentences occur **exactly twice** in the amended design — once in the docked panel's footnote, once in the strip's — and the two occurrences are byte-identical to each other.

**pytest:**

6. `tests/census/test_design_shading_labels.py` — a new case in `test_every_layer_row_names_the_geography_that_layer_shades`'s own shape: `LAYER_META.competition.means` names `SHADING["competition"]["label"]` and no other layer's geography.
7. `tests/census/test_design_shading_labels.py` — `EMPLOYER_UNIVERSE` appears in the design exactly once and is in the served competition caveat, in `test_the_census_threshold_rule_is_one_sentence_read_by_both_the_api_and_the_design`'s own shape.
8. `tests/census/test_band_distance.py` — a fifth derivation of the one radius: the design's ring legend row reads `f"About {_miles()} miles around the selected practice"`, so changing `BANDS["drive_10"]` fails here instead of leaving the map naming a distance it does not draw.
9. `tests/api/test_contract_doc.py` — `docs/integrations/market-data-api.md` carries the widened caveat.

**Design and ledger gates (all existing, all must stay green):** `frontend/tests/design-amendments.test.ts` (pristine + amendments == the amended file, byte for byte), `frontend/tests/amend-guard.ts` (the four `Consumes` tokens of §8.2, on the consuming rows), the citation pins, `npm run remap:citations`, `frontend/tests/app-generated.test.ts`, `bundle-budget.test.ts`.

**Visual and DOM:** `npm run test:visual:baselines` then `npm run test:e2e`; the four re-bases of §9 recorded with their measured hashes, the appended state's baseline generated, `baseline-manifest.json` proved unmoved.

**Smoke — `frontend/tests/smoke.spec.ts`, real Chromium against the live API:** select a practice with a point → the ring key row is visible with its text; close the panel → it is gone; select again and switch metro → it is gone (A30's path); select a listing served with no coordinates → neither the ring nor the row is drawn (A25.6's path, which the row now shares by construction).

---

## 11. Out of scope

- **Approach B — a member-chosen radius (5 / 10 miles).** Ruled out by **D-C56**: D-C44 stands, no ring toggle and no chooser. The `drive_20` rows stay materialised and served by nothing, and `tests/census/test_band_distance.py`'s note that they are "drawn by nothing and named by nothing" stays true.
- **Approach C — state premises registers.** **D-C58**: a research spike with no screen and no ingestion until the VIN Foundation clears a registry row. Nothing in this spec depends on it.
- **Approach D — counting the marketplace's own listings within a radius.** Not pursued and never labelled competition: 29 listings against thousands of establishments, and D8/C4 makes a circle around an anonymised listing's place centroid either a leak or a count of the wrong place.
- **The `"community level"` fallback word** (brainstorm §3-A item A7). This spec appends a qualifier to it and does not rule on it.
- **The Low / Moderate / High thresholds** (1.4 and 2.2 per 10 000 households, `frontend/src/logic.js:1288`), stated nowhere a member can read them. Named in the brainstorm as item A5 and not in D-C57's list; a one-sentence footnote change whenever John wants it.
- **The layer-menu option's bare title** — §3 records why it stays.
- **Any change to `MarketMapV3.jsx`,** the ring's radius, colour, dash or interactivity.

---

## 12. Order

1. **Release 0.1.25 to QA and production first.** A34.6 — the Competitive Landscape block's own scope sub-line, which "takes the Market Overview heading's own sub-line, element for element" so that block's three figures stop standing under no scope line at all — is merged on `main` at `bf730ef` and has never reached QA. A48.3/A48.4 edit that exact sub-line, so it must be live and seen before it is widened.
2. **Sequence against the branches that touch the same files.** `feat/admin-users` (A36), `feat/admin-data-sources` (A38) and `feat/admin-listings` (A39) all append to `design-amendments.ts` and `LOCAL_AMENDMENTS.md`; merge `main` into the A48 branch before its final push and merge the ledger branches one at a time (the standing rule).
3. **Sequence against A31.14.** `feat/snap-metro` is reserved for it and is still empty at `bf730ef`, but A34.7's own row records that when SNAP-METRO lands "the metro sentence changes" in **both** footnotes — the same two paragraphs A48.5 and A48.6 append to. Whichever lands second re-anchors its `find` against the other's output and declares the consumption. Recommendation: **A48 first**, because it is a copy-only change with no route behind it, and A31.14 is not written.
4. Then the A48 branch: entries, tests, measured re-bases, review, QA click-through on the changed flow (select a practice on Browse; open the layer menu and choose Veterinary competition; open the snapshot strip in both modes), full verification gate, deploy.

---

## 13. What John should confirm

1. **The ring swatch.** A dashed 26 × 9 outline in `--vf-navy`, composed from the compare key's box and the design's own dashed-border treatment — because **no dashed glyph exists in the design to copy**. The alternative is a filled square in the ring's colour, which reads as a sixth choropleth class. **Recommended: the dashed outline.** (§4)
2. **The row's words: "About 5 miles around the selected practice"**, which is the panel footnote's own phrasing plus "selected", rather than the served `BAND_LABEL` sentence "Within about 5 miles of the practice". A key names a glyph; a caption names a figure. The distance is pinned across both. **Recommended: as written.** (§4)
3. **Two qualifiers, not one.** The strip card says "· estimated" (its `src` line already names the dataset) and the panel sub-line says "· estimated from ZIP Code Business Patterns 2022" (the panel has no source line at all). That is one fact composed per surface, `metaSource`'s own rule — but it does mean the two surfaces read differently. **Recommended: as written.** (§5)
4. **Where the two "said once" facts live.** The paid-employee universe on the "What this means" card only; the apportionment and the withheld-ZIP floor on **both** footnotes, byte for byte. The brief suggested the card, with the footnote "if the card is not shown" — and the card is never guaranteed to be on screen beside the ring figure (it is dismissible, it needs competition active, and it needs a map ≥ 810 px wide), so the ring facts are put where the ring figure is. **Recommended: as written.** (§6)
5. **`browse-market-strip` re-bases too.** The brief named three states; the strip footnote makes it four, plus the appended `browse-insight-competition`. None of the thirteen frozen hashes moves. **Noted, not a question — but it is one more approved baseline than the brief expected.** (§9)
6. **The panel sub-line stays gated on a served `community_label`,** so the one QA listing served from the place band keeps a competition figure with no scope line. Widening it to adapter presence would state the basis for every listing and re-base `browse-market-panel` for that one case. **Recommended: keep the gate.** (§5.1)
