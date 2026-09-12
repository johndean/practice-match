import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AMENDED, AMENDED_JSX, type Amendment, LOCAL_AMENDMENTS_MD, PRISTINE, PRISTINE_JSX, amendments, amendmentsFor, applyAmendments, deriveTypographyB, templateRegions, V2 } from './design-amendments';

describe('local design amendments (spec D15)', () => {
  const pristine = readFileSync(PRISTINE, 'utf8');
  // D15 makes the pristine copy the authority every amendment is measured from, so it needs an
  // oracle of its own: without one, a consistent edit to BOTH the pristine file and the amended
  // file keeps every other case green while "pristine, never edited" quietly stops being true.
  // This hash changes only when a re-issued bundle lands (and then the amendments retire with it).
  it('the pristine Rev 2 copy is the bundle\'s file, untouched', () => {
    expect(createHash('sha256').update(readFileSync(PRISTINE)).digest('hex')).toBe('335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d');
  });

  // The bundle's SECOND amendable file (spec §9.2, ruled by the controller 2026-09-10 §14 Q3).
  // A24 is the family that first needed a file other than the `.dc.html` (A28.1 reached it
  // first, by merging first), and the alternative — hand-editing an approved bundle file — is the exact
  // failure mode spec D15 exists to remove. Same contract, same proof: a frozen pristine twin
  // that is never edited, and byte equality with the amended file it plus its own amendments
  // produce. This hash changes only when a re-issued bundle lands.
  it('the pristine MarketMapV3 copy is the bundle\'s file, untouched', () => {
    expect(createHash('sha256').update(readFileSync(PRISTINE_JSX)).digest('hex')).toBe('662e4105fd258b6380f1f66f6289629d999aa657b8dc5a4d1303be88e26c0adc');
  });

  it('the amended MarketMapV3.jsx is the pristine copy plus exactly the ruled edits', () => {
    expect(applyAmendments(readFileSync(PRISTINE_JSX, 'utf8'), amendmentsFor('jsx'))).toBe(readFileSync(AMENDED_JSX, 'utf8'));
  });

  // The partition itself, both ways: every entry lands in exactly one file's list, an entry with
  // no `file` is a `.dc.html` entry (which is what leaves all 182 pre-A24 entries — the 24 A1
  // derives plus the 158 literal consts — unchanged), and
  // the two partitions reassemble into the whole list in the original order.
  it('amendmentsFor partitions the list by file, defaulting to the .dc.html', () => {
    const all = amendments();
    const dc = amendmentsFor('dc');
    const jsx = amendmentsFor('jsx');
    expect(dc.length + jsx.length, 'an amendment landed in neither partition, or in both').toBe(all.length);
    expect(dc.every((a) => (a.file ?? 'dc') === 'dc')).toBe(true);
    expect(jsx.every((a) => a.file === 'jsx')).toBe(true);
    expect(dc.map((a) => a.id)).toEqual(all.filter((a) => a.file === undefined || a.file === 'dc').map((a) => a.id));
    expect(all.filter((a) => a.file === undefined).length, 'every pre-A24 entry declares no file at all').toBeGreaterThan(150);
  });
  // The 24 elements V2 typed differently from V3 (measured in the V13 STOP reports and Step 5, 2026-09-07): 22 display headings, the
  // key-fact values `{{ m.v }}` (V2 set them uppercase .005em — one element in the template) and the 28 px mobile asking price
  // `{{ d.priceLabel }}` (V2: uppercase .005em; the 34 px desktop price is styled like V3 already). `{{ resultHeadline }}` is NOT among them:
  // V3's only occurrence is the mobile list's, byte-identical to V2's (the V7 review had paired it with V2's desktop Browse element).
  const A1_TEXTS = [
    'Veterinary Practice Transitions', "We're here to help connect veterinary practice owners", 'Member Sign In', 'Request Access',
    '{{ status.title }}', 'New to ownership? Start with the StartUp Club.', '{{ md.mdHeadline }}', '{{ d.title }}', '{{ sec.title }}',
    'Photos and Documents', 'Community Context', '{{ m.v }}', '{{ modal.title }}', 'My Requests', 'No requests yet', '{{ seller.heading }}',
    'My Listings', 'Buyer Interest', '{{ wiz.title }}', '{{ wiz.previewTitle }}', 'Your listing is with the VIN Foundation',
    'VIN Foundation Admin', '{{ d.priceLabel }}',
  ];
  it('A1 derives exactly the 24 V2-typography edits — value changes only, in place, none inside a script', () => {
    const a1 = deriveTypographyB(readFileSync(V2, 'utf8'), pristine);
    expect(a1).toHaveLength(24);
    expect(a1.filter((a) => a.text === '{{ d.priceLabel }}').map((a) => /font-size:\s*(\d+)px/.exec(a.find)?.[1])).toEqual(['28']);
    // `{{ d.title }}` occurs twice (34 px detail title, 19 px mobile title) — the key is (tag, text, size), so each pairs with its own V2 counterpart; the text list has one entry per distinct text.
    expect(new Set(a1.map((a) => a.text!.startsWith("We're here") ? "We're here to help connect veterinary practice owners" : a.text!))).toEqual(new Set(A1_TEXTS));
    for (const a of a1) {
      expect(a.replace, a.text).toContain('text-transform: uppercase');
      expect(a.replace, a.text).toMatch(/letter-spacing: \.0(2|05)em/);
      // M6 (re-review): this was `find.length - replace.length <= 0`, which only forbade the
      // replacement SHRINKING — it would have passed a `replace` that rewrote a colour or a font
      // size on the same tag, provided the string grew. Assert the real property instead: strip
      // the two declarations A1 is allowed to touch from both styles and everything left, plus
      // every byte outside the style attribute, must be identical.
      expect(withoutTypography(a.replace), `${a.text}: A1 changed something other than text-transform/letter-spacing`)
        .toBe(withoutTypography(a.find));
    }
    // The two elements the ruling leaves alone: `{{ c.value }}` is V3-only (no V2 counterpart, spec
    // D6) and `{{ resultHeadline }}` already equals V2's (V3's only occurrence is the mobile list's).
    for (const a of a1) {
      expect(a.text).not.toBe('{{ c.value }}');
      expect(a.text).not.toBe('{{ resultHeadline }}');
    }
    // "none inside a script", asserted rather than asserted-in-the-title: every `find` starts inside
    // one of the template regions — the spans OUTSIDE <script>/<style> — and ends before that region does.
    const regions = templateRegions(pristine);
    for (const a of a1) {
      const at = pristine.indexOf(a.find);
      expect(at, `${a.text}: find not present in the pristine file`).toBeGreaterThanOrEqual(0);
      expect(regions.some(([s, e]) => at >= s && at + a.find.length <= e), `${a.text}: find is not inside a template region`).toBe(true);
    }
  });
  // ---------------------------------------------------------------------------------------
  // The SET, pinned both ways (A-I8). Until I8 there was no explicit count or id list
  // anywhere: the only set-level guard was `LOCAL_AMENDMENTS.md`'s row equality below, which
  // compares the code against the doc and is therefore satisfied by editing both. This is
  // the third point of reference — a literal list in the test file — so adding, dropping or
  // renaming an amendment is a deliberate three-file change, and the ORDER is pinned too
  // (A2.5 matches A2.4's output, so the list may never be reordered).
  // ---------------------------------------------------------------------------------------
  const AMENDMENT_IDS = [
    ...Array.from({ length: 24 }, (_, i) => `A1.${i + 1}`),
    'A2', 'A2.2', 'A2.3', 'A2.4', 'A2.5', 'A3', 'A4',
    // A-I8 (Task I8a): sign-in and sign-out through the `auth` adapter, the account-on-load
    // bootstrap, and the two prototype props that let the reference reach a gate state and render
    // the same account the app does.
    'A5.1', 'A5.3a', 'A5.3b', 'A5.4', 'A5.6', 'A5.7',
    // A6 — CLAUDE.md's launch-removal list, executed against the design; A7 — the sign-in copy.
    'A6.1', 'A6.2', 'A6.3a', 'A6.3b', 'A6.3c', 'A6.4a', 'A6.4b', 'A6.4c', 'A6.4d', 'A6.5', 'A6.6a', 'A6.6b',
    'A7.1', 'A7.2',
    // A-S4 (Task S4): the two ruled touches to the sign-in card, then the account screens —
    // composed from the gate card's own elements. A ruling that needed more than one literal
    // edit carries a letter suffix, exactly as A5.3a/A6.3a/A6.4a do.
    'A7.3', 'A7.4',
    'A8.1a', 'A8.1b', 'A8.1c', 'A8.2', 'A8.3a', 'A8.3b', 'A8.4a', 'A8.4b', 'A8.5', 'A8.6', 'A8.7', 'A8.8a', 'A8.8b',
    // A-S5 (Task S5): the one seam the oracle could not close from outside the design — the
    // applicant-answer card's note, which only `applicationsMe()` fed and the reference never
    // calls. One more declared prototype prop, exactly as A8.8b did for the sign-in notices.
    'A9.1a', 'A9.1b',
    // A10 — the sign-in card's second gate point (John, 2026-09-08). Ruled on `main` while A8/A9
    // were reserved by this branch; the merge puts all three families in one list, A10 last
    // because A10.2's `find` is A10's output.
    'A10',
    // A11 — unifies the docked panel's other-tabs CTA with the Insights tab's (John, 2026-09-08).
    'A11',
    // A10.2 — John revised A10's wording later the same day; A10 stays as the record of the
    // first ruling and A10.2 applies after it.
    'A10.2',
    // A12 — the Seed Listings launch (John, 2026-09-08). Five literal script edits so the design
    // reads a listing's own name and photographs; the fixtures carry neither key, so every
    // approved state keeps its pixels.
    'A12.1', 'A12.2', 'A12.3', 'A12.4', 'A12.5',
    // A12.6/A12.7 (L6 ruling, 2026-09-08): the two member accesses on the four community
    // figures D4 leaves null — `renderVals()` computes `detail()` on every render, so an
    // unguarded null was a blank app, not a blank card.
    'A12.6', 'A12.7',
    // A12.8–A12.11 (final review C1/I1, ruled A-L8): the detail names the listing's own state
    // through the design's `stateOf` helper, and Community Context reaches the design's own
    // "Community data unavailable" card when D4 leaves the four figures null.
    'A12.8', 'A12.9', 'A12.10', 'A12.11',
    // A13 — the metro selector becomes the design's own listbox (John, 2026-09-08). Five literal
    // edits: the `setMarket` class property beside `setF`, the render values that drive the menu,
    // the trigger-and-listbox markup, and the two lifecycle hooks that add and remove the Escape
    // and outside-click listeners the design has never had. (A13.6–A13.8 follow, below and last.)
    'A13.1', 'A13.2', 'A13.3', 'A13.4', 'A13.5',
    // A13.6/A13.7 (review round 1, I2 — ruled): the two render-value orphans the <select> left,
    // deleted under the bundle's own dead-code rule exactly as A2.2–A2.5 deleted the browseSel
    // ones — `market:` (whose only reader was `<select value="{{ market }}">`) and the option
    // rows' `v: m` (the `<option value>` a role="option" button does not have).
    'A13.6', 'A13.7',
    // A14 — the header's Give button IS vinfoundation.org's Give dropdown (John, 2026-09-08),
    // measured on the live site rather than composed from this design's tokens. Six literal
    // edits here: the focus helper, the renderVals keys, the markup, the two Give branches inside
    // A13's shared `trackMenuDismiss` closures, and the `@font-face` that self-hosts the live
    // site's Montserrat 600 — scoped to this control alone, which is John's ruling. (A14.7 and
    // A14.8 follow.)
    'A14.1', 'A14.2', 'A14.3', 'A14.4', 'A14.5', 'A14.6',
    // A14.7 (review round 1, m2 — ruled): Tab out of the open menu closes it, the third
    // dismissal beside A14.4's outside-click and A14.5's Escape, registered and torn down
    // in A13.4's own `trackMenuDismiss`.
    'A14.7',
    // A14.8 (final whole-branch review, m7 — ruled): the last toggle no other amendment touches,
    // so "opening me closes you" holds in every direction between the three header menus and the
    // metro listbox rather than only outward from Give.
    'A14.8',
    // A13.8 (final whole-branch review, m4 — ruled): Tab out of the metro listbox closes it, on
    // the reasoning A14.7 was accepted on. LAST in the list, and the one A13 entry that applies
    // after A14's: the `out` closure it edits is A14.7's own.
    'A13.8',
    // A15 — every uploaded photograph renders, with its own description (A-L11, John 2026-09-09).
    // Six literal script edits: a photograph's own `photoCaptions[i]` wins over the design's
    // fixed slot caption (A15.1/A15.2) and every photograph past the sixth gets a tile of its
    // own (A15.3a–A15.3d, the two ends of each branch's `return`). The fixtures carry no
    // `photos` and no `photoCaptions` at all, so both guards are falsey and A15 moves no
    // approved state.
    'A15.1', 'A15.2', 'A15.3a', 'A15.3b', 'A15.3c', 'A15.3d',
    // A16 — the seller wizard and dashboard read and write the real API (spec D23, controller
    // amendments A-SL17/A-SL20/A-SL22). A13 and A14 were the dropdown branch's, reserved while
    // this branch was built; the family id is derived from the tree at branch time (A-SL4), never
    // typed from the plan, which is why this one is 16. Merged after A13/A14/A15 at SL9 (A-SL34
    // (3)): A16/A17 land here, between A15 and A18/A19, in id order.
    'A16.1', 'A16.2', 'A16.3', 'A16.4', 'A16.5', 'A16.6', 'A16.7', 'A16.8', 'A16.9', 'A16.10',
    // A16.11a/b — the eighth declared prototype prop, `startMyListings`: A-SL17's empty
    // dashboard is a state the design's fixtures cannot express, and this is the mechanism
    // A8.8b and A9.1a established for exactly that.
    'A16.11a', 'A16.11b',
    // A16.12/A16.13 — the preview tells the truth about the draft behind it (A-SL22 (4)): the
    // photograph count stops counting documents, and the location names the listing's own state
    // rather than Texas (A12.8's ruled edit, in the one place the wizard repeats it).
    'A16.12', 'A16.13',
    // A16.14/A16.15 (A-SL23 (1) and (3), the SL7 review's Critical-1/Major-1 and Major-2): the
    // wizard's two doors. "Create a listing" creates one — and, in the same `setState`, stops
    // carrying the LAST listing's `editingId` into it — and "Save and exit" saves the step it is
    // on before it exits, which is what its own label has always promised.
    'A16.14', 'A16.15',
    // A16.16/A16.17 (A-SL25 (1), (3) and (5), the re-review's Critical-A, Major-A, Major-B and
    // Minor-B): `wizAssets` and `creating` declared in the design's own state literal, and the two
    // helpers every adapter path shares — `openDraft`, the ONE place a draft becomes the wizard's
    // state, and `reloadListings`, the one loader, which carries the rejection arm its callers
    // kept forgetting.
    'A16.16', 'A16.17',
    // A16.18 (A-SL27 (3), the round-3 re-review's MAJOR-E): the step rail saves the step it leaves
    // before it moves — in the adapter's partial mode, through Continue's own rejection arm — so
    // the one navigation control that silently discarded typed work under "Saved automatically"
    // no longer does. A16.15 was revised in the same round to save in that partial mode (MAJOR-D).
    'A16.18',
    // A16.19 (A-SL29 (1), the round-4 re-review's MAJOR-F): the wizard's Back button saves the step
    // it leaves before it moves — A16.18's own shape on the other navigation control, which round
    // 3's "the ONE navigation control that silently discards work" missed by one.
    'A16.19',
    // A16.20a/A16.20b (A-SL30 (3), on the round-5 re-review's Info-15): the two remaining doors out
    // of the wizard also save the step it is on — the header nav (`go`), the rail/Back's own shape,
    // and Sign out, which ATTEMPTS the same save and ends the session regardless of the answer,
    // because a session end is the seller's own explicit act and must never be held hostage to one.
    'A16.20a', 'A16.20b',
    // A16.21/A16.22 (A-SL25 (10), SL7b): the step-6 tile re-describes an EXISTING photograph,
    // seeded ones included, by clicking it — one script literal (the tile's own `describe`,
    // photographs only, routed by source through the adapter's overloaded `describe`) and one
    // template literal (the one `onClick` the script literal needs).
    'A16.21', 'A16.22',
    // A17 — Admin › Listings reads the real table (Task SL8; D24 and John's standing rule:
    // "every Admin tab must show real database data, never dummy rows"). A17.1 is A16.1's own
    // shape applied to the review queue; A17.2 is A16.9's, one line after A16.11b's.
    'A17.1', 'A17.2',
    // A18 — the two backwards arrows (John, 2026-09-09: "the arrow icons are backwards on each
    // location, reverse each"). Two template literals using the design's own flip idiom
    // (V3:724): the Insights-tab CTA's arrow turns right, the detail's Back-to-results arrow
    // turns left. Both finds are unique in the pristine file (A18.1 anchors on the bare <img>,
    // never on A3's label — the citation chase); the family is appended last, as every family is.
    'A18.1', 'A18.2',
    // A19 — the photo lightbox (John, 2026-09-09). Twelve literal edits: the state keys, the
    // five class members, the render key, the two openers (detail tiles and the docked panel's
    // photograph), the two hit-targets, the overlay block at the root, the Escape/Arrow/Tab
    // branch in A14.5's shared `key` closure and a comment (A-LB3: a focus trap was tried and
    // retracted here) in A13.8's `out` closure, and the two screen changes the design owns
    // (`go()`, `signOut`) clearing it. A19.9 and A19.10 read A14.5's and A13.8's output, so the
    // whole family is appended last — after A16/A17 too: A19.11 was adapted at the SL9 merge to
    // match `go()`'s shape once A16.20a has already split it (see the amendment's own comment).
    'A19.1', 'A19.2', 'A19.3', 'A19.4', 'A19.5', 'A19.6', 'A19.7', 'A19.8', 'A19.9', 'A19.10', 'A19.11', 'A19.12',
    // A21 — the Browse map's veterinarian and economic layers read real API data without
    // rendering missing data as zero (controller amendment A-C28, 2026-09-10, controller amendment
    // A-C29, 2026-09-10). A21.1 removes the `|| 0` defaults so missing census figures become
    // undefined in communities(); A21.1b completes the fix at the assembly point, skipping entries
    // in marketVals when the raw value is null/undefined so they never reach the renderer. A21.2b-e
    // fix the docked panel's derivative values when figures are missing. A21.2f-h complete the fix
    // at the READERS: compPer10k guards .toFixed(), score/scoreLabel omit when inputs missing.
    // A21.2i-l complete the fix at RENDERING: c.pets, compLevel, score, scoreRing omit undefined.
    // A21.3a/b/c/d remove hardcoded years from four places (VALUE_LAYERS label, LAYER_META
    // sub-line, Data Layers card row, and the detail Growth row), making the vintage-dependent
    // display match the data.
    'A21.1', 'A21.1b', 'A21.2b', 'A21.2c', 'A21.2d', 'A21.2e', 'A21.2f', 'A21.2g', 'A21.2h', 'A21.3a', 'A21.3b', 'A21.3c', 'A21.3d', 'A21.2i', 'A21.2j', 'A21.2k', 'A21.2l',
    // Task B10 (D-C31/D-C32, 2026-09-10): A21.1c is the root cause — `communities()` zeroed every
    // absent figure, so every guard above was satisfied by a 0. A21.2m-p omit the bars and the
    // strip-card median drawn from those zeros; A21.4a-d put the design's own "Community data
    // unavailable" card on the docked panel; A21.5a-d name the area the figures describe.
    'A21.1c', 'A21.2m', 'A21.2n', 'A21.2o', 'A21.2p', 'A21.4a', 'A21.4b', 'A21.4c', 'A21.4d', 'A21.5a', 'A21.5b', 'A21.5c', 'A21.5d',
    // A22 — the ownership vocabulary widens to the seeds' own wording (John, 2026-09-10, Task SL10:
    // "Preserve existing seed wording/detail"). One literal edit: the wizard step 1 ownership
    // select's ten options, combining the design's four with the seeds' own six phrasings.
    'A22',
    // A23 — collapsing the Market data card leaves its LAYER menu floating (John, 2026-09-10,
    // Task MD1: "the collapse widget top left expand/collapse is disconnected to the drop down").
    // That panel is the one element absolutely positioned outside the card's collapsible region;
    // the comparison listbox is inside it, in normal flow, and has always unmounted with the card.
    // One literal edit: `toggleLegend` clears mdLayerMenu and mdCompareMenu unconditionally — on
    // expand as well as collapse — so neither menu can come back open.
    'A23',
    // A25 — Task MP1 (John, 2026-09-10): "a listing with no coordinates keeps its place in the
    // results and does not get a pin." Six literal script edits: A25.1 the pin list, A25.2 the
    // drive-ring centre and A25.3 the map's community list all skip a listing with no finite
    // point (the three legs into Leaflet's `toLatLng(null)`); A25.4 stops the panel's
    // last-resort community object standing in zeros for absent figures; A25.5 gives the panel
    // the `p8` term A21.4a dropped, so it and the detail agree. A20 is reserved by the
    // image-identifiability plan and A24 by the neighbourhood-shading spec, both in flight.
    // A25.6 — fix round 1, Important-1: `showDrive` had no coordinate term, so A25.2's restored
    // else-branch painted the drive-time ring around the metro centre for an unlocated listing.
    'A25.1', 'A25.2', 'A25.3', 'A25.4', 'A25.5', 'A25.6',
    // A26 — the Browse filter bar's native <select>s become in-design dropdowns (John,
    // 2026-09-11: "the dropdown 'more filters' is correct implementation while everything else on
    // the filter bar is implemented incorrectly and not using the site design, this must be
    // corrected"). The SECOND report about this toolbar row, so the family reuses A13's own idiom
    // rather than a second one. Task F1's sixteen: A26.1 the four shared class members, A26.2 the
    // `filters` map body, A26.4 the More-filters popover's parent edge, A26.5-A26.7 one branch
    // each in the three dismissal closures A13.4/A13.8 already arm, A26.8a-f the six inbound
    // cross-close edges, A26.9a-c go()'s three arms, A26.10 the markup. Task F2 adds the two
    // that convert the three inside the "More filters" popover on the same idiom and the same
    // state slot — A26.3 the `moreFilters` map body, beside A26.2's, and A26.11 the markup,
    // beside A26.10's.
    'A26.1', 'A26.2', 'A26.3', 'A26.4', 'A26.5', 'A26.6', 'A26.7', 'A26.8a', 'A26.8b', 'A26.8c', 'A26.8d', 'A26.8e', 'A26.8f',
    'A26.9a', 'A26.9b', 'A26.9c', 'A26.10', 'A26.11',
    // A26.12-A26.14 — the Q2 widening (controller ruling on the A26 plan's Q2, 2026-09-11).
    // Not new scope: a defect against John's own 2026-09-08 m7 ruling, on three lines A26.8
    // is already editing, given their OWN ids so they can be lifted out without touching it.
    // Each reads A26.8a/A26.8b/A26.8e's output, so all three run after the family's own.
    // A26.15 is the fourth direction, found by the exhaustive pair enumeration rather than by
    // reading: the metro listbox's ARROW open path closed none of the other three, where its
    // click path closes all three after A26.14. A14 had to cover both of Give's paths for the
    // same reason. Reads A26.8f's output, so it runs after it.
    'A26.12', 'A26.13', 'A26.14', 'A26.15',
    // A26.16 — the panel width (John, 2026-09-11, Task F1b): "the panel takes the width of the
    // trigger that opened it, so their edges line up." Its own id and its own ruling, because it
    // is its own ruling; it reads A26.10's and A26.11's output, so it is applied last and it
    // edits BOTH panels in one entry (count: 2) — which is how F2's three are born with the
    // width instead of acquiring it in a third pass.
    'A26.16',
    // A27 — per-figure geography on the Community Context card (John, 2026-09-11, D-C38/D-C39).
    // A27.1 and A27.2 give the Median income and Growth tiles their own sub-lines; A27.3 and
    // A27.4 correct the two live sentences on the docked panel that describe the band as a drive
    // time when it is an 8 km straight-line buffer. A27.2/A27.3/A27.4 read A21.3d's, A21.4a's and
    // A21.4d's output, so the family is appended last.
    'A27.1', 'A27.2', 'A27.3', 'A27.4', 'A27.5',
    // D-C42 (John, 2026-09-11): the Insights heading keeps its name and the geography moves to a
    // sub-line beneath it. A27.6 reads A27.3's output and A27.7 A21.5a's, so both come after them.
    'A27.6', 'A27.7', 'A27.8',
    // A28 — the ring is drawn at the distance the card names (John, 2026-09-11, ruling D-C44).
    // A28.1 is the first entry that edits `MarketMapV3.jsx` (`file: 'jsx'`); A28.2-A28.4 delete
    // the legacy panel's orphan rows and the two state flags those rows were the only reader of.
    // A28.5-A28.8 (controller amendment D-C45) delete the four helpers those rows called.
    'A28.1', 'A28.2', 'A28.3', 'A28.4', 'A28.5', 'A28.6', 'A28.7', 'A28.8', 'A28.9',
    // A24 — real Census boundary polygons replace the grid mosaic (2026-09-10; John's rulings
    // D-C34–D-C37, spec 2026-09-10-neighbourhood-shading-design.md). Numerically before A25/A26
    // and applied after them: A24 was reserved by the ledger's own A25.1 row while those two
    // families were written and merged, so every A24 `find` is measured against the file they
    // leave behind. The four `.jsx` entries are the ones the second-file partition was built for
    // (A28.1, merged first, is the first jsx entry in this list); `amendmentsFor` partitions them and each
    // file is proved on its own. A24.13 is the same family's OTHER ruling, D-C46 (John,
    // 2026-09-11): real polygons drawn on class breaks that cannot represent real data would
    // still be one colour, so the breaks move in the same change that makes them visible.
    'A24.1', 'A24.2', 'A24.3', 'A24.4', 'A24.5', 'A24.6a', 'A24.6b', 'A24.7', 'A24.8a', 'A24.8b',
    'A24.13',
    // Task 10 -- the adapter path. The plan allotted it A24.13-A24.17; D-C46 took A24.13
    // inside Task 4, so these are A24.14-A24.18 and the family totals twenty.
    'A24.14', 'A24.15', 'A24.16', 'A24.17', 'A24.18',
    // The Census tract ruling (controller, 2026-09-12). Both CHAINED, so both sit after the
    // entries they read: A24.19 after A24.2, A24.20 after A24.7.
    'A24.19', 'A24.20',
    'A24.21', 'A24.22', 'A24.23',
    // D-L1 (John, 2026-09-12): the four layers that painted nothing. Every entry is CHAINED on
    // an earlier A24 entry's output, so each runs after the one it reads.
    'A24.24', 'A24.25', 'A24.26', 'A24.27', 'A24.28', 'A24.29', 'A24.30a', 'A24.30b',
    'A24.31a', 'A24.31b', 'A24.32',
    // Fix round 1 (review of e984c85..304b80f, 2026-09-12). Every entry is CHAINED on an earlier
    // A24 entry's output, so each runs after the one it reads.
    'A24.33', 'A24.34', 'A24.35', 'A24.36', 'A24.37', 'A24.38', 'A24.39', 'A24.40', 'A24.41',
    'A24.42',
    // MS1 (2026-09-12): the snapshot strip's own sign. Not chained — its `find` is the pristine
    // bundle's own `num` declaration.
    'A24.43',
    // Fix round 2 (2026-09-12): the snapshot states its own basis (B) and the threshold tip
    // carries the ruled sentence alone (E). A24.56 reads A24.20's output and A24.57 A24.38's.
    'A24.44', 'A24.45', 'A24.46', 'A24.47', 'A24.48', 'A24.49', 'A24.50', 'A24.52', 'A24.51',
    'A24.54', 'A24.53', 'A24.55', 'A24.56', 'A24.57',
    // Fix round 2, C and D: one number parser, and a comment that stopped being true when A24.43
    // fixed it. A24.59 reads A24.3's own output.
    'A24.58', 'A24.59',
    'A24.9', 'A24.10', 'A24.11', 'A24.12',
    // A30 — a metro change closes the docked panel (John's ruling, Task PANEL-STALE, 2026-09-12:
    // "the design has no treatment for 'the selected practice is not in this metro', and closing
    // is the only honest state"). One literal edit: `setMarket` clears `mdSel` in the same
    // object literal A13.1 wrote, so it reads A13.1's own output and is appended last.
    'A30',
    // A32 — the metro switch waits for the map to move before asking (Task ADAPT-STALE-3,
    // 2026-09-12). One literal edit, CHAINED on A24.18: its `find` is the `this.loadAreas(v);`
    // line A24.18 put in `setMarket`, so it is appended after it.
    'A32',
    // A31 — the Market snapshot has two modes, AREA and LOCATION (Task SNAP, ruling D-C50 as
    // revised by the stakeholder, 2026-09-12: the strip described the LISTINGS' own
    // five-mile rings while the map beside it painted Census geography, and a clicked
    // practice changed nothing at all). Appended last, as every family is, and it has to
    // be: A31.4 reads A24.17's line, A31.8 the whole A24.53/A24.54/A24.55 block, A31.9
    // A24.44's and A31.11 A24.20's and A24.56's — and A31.5 reads A32's OWN output, which
    // is why this block sits after A32: ADAPT-STALE-3 replaced the line A31.5 used to read.
    'A31.1', 'A31.2', 'A31.3', 'A31.4', 'A31.5', 'A31.6', 'A31.7', 'A31.8', 'A31.9', 'A31.10', 'A31.11',
    // Fix round 1 of Task SNAP (2026-09-13): A31.12 is CHAINED on A31.8's own two caption
    // lines and A31.12b on A24.45's whole helper, so both run after the entries they read.
    'A31.12', 'A31.12b', 'A31.12c',
    // A31.13/A31.13b are CHAINED on A31.8 too, on lines A31.12 does not touch.
    'A31.13', 'A31.13b',
    // A33 — three Browse labels that stated more than the data supports (Task SCREEN-LABELS,
    // 2026-09-13). A33.1b is CHAINED on A21.2d, whose `replace` its `find` is part of.
    'A33.1a', 'A33.1b',
    // A33.2 — the margin caveat counts the bands it spans. A33.2a is CHAINED on A24.25/A24.37
    // (the `AREA_LAYERS` literal it declares the word table beside) and A33.2c on A24.3 (the
    // margin expression it rewrites); A33.2b's `find` is the pristine bundle's own `bucket`.
    'A33.2a', 'A33.2b', 'A33.2c',
    // A33.3 — every Market data layer row names the geography it shades (D-C51 caption audit,
    // rows R13–R18). Six independent literals, one per row, each measured in the pristine bundle.
    'A33.3a', 'A33.3b', 'A33.3c', 'A33.3d', 'A33.3e', 'A33.3f',
  ];

  it('A24 draws real boundary polygons, each at its own geography, through the design\'s own bucket()', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const jsx = readFileSync(AMENDED_JSX, 'utf8');

    // D-C35's rule and the six geographies it now governs, each with its own legend label.
    // income moved 860 -> 140 "Census tract" on 2026-09-12 (A24.19); growth and econ did NOT,
    // and that asymmetry is the ruling rather than an oversight — growth cannot be computed at
    // tract level across the 2010->2020 boundary change (plan D12).
    // A24.24 (D-L1, 2026-09-12) INVERTS the assertion that stood here: `pets`, `households` and
    // `competition` were required NOT to have a geography, because they were graduated symbols
    // at the listing point. They painted NOTHING on QA, the stakeholder said so, and each now
    // shades where its own figure is measured — the two ACS counts at the tract beside income,
    // and the ZIP Business Patterns count at the ZCTA, which is that dataset's own geography.
    expect(amended).toContain('const AREA_LEVEL = { income: "140", growth: "160", econ: "050", households: "140", pets: "140", competition: "860" };');
    expect(amended).toContain('const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County", households: "Census tract", pets: "Census tract", competition: "ZIP Code Tabulation Area" };');
    expect(amended).toContain('const FILL_KEYS = ["income", "growth", "econ", "households", "pets", "competition"];');
    // The choropleth's own class breaks, measured over the distribution the MAP paints rather
    // than over the community cards' (A24.25). `VALUE_LAYERS` is untouched, which is what keeps
    // the snapshot strip, the Compare rows and the docked panel on their own scale and pixels.
    expect(amended).toContain('  households: { buckets: ["< 1,000", "1,000\u20131,500", "1,500\u20132,000", "> 2,000"], stops: [1000, 1500, 2000] },');
    expect(amended).toContain('  pets: { buckets: ["< 600", "600\u2013850", "850\u20131,100", "> 1,100"], stops: [600, 850, 1100] },');
    // Fix round 1, Important 3: the first class is labelled "3", not "1-3". The Census publishes
    // no ZIP-level count for a category under three establishments, so the served distribution has
    // a floor of three and a class promising a 1 or a 2 is false precision.
    expect(amended).toContain('  competition: { buckets: ["3", "4\u20135", "6\u20139", "10+"], stops: [4, 6, 10] }');
    // …and the alias `areaSet` was missing, which is what painted households 503/503 "No data".
    expect(amended).toContain('const raw = best ? (layer === "households" ? best.hh : layer === "competition" ? best.vets : best[layer]) : undefined;');
    expect(amended).toContain('  households: { label: "Households (ACS)", short: "Total households", unit: "count", buckets: ["< 10K", "10K\u201325K", "25K\u201345K", "> 45K"], stops: [10000, 25000, 45000] },');
    // §9: the modelled estimate says it is modelled, in the tip as well as in the catalogue.
    expect(amended).toContain('"Modelled estimate: households \u00d7 0.57. Not an observed count."');
    // §15: a competition count never reaches the screen bare — it names what it counts and the
    // geography it counts them in, and the geography comes from AREA_LABEL rather than a literal.
    expect(amended).toContain('(layer === "competition" ? " veterinary practices" : "")');
    expect(amended).toContain('"Counted within this " + AREA_LABEL[layer] + ". ZIP Code Business Patterns is published per ZIP code, which is this dataset\u2019s own authoritative geography.');
    // Fix round 1, Important 3: the third ZCTA state says which rule hid it, in the API's own
    // words (`tests/census/test_design_shading_labels.py` pins the sentence across both sides).
    // Fix round 2, E: the ruled sentence and NOTHING else — A24.38 had shipped a lead-in in
    // front of it, and the stakeholder rejected invented copy.
    expect(amended).toContain('p.suppress_reason === "source_threshold" ? "The Census does not publish a ZIP-level count');
    expect(amended, 'the lead-in sentence is still there').not.toContain('Fewer than three veterinary establishments here');
    // Fix round 2, B: one string per fact — the three layers whose line named the MAP's geography
    // carry the dataset alone, and `metaSource` composes the rest for the surface that prints it.
    expect(amended).toContain('const metaSource = (k, basis) => {');
    expect(amended).toContain('    dataset: "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940",');
    // A31.12c (fix round 1, 2026-09-13, Minor 3): `growth` was the ONE layer A24.45's split
    // left carrying a whole `source` sentence ending "\u00b7 community level", while its AREA card
    // measures PLACE polygons and `AREA_LABEL.growth` is "Place (city/town)" — so the vaguer
    // wording stood on the card AND on the map legend. It carries the dataset now.
    expect(amended).toContain('    dataset: "U.S. Census ACS population estimates, 2015\u20132023",');
    expect(amended, 'growth still bakes a geography into its own source line')
      .not.toContain('population estimates, 2015\u20132023 \u00b7 community level');
    // …and the footnote's growth caveat is untouched by it, which is what keeps the
    // paragraph true of both modes (A31.11 / A24.20).
    expect(amended).toContain('Population growth is measured for the surrounding city or county, not the tract.');
    expect(amended, 'a layer still carries the map geography baked into its source line')
      .not.toContain('estimates (2023) \u00b7 Census tract",');
    // A31.8 (Task SNAP, D-C50 as revised) SUPERSEDES the interim basis: in AREA mode the card
    // measures the MAP's own geography, so `metaSource` is asked the same question the legend
    // and the tip ask it, and in LOCATION mode it is asked the selected practice's own label.
    // `stripBasis` — and with it `communities()`'s per-community `communityLabel`, A24.44 — is
    // gone under the bundle's own dead-code rule (A31.9).
    // …and A31.12 (fix round 1, 2026-09-13) takes the basis OFF the LOCATION arm: the card's
    // own note carries the geography there, so the source line carries the dataset alone.
    expect(amended).toContain("            src: metaSource(k, sel ? \"\" : (AREA_LABEL[k] || \"\")),");
    expect(amended, 'metaSource still glues a separator onto an empty basis')
      .toContain('  return basis ? m.dataset + " \u00b7 " + basis : m.dataset;');
    expect(amended, 'the interim per-listing basis survived A31.8').not.toContain('stripBasis');
    expect(amended, "the community objects still carry a label nothing reads").not.toContain('communityLabel: p.communityLabel');

    // D-NS16 (John, 2026-09-10): the no-data class is the design's own --border-subtle value and
    // the legend gains one row reading exactly "No data".
    expect(amended).toContain('const NO_DATA_FILL = "#e6e6e6";');
    expect(amended).toContain('const NO_DATA_LABEL = "No data";');

    // The one door (spec §2.2): every polygon's colour comes from the design's own bucket() and
    // its label from the design's own fmtMetric(), so the fill and the legend cannot disagree.
    expect(amended).toContain('const b = shown ? this.bucket(layer, p.value, true) : null;');
    expect(amended).toContain('label: shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL,');

    // The tip is built ONCE, in the script, and both renderers bind it — the design and the port
    // used to build it twice and keep the two in step by hand.
    expect(amended.split('Estimate too imprecise to show at this geography')).toHaveLength(2);
    expect(jsx).not.toContain('Estimate too imprecise');
    expect(jsx).toContain('l.bindTooltip(f.properties.tip, { sticky: true, className: "rf-tip" });');

    // The grid is gone from the reference, name and all.
    expect(jsx).not.toContain('mosaicCells');
    expect(jsx).not.toContain('0.0055');
    expect(jsx).not.toContain('GEOMETRY NOTE');
    expect(jsx).toContain('// GEOMETRY: real Census boundary polygons, handed in as `areas`');
    // `voronoiCells`/`clipPolygon` were dead before this change and are left alone: the bundle's
    // dead-code rule applies to orphans a change CREATES (A2.3, A13.6), not to pre-existing ones.
    expect(jsx).toContain('function voronoiCells(sites, bbox) {');

    // Both maps are handed the polygons, and `communities` stays passed — the fixture's figures
    // are derived from it, so it is not dead.
    expect(amended.split('areas="{{ md.areas }}"')).toHaveLength(3);
    expect(amended.split('communities="{{ md.communities }}"')).toHaveLength(3);

    // The footnote John ruled on, byte for byte (§14 Q2), and the sentence it replaced is gone.
    // A24.20 (2026-09-12) renamed the geography here and added the growth caveat: a reader told the
    // areas are tracts would otherwise take EVERY figure on the strip for a tract-level one.
    // A24.56 (fix round 2, B) rewrote the sentence that described the MAP alone while sitting
    // under the snapshot strip, whose figures are per-practice. Its `find` reached one sentence
    // too far and took A24.20's ruled caveat with it (fix round 3, the re-review's Important):
    // the growth geography is exactly the fact the snapshot cannot state — its card still reads
    // "· community level" — so the paragraph carries BOTH sentences, in that order.
    const footnote = amended.split('<p style="margin: 12px 0 0; font-size: 10.5px; line-height: 1.55; color: #767676; max-width: 96ch;">')[1].split('</p>')[0];
    // A31.11 (Task SNAP, D-C50 as revised) SUPERSEDES A24.56's sentence and the opening clause it
    // restated: in AREA mode the figures describe the metro's Census areas and NO practice at all,
    // so "Figures describe the area around each practice" became false by this release's own act
    // (the A27.5 rule). The paragraph states both modes now, and A24.20's growth caveat still
    // stands beside them byte for byte, because growth is measured at place or county in either.
    expect(footnote).toContain('In AREA mode each card is the median across the metro\u2019s Census tracts, places, counties or ZIP areas, as the card itself names; with a practice selected each card is that practice\u2019s own community figure.');
    expect(footnote, 'A24.20\'s growth caveat is gone from the product').toContain('Population growth is measured for the surrounding city or county, not the tract.');
    // …and the sentence A31.11 retired is gone from the product, not merely joined by a newer one.
    expect(footnote, 'the superseded per-practice sentence survives in the footnote').not.toContain('not the practice itself');
    expect(amended).not.toContain('production draws Census ZCTA boundaries');

    // The legend names the geography, on the desktop panel and in the phone sheet, and nowhere
    // introduces a style the design does not already carry.
    expect(amended.split('{{ md.active.geoLine }}')).toHaveLength(3);
    expect(amended.split('value="{{ md.active.hasGeo }}"')).toHaveLength(3);
  });

  it('A24.14-A24.18 wire the map to the API on adapter presence, never on data', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // A16.1's exact shape (A-SL23 (2)): with the adapter present the map draws what the API
    // answered or NOTHING, and never the design's fixture, whatever the API answered.
    // A24.31a/A24.31b hoisted the expression into `areaFc` so the legend can see how many
    // polygons were drawn; the ternary itself is byte-unchanged and still keyed on adapter
    // PRESENCE rather than on data.
    expect(amended).toContain('    const areaFc = this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer);');
    expect(amended).toContain('      areas: areaFc,');
    // A24.32 (whole-branch review, finding 5): zero polygons drawn, no ramp and no geography
    // name — the legend never claims a scale the map does not carry.
    // A24.41/A24.42 (fix round 1, Minor 7): the legend stays mounted while a metro's areas load,
    // exactly as a pan already keeps it — a legend that disappears and returns is a flicker.
    expect(amended).toContain('          hasRamp: !!valueLayer && (areaFc.features.length > 0 || areasPending),');
    expect(amended).toContain('          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1 && (areaFc.features.length > 0 || areasPending),');
    expect(amended).toContain('    const areasPending = !!this.props.market && s.mdAreas === null;');
    expect(amended).toContain('mdAreas: null,');
    // One loader, with the rejection arm every adapter path in this design keeps forgetting
    // (A16.17's own lesson): a refused load empties the map, it does not restore the fixture.
    expect(amended).toContain('loadAreas(market, keep) {');   // A24.21 widened the signature
    expect(amended).toContain('if (mine()) this.setState({ mdAreas: {} });');
    // It clears before it asks, so a metro change cannot leave the previous metro's polygons
    // painted over the new metro's view; and it ignores an answer for a market the member has
    // since left, so two fetches resolving out of order cannot strand the wrong metro's
    // boundaries on screen. Both are "draw what the API answered for what you are looking at".
    expect(amended).toContain('if (!keep) this.setState({ mdAreas: null });');
    expect(amended).toContain('const mine = () => (this.state.market || "Austin, TX") === asked &&');
    // Three call sites since A24.22: the bootstrap, a change of metro, and a settled pan or zoom.
    expect(amended.split('this.loadAreas(')).toHaveLength(4);
    expect(amended.split('loadAreas(market, keep) {')).toHaveLength(2); // and exactly one definition
    // NO new prototype prop: the reference reaches the fixture path by having no adapter at all,
    // exactly as it does for `listings` and `adminListings`. `market` is an app-only prop, so it
    // must NOT appear in the design's declared `data-props` (which `app-generated.test.ts`
    // requires app.setup.js to mirror).
    const props = /data-props="([^"]*)"/.exec(amended)![1].replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    expect(Object.keys(JSON.parse(props))).not.toContain('market');
  });

  it('A24.13 re-scales the growth breaks onto real ACS data, with a band below zero (D-C46)', () => {
    const amended = readFileSync(AMENDED, 'utf8');

    // D-C46 (John, 2026-09-11). The published stops were [10, 20, 35] with no band below zero, so
    // a place that LOST population was painted the same colour as one that grew 9 %, and — measured
    // against ACS 2014-2018 → 2019-2023 place populations, which is exactly what
    // `app.census.metrics.population_growth_pct` computes — 79.9 % of US places of 10,000 people or
    // more landed in the single bottom bucket. The new breaks are the tertiles of the non-declining
    // half of that distribution (+3.3 / +8.8 nationally, +4.8 / +13.5 across Texas metro places),
    // rounded to numbers a legend can carry; 30.5 % of those places are declining and now read as
    // declining.
    expect(amended).toContain('buckets: ["Declining", "0–5%", "5–15%", "> 15%"], stops: [0, 5, 15] }');
    expect(amended, 'the un-scaled stops must be gone, not merely joined').not.toContain('stops: [10, 20, 35]');
    expect(amended).not.toContain('buckets: ["< 10%", "10–20%", "20–35%", "> 35%"]');

    // D-C36 froze the OTHER two fill layers' bands, and this ruling does not reach them.
    expect(amended).toContain('stops: [50000, 75000, 100000, 150000]');
    expect(amended).toContain('stops: [450000, 650000, 900000]');
    // Four buckets, because the growth ramp carries exactly four colours in all three palettes —
    // a fifth class would mean inventing a colour the design does not have.
    for (const pal of ['#efe6dd', '#e6f2e8', '#e8f1e3']) expect(amended).toContain(pal);
  });

  it('amendments() is exactly the pinned id list, in the pinned order, and nothing else', () => {
    expect(amendments().map((a) => a.id)).toEqual(AMENDMENT_IDS);
    expect(amendments(), 'the count, stated as a number as well as a list').toHaveLength(314);
    expect(new Set(AMENDMENT_IDS).size, 'two amendments share an id').toBe(AMENDMENT_IDS.length);
  });

  it('every amendment carries a date and a ruling, so no edit to the approved design is anonymous', () => {
    for (const a of amendments()) {
      expect(a.date, a.id).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(a.ruling.length, `${a.id} has no ruling`).toBeGreaterThan(10);
      expect(a.count, a.id).toBeGreaterThan(0);
      expect(a.find, `${a.id}: an empty find would match everywhere`).not.toBe('');
    }
  });

  // A-I8.1 (John's ruling on the implementer's NEEDS_CONTEXT): a removal amendment swallows
  // exactly one adjacent newline, so the regenerated design keeps SINGLE blank lines. Without
  // it, deleting a block that had a blank line on each side leaves two — a byte change in the
  // approved design with no rendered effect, and the kind of drift the D15 mechanism exists to
  // prevent. Asserted on the OUTPUT, which is the only place it can be true or false.
  it('no amendment introduces a doubled blank line (A-I8.1)', () => {
    // COUNTED, not located: the pristine bundle ships one doubled blank of its own (script
    // line 1744, between `ECON_K`'s closing `};` and `const num`), which is the design's and
    // not this mechanism's to tidy. Line NUMBERS move whenever an amendment adds or removes a
    // line, so the invariant has to be the count — it may not grow.
    const doubled = (text: string) => text.split('\n').filter((line, i, all) => line.trim() === '' && (all[i + 1] ?? 'x').trim() === '').length;
    expect(doubled(readFileSync(AMENDED, 'utf8')), 'a removal amendment left two blank lines where the design had one').toBe(doubled(pristine));
  });

  // A5.6: the `startGate` prototype prop. Asserted through the DECODED attribute rather than
  // as a substring, because that is what the bundle's runtime reads (support.js's
  // `parseDataProps` → `propsMeta[k].default`) and what `app-generated.test.ts` requires
  // `app.setup.js` to declare.
  it('A5.6 adds the startGate prototype prop with the ruled shape, immediately after startViewport', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const attr = /<script type="text\/x-dc" data-dc-script[^>]*data-props="([^"]*)"/.exec(amended)!;
    const declared = JSON.parse(attr[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&')) as Record<string, unknown>;
    expect(Object.keys(declared)).toEqual(['$preview', 'prototypeBar', 'startScreen', 'startViewport', 'startGate', 'me', 'startNotice', 'startAnswerNote', 'startMyListings', 'layerPalette']);
    // A8.8a widened the enum to every gate value the account screens add; the shape is A5.6's.
    expect(declared.startGate).toEqual({
      editor: 'enum',
      options: ['signin', 'apply', 'pending', 'rejected', 'signup', 'check-email', 'verify-expired', 'forgot', 'reset', 'reset-expired', 'invite', 'answer', 'unavailable'],
      default: '', tsType: 'string', section: 'Prototype', label: 'Start on gate state'
    });
    // A5.7: the account the reference is handed, so its header matches the app's. `null` must
    // survive the round trip — `support.js` copies a default only `if (v !== void 0)`, so a
    // `null` default is passed to the Root and `logic.js`'s A5.4 bootstrap skips its branches.
    expect(declared.me).toEqual({
      editor: 'json', default: null, tsType: 'object', section: 'Prototype', label: 'Signed-in account'
    });
    // A9.1a (A-S5): the applicant-answer card's note, the reference's only way to it. Same shape
    // as A8.8b's `startNotice`, spliced immediately after it, and defaulting to `""` — which is
    // what keeps the 28 approved states on their pixels (an empty note renders nothing).
    expect(declared.startAnswerNote).toEqual({
      editor: 'text', default: '', tsType: 'string', section: 'Prototype', label: 'Applicant answer note on load'
    });
    // A16.11a (A-SL17/A-SL22 (1)): the seller's own listings, the reference's only way to the
    // empty dashboard. `me`'s own `json` editor because the value is an array, and `null` —
    // "nothing was handed over" — because an empty ARRAY is a real answer that empties the table,
    // which is what keeps every other approved state on its pixels.
    expect(declared.startMyListings).toEqual({
      editor: 'json', default: null, tsType: 'object', section: 'Prototype', label: 'Seller listings on load'
    });
    // The pristine bundle declares none of the three — all exist only as local amendments.
    expect(pristine).not.toContain('startGate');
    expect(pristine).not.toContain('&quot;me&quot;');
    expect(pristine).not.toContain('startAnswerNote');
  });

  // A6/A7 — the launch-removal list and the sign-in copy, asserted on the OUTPUT: every
  // affordance CLAUDE.md's list names is gone from the design itself, so the oracle and the app
  // lose them together. `prototypeBar`, `startScreen`, `startViewport` and `startGate` stay
  // DECLARED (D-I8-2) — the parity test requires app.setup.js to declare what the design does,
  // and the app simply never passes the first three.
  it('A6/A7 take the prototype affordances out of the design and leave the props declared', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const gone of [
      'showPrototypeBar', 'Prototype — access states', 'gateStates', 'jumpTo', 'const jumps',
      'r.mendes@example.com', '············', 'viewportLabel', 'toggleViewport',
      'Mobile view', 'VIN username or email', 'Enter both your VIN username'
    ]) {
      expect(amended, `the launch removal left ${gone} in the design`).not.toContain(gone);
    }
    expect(amended, 'the sign-in label is the address the API actually authenticates').toContain('Email</span>');
    expect(amended).toContain('"Enter both your email and password."');
    // D-I8-2: declared, never passed.
    for (const declared of ['prototypeBar', 'startScreen', 'startViewport', 'startGate']) {
      expect(amended, `${declared} must stay declared in data-props`).toContain(`&quot;${declared}&quot;`);
    }
    // The fixture ARRAYS stay until the listings API replaces them (CLAUDE.md keeps the field
    // names because the UI reads them) — this is the launch removal, not a data migration.
    for (const kept of ['const P = [', 'sellerListings', 'const MARKETS', 'me: { name: "Dr. Rachel Mendes"']) {
      expect(amended, `${kept} is not part of this list`).toContain(kept);
    }
  });

  // ---------------------------------------------------------------------------------------
  // A-S4 (Task S4) — the account screens. The design gains seven gate states and the two
  // touches to the sign-in card John ruled, and every one of them is composed from the gate
  // card the design already ships. That is what keeps the other 27 approved states on their
  // pixels, and the cases below are what stop a new block from styling anything of its own.
  // ---------------------------------------------------------------------------------------
  const GATE_OPEN = '    <sc-if value="{{ showGate }}" hint-placeholder-val="{{ true }}">';
  const GATE_CLOSE = '        <div style="background: var(--color-navy); color: var(--color-white); padding: 30px 34px;">';
  /** The gate screen's own markup: the band, the two columns and the cards, up to the footer band. */
  const gateRegion = (html: string) => {
    const a = html.indexOf(GATE_OPEN); const b = html.indexOf(GATE_CLOSE, a);
    expect(Math.min(a, b), 'the gate region moved — this helper no longer finds it').toBeGreaterThan(0);
    return html.slice(a, b);
  };
  /** What an amendment ADDS: `replace` minus the prefix and suffix it shares with `find`. */
  const insertedText = (a: Amendment) => {
    let head = 0; while (head < a.find.length && a.find[head] === a.replace[head]) head++;
    let tail = 0; while (tail < a.find.length - head && a.find[a.find.length - 1 - tail] === a.replace[a.replace.length - 1 - tail]) tail++;
    return a.replace.slice(head, a.replace.length - tail);
  };

  it('A7.3/A7.4 are the two ruled touches to the sign-in card, and the VIN wording is gone', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(amended, 'A7.3: the forgot-password entry point').toContain('Not approved yet? <a href="#apply" onClick="{{ goApply }}">Request access</a> · <a href="#forgot" onClick="{{ goForgot }}">Forgot your password?</a></div>');
    expect(amended, 'A7.4: the sub-line').toContain('>Use the email and password you registered with.</div>');
    expect(amended, 'the VIN-credentials sub-line is the copy John ruled out').not.toContain('Use your VIN credentials.');
  });

  // The composition rule, machine-checked. Without it "built only from the existing gate card"
  // is a promise in a document; with it, a block that invents a padding, a colour or a radius
  // fails here rather than in a screenshot review.
  it('A8.7 invents no style: every style attribute in the blocks it inserts is one the gate card already carries', () => {
    const list = amendments();
    const i = list.findIndex((a) => a.id === 'A8.7');
    expect(i, 'A8.7 is not in the amendment list').toBeGreaterThan(-1);
    const inserted = insertedText(list[i]);
    // The design the blocks are copied FROM: the pristine file with every earlier amendment
    // applied — A1's ruled typography included, since the gate card's own 20 px title carries it.
    const from = gateRegion(applyAmendments(pristine, list.slice(0, i)));
    const pristineGate = gateRegion(pristine);
    const attrs = [...inserted.matchAll(/\bstyle(?:-[a-z]+)?="[^"]*"/g)].map((m) => m[0]);
    expect(attrs.length, 'A8.7 inserted no styled element at all').toBeGreaterThan(30);
    for (const attr of attrs) {
      expect(from, `A8.7 introduces a style the gate card does not carry: ${attr}`).toContain(attr);
      // …and, apart from A1's two ruled declarations, it is the PRISTINE card's own string, so no
      // block can smuggle in a style that some earlier amendment happened to invent.
      expect(withoutTypography(pristineGate), `not the pristine gate card's own style either: ${attr}`).toContain(withoutTypography(attr));
    }
  });

  it('A8.7 adds exactly the five account form cards, and the four status states add no markup at all', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const flag of ['gateSignup', 'gateForgot', 'gateReset', 'gateInvite', 'gateAnswer']) {
      expect(amended.split(`<sc-if value="{{ ${flag} }}"`).length - 1, `${flag} is not rendered exactly once`).toBe(1);
    }
    // check-email, verify-expired, reset-expired and unavailable render through the status card
    // the design already had (A8.4 widens `gateStatus` and fills `statusMap`) — "absent beats
    // faked" cuts both ways, and a second card would have moved the four approved status states.
    for (const flag of ['gateCheckEmail', 'gateVerifyExpired', 'gateResetExpired', 'gateUnavailable']) {
      expect(amended, `${flag} must render through the existing gateStatus card`).not.toContain(`<sc-if value="{{ ${flag} }}"`);
    }
  });

  it('A8.8 declares startNotice beside the other prototype props, with the ruled shape', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const attr = /<script type="text\/x-dc" data-dc-script[^>]*data-props="([^"]*)"/.exec(amended)!;
    const declared = JSON.parse(attr[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&')) as Record<string, unknown>;
    expect(declared.startNotice).toEqual({ editor: 'text', default: '', tsType: 'string', section: 'Prototype', label: 'Sign-in notice on load' });
    expect(pristine, 'startNotice exists only as a local amendment').not.toContain('startNotice');
  });

  // A13 composes the metro dropdown from the design's OWN listbox: every style value it
  // introduces already appears on the pristine bundle's layer/compare menu or on the metro
  // field the amendment replaces. The one exception is asserted as an exception: the panel's
  // `top: 46px`/`z-index: 700` anchoring comes from the "More filters" popover in the SAME
  // toolbar row, which is a different element of the same design.
  it('A13 introduces no new styling — every value is the design\'s own', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const decl of [
      'font-family: var(--rf-display); font-size: 13px; font-weight: ',   // rowStyle, V3:2112
      'background: var(--vf-accent-bg)',                                   // selected row, V3:2113
      'background: var(--vf-neutral)',                                     // hover / highlight, V3:525
      'transition: transform 150ms var(--easing-out); transform: rotate(', // caret, V3:2096
      'box-shadow: 0 6px 20px rgba(0,58,112,.16)',                         // More filters panel, V3:382
      'top: 46px; z-index: 700',                                           // More filters anchoring, V3:382
      'max-height: 232px; overflow-y: auto',                               // compare menu, V3:482
      'flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'
    ]) {
      expect(pristine, `${decl} is not the design's own`).toContain(decl);
    }
    // …and the operating system's popup is gone from the toolbar: the metro control is now a
    // button that says what it opens, and the four markets are options in a labelled listbox.
    expect(amended).toContain('aria-label="Metro area" aria-haspopup="listbox"');
    expect(amended).toContain('<div role="listbox" aria-label="Metro area"');
    // A13 round 3: `aria-activedescendant` belongs on the element that HOLDS FOCUS. Focus stays
    // on the trigger button — the role="listbox" div is not focusable and never receives it — so
    // on the panel the attribute is inert and no screen reader reads it.
    expect(amended, 'aria-activedescendant must sit on the focused trigger')
      .toContain('aria-expanded="{{ marketMenuOpen }}" aria-activedescendant="{{ marketActiveId }}"');
    expect(amended, 'and not on the panel, which never holds focus')
      .not.toContain('<div role="listbox" aria-label="Metro area" aria-activedescendant=');
    // …and the reference has to RESOLVE: ARIA looks for the active descendant inside the element
    // carrying the attribute or inside the one it owns/controls, and the panel is the trigger's
    // sibling. `aria-controls` is what makes the pair reachable (round 5, N4).
    expect(amended, 'the trigger must control the panel by id')
      .toContain('aria-haspopup="listbox" aria-controls="metro-listbox" aria-expanded="{{ marketMenuOpen }}"');
    expect(amended, 'and the panel must carry that id')
      .toContain('<div role="listbox" aria-label="Metro area" id="metro-listbox"');
    // Final review I1 (ruled, a widening of A13.3): ARIA 1.2 lists `aria-activedescendant` as
    // supported on `application`, `combobox`, `group`, `textbox` and the composite widget roles —
    // `button` is not among them, so a user agent need not expose it and the whole chain rounds 3
    // to 5 built was liable to be dropped on the way to the accessibility tree. The trigger is the
    // APG Select-Only Combobox in every other respect; it now says so. And a listbox driven by
    // `aria-activedescendant` keeps focus on the one element that holds it, so the option rows
    // leave the tab order rather than being Tab-able into a panel whose keys are not bound.
    expect(amended, 'the trigger must carry a role that supports aria-activedescendant')
      .toContain('role="combobox" aria-label="Metro area" aria-haspopup="listbox"');
    expect(amended, 'the options leave the tab order — focus stays on the combobox')
      .toContain('role="option" tabindex="-1"');
    expect(amended).not.toContain('onChange="{{ setMarket }}"');
    // A13's scope was "the five filter selects, the sort select and the wizard's stay native
    // (Q1)". OVERRULED on 2026-09-11 in its first clause (family A26, John: "the dropdown 'more
    // filters' is correct implementation while everything else on the filter bar is implemented
    // incorrectly and not using the site design"), which converts the five and — in Task F2 — the
    // three inside the More-filters popover, on this same idiom. The results-rail sort select
    // becomes its own wired change (he ruled make it actually sort, not merely convert it) and
    // the wizard's four field selects convert later as their own change, because `wizard-step-1`
    // is one of the thirteen frozen hashes and A26 is deliberately a family in which none moves.
    //
    // So the count is the live scope statement, not A13's, and not a stale literal: the amended
    // design holds exactly TWO `<select >` tags now that Task F2 has converted the popover's
    // loop as well — the results-rail sort control and the wizard's field-select loop, one tag
    // each, and each left native by a ruling of its own. It was four before A26 and three
    // between F1 and F2. The floor is two: converting either of those two here would be scope
    // this family does not have.
    expect((amended.match(/<select /g) ?? []).length, 'a select changed outside the ruled scope').toBe(2);
    expect(amended, 'the results-rail sort control stays native (D-F1: it must be WIRED as well as converted)')
      .toContain('<select style="flex: none; height: 34px; padding: 0 9px;');
    expect(amended, 'the wizard\'s field selects stay native (wizard-step-1 is a frozen hash)')
      .toContain('<select value="{{ fd.value }}" onChange="{{ fd.set }}"');
  });

  // A14 (John, 2026-09-08: "the Give button must be identical to the https://vinfoundation.org/
  // where the button is an actual drop down (match button design pixel-by-pixel)"). The pristine
  // file has ONE Give control — an inert <button> at V3:104, outside both the signedIn and the
  // signedOut blocks, so it is in the header of every screen. After A14 it is a trigger plus a
  // four-item menu, and the four hrefs are John's, verbatim.
  it('A14 turns the one Give button into a dropdown with John\'s four links', () => {
    expect(pristine.split('>Give</button>').length - 1, 'the pristine file has exactly one Give button').toBe(1);
    const amended = readFileSync(AMENDED, 'utf8');
    expect(amended.split('role="menuitem"').length - 1).toBe(1);            // one row template, sc-for'd four times
    expect(amended).toContain('aria-haspopup="menu"');
    for (const href of ['https://vinfoundation.org/give/', 'https://vinfoundation.org/cor/',
      'https://vinfoundation.org/legacy-giving/', 'https://vinfoundation.org/resources/dr-sophia-yin-memorial-fund/']) {
      expect(amended.split(href).length - 1, `${href} is not in the amended design exactly once`).toBe(1);
    }
    expect(amended, 'a Give link must not open a new tab — the live site\'s do not').not.toContain('target="_blank"');
    // m1 (review round 1, ruled): the same pairing A13's round 5 gave the metro control — a
    // trigger that names the panel it controls, and a panel that carries that id. Without it the
    // two dropdowns shipping together are inconsistent, and `aria-haspopup` alone leaves an
    // assistive technology no route from the button to the menu.
    expect(amended, 'the trigger must control the panel by id')
      .toContain('aria-haspopup="menu" aria-controls="give-menu" aria-expanded="{{ giveMenuOpen }}"');
    expect(amended, 'and the panel must carry that id')
      .toContain('<div role="menu" aria-label="Give" id="give-menu" ref="{{ givePanelRef }}"');
    // C1 (review round 1, ruled): the panel's mount ref is what spends the arrow keys' pending
    // index, so its presence in the DESIGN is what makes the keyboard work on BOTH targets.
    expect(amended, 'the arrow keys must not focus inside a setState callback — the app has not rendered yet')
      .not.toContain('}, () => this.giveFocus(');
    expect(amended).toContain('this.setState({ giveMenu: true, giveMenuAt: at, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1, fMenu: null, fMenuAt: -1 });');
    // m7 (final review, ruled): the invariant runs in every direction now — Give's two open paths
    // close the other three menus, and each of the other three closes Give.
    //
    // WIDENED, NOT WITHDRAWN (A26, 2026-09-11). Each of these four open paths gained the filter
    // dropdowns' two keys (A26.8a-e), because A26 put five more menus on the same screen and the
    // invariant they encode is being EXTENDED. The strings stay byte-exact and stay pinned: a
    // future edit that drops `giveMenu: false` from any of them still fails here, which is the
    // only reason these lines exist.
    //
    // WIDENED A SECOND TIME by A26.12-A26.14 (controller ruling on the A26 plan's Q2, 2026-09-11).
    // m7 says "opening any one of the FOUR menus closes the other three", and three of the six
    // directions among nav/account/metro were never written: the account toggle closed neither
    // the nav menu nor the metro listbox, the nav toggle closed no metro listbox, and the metro
    // trigger closed neither of the header's two. Give's own six were complete, which is why the
    // gap survived — Give and the metro also have global pointerdown/focusout dismissal, while
    // `navMenu` and `userMenu` have none of any kind (D-F2, reported and NOT built here), so a
    // pointer could hold the account menu open beside a freshly opened metro listbox with two
    // clicks. A26 was already editing all three lines; the widening carries its own ids so it
    // can be lifted out without touching A26.8.
    expect(amended, 'the nav toggle must close Give (A14.8) and the metro listbox (A26.12)')
      .toContain('toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false, fMenu: null, fMenuAt: -1, marketMenu: false, marketMenuAt: -1 }),');
    expect(amended, 'the account toggle must close Give (A14.2), the nav menu and the metro listbox (A26.13)')
      .toContain('toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, marketMenu: false, marketMenuAt: -1 }),');
    expect(amended, 'the metro listbox must close Give (A13.2) and the header\'s two menus (A26.14)')
      .toContain('Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, userMenu: false }),');
    // m6 (final review, ruled): Home and End on the TRIGGER, guarded on the menu being open, the
    // way `marketMenuKeys` has them — the per-row handler already had them.
    expect(amended, 'Home and End must reach the Give trigger')
      .toContain('if (s.giveMenu && (e.key === "Home" || e.key === "End")) {');
  });

  // A14.7 (m2) and A13.8 (final review m4): the third dismissal, shared by both menus, and the
  // proof it left A13's other two — and A14's Give behaviour — exactly as they were.
  it('the focusout dismissal in trackMenuDismiss covers both menus and touches neither of the other two closures', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(amended).toContain('document.addEventListener("focusout", out, true);');
    expect(amended).toContain('if (this._onDocOut) document.removeEventListener("focusout", this._onDocOut, true);');
    // Window blur (relatedTarget null) is the shared non-dismissal, and a move inside either
    // control is a move within that control: A13.8 kept A14.7's Give semantics exactly.
    expect(amended).toContain('      const to = e.relatedTarget;\n      if (!to) return;\n      if (this.state.giveMenu) {\n        const give = this._giveMenuEl;\n        if (!(give && give.contains(to))) this.setState({ giveMenu: false });\n      }');
    // …and the metro branch is A14.4's own shape, one closure over (m4).
    expect(amended, 'Tab out of the metro listbox must close it too').toContain('      if (!this.state.marketMenu) return;\n      const host = this._marketMenuEl;\n      if (host && host.contains(to)) return;\n      this.setState({ marketMenu: false, marketMenuAt: -1 });');
    // A13's own pointerdown closure, byte for byte, after every A14 edit to the function.
    expect(amended, 'A14 changed the metro menu\'s outside-click').toContain('      if (!this.state.marketMenu) return;\n      const host = this._marketMenuEl;\n      if (host && e.target && host.contains(e.target)) return;\n      this.setState({ marketMenu: false, marketMenuAt: -1 });');
    // NINE metro dismissal sites. Six from A13/A14: A13.4's pointerdown and keydown, A13.8's
    // focusout, A13.1's setMarket, and m7's two — Give's pointer open and its arrow open (A14.2).
    // The seventh is A26's (2026-09-11): the filter dropdowns' ONE open path, A26.1's
    // `openFilterMenu`, which is the whole family's outbound edge. The eighth and ninth are the
    // Q2 widening — A26.12's nav toggle and A26.13's account toggle, the two m7 directions that
    // were never written.
    expect((amended.match(/marketMenu: false, marketMenuAt: -1/g) ?? []).length, 'the metro menu is shut in exactly these nine places').toBe(9);
  });

  // A14.6 + the ruling: "Self-host Montserrat 600 under the SIL Open Font Licence, scoped
  // exclusively to the Give button and its menu. Keep the rest of the design typography
  // unchanged." The scope is the whole point, and it is machine-checked here rather than
  // promised: exactly one @font-face, exactly two declarations that name the family, and both of
  // them inside the two style strings A14.2 builds.
  it('A14.6 self-hosts Montserrat 600 and scopes it to the Give control alone', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(pristine, 'the bundle loads no Montserrat of any kind').not.toContain('Montserrat');
    expect(amended.split('@font-face').length - 1, 'A14 adds exactly one @font-face').toBe(1);
    expect(amended).toContain("src: url('assets/fonts/Montserrat-SemiBold.woff2') format('woff2');");
    expect(amended).toContain('font-weight: 600; font-style: normal; font-display: swap;');
    // Two readers, and only two: the trigger's style and the menu row's style.
    expect(amended.split("font-family: 'Montserrat', var(--rf-display)").length - 1).toBe(2);
    expect((amended.match(/Montserrat/g) ?? []).length, 'Montserrat is named only by the @font-face and its two readers').toBe(5);
    // …and no OTHER element's face changed: every remaining font-family in the design is the
    // bundle's own token or its own literal stack.
    for (const decl of [...amended.matchAll(/font-family:\s*([^;"']*(?:'[^']*')?[^;"]*)/g)].map((m) => m[0])) {
      expect(decl.includes('Montserrat') || decl.includes('--rf-display') || decl.includes('--rf-serif') || decl.includes('ProximaNova') || decl.includes('inherit'),
        `A14 must not restyle anything but the Give control: ${decl}`).toBe(true);
    }
  });

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

  // A-LB3 (2026-09-09, ruling on fix round 1's NEEDS_CONTEXT — the focusout trap does not hold
  // in real Chromium): the trap is removed at the byte level, and Tab is instead handled
  // deterministically in the shared `keydown` closure. Both are asserted directly against the
  // amended file, independent of the row prose and of logic.test.ts's characterisation.
  it('A-LB3 removes the focusout trap and moves Tab into the shared keydown closure', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // The removed trap: no deferred focus() call into the dialog from a focusout, anywhere.
    expect(amended).not.toContain('setTimeout(() => box.focus()');
    // The `out` closure carries no lightbox branch at all — A13.8's own output, verbatim, right
    // after the closure head (the comment recording the retraction, `document.addEventListener`
    // count elsewhere already pins that no listener was added or removed by this).
    expect(amended).toContain(
      '    const out = (e) => {\n'
      + '      // A19 (A-LB3, 2026-09-09): a focusout-based trap was tried here — deferring focus back\n'
      + '      // into the dialog whenever it left for a non-null relatedTarget outside it — and found\n'
      + '      // not to hold in real Chromium: a null relatedTarget also occurs at the edges of the\n'
      + '      // dialog\'s own tabbable set, which the arm cannot tell apart from a window blur. Tab is\n'
      + '      // instead handled deterministically in the shared keydown closure above (A19.9).\n'
      + '      // `relatedTarget` is where focus is GOING'
    );
    expect(pristine).not.toContain('A-LB3');
    // Tab, deterministically, by DOM position: read once, in the keydown closure, one code path
    // for both directions, no `relatedTarget` anywhere in it.
    expect(amended.split('else if (e.key === "Tab") {').length - 1).toBe(1);
    expect(amended).toContain('const controls = box ? Array.from(box.querySelectorAll("button")) : [];');
    expect(amended).toContain('if (e.shiftKey) { if (at <= 0) { e.preventDefault(); controls[controls.length - 1].focus(); } }');
    expect(amended).toContain('else if (at === controls.length - 1) { e.preventDefault(); controls[0].focus(); }');
    expect(pristine, 'Array.from(...querySelectorAll("button")) is new to the design with A-LB3').not.toContain('querySelectorAll');
  });

  it('the amended reference is the pristine Rev 2 file plus exactly the ruled edits', () => {
    expect(applyAmendments(pristine, amendmentsFor('dc'))).toBe(readFileSync(AMENDED, 'utf8'));
  });

  // A26 (John, 2026-09-11: "the dropdown 'more filters' is correct implementation while
  // everything else on the filter bar is implemented incorrectly and not using the site design,
  // this must be corrected"). The SECOND report about this toolbar row — the metro picker
  // immediately to their left was the first, ruled A13 on 2026-09-08 — so A26 reuses A13's own
  // idiom rather than authoring a second one: trigger + `role="listbox"` panel composed from the
  // Market data card's layer menu, anchored with the "More filters" popover's own pair.
  //
  // Task F1 converted the FIVE toolbar filters (one `.map()` body, five instances, one state
  // slot); Task F2 converted the three inside the "More filters" popover (a second `.map()`
  // body). Both are done, which is why the scope count below reads the family's final 2 — the
  // results-rail sort control and the wizard's field loop, both ruled OUT and both left native.
  it('A26 introduces no new styling — every value is A13\'s, which is the design\'s own', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const decl of [
      'display: inline-flex; align-items: center; gap: 8px;',              // More filters button, V3:382
      'height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: ',  // the <select> A26 replaces
      'font-family: var(--rf-display); font-size: 13px; font-weight: ',    // rowStyle, layer menu
      'background: var(--vf-accent-bg)',                                   // selected row
      'background: var(--vf-neutral)',                                     // hover / highlight
      'transition: transform 150ms var(--easing-out); transform: rotate(', // caret
      'box-shadow: 0 6px 20px rgba(0,58,112,.16)',                         // More filters panel
      'top: 46px; z-index: 700',                                           // More filters anchoring
      'max-height: 232px; overflow-y: auto',                               // compare menu
      'position: relative;',                                               // the More filters wrapper
      'flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'
    ]) {
      expect(pristine, `${decl} is not the design's own`).toContain(decl);
    }
    // A26.16 — the panel width (John, 2026-09-11, Task F1b): "the panel takes the width of the
    // trigger that opened it, so their edges line up."
    //
    // Task F1 shipped the panel with no width at all and left two `not.toContain` trip-wires
    // here — one on the pristine file, one on the amended — precisely so a later hand had to get
    // this RULED rather than add a number quietly. F1's review then measured the capture: the
    // Practice type trigger is 155 px and its panel 153 px, four of the five sat ~2 px inside the
    // button that opened them, and Property inverted and opened far wider than its collapsed
    // trigger. "The design is silent here" was never the honest description either — the panel
    // string is A13's metro panel with `width: 300px` DELETED, and FOUR of the four absolutely
    // positioned menu panels the PRISTINE bundle itself carries have a fixed pixel width
    // (account 208, the other header menu 236, More filters 262, the layer menu 300). The
    // controller's ruling said "six of six ... in the pristine bundle" and counted A13's listbox
    // and A14's Give panel among them; both are AMENDMENTS. A commit of 2026-09-11 claimed that
    // error was "corrected in place" and corrected one of its three copies — this is another.
    // The point survives unchanged: the design does not leave panel widths open, it fixes them,
    // and pristine contains no `max-content` anywhere.
    //
    // So `min-width: 100%` is the SECOND named exception to "every declaration must already
    // appear in the pristine bundle", after the More-filters anchoring pair above. It invents no
    // number for any of the eight controls: it resolves against the `position: relative` wrapper,
    // which IS the trigger. A trip-wire that has become false is worse than none, so the pair is
    // INVERTED rather than deleted — the declaration must sit on this family's two listbox panels
    // and nowhere else, so the exception cannot spread to a third element by accident.
    expect(pristine, 'min-width: 100% is a RULED exception, not the design\'s own — it must stay absent here').not.toContain('min-width: 100%');
    const widthed = amended.split('\n').filter((l) => l.includes('min-width: 100%')).map((l) => l.trim());
    expect(widthed.length, 'A26.16 applies to the two A26 panels and to nothing else').toBe(2);
    for (const line of widthed) expect(line.startsWith('<div role="listbox" '), line).toBe(true);
    expect(widthed[0], 'the toolbar five (A26.10)').toContain('id="{{ fl.listId }}" ref="{{ fl.panelRef }}"');
    expect(widthed[1], 'the three inside More filters (A26.11)').toContain('id="{{ mf.listId }}" ref="{{ mf.panelRef }}"');
    // …and A13's metro panel keeps the width the design measured for it, rather than being
    // quietly swept into the new rule: its field is `min-width: 300px` and its panel 300 px, and
    // pinning the two together is the design's own stated intent for this idiom.
    expect(amended, 'A13\'s metro panel must keep its own 300 px')
      .toContain('id="metro-listbox" ref="{{ marketPanelRef }}" style="position: absolute; left: 0; top: 46px; z-index: 700; width: 300px; padding: 4px;');
  });

  it('A26 turns the five toolbar filters into labelled comboboxes with listbox panels', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // The operating system's popup is gone from the five: no <select> in the `filters` loop.
    expect(pristine).toContain('<select value="{{ fl.value }}" onChange="{{ fl.set }}" style="{{ fl.style }}">');
    expect(amended).not.toContain('onChange="{{ fl.set }}"');
    // A13's own attribute chain, per instance: `role="combobox"` (ARIA 1.2 — the role that
    // supports `aria-activedescendant`, which `button` does not; final review I1), an
    // `aria-label` on every trigger, `aria-controls` to the panel by id, and `tabindex="-1"` on
    // the rows so focus stays on the element that holds the highlight.
    expect(amended).toContain('role="combobox" aria-label="{{ fl.aria }}" aria-haspopup="listbox" aria-controls="{{ fl.listId }}" aria-expanded="{{ fl.open }}" aria-activedescendant="{{ fl.activeId }}"');
    expect(amended).toContain('<div role="listbox" aria-label="{{ fl.aria }}" id="{{ fl.listId }}" ref="{{ fl.panelRef }}"');
    expect(amended, 'aria-activedescendant must sit on the focused trigger, never on the panel')
      .not.toContain('<div role="listbox" aria-label="{{ fl.aria }}" aria-activedescendant=');
    expect((amended.match(/role="option" tabindex="-1"/g) ?? []).length, 'A13\'s row, A26.10\'s and A26.11\'s').toBe(3);

    // Collateral 2 (`screens.ts:59`): `layerTrigger` is
    // `button[aria-haspopup="listbox"]:not([aria-label])`, so the five new triggers are excluded
    // from `.first()`/`.nth(1)` ONLY because each carries an aria-label. Every listbox trigger in
    // the design that is NOT one of the Market data card's two must be labelled.
    const triggers = [...amended.matchAll(/<button[^>]*aria-haspopup="listbox"[^>]*>/g)].map((m) => m[0]);
    expect(triggers.length, 'the metro trigger, the layer trigger, the compare trigger and A26\'s two').toBe(5);
    expect(triggers.filter((t) => !t.includes('aria-label')).length, 'the Market data card\'s two, which screens.ts addresses by exclusion').toBe(2);
  });

  // Task F2 — the three inside the "More filters" popover (A26.3 and A26.11). John called this
  // control the CORRECT implementation, so his words do not cover the three under it; the user's
  // experience does. A native `<select>`'s popup is an operating-system window and renders above
  // the popover's own `z-index: 700`, so converting only the toolbar five would have relocated
  // the dark menu he photographed one click deeper — on top of his own exemplar — rather than
  // removed it. They are also the cheapest three in the tree: no approved state had ever clicked
  // "More filters", so no committed pixel moves and the popover gains its first oracle here.
  it('A26 turns the three inside "More filters" into labelled comboboxes too', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(pristine).toContain('<select value="{{ mf.value }}" onChange="{{ mf.set }}"');
    expect(amended, 'the operating system\'s popup is gone from the popover as well').not.toContain('onChange="{{ mf.set }}"');
    // The design's own visible caption stays exactly where it was — and it also NAMES the
    // trigger. A `<label>` does not name a `<button>`: a button's accessible name is computed
    // from its own contents before the host language's label is consulted, so the caption is
    // spelled again as an `aria-label` rather than a new render key being authored for it.
    expect(amended).toContain('<span style="font-size: 12px; font-weight: 500; color: var(--vf-text);">{{ mf.label }}</span>');
    expect(amended).toContain('role="combobox" aria-label="{{ mf.label }}" aria-haspopup="listbox" aria-controls="{{ mf.listId }}" aria-expanded="{{ mf.open }}" aria-activedescendant="{{ mf.activeId }}"');
    expect(amended).toContain('<div role="listbox" aria-label="{{ mf.label }}" id="{{ mf.listId }}" ref="{{ mf.panelRef }}"');
    expect(amended, 'aria-activedescendant must sit on the focused trigger, never on the panel')
      .not.toContain('<div role="listbox" aria-label="{{ mf.label }}" aria-activedescendant=');
    // The trigger fills the popover's column exactly as the `<select>` did. The `<select>` was a
    // flex item of the `<label>` and stretched; a button inside the new `position: relative`
    // wrapper is not one, so it is told to fill it — with the popover's own declaration, which
    // its "Done" button already carries. Every other declaration is the `<select>`'s, byte for
    // byte, plus the three a label and a chevron need where the user agent drew its own arrow.
    expect(pristine, 'width: 100% is not the design\'s own').toContain('width: 100%');
    expect(amended).toContain('style="display: inline-flex; align-items: center; gap: 8px; width: 100%; height: 38px; padding: 0 10px; font-size: 13px; font-weight: 500; color: var(--vf-navy); background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;"');
    // The `<select>`'s orphaned render keys go with it under the bundle's own dead-code rule,
    // exactly as A13.6/A13.7 and A26.2 dropped theirs: `value:` fed `value="{{ mf.value }}"`,
    // `set:` fed `onChange="{{ mf.set }}"`, and the option rows' `v:` fed `<option value>`.
    for (const dead of ['{{ mf.value }}', '{{ mf.set }}']) expect(amended, `${dead} has no reader left`).not.toContain(dead);
    expect(amended, 'the moreFilters options no longer mint an <option> value').not.toContain('        value: s.f[fl.key] || "Any",');
    // …and the popover's own parent edge (A26.4) still reaches them: `toggleMore` clears the
    // family's keys unconditionally, which closes a child with its parent AND a toolbar
    // dropdown when the parent opens.
    expect(amended).toContain('toggleMore: () => this.setState({ moreFilters: !s.moreFilters, fMenu: null, fMenuAt: -1 }),');
  });

  it('A26 writes ONE open path, so the cross-menu invariant is structural inside the family', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // One `openFilterMenu`, and it is the only place the family names the four overlay menus.
    expect(amended).toContain('  openFilterMenu = (key, at) => {\n    this.setState({ fMenu: key, fMenuAt: at, navMenu: false, userMenu: false, giveMenu: false, marketMenu: false, marketMenuAt: -1 });\n  };');
    expect((amended.match(/fMenu: key, fMenuAt: at/g) ?? []).length, 'a second open path would have to carry the edges by hand').toBe(1);
    // …and the six inbound edges (A26.8a-f), plus the popover parent (A26.4) and go()'s three
    // arms (A26.9). Ten places shut a filter dropdown; the family's own toggle is the eleventh.
    expect((amended.match(/fMenu: null, fMenuAt: -1/g) ?? []).length, 'the filter dropdowns are shut in exactly these places').toBe(16);
  });

  it('A26 leaves Give\'s and the metro\'s three dismissal closures byte for byte (the A14.4 precedent)', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    // The new branch goes AFTER Give's and BEFORE the metro's — the metro branch's guard is an
    // early `return`, so a branch appended after it would be dead while its menu is closed.
    // Both existing branches keep their own bytes, which is what A14.4 proved for A13's.
    expect(amended, 'A26 changed the metro menu\'s outside-click').toContain('      if (!this.state.marketMenu) return;\n      const host = this._marketMenuEl;\n      if (host && e.target && host.contains(e.target)) return;\n      this.setState({ marketMenu: false, marketMenuAt: -1 });');
    expect(amended, 'A26 changed the metro menu\'s Tab dismissal').toContain('      if (!this.state.marketMenu) return;\n      const host = this._marketMenuEl;\n      if (host && host.contains(to)) return;\n      this.setState({ marketMenu: false, marketMenuAt: -1 });');
    expect(amended, 'A26 changed Give\'s pointerdown').toContain('      if (this.state.giveMenu) {\n        const give = this._giveMenuEl;\n        if (!(give && e.target && give.contains(e.target))) this.setState({ giveMenu: false });\n      }');
    expect(amended, 'A26 changed Give\'s Escape').toContain('      if (this.state.giveMenu) {\n        this.setState({ giveMenu: false });\n        if (this._giveButtonEl) this._giveButtonEl.focus();\n      }');
    expect(amended, 'A26 changed Give\'s focusout').toContain('      if (this.state.giveMenu) {\n        const give = this._giveMenuEl;\n        if (!(give && give.contains(to))) this.setState({ giveMenu: false });\n      }');
    // No new listener: the three closures A13.4/A13.8 armed are still the only ones.
    expect((amended.match(/document\.addEventListener/g) ?? []).length).toBe(3);
    // The family's own three branches, each resolving its host through the field the component
    // recorded rather than across the document (A13's rule, final review m5).
    expect(amended).not.toContain('document.getElementById');
    expect((amended.match(/this\._fMenuEls\[this\.state\.fMenu\]/g) ?? []).length, 'pointerdown and focusout').toBe(2);
  });

  // D18 (John, 2026-09-07: "update across the application"). One occurrence in the pristine
  // file — the Insights-tab primary button of the docked panel (V3:705) opens the listing;
  // its label was wrong. The other tabs' "Open full listing" (V3:717) is unified by A11
  // (John, 2026-09-08), below.
  it('A3 replaces the Insights tab\'s "View full market report" with "View full listing" (spec D18), exactly once', () => {
    expect(pristine.split('View full market report').length - 1).toBe(1);
    expect(readFileSync(AMENDED, 'utf8')).not.toContain('View full market report');
    expect(readFileSync(AMENDED, 'utf8')).toContain('View full listing');
  });
  // A11 (John, 2026-09-08: "UNIFY — Change all Browse V3 docked-panel CTAs to 'View full
  // listing', including the Insights tab"). The other tabs' primary button (V3:717,
  // `md.panel.openListing`) took A3's wording, so every docked-panel CTA now reads the same.
  it('A11 unifies the docked panel\'s other-tabs CTA with the Insights tab\'s "View full listing"', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    expect(amended).not.toContain('Open full listing');
    expect(amended.split('View full listing').length - 1).toBe(2);
  });
  it('after A1 every display-size heading in the template is uppercase with V2 tracking (19–22 px → .02em, ≥ 24 px → .005em)', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const figures = /p\.priceLabel|\{\{ c\.value \}\}/;   // `{{ m.v }}` and the 28 px `{{ d.priceLabel }}` are uppercase in V2 and return with A1; the 34 px price is not and V3 already matches it
    const re = /<(\w+)[^>]*?style="([^"]*font-size:\s*(\d+)px[^"]*)"[^>]*>([^<]{0,120})/g; let m: RegExpExecArray | null; let seen = 0;
    const body = amended.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, '');
    while ((m = re.exec(body))) {
      const px = Number(m[3]); if (px < 19 || m[1] === 'p' || figures.test(m[4]) || (m[4].includes('{{ d.priceLabel }}') && px === 34)) continue; seen++;
      expect(m[2], m[4]).toContain('text-transform: uppercase');
      expect(m[2], m[4]).toContain(`letter-spacing: ${px >= 24 ? '.005em' : '.02em'}`);
    }
    // 24 before Task S4; the five account form cards (A8.7) each carry the gate card's own
    // 20 px title, and a heading is a heading — the census counts them too.
    expect(seen).toBe(29);
  });
  // M4/M6 (re-review): the `find`-count contract had no explicit expectation anywhere — the
  // general guard is `applyAmendments`' own `throw`, reachable only through the byte-identity
  // case above, so a future refactor to a plain `replace` chain would drop it silently and the
  // failure would point at the wrong test. It is also the case that states spec D15's contract
  // as implemented: the count is measured at the point the amendment is APPLIED, in list order,
  // because A2.5's `find` is the text A2.4 produces and does not exist in the pristine file.
  it('every `find` occurs exactly `count` times at the point it is applied, in list order (spec D15)', () => {
    // Per FILE, since A24: `applyAmendments` walks one string, and an entry that edits
    // MarketMapV3.jsx can never be counted against the .dc.html (it would read 0 and throw).
    for (const [file, from, to] of [
      ['dc', pristine, readFileSync(AMENDED, 'utf8')],
      ['jsx', readFileSync(PRISTINE_JSX, 'utf8'), readFileSync(AMENDED_JSX, 'utf8')]
    ] as const) {
      let out = from;
      for (const a of amendmentsFor(file)) {
        expect(out.split(a.find).length - 1, `${a.id}: find count at the point of application`).toBe(a.count);
        out = out.split(a.find).join(a.replace);
      }
      expect(out, `${file}: pristine + amendments is not the amended file`).toBe(to);
    }
    // The ordering dependency itself, named: A2.5 matches A2.4's output, so it cannot be counted
    // against the pristine file and the two may never be reordered.
    const list = amendments();
    const a24 = list.find((a) => a.id === 'A2.4')!; const a25 = list.find((a) => a.id === 'A2.5')!;
    expect(list.indexOf(a24)).toBeLessThan(list.indexOf(a25));
    expect(pristine.split(a25.find).length - 1, 'A2.5 is expected to be absent from the pristine file').toBe(0);
    expect(a24.replace.trim() + '\n', 'A2.5 must match what A2.4 leaves behind').toContain(a25.find.trim());
  });
  it('applyAmendments refuses a list whose `find` count does not match, naming the amendment', () => {
    const bogus = { id: 'A0', date: '2026-09-07', ruling: 'a fabricated entry', find: 'View full market report', replace: 'x', count: 2 };
    expect(() => applyAmendments(pristine, [bogus])).toThrow(/A0: expected 2 match\(es\).*found 1/);
  });
  // M7 (re-review): `setDecl`'s removal path (`value === null`) is never taken by A1 against the
  // two design files — V2 declares `text-transform`/`letter-spacing` wherever V3 does — so the
  // rule "take V2's VALUES, including its absence" was asserted by nothing. This is that case,
  // on two synthetic files: V2 lacks a declaration V3 has, so the amendment must delete it.
  it('A1 removes a declaration V3 has and V2 does not (setDecl\'s removal path)', () => {
    const v2 = '<div style="font-size: 24px; color: red">Heading</div>';
    const v3 = '<div style="font-size: 24px; text-transform: uppercase; color: red">Heading</div>';
    const a1 = deriveTypographyB(v2, v3);
    expect(a1, 'the removal path produced no amendment: V3 keeps a declaration V2 does not have').toHaveLength(1);
    expect(a1[0].find).toBe('style="font-size: 24px; text-transform: uppercase; color: red">Heading');
    expect(a1[0].replace, 'the declaration V2 does not carry must be gone').toBe('style="font-size: 24px; color: red">Heading');
    expect(applyAmendments(v3, a1)).toBe(v2);
  });
  // The other half of the same rule, and the other half of `setDecl`'s append path: V2 carries a
  // declaration V3 dropped, on a style that does NOT end in a semicolon, so the appended
  // declaration has to bring one with it. Every real A1 style ends in `;`, so this variant is
  // reachable only from a synthetic pair (M7: the engine is now inside the coverage gate).
  it('A1 adds a declaration V2 has and V3 dropped, semicolon and all', () => {
    const v2 = '<div style="font-size: 24px; color: red; text-transform: uppercase">Heading</div>';
    const v3 = '<div style="font-size: 24px; color: red">Heading</div>';
    const a1 = deriveTypographyB(v2, v3);
    expect(a1, 'V3 dropped a declaration V2 carries and no amendment was derived').toHaveLength(1);
    expect(a1[0].replace).toBe('style="font-size: 24px; color: red; text-transform: uppercase;">Heading');
    expect(applyAmendments(v3, a1)).toBe('<div style="font-size: 24px; color: red; text-transform: uppercase;">Heading</div>');
  });
  // M5 (re-review): the row regex was `^\|\s*(A\d+)\s*\|`, which required the pipe immediately
  // after the digits — it matched `| A1 |`, `| A2 |`, `| A3 |`, `| A4 |` and skipped all four
  // `| A2.2 |`–`| A2.5 |` rows. The file held eight rows and the test read four, so an `A2.6`
  // row with no code (or an `A2.6` amendment with no row) was invisible and the duplicate guard
  // covered only the top-level ids. The id set is now compared in full, both ways.
  // M4 (review round 1): the rows had drifted out of order — A5.7 above A5.6, A4 below A5.x, the
  // A6/A7 block appended after everything. The set case below could not see it, and the file is
  // read by people. The order that matters is the order the edits are APPLIED, which is also the
  // order the ids are pinned in above.
  it('LOCAL_AMENDMENTS.md lists its rows in the order the amendments are applied', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    const rows = [...md.matchAll(/^\|\s*(A[\w.]+)\s*\|/gm)].map((m) => m[1]);
    expect(rows).toEqual([...new Set(amendments().map((a) => (a.id.startsWith('A1.') ? 'A1' : a.id)))]);
  });

  // Fix round 1 (Minor): A8.1b's row paraphrased its amendment's `ruling` instead of quoting it,
  // and nothing could see the difference — the two set cases below compare IDS, not text. A row
  // that says something other than the ruling it documents is the drift D15 exists to prevent, so
  // the ruling column is now the `ruling` field, byte for byte, for every amendment. (The "What
  // changes" column is free prose and is not compared: it is the row's own explanation.)
  it('every LOCAL_AMENDMENTS.md row quotes its amendment\'s ruling verbatim', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    const cells = new Map([...md.matchAll(/^\|\s*(A[\w.]+)\s*\|[^|]*\|\s*(.*?)\s*\|/gm)].map((m) => [m[1], m[2]]));
    for (const a of amendments()) {
      const id = a.id.startsWith('A1.') ? 'A1' : a.id;
      expect(cells.get(id), `${a.id}: LOCAL_AMENDMENTS.md has no row`).toBeDefined();
      expect(cells.get(id), `${id}: the row's ruling is not the amendment's`).toBe(a.ruling);
    }
    // A1's 24 derived edits collapse to one row, which is only meaningful because they share one
    // ruling — asserted rather than assumed.
    expect(new Set(amendments().filter((a) => a.id.startsWith('A1.')).map((a) => a.ruling)).size).toBe(1);
  });

  // ---------------------------------------------------------------------------------------
  // A-L11 re-review. Most rows cite the line their edit lands on (`V3:2407`), and NOTHING checked
  // them: A15 inserted twelve lines into `photoSet` and every citation below it silently became a
  // pointer to the wrong line — A12.6's row said 2450 while its edit had been at 2931 since the
  // account screens landed. A citation nobody can follow is worse than none, so it is measured.
  //
  // The rule: for every `V3:<line>` a row carries, that line of the AMENDED file — or one either
  // side of it, so a citation may name the anchor a multi-line edit starts from — must contain a
  // line of what that amendment PUT there.
  //
  // Two shapes need care, and neither is skipped:
  //   * A SUPERSEDED amendment (A10, whose `replace` is A10.2's `find`) has no output left in the
  //     file. Its row is validated against the text that stands at its site today — which is what
  //     a reader following the citation will actually see — by following the chain forward.
  //   * A1's 24 derived edits collapse to ONE row (`| A1 |`), which cites no line at all today;
  //     were one added, it is validated against the union of those 24 in-place style edits.
  // A pure REMOVAL amendment (A6's) has no output to point at and must not carry a citation; the
  // assertion below says so rather than passing vacuously.
  // ---------------------------------------------------------------------------------------
  it('every V3:<line> citation in LOCAL_AMENDMENTS.md lands on the line that amendment produced', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    const fileLines = readFileSync(AMENDED, 'utf8').split('\n');
    const list = amendments();
    const trimmed = (text: string) => text.split('\n').map((s) => s.trim()).filter(Boolean);
    /** What stands at this amendment's site in the amended file: its own `replace`, or — when a
     *  later amendment's `find` swallowed that `replace` whole — whatever superseded it. */
    const outputOf = (a: Amendment): string[] => {
      const later = list.slice(list.indexOf(a) + 1).find((b) => b.find.includes(a.replace));
      return later ? outputOf(later) : trimmed(a.replace);
    };
    // H3 (controller, 2026-09-11): this loop used to `expect(...).toBe(true)` inline, so the
    // FIRST stale citation threw and the run stopped there — correct (it went red), but it
    // named one of however many were actually stale and left a reader to conclude there was
    // only one. Every citation is still checked, and every stale one is collected, so a single
    // run names all of them.
    let checked = 0;
    const stale: string[] = [];
    for (const row of md.split('\n')) {
      const id = /^\|\s*(A[\w.]+)\s*\|/.exec(row)?.[1];
      if (id === undefined) continue;
      // BOTH ENDS of a range, not only the first number (Task MP1). `V3:1974–1969` and
      // `V3:2613-2431` both stood in this file with an end left behind by an earlier
      // re-map, and both passed: the pattern stopped at the first number, so the half of
      // the citation a reader uses to find the END of a multi-line edit was never measured.
      const cited = [...row.matchAll(/V3:(\d+)(?:[\u2013-](\d+))?/g)].flatMap((c) => [Number(c[1]), ...(c[2] ? [Number(c[2])] : [])]);
      if (cited.length === 0) continue;
      const own = id === 'A1' ? list.filter((a) => a.id.startsWith('A1.')) : list.filter((a) => a.id === id);
      expect(own.length, `${id}: the row cites a V3 line but no amendment carries that id`).toBeGreaterThan(0);
      const output = own.flatMap(outputOf);
      expect(output.length, `${id}: a removal amendment puts nothing at a line, so its row may not cite one`).toBeGreaterThan(0);
      for (const n of cited) {
        const window = [n - 1, n, n + 1].map((k) => fileLines[k - 1] ?? '');
        if (!window.some((line) => output.some((piece) => line.includes(piece)))) {
          stale.push(`${id}: V3:${n} is stale — that line of the amended design holds none of this amendment's text`);
        }
        checked++;
      }
    }
    expect(stale, `${stale.length} stale citation(s) found`).toEqual([]);
    // Not a vacuous pass: the parser must actually have found the rows and their citations.
    expect(checked, 'no V3 citation was checked — the row or citation pattern stopped matching').toBeGreaterThan(20);
  });

  // ---------------------------------------------------------------------------------------
  // A28 (John, 2026-09-11, ruling D-C44). Two parts, one change: the ring is drawn at the
  // distance the Community Context card names, and the legacy panel's orphans go.
  //
  // The family is asserted on the OUTPUT of both bundle files, and both directions are measured:
  // the PRISTINE bundle must still carry what A28 removes, or the removal assertions would pass
  // against a file that never had them and this case would protect nothing.
  // ---------------------------------------------------------------------------------------
  it('A28.1 draws the ring at the 8 000 m band the card names, in V2\'s own colour for it', () => {
    const jsx = readFileSync(AMENDED_JSX, 'utf8');
    const pristineJsx = readFileSync(PRISTINE_JSX, 'utf8');
    // The pristine file is the mash-up D-C44 describes: V2's FAR radius in V2's NEAR colour.
    expect(pristineJsx, 'the pristine bundle no longer carries the 16 000 m ring A28.1 corrects')
      .toContain('radius: 16000, color: "#003a70"');
    expect(jsx).toContain('radius: 8000, color: "#003a70", weight: 1.5, dashArray: "4 4"');
    expect(jsx, 'the ten-mile radius is still drawn somewhere in the component').not.toContain('16000');
    // Only the radius moved: the rest of the declaration, and the finite-point test A25.6 gave
    // `showDrive` (in the .dc.html, not here), are untouched.
    expect(jsx).toContain('fill: false, interactive: false');
    expect(jsx.split('L.circle(').length - 1, 'A28.1 added or removed a circle').toBe(pristineJsx.split('L.circle(').length - 1);
    // A28.1 was the only jsx entry when this case was written, and the first the programme ever
    // had; the A24 merge (real Census boundary polygons, 2026-09-11) added the four the partition
    // was built for, and they are appended after it because A24 is appended after A28 in
    // `amendments()`. The list is spelled out rather than counted so an entry that silently
    // changes file still fails here.
    expect(amendmentsFor('jsx').map((a) => a.id)).toEqual(['A28.1', 'A24.9', 'A24.10', 'A24.11', 'A24.12']);
  });

  it('A28.2-A28.4 delete the legacy panel\'s orphans, and the last "drive time" strings with them', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const gone of ['fillRows', 'overlayRows', 'layerHelp', 'drive5', 'drive10', 'GROUP 1 —', 'GROUP 2 —']) {
      // Both directions: the pristine bundle HAS it (so the assertion below is not vacuous) and
      // the amended design does not.
      expect(pristine, `the pristine bundle no longer carries ${gone}`).toContain(gone);
      expect(amended, `A28 left ${gone} in the design`).not.toContain(gone);
    }
    // The point of the deletion, in John's own terms: no "drive time" string is left anywhere.
    expect(amended, 'a "drive time" string survives in the design').not.toContain('drive time');
    // The LIVE members of the layer defaults stay, in the design's own order. A28.4 took the two
    // flags the deleted rows were the sole reader of; A28.9 (whole-branch review, 2026-09-11)
    // then took `practices`, the third — `SYMBOL_KEYS` is `["pets", "households", "competition"]`
    // and A28.2's own deleted `layerRow("practices", …)` was the only thing that ever read it.
    // What is left is exactly `SYMBOL_KEYS`, which `activeSymbols` reads on every render.
    expect(pristine, 'the pristine bundle no longer carries the practices default A28.9 removes')
      .toContain('{ practices: true, drive5: true, drive10: true, competition: true, households: false, pets: false },');
    expect(amended).toContain('{ competition: true, households: false, pets: false },');
    expect(amended, 'A28.9 left the orphaned practices default in the design').not.toContain('practices: true');
  });

  // D-C45 (controller amendment, 2026-09-11): the four helpers A28.2/A28.3's deleted rows were
  // the only callers of go too, under the same dead-code rule. Both directions again — the
  // pristine bundle still declares all four (so the removal assertion is not vacuous) and the
  // amended design declares none of them.
  it('A28.5-A28.8 delete the helpers those rows called, the last piece of the same dead code', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    for (const gone of ['const layerRow = ', 'const radioRow = ', 'const setValue = ', 'const setLayer = ']) {
      expect(pristine, `the pristine bundle no longer declares ${gone.trim()}`).toContain(gone);
      expect(amended, `A28.5-A28.8 left ${gone.trim()} in the design`).not.toContain(gone);
    }
    // Each deletion took its own trailing blank line, so no double-blank or orphaned separator
    // is left behind: `minLng` and the footer-card switch that used to sit three declarations
    // away are now adjacent, with exactly the one blank line the design had between them.
    expect(amended).toContain(
      '    const minLng = Math.min.apply(null, lngs) - pad, maxLng = Math.max.apply(null, lngs) + pad;\n'
      + '\n'
      + '    // A footer card is the SOURCE switch for its dataset: off means the dataset\n'
    );
  });

  it('LOCAL_AMENDMENTS.md carries exactly one table row per amendment id (A1 collapsed to one)', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    // `[\w.]`, not `[\d.]`: A-I8's ids include a letter suffix where one ruling needed two edits
    // (`A5.3a`/`A5.3b`), and the digits-only class silently skipped those rows — the same class of
    // hole as M5's missing pipe, which is what this case exists to catch.
    const rows = [...md.matchAll(/^\|\s*(A[\w.]+)\s*\|/gm)].map((m) => m[1]);
    expect(new Set(rows).size, 'an amendment is documented twice').toBe(rows.length);
    // A1 derives 24 edits (`A1.1`…`A1.24`) from ONE ruling and is documented as one row; every
    // other id is literal and must appear in the file exactly as `amendments()` spells it.
    expect(new Set(rows)).toEqual(new Set(amendments().map((a) => (a.id.startsWith('A1.') ? 'A1' : a.id))));
  });
});

/**
 * `a.find`/`a.replace` with the two declarations A1 is allowed to change removed, and the
 * whitespace those removals leave behind normalised — `setDecl` appends a declaration after a
 * space and deletes it with its leading space, so a legitimate edit differs from its source by
 * whitespace at the seam and by nothing else.
 */
function withoutTypography(s: string): string {
  return s.replace(/(text-transform|letter-spacing):\s*[^;"]*;?/g, '')
    .replace(/\s+/g, ' ').replace(/ ;/g, ';').replace(/ "/g, '"').trim();
}
