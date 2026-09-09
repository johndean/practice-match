# Photo Lightbox and Arrow Reversal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two rulings from John, 2026-09-09, on the approved V3 design as it renders on qa.foundation.vin. (1) The two `navigate-arrow.svg` glyphs that point the wrong way — after "View full listing" on the Browse docked panel's Insights tab, and before "Back to results" on the listing detail — are reversed. (2) Every photograph a member can see — the detail's photo tiles, the tiles A15 appends beyond the sixth, and the Browse docked panel's current photograph — becomes clickable and opens an enlarged view with `<` and `>` to page through every photograph of that listing and a simple X to close.

**Architecture:** Two new ruled amendment families on `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, applied through the D15 engine and never by hand. **A18** is two literal template edits (a `transform: rotate(180deg)` added at V3:819 and removed at V3:895 — the design's own flip idiom, V3:724). **A19** is twelve literal edits — seven in the `<script data-dc-script>` block and three in the template, plus the two literals that clear the lightbox on the design's own screen changes — composing the lightbox from the design's own elements: the interest modal's scrim (V3:1048) at a z-index above Leaflet's, the docked panel's 34 px `nav-arrow-white.svg` prev/next pair (V3:720–725) verbatim, its 38 px close button (V3:707–709) with `close-x-gray.svg` whitened, and its counter and caption pills (V3:729–731) verbatim. One app-side TypeScript edit (`frontend/src/router/useStateRouteSync.ts`) closes the lightbox on a route-driven screen change, because the reference has no router. `npm run gen:design` regenerates the design, the python snippet re-ports `logic.js`, `npm run gen:app` regenerates `App.vue`/`pseudo.css`; the oracles regenerate from the amended design in the same run. **A18 lands first and alone**, so that `frontend/tests/baseline-manifest.json`'s `detail` hash moves exactly once, by ruled design change, with the other twelve rows unchanged as the proof the change reached nothing else; **A19 lands second with the manifest test GREEN and zero moves**, which is the proof the closed lightbox changed no approved pixel. Three approved states are appended (45 → 48).

**Tech Stack:** the design bundle's own dc runtime (React 18 + `support.js`) on the reference side · Vue 3 + `frontend/scripts/convert-dc.mjs` on the app side · Vitest 3 (`frontend/src/logic.test.ts`, `frontend/tests/design-amendments.test.ts`, `frontend/src/router/useStateRouteSync.test.ts`) · Playwright (`visual.spec.ts`, `dom.spec.ts`, the `reference` project) · pytest (`tests/test_docs.py` count pins). No new dependency, no new icon or asset, no new prototype prop.

**Branch:** worktree `.worktrees/feat-photo-lightbox` on branch `feat/photo-lightbox`, cut from `main` (HEAD `7a85245`, 0.1.9) **after this plan is committed**. Nothing here touches the backend beyond `tests/test_docs.py`. Implementers never push, deploy or run `railway`; the controller does those at hand-back.

---

## The rulings

John, 2026-09-09, verbatim. Each string is the `ruling` field on every entry of its family and the ruling column of every `LOCAL_AMENDMENTS.md` row of that family, byte for byte.

**(1) A18** — with two screenshots: the docked panel's "View full listing" button and the detail's "Back to results" link:

```
the arrow icons are backwards on each location, reverse each
```

**(2) A19:**

```
the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close
```

**Controller rulings on the proposals (2026-09-09, the understand workflow `wf_cff4a740-150`), which govern wherever a proposal differed:**

- Family ids on `main`: **A18** = the two arrow reversals; **A19** = the lightbox. **A16/A17 are reserved** by `feat/seller-lifecycle` (`2026-09-08-seller-listing-lifecycle.md`, Tasks SL7/SL8) and are not used here. `tests/test_docs.py`'s `number_words` is extended through "Twenty".
- A18 scope: V3:819 (add `rotate(180deg)`) and V3:895 (remove it) — John's two. V3:140 (the account menu's Sign out row) and V3:1434 (the phone frame's sign-out pill) are **questions for John (D-A18), not changes**: flipping V3:1434 would move the two frozen mobile rows.
- Sequencing: A18 lands alone first (`gen:design` → baselines → manifest test shows exactly `detail` → re-pin + header paragraph → commit); A19 lands second with the manifest test GREEN (zero moves).
- A19 surfaces: the detail grid's filled tiles (A15's extra tiles included) and the Browse docked panel's current photograph. **Not** the results-rail thumbnails (a card click is the selection). No mobile surface exists — the 390×800 frame renders static bands (V3:1456 "Photo", V3:1636 "Exterior photo") and no `<image-slot>`.
- A19 composition: the interest modal's scrim string at **`z-index: 1100`** (above Leaflet's `.leaflet-top`/`.leaflet-bottom` at 1000 — the Esri attribution and controls sit in the root stacking context on Browse; a dialog covers the page while open and the attribution returns on close); the panel's 34 px `nav-arrow-white` prev/next verbatim, hidden when there is one photograph; the panel's 38 px close button with `close-x-gray` whitened, `aria-label="Close photo"`; the panel's caption pill (the photograph's own A15 description, "Photo N" fallback) and counter pill "N/M" at 12 px; natural size, never upscaled, bounded to the viewport minus 24 px; wrap-around; backdrop click (`target === currentTarget`) closes; every `sc-if` carries `hint-placeholder-val="{{ false }}"`; `role="dialog" aria-modal="true" aria-label="Photograph N of M" tabindex="-1"` with `outline: none`; focus into the dialog through the mount-ref idiom (never a `setState` callback), returned to the opener on close; Tab trapped (synchronous `focus()` inside the capture-phase `focusout` verified on both targets, `setTimeout` 0 fallback); Escape/ArrowLeft/ArrowRight in the shared `key` closure (A19.9 follows A14.5; A19.10 follows A13.8; every A19 entry after A15.3d); no `marketMenu` site added (the six-site pin); `navMenu`/`userMenu`/`giveMenu` cleared on open; the design's `go()`, the app's route sync (Browser Back) and `signOut` clear `lightbox`; body scroll not locked; `e.currentTarget` documented as NEW (no design precedent); A19.4 anchors on `photos: this.photoSet(p),` alone, never the `photoHeroId` orphan; hit-targets are contentless absolute `<button>`s with `aria-label="Expand photo: <caption>"` on the `hasSrc`/`hasAny` branches only.
- New approved states (append; 45 → 48): `detail-lightbox`, `browse-panel-lightbox`, `detail-lightbox-next` — each waits for the enlarged `<img>` `complete && naturalWidth > 0` and ends with `atTop`; added to `placeholderRings`; the raw-template `{{ lightbox.src }}` pre-hydration fetch on the reference is covered by harness.ts's `%7B%7B` route (verify no console error).
- Gates: the full set, with the worktree env below. No byte-identity pin on any icon outside `NEW_IN_V3`.
- Release: the version bump is the controller's at release, lockstep, next free patch in MERGE order (0.1.10 if this lands before the seller branch). QA click-through: both arrows; lightbox open/`<`/`>`/X/Escape/backdrop/keyboard on a seeded hospital with 7+ photographs.
- Defaults queued for John (D-A19): caption + counter pills shown; backdrop closes; wrap-around; no body-scroll lock; the third state included; no swipe/pinch/Home/End.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **(a) The design file is never hand-edited.** `Practice Match V3.rev2.dc.html` (pristine, SHA-256 `335753c3…f01d` pinned in `design-amendments.test.ts`) + `amendments()` == `Practice Match V3.dc.html`, produced by `npm run gen:design` and proved byte for byte. Every A18/A19 entry is `{ id, date: '2026-09-09', ruling, find, replace, count }`, and one row in `LOCAL_AMENDMENTS.md` quotes that `ruling` **byte for byte** (`every LOCAL_AMENDMENTS.md row quotes its amendment's ruling verbatim`).
- **(b) Nothing is invented.** Every element, attribute and style declaration below is copied from a cited line of the V3 design. The four compositions the design has no counterpart for (`z-index: 1100`; the image's two viewport `calc()` bounds; the X's `right: 10px; top: 10px` corner; the X glyph's combined `filter`) are named as exceptions in the A19 test and in the Open Questions, never presented as design.
- **(c) `logic.js` is a verbatim port; `App.vue`, `pseudo.css` are generated.** `app-generated.test.ts` requires `src/logic.js` == HEADER + the amended `<script data-dc-script>` body (with `"assets/` → `"/assets/` and `\n+$` → `\n`) + FOOTER. Re-derived by the python snippet in Task L2 Step 5, never hand-edited. `src/app.setup.js` is untouched: no new prototype prop.
- **(d) Zero pixel tolerance, never relaxed.** `maxDiffPixels: 0` beside `threshold: 0.1` stays. Baselines regenerate from the amended design in the same run, so the ruled change is legal there; a failure after regeneration means the app and the design diverged — stop and diff.
- **(e) The frozen manifest moves once, under A18, by exactly one row.** `frontend/tests/baseline-manifest.json` is re-pinned in Task L1 Step 7 with the reason recorded in `baseline-manifest.test.ts`'s header (the A6/A14 mechanism); `detail` alone moves. After A19 the manifest test is GREEN with **zero** moves — that is A19's acceptance criterion, not a nicety.
- **(f) 100 % lines, branches, functions and statements, frontend.** `cd frontend && npx vitest run --coverage`. `logic.js` is excluded from the measured set (it is the design's script), but every new branch in it is characterised in `logic.test.ts` regardless; `tests/design-amendments.ts` IS measured (new plain consts add no branches); the one app-side edit (`useStateRouteSync.ts`) is measured and gets its RED case first.
- **(g) 100 % backend, strict types, warnings as errors.** `poetry run ruff check app tests scripts && poetry run mypy app --strict && poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`. Only `tests/test_docs.py` changes here.
- **(h) No suppressions.** No `@ts-expect-error`, `@ts-nocheck`, `eslint-disable`, `# pragma: no cover`, no widened tolerance, no widened `coverage.exclude`.
- **(i) Surgical diffs.** The two arrows and the lightbox, nothing else. No drive-by tidy of the `photoHeroId`/`photoHeroHint`/`morePhotos` orphans, no SVG file is touched, no icon is re-synced.
- **(j) Deviations STOP.** A `find` that does not match with `count: 1` at its point of application, a moved frozen hash the plan did not predict (anything but `detail` in L1; anything at all in L2), a DOM-oracle line after regeneration, a gate that needs relaxing — stop and report. Do not improvise.
- **(k) Conventional commits, explicit pathspecs, the trailer.** `git add <path> …`, never `git add -A`. Trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Implementers do not push; the controller pushes to `origin` and `production` at hand-back.
- **(l) Worktree isolation.** Own database `practice_match_lightbox`, own Redis index, own Playwright ports (below). `lsof` the ports before every Playwright run. Never `pkill` by substring; never `git stash`; never enter another worktree.
- **(m) Retired numbers.** `tests/test_docs.py::test_no_tracked_text_file_cites_a_retired_number` scans every tracked text file against `RETIRED_TEXT`, which holds exactly two patterns: the photo-captions migration under its OLD number (the `migrations/024_…` path A-L12 renumbered to 090) and the A-L10 "N of M" arithmetic that the folders' true figures — 195 photographs, 73 rendered — replaced. Nothing written here may spell either. A `V3:<line>` number is never a retired number: the two patterns are a path and a phrase, so every `LOCAL_AMENDMENTS.md` row below may cite its line.

---

## Preconditions

Verify by grep, not by memory. If any check fails, **STOP** — `main` has moved and the numbers below must be re-derived.

```bash
cd "/Users/johndean/Development/Practice Match"
git rev-parse --short HEAD                                                # 7a85245
grep -c "id: 'A" frontend/tests/design-amendments.ts                     # 80 (the literals; A16/A17 must NOT be here)
grep -n "Fifteen families, 104 entries" CLAUDE.md                        # the current count sentence, line 28
grep -n "the 45 approved states" CLAUDE.md                               # the current state count, line 53
grep -n "toHaveLength(104)" frontend/tests/design-amendments.test.ts
grep -c "^| A" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md   # 81
grep -n '"Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen"' tests/test_docs.py           # the tuple ends at Fifteen
python3 - <<'PY'
import pathlib
P = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.rev2.dc.html").read_text()
A = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text()
for k in ['<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="filter: brightness(0) invert(1);">',
          '<img src="assets/icons/navigate-arrow.svg" alt="" width="13" height="13" style="flex: none; transform: rotate(180deg); opacity: .7;">Back to results',
          'transform: rotate(180deg)', 'e.currentTarget', 'lightbox', 'z-index: 900', 'position: fixed']:
    print(f"{k[:60]!r:64s} pristine={P.count(k)} amended={A.count(k)}")
print("lines", P.count("\n"), A.count("\n"))
PY
```

Expected exactly: `1 1`, `1 1`, `3 3`, `0 0`, `0 0`, `1 1`, `1 1`; `lines 3168 3557`. (Both A18 finds are unique in the pristine file and in today's amended file — neither depends on an earlier amendment's output.) (`transform: rotate(180deg)` is 3 in both because A13's caret builds its rotation in pieces; the three sites are V3:724, V3:895 and the pristine `moreCaretStyle` in the script — never use it bare as a `find`.)

```bash
docker compose -f docker-compose.dev.yml up -d
cd frontend && npm ci && npm run typecheck && npm test && npm run build
```

---

## What the design already has (the evidence this plan is built on)

### The arrow glyph and its seven sites

`assets/icons/navigate-arrow.svg` and `assets/icons/nav-arrow-white.svg` share one path in a 640 viewBox — arrowhead apex at x = 199, shaft to x = 424 — so the glyph points **LEFT** unrotated, and it is mirror-symmetric about y ≈ 320, which is why `transform: rotate(180deg)` is a horizontal flip and the design's own idiom for "point right" (V3:724). The public copy under `frontend/public/assets/icons/` differs from the bundle's by its C2PA `<metadata>` block only (the `<path d>` and the 8306-byte length are identical) — so **no SVG is touched**, and no byte-identity pin is added for it (`icons.test.ts` pins byte identity only for the seven `NEW_IN_V3` glyphs; eight of the 24 public icons differ from the bundle's copies by metadata today and such a pin would fail).

| Amended line | Screen | Element | Renders | Verdict | Approved states showing it | Frozen rows moved |
|---|---|---|---|---|---|---|
| V3:140 | desktop account menu, Sign out row | `navigate-arrow.svg` 14×14, unrotated, icon BEFORE "Sign out" | left | **ambiguous — question D-A18.1** | none (no state opens the menu) | none |
| V3:721 | Browse docked panel carousel, "Previous photo" | `nav-arrow-white.svg` 34×34, unrotated | left | correct | none today (needs two photographs; `browse-market-panel` selects Cedar Park) | — |
| V3:724 | same, "Next photo" | `nav-arrow-white.svg`, `transform: rotate(180deg)` | right | correct | none today | — |
| V3:784 | Browse docked panel, Competitive Landscape tile | `move-arrow.svg` 15×15 — a different glyph (shaft y 64→467, tip y 566.6): a down-pointing metric pictogram beside "per 10k households" | down | n/a — not a navigation arrow | `browse-market-panel` | — |
| **V3:819** | Browse docked panel, Insights-tab CTA "View full listing" | `navigate-arrow.svg` 12×12, unrotated, icon AFTER the text (pristine 705, text renamed by A3) | left | **backwards — A18.1** | `browse-market-panel` | none (a Browse state) |
| **V3:895** | detail header, "Back to results" | `navigate-arrow.svg` 13×13, `transform: rotate(180deg)`, icon BEFORE the text (pristine 781) | right | **backwards — A18.2** | `detail`; `interest-modal` (the detail under the translucent `rgba(0,58,112,.55)` scrim — its pixels change beneath it) | **`detail`** |
| V3:1434 | phone-frame header sign-out pill, after `{{ me.initials }}` | `navigate-arrow.svg` 12×12, unrotated, wired straight to `signOut` | left | **ambiguous — question D-A18.2** | `mobile-list`, `mobile-map`, `mobile-sheet`, `mobile-detail` | would be `mobile-list`, `mobile-detail` — **not touched** |

Both A18 finds are unique in the pristine file and at their point of application (1 / 1). A18.1 anchors on the **bare** `<img>` — the only 12 × 12 `navigate-arrow` carrying the whitening filter — and deliberately NOT on the "View full listing" label in front of it, although `View full listing<img …>` is unique too. The reason is the citation case in `design-amendments.test.ts`: its `outputOf` chases a row's output forward through any LATER amendment whose `find` includes that row's `replace`. A3's `replace` is `View full listing`; a find of `View full listing<img …>` would include it, A3's checked output would become A18.1's `<img>` line — which stands only at the CTA (V3:819) — and A3's own row, which also cites V3:831 (A11's site, where A3's text stands as well), would fail as stale. With the bare anchor the chase stops at A3, and A18 has no ordering dependency on any other family (measured: A3 is swallowed by nothing in either list). Declaration order `transform` before `filter` copies V3:724 (`display: block; transform: rotate(180deg); filter: drop-shadow(…)`). A18 changes no line count, so no `V3:<line>` citation moves under it — the citation case checks 30 and reports none stale on the L1 file.

### The photo surfaces

| Surface | Design lines | What is there | Click today |
|---|---|---|---|
| **Detail grid** (`isDetail`, V3:912–926) | tile frame V3:914 `position: relative; height: 168px; border-radius: 10px; overflow: hidden; background: var(--rf-band);` → `sc-if ph.hasSrc` filled `<image-slot>` (V3:915–917) → `sc-if ph.noSrc` empty `<image-slot>` (V3:918–920) → index + caption row | script: `detail()` V3:3010, `photos: this.photoSet(p)` V3:3032; `photoSet` V3:2503 (p2's `SRC` map V3:2505–2509; A15's extra tiles) | filled: nothing (`image-slot.js`'s shadow click handler acts only on editor `data-act` targets); **empty, on the reference only: `.empty` click → hidden `<input type=file>` → the OS file chooser** (`image-slot.js:571`, not gated on `data-editable`); the app's `ImageSlot.vue` builds no input |
| **Browse docked panel** (`md.hasSel`, V3:703; inside `md.isMarket`, so never mounted on the detail) | box V3:711 `position: relative; height: 232px; background: var(--rf-band); display: grid; place-items: center;` → current photo `sc-if hasAny` (V3:712–714) → empty `sc-if isEmpty` (V3:715–717) → prev/next `sc-if multiple` in a bare `<div>` (V3:718–726) → counter + caption pills `sc-if hasAny` (V3:727–732) → dots (V3:733–738) | `marketPanel()` V3:2577; the `photos` IIFE V3:2594–2617 — `withPhoto = photoSet(sel).filter(hasSrc)`, modulo wrap, `counter`, `currentCaption`, `prev`/`next` | photo: as the tile. Prev/Next: `mdPhoto ∓ 1`. `select`/`selectFromMap` reset `mdPhoto: 0` |
| Browse results-rail thumbnail (V3:657–668) | `<div onClick="{{ r.select }}">` card → 108×88 `<image-slot>` when `r.hasPhotoSrc` | `mdResults` V3:2415 `photoSrc: this.heroSrc(p)` — Round Rock's thumbnail IS filled on every Browse state | selects into the panel — **not a lightbox surface** |
| Mobile list card (V3:1453–1466) / mobile detail (V3:1634–1657) | static 108 px "Photo" band (V3:1456) / static 168 px "Exterior photo" band (V3:1636) — no `<image-slot>`, no `<img>` anywhere in the phone frame | — | nothing to click; **no mobile surface until a responsive design exists (D-I8-7)** |

Only **`p2` (Round Rock)** carries photographs on BOTH targets: the design's `SRC` map (three files, byte-identical in the bundle's `assets/photos/` and in `frontend/public/assets/photos/`; `round-rock-exterior-street.webp` md5 `fe8940bc…`), and the app's D6 stub (`tests/design-listings.mjs`) sends `photos: []`, which `load.ts` never copies onto `P`, so `p.photos &&` is falsey on both and the `SRC` branch resolves identically. `p1` (Cedar Park), the `detail` state's listing (`detailId: "p1"`, route `/practices/p1`), has six empty slots. That is why every lightbox state reaches p2 by clicks (browse → "Round Rock" → "View full listing"), exactly as `interest-modal` does — extending `ROUTE`/`ReachTarget` in harness.ts would trip `harness.test.ts`'s `referenceUrl`/`appPlan` pins for no gain.

### The idioms A19 reuses (each cited; each asserted in Task L2 Step 2)

- **Modal scrim**, V3:1048 (the design's only overlay tier, 1 occurrence): `position: fixed; inset: 0; z-index: 900; background: rgba(0,58,112,.55); display: grid; place-items: center; padding: 24px;` — taken verbatim except the z-index (below). Its inner box, V3:1049: `box-shadow: var(--shadow-xl); overflow: hidden; animation: rf-fade-up 300ms var(--easing-out) both;`.
- **Photo frame**, V3:914: `position: relative; border-radius: 10px; overflow: hidden; background: var(--rf-band);` (the tile's string minus its fixed `height: 168px`).
- **Prev/next arrows**, V3:720–725, verbatim: `<button onClick aria-label="Previous photo" style="position: absolute; left: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">` with `<img src="assets/icons/nav-arrow-white.svg" alt="" width="34" height="34" style="display: block; filter: drop-shadow(0 1px 3px rgba(0,58,112,.4));">`, and the Next twin with `right: 10px` and `transform: rotate(180deg)`. Hidden when `multiple` is false.
- **Close X**, V3:707–709: `width: 38px; height: 38px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center;` and `<img src="assets/icons/close-x-gray.svg" alt="" width="26" height="26" style="display: block;">`. `close-x-gray.svg` is a filled `#9aa5b1` circle-x; on the navy scrim it takes the design's own whitening `filter: brightness(0) invert(1)` (V3:819, 5 uses) plus the arrows' drop shadow.
- **Counter and caption pills**, V3:729–731, verbatim (12 px and 11.5 px — under the 19 px display-heading census, so the 29-count case is untouched).
- **Transparent hit-target**: the design's icon-button reset `padding: 0; border: 0; background: none; cursor: pointer;` (5 uses) + `position: absolute; inset: 0` (the mobile sheet, 1 use) + `width: 100%; height: 100%` (1 use) → a contentless, borderless, transparent `<button>` laid OVER the `<image-slot>` paints no pixel and changes none of the slot's geometry (`image-slot.css` `:host{display:block;position:relative;width:100%;height:100%}`). Dynamic `aria-label="{{ … }}"` has precedent (the pager, V3:692; 2 uses).
- **Dismissal closures** (A13.4 / A14.4 / A14.5 / A14.7 / A13.8): `trackMenuDismiss()` (V3:1898) registers ONE `pointerdown`, ONE `keydown` and ONE `focusout` capture listener on `document` in `componentDidMount` and removes them in `componentWillUnmount`; each menu is a guarded branch inside the shared closure. A19 adds a branch to `key` and to `out` and **no new listener**; the `pointerdown` closure is untouched (the backdrop closes through its own `onClick`).
- **Mount-ref focus idiom** (A13.2 `marketPanelRef`, A14.2 `givePanelRef`, review C1): never focus inside a `setState` callback — the app's `dc-logic.js` runs the callback synchronously before Vue renders; the reference's React runs it after commit. Seed a one-shot flag in state and let the element's callback `ref="{{ fn }}"` spend it. `ref` passes straight through on both runtimes (`support.js` as a React prop; `convert-dc.mjs` emits `:ref`).
- **"Opening me closes you"** (final review m7): every open path clears the other menus — `openLightbox` clears `navMenu`, `userMenu`, `giveMenu`. It does **not** name `marketMenu`: the metro listbox is shut by A13.4's `pointerdown` (capture, before the click) and A13.8's `focusout` before a tile click or an Enter on a tile can land, and `design-amendments.test.ts` pins `marketMenu: false, marketMenuAt: -1` to EXACTLY six sites.
- **`e.target` is the design's idiom (13 uses in the pristine file). `e.currentTarget` is NEW** — 0 uses in either file. It works on both runtimes (React 18's synthetic event sets `currentTarget` per listener during dispatch, and `openLightbox` reads it synchronously before `setState`; Vue passes the native event), but the claim rests on runtime behaviour, not on a design precedent — it is in the parity-risk list, not the idiom list.
- `tabindex="-1"` (A13.3 — the only `tabindex` in the design), `role`/`aria-*` pass through unchanged on both runtimes. `role="dialog"`/`aria-modal` do not yet exist in the design; adding them is the A13 move (`role="combobox"`/`listbox` were new too). `outline: none` (8 pristine uses), `calc(` (3), `100vh` (3) exist; `100vw` does not (an exception, below).

**What the design has nowhere:** any lightbox, any enlarged photograph, any `<img>` with a dynamic `src` (the pristine file's three `src="{{ … }}"` are all on `<image-slot>`), any `document.body` scroll lock, any `findIndex`. Body scroll is therefore NOT locked (the interest modal does not lock it either) — D-A19.

---

## File Structure

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `frontend/tests/design-amendments.ts` | modify | `A18_1`, `A18_2`, `A19_1`–`A19_12` + `amendments()` (definition order = list order, m8) | L1, L2 |
| `frontend/tests/design-amendments.test.ts` | modify | `AMENDMENT_IDS` + 2 then + 12; `toHaveLength(104)` → `(106)` → `(118)`; an A18 case; an A19 case | L1, L2 |
| `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` | **regenerated** | `npm run gen:design` | L1, L2 |
| `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` | modify | 2 rows, then 12 rows, in apply order; every `V3:<line>` recomputed in L2 | L1, L2 |
| `frontend/src/logic.js` | **re-ported** | unchanged bytes under A18 (template-only — verified, not assumed); the amended script under A19 | L1, L2 |
| `frontend/src/App.vue`, `frontend/src/generated/pseudo.css` | **regenerated** | `npm run gen:app` | L1, L2 |
| `frontend/src/logic.test.ts` | modify | `describe('A19 — the photo lightbox')` (RED first) | L2 |
| `frontend/src/router/useStateRouteSync.ts` | modify | a route-driven screen change closes the lightbox | L2 |
| `frontend/src/router/useStateRouteSync.test.ts` | modify | the RED case for it | L2 |
| `frontend/tests/screens.ts` | modify | `LIGHTBOX`, `photoLoaded`; three appended states | L2 |
| `frontend/tests/reference-baselines.spec.ts` | modify | the three names added to `placeholderRings`'s list | L2 |
| `frontend/tests/baseline-manifest.json` | **regenerated** (`node tests/baseline-manifest.mjs`) | ONE hash moves (`detail`), under A18 | L1 |
| `frontend/tests/baseline-manifest.test.ts` | modify | the A18 paragraph in the header record | L1 |
| `frontend/tests/visual.spec.ts-snapshots/`, `frontend/tests/dom-snapshots/` | **regenerated** | git-ignored (`.gitignore`) — a local step, not a committed artefact | L1, L2 |
| `CLAUDE.md` | modify | A18 and A19 clauses; the count sentence twice; the manifest sentence; the Layout state count | L1, L2 |
| `tests/test_docs.py` | modify | `number_words` through "Twenty", docstring | L1 |
| `DEPLOY.md` | — | no edit expected (nothing in it names an amendment count or a state) | L3 |
| `frontend/src/app.setup.js`, `frontend/tests/reference-server.mjs`, `frontend/tests/harness.ts` | — | **untouched**: no new prototype prop; p2 is reached by clicks | — |

---

## The amendments

Counts are measured **at the point of application, in list order** (`applyAmendments` throws, naming the entry, otherwise). All fourteen were re-counted against both files on 2026-09-09; the "pristine" column is informational — an entry whose `find` is an earlier entry's output is 0 there and 1 at application, and that is the D15 contract, not a defect.

| Id | Kind | Anchor (`find`) | At application / pristine | What it puts there |
|---|---|---|---|---|
| A18.1 | template, V3:819 | `<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="filter: brightness(0) invert(1);">` (the bare `<img>` — never the "View full listing" label before it, which would swallow A3's output in the citation chase) | 1 / 1 | the same `<img>` with `style="transform: rotate(180deg); filter: brightness(0) invert(1);"` |
| A18.2 | template, V3:895 | `<img src="assets/icons/navigate-arrow.svg" alt="" width="13" height="13" style="flex: none; transform: rotate(180deg); opacity: .7;">Back to results` | 1 / 1 | the same `<img>` with `style="flex: none; opacity: .7;"` |
| A19.1 | script — `state` literal | `    interest: "closed", interestMsg: "", sent: [],\n` | 1 / 1 | `+ lightbox: null, lightboxFocus: false,` |
| A19.2 | script — class members, before `marketPanel` | `  marketPanel(sel, selComm, comms, market) {\n` | 1 / 1 | `openLightbox`, `closeLightbox`, `lightboxPhotos()`, `stepLightbox`, `lightboxVals()` |
| A19.3 | script — `renderVals()` key | `      interestOpen: s.interest !== "closed",\n` | 1 / 1 | `lightbox: this.lightboxVals(),` before it |
| A19.4 | script — `detail()` | `      photos: this.photoSet(p),\n` (alone — never the `photoHeroId` orphan) | 1 / 1 | filled tiles gain `open(e)` and `openLabel` |
| A19.5 | script — `marketPanel()` photos IIFE | `          currentCaption: cur ? cur.caption : "",\n` | 1 / 1 | `open(e)` and `openLabel` for the current photograph |
| A19.6 | template — detail tile | the `ph.noSrc` `sc-if` block (3 lines, V3:918–920) | 1 / 1 | + a third `sc-if ph.hasSrc` holding the hit-target `<button>` |
| A19.7 | template — docked panel box | the `md.panel.photos.isEmpty` `sc-if` block (3 lines, V3:715–717) | 1 / 1 | + an `sc-if md.panel.photos.hasAny` holding the hit-target, BEFORE the arrows so arrows, pills and dots stay above it |
| A19.8 | template — root, after the `isMobile` block | `  </sc-if>\n\n</div>\n\n</x-dc>` | 1 / 1 | the overlay `sc-if lightbox.open`, once |
| A19.9 | script — the shared `key` closure | `    const key = (e) => {\n      if (e.key !== "Escape") return;\n` | 1 / **0** (A14.5's output — after A14.5) | Escape / ArrowLeft / ArrowRight while the lightbox is open |
| A19.10 | script — the shared `out` closure | `    const out = (e) => {\n` | 1 / **0** (A14.7's output as A13.8 left it — after A13.8) | the focus trap, ABOVE the `const to` line so the pinned Give/metro text stays contiguous |
| A19.11 | script — `go()` | `    this.setState({ screen, interest: "closed", userMenu: false });\n` | 1 / 1 | `+ lightbox: null, lightboxFocus: false` |
| A19.12 | script — `signOut` | `        interest: "closed", activeId: null, hoverId: null, sellerView: "dash", wizSubmitted: false, formError: ""\n` | 1 / 1 | `+ lightbox: null, lightboxFocus: false` |

**Counts.** A18: 80 → **82 literals**, 104 → **106 entries**, **Sixteen** families (2–15, 18, plus A1), 81 → **83 rows**. A19: **94 literals**, **118 entries**, **Seventeen** families (2–15, 18, 19, plus A1), **95 rows**. `tests/test_docs.py` derives every one of these from `design-amendments.ts` (`id: 'A(\d+)` → distinct numbers + 1 for A1; literals = match count; A1's 24 from the test file's `Array.from({ length: 24 } …)`), so CLAUDE.md must contain exactly `Sixteen families, 106 entries` and `A1's 24 derived edits plus 82 literals` after L1, and exactly `Seventeen families, 118 entries` and `A1's 24 derived edits plus 94 literals` after L2. The number-word tuple stops at "Fifteen" today — extending it is L1 Step 5's first move.

**Why A19.10 anchors on `const out = (e) => {` and not on `const to = e.relatedTarget;\n if (!to) return;`.** `design-amendments.test.ts` pins the `out` closure's Give text as one contiguous substring — `      const to = e.relatedTarget;\n      if (!to) return;\n      if (this.state.giveMenu) {\n …` — so a branch inserted between `if (!to) return;` and the Give guard would break that pin. Inserting the lightbox branch at the top of the closure, reading `e.relatedTarget` directly and returning early, leaves every pinned byte of A13.8's output contiguous; a null `relatedTarget` (window blur, a click on the photograph or the scrim) is left alone there exactly as it is below.

---

## Pre-flight — every gate this change touches

| Gate | Where | What this plan does to it | Action |
|---|---|---|---|
| Pristine-file hash | `design-amendments.test.ts` | untouched — nothing edits `…rev2.dc.html` | stays green |
| pristine + amendments == amended | `design-amendments.test.ts` | 2 then 12 more entries | `npm run gen:design` (expect `106 amendments applied`, then `118`) |
| Amendment set pinned both ways | `design-amendments.test.ts` | `AMENDMENT_IDS` + 2 / + 12; `toHaveLength(104)` → `106` → `118` | edit, RED first |
| Every `find` counts `count` at application | `design-amendments.test.ts` | A19.9 and A19.10 are outputs of A14.5 and A13.8; A18's two finds are unique in both files | the A19 pair after A15.3d — the last entries; A18 is appended too, as every family is, not for a dependency |
| The citation chase (`outputOf`: a later `find` that includes a row's `replace` takes over that row's output) | `design-amendments.test.ts` | A18.1's bare `<img>` anchor includes no earlier `replace`; nothing later includes A18's or A19's | stays green (A3 swallowed by nothing — measured in both lists) |
| No doubled blank line | `design-amendments.test.ts` | A19.8 keeps exactly one blank line before and after its block; the count stays 1 (verified in simulation) | stays green |
| The six metro-dismissal sites | `design-amendments.test.ts` | `openLightbox` names no `marketMenu` key — count stays 6 | stays green (asserted in `logic.test.ts` too) |
| The `out`/`down` closure substrings | `design-amendments.test.ts` | A19.10 inserts ABOVE the pinned text; `down` is untouched | stays green |
| `<select ` = 4, Montserrat = 5, `View full listing` = 2, `@font-face` = 1, `role="menuitem"` = 1 | `design-amendments.test.ts` | A18.1's `replace` keeps the "View full listing" text; nothing else touches these | stays green (verified in simulation) |
| The 29-count display-heading census | `design-amendments.test.ts` | the two pills are 12 px / 11.5 px — below the 19 px census floor; the hit-target and dialog carry no `font-size` | stays green (29 in simulation) |
| The A14.6 font-family walk | `design-amendments.test.ts` | no new `font-family` | stays green |
| Row per amendment, ruling verbatim, apply order | `LOCAL_AMENDMENTS.md` | 81 → 83 → 95 rows | rows appended LAST, in list order |
| Every `V3:<line>` citation lands (n ± 1) | `design-amendments.test.ts` | A18 moves no line; **A19 inserts 31 template lines above the `<script>` and 72 inside it (+103 total; the file goes 3557 → 3660 lines)** — every existing citation numbered above V3:717 goes stale (A19.7's insertion, after V3:717, is the first): 27 of the 28, A14.3's V3:112 excepted | recompute all of them in L2 Step 7 (table given; the test names each stale row) |
| CLAUDE.md family/entry pin | `tests/test_docs.py::test_claude_md_amendment_family_and_entry_counts_match_design_amendments` | **`number_words` ends at "Fifteen" — sixteen families fails the PYTHON test before CLAUDE.md is read** | extend through "Twenty" (L1 Step 5), then the two exact substrings |
| `LOCAL_AMENDMENTS.md` row-count pin | `tests/test_docs.py` | `literal_count + 1` == 83, then 95 | satisfied by the rows |
| CLAUDE.md approved-state count | `tests/test_docs.py::test_claude_md_approved_screen_count_matches_screens_ts` (regex `^\s*\{ name: '` over screens.ts) | 45 → **48** — each new entry must START its line with `{ name: '` | edit the Layout line (L2 Step 8) |
| Retired numbers | `tests/test_docs.py::test_no_tracked_text_file_cites_a_retired_number` | this plan and every edit spell neither | — |
| Relative markdown links resolve | `tests/test_docs.py::test_relative_markdown_links_resolve` | this plan's links | verified before commit |
| `logic.js` byte-identity | `app-generated.test.ts` | unchanged under A18 (proved by `git diff --exit-code`); the script changed in nine places under A19 (A19.1–A19.5, A19.9–A19.12) | re-port with the snippet |
| `App.vue` / `pseudo.css` byte-identity; Vue compile; prop parity; `isBrowse` once; no `v-hover` | `app-generated.test.ts` | two style attributes (A18); three template blocks and three new `style-hover` rules (A19) — `pseudo.css` renumbers by first encounter, which is harmless (regenerated wholesale, folded by the DOM oracle); **no new prop; `style-hover` only, never a directive** | `npm run gen:app` |
| Icon assets exist | `icons.test.ts` | `nav-arrow-white.svg`, `close-x-gray.svg` already exist in both directories; **no new SVG; no new byte-identity pin** | stays green |
| Bundle budget (main ≤ 220 KB gz) | `bundle-budget.test.ts` | grows by well under 2 KB | `npm run build` before `vitest` |
| First-28-states order | `cross-plan-deltas.test.ts` `SCREENS.slice(0, 28)` | the three states are APPENDED after `header-give-menu` (the A13 controller ruling: future states append; artefacts are keyed by name) | append only |
| `placeholderRings` guard | `reference-baselines.spec.ts` (`['browse', 'detail', 'interest-modal']`) | the three new states mount filled `<image-slot>`s beneath a 55 % scrim, where a pre-hydration ring (B2) would be frozen into the oracle | add the three names |
| **Visual** | `visual.spec.ts` at `maxDiffPixels: 0` | A18 re-bases `browse-market-panel`, `detail`, `interest-modal`; A19 re-bases nothing existing and adds three | `npm run test:visual:baselines`, then `npm run test:e2e` — twice, once per task |
| **The thirteen frozen hashes** | `baseline-manifest.json` / `.test.ts` | **A18: exactly `detail` moves**, re-pinned with the reason. **A19: zero moves** — the acceptance criterion | L1 Step 7; L2 Step 9 |
| **DOM oracle** | `dom.spec.ts`, `dom.ts`, `dom-snapshots/` | both sides change together (the reference project writes the snapshots from the amended design). A19's attributes that must agree on both targets: `role`, `aria-modal`, `aria-label` (bound), `tabindex="-1"`, `alt` (bound), `src` (bound — the reference's `assets/photos/…` is Rule B-normalised to `/assets/photos/…`, the app's logic.js already reads `/assets/photos/…` from the port's `"assets/` rewrite); `ref`, `onClick` and `hint-*` are attributes on neither | regenerate, then read any line to zero |
| Smoke | `smoke.spec.ts` | its `div[style*="z-index: 900"]` query runs inside the interest-modal guard; the lightbox is `z-index: 1100` and is never mounted in that state | stays green |
| `harness.ts` `atTop`; the "exactly ONE `position: fixed` element" comment | `harness.ts` | the lightbox is the app's SECOND fixed element; the two are never mounted in the same state, so `MODAL`'s `.first()` sites still resolve to the modal; the states use `atTop(p, LIGHTBOX)` with a `[role="dialog"]` selector | correct the comment (L2 Step 6) |
| Sign-in budget (FOURTEEN of thirty, pinned against the runbook) | `harness.ts`, `test_docs.py` | the three states are buyer-family — the buyer's session jar is minted once per run and reused | unchanged |
| Backend | `poetry run pytest …` | only `tests/test_docs.py` | run it |
| Coverage | `vitest --coverage` | `useStateRouteSync.ts` gains one branch (RED case first); `design-amendments.ts` gains consts | 100/100/100/100 |

---

## Sequencing — A18 before A19, and why the order is evidence

`detail` is the only one of the thirteen frozen screens that carries either family's markup: A18.2's Back-to-results arrow is on the detail header, and A19.6's hit-target sits in the detail grid (`p1` has no filled tile there, so A19 mounts nothing on it — but that is the claim under test). Land both together and a one-line manifest diff cannot tell "A18.2 moved `detail`" from "A18.2 plus an A19 leak moved `detail`". So: A18 alone → `npx vitest run tests/baseline-manifest.test.ts` shows exactly `detail` → re-pin → commit. Then A19 → the same test is GREEN with zero moves, which is the direct, machine-checked proof that a transparent hit-target and an unmounted overlay changed no approved pixel. The same masking applies to `interest-modal` and `browse-market-panel` (A18 re-bases both; A19 adds three transparent buttons under `interest-modal`'s scrim): there the DOM oracle and the pixel gate after A19's regeneration are the check, and L2 Step 9 reads them.

Merge order against `feat/seller-lifecycle` (A16/A17): whichever branch merges second re-runs the four derived counts (`AMENDMENT_IDS`, `toHaveLength`, the CLAUDE.md sentence, `LOCAL_AMENDMENTS.md`'s tail) and recomputes every `V3:<line>` citation against the merged design (the fa1ab3f precedent, `docs(amendments): recompute every V3:<line> citation against the merged design`). `number_words` through "Twenty" covers 19 families after that merge.

---

### Task L1: A18, the two arrow reversals

### Step 0 — the worktree

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/feat-photo-lightbox -b feat/photo-lightbox main
cd .worktrees/feat-photo-lightbox
docker compose -f docker-compose.dev.yml up -d
psql "postgresql://pm:pm_dev_pw@localhost:5433/postgres" -c 'CREATE DATABASE practice_match_lightbox'
```

Every command in every task runs with this environment, and nothing is ever pointed at `practice_match`, the shared dev database (`tests/conftest.py::db_ready` migrates whatever `DATABASE_URL` names; `frontend/tests/targets.ts`'s api webServer runs `migrate.py` + `reset_rate_limits.py` + `seed_persona.py` against it too; process env beats its defaults):

```bash
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_lightbox
export REDIS_URL=redis://localhost:6380/8
export ENVIRONMENT=test
export API_SECRET_KEY=local_only_secret_change_me     # the sibling plans' value (seller plan, metro plan); app/config.py puts no length rule on it
export PW_APP_PORT=5473 PW_REF_PORT=5474 PW_CS_PORT=5475 PW_API_PORT=8047
lsof -nP -iTCP:5473,5474,5475,8047 -sTCP:LISTEN || true     # expect nothing listening — `reuseExistingServer: !CI` would adopt any process it finds
```

Redis `/8`: `targets.ts` defaults to `/0`, the metro plan used `/6`, the seller plan reserves `/7`; verify with `docker compose -f docker-compose.dev.yml exec -T redis redis-cli INFO keyspace` rather than asserting occupancy. Ports: the seller worktree uses 5513–5515/8357, the dropdowns worktree used 5503–5505/8347; distinct ports are what keep a parallel worktree's Vite, reference server or API from being adopted silently. A gate log must show `N passed` — a seconds-long "green" e2e is the API webServer failing to start.

- [ ] `cd frontend && npm ci` (node_modules are per checkout), then the Preconditions block above.

### Step 1 — RED: `frontend/tests/design-amendments.test.ts`

- [ ] Extend `AMENDMENT_IDS`, after `'A15.3d',`:

```ts
    // A18 — the two backwards arrows (John, 2026-09-09: "the arrow icons are backwards on each
    // location, reverse each"). Two template literals using the design's own flip idiom
    // (V3:724): the Insights-tab CTA's arrow turns right, the detail's Back-to-results arrow
    // turns left. Both finds are unique in the pristine file (A18.1 anchors on the bare <img>,
    // never on A3's label — the citation chase); the family is appended last, as every family is.
    'A18.1', 'A18.2',
```

- [ ] Raise the count: `toHaveLength(104)` → `toHaveLength(106)`.
- [ ] Add, after the A14.6 case:

```ts
  // A18 (John, 2026-09-09: "the arrow icons are backwards on each location, reverse each").
  // `navigate-arrow.svg` points LEFT unrotated (path apex at x = 199 in a 640 viewBox) and the
  // design's own way to point it RIGHT is `transform: rotate(180deg)` (V3:724). The Insights-tab
  // CTA (V3:819) showed it unrotated AFTER "View full listing" — pointing back at the label; the
  // detail's Back-to-results link (V3:895) showed it rotated BEFORE "Back to results" — pointing
  // away from where it goes. A18 swaps the two. The other five sites are untouched: the docked
  // panel's prev/next pair (correct), the metric glyph, and the two sign-out arrows John has not
  // ruled on (D-A18).
  it('A18 reverses exactly the two arrows John named and leaves the other five sites byte for byte', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(amended.split('View full listing<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="transform: rotate(180deg); filter: brightness(0) invert(1);">').length - 1).toBe(1);
    expect(amended.split('<img src="assets/icons/navigate-arrow.svg" alt="" width="13" height="13" style="flex: none; opacity: .7;">Back to results').length - 1).toBe(1);
    expect(amended).not.toContain('height="12" style="filter: brightness(0) invert(1);">');
    expect(amended).not.toContain('style="flex: none; transform: rotate(180deg); opacity: .7;">Back to results');
    // (Not asserted: a count of the rotate idiom. A18 adds one and removes one, but A19.8's
    // lightbox Next arrow adds another later in this branch, so an equality here would be a
    // pin on the wrong family.)
    // The five other sites, as designed. (Unrotated sign-out arrows at V3:140 and V3:1434 are
    // John's question, not this amendment's; the phone frame's is on two frozen screens.) The
    // docked panel's prev/next pair is pinned as each button line JOINED to its <img> line — by
    // the panel's own `md.panel.photos.prev`/`.next` handlers — and not as the bare <img>: A19.8
    // later in this branch copies both <img> tags verbatim into the lightbox, where a bare count
    // would read 2 against the pristine 1 and fail this case for the wrong family.
    for (const kept of [
      '<img src="assets/icons/navigate-arrow.svg" alt="" width="14" height="14" style="flex: none; opacity: .7;">',                          // V3:140
      '<button onClick="{{ md.panel.photos.prev }}" aria-label="Previous photo" style="position: absolute; left: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">\n                      <img src="assets/icons/nav-arrow-white.svg" alt="" width="34" height="34" style="display: block; filter: drop-shadow(0 1px 3px rgba(0,58,112,.4));">',                              // V3:720–721
      '<button onClick="{{ md.panel.photos.next }}" aria-label="Next photo" style="position: absolute; right: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">\n                      <img src="assets/icons/nav-arrow-white.svg" alt="" width="34" height="34" style="display: block; transform: rotate(180deg); filter: drop-shadow(0 1px 3px rgba(0,58,112,.4));">',  // V3:723–724
      'assets/icons/move-arrow.svg',                                                                                                            // V3:784
      '<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="flex: none; opacity: .7;">'                            // V3:1434
    ]) {
      expect(pristine, `${kept} is not the pristine site this case thinks it is`).toContain(kept);
      expect(amended.split(kept).length - 1, `A18 changed a site outside its ruling: ${kept}`).toBe(pristine.split(kept).length - 1);
    }
  });
```

> Before running, verify the five `kept` strings against the pristine file — with Python's `str.count`, not `grep -c`, because the two panel strings span a line break (the `<button>` line, `\n`, 22 spaces, the `<img>` line, exactly as V3:720–721 and V3:723–724 read). The V3:140 and V3:1434 strings are quoted from the amended file's `<img>` tags (14×14 with `flex: none; opacity: .7;`; 12×12 with the same style). Measured on 2026-09-09: each of the five counts 1 in the pristine file, 1 after A18 and — the point of the joined form — still 1 after A19. If a count is not 1, correct the string, not the assertion.

- [ ] `npx vitest run tests/design-amendments.test.ts` — RED on the id list, the count and the new case.

### Step 2 — GREEN: the two amendments

- [ ] Add to `frontend/tests/design-amendments.ts`, immediately after `A15_3d` and before `export function amendments()` (definition order matches list order — m8):

```ts
/** A18 — the two backwards arrows (John, 2026-09-09; screenshots of the docked panel's "View
 *  full listing" button and the detail's "Back to results" link).
 *
 *  `navigate-arrow.svg` points LEFT unrotated — its path's apex is at x = 199 of a 640 viewBox
 *  and the shaft runs to x = 424 — and it is mirror-symmetric about its horizontal axis, which is
 *  why `transform: rotate(180deg)` is a horizontal flip and the design's own idiom for pointing
 *  it right (V3:724, the docked panel's Next arrow). The Insights-tab CTA carried it unrotated
 *  AFTER its label, so it pointed back at the words; the detail's Back link carried it rotated
 *  BEFORE its label, so it pointed away from where the link goes. A18 swaps the two — the
 *  declaration order `transform` before `filter` copies V3:724.
 *
 *  Not touched, deliberately: the SVG files (flipping the glyph would reverse the correct
 *  prev/next pair at V3:721/724 and the two sign-out arrows, and the app serves its own public
 *  copy anyway — identical path, different C2PA metadata); V3:140 and V3:1434, the two unrotated
 *  sign-out arrows, which are John's question (D-A18) and not his two screenshots — V3:1434 is
 *  inside the phone frame, on `mobile-list` and `mobile-detail`'s frozen pixels.
 *
 *  Line numbers in this family's comments name the amended file as it stood when A18 was written
 *  (the fa1ab3f convention: comments keep their numbers, LOCAL_AMENDMENTS.md's rows carry the ones
 *  the citation test re-checks after a later family inserts lines).
 */
const A18 = {
  date: '2026-09-09',
  ruling: 'the arrow icons are backwards on each location, reverse each'
};

/** A18.1 — the Insights-tab CTA (V3:819). Anchored on the bare `<img>` — the only 12 × 12
 *  `navigate-arrow` carrying the whitening filter, unique in the pristine file and at application
 *  — and deliberately NOT on the button's "View full listing" label in front of it:
 *  design-amendments.test.ts's citation case chases a row's output forward through any LATER
 *  amendment whose `find` includes its `replace`, so a find that carried A3's text would make
 *  A3's checked output this `<img>` line and stale A3's own V3:831 citation (A11's site, where
 *  A3's text also stands). The bare anchor keeps A18 independent of A3's position in the list. */
const A18_1: Amendment = {
  id: 'A18.1', ...A18,
  find: '<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="filter: brightness(0) invert(1);">',
  replace: '<img src="assets/icons/navigate-arrow.svg" alt="" width="12" height="12" style="transform: rotate(180deg); filter: brightness(0) invert(1);">',
  count: 1
};

/** A18.2 — the detail's Back-to-results link (V3:895). The plain text "Back to results" occurs
 *  twice (the mobile back button's `backLabel` in the script is the other); the `<img` prefix
 *  keeps this to the desktop link. */
const A18_2: Amendment = {
  id: 'A18.2', ...A18,
  find: '<img src="assets/icons/navigate-arrow.svg" alt="" width="13" height="13" style="flex: none; transform: rotate(180deg); opacity: .7;">Back to results',
  replace: '<img src="assets/icons/navigate-arrow.svg" alt="" width="13" height="13" style="flex: none; opacity: .7;">Back to results',
  count: 1
};
```

- [ ] Extend the return of `amendments()` — A18 last:

```ts
    A13_8,
    A15_1, A15_2, A15_3a, A15_3b, A15_3c, A15_3d,
    // A18 — the two arrow reversals (2026-09-09). Both finds are unique in the pristine file.
    A18_1, A18_2];
```

### Step 3 — regenerate

- [ ] `cd frontend && npm run gen:design` — expect `106 amendments applied`. A count error names the amendment whose `find` is not present exactly once at its point of application — STOP and re-measure, never edit the design by hand.
- [ ] Re-port `logic.js`. A18 is template-only, so the bytes must not change — run the snippet anyway and **prove** it:

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-photo-lightbox"
python3 - <<'PY'
import re, pathlib
dc = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text()
m = re.search(r'<script type="text/x-dc" data-dc-script[^>]*>', dc)
body = dc[m.end():dc.index("</script>", m.end())].replace('"assets/', '"/assets/')
body = re.sub(r'\n+$', '\n', body)
head = ("// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
        "// Do not restyle or restructure: every value here is design-approved.\n"
        "import { DCLogic } from './dc-logic.js';\n")
pathlib.Path("frontend/src/logic.js").write_text(head + body + "\nexport { Component, MARKETS, P };\n")
PY
git diff --exit-code -- frontend/src/logic.js      # MUST exit 0: a template-only family leaves the script byte-identical
```

- [ ] `cd frontend && npm run gen:app` — `App.vue` changes in exactly two `style` attributes (`git diff --stat -- src/App.vue` shows one file, two lines changed); `pseudo.css` is unchanged.
- [ ] `npx vitest run tests/design-amendments.test.ts tests/app-generated.test.ts tests/icons.test.ts` — green.
- [ ] `npm run typecheck && npm run build && npx vitest run --coverage` — green, 100/100/100/100.

### Step 4 — `LOCAL_AMENDMENTS.md`

Append two rows after `| A15.3d |`, in apply order. The ruling column is the `ruling` string byte for byte. The citations are valid at this commit (A18 changes no line count) and are **recomputed in L2 Step 7** when A19 shifts them.

```md
| A18.1 | 2026-09-09 | the arrow icons are backwards on each location, reverse each | One template literal (V3:819): the docked panel's Insights-tab CTA arrow. `navigate-arrow.svg` points left unrotated and sat AFTER "View full listing", pointing back at its own label; it gains `transform: rotate(180deg)` — the design's own flip, the docked panel's Next arrow — and points right, toward the listing it opens. The bytes of the `<img>` are otherwise unchanged; `transform` precedes `filter` as on that arrow. |
| A18.2 | 2026-09-09 | the arrow icons are backwards on each location, reverse each | One template literal (V3:895): the detail's "Back to results" link. The same glyph carried `transform: rotate(180deg)` BEFORE its label, pointing right — away from the results it returns to; the rotation is removed and it points left. The SVG files are untouched (the docked panel's prev/next pair and the two sign-out arrows share the glyph and are as designed). |
```

- [ ] `npx vitest run tests/design-amendments.test.ts` — the row-order, verbatim-ruling, citation and row-count cases green.

### Step 5 — `tests/test_docs.py`, then `CLAUDE.md`

- [ ] RED first: `poetry run pytest tests/test_docs.py -q -k amendment_family` — fails with `no spelled-out word on hand for 16 families`. The pin's own vocabulary stops at "Fifteen", so it cannot even reach CLAUDE.md.
- [ ] Extend the tuple in `test_claude_md_amendment_family_and_entry_counts_match_design_amendments`:

```python
    number_words = {n: w for n, w in enumerate(
        ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
         "Nineteen", "Twenty"))}
```

  and add to its docstring:

```python
    A18 (2026-09-09) made sixteen families and the tuple stopped at "Fifteen", so the assertion
    below failed on its own vocabulary before it ever compared CLAUDE.md — the tuple runs to
    "Twenty" now, which covers A19 (seventeen) and the seller branch's reserved A16/A17 (nineteen
    after that merge)."""
```

- [ ] Re-run: now RED on CLAUDE.md's sentence, naming `16 families, 106 entries (24 derived + 82 literals)`.
- [ ] `CLAUDE.md` line 28 — the count sentence: `Fifteen families, 104 entries: A1's 24 derived edits plus 80 literals` → **`Sixteen families, 106 entries: A1's 24 derived edits plus 82 literals`**.
- [ ] `CLAUDE.md` line 28 — the A18 clause, inserted after the A15 clause (after `…so every approved state keeps its pixels).`) and before `Fifteen families` (now `Sixteen families`), in the paragraph's voice:

> **A18** (John, 2026-09-09 — "the arrow icons are backwards on each location, reverse each"; screenshots of the docked panel's "View full listing" button and the detail's "Back to results" link): `navigate-arrow.svg` points left unrotated, and the design's own way to point it right is `transform: rotate(180deg)` (the docked panel's Next arrow); the Insights-tab CTA carried it unrotated after its label and the Back link carried it rotated before its label, so each pointed away from where it goes. Two literal template edits — A18.1 adds the rotation to the CTA's arrow, A18.2 removes it from the Back link's — and no SVG changes: the docked panel's prev/next pair and the two sign-out arrows (the account menu's row and the phone frame's pill — John's open question, D-A18) share the glyph and are untouched. `browse-market-panel`, `detail` and `interest-modal` re-based; `detail` is the one frozen row that moved and was re-pinned under the ruling, the other twelve — the two phone-frame captures included — unchanged.

- [ ] No `V3:<line>` in CLAUDE.md — this clause and A19's name their sites, never their lines. CLAUDE.md cites no line anywhere today (`grep -c "V3:" CLAUDE.md` → 0), nothing re-checks a number there, and the A18 sites move by three lines the moment A19 inserts above them; the rows in `LOCAL_AMENDMENTS.md` carry the citations and `design-amendments.test.ts` re-checks those.
- [ ] `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100` and `poetry run ruff check app tests scripts && poetry run mypy app --strict` — green.

### Step 6 — commit 1

```
fix(design): A18 — the two backwards arrows are reversed

The Browse docked panel's "View full listing" arrow pointed back at its
label and the detail's "Back to results" arrow pointed away from the
results. navigate-arrow.svg points left unrotated; the design's own way to
point it right is transform: rotate(180deg) (V3:724). A18.1 adds the
rotation at V3:819, A18.2 removes it at V3:895. No SVG changes; the docked
panel's prev/next pair and the two sign-out arrows are untouched (the
latter are John's open question, D-A18).

Two ruled amendments on the approved design; the file is regenerated from
the pristine bundle and App.vue regenerated. logic.js is byte-identical
(template-only family). tests/test_docs.py's number-word tuple runs to
"Twenty" so the family count can be compared at all.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `frontend/tests/design-amendments.ts`, `frontend/tests/design-amendments.test.ts`, `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `frontend/src/App.vue`, `CLAUDE.md`, `tests/test_docs.py`. (`frontend/src/logic.js` and `frontend/src/generated/pseudo.css` are unchanged — `git status` must confirm.)

### Step 7 — the oracles and the one-row re-pin

```bash
cd frontend
npm run test:visual:baselines     # the reference project: every PNG and DOM snapshot from the amended design (45 states)
npm run test:e2e                  # the app project: visual + DOM oracle + smoke + signin-form + account-flows — read the log for `N passed`
```

- [ ] **Green, or STOP.** A pixel or DOM line here is the app and the design having diverged, not a baseline problem. The three re-based captures — `browse-market-panel`, `detail`, `interest-modal` — are the ONLY ones whose PNGs differ from the previous run; check by eye that the CTA's arrow now points right and the Back link's left.
- [ ] `npx vitest run tests/baseline-manifest.test.ts` — expect **exactly one failure**, `every frozen baseline still hashes to its recorded SHA-256`, and in its diff **only `detail`** differs. `mobile-list` and `mobile-detail` unchanged is the proof the change reached nothing in the phone frame (V3:1434 untouched); the other ten unchanged proves no header or token leak. **Anything else moved = leak. STOP and diff; never re-write the manifest to make a test pass.**
- [ ] `node tests/baseline-manifest.mjs` — run directly it calls its own `writeManifest()` (2-space JSON + trailing newline). Never hand-edit a hash.
- [ ] `cd .. && git diff --stat frontend/tests/baseline-manifest.json` — **exactly one changed line**. More is a leak.
- [ ] Extend `frontend/tests/baseline-manifest.test.ts`'s header comment, after the A14 paragraph and before `const manifest =`, in the same voice:

```ts
// Amendment A18 (John, 2026-09-09: "the arrow icons are backwards on each location, reverse
// each") re-based ONE row. The detail's Back-to-results arrow (V3:895) pointed away from the
// results — the glyph points left unrotated and the design had rotated it; A18.2 removes the
// rotation, so `detail` moved by ruled design change. The other twelve kept their hashes: the
// two phone-frame captures because the frame's own sign-out arrow (V3:1434) is not in the ruling
// and was not touched, the other ten because nothing but that one `<img>` style changed. That is
// the tidiest available proof that A18 reached exactly the two elements John named. A18.1's
// site (the docked panel's CTA) is a Browse capture and not in this manifest. (Line numbers
// name the design as it stood at this re-pin; the rows in LOCAL_AMENDMENTS.md carry the ones
// re-checked after later insertions.)
//
// From here a moved hash means a CODE change moved a screen the design did not.
```

- [ ] `CLAUDE.md` line 28 — the manifest sentence, EXTENDED, never rewritten (`test_claude_md_does_not_claim_v2_byte_identity_after_the_launch_removal` pins `byte-identical to V2 again, hashes and all, **until the launch removal**`, `post-launch-removal hashes` and `D-I8-6`; keep every one). The A18 clause written in Step 5 already carries the re-pin sentence; nothing else in the paragraph changes.
- [ ] `npx vitest run tests/baseline-manifest.test.ts` — green.

### Step 8 — commit 2

```
test(baselines): re-pin `detail` under A18 — one row, the other twelve unchanged

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `frontend/tests/baseline-manifest.json`, `frontend/tests/baseline-manifest.test.ts`.

---

**Controller amendment A-LB1 (2026-09-09 ~17:15 WITA; ruling on the L1 review's one Important finding — a worktree-setup gap, not a code defect).** L1's first attempt died at Playwright's web-server start and its second attempt fixed it by hand: **a fresh worktree needs `npm ci` in `coming-soon/` as well as in `frontend/`**, because `frontend/tests/targets.ts` starts the Coming Soon app as one of its web servers, and a missing `node_modules` there fails the whole e2e run in seconds — the failure mode this plan already warns about reading as a pass. **And `docker-compose.dev.yml` binds fixed host ports (5433/6380), so a second worktree must never start its own stack**: reuse the running one, inside which this worktree's own database `practice_match_lightbox` and Redis index `/8` already live (Global Constraint (l)'s isolation is the database name, the Redis index and the Playwright ports — not a private container). Both facts are now Step 0 of every task in this plan and of any future worktree brief. The finding's process half is upheld and recorded: an implementer that meets an environmental blocker fixes it only when it touches nothing under version control, and says so in its return, not only in its report — anything that would edit a tracked file is still a STOP.

### Task L2: A19, the photo lightbox

### Step 1 — RED: `frontend/src/logic.test.ts`

Append after the A14 block. `logic.test.ts` runs `// @vitest-environment jsdom`, imports `{ Component, P }` and constructs `c = new Component({})` in a `beforeEach`; every case below fails with `TypeError`/`undefined` until Step 4 lands. Cases that arm the real `document` listeners mount and unmount **inside the test**, exactly as A13's cases do (`logic.test.ts` 1566–1575), and the block also carries A13's and A14's unconditional `afterEach` (M4) so a failed assertion cannot leave a listener bound to a dead component for the rest of the file.

```ts
// ---------------------------------------------------------------------------------------
// A19 — the photo lightbox (John, 2026-09-09: "the images/photos should be clickable and they
// expand and have < > to view all images larger with simple X to close"). The design shows a
// photograph at 168 px in the detail grid and at 232 px in the Browse docked panel and enlarges
// neither. The lightbox is composed from the interest modal's scrim, the panel's own prev/next
// arrows, its close button and its two pills; every branch of the state machine is new and
// every branch is covered here. `p2` (Round Rock) is the design's own three-photograph fixture.
// ---------------------------------------------------------------------------------------
describe('A19 — the photo lightbox', () => {
  afterEach(() => { c.componentWillUnmount(); });

  const P2 = { pid: 'p2', at: 'ph-p2-exterior' };
  /** A mounted, focusable stand-in for a tile's hit-target — what `closeLightbox` hands focus back to. */
  const opener = () => { const b = document.createElement('button'); document.body.appendChild(b); return b; };
  /** Round Rock's tiles, through the detail's own render values. */
  const p2Photos = () => { c.setState({ detailId: 'p2' }); return c.renderVals().d.photos; };

  it('starts closed and exposes nothing the template would render (A19.1/A19.3)', () => {
    expect(c.state).toMatchObject({ lightbox: null, lightboxFocus: false });
    const lb = c.renderVals().lightbox;
    expect(lb).toMatchObject({ open: false, src: '', caption: '', counter: '', label: '', multiple: false });
    // No orphan keys (the A2.3/A13.6 dead-code rule): every key has a reader in A19.8's block.
    expect(Object.keys(lb).sort()).toEqual(['backdrop', 'caption', 'close', 'counter', 'label', 'multiple', 'next', 'open', 'prev', 'ref', 'src']);
  });

  it('a filled tile carries an opener and its own label; an empty tile carries neither (A19.4)', () => {
    const photos = p2Photos();
    expect(photos.map((ph: any) => typeof ph.open)).toEqual(['function', 'function', 'function', 'undefined', 'undefined', 'undefined']);
    expect(photos[0].openLabel).toBe('Expand photo: Exterior — street view');
    expect(photos[1].openLabel).toBe('Expand photo: Exterior — side elevation');
    // The empty tile is the design's own object, untouched.
    expect(Object.keys(photos[3]).sort()).toEqual(['caption', 'hasSrc', 'id', 'index', 'noSrc', 'placeholder', 'src']);
    // Cedar Park (p1), the `detail` state's listing, has no photograph and therefore no hit-target —
    // which is why that frozen baseline cannot move.
    c.setState({ detailId: 'p1' });
    expect(c.renderVals().d.photos.every((ph: any) => ph.open === undefined && ph.openLabel === undefined)).toBe(true);
  });

  it('opening records the opener, names the photograph and closes the three header menus — not the metro one (A19.2)', () => {
    const btn = opener();
    try {
      c.setState({ navMenu: true, userMenu: true, giveMenu: true, marketMenu: true, marketMenuAt: 1 });
      p2Photos()[1].open({ currentTarget: btn });
      expect(c.state).toMatchObject({ lightbox: { pid: 'p2', at: 'ph-p2-exterior2' }, lightboxFocus: true, navMenu: false, userMenu: false, giveMenu: false });
      // The metro listbox is shut by its own pointerdown/focusout closures before a tile click can
      // land, so `openLightbox` does not name it — which is what keeps design-amendments.test.ts's
      // "exactly six sites" pin on `marketMenu: false, marketMenuAt: -1` true.
      expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 1 });
      expect(c._lightboxOpener).toBe(btn);
      expect(c.renderVals().lightbox).toMatchObject({
        open: true, src: '/assets/photos/round-rock-exterior-side.webp', caption: 'Exterior — side elevation',
        counter: '2/3', label: 'Photograph 2 of 3', multiple: true
      });
    } finally { btn.remove(); }
  });

  it('the docked panel opens the photograph its carousel is showing, so "N of M" equals its counter (A19.5)', () => {
    c.setState({ screen: 'browse', mdSel: 'p2', mdPhoto: 2 });
    const photos = c.renderVals().md.panel.photos;
    expect(photos.counter).toBe('3/3');
    expect(photos.openLabel).toBe('Expand photo: Exterior — parking and signage');
    photos.open(undefined);
    expect(c.state.lightbox).toEqual({ pid: 'p2', at: 'ph-p2-exterior3' });
    expect(c.renderVals().lightbox.label).toBe('Photograph 3 of 3');
    // Cedar Park has no photograph: `hasAny` is false, so the template mounts no hit-target there.
    c.setState({ mdSel: 'p1', mdPhoto: 0 });
    expect(c.renderVals().md.panel.photos.hasAny).toBe(false);
  });

  it('stepping wraps at both ends; a slot id the set no longer carries reads as the first (A19.2)', () => {
    c.setState({ lightbox: P2 });
    const step = (d: number) => { c.stepLightbox(d); return c.state.lightbox.at; };
    expect(step(1)).toBe('ph-p2-exterior2');
    expect(step(1)).toBe('ph-p2-exterior3');
    expect(step(1), 'past the last photograph, wraps to the first').toBe('ph-p2-exterior');
    expect(step(-1), 'before the first, wraps to the last').toBe('ph-p2-exterior3');
    c.setState({ lightbox: { pid: 'p2', at: 'ph-p2-gone' } });
    expect(c.renderVals().lightbox.label).toBe('Photograph 1 of 3');
    expect(step(1)).toBe('ph-p2-exterior2');
  });

  it('one photograph never steps and hides the arrows; nothing open never steps (A19.2)', () => {
    const one = { id: 'lb-one', area: 'Elgin', type: 'Small animal', photos: ['/api/listings/lb/photos/1'] };
    (P as unknown as Array<{ id: string }>).push(one);
    try {
      c.setState({ lightbox: { pid: 'lb-one', at: 'ph-lb-one-exterior' } });
      expect(c.renderVals().lightbox).toMatchObject({ open: true, multiple: false, counter: '1/1', label: 'Photograph 1 of 1' });
      c.stepLightbox(1);
      expect(c.state.lightbox.at).toBe('ph-lb-one-exterior');
      c.setState({ lightbox: null });
      c.stepLightbox(1);
      expect(c.state.lightbox).toBeNull();
    } finally {
      const fixtures = P as unknown as Array<{ id: string }>;
      fixtures.splice(fixtures.findIndex((x) => x.id === 'lb-one'), 1);   // structural restore (N1)
    }
  });

  it('a lightbox that names a listing with no photograph, or no listing, renders nothing (A19.2)', () => {
    c.setState({ lightbox: { pid: 'p1', at: 'ph-p1-exterior' } });
    expect(c.renderVals().lightbox.open).toBe(false);
    expect(c.lightboxPhotos()).toEqual([]);
    c.setState({ lightbox: { pid: 'no-such-listing', at: 'x' } });
    expect(c.lightboxPhotos()).toEqual([]);
  });

  it('closing clears the state and returns focus to the opener; with no opener recorded it just closes (A19.2)', () => {
    const btn = opener();
    try {
      p2Photos()[0].open({ currentTarget: btn });
      c.renderVals().lightbox.close();
      expect(c.state).toMatchObject({ lightbox: null, lightboxFocus: false });
      expect(document.activeElement).toBe(btn);
      expect(c._lightboxOpener).toBeNull();
      btn.blur();
      p2Photos()[0].open(undefined);          // no event, no opener
      expect(c._lightboxOpener).toBeNull();
      c.closeLightbox();                       // no throw; focus is left where it was
      expect(c.state.lightbox).toBeNull();
      expect(document.activeElement).not.toBe(btn);
    } finally { btn.remove(); }
  });

  it('the mount ref spends lightboxFocus exactly once — a Next or Prev re-render must not re-steal focus (A19.2)', () => {
    const box = document.createElement('div'); box.tabIndex = -1; document.body.appendChild(box);
    try {
      p2Photos()[0].open(undefined);
      c.renderVals().lightbox.ref(box);
      expect(document.activeElement).toBe(box);
      expect(c.state.lightboxFocus).toBe(false);
      expect(c._lightboxEl).toBe(box);
      box.blur();
      // Both runtimes call the OLD ref with null and the NEW one with the element on every render
      // (renderVals mints a new function each pass): the handle follows, the focus does not.
      c.renderVals().lightbox.ref(null);
      expect(c._lightboxEl).toBeNull();
      c.renderVals().lightbox.ref(box);
      expect(c._lightboxEl).toBe(box);
      expect(document.activeElement).not.toBe(box);
    } finally { box.remove(); }
  });

  it('the backdrop closes only when the click lands on the scrim itself (A19.2)', () => {
    const scrim = document.createElement('div'); const inner = document.createElement('img');
    c.setState({ lightbox: P2 });
    c.renderVals().lightbox.backdrop({ target: inner, currentTarget: scrim });
    expect(c.state.lightbox, 'a click on the photograph or inside the dialog must not close it').toEqual(P2);
    c.renderVals().lightbox.backdrop({ target: scrim, currentTarget: scrim });
    expect(c.state.lightbox).toBeNull();
  });

  it('Escape closes and ArrowLeft/ArrowRight step through the armed document listener; other keys are not swallowed (A19.9)', () => {
    const btn = opener();
    try {
      c.componentDidMount();
      p2Photos()[0].open({ currentTarget: btn });
      const press = (key: string) => { const e = new KeyboardEvent('keydown', { key, cancelable: true }); document.dispatchEvent(e); return e.defaultPrevented; };
      expect(press('ArrowRight')).toBe(true);
      expect(c.state.lightbox.at).toBe('ph-p2-exterior2');
      expect(press('ArrowLeft')).toBe(true);
      expect(c.state.lightbox.at).toBe('ph-p2-exterior');
      expect(press('a')).toBe(false);
      expect(c.state.lightbox).toEqual(P2);
      expect(press('Escape')).toBe(true);
      expect(c.state.lightbox).toBeNull();
      expect(document.activeElement).toBe(btn);
      c.componentWillUnmount();
    } finally { btn.remove(); }
  });

  it('with the lightbox closed, A13\'s and A14\'s dismissals are unchanged by A19\'s branches (A19.9/A19.10)', () => {
    c.componentDidMount();
    c.setState({ marketMenu: true, marketMenuAt: 2, giveMenu: true, lightbox: null });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    expect(c.state).toMatchObject({ marketMenu: true, marketMenuAt: 2, giveMenu: true });   // arrows mean nothing while closed
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(c.state).toMatchObject({ marketMenu: false, marketMenuAt: -1, giveMenu: false });
    const give = document.createElement('div'); const away = document.createElement('button');
    document.body.append(give, away);
    try {
      c.renderVals().giveMenuRef(give);
      c.setState({ giveMenu: true });
      give.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
      expect(c.state.giveMenu, 'Tab out of the Give menu still closes it').toBe(false);
    } finally { give.remove(); away.remove(); }
    c.componentWillUnmount();
  });

  it('Tab out of the open dialog is pulled back; a move inside it, a window blur and an unmounted dialog are left alone (A19.10)', () => {
    const box = document.createElement('div'); box.tabIndex = -1;
    const inside = document.createElement('button'); box.appendChild(inside);
    const away = document.createElement('button');
    document.body.append(box, away);
    try {
      c.componentDidMount();
      c.setState({ lightbox: P2 });
      // No dialog mounted yet (its ref has not run): nothing to pull focus to, and no throw.
      inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
      c.renderVals().lightbox.ref(box);
      away.focus();
      inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: away, bubbles: true }));
      expect(document.activeElement, 'focus leaving the dialog is returned to it').toBe(box);
      inside.focus();
      inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: box, bubbles: true }));
      expect(document.activeElement, 'a move inside the dialog is not interfered with').toBe(inside);
      inside.dispatchEvent(new FocusEvent('focusout', { relatedTarget: null, bubbles: true }));
      expect(document.activeElement, 'a window blur is left alone, as A14.7 leaves it').toBe(inside);
      c.componentWillUnmount();
    } finally { box.remove(); away.remove(); }
  });

  it('go() and signOut clear it — a screen change closes the lightbox (A19.11/A19.12)', async () => {
    c.setState({ auth: true, lightbox: P2, lightboxFocus: true });
    c.go('browse')();
    expect(c.state).toMatchObject({ screen: 'browse', lightbox: null, lightboxFocus: false });
    c.setState({ lightbox: P2, lightboxFocus: true });
    await c.renderVals().signOut();
    expect(c.state).toMatchObject({ screen: 'gate', auth: false, lightbox: null, lightboxFocus: false });
  });

  it('componentWillUnmount still removes the three document listeners — A19 added none', () => {
    const add = vi.spyOn(document, 'addEventListener');
    const remove = vi.spyOn(document, 'removeEventListener');
    c.componentDidMount();
    c.componentWillUnmount();
    const ours = (calls: unknown[][]) => calls.filter(([t]) => t === 'pointerdown' || t === 'keydown' || t === 'focusout');
    expect(ours(add.mock.calls)).toHaveLength(3);
    expect(ours(remove.mock.calls)).toHaveLength(3);
    add.mockRestore(); remove.mockRestore();
  });
});
```

- [ ] `npx vitest run src/logic.test.ts` — every A19 case RED; everything else green. (`go()`'s signed-out branch is not exercised with a lightbox open: a signed-out visitor cannot reach a photograph on either target.)

### Step 2 — RED: `frontend/tests/design-amendments.test.ts`

- [ ] Extend `AMENDMENT_IDS`, after `'A18.1', 'A18.2',`:

```ts
    // A19 — the photo lightbox (John, 2026-09-09). Twelve literal edits: the state keys, the
    // five class members, the render key, the two openers (detail tiles and the docked panel's
    // photograph), the two hit-targets, the overlay block at the root, the Escape/Arrow branch
    // in A14.5's `key` closure and the focus trap in A13.8's `out` closure, and the two screen
    // changes the design owns (`go()`, `signOut`) clearing it. A19.9 and A19.10 read A14.5's and
    // A13.8's output, so the whole family is appended last.
    'A19.1', 'A19.2', 'A19.3', 'A19.4', 'A19.5', 'A19.6', 'A19.7', 'A19.8', 'A19.9', 'A19.10', 'A19.11', 'A19.12',
```

- [ ] Raise the count: `toHaveLength(106)` → `toHaveLength(118)`.
- [ ] Add, after the A18 case. The four compositions are the design's own values put together, and they are asserted AS exceptions — each present exactly once and absent from the pristine file — rather than passed off as design:

```ts
  // A19 (John, 2026-09-09: "the images/photos should be clickable and they expand and have < >
  // to view all images larger with simple X to close"). Composed from the design's own elements —
  // the interest modal's scrim (V3:1048), the detail tile's frame (V3:914), the docked panel's
  // prev/next arrows (V3:720–725), its close button (V3:707–709) and its two pills (V3:729–731).
  // Line numbers here name the file A19 is applied to — the design as A18 left it, the numbering
  // its finds were measured against; the rows in LOCAL_AMENDMENTS.md carry the post-A19 ones.
  const A19_PREV = '<button onClick="{{ lightbox.prev }}" aria-label="Previous photo" style="position: absolute; left: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">';
  const HIT_TARGET = 'style="position: absolute; inset: 0; width: 100%; height: 100%; padding: 0; border: 0; background: none; cursor: pointer;"></button>';
  it('A19 introduces no styling beyond four named compositions, and every sc-if carries the design\'s hint', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const decl of [
      'position: fixed; inset: 0;',                                                            // scrim, V3:1048
      'background: rgba(0,58,112,.55); display: grid; place-items: center; padding: 24px;',     // scrim, V3:1048
      'border-radius: 10px; overflow: hidden; background: var(--rf-band);',                    // tile frame, V3:914
      'box-shadow: var(--shadow-xl);',                                                         // modal box, V3:1049
      'animation: rf-fade-up 300ms var(--easing-out) both;',                                   // modal box, V3:1049
      'outline: none;',                                                                        // the design's inputs
      'width: 38px; height: 38px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center;', // Close panel, V3:707
      'opacity: .92; transition: opacity 150ms var(--easing-out);',                            // arrows, V3:720
      'position: absolute; inset: 0',                                                          // the mobile sheet
      'width: 100%; height: 100%',
      'padding: 0; border: 0; background: none; cursor: pointer;',                             // the icon-button reset
      'filter: brightness(0) invert(1)',                                                       // whitening, V3:819
      'drop-shadow(0 1px 3px rgba(0,58,112,.4))',                                              // the arrows' shadow, V3:721
      'aria-label="Previous photo" style="position: absolute; left: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px;',
      'aria-label="Next photo" style="position: absolute; right: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px;',
      'position: absolute; right: 12px; bottom: 12px; font-size: 12px; font-weight: 500; color: var(--vf-navy); background: rgba(255,255,255,.92); border-radius: 4px; padding: 3px 9px;',
      'position: absolute; left: 12px; bottom: 12px; max-width: 55%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 11.5px; font-weight: 500; color: var(--vf-navy); background: rgba(255,255,255,.92); border-radius: 4px; padding: 3px 9px;'
    ]) expect(pristine, `${decl} is not the design's own`).toContain(decl);
    // The four compositions — each once, and none in the pristine file.
    for (const [decl, why] of [
      ['z-index: 1100;', 'above Leaflet\'s .leaflet-top/.leaflet-bottom at 1000 — the Esri attribution and controls sit in the root stacking context on Browse'],
      ['max-width: calc(100vw - 48px); max-height: calc(100vh - 48px);', 'the viewport minus the scrim\'s 24px padding; natural size otherwise'],
      ['right: 10px; top: 10px;', 'the arrows\' 10px inset, applied to the top corner for the X'],
      ['filter: brightness(0) invert(1) drop-shadow(0 1px 3px rgba(0,58,112,.4));', 'the whitening and the arrows\' shadow on one glyph']
    ] as const) {
      expect(amended.split(decl).length - 1, `${decl} — ${why} — must appear exactly once`).toBe(1);
      expect(pristine, `${decl} is a composition, not the design's`).not.toContain(decl);
    }
    // One overlay at the root; the dialog, its accessible name, its image and its controls.
    expect(amended.split('<sc-if value="{{ lightbox.open }}" hint-placeholder-val="{{ false }}">').length - 1).toBe(1);
    expect(amended).toContain('<div role="dialog" aria-modal="true" aria-label="{{ lightbox.label }}" tabindex="-1" ref="{{ lightbox.ref }}"');
    expect(amended).toContain('<img src="{{ lightbox.src }}" alt="{{ lightbox.caption }}"');
    expect(amended.split('aria-label="Close photo"').length - 1).toBe(1);
    expect(amended.split(A19_PREV).length - 1).toBe(1);
    expect(amended.split('aria-label="Previous photo"').length - 1, 'the panel\'s pair and the lightbox\'s').toBe(2);
    expect(amended.split('aria-label="Next photo"').length - 1).toBe(2);
    // Two hit-targets, on the hasSrc/hasAny branches ONLY — never on an empty slot, whose click on
    // the reference opens the design tool's file chooser (image-slot.js:571).
    expect(amended.split(HIT_TARGET).length - 1).toBe(2);
    expect(amended).toContain('<sc-if value="{{ ph.hasSrc }}" hint-placeholder-val="{{ false }}">\n                        <button onClick="{{ ph.open }}" aria-label="{{ ph.openLabel }}"');
    expect(amended).toContain('<sc-if value="{{ md.panel.photos.hasAny }}" hint-placeholder-val="{{ false }}">\n                  <button onClick="{{ md.panel.photos.open }}" aria-label="{{ md.panel.photos.openLabel }}"');
    // The pristine file has zero hint-less sc-ifs — a 100 % convention, kept.
    expect(amended.match(/<sc-if value="\{\{ [^"]* \}\}">/g)).toBeNull();
    // Focus moves through the mount ref, never a setState callback (A14 review C1); no new
    // document listener; nothing of this exists in the pristine file.
    expect(amended).not.toContain('}, () => this.closeLightbox(');
    expect(amended).not.toContain('}, () => el.focus(');
    expect(amended.split('document.addEventListener(').length - 1).toBe(3);
    expect(pristine).not.toContain('lightbox');
    expect(pristine, 'e.currentTarget is NEW to the design with A19 — parity rests on both runtimes, not on precedent').not.toContain('e.currentTarget');
  });
```

- [ ] `npx vitest run tests/design-amendments.test.ts` — RED on the id list, the count and the new case.

### Step 3 — RED: `frontend/src/router/useStateRouteSync.test.ts`

The reference has no router, so "a screen change closes the lightbox" has one leg that lives only on the app: Browser Back (and Forward) arrive as a route the visitor did not reach through state. Append, after the S2 token-route block (the file's real-router rule applies — `setup()` uses the real `Component`, the real route table and `createMemoryHistory`):

```ts
// ---------------------------------------------------------------------------------------
// A19 (John, 2026-09-09). The design's own `go()` and `signOut` clear the lightbox (A19.11/
// A19.12); a route-driven screen change — what history.back() delivers — reaches state through
// `apply()` and must clear it the same way, or the scrim outlives the screen it was opened on.
// ---------------------------------------------------------------------------------------
describe('useStateRouteSync — a route-driven screen change closes the photo lightbox (A19)', () => {
  it('Browser Back from an open lightbox closes it; a navigation that changes no state leaves it open', async () => {
    const { c, router } = await setup('/practices/p2');
    // `new Component({})` starts signed out, and `guard()` (sync.ts) answers a member route with
    // the sign-in gate and a pending patch while `state.auth` is false — so, exactly as the
    // pending-route cases above do, sign in first and let the remembered deep link apply. Without
    // this the component sits on the gate, `needsPatch` is false there, and the branch under test
    // is never entered.
    c.setState({ auth: true }); await flush(); await nextTick();
    expect(c.state).toMatchObject({ screen: 'detail', detailId: 'p2' });
    c.openLightbox('p2', 'ph-p2-exterior', undefined);
    expect(c.state.lightbox).toEqual({ pid: 'p2', at: 'ph-p2-exterior' });
    await router.push('/browse');                 // a route the visitor did not reach through state
    await flush(); await nextTick();
    expect(c.state.screen).toBe('browse');
    expect(c.state).toMatchObject({ lightbox: null, lightboxFocus: false });
    await router.push('/practices/p2');
    await flush(); await nextTick();
    c.openLightbox('p2', 'ph-p2-exterior2', undefined);
    await router.push('/practices/p2');           // the same route again: no state change, nothing closes
    await flush(); await nextTick();
    expect(c.state.lightbox).toEqual({ pid: 'p2', at: 'ph-p2-exterior2' });
  });
});
```

- [ ] `npx vitest run src/router/useStateRouteSync.test.ts` — the new case RED, in two stages: `c.openLightbox is not a function` until Step 4's re-port of `logic.js`; then RED on the `lightbox: null` assertion until Step 4's edit of `useStateRouteSync.ts`. This case is the only one that drives the new branch true (`c.state.lightbox` set when a route-driven patch lands), which is what keeps Global Constraint (f)'s 100 % on that file; every existing case covers the branch false.

### Step 4 — GREEN: the twelve amendments and the one app edit

- [ ] Add to `frontend/tests/design-amendments.ts`, immediately after `A18_2` and before `export function amendments()`:

```ts
/** A19 — the photo lightbox (John, 2026-09-09: "the images/photos should be clickable and they
 *  expand and have < > to view all images larger with simple X to close").
 *
 *  The design shows a photograph at 168 px (the detail grid's tiles, V3:914) and at 232 px (the
 *  Browse docked panel's carousel, V3:711) and enlarges neither; no `<img>` in the file has a
 *  dynamic `src`, and no overlay but the interest modal's exists. The lightbox is composed from
 *  what the design already has — the modal's scrim (V3:1048), the tile's frame (V3:914), the
 *  panel's 34 px prev/next arrows (V3:720–725) verbatim, its 38 px close button (V3:707–709)
 *  with the glyph whitened by the design's own `brightness(0) invert(1)`, and its counter and
 *  caption pills (V3:729–731) verbatim — and it pages the SAME list the carousel counts
 *  (`photoSet(p).filter(hasSrc)`, V3:2595), so "N of M" equals the panel's counter and A15's
 *  extra tiles page too.
 *
 *  Four compositions have no counterpart and are asserted as exceptions in the test: the scrim's
 *  `z-index: 1100` (Leaflet's attribution and controls are at 1000 in the root stacking context
 *  on Browse — a dialog covers the page while open, and the attribution returns on close); the
 *  image's two viewport bounds; the X's `right: 10px; top: 10px` corner; the X glyph's combined
 *  `filter`. `e.currentTarget` is NEW to the design here (0 uses before); it works on both
 *  runtimes because React 18's synthetic event sets it per listener during dispatch and
 *  `openLightbox` reads it synchronously before `setState`, and Vue passes the native event.
 *
 *  Focus follows the A13/A14 mount-ref idiom, never a `setState` callback (review C1): the
 *  dialog's callback ref spends the one-shot `lightboxFocus` flag, and `closeLightbox` focuses
 *  the still-mounted opener directly. Every closure that runs after a render reads `this.state`,
 *  because the reference replaces the state object on each `setState` while the app mutates it.
 *
 *  PIXEL-SAFE by construction: the overlay is one `sc-if` on `lightbox.open`, false in every
 *  approved state, so it is never mounted there; the only closed-state markup added is a
 *  contentless, borderless, transparent `<button>` over a FILLED slot, which paints nothing —
 *  and across the 45 states that is exactly Round Rock's three tiles under `interest-modal`'s
 *  scrim (`detail` is Cedar Park, six empty slots; `browse-market-panel` selects Cedar Park,
 *  `isEmpty`; the results rail is not an amended site). The frozen manifest must not move at
 *  all under A19 — that is the acceptance criterion, checked after A18's one-row re-pin.
 *
 *  Line numbers in this family's comments name the file A19 is applied to — the amended design
 *  as A18 left it, the numbering every A19 `find` was measured against. The post-A19 numbers,
 *  which the citation test checks, are LOCAL_AMENDMENTS.md's rows (fa1ab3f's convention: the rows
 *  are recomputed, the comments keep the numbers they were written with).
 */
const A19 = {
  date: '2026-09-09',
  ruling: 'the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close'
};

/** A19.1 — the two state keys, declared beside the interest modal's (A8.2 precedent for growing
 *  `state`). `lightbox` is null while closed and `{ pid, at }` — listing id, slot id of the
 *  photograph showing — while open, a slot id rather than an index so the open lightbox survives
 *  a `photoSet` re-evaluation and the docked panel can hand over `cur.id` directly. */
const A19_1: Amendment = {
  id: 'A19.1', ...A19,
  find: '    interest: "closed", interestMsg: "", sent: [],\n',
  replace: '    interest: "closed", interestMsg: "", sent: [],\n    lightbox: null, lightboxFocus: false,\n',
  count: 1
};

/** A19.2 — the class members, inserted before `marketPanel` (one occurrence) so the docked panel's
 *  code and the lightbox's sit together; A14.1's `money(n)` anchor is left alone so the two
 *  families never share a seam. `P.filter((x) => x.id === …)[0]` is `detail()`'s own lookup, so
 *  seeded listings (load.ts replaces `P` in place) resolve exactly as fixtures do. */
const A19_2: Amendment = {
  id: 'A19.2', ...A19,
  find: '  marketPanel(sel, selComm, comms, market) {\n',
  replace: [
    '  // A19 — the photo lightbox (John, 2026-09-09): one implementation of open, close and step,',
    '  // shared by the render values and by the document `key` closure in `trackMenuDismiss`.',
    '  // Every closure that runs AFTER a render reads `this.state`: the reference replaces the state',
    '  // object on each setState and the app mutates it in place, so a captured `s` is stale on one.',
    '  openLightbox = (pid, at, e) => {',
    '    this._lightboxOpener = (e && e.currentTarget) || null;',
    '    this.setState({ lightbox: { pid, at }, lightboxFocus: true, navMenu: false, userMenu: false, giveMenu: false });',
    '  };',
    '  closeLightbox = () => {',
    '    const back = this._lightboxOpener;',
    '    this._lightboxOpener = null;',
    '    this.setState({ lightbox: null, lightboxFocus: false });',
    '    if (back && back.focus) back.focus();',
    '  };',
    '  lightboxPhotos() {',
    '    const lb = this.state.lightbox;',
    '    const p = lb ? P.filter((x) => x.id === lb.pid)[0] : null;',
    '    return p ? this.photoSet(p).filter((ph) => ph.hasSrc) : [];',
    '  }',
    '  stepLightbox = (d) => {',
    '    const lb = this.state.lightbox;',
    '    const photos = this.lightboxPhotos();',
    '    const n = photos.length;',
    '    if (!lb || n < 2) return;',
    '    const i = Math.max(0, photos.map((ph) => ph.id).indexOf(lb.at));',
    '    this.setState({ lightbox: { pid: lb.pid, at: photos[((i + d) % n + n) % n].id } });',
    '  };',
    '  lightboxVals() {',
    '    const lb = this.state.lightbox;',
    '    const photos = this.lightboxPhotos();',
    '    const n = photos.length;',
    '    const i = lb ? Math.max(0, photos.map((ph) => ph.id).indexOf(lb.at)) : 0;',
    '    const cur = photos[i];',
    '    return {',
    '      open: !!(lb && cur),',
    '      src: cur ? cur.src : "",',
    '      caption: cur ? cur.caption : "",',
    '      counter: cur ? (i + 1) + "/" + n : "",',
    '      label: cur ? "Photograph " + (i + 1) + " of " + n : "",',
    '      multiple: n > 1,',
    '      prev: () => this.stepLightbox(-1),',
    '      next: () => this.stepLightbox(1),',
    '      close: this.closeLightbox,',
    '      backdrop: (e) => { if (e.target === e.currentTarget) this.closeLightbox(); },',
    '      ref: (el) => {',
    '        this._lightboxEl = el || null;',
    '        if (!el || !this.state.lightboxFocus) return;',
    '        this.setState({ lightboxFocus: false });',
    '        el.focus();',
    '      }',
    '    };',
    '  }',
    '',
    '  marketPanel(sel, selComm, comms, market) {',
    ''
  ].join('\n'),
  count: 1
};

/** A19.3 — the render key, beside the interest modal's, so the root-level block reads
 *  `{{ lightbox.open }}`, `{{ lightbox.src }}` and the rest. Closed → `open: false` and the
 *  sc-if mounts nothing. */
const A19_3: Amendment = {
  id: 'A19.3', ...A19,
  find: '      interestOpen: s.interest !== "closed",\n',
  replace: '      lightbox: this.lightboxVals(),\n      interestOpen: s.interest !== "closed",\n',
  count: 1
};

/** A19.4 — `detail()`: every FILLED tile gains its opener and its label; an empty tile is the
 *  design's own object, untouched (nothing to enlarge, and on the reference an empty slot's click
 *  is the design tool's file chooser). Anchored on the `photos:` line ALONE — the `photoHeroId`
 *  line beneath it is a pristine orphan no template reads, a candidate for the dead-code rule,
 *  and an anchor that includes it would break the day it is deleted. `Object.assign({}, …)` is
 *  the design's own spread idiom. The label carries the photograph's OWN caption (A15), so three
 *  buttons are not three identical names to a screen reader. */
const A19_4: Amendment = {
  id: 'A19.4', ...A19,
  find: '      photos: this.photoSet(p),\n',
  replace: '      photos: this.photoSet(p).map((ph) => ph.hasSrc ? Object.assign({}, ph, { open: (e) => this.openLightbox(p.id, ph.id, e), openLabel: "Expand photo: " + ph.caption }) : ph),\n',
  count: 1
};

/** A19.5 — the docked panel's photos IIFE: `cur` is already the photograph the carousel shows
 *  (`withPhoto[i]`), so the lightbox opens on exactly that one and its "N of M" is the panel's
 *  own counter. */
const A19_5: Amendment = {
  id: 'A19.5', ...A19,
  find: '          currentCaption: cur ? cur.caption : "",\n',
  replace: '          currentCaption: cur ? cur.caption : "",\n          open: (e) => this.openLightbox(sel.id, cur ? cur.id : "", e),\n          openLabel: "Expand photo: " + (cur ? cur.caption : ""),\n',
  count: 1
};

/** A19.6 — the detail tile: a third `sc-if`, on `ph.hasSrc`, holding a contentless absolute
 *  `<button>` laid OVER the `<image-slot>` (never wrapping it, so the slot's `height: 100%`
 *  geometry and the DOM around it are unchanged). A button is keyboard-reachable and
 *  announceable where an `onClick` on a `<div>` is not (A13's standard). Its style is the
 *  design's icon-button reset plus `inset: 0` and `width/height: 100%`: transparent, borderless,
 *  contentless — zero painted pixels in the closed state, no outline unless `:focus-visible`,
 *  which no mouse-driven capture triggers. Placed last in the frame so it paints above the slot. */
const A19_6: Amendment = {
  id: 'A19.6', ...A19,
  find: [
    '                      <sc-if value="{{ ph.noSrc }}" hint-placeholder-val="{{ false }}">',
    '                        <image-slot id="{{ ph.id }}" shape="rect" placeholder="{{ ph.placeholder }}"></image-slot>',
    '                      </sc-if>',
    ''
  ].join('\n'),
  replace: [
    '                      <sc-if value="{{ ph.noSrc }}" hint-placeholder-val="{{ false }}">',
    '                        <image-slot id="{{ ph.id }}" shape="rect" placeholder="{{ ph.placeholder }}"></image-slot>',
    '                      </sc-if>',
    '                      <sc-if value="{{ ph.hasSrc }}" hint-placeholder-val="{{ false }}">',
    '                        <button onClick="{{ ph.open }}" aria-label="{{ ph.openLabel }}" style="position: absolute; inset: 0; width: 100%; height: 100%; padding: 0; border: 0; background: none; cursor: pointer;"></button>',
    '                      </sc-if>',
    ''
  ].join('\n'),
  count: 1
};

/** A19.7 — the docked panel's photograph: the same hit-target on a `hasAny` sc-if (the panel's
 *  own habit — it gates the pills the same way, V3:727), placed BEFORE the `multiple` arrows so
 *  the prev/next buttons, the pills and the dots — all later siblings, all absolutely positioned —
 *  keep painting above it and stay clickable. */
const A19_7: Amendment = {
  id: 'A19.7', ...A19,
  find: [
    '                <sc-if value="{{ md.panel.photos.isEmpty }}" hint-placeholder-val="{{ false }}">',
    '                  <image-slot id="{{ md.panel.photos.emptyId }}" shape="rect" placeholder="{{ md.panel.photos.emptyHint }}"></image-slot>',
    '                </sc-if>',
    ''
  ].join('\n'),
  replace: [
    '                <sc-if value="{{ md.panel.photos.isEmpty }}" hint-placeholder-val="{{ false }}">',
    '                  <image-slot id="{{ md.panel.photos.emptyId }}" shape="rect" placeholder="{{ md.panel.photos.emptyHint }}"></image-slot>',
    '                </sc-if>',
    '                <sc-if value="{{ md.panel.photos.hasAny }}" hint-placeholder-val="{{ false }}">',
    '                  <button onClick="{{ md.panel.photos.open }}" aria-label="{{ md.panel.photos.openLabel }}" style="position: absolute; inset: 0; width: 100%; height: 100%; padding: 0; border: 0; background: none; cursor: pointer;"></button>',
    '                </sc-if>',
    ''
  ].join('\n'),
  count: 1
};

/** A19.8 — the overlay, ONCE, at the root after the `isMobile` block: two screens open it, it is
 *  `position: fixed` so its place in the tree affects no layout, and one block means one set of
 *  render values and one focus/keyboard implementation. The scrim is the interest modal's string
 *  (V3:1048) at `z-index: 1100`; the dialog takes the tile frame's declarations (V3:914) minus
 *  its fixed height plus the modal box's shadow and entrance (V3:1049) and `outline: none`; the
 *  image is natural size, never upscaled, bounded to the viewport minus the scrim's padding; the
 *  X is the panel's close button (V3:707–709) at the arrows' 10 px inset with the glyph
 *  whitened; the arrows are V3:720–725 verbatim, hidden when there is one photograph; the pills
 *  are V3:729–731 verbatim. Exactly one blank line before and after (the doubled-blank-line
 *  invariant). `aria-label="Close photo"` is new copy — the panel's says "Close panel". */
const A19_8: Amendment = {
  id: 'A19.8', ...A19,
  find: '  </sc-if>\n\n</div>\n\n</x-dc>',
  replace: [
    '  </sc-if>',
    '',
    '  <sc-if value="{{ lightbox.open }}" hint-placeholder-val="{{ false }}">',
    '    <div onClick="{{ lightbox.backdrop }}" style="position: fixed; inset: 0; z-index: 1100; background: rgba(0,58,112,.55); display: grid; place-items: center; padding: 24px;">',
    '      <div role="dialog" aria-modal="true" aria-label="{{ lightbox.label }}" tabindex="-1" ref="{{ lightbox.ref }}" style="position: relative; border-radius: 10px; overflow: hidden; background: var(--rf-band); box-shadow: var(--shadow-xl); outline: none; animation: rf-fade-up 300ms var(--easing-out) both;">',
    '        <img src="{{ lightbox.src }}" alt="{{ lightbox.caption }}" style="display: block; max-width: calc(100vw - 48px); max-height: calc(100vh - 48px);">',
    '        <button onClick="{{ lightbox.close }}" aria-label="Close photo" style="position: absolute; right: 10px; top: 10px; width: 38px; height: 38px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">',
    '          <img src="assets/icons/close-x-gray.svg" alt="" width="26" height="26" style="display: block; filter: brightness(0) invert(1) drop-shadow(0 1px 3px rgba(0,58,112,.4));">',
    '        </button>',
    '        <sc-if value="{{ lightbox.multiple }}" hint-placeholder-val="{{ false }}">',
    '          <div>',
    '            <button onClick="{{ lightbox.prev }}" aria-label="Previous photo" style="position: absolute; left: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">',
    '              <img src="assets/icons/nav-arrow-white.svg" alt="" width="34" height="34" style="display: block; filter: drop-shadow(0 1px 3px rgba(0,58,112,.4));">',
    '            </button>',
    '            <button onClick="{{ lightbox.next }}" aria-label="Next photo" style="position: absolute; right: 10px; top: 50%; margin-top: -17px; width: 34px; height: 34px; padding: 0; border: 0; background: none; cursor: pointer; display: grid; place-items: center; opacity: .92; transition: opacity 150ms var(--easing-out);" style-hover="opacity: 1;">',
    '              <img src="assets/icons/nav-arrow-white.svg" alt="" width="34" height="34" style="display: block; transform: rotate(180deg); filter: drop-shadow(0 1px 3px rgba(0,58,112,.4));">',
    '            </button>',
    '          </div>',
    '        </sc-if>',
    '        <div>',
    '          <span style="position: absolute; right: 12px; bottom: 12px; font-size: 12px; font-weight: 500; color: var(--vf-navy); background: rgba(255,255,255,.92); border-radius: 4px; padding: 3px 9px;">{{ lightbox.counter }}</span>',
    '          <span style="position: absolute; left: 12px; bottom: 12px; max-width: 55%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 11.5px; font-weight: 500; color: var(--vf-navy); background: rgba(255,255,255,.92); border-radius: 4px; padding: 3px 9px;">{{ lightbox.caption }}</span>',
    '        </div>',
    '      </div>',
    '    </div>',
    '  </sc-if>',
    '',
    '</div>',
    '',
    '</x-dc>'
  ].join('\n'),
  count: 1
};

/** A19.9 — the lightbox branch of the shared `keydown` closure, ahead of A14.5's Give guard. The
 *  find is A14.5's OUTPUT (0 in the pristine file), so this applies after it. With the lightbox
 *  closed the block is skipped and A13's and A14's Escape semantics are byte-identical; open, it
 *  owns the three keys and returns — every menu is already shut (A19.2), and none can reopen
 *  under a modal scrim. `preventDefault` so an arrow does not also scroll the page behind. */
const A19_9: Amendment = {
  id: 'A19.9', ...A19,
  find: '    const key = (e) => {\n      if (e.key !== "Escape") return;\n',
  replace: [
    '    const key = (e) => {',
    '      if (this.state.lightbox) {',
    '        if (e.key === "Escape") { e.preventDefault(); this.closeLightbox(); }',
    '        else if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); this.stepLightbox(e.key === "ArrowLeft" ? -1 : 1); }',
    '        return;',
    '      }',
    '      if (e.key !== "Escape") return;',
    ''
  ].join('\n'),
  count: 1
};

/** A19.10 — the focus trap, at the TOP of the shared `focusout` closure. The find is the closure
 *  head A14.7 introduced and A13.8 rewrote (0 in the pristine file), so this applies after A13.8;
 *  and it goes above the `const to` line rather than after `if (!to) return;` because
 *  design-amendments.test.ts pins A13.8's Give text as one contiguous substring starting at that
 *  `const to`. `aria-modal="true"` tells assistive tech the page behind is inert; this is what
 *  makes Tab honour it. A null `relatedTarget` (window blur, or a click on the non-focusable
 *  photograph or scrim) is left alone — nothing fights the backdrop click. */
const A19_10: Amendment = {
  id: 'A19.10', ...A19,
  find: '    const out = (e) => {\n',
  replace: [
    '    const out = (e) => {',
    '      // A19: while the lightbox is open, focus that is leaving the dialog for anywhere else in the',
    '      // document is pulled back to it — `aria-modal` says the page behind is inert, and Tab honours',
    '      // that only if something makes it. A null `relatedTarget` (a window blur, or a click on the',
    '      // photograph or the scrim, neither of which is focusable) is left alone, as it is below.',
    '      if (this.state.lightbox) {',
    '        const box = this._lightboxEl;',
    '        if (e.relatedTarget && box && !box.contains(e.relatedTarget)) box.focus();',
    '        return;',
    '      }',
    ''
  ].join('\n'),
  count: 1
};

/** A19.11 — `go()`: a screen change closes the lightbox, on the line that already closes the
 *  interest modal for the same reason. (The signed-out branch above it is unreachable with a
 *  lightbox open: a photograph is behind the sign-in gate on both targets.) */
const A19_11: Amendment = {
  id: 'A19.11', ...A19,
  find: '    this.setState({ screen, interest: "closed", userMenu: false });\n',
  replace: '    this.setState({ screen, interest: "closed", userMenu: false, lightbox: null, lightboxFocus: false });\n',
  count: 1
};

/** A19.12 — `signOut`: the reset that already closes the interest modal closes the lightbox too,
 *  so a session that ends (the 401 path on the app) cannot leave the scrim over the gate card. */
const A19_12: Amendment = {
  id: 'A19.12', ...A19,
  find: '        interest: "closed", activeId: null, hoverId: null, sellerView: "dash", wizSubmitted: false, formError: ""\n',
  replace: '        interest: "closed", activeId: null, hoverId: null, sellerView: "dash", wizSubmitted: false, formError: "",\n        lightbox: null, lightboxFocus: false\n',
  count: 1
};
```

- [ ] Extend the return of `amendments()` — A19 last, after A18:

```ts
    // A18 — the two arrow reversals (2026-09-09). Both finds are unique in the pristine file.
    A18_1, A18_2,
    // A19 — the photo lightbox (2026-09-09). A19.9 reads A14.5's output and A19.10 reads A13.8's,
    // so the family is last. Definition order in this file matches this list (m8).
    A19_1, A19_2, A19_3, A19_4, A19_5, A19_6, A19_7, A19_8, A19_9, A19_10, A19_11, A19_12];
```

- [ ] `frontend/src/router/useStateRouteSync.ts` — the one app-side edit. The interface:

```ts
// A19 (John, 2026-09-09): a route-driven screen change calls the design's own `closeLightbox` —
// see `apply()`. Required, not optional: the one component this composable ever receives is the
// design's `Component` (app.setup.js; every test here uses the real one), which carries it, and
// an optional call would leave a branch no test could reach.
interface StatefulComponent { state: RoutedState & { lightbox?: unknown }; setState(patch: Partial<RoutedState>): void; closeLightbox(): void }
```

  and in `apply()`, the line `if (needsPatch(c.state, g.apply)) c.setState(g.apply);` becomes:

```ts
    if (needsPatch(c.state, g.apply)) {
      c.setState(g.apply);
      // A19: a route-driven screen change — Browser Back or Forward — closes the photo lightbox,
      // as the design's own `go()` and `signOut` do (A19.11/A19.12). The reference has no router,
      // so this is the one leg of "a screen change closes it" that lives on the app side; it calls
      // the design's own `closeLightbox` so the clearing stays one implementation.
      if (c.state.lightbox) c.closeLightbox();
    }
```

### Step 5 — regenerate and run the unit gates

- [ ] `cd frontend && npm run gen:design` — expect `118 amendments applied`. A count error names the entry — STOP.
- [ ] Re-port `logic.js` with the snippet from L1 Step 3 (the script changed in nine places this time — A19.1–A19.5 and A19.9–A19.12; `git diff --stat -- frontend/src/logic.js` shows one file).
- [ ] `npm run gen:app` — `App.vue` gains the two hit-target `<template v-if>` blocks and the overlay block; `pseudo.css` gains three `opacity: 1` hover rules (the X and the two arrows) and renumbers later hooks by first encounter (harmless; regenerated wholesale, folded by the DOM oracle).
- [ ] `npx vitest run tests/design-amendments.test.ts tests/app-generated.test.ts tests/icons.test.ts src/logic.test.ts src/router/useStateRouteSync.test.ts` — all green; the A19 block and the route-sync case have gone RED → GREEN.
- [ ] `npm run typecheck && npm run build && npx vitest run --coverage` — green, 100/100/100/100.

### Step 6 — the three approved states

Append to `frontend/tests/screens.ts`, **at the end** of `SCREENS` after `header-give-menu` (`cross-plan-deltas.test.ts` pins `SCREENS.slice(0, 28)`; the A13 controller ruling: future states append; artefacts are keyed by name). Each entry's line **starts** with `{ name: '` — that is what `tests/test_docs.py`'s `^\s*\{ name: '` regex counts.

- [ ] Beside `MODAL`, the two helpers:

```ts
// A19: the photo lightbox. Addressed by ROLE, not by a z-index string: the overlay is App.vue's
// SECOND `position: fixed` element (the interest modal's scrim is the first — see harness.ts's
// `atTop`), and the two are never mounted in the same state, so `MODAL`'s `.first()` sites still
// resolve to the modal in theirs. `atTop` runs `document.querySelector`, and this is a plain
// selector.
const LIGHTBOX = '[role="dialog"][aria-modal="true"]';
// The enlarged photograph starts loading only when the dialog mounts, and `settle()`'s 600 ms is
// not a proof that a 680 px WebP has decoded: wait for the image element itself.
const photoLoaded = async (p: Page) => {
  await p.waitForFunction((sel) => {
    const i = document.querySelector(`${sel} img`) as HTMLImageElement | null;
    return !!i && i.complete && i.naturalWidth > 0;
  }, LIGHTBOX);
};
```

- [ ] The three states:

```ts
  // A19: the photo lightbox — the 46th, 47th and 48th approved states, APPENDED for the reason
  // A13's and A14's were. Only Round Rock (p2) carries photographs on BOTH targets — the design's
  // own `SRC` map, byte-identical in the bundle and in frontend/public — and the D6 stub sends
  // `photos: []`, so both targets take the same branch; Cedar Park (`detail`'s p1) has six empty
  // slots. So each state reaches p2 the way `interest-modal` does, clicks the FIRST tile's
  // hit-target by its own label, waits for the dialog by its accessible name and for the image to
  // decode, and — because the overlay is `position: fixed` — ends pinned at the top exactly as
  // `interest-modal` is. There is no prototype prop for any of this and none is needed: it is a
  // click on markup both targets render.
  { name: 'detail-lightbox', steps: async (p) => {
    await browse(p);
    await p.getByText('Round Rock').first().click();
    await click(p, 'View full listing');
    await p.getByRole('button', { name: 'Expand photo: Exterior — street view' }).click();
    await p.getByRole('dialog', { name: 'Photograph 1 of 3' }).waitFor({ state: 'visible' });
    await photoLoaded(p);
    await atTop(p, LIGHTBOX);
  } },
  // The Browse docked panel's photograph. `select` sets `mdPhoto: 0`, so the panel shows
  // `withPhoto[0]` — the street view — and its hit-target is the only "Expand photo: Exterior —
  // street view" button on the Browse screen (the detail grid is not mounted). Over the Leaflet
  // map: this is the state that proves the scrim sits ABOVE the attribution (z-index 1100 > 1000).
  { name: 'browse-panel-lightbox', steps: async (p) => {
    await browse(p);
    await p.getByText('Round Rock').first().click();
    await p.getByText('View full listing').first().waitFor({ state: 'visible' });
    await p.getByRole('button', { name: 'Expand photo: Exterior — street view' }).click();
    await p.getByRole('dialog', { name: 'Photograph 1 of 3' }).waitFor({ state: 'visible' });
    await photoLoaded(p);
    await atTop(p, LIGHTBOX);
  } },
  // One Next: the second photograph (side elevation, 680 x 510) and the counter at 2/3, on both
  // runtimes. "Next photo" is unique on the detail screen (the docked panel is not mounted). The
  // button's hover cannot leak into the capture: `settle()` parks the mouse at (0,0) and the
  // 150 ms opacity transition ends inside its 600 ms. The wrap-around and the keyboard paths are
  // characterised in logic.test.ts, not photographed.
  { name: 'detail-lightbox-next', steps: async (p) => {
    await browse(p);
    await p.getByText('Round Rock').first().click();
    await click(p, 'View full listing');
    await p.getByRole('button', { name: 'Expand photo: Exterior — street view' }).click();
    await p.getByRole('dialog', { name: 'Photograph 1 of 3' }).waitFor({ state: 'visible' });
    await photoLoaded(p);
    await p.getByRole('button', { name: 'Next photo' }).click();
    await p.getByRole('dialog', { name: 'Photograph 2 of 3' }).waitFor({ state: 'visible' });
    await photoLoaded(p);
    await atTop(p, LIGHTBOX);
  } }
```

- [ ] `frontend/tests/reference-baselines.spec.ts` — the `placeholderRings` guard list: `['browse', 'detail', 'interest-modal']` → `['browse', 'detail', 'interest-modal', 'detail-lightbox', 'browse-panel-lightbox', 'detail-lightbox-next']`, with one added comment line: `// A19's three states mount filled slots beneath a 55 % scrim, where a pre-hydration ring would be frozen into the oracle.`
- [ ] `frontend/tests/harness.ts` — correct the comment above `atTop` (lines 192–193): "App.vue has exactly ONE `position: fixed` element" → "App.vue has exactly TWO `position: fixed` elements — the interest modal's overlay (`… z-index: 900 …`) and, since A19, the photo lightbox's scrim (`z-index: 1100`, addressed by `[role="dialog"]`), never mounted in the same state". No code changes; `harness.test.ts` pins nothing about the count.
- [ ] `npx vitest run tests/cross-plan-deltas.test.ts tests/harness.test.ts` — green (the first 28 positions unchanged).

### Step 7 — `LOCAL_AMENDMENTS.md`: twelve rows, and every citation recomputed

A19 inserts 31 template lines above the `<script>` (3 at V3:718, 3 at V3:924, 25 at V3:1678) and 72 inside it; the file goes 3557 → 3660 lines and **every existing `V3:<line>` numbered above V3:717 is stale** — 27 of the 28 existing citations; A14.3's V3:112 alone stands — and the citation case names each one. The offsets, from a simulation of the twelve replacements on the L1 file (verify against the regenerated file — the test is the authority; these are the expected values):

| Row | Old → new |
|---|---|
| A3 | 819 → **822**; 831 → **834** |
| A11 | 831 → **834** |
| A10, A10.2 | 3258 → **3360** |
| A12.1 | 2572 → **2618** |
| A12.2 | 2521 → **2567** |
| A12.3 | 2544 → **2590** |
| A12.4 | 2555 → **2601** |
| A12.5 | 2560 → **2606** |
| A12.6 | 3045 → **3146** |
| A12.7 | 3047 → **3148** |
| A12.8 | 3026 → **3127** |
| A12.9 | 3067 → **3168** |
| A12.10 | 3041 → **3142** |
| A12.11 | 3042 → **3143** |
| A14.1 | 1970 → **2016** |
| A14.3 | 112 — unchanged (above every insertion) |
| A15.1 | 2521 → **2567** |
| A15.2 | 2541 → **2587**; 2543 → **2589** |
| A15.3a | 2539 → **2585** |
| A15.3b | 2546 → **2592**; 2544 → **2590** |
| A15.3c | 2512 → **2558**; 2510 → **2556** |
| A15.3d | 2523 → **2569**; 2522 → **2568** |
| A18.1 | 819 → **822** |
| A18.2 | 895 → **898** |

- [ ] Recompute the 29 citations that move in place (a ±1 miss fails the test by name; a citation is valid only if line n, n−1 or n+1 of the amended file contains a trimmed line of that amendment's output). A3's V3:834 lands because A18.1's anchor is the bare `<img>`: A3's checked output stays `View full listing`, which stands at both L2:822 and L2:834 — the label anchor the proposal had would have made it stale.
- [ ] Append twelve rows after `| A18.2 |`, in apply order. The ruling column is the `ruling` string byte for byte; the ruling cell may not contain a `|`. Citations are against the amended-after-A19 file:

```md
| A19.1 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:1905), the line after the interest modal's own `interest: "closed"` entry in `state`: two state keys beside the interest modal's. `lightbox` is null while closed and `{ pid, at }` — listing id, slot id of the photograph showing — while open; `lightboxFocus` is the one-shot "move focus into the dialog on mount" flag the mount ref spends (the A14 `giveMenuAt` idiom). Closed in every approved state, so no state renders an overlay. |
| A19.2 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:2623–2676 — the block ends on the `marketPanel` line it was anchored to): `openLightbox` (records the opener from `e.currentTarget` — new to the design — and clears the three header menus, not the metro one, which its own closures shut first), `closeLightbox` (clears and returns focus to the opener), `lightboxPhotos()` (the docked panel's own `photoSet(p).filter(hasSrc)`, so A15's extra tiles page and "N of M" equals the carousel's counter), `stepLightbox` (wrap-around, the panel's modulo) and `lightboxVals()` (`open`, `src`, `caption`, `counter`, `label`, `multiple`, `prev`, `next`, `close`, `backdrop` — closes only when `e.target === e.currentTarget` — and `ref`, which stores the dialog element and spends `lightboxFocus` once). Every later-running closure reads `this.state`. |
| A19.3 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:3594): `renderVals()` gains `lightbox: this.lightboxVals()` beside the interest modal's keys, so the root-level block reads `{{ lightbox.open }}` and the rest. |
| A19.4 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:3133): `detail()`'s filled tiles gain `open(e)` and `openLabel` ("Expand photo: " + the photograph's own caption, A15); empty tiles are the design's own objects, untouched. Anchored on the `photos:` line alone, never the `photoHeroId` orphan beneath it. |
| A19.5 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:2707): the docked panel's photos object gains `open(e)` and `openLabel` for the photograph its carousel is showing (`cur`), so the lightbox opens on that one and counts as the panel does. |
| A19.6 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One template literal (V3:925): in each detail tile's 168 px frame, a third `sc-if` on `ph.hasSrc` holding a contentless, transparent, borderless absolute `<button aria-label="{{ ph.openLabel }}">` laid over the `<image-slot>` — the design's icon-button reset plus `inset: 0` — which paints no pixel while closed and never exists on an empty slot (whose click on the reference is the design tool's file chooser). |
| A19.7 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One template literal (V3:719): the same hit-target over the docked panel's current photograph, on a `hasAny` sc-if (the panel's own habit — it gates the pills the same way), placed before the arrows so the prev/next buttons, the pills and the dots keep painting above it and stay clickable. |
| A19.8 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One template literal (V3:1678–1701), the overlay, once, at the root: the interest modal's scrim at `z-index: 1100` — above Leaflet's attribution and controls at 1000 on Browse — closing on a click on itself; a `role="dialog" aria-modal="true" aria-label="Photograph N of M" tabindex="-1"` box with the tile frame's declarations, the modal box's shadow and entrance and `outline: none`; the photograph at natural size bounded to the viewport minus 24 px (V3:1681); the panel's 38 px close button with `close-x-gray.svg` whitened, "Close photo" (V3:1682); the panel's prev/next arrows verbatim, hidden for a single photograph (V3:1687, V3:1690); the panel's counter and caption pills verbatim (V3:1696, V3:1697). Four compositions are asserted as exceptions in the test. |
| A19.9 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:1942): the lightbox branch of the shared `keydown` closure, ahead of A14.5's Give guard — Escape closes and returns focus to the opener, ArrowLeft and ArrowRight step with wrap-around, each preventing the default. Skipped while closed, so A13's and A14's Escape are byte-identical. Its find is A14.5's output. |
| A19.10 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:1955–1964, from the closure's `const out` line): the focus trap at the top of the shared `focusout` closure — focus leaving the dialog for anywhere else is pulled back, honouring `aria-modal`; a null `relatedTarget` is left alone as A14.7 leaves it. Above the `const to` line so the pinned Give and metro text stays contiguous; its find is the closure head as A13.8 left it. |
| A19.11 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:2030): `go()` clears `lightbox` and `lightboxFocus` on the line that already closes the interest modal — a screen change closes it. |
| A19.12 | 2026-09-09 | the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close | One script literal (V3:3350): `signOut`'s reset clears `lightbox` and `lightboxFocus` too, so a session that ends cannot leave the scrim over the gate card. The app's route sync (`frontend/src/router/useStateRouteSync.ts`) is the third leg — Browser Back — because the reference has no router. |
```

- [ ] `npx vitest run tests/design-amendments.test.ts` — the row-order, verbatim-ruling, citation and row-count cases green. The citation case's `checked` reads **48**: the 30 existing citations (28 recomputed or standing, plus A18's two) and the eighteen the twelve new rows carry (a `V3:a–b` range counts once — the regex reads the number after `V3:`). A stale row is named — fix the number, never drop the citation.

### Step 8 — `CLAUDE.md` and the doc pins

- [ ] RED: `poetry run pytest tests/test_docs.py -q -k "amendment or approved_screen or local_amendments"` — three tests selected, **two** failures naming the numbers: the family/entry sentence (`17 families, 118 entries (24 derived + 94 literals)`) and the Layout line (`48` in `screens.ts` since Step 6, `45` here). The row-count pin is already green — Step 7's rows made 95 = 94 + 1.
- [ ] The count sentence: `Sixteen families, 106 entries: A1's 24 derived edits plus 82 literals` → **`Seventeen families, 118 entries: A1's 24 derived edits plus 94 literals`**.
- [ ] The Layout line: `the 45 approved states` → **`the 48 approved states`**.
- [ ] The A19 clause, after the A18 clause and before the count sentence:

> **A19** (John, 2026-09-09 — "the images/photos should be clickable and they expand and have < > to view all images larger with simple X to close"): every photograph a member can see — the detail's filled tiles, A15's extra tiles included, and the Browse docked panel's current photograph — carries a transparent hit-target that opens a lightbox composed from the design's own elements: the interest modal's scrim at `z-index: 1100`, above Leaflet's attribution and controls at 1000 on Browse; a `role="dialog"` box in the tile frame's declarations; the photograph at natural size, never upscaled, bounded to the viewport; the docked panel's 34 px `nav-arrow-white` prev/next pair verbatim, hidden for a single photograph; its 38 px close button with `close-x-gray` whitened, "Close photo"; and its counter and caption pills verbatim — the caption the photograph's own A15 description, "Photo N" where nobody has described it. Twelve literal edits (A19.1–A19.12): the state keys, the five class members (open, close, the photo list the carousel already counts, step with wrap-around, the render values), the render key, the two openers, the two hit-targets on the `hasSrc`/`hasAny` branches only (an empty slot's click on the reference is the design tool's file chooser), the overlay once at the root, the Escape/ArrowLeft/ArrowRight branch in A14.5's shared `key` closure and the Tab trap in A13.8's `out` closure — no new listener — and `go()`/`signOut` clearing it; `frontend/src/router/useStateRouteSync.ts` clears it on Browser Back, the one leg the reference (no router) cannot carry. Focus enters through the mount-ref idiom (A13/A14, review C1), returns to the opener on close; `e.currentTarget` is new to the design. The results-rail thumbnails do not open it (a card click is the selection) and the phone frame has no photograph. Three approved states appended (`detail-lightbox`, `browse-panel-lightbox`, `detail-lightbox-next`), all through Round Rock, the design's own three-photograph fixture; the frozen manifest did not move — the closed lightbox is one unmounted `sc-if` and a button that paints nothing — which is the proof, checked after A18's one-row re-pin.

- [ ] As in L1 Step 5: no `V3:<line>` in either CLAUDE.md clause — sites by name, never by number (CLAUDE.md cites no line anywhere; the rows do, and the test re-checks them).
- [ ] `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100 && poetry run ruff check app tests scripts && poetry run mypy app --strict` — green.

### Step 9 — the oracles, and the manifest that must not move

```bash
cd frontend
lsof -nP -iTCP:5473,5474,5475,8047 -sTCP:LISTEN || true     # nothing
npm run test:visual:baselines     # 48 states from the amended design; `placeholderRings` guarded on six of them
npm run test:e2e                  # visual + DOM oracle + smoke + signin-form + account-flows — `N passed`
```

- [ ] **Green, or STOP.** Read the three new PNGs by eye: the navy scrim covers the whole viewport (on `browse-panel-lightbox`, the Esri attribution and the Leaflet controls are UNDER it — that is the `z-index: 1100` ruling made visible); the photograph at 680 px wide, centred; the white X top-right of the photograph; the two white arrows at mid-height; the "1/3" (or "2/3") pill bottom-right and the caption pill bottom-left. A DOM line here names a real divergence — most likely a bound attribute one runtime emits and the other does not — read the path; never widen tolerance or edit a snapshot by hand.
- [ ] `npx vitest run tests/baseline-manifest.test.ts` — **GREEN, zero moves.** This is A19's acceptance criterion: A18 already moved `detail` and re-pinned it, so any movement here is A19 leaking into a closed state (a painted button, a wrapper that changed layout, a z-index on an always-rendered node). **STOP and diff. Do not re-pin.**
- [ ] `git diff --exit-code -- tests/baseline-manifest.json` — exit 0.
- [ ] The existing `interest-modal` PNG differs from L1's ONLY if a hit-target painted: `cmp` it against L1's copy (keep one before regenerating: `cp tests/visual.spec.ts-snapshots/interest-modal-darwin.png /tmp/…` is fine here — it is a git-ignored artefact) — identical bytes is the direct proof that an empty `<button style="position: absolute; inset: 0; padding: 0; border: 0; background: none">` paints nothing under the 55 % scrim. Record the result in the commit message.

### Step 10 — the two things only a browser can settle

- [ ] **The focus trap (A19.10).** On the app (`http://localhost:5473`, signed in as the buyer persona) and on the reference (`http://localhost:5474/?props=…` for `browse`): open a Round Rock photograph, press Tab repeatedly. Focus must cycle X → Previous photo → Next photo → (the dialog container) → X and never reach the page behind; Shift+Tab likewise. If Chromium drops a synchronous `focus()` inside the capture-phase `focusout` on either target, the fallback is the design's own `setTimeout` idiom (`this._t = setTimeout(…)`, 2 uses) at 0 ms — a change to A19.10's `replace` (one line: `if (…) setTimeout(() => box.focus(), 0);`), re-run `gen:design` + re-port + `gen:app`, and a note in the row. Do not accept a trap that only works on one target.
- [ ] **The reference's pre-hydration fetch.** A19.8's `<img src="{{ lightbox.src }}">` is the first raw `<img>` with a dynamic `src` in the design, so the reference requests `%7B%7B%20lightbox.src%20%7D%7D` once at load, before `support.js` compiles the template. `prepare()`'s route `/%7B%7B|\.image-slots\.state\.json$/` answers it with a blank GIF; confirm no console error surfaced in the `reference` project's run (a 404 there would have failed every state), and that the app issues no such request (Vue compiles the binding; `<template v-if>` mounts the `<img>` only with a real `src`).
- [ ] **Keyboard and mouse on the app:** Escape closes and focus is back on the tile; `<`/`>` step and wrap; the backdrop closes; a click on the photograph does nothing; Browser Back from an open lightbox lands on Browse with no scrim; the docked panel's photograph opens on the one the carousel shows.

### Step 11 — commit 3

**One commit for A19, not two.** `CLAUDE.md` is one file and carries both the count sentence and the Layout line's `48` (Step 8), and `tests/test_docs.py::test_claude_md_approved_screen_count_matches_screens_ts` compares that line with `screens.ts` on the same tree — a commit that carried `CLAUDE.md` without `screens.ts` would be a tree on which the backend suite is red (`48` against `45`). So the three oracle files travel with the family, and both suites are green at each of the branch's **three** commits: commit 1 (`Sixteen families, 106 entries`; 45 states in `screens.ts`, `45` in CLAUDE.md), commit 2 (the one-row re-pin), commit 3 (`Seventeen families, 118 entries`, 95 rows; 48 and `48`; the manifest unchanged).

```
feat(design): A19 — every photograph opens a lightbox with < > and X

The detail's filled photo tiles (A15's extras included) and the Browse
docked panel's current photograph carry a transparent hit-target that
opens an enlarged view: the interest modal's scrim at z-index 1100 (above
Leaflet's attribution on Browse), the panel's own prev/next arrows and
close button, its counter and caption pills, the photograph at natural
size bounded to the viewport. Escape/ArrowLeft/ArrowRight in the shared
key closure, Tab trapped in the shared focusout closure, focus in through
the mount ref and back to the opener on close; go(), signOut and the app's
route sync (Browser Back) close it.

Twelve ruled amendments (A19.1–A19.12) on the approved design, regenerated
from the pristine bundle; logic.js re-ported, App.vue regenerated. One
app-side edit (useStateRouteSync.ts) for the leg the reference cannot
carry. Every V3:<line> citation recomputed against the regenerated design.
Seventeen families, 118 entries, 95 rows.

Three approved states appended — detail-lightbox, browse-panel-lightbox,
detail-lightbox-next; the 48 approved states — each through Round Rock's
three design-shipped photographs, waiting for the enlarged image to decode
and pinned at the top as interest-modal is; added to placeholderRings. The
manifest test is green with no change to baseline-manifest.json: the
closed lightbox moved no approved pixel. interest-modal's PNG is
byte-identical to the A18 run's.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

Files: `frontend/tests/design-amendments.ts`, `frontend/tests/design-amendments.test.ts`, `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html`, `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`, `frontend/src/logic.test.ts`, `frontend/src/router/useStateRouteSync.ts`, `frontend/src/router/useStateRouteSync.test.ts`, `frontend/tests/screens.ts`, `frontend/tests/reference-baselines.spec.ts`, `frontend/tests/harness.ts` (the comment), `CLAUDE.md` (the A19 clause, the count sentence and the Layout line together).

---

### Task L3: docs, QA click-through, hand-back

### Step 1 — the documents

- [ ] `DEPLOY.md` — no edit expected. Verify: `grep -n "45 approved\|Fifteen families\|lightbox" DEPLOY.md` → nothing. Its "click through the changed flow" line is generic and stays.
- [ ] `CLAUDE.md` — done in L1 Step 5/7 and L2 Step 8. Re-run `poetry run pytest tests/test_docs.py -q` one last time on the final tree.
- [ ] This plan — append the controller's record at hand-back (commits, counts, what moved), in the style of the metro and Give plans' closing records.
- [ ] `tests/test_docs.py::test_relative_markdown_links_resolve` covers this plan once committed: every relative link here resolves from `docs/superpowers/plans/`.

### Step 2 — the release note (for John and the controller)

The version is **not** bumped in this branch. `frontend/package.json` and `pyproject.toml` move in lockstep (`tests/test_versions.py`), one patch per release, in the release commit only — and the next free patch is decided in **merge order** against the queued branches (John's 2026-09-09 release order: Census → sign-ups → dropdowns → seller). If this branch lands before the seller branch it takes **0.1.10**; otherwise the next free number. The controller performs the bump, the production deploy and `scripts/verify-deploy.sh production`.

### Step 3 — the QA click-through (controller, after `scripts/deploy.sh QA .worktrees/feat-photo-lightbox`)

`railway status` must read **Project: Practice Match** first; `deploy.sh` enforces it and SOURCE_DIR is mandatory for a worktree (P14). Then on https://qa.foundation.vin, signed in as a buyer:

1. **A18.1** — Browse, click any result card: the docked panel's Insights tab shows "View full listing" with the arrow pointing **right**, toward the listing.
2. **A18.2** — click it: the detail's "Back to results" arrow points **left**; it works.
3. **A19, open** — on a seeded hospital with **7+ photographs** (the tiles beyond six, captioned "Photo N" where nobody has described them, are the point): click any filled tile; the lightbox opens on that photograph, the caption pill shows its own description, the counter shows "N/M" with M = every photograph the grid shows, the dialog's accessible name is "Photograph N of M". A large photograph is bounded to the viewport and never upscaled.
4. **`<` / `>`** — page through all M, including the extras; past the last wraps to the first and before the first to the last; the counter follows.
5. **X** — closes; focus is back on the tile that opened it (Tab moves to the next tile).
6. **Escape** — reopen, press Escape: closes, focus back on the tile.
7. **Backdrop** — reopen, click the navy area: closes. Click the photograph: nothing.
8. **Keyboard** — Tab to a tile, Enter: opens; ArrowRight/ArrowLeft step; Tab cycles X → Previous → Next → the dialog and never reaches the page; Escape closes.
9. **Docked panel** — Browse, select the same hospital, step the carousel to its third photograph, click the photograph: the lightbox opens on the third (counter "3/M"); the Esri attribution is under the scrim while it is open and back when it closes.
10. **Browser Back** with the lightbox open: the previous screen, no scrim.
11. **Single photograph** — a hospital with exactly one: the lightbox opens with no arrows.
12. **Screenshots for the hand-back:** the two arrows; the open lightbox on the detail; the open lightbox over the Browse map; one "Photo N" extra tile enlarged.

### Step 4 — the hand-back

Forwardable plain-language summary (two rulings, what changed, what a member sees), the screenshots above, and a one-line engineer's note naming the risks: `e.currentTarget` is new to the design and rests on both runtimes' event semantics; the focus trap's synchronous `focus()` was verified in Chromium on both targets (or the `setTimeout` fallback was taken — say which); the lightbox does not lock body scroll (D-A19); the two other arrow sites await John's word (D-A18).

---

## The gate, then QA

All four, in order (CLAUDE.md § Non-negotiables), on the final tree of the worktree:

1. - [ ] `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100` · `poetry run ruff check app tests scripts && poetry run mypy app --strict`
   - [ ] `cd frontend && npm run typecheck && npm test && npm run build`
2. - [ ] `cd frontend && npm run test:visual:baselines && npm run test:e2e` — visual + DOM oracle + smoke, green (48 states); `npx vitest run tests/baseline-manifest.test.ts` green against the L1 re-pin.
3. - [ ] Controller: `railway status` → **Project: Practice Match**; `scripts/deploy.sh QA .worktrees/feat-photo-lightbox`; the click-through in L3 Step 3.
4. - [ ] Controller, after merge and the lockstep bump: `scripts/deploy.sh production && scripts/verify-deploy.sh production`. Production runs `SITE_MODE=coming_soon` until launch, so the change is not publicly visible there; the smoke is still required and the hand-back says so.

---

## Parity-risk checklist (A19) — each one is either designed around or verified in Step 10

- **The setState-callback trap (A14 review C1).** `dc-logic.js` runs a `setState` callback synchronously before Vue renders; `support.js` runs it after React commits. Focusing the dialog or the opener from a callback would work on the reference and do nothing on the app. Designed around: the mount ref spends `lightboxFocus`; `closeLightbox` focuses the still-mounted opener directly. Asserted: the amended file contains no `}, () => this.closeLightbox(` / `}, () => el.focus(`.
- **State identity differs.** The reference REPLACES `this.logic.state` on every `setState` (`{ …prev, …patch }`); the app mutates a reactive object in place. Every closure that runs later — the ref, the `key`/`out` branches, `stepLightbox` — reads `this.state`, never a `const s` captured at render time. (Both runtimes update `this.state` synchronously, so `back.focus()` inside `closeLightbox` sees `lightbox === null` in the `focusout` it causes, and the trap does not fight the focus return.)
- **Function refs re-fire on every render on BOTH runtimes** (`renderVals` mints a new function each pass → old(null), new(el)). Without the one-shot flag, pressing Next would re-focus the container and pull the keyboard user off the arrow. Characterised.
- **`e.currentTarget` is NEW.** On the reference it is a React 18 synthetic event, valid only during dispatch — `openLightbox` reads it synchronously before `setState` (it does); on the app it is the native event and `currentTarget` is the listener's element. Both runtimes pass the event as the handler's first argument (the design's `toggleSave` calls `e.stopPropagation()`).
- **The dynamic `src` is not rewritten by `convert-dc`** (it rewrites STATIC `assets/` attributes only). It works because `logic.js`'s port rewrites `"assets/` → `"/assets/` inside the `SRC` map and `load.ts` sends absolute API URLs for seeded photographs; `dom.ts` Rule B normalises the reference's `assets/` attribute. The new static icon `src`s are rewritten as every other icon is.
- **Image load timing.** The dialog's `<img>` starts loading only when mounted; `settle()`'s 600 ms is not a proof. Every state waits for `complete && naturalWidth > 0`. Same bytes, same Chromium → identical decode on both targets.
- **A fixed overlay in a fullPage capture** is composited at the offset it paints at, so a page scrolled by Playwright's scroll-into-view before the tile click shifts the whole overlay (the `interest-modal` failure `atTop` was written for). Every lightbox state ends with `atTop(p, LIGHTBOX)`.
- **`:focus-visible`.** Chromium does not apply it to programmatic focus that follows a mouse click, and the container carries `outline: none`, so no ring can differ between captures; keyboard users still get the UA ring on the X and the arrows. Both targets are the same Chromium.
- **The focus trap's synchronous `focus()` inside a capture-phase `focusout`** is browser-sensitive → Step 10, both targets, `setTimeout` 0 fallback named.
- **The reference-only file chooser.** `image-slot.js:571` opens a hidden `<input type=file>` on a click on an EMPTY slot (not gated on `data-editable`); the app's `ImageSlot.vue` has no input. The hit-target exists ONLY on the `hasSrc`/`hasAny` branches, so an empty slot's behaviour is unchanged on both targets and a filled slot's click never reaches the shadow root. On the reference prototype the hit-target also masks the editor's drag-drop replacement on FILLED tiles — a change to a prototype-editing affordance the app never had (John's 2026-09-05 ruling removed the editor).
- **The reference's pre-hydration fetch** of `{{ lightbox.src }}` → Step 10; covered by `prepare()`'s existing `%7B%7B` route, which must stay in place.
- **`hint-placeholder-val`.** The pristine file has zero hint-less `sc-if`s; every A19 `sc-if` carries `hint-placeholder-val="{{ false }}"` (asserted).
- **The design's interest modal has no focus trap**, so the three new buttons under `interest-modal`'s scrim are Tab-reachable behind it — a pre-existing class of defect the modal shares with every other control on that page, now with three more instances; recorded, not fixed here (Q7 below).
- **`e.preventDefault` on the arrows** keeps the page behind from scrolling; the `pointerdown` closure is untouched, so with every menu shut it returns early while the lightbox is open.

---

## Open questions for John — one line each, with the controller's default applied

**D-A18 — the two other arrows** (default: **unchanged until ruled**; neither is in A18):

- **D-A18.1** — the desktop account menu's "Sign out" row (V3:140) carries the same glyph unrotated, pointing LEFT before the label. Is a left-pointing arrow on Sign out intended, or should it face right like a conventional sign-out glyph? No approved state opens this menu, so flipping it moves no baseline and no frozen row — but it is not one of the two screenshots. **Default: unchanged.**
- **D-A18.2** — the phone frame's initials pill (V3:1434) carries the same LEFT-pointing arrow after the initials and is wired straight to `signOut`. Should it flip with the desktop one, and is the immediate sign-out on tap intended? Flipping it moves the frozen `mobile-list` and `mobile-detail` rows plus the `mobile-map`/`mobile-sheet` baselines, so it needs an explicit ruling. **Default: unchanged.**
- Confirmed not in scope, no question: the docked panel's prev/next pair (V3:721/724) renders correctly; the `move-arrow.svg` beside "per 10k households" (V3:784) is a metric pictogram, not navigation.

**D-A19 — the lightbox's composition** (each default applied in this plan):

- **Q1** Caption pill (the photograph's own A15 description, "Photo N" fallback) and counter pill ("N/M") shown inside the enlarged photograph, bottom-left and bottom-right as on the panel — **default: both shown**; the dialog's accessible name "Photograph N of M" is independent of them.
- **Q2** A click on the navy scrim closes (the interest modal closes only by its X) — **default: closes**. The scrim colour is the design's own `rgba(0,58,112,.55)`; a darker photo-viewer black is NOT proposed (absent beats faked).
- **Q3** `<` past the first photograph and `>` past the last wrap around (the panel's own modulo) — **default: wrap-around**.
- **Q4** Body scroll behind the scrim is not locked (the design has no such idiom; the interest modal does not lock) — **default: not locked**.
- **Q5** The third state `detail-lightbox-next` (the second photograph after one Next) — **default: included**, so stepping is photographed and serialised, not only characterised.
- **Q6** Swipe/touch gestures, pinch-zoom, Home/End and a live-region announcement — **default: not included**; the dialog's label changes on step, which most assistive technology re-announces.
- **Q7** The hit-target buttons are focusable behind the interest modal's scrim on `interest-modal` (the modal has no trap of its own — a pre-existing class of defect) — **default: recorded, not fixed here**; a modal focus trap for the interest modal is a separate ruling.
- **Q8** The X is the docked panel's 38 px "Close panel" button with `close-x-gray.svg` whitened at the photograph's top-right corner (vs the interest modal's small 30 px bordered square with `delete-x`) — **default: the panel's button**, because the arrows beside it are the panel's too.
- **Q9** Image size: natural, never upscaled, bounded to the viewport minus 24 px (Round Rock's three are 680 px wide → about four times the tile) — **default: natural**; "fill the viewport width" is the alternative.
- **Q10** Label copy: "Expand photo: <caption>", "Photograph N of M", "Close photo" — **default: as written**; they are literals in A19.2/A19.4/A19.5/A19.8.

---

**Controller record (2026-09-09, at plan time).** Rulings 1–10 above are the controller's defaults, queued for John's veto with the hand-back; D-A18.1/D-A18.2 are open and default to "unchanged". A16/A17 remain the seller branch's. Family ids A18/A19, the sequencing (A18 alone → `detail` re-pinned → A19 with zero moves), the surfaces (detail tiles incl. A15's extras + the docked panel's photograph; not the rail; no mobile surface), the composition (scrim at 1100, the panel's arrows/X/pills verbatim, natural size bounded to the viewport, wrap-around, backdrop closes, `hint-placeholder-val` on every `sc-if`, dialog role/`aria-modal`/label, `tabindex="-1"`, `outline: none`, mount-ref focus, focus return, Tab trap with the `setTimeout` 0 fallback, Escape/Arrows in the shared `key` closure after A14.5, the trap in the shared `out` closure after A13.8, no `marketMenu` site, the three header menus cleared on open, `go()`/route sync/`signOut` clearing, no scroll lock, `e.currentTarget` recorded as new, A19.4 anchored on the `photos:` line alone, hit-targets on `hasSrc`/`hasAny` only), the three appended states with the image-decode wait and `atTop`, `placeholderRings`, the `%7B%7B` route dependency, the full gate set on the worktree env above, no icon byte-identity pin, and the release note (controller's bump, lockstep, merge order) are as ruled in the understand workflow and are not the implementer's to vary. Any deviation STOPS and comes back as a controller amendment.
