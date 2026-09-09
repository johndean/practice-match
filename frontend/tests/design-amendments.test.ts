import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AMENDED, type Amendment, LOCAL_AMENDMENTS_MD, PRISTINE, amendments, applyAmendments, deriveTypographyB, templateRegions, V2 } from './design-amendments';

describe('local design amendments (spec D15)', () => {
  const pristine = readFileSync(PRISTINE, 'utf8');
  // D15 makes the pristine copy the authority every amendment is measured from, so it needs an
  // oracle of its own: without one, a consistent edit to BOTH the pristine file and the amended
  // file keeps every other case green while "pristine, never edited" quietly stops being true.
  // This hash changes only when a re-issued bundle lands (and then the amendments retire with it).
  it('the pristine Rev 2 copy is the bundle\'s file, untouched', () => {
    expect(createHash('sha256').update(readFileSync(PRISTINE)).digest('hex')).toBe('335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d');
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
    // A15 — every uploaded photograph renders, with its own description (A-L11, John 2026-09-09).
    // A13/A14 are reserved by the design-dropdowns branch. Six literal script edits: a
    // photograph's own `photoCaptions[i]` wins over the design's fixed slot caption (A15.1/A15.2)
    // and every photograph past the sixth gets a tile of its own (A15.3a–A15.3d, the two ends of
    // each branch's `return`). The fixtures carry no `photos` and no `photoCaptions` at all, so
    // both guards are falsey and no approved state moves.
    'A15.1', 'A15.2', 'A15.3a', 'A15.3b', 'A15.3c', 'A15.3d',
    // A16 — the seller wizard and dashboard read and write the real API (spec D23, controller
    // amendments A-SL17/A-SL20/A-SL22). A13 and A14 are the dropdown branch's; the family id is
    // derived from the tree at branch time (A-SL4), never typed from the plan, which is why this
    // one is 16.
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
  ];

  it('amendments() is exactly the pinned id list, in the pinned order, and nothing else', () => {
    expect(amendments().map((a) => a.id)).toEqual(AMENDMENT_IDS);
    expect(amendments(), 'the count, stated as a number as well as a list').toHaveLength(114);
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

  it('the amended reference is the pristine Rev 2 file plus exactly the ruled edits', () => {
    expect(applyAmendments(pristine, amendments())).toBe(readFileSync(AMENDED, 'utf8'));
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
    let out = pristine;
    for (const a of amendments()) {
      expect(out.split(a.find).length - 1, `${a.id}: find count at the point of application`).toBe(a.count);
      out = out.split(a.find).join(a.replace);
    }
    expect(out).toBe(readFileSync(AMENDED, 'utf8'));
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
    let checked = 0;
    for (const row of md.split('\n')) {
      const id = /^\|\s*(A[\w.]+)\s*\|/.exec(row)?.[1];
      if (id === undefined) continue;
      const cited = [...row.matchAll(/V3:(\d+)/g)].map((c) => Number(c[1]));
      if (cited.length === 0) continue;
      const own = id === 'A1' ? list.filter((a) => a.id.startsWith('A1.')) : list.filter((a) => a.id === id);
      expect(own.length, `${id}: the row cites a V3 line but no amendment carries that id`).toBeGreaterThan(0);
      const output = own.flatMap(outputOf);
      expect(output.length, `${id}: a removal amendment puts nothing at a line, so its row may not cite one`).toBeGreaterThan(0);
      for (const n of cited) {
        const window = [n - 1, n, n + 1].map((k) => fileLines[k - 1] ?? '');
        expect(
          window.some((line) => output.some((piece) => line.includes(piece))),
          `${id}: V3:${n} is stale — that line of the amended design holds none of this amendment's text`
        ).toBe(true);
        checked++;
      }
    }
    // Not a vacuous pass: the parser must actually have found the rows and their citations.
    expect(checked, 'no V3 citation was checked — the row or citation pattern stopped matching').toBeGreaterThan(20);
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
