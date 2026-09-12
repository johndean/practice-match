import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { DESIGN_AREAS_LITERAL } from './design-boundary-fixture';

const V3_DIR = new URL('../../docs/design-reference/design_handoff_practice_match_v3/', import.meta.url);
export const PRISTINE = fileURLToPath(new URL('Practice Match V3.rev2.dc.html', V3_DIR));
export const AMENDED = fileURLToPath(new URL('Practice Match V3.dc.html', V3_DIR));
// The bundle's second amendable file (spec §9.2; controller ruling 2026-09-10 §14 Q3). A24 is the
// first family that has to reach `MarketMapV3.jsx` — the component that draws the shading — and
// the engine had only ever known the `.dc.html`. Same contract on both: a frozen pristine twin
// that is never edited, plus the ruled edits, equals the amended file byte for byte.
export const PRISTINE_JSX = fileURLToPath(new URL('MarketMapV3.rev2.jsx', V3_DIR));
export const AMENDED_JSX = fileURLToPath(new URL('MarketMapV3.jsx', V3_DIR));
export const V2 = fileURLToPath(new URL('../../docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html', import.meta.url));
export const LOCAL_AMENDMENTS_MD = fileURLToPath(new URL('LOCAL_AMENDMENTS.md', V3_DIR));

/** Which bundle file an amendment edits. Absent means `'dc'`, so every entry written before A24
 *  is unchanged and the field never has to be back-filled. */
export type AmendmentFile = 'dc' | 'jsx';

export type Amendment = { id: string; date: string; ruling: string; find: string; replace: string; count: number; text?: string; file?: AmendmentFile };

/** The template region: everything outside <script>…</script> and <style>…</style>. A1 must never touch a script. */
export function templateRegions(html: string): Array<[number, number]> {
  const regions: Array<[number, number]> = [];
  const skip = /<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g;
  let last = 0; let m: RegExpExecArray | null;
  while ((m = skip.exec(html))) { regions.push([last, m.index]); last = m.index + m[0].length; }
  regions.push([last, html.length]);
  return regions;
}

type Styled = { tag: string; text: string; style: string; rest: string; start: number; end: number; fontPx: number | null };
const STYLED = /<(\w+)([^>]*?)style="([^"]*)"([^>]*)>([^<]{0,120})/g;
function styledElements(html: string): Styled[] {
  const out: Styled[] = [];
  for (const [a, b] of templateRegions(html)) {
    const slice = html.slice(a, b); let m: RegExpExecArray | null; STYLED.lastIndex = 0;
    while ((m = STYLED.exec(slice))) {
      const fs = /font-size:\s*([\d.]+)px/.exec(m[3]);
      const styleStart = a + m.index + m[0].indexOf('style="') + 7;
      out.push({ tag: m[1], text: m[5].trim(), style: m[3], rest: m[4], start: styleStart, end: styleStart + m[3].length, fontPx: fs ? Number(fs[1]) : null });
    }
  }
  return out;
}
const decl = (style: string, prop: string) => { const m = new RegExp(`(?:^|;)\\s*${prop}:\\s*([^;]+)`).exec(style); return m ? m[1].trim() : null; };

/** Set, replace or remove ONE declaration in place — never reorders the others (a reorder is a byte change with no rendered effect, and would be a spurious amendment). */
function setDecl(style: string, prop: string, value: string | null): string {
  const present = new RegExp(`(^|;)(\\s*)${prop}:\\s*[^;]+(;?)`);
  if (value === null) return style.replace(new RegExp(`\\s*${prop}:\\s*[^;]+;?`), '').replace(/^\s+/, '');
  if (present.test(style)) return style.replace(present, `$1$2${prop}: ${value}$3`);
  const t = style.trim(); return `${t}${t.endsWith(';') ? '' : ';'} ${prop}: ${value};`;
}

/** A1 — V2 typography (spec D16, corrected 2026-09-07 after the V13 STOP). Rule-based and evidence-only: an element paired with V2 by its unique
 *  (tag, text, size) key takes V2's `text-transform` and `letter-spacing` VALUES wherever they differ from V3's, edited in place. Elements whose two
 *  declarations already equal V2's produce NO amendment. Unpaired elements — and elements whose key is not unique on one side — are never touched
 *  (that rule is what keeps `{{ resultHeadline }}` alone: V3's only occurrence is the mobile list's, byte-identical to V2's; V2's 19 px desktop one
 *  lived in the Browse column V3 replaced by design). The key carries the font size so that same-text elements V2 sized and styled
 *  differently (the 34 px and 28 px `{{ d.priceLabel }}`) pair with their own counterpart instead of being dropped as ambiguous. */
export function deriveTypographyB(v2Html: string, pristineHtml: string): Amendment[] {
  const key = (e: Styled) => `${e.tag}|${e.text}|${e.fontPx ?? ''}`;   // the size disambiguates the two `{{ d.priceLabel }}` (34 px desktop, 28 px mobile) — V2 styles them differently on purpose
  const uniq = (els: Styled[]) => { const c = new Map<string, number>(); els.forEach((e) => c.set(key(e), (c.get(key(e)) ?? 0) + 1)); return new Map(els.filter((e) => c.get(key(e)) === 1).map((e) => [key(e), e])); };
  const v2 = uniq(styledElements(v2Html)); const v3u = uniq(styledElements(pristineHtml));
  const out: Amendment[] = [];
  for (const [k, e3] of v3u) {
    const e2 = v2.get(k); if (!e2) continue;
    let next = e3.style;
    for (const prop of ['text-transform', 'letter-spacing']) { const want = decl(e2.style, prop); if (want !== decl(e3.style, prop)) next = setDecl(next, prop, want); }
    if (next === e3.style) continue;
    out.push({ id: `A1.${out.length + 1}`, date: '2026-09-07', ruling: 'keep the V2 header and do not restyle header or fonts',
      find: `style="${e3.style}"${e3.rest}>${e3.text}`, replace: `style="${next}"${e3.rest}>${e3.text}`, count: 1, text: e3.text });
  }
  return out;
}

export function applyAmendments(html: string, list: Amendment[]): string {
  let out = html;
  for (const a of list) {
    const n = out.split(a.find).length - 1;
    if (n !== a.count) throw new Error(`${a.id}: expected ${a.count} match(es) of ${JSON.stringify(a.find.slice(0, 60))}, found ${n}`);
    out = out.split(a.find).join(a.replace);
  }
  return out;
}

/** The entries that edit one bundle file, in `amendments()`' own order. `applyAmendments` counts
 *  every `find` at the point it is applied, so the partition has to preserve order: an entry whose
 *  `find` is an earlier entry's output is only correct where that earlier entry has already run. */
export function amendmentsFor(file: AmendmentFile): Amendment[] {
  return amendments().filter((a) => (a.file ?? 'dc') === file);
}

/** A2 — the mobile practice card opens the detail (spec D17, John: "resolve this"). A literal, not
 *  rule-derived, entry: it edits the design's SCRIPT (the mobile card's `open` handler in `results`),
 *  not the template, so it is exempt from A1's "inside a template region" check (that check runs
 *  only over `deriveTypographyB`'s own output, never over the combined `amendments()` list). Root
 *  cause (task V14 report): `open` set `browseSel`, which C13 left nothing to read once it removed
 *  the peek card that used to display it — the tap was a no-op. It now navigates directly, the way
 *  V2's card and C13's own second-pin-tap (`mobileVals.selectMarker`) both do.
 */
const A2: Amendment = {
  id: 'A2', date: '2026-09-07', ruling: 'resolve this — the mobile practice card opens the detail (spec D17)',
  find: 'open: () => this.setState({ browseSel: p.id, activeId: p.id }),',
  replace: 'open: () => this.setState({ screen: "detail", detailId: p.id }),', count: 1
};

/** A2.2 — the comment above the handler A2 just changed described the OLD (dead) behaviour;
 *  it now describes what the handler actually does (zero-gaps review). */
const A2_2: Amendment = {
  id: 'A2.2', date: '2026-09-07', ruling: 'the amended handler’s comment now matches what it does (zero-gaps review)',
  find: '// Select into the docked side panel rather than navigating to a separate page.',
  replace: "// Open the practice detail (John's ruling, 2026-09-07; C13 left no peek card to select into).",
  count: 1
};

/** A2.3 — the bundle's own dead-code rule (spec D8/D12: a dead mapping is dead code), applied to
 *  the design's script through the amendment mechanism. `hasBrowseSel`, `closeBrowseSel` and `bsel`
 *  all read or wrote `browseSel`; C13 removed the peek card that was their only template reader, and
 *  none of the three is referenced anywhere else (verified: zero matches outside the script for
 *  `hasBrowseSel`, `closeBrowseSel` or `bsel`). All three keys are deleted outright. `isBrowse:
 *  false` immediately above them is a DIFFERENT, still-vestigial-but-unrelated key (README §7 risk
 *  register) and is left untouched. */
const A2_3: Amendment = {
  id: 'A2.3', date: '2026-09-07', ruling: 'delete the orphaned browseSel helpers (zero-gaps review, spec D8/D12)',
  find: "      hasBrowseSel: !!s.browseSel,\n      closeBrowseSel: () => this.setState({ browseSel: null }),\n      bsel: (() => {\n        const p = P.filter((x) => x.id === s.browseSel)[0];\n        if (!p) return { facts: [] };\n        const bldg = p.bldg === \"Included\" ? \"Included in sale\" : p.bldg === \"Separate\" ? \"Available separately\" : \"Leased — assignable\";\n        return {\n          eyebrow: p.type,\n          name: this.practiceName(p),\n          place: p.area + \", \" + this.stateOf(p.market || \"Austin, TX\"),\n          priceLabel: this.money(p.price),\n          photoId: \"ph-\" + p.id + \"-exterior\",\n          photoSrc: this.heroSrc(p),\n          note: p.note,\n          facts: [\n            { k: \"Gross revenue\", v: this.money(p.rev) + \" (seller-stated)\" },\n            { k: \"Doctors\", v: p.docs + \" full-time equivalent\" },\n            { k: \"Exam rooms\", v: String(p.rooms) },\n            { k: \"Square feet\", v: p.sqft.toLocaleString() },\n            { k: \"Property\", v: bldg },\n            { k: \"Established\", v: String(p.est) }\n          ],\n          openFull: () => this.setState({ screen: \"detail\", detailId: p.id })\n        };\n      })(),\n",
  replace: '', count: 1
};

/** A2.4 — the top-level `selectMarker` (distinct from `mobileVals.selectMarker`, which C13 already
 *  points at the detail screen) is not wired to any template prop, but it still wrote the same dead
 *  `browseSel` key on every call, alongside the live `activeId` key. The dead key is dropped; the
 *  live key and the handler itself are otherwise untouched — this is not the "select into the docked
 *  panel" flow (`md.selectFromMap`), which A2/A2.2/A2.3 do not touch. */
const A2_4: Amendment = {
  id: 'A2.4', date: '2026-09-07', ruling: 'drop the dead browseSel key, keep the live activeId key (zero-gaps review, spec D8/D12)',
  find: 'selectMarker: (id) => this.setState({ browseSel: id, activeId: id }),',
  replace: 'selectMarker: (id) => this.setState({ activeId: id }),', count: 1
};

/** A2.5 — same dead-code rule again: the top-level `selectMarker` A2.4 just trimmed is itself
 *  never wired to any template prop. The only `on-select` bindings in the whole design are
 *  `mob.selectMarker` (the mobileVals one, C13's own fix) on the mobile map mount and
 *  `md.selectFromMap` on the desktop one — confirmed by grep against both the template region
 *  and the built `App.vue`. Deleted outright, together with the now-orphaned blank line above
 *  `isDetail:` it would otherwise leave doubled. */
const A2_5: Amendment = {
  id: 'A2.5', date: '2026-09-07', ruling: 'delete the unwired top-level selectMarker (zero-gaps review, same dead-code rule as A2.3)',
  find: '      selectMarker: (id) => this.setState({ activeId: id }),\n',
  replace: '', count: 1
};

/** A3 — the Insights-tab primary button of the docked panel (spec D18, John: "update across the
 *  application 'view full market report' to 'View full listing'"). A literal template edit (a
 *  text node, V3:705): one occurrence in the pristine file. The other tabs' "Open full listing"
 *  (V3:717) was not part of John's instruction and was left as designed, flagged to him in the
 *  V15 report for possible unification — A11, below, is that unification. */
const A3: Amendment = {
  id: 'A3', date: '2026-09-07', ruling: 'update across the application "view full market report" to "View full listing"',
  find: 'View full market report', replace: 'View full listing', count: 1
};

/** A4 — Compare hides the "What this means" card (spec D21, John: "if user clicks + Compare
 *  that action 'closes' the 'What this means card' and when X Compare is clicked it closes
 *  the compare and 'What this means card' appears again"). A literal, not rule-derived, entry:
 *  it edits the design's SCRIPT (the `insightOpen` IIFE inside `marketVals`), not the template,
 *  so — like A2 — it is exempt from A1's "inside a template region" check. One condition is
 *  added to the existing expression; nothing else about `insightOpen`'s gating (a value layer,
 *  an undismissed member, the mapW >= 810 width gate) changes. */
const A4: Amendment = {
  id: 'A4', date: '2026-09-07',
  ruling: "if user clicks + Compare that action closes the 'What this means' card; when X Compare is clicked it closes the compare and the card appears again (spec D21)",
  find: '        return !!valueLayer && !s.mdInsightOff && s.mdLegendOff !== true && mapW >= 810;',
  replace: '        return !!valueLayer && !s.mdInsightOff && s.mdLegendOff !== true && !s.mdCompareOpen && mapW >= 810;', count: 1
};

/** A5.1 — sign-in through the `auth` adapter (amendment A-I8; spec §"Prototype wiring" step 2).
 *
 *  A literal script edit, like A2 and A4. `this.props.auth` is the prototype's other hook: the app
 *  passes the real `/api/auth/*` client, and the reference — which has no `auth` prop and no API —
 *  keeps the design's fixture path exactly as it shipped, which is what keeps the two targets on
 *  the same pixels.
 *
 *  The refusal message rendered is the SERVER's own: `INVALID_CREDENTIALS` and `RATE_LIMITED` are
 *  both 4xx on the same form and want different copy, and `src/auth/api.ts` deliberately carries
 *  the API's prose rather than an identifier. `|| "Sign-in failed."` covers a rejection that
 *  carries none.
 *
 *  The handler RETURNS the adapter's promise, so a caller can await the settled state; the
 *  design's own button ignores the return value, exactly as it ignored the fixture path's
 *  `undefined`. The empty-form validation above it is untouched — it must refuse before it spends
 *  a request against a rate-limited endpoint (its wording is A7.2's).
 */
const A5_1: Amendment = {
  id: 'A5.1', date: '2026-09-07',
  ruling: 'spec §"Prototype wiring" step 2: the prototype signs in through the API; the reference keeps the fixture path because it has no auth prop',
  find: '        this.setState({ screen: "browse", formError: "", auth: true });\n      },\n      signedIn: !!s.auth,',
  replace: '        if (!this.props.auth) return this.setState({ screen: "browse", formError: "", auth: true });\n'
    + '        return this.props.auth.signIn(s.email, s.pw).then(\n'
    + '          (me) => this.setState({ screen: "browse", formError: "", auth: true, email: me.email, me: { name: me.name, role: me.role, initials: me.initials } }),\n'
    + '          (e) => this.setState({ formError: (e && e.message) || "Sign-in failed.", auth: false, screen: "gate" })\n'
    + '        );\n'
    + '      },\n'
    + '      signedIn: !!s.auth,',
  count: 1
};

/** A5.3a/b — sign-out through the adapter (amendment A-I8). Two literal edits, because the
 *  handler's `setState` object spans several lines: (a) wraps the call in the adapter's promise,
 *  (b) closes the extra parenthesis that wrap opened.
 *
 *  `.catch(() => {})` on the API call, deliberately: the reset must happen whatever the network
 *  did. A failed sign-out that left the member looking signed in — with a session the server may
 *  well have already revoked — is the worse of the two failures, and the server-side session is
 *  what actually authorises anything.
 */
const A5_3a: Amendment = {
  id: 'A5.3a', date: '2026-09-07',
  ruling: 'spec §"Prototype wiring" step 2: sign-out ends the real session, and resets whatever the network did',
  find: '      signOut: () => this.setState({',
  replace: '      signOut: () => (this.props.auth ? this.props.auth.signOut().catch(() => {}) : Promise.resolve()).then(() => this.setState({',
  count: 1
};
const A5_3b: Amendment = {
  id: 'A5.3b', date: '2026-09-07',
  ruling: 'closes the parenthesis A5.3a opened (same ruling)',
  find: '      }),\n      goHome: this.go("gate"),',
  replace: '      })),\n      goHome: this.go("gate"),',
  count: 1
};

/** A5.4 — the bootstrap reads the account the app loaded from `/api/me`, and the `startGate`
 *  prototype prop (amendment A-I8, ordering A-I8.1). A literal script edit, like A2 and A4.
 *
 *  `this.props.me` is the ONE hook a real session reaches the approved prototype through:
 *  `src/main.ts` awaits `useMe().load()` before `bootstrap()` and `src/app.setup.js` passes the
 *  payload down, so `componentDidMount` can put the visitor where the spec's account lifecycle
 *  says they belong. The reference and the Claude Design preview pass no `me` at all and take
 *  the design's own fixture path unchanged — which is what keeps the oracle and the app on the
 *  same pixels.
 *
 *  `unverified` is deliberately unmapped: it has nowhere to go until I8c's "check your email"
 *  screen exists, and "absent beats faked" forbids inventing one, so it falls through to the
 *  sign-in gate. (That card exists as of Task S4, and A8.3b maps it.) `verified → apply` is the
 *  D-I8-5 rider: an address that has never applied.
 *
 *  `startGate` is the reference's way into a gate state now that A6.2 takes the "Prototype —
 *  access states" shortcuts out; `tests/reference-server.mjs` injects it through `?props=`.
 *
 *  A SET `startScreen` WINS over the account's landing screen (review round 1, I1). The branch
 *  first set `screen: "browse"` unconditionally, which silently overrode the prop — so the
 *  reference, whose ONLY screen driver is `startScreen`, could not be signed in and placed on a
 *  named screen at once, and the harness worked around it by clicking the design's header nav.
 *  That workaround was an undeclared deviation from the ruled A-I8.2 and is gone. The app never
 *  passes `startScreen`, so its behaviour is untouched: it lands on Browse and `useStateRouteSync`
 *  moves it to the pending deep link the instant `auth` flips.
 */
const A5_4: Amendment = {
  id: 'A5.4', date: '2026-09-07',
  ruling: 'the app reads the signed-in account on load; the reference reaches a gate state through the startGate prop (A-I8 / A-I8.1, spec §"Prototype wiring" step 1)',
  find: '    if (this.props.startViewport === "mobile") this.setState({ viewport: "mobile" });\n  }',
  replace: '    if (this.props.startViewport === "mobile") this.setState({ viewport: "mobile" });\n'
    + '    if (this.props.startGate) this.setState({ screen: "gate", gate: this.props.startGate });\n'
    + '    const me = this.props.me;\n'
    + '    if (me && me.state === "active") this.setState({ auth: true, screen: (this.props.startScreen && this.props.startScreen !== "gate") ? this.props.startScreen : "browse", email: me.email, me: { name: me.name, role: me.role, initials: me.initials } });\n'
    + '    else if (me && (me.state === "pending" || me.state === "needs_review")) this.setState({ screen: "gate", gate: "pending" });\n'
    + '    else if (me && me.state === "declined") this.setState({ screen: "gate", gate: "rejected" });\n'
    + '    else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });\n'
    + '  }',
  count: 1
};

/** A5.6 — the `startGate` prototype prop in `data-props` (amendment A-I8, decision D-I8-3).
 *
 *  Declared beside its neighbours so the bundle's runtime hands it to the Root as a default
 *  (support.js's `parseDataProps` → `propsMeta[k].default`), which is what makes the reference
 *  server's `?props=` injection work at all, and so `app-generated.test.ts` requires
 *  `app.setup.js` to declare it too. The literal MIRRORS `startScreen`'s shape and carries the
 *  same `&quot;` escaping as the entry it is spliced in after — the equality proof in
 *  design-amendments.test.ts decodes the attribute and pins the decoded object, so a mis-escape
 *  cannot pass.
 */
const STARTVIEWPORT_ENTRY = '&quot;startViewport&quot;:{&quot;editor&quot;:&quot;enum&quot;,&quot;options&quot;:[&quot;desktop&quot;,&quot;mobile&quot;],&quot;default&quot;:&quot;desktop&quot;,&quot;tsType&quot;:&quot;string&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Viewport on load&quot;}';
const STARTGATE_ENTRY = '&quot;startGate&quot;:{&quot;editor&quot;:&quot;enum&quot;,&quot;options&quot;:[&quot;signin&quot;,&quot;apply&quot;,&quot;pending&quot;,&quot;rejected&quot;],&quot;default&quot;:&quot;&quot;,&quot;tsType&quot;:&quot;string&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Start on gate state&quot;}';
const A5_6: Amendment = {
  id: 'A5.6', date: '2026-09-07',
  ruling: 'the reference needs a prop-driven way into a gate state once the access-state shortcuts leave (A-I8, D-I8-3)',
  find: STARTVIEWPORT_ENTRY, replace: `${STARTVIEWPORT_ENTRY},${STARTGATE_ENTRY}`, count: 1
};

/** A5.7 — the `me` prototype prop in `data-props` (amendment A-I8.2).
 *
 *  A5.4 makes the header render `/api/me`'s computed `role` and `initials`. The APP gets those
 *  from a real session; the REFERENCE has none, so without this it would render the design's
 *  fixture persona while the app rendered the signed-in one — and John's rule for this wave is
 *  that the design's copy does not change, so the fixture cannot be edited to match (the drafted
 *  A5.5 was rejected on exactly that ground). The two targets are reconciled the other way
 *  instead: the reference is handed the SAME account, through the design's own prop mechanism.
 *
 *  `tests/reference-server.mjs` injects it per request from `?props=`, and the bundle's runtime
 *  copies a `default` into the Root's props verbatim — `support.js`'s `parseDataProps` only
 *  JSON-parses the attribute and strips `$`-prefixed keys, and the defaults loop is
 *  `if (v !== void 0) d[k] = v` with no coercion — so an object default and a `null` default both
 *  arrive unchanged (checked before this amendment was written, as A-I8.2 required).
 *
 *  `editor: "json"` because the value is an object rather than one of the tool's scalar editors;
 *  the runtime reads only `default`, so the editor name has no bearing on what either target
 *  renders. Everything else mirrors `startGate`'s entry, in the same key order.
 */
const ME_ENTRY = '&quot;me&quot;:{&quot;editor&quot;:&quot;json&quot;,&quot;default&quot;:null,&quot;tsType&quot;:&quot;object&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Signed-in account&quot;}';
const A5_7: Amendment = {
  id: 'A5.7', date: '2026-09-07',
  ruling: 'the reference must render the same account the app does, and the design\'s copy does not change (A-I8.2, D-I8-8)',
  find: STARTGATE_ENTRY, replace: `${STARTGATE_ENTRY},${ME_ENTRY}`, count: 1
};

// ---------------------------------------------------------------------------------------
// A6 — the launch-removal list, executed against the DESIGN (amendment A-I8, D-I8-1).
//
// CLAUDE.md's list has waited for real authentication since the platform plan: the prototype
// jump bar, the "Prototype — access states" shortcuts, the pre-filled demo credentials. They
// leave the design rather than the port, so the oracle and the app lose them together and every
// gate keeps holding — which is the whole reason the D15 mechanism carries this.
//
// BLANK LINES (A-I8.1). Every removal below swallows exactly ONE adjacent newline where the
// design had a blank line on both sides of the removed block, so the regenerated file keeps
// single blank lines. `design-amendments.test.ts` counts them against the pristine file, which
// ships one doubled blank of its own that is not this mechanism's to tidy.
//
// The `find` strings for the two markup blocks and the two multi-line script blocks are the
// pristine file's own bytes, quoted with \n escapes exactly as A2.3 quotes its block: readable
// enough to review against the source, and impossible to get wrong by re-indenting.
// ---------------------------------------------------------------------------------------
const FIND_A6_1 = "  <sc-if value=\"{{ showPrototypeBar }}\" hint-placeholder-val=\"{{ true }}\">\n  <div style=\"display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 7px 18px; background: #003a70; color: #fff; font-size: 11px;\">\n    <div style=\"display: flex; align-items: center; gap: 10px;\">\n      <span style=\"font-family: var(--rf-display); font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #deecf7;\">Prototype</span>\n      <span style=\"color: #deecf7;\">Practice Match — internal working title. Public name to be set by the VIN Foundation.</span>\n    </div>\n    <div style=\"display: flex; align-items: center; gap: 6px;\">\n      <span style=\"color: #deecf7;\">Jump to</span>\n      <sc-for list=\"{{ jumps }}\" as=\"j\" hint-placeholder-count=\"6\">\n        <button onClick=\"{{ j.go }}\" style=\"{{ j.style }}\" style-hover=\"background: rgba(255,255,255,.26);\">{{ j.label }}</button>\n      </sc-for>\n      <span style=\"width: 1px; height: 15px; background: rgba(255,255,255,.22); margin: 0 4px;\"></span>\n      <button onClick=\"{{ toggleViewport }}\" style=\"font-size: 11px; font-weight: 500; color: #003a70; background: #deecf7; border: 0; border-radius: 3px; padding: 4px 9px; cursor: pointer;\">{{ viewportLabel }}</button>\n    </div>\n  </div>\n  </sc-if>\n\n";
const FIND_A6_2 = "              <div style=\"margin-top: 16px; padding: 15px 17px; border: 1px dashed var(--border-subtle); border-radius: 8px;\">\n                <div style=\"font-family: var(--rf-display); font-size: 11px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; color: var(--color-steel);\">Prototype — access states</div>\n                <div style=\"display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px;\">\n                  <sc-for list=\"{{ gateStates }}\" as=\"s\" hint-placeholder-count=\"3\">\n                    <button onClick=\"{{ s.go }}\" style=\"font-size: 12px; font-weight: 500; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 999px; padding: 6px 12px; cursor: pointer;\" style-hover=\"border-color: var(--color-steel); background: var(--color-off-white);\">{{ s.label }}</button>\n                  </sc-for>\n                </div>\n              </div>\n";
const FIND_A6_4a = "    const jumps = [\"gate\", \"browse\", \"detail\", \"requests\", \"seller\", \"admin\"].map((k) => ({\n      label: k === \"gate\" ? \"Access\" : k === \"detail\" ? \"Listing\" : k.charAt(0).toUpperCase() + k.slice(1),\n      go: this.jumpTo(k),\n      style: \"font-size: 11px; font-weight: 500; color: #fff; background: rgba(255,255,255,\" +\n        (s.screen === k ? \".3\" : \".1\") + \"); border: 1px solid rgba(255,255,255,.16); border-radius: 3px; padding: 3px 8px; cursor: pointer;\"\n    }));\n\n";
const FIND_A6_5 = "      gateStates: [\n        { label: \"Pending approval\", go: () => this.setState({ gate: \"pending\" }) },\n        { label: \"Request declined\", go: () => this.setState({ gate: \"rejected\" }) },\n        { label: \"Approved — enter\", go: () => this.setState({ screen: \"browse\", auth: true }) }\n      ],\n";

/** A6.1 — the jump bar leaves the template. Its markup, plus the blank line it left behind. */
const A6_1: Amendment = {
  id: 'A6.1', date: '2026-09-07',
  ruling: "CLAUDE.md's launch-removal list, executed with real auth: the prototype jump bar's markup",
  find: FIND_A6_1, replace: '', count: 1
};

/** A6.2 — the "Prototype — access states" shortcuts leave the sign-in card: the smallest
 *  enclosing element (the dashed-border block), which is also its label and its `sc-for` loop.
 *  No adjacent blank line here — the block sits between the card's `</div>` and the `</sc-if>`. */
const A6_2: Amendment = {
  id: 'A6.2', date: '2026-09-07',
  ruling: "CLAUDE.md's launch-removal list: the \"Prototype — access states\" shortcuts",
  find: FIND_A6_2, replace: '', count: 1
};

/** A6.3a/b/c — the pre-filled demo credentials and the pre-filled application.
 *  The design ships a real-looking address and a masked password in `state` so the prototype's
 *  Sign in button works on the first click; with A5.1 that click reaches the API, so the fields
 *  must start empty. `apply` is the same class: a half-filled application with `affirm: true`
 *  would submit an affirmation nobody made. Field names are kept — the UI reads them. */
const A6_3a: Amendment = {
  id: 'A6.3a', date: '2026-09-07',
  ruling: "CLAUDE.md's launch-removal list: the pre-filled demo credentials",
  find: '    email: "r.mendes@example.com", pw: "············", formError: "",',
  replace: '    email: "", pw: "", formError: "",', count: 1
};
const A6_3b: Amendment = {
  id: 'A6.3b', date: '2026-09-07',
  ruling: "the same, where signOut restores them (CLAUDE.md's launch-removal list)",
  find: '        userMenu: false, auth: false, screen: "gate", gate: "signin", pw: "············",',
  replace: '        userMenu: false, auth: false, screen: "gate", gate: "signin", pw: "",', count: 1
};
const A6_3c: Amendment = {
  id: 'A6.3c', date: '2026-09-07',
  ruling: "the pre-filled application, including an affirmation nobody made (CLAUDE.md's launch-removal list)",
  find: '    apply: { name: "Rachel Mendes, DVM", vin: "", grad: "", state: "TX", employer: "", intent: "", affirm: true, error: "" },',
  replace: '    apply: { name: "", vin: "", grad: "", state: "", employer: "", intent: "", affirm: false, error: "" },', count: 1
};

/** A6.4a/b/c/d — the jump bar's script: the `jumps` array it rendered from (plus the blank line
 *  it left behind), the `showPrototypeBar` flag its `sc-if` read, the `jumps` key in
 *  `renderVals()`'s return, and the `jumpTo` handler its buttons called. */
const A6_4a: Amendment = {
  id: 'A6.4a', date: '2026-09-07',
  ruling: "CLAUDE.md's launch-removal list: the jump bar's own array",
  find: FIND_A6_4a, replace: '', count: 1
};
const A6_4b: Amendment = {
  id: 'A6.4b', date: '2026-09-07',
  ruling: 'the flag the removed sc-if read (same ruling)',
  find: '      showPrototypeBar: this.props.prototypeBar !== false,\n', replace: '', count: 1
};
const A6_4c: Amendment = {
  id: 'A6.4c', date: '2026-09-07',
  ruling: 'the jumps key in renderVals()\'s return (same ruling)',
  find: '      nav, jumps,', replace: '      nav,', count: 1
};
const A6_4d: Amendment = {
  id: 'A6.4d', date: '2026-09-07',
  ruling: 'the handler the removed buttons called (same ruling)',
  find: '  jumpTo = (screen) => () => this.setState({ screen, auth: screen !== "gate", interest: "closed", userMenu: false, gate: "signin" });\n\n',
  replace: '', count: 1
};

/** A6.5 — `gateStates` in the script: the three shortcut buttons A6.2's markup rendered. */
const A6_5: Amendment = {
  id: 'A6.5', date: '2026-09-07',
  ruling: "CLAUDE.md's launch-removal list: the access-state shortcuts' own array",
  find: FIND_A6_5, replace: '', count: 1
};

/** A6.6a/b — the viewport toggle's script (A-I8.1). After A6.1 nothing references
 *  `viewportLabel` or `toggleViewport`: the "Mobile view" / "Desktop view" button that read them
 *  lived in the jump bar. The bundle's own dead-code rule applies, exactly as it did to A2.3–A2.5.
 *  `isDesktop` — which reads the same `s.viewport` — is untouched: the phone-frame presentation
 *  stays reachable through `startViewport` until a responsive design exists (D-I8-7). */
const A6_6a: Amendment = {
  id: 'A6.6a', date: '2026-09-07',
  ruling: 'a dead mapping is dead code (spec D8/D12, A-I8.1): nothing reads viewportLabel after A6.1',
  find: '      viewportLabel: s.viewport === "desktop" ? "Mobile view" : "Desktop view",\n', replace: '', count: 1
};
const A6_6b: Amendment = {
  id: 'A6.6b', date: '2026-09-07',
  ruling: 'the same for toggleViewport, the handler the removed button called (A-I8.1)',
  find: '      toggleViewport: () => this.setState({ viewport: s.viewport === "desktop" ? "mobile" : "desktop" }),\n', replace: '', count: 1
};

/** A7.1/A7.2 — the sign-in copy (spec §Sign-in: "The design's 'VIN username' copy changes to
 *  'Email' (design delta)"). The API authenticates an email address and knows nothing about VIN
 *  usernames, so the label and the empty-form message would both be asking for the wrong thing.
 *  A ruled amendment, not a harness mask: `maxDiffPixels: 0` admits no masks. */
const A7_1: Amendment = {
  id: 'A7.1', date: '2026-09-07',
  ruling: "spec §Sign-in: the design's 'VIN username' copy changes to 'Email' (design delta)",
  find: 'VIN username or email</span>', replace: 'Email</span>', count: 1
};
const A7_2: Amendment = {
  id: 'A7.2', date: '2026-09-07',
  ruling: 'the same copy in the empty-form message (spec §Sign-in)',
  find: '"Enter both your VIN username and password."', replace: '"Enter both your email and password."', count: 1
};

// ---------------------------------------------------------------------------------------
// A7.3/A7.4 and A8 — the account screens (Task S4, spec `2026-09-07-account-screens-design.md`).
//
// The Wave 2a API serves the whole account lifecycle; the approved design has screens for four
// of its states. John's ruling (2026-09-08, "approved") clears that blocker the way D15 exists
// to: the missing screens are composed STRICTLY from the gate card the design already ships —
// the same shell, band, label, input, error box, button and footer line — and land in the
// design as ruled amendments, so `logic.js` and `App.vue` are regenerated rather than edited
// and the other 27 approved states keep their pixels and their DOM.
//
// A ruling that needs more than one literal edit carries a letter suffix (A8.1a/b/c), exactly
// as A5.3a and A6.3a/b/c do. The order below is the order the edits are applied.
// ---------------------------------------------------------------------------------------
const S4 = { date: '2026-09-08', ruling: "account screens composed from the V3 gate card — John, 2026-09-08 ('approved')" };

/** A7.3 — the sign-in card's footer line gains the forgot-password entry (spec §4.1). The only
 *  two edits to an existing screen in this task are this and A7.4, both ruled, both on
 *  `gate-signin`, which is not one of the thirteen V2-oracle screens. */
const A7_3: Amendment = {
  id: 'A7.3', ...S4,
  ruling: 'spec §4.1: the sign-in card offers "Forgot your password?" beside "Request access"',
  find: 'Not approved yet? <a href="#apply" onClick="{{ goApply }}">Request access</a></div>',
  replace: 'Not approved yet? <a href="#apply" onClick="{{ goApply }}">Request access</a> · <a href="#forgot" onClick="{{ goForgot }}">Forgot your password?</a></div>',
  count: 1
};

/** A7.4 — the sign-in sub-line (spec §4.2, John: "remove the VIN language"). The API
 *  authenticates an email address and a password of its own; "VIN credentials" describes a
 *  login this marketplace does not have. A7.1 already did the same for the field label. */
const A7_4: Amendment = {
  id: 'A7.4', ...S4,
  ruling: 'spec §4.2: "remove the VIN language" from the sign-in card\'s sub-line',
  find: '>Use your VIN credentials.</div>', replace: '>Use the email and password you registered with.</div>', count: 1
};

/** A8.1a — the notice slot (spec §3, "The notice slot"). Five outcomes — a verified address, a
 *  reset link requested, a password updated, an invitation accepted, an invitation link that has
 *  expired — have signing in as their only next step, and the status card's fixed secondary
 *  button is already "Sign in", so a status card for them would have shown two identical
 *  buttons. They speak through the SIGN-IN card's existing message box instead: a second state
 *  field (`formNotice`) feeds the same template slot, so the card's markup is untouched and the
 *  box still appears only when there is something to say. A refusal wins over a notice —
 *  `formError` is checked first. */
const A8_1a: Amendment = {
  id: 'A8.1a', ...S4,
  find: '      form: { email: s.email, pw: s.pw, error: !!s.formError, errorText: s.formError },',
  replace: '      form: { email: s.email, pw: s.pw, error: !!(s.formError || s.formNotice), errorText: s.formError || s.formNotice },',
  count: 1
};

/** A8.1b — `goSignin` signs the visitor out first (spec §4.3, John: agreed), and the two new
 *  ways into the account cards. The status cards' secondary button keeps its label — no pixel
 *  moves — but a signed-in member who presses it must not be left looking at a sign-in card
 *  behind their own signed-in header. `show` runs on both settlements for A5.3's reason: the
 *  server-side session is what authorises anything, and a member left looking signed in is the
 *  worse of the two failures.
 *
 *  The guard is `(s.auth || this.props.me)`, not `s.auth` alone (fix round 1, Important 1): A5.4
 *  never sets `auth` for an APPLICANT — `pending`, `needs_review`, `declined` and `unverified` all
 *  land on a gate card signed out as far as the prototype's own flag is concerned — so `s.auth`
 *  alone meant spec §4.3 held on the `unavailable` card and nowhere else, and those four states
 *  could not end their session at all. A loaded account is the evidence that a session exists. */
const A8_1b: Amendment = {
  id: 'A8.1b', ...S4,
  ruling: 'spec §4.3 (agreed): the status cards\' secondary button ends the session before it shows the sign-in card — and an applicant has a session too',
  find: '      goSignin: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signin", screen: "gate" }); },',
  replace: '      // Reaching the sign-in card means signing in as SOMEBODY, so whoever is signed in now is on their way out — the\n'
    + '      // same rule on every card that leads here: a status card\'s "Sign in", and the account cards\' "Back to sign in".\n'
    + '      goSignin: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", formNotice: "" }); if ((s.auth || this.props.me) && this.props.auth) return this.props.auth.signOut().then(show, show); show(); },\n'
    + '      goForgot: (e) => { if (e) e.preventDefault(); this.setState({ gate: "forgot", formError: "", formNotice: "" }); },\n'
    + '      goSignup: (e) => { if (e) e.preventDefault(); this.setState({ gate: "signup", formError: "", formNotice: "" }); },',
  count: 1
};

/** A8.1c — where "Request access" leads. An anonymous visitor on the APP has no account yet, so
 *  the first step is sign-up; a signed-in `verified` account already has one and wants the
 *  application form. The reference — no adapter — keeps the design's own path to `apply`, which
 *  is what leaves `gate-apply` on its pixels. */
const A8_1c: Amendment = {
  id: 'A8.1c', ...S4,
  find: '      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: "apply" }); },',
  replace: '      goApply: (e) => { if (e) e.preventDefault(); this.setState({ gate: (s.auth || !this.props.auth) ? "apply" : "signup" }); },',
  count: 1
};

/** A8.2 — the state the new cards read. All empty, like A6.3's: nothing is pre-filled, and
 *  `gateToken` is where the router parks an incoming `?token=` so the app never writes one into
 *  a URL of its own (spec S3). Edits the line A6.3a left. */
const A8_2: Amendment = {
  id: 'A8.2', ...S4,
  find: '    email: "", pw: "", formError: "",',
  replace: '    email: "", pw: "", formError: "", formNotice: "", gateToken: "",\n'
    + '    signup: { email: "", pw: "", error: "" }, forgot: { email: "", error: "" }, reset: { pw: "", pw2: "", error: "" }, invite: { pw: "", pw2: "", error: "" }, answer: { text: "", error: "", applicationId: "", note: "" },',
  count: 1
};

/** A8.3a — a token-bearing gate wins over the active-account redirect (S2 review rider,
 *  2026-09-08). A5.4 sent every `active` account straight to Browse; an approved member who
 *  follows a reset or invitation link is an `active` account, and would never have seen the page
 *  the link was for. The three gate values the router sets from a `?token=` URL are exempt. */
const A8_3a: Amendment = {
  id: 'A8.3a', ...S4,
  ruling: 'S2 review rider (2026-09-08): a token-bearing gate value wins over the active-account redirect',
  find: '    if (me && me.state === "active") this.setState({ auth: true, screen: (this.props.startScreen && this.props.startScreen !== "gate") ? this.props.startScreen : "browse", email: me.email, me: { name: me.name, role: me.role, initials: me.initials } });',
  replace: '    if (me && me.state === "active" && !["verify", "reset", "invite"].includes(this.state.gate)) this.setState({ auth: true, screen: (this.props.startScreen && this.props.startScreen !== "gate") ? this.props.startScreen : "browse", email: me.email, me: { name: me.name, role: me.role, initials: me.initials } });',
  count: 1
};

/** A8.3b — the rest of the bootstrap. `unverified` finally has somewhere to go (A5.4 left it
 *  deliberately unmapped because I8c's card did not exist yet); `needs_review` keeps A5.4's
 *  synchronous `pending` card and switches to the answer card when the application arrives, so
 *  a slow API never shows a blank screen; `declined` pre-fills the application form from the
 *  applicant's own last answers (spec §3, "Re-apply needs no new screen"); `startNotice` is how
 *  the reference reaches the five sign-in-with-a-notice states; and a `/verify` landing posts
 *  its token on arrival — or, with NO token, shows the expired card outright (controller ruling,
 *  2026-09-08): there is nothing to verify without one, so posting an empty token spent a
 *  rate-limited request to be told what the client already knew. Every one of the four API calls is guarded by `this.props.auth`, so the
 *  reference — which has none — takes the design's fixture path unchanged. */
const A8_3b: Amendment = {
  id: 'A8.3b', ...S4,
  find: '    else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });\n  }',
  replace: '    else if (me && me.state === "verified") this.setState({ screen: "gate", gate: "apply" });\n'
    + '    else if (me && me.state === "unverified") this.setState({ screen: "gate", gate: "check-email", email: me.email });\n'
    + '    if (me && me.state === "needs_review" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current) this.setState({ screen: "gate", gate: "answer", answer: Object.assign({}, this.state.answer, { applicationId: r.current.id, note: r.current.info_request || "" }) }); }, () => {});\n'
    + '    if (me && me.state === "declined" && this.props.auth) this.props.auth.applicationsMe().then((r) => { if (r && r.current && r.current.fields) { const f = r.current.fields; this.setState({ apply: Object.assign({}, this.state.apply, { name: f.name || "", vin: f.vin_member_id || "", grad: f.school_year || "", state: f.license_state || "", employer: f.employer || "", intent: f.intent || "", affirm: !!f.affirm }) }); } }, () => {});\n'
    + '    if (this.props.startNotice) this.setState({ screen: "gate", gate: "signin", formNotice: this.props.startNotice });\n'
    + '    if (this.state.gate === "verify" && !this.state.gateToken) this.setState({ gate: "verify-expired" });\n'
    + '    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));\n'
    + '  }',
  count: 1
};

/** A8.4a — `gateStatus` covers every status value. The four new ones render through the card
 *  the design already has, which is why they add no markup at all. */
const A8_4a: Amendment = {
  id: 'A8.4a', ...S4,
  find: '      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected"),',
  replace: '      gateStatus: s.screen === "gate" && (s.gate === "pending" || s.gate === "rejected" || s.gate === "check-email" || s.gate === "verify-expired" || s.gate === "reset-expired" || s.gate === "unavailable"),',
  count: 1
};

/** A8.4b — the four status cards' content (spec §3 rows 2, 3b, 5c, 8). Their `headStyle` is the
 *  grey one `pending` and `rejected` already use, byte for byte.
 *
 *  "Send it again" has TWO branches (fix round 1, ruled A-S4.1). It re-posts the SIGN-UP when the
 *  visitor got here by signing up, because the client still holds the password; and it calls
 *  `POST /api/auth/verify/resend` — which needs none, only the session — when it does not and an
 *  account is loaded, which is how somebody who reached this card by SIGNING IN as an unverified
 *  account arrives. Before that endpoint existed the second case posted an empty password, the
 *  API's uniform 202 answered, and the card claimed to have sent a link that was never issued. */
const A8_4b: Amendment = {
  id: 'A8.4b', ...S4,
  find: '        primary: { label: "Reply with more information", go: () => this.setState({ gate: "apply" }) }\n      }\n    };',
  replace: '        primary: { label: "Reply with more information", go: () => this.setState({ gate: "apply" }) }\n'
    + '      },\n'
    + '      "check-email": {\n'
    + '        kicker: "Almost there", title: "Check your email",\n'
    + '        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",\n'
    + '        body: "We sent a verification link to " + (s.signup.email || s.email) + ". It is valid for 24 hours. Open it to confirm your address, then sign in to complete your access request.",\n'
    + '        meta: [{ k: "Sent to", v: s.signup.email || s.email }, { k: "Link valid for", v: "24 hours" }],\n'
    + '        primary: { label: "Send it again", go: () => { if (!this.props.auth) return; return (!s.signup.pw && this.props.me ? this.props.auth.resendVerification() : this.props.auth.signUp(s.signup.email || s.email, s.signup.pw)).catch(() => {}); } }\n'
    + '      },\n'
    + '      "verify-expired": {\n'
    + '        kicker: "Link expired", title: "This link is no longer valid",\n'
    + '        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",\n'
    + '        body: "Verification links work once and expire after 24 hours. Request a new one with the same email and password.",\n'
    + '        meta: [],\n'
    + '        primary: { label: "Request a new link", go: () => this.setState({ gate: "signup" }) }\n'
    + '      },\n'
    + '      "reset-expired": {\n'
    + '        kicker: "Link expired", title: "This link is no longer valid",\n'
    + '        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",\n'
    + '        body: "Reset links work once and expire after 1 hour.",\n'
    + '        meta: [],\n'
    + '        primary: { label: "Request a new link", go: () => this.setState({ gate: "forgot" }) }\n'
    + '      },\n'
    + '      unavailable: {\n'
    + '        kicker: "Access", title: "This page is not available to your account",\n'
    + '        headStyle: "padding: 22px 26px; background: #f5f5f5; color: #494949;",\n'
    + '        body: "Your approved access does not include this page. If you think it should, write to the VIN Foundation from the address on your account.",\n'
    + '        meta: [],\n'
    + '        primary: { label: "Back to Browse Practices", go: () => this.setState({ screen: "browse" }) }\n'
    + '      }\n'
    + '    };',
  count: 1
};

/** A8.5 — the form values, setters and submits for the five new form cards, plus `goSignOut`
 *  for the answer card's footer link. Each mirrors the design's own `form`/`setEmail`/`setPw`/
 *  `signIn` trio in shape, returns the adapter's promise so a caller can await the settled
 *  state, and renders the SERVER's own message (`src/auth/api.ts` carries the API's prose, not
 *  an identifier) with a fallback for a rejection that carries none.
 *
 *  The client checks only what the server cannot answer more cheaply: both fields present, and
 *  the two passwords equal. Password STRENGTH is the server's (zxcvbn ≥ 3, HIBP) and its message
 *  is what the card shows — a client-side scorer would cost the bundle budget for a second
 *  opinion. The match check runs BEFORE the request precisely so a mistyped confirmation cannot
 *  burn a single-use token.
 *
 *  `TOKEN_INVALID` is `app/api/auth.py`'s own code, and all three consume paths (`verify`,
 *  `password/reset`, `accept-invite`) raise the same `TokenInvalid` — checked before this was
 *  written, because the brief made a differing code a STOP. */
const A8_5: Amendment = {
  id: 'A8.5', ...S4,
  find: '      submitApply: () => {',
  replace: '      gateSignup: s.screen === "gate" && s.gate === "signup",\n'
    + '      gateForgot: s.screen === "gate" && s.gate === "forgot",\n'
    + '      gateReset: s.screen === "gate" && s.gate === "reset",\n'
    + '      gateInvite: s.screen === "gate" && s.gate === "invite",\n'
    + '      gateAnswer: s.screen === "gate" && s.gate === "answer",\n'
    + '      signupForm: { email: s.signup.email, pw: s.signup.pw, error: !!s.signup.error, errorText: s.signup.error },\n'
    + '      setSignupEmail: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { email: e.target.value, error: "" }) })),\n'
    + '      setSignupPw: (e) => this.setState((st) => ({ signup: Object.assign({}, st.signup, { pw: e.target.value, error: "" }) })),\n'
    + '      submitSignup: () => {\n'
    + '        const f = s.signup;\n'
    + '        if (!f.email || !f.pw) return this.setState({ signup: Object.assign({}, f, { error: "Enter both your email and password." }) });\n'
    + '        if (!this.props.auth) return this.setState({ gate: "check-email" });\n'
    + '        return this.props.auth.signUp(f.email, f.pw).then(() => this.setState({ gate: "check-email", email: f.email }), (e) => this.setState({ signup: Object.assign({}, f, { error: (e && e.message) || "Sign-up failed." }) }));\n'
    + '      },\n'
    + '      forgotForm: { email: s.forgot.email, error: !!s.forgot.error, errorText: s.forgot.error },\n'
    + '      setForgotEmail: (e) => this.setState((st) => ({ forgot: Object.assign({}, st.forgot, { email: e.target.value, error: "" }) })),\n'
    + '      submitForgot: () => {\n'
    + '        const f = s.forgot;\n'
    + '        if (!f.email) return this.setState({ forgot: Object.assign({}, f, { error: "Enter your email." }) });\n'
    + '        const done = () => this.setState({ gate: "signin", formNotice: "If that address has an account, a reset link is on its way. It is valid for 1 hour." });\n'
    + '        if (!this.props.auth) return done();\n'
    + '        return this.props.auth.forgot(f.email).then(done, (e) => this.setState({ forgot: Object.assign({}, f, { error: (e && e.message) || "Request failed." }) }));\n'
    + '      },\n'
    + '      resetForm: { pw: s.reset.pw, pw2: s.reset.pw2, error: !!s.reset.error, errorText: s.reset.error },\n'
    + '      setResetPw: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw: e.target.value, error: "" }) })),\n'
    + '      setResetPw2: (e) => this.setState((st) => ({ reset: Object.assign({}, st.reset, { pw2: e.target.value, error: "" }) })),\n'
    + '      submitReset: () => {\n'
    + '        const f = s.reset;\n'
    + '        if (!f.pw || !f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "Enter your new password twice." }) });\n'
    + '        if (f.pw !== f.pw2) return this.setState({ reset: Object.assign({}, f, { error: "The two passwords do not match." }) });\n'
    + '        const done = () => this.setState({ gate: "signin", gateToken: "", reset: { pw: "", pw2: "", error: "" }, formNotice: "Password updated. Sign in with your new password." });\n'
    + '        if (!this.props.auth) return done();\n'
    + '        return this.props.auth.reset(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "reset-expired", gateToken: "" }) : this.setState({ reset: Object.assign({}, f, { error: (e && e.message) || "Reset failed." }) }));\n'
    + '      },\n'
    + '      inviteForm: { pw: s.invite.pw, pw2: s.invite.pw2, error: !!s.invite.error, errorText: s.invite.error },\n'
    + '      setInvitePw: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw: e.target.value, error: "" }) })),\n'
    + '      setInvitePw2: (e) => this.setState((st) => ({ invite: Object.assign({}, st.invite, { pw2: e.target.value, error: "" }) })),\n'
    + '      submitInvite: () => {\n'
    + '        const f = s.invite;\n'
    + '        if (!f.pw || !f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "Enter your new password twice." }) });\n'
    + '        if (f.pw !== f.pw2) return this.setState({ invite: Object.assign({}, f, { error: "The two passwords do not match." }) });\n'
    + '        const done = () => this.setState({ gate: "signin", gateToken: "", invite: { pw: "", pw2: "", error: "" }, formNotice: "Your password is set. Sign in with your email and the password you just chose." });\n'
    + '        if (!this.props.auth) return done();\n'
    + '        return this.props.auth.acceptInvite(s.gateToken, f.pw).then(done, (e) => (e && e.code === "TOKEN_INVALID") ? this.setState({ gate: "signin", gateToken: "", formNotice: "This invitation link is no longer valid. Ask the VIN Foundation for a new one." }) : this.setState({ invite: Object.assign({}, f, { error: (e && e.message) || "Could not set the password." }) }));\n'
    + '      },\n'
    + '      answerForm: { text: s.answer.text, note: s.answer.note, error: !!s.answer.error, errorText: s.answer.error },\n'
    + '      setAnswer: (e) => this.setState((st) => ({ answer: Object.assign({}, st.answer, { text: e.target.value, error: "" }) })),\n'
    + '      submitAnswer: () => {\n'
    + '        const f = s.answer;\n'
    + '        if (!f.text) return this.setState({ answer: Object.assign({}, f, { error: "Write your answer first." }) });\n'
    + '        if (!this.props.auth) return this.setState({ gate: "pending" });\n'
    + '        return this.props.auth.answer(f.applicationId, f.text).then(() => this.setState({ gate: "pending" }), (e) => this.setState({ answer: Object.assign({}, f, { error: (e && e.message) || "Could not send your answer." }) }));\n'
    + '      },\n'
    + '      goSignOut: (e) => { if (e) e.preventDefault(); const show = () => this.setState({ gate: "signin", screen: "gate", auth: false, formNotice: "" }); if (this.props.auth) return this.props.auth.signOut().then(show, show); show(); },\n'
    + '      submitApply: () => {',
  count: 1
};

/** A8.6 — the application reaches the API. The design's own required-field check above is
 *  untouched and still runs first; the field names are the API's (`vin_member_id`,
 *  `school_year`, `license_state`), mapped from the prototype's short ones, which CLAUDE.md
 *  keeps because the UI reads them. With no adapter the fixture transition to the pending card
 *  is exactly what it was. */
const A8_6: Amendment = {
  id: 'A8.6', ...S4,
  find: '        this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });\n      },',
  replace: '        if (!this.props.auth) return this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" });\n'
    + '        return this.props.auth.apply("buyer", { name: a.name, vin_member_id: a.vin, school_year: a.grad, license_state: a.state, employer: a.employer, intent: a.intent, affirm: !!a.affirm }).then(() => this.setState({ apply: Object.assign({}, a, { error: "" }), gate: "pending" }), (e) => this.setState({ apply: Object.assign({}, a, { error: (e && e.message) || "Your request could not be sent." }) }));\n'
    + '      },',
  count: 1
};

/** A8.7 — the five form cards' markup, appended in the gate's right column after the existing
 *  `gateStatus` block and before the column's own close.
 *
 *  Every element is the sign-in or apply card's, element for element — the card shell, the band
 *  header, `<label>`/`<span>`/`<input>`, the grey left-bordered error box, the 48 px primary
 *  button and the 14 px centred footer line — with only bindings and text changed.
 *  `design-amendments.test.ts` proves it: every `style`/`style-hover` value below already
 *  appears on the design's own gate card, and (A1's two ruled declarations aside) on the
 *  PRISTINE card. Nothing here is newly styled, which is why the 27 other approved states do not
 *  move a pixel.
 *
 *  The four status states (`check-email`, `verify-expired`, `reset-expired`, `unavailable`) get
 *  NO block: they render through the card A8.4 fills. Absent beats faked, in both directions.
 */
const A8_7_FIND = '            </sc-if>\n'
    + '          </div>\n'
    + '        </div>\n'
    + '\n'
    + '        <div style="background: var(--color-navy); color: var(--color-white); padding: 30px 34px;">';
const A8_7_REPLACE = [
  '            </sc-if>',
  '',
  '            <sc-if value="{{ gateSignup }}" hint-placeholder-val="{{ false }}">',
  '              <div style="background: var(--color-white); border: 1px solid var(--rf-line); border-radius: 10px; box-shadow: var(--shadow-md); overflow: hidden;">',
  '                <div style="padding: 22px 26px; background: var(--rf-band);">',
  '                  <div style="font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;">Request Access</div>',
  '                  <div style="font-size: 13px; line-height: 1.5; color: #494949; margin-top: 4px;">Start with the email and password you will sign in with.</div>',
  '                </div>',
  '                <div style="padding: 24px 26px 26px; display: flex; flex-direction: column; gap: 16px;">',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Email</span>',
  '                    <input value="{{ signupForm.email }}" onChange="{{ setSignupEmail }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Password</span>',
  '                    <input type="password" value="{{ signupForm.pw }}" onChange="{{ setSignupPw }}" placeholder="At least 12 characters" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <sc-if value="{{ signupForm.error }}" hint-placeholder-val="{{ false }}">',
  '                    <div style="display: flex; gap: 9px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; line-height: 1.5; color: #494949;">{{ signupForm.errorText }}</div>',
  '                  </sc-if>',
  '                  <button onClick="{{ submitSignup }}" style="font-family: var(--rf-display); height: 48px; font-size: 15px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--color-navy);">Create account</button>',
  '                  <div style="text-align: center; font-size: 14px; color: #494949;">Already have an account? <a href="#signin" onClick="{{ goSignin }}">Sign in</a></div>',
  '                </div>',
  '              </div>',
  '            </sc-if>',
  '',
  '            <sc-if value="{{ gateForgot }}" hint-placeholder-val="{{ false }}">',
  '              <div style="background: var(--color-white); border: 1px solid var(--rf-line); border-radius: 10px; box-shadow: var(--shadow-md); overflow: hidden;">',
  '                <div style="padding: 22px 26px; background: var(--rf-band);">',
  '                  <div style="font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;">Reset your password</div>',
  '                  <div style="font-size: 13px; line-height: 1.5; color: #494949; margin-top: 4px;">We will email you a link.</div>',
  '                </div>',
  '                <div style="padding: 24px 26px 26px; display: flex; flex-direction: column; gap: 16px;">',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Email</span>',
  '                    <input value="{{ forgotForm.email }}" onChange="{{ setForgotEmail }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <sc-if value="{{ forgotForm.error }}" hint-placeholder-val="{{ false }}">',
  '                    <div style="display: flex; gap: 9px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; line-height: 1.5; color: #494949;">{{ forgotForm.errorText }}</div>',
  '                  </sc-if>',
  '                  <button onClick="{{ submitForgot }}" style="font-family: var(--rf-display); height: 48px; font-size: 15px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--color-navy);">Send reset link</button>',
  '                  <div style="text-align: center; font-size: 14px; color: #494949;"><a href="#signin" onClick="{{ goSignin }}">Back to sign in</a></div>',
  '                </div>',
  '              </div>',
  '            </sc-if>',
  '',
  '            <sc-if value="{{ gateReset }}" hint-placeholder-val="{{ false }}">',
  '              <div style="background: var(--color-white); border: 1px solid var(--rf-line); border-radius: 10px; box-shadow: var(--shadow-md); overflow: hidden;">',
  '                <div style="padding: 22px 26px; background: var(--rf-band);">',
  '                  <div style="font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;">Choose a new password</div>',
  '                  <div style="font-size: 13px; line-height: 1.5; color: #494949; margin-top: 4px;">At least 12 characters. Your other sessions will be signed out.</div>',
  '                </div>',
  '                <div style="padding: 24px 26px 26px; display: flex; flex-direction: column; gap: 16px;">',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">New password</span>',
  '                    <input type="password" value="{{ resetForm.pw }}" onChange="{{ setResetPw }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Confirm password</span>',
  '                    <input type="password" value="{{ resetForm.pw2 }}" onChange="{{ setResetPw2 }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <sc-if value="{{ resetForm.error }}" hint-placeholder-val="{{ false }}">',
  '                    <div style="display: flex; gap: 9px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; line-height: 1.5; color: #494949;">{{ resetForm.errorText }}</div>',
  '                  </sc-if>',
  '                  <button onClick="{{ submitReset }}" style="font-family: var(--rf-display); height: 48px; font-size: 15px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--color-navy);">Save password</button>',
  '                  <div style="text-align: center; font-size: 14px; color: #494949;"><a href="#signin" onClick="{{ goSignin }}">Back to sign in</a></div>',
  '                </div>',
  '              </div>',
  '            </sc-if>',
  '',
  '            <sc-if value="{{ gateInvite }}" hint-placeholder-val="{{ false }}">',
  '              <div style="background: var(--color-white); border: 1px solid var(--rf-line); border-radius: 10px; box-shadow: var(--shadow-md); overflow: hidden;">',
  '                <div style="padding: 22px 26px; background: var(--rf-band);">',
  '                  <div style="font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;">Set your password</div>',
  '                  <div style="font-size: 13px; line-height: 1.5; color: #494949; margin-top: 4px;">You have been invited to the Practice Match team. Staff passwords are at least 14 characters.</div>',
  '                </div>',
  '                <div style="padding: 24px 26px 26px; display: flex; flex-direction: column; gap: 16px;">',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">New password</span>',
  '                    <input type="password" value="{{ inviteForm.pw }}" onChange="{{ setInvitePw }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Confirm password</span>',
  '                    <input type="password" value="{{ inviteForm.pw2 }}" onChange="{{ setInvitePw2 }}" style="height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;">',
  '                  </label>',
  '                  <sc-if value="{{ inviteForm.error }}" hint-placeholder-val="{{ false }}">',
  '                    <div style="display: flex; gap: 9px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; line-height: 1.5; color: #494949;">{{ inviteForm.errorText }}</div>',
  '                  </sc-if>',
  '                  <button onClick="{{ submitInvite }}" style="font-family: var(--rf-display); height: 48px; font-size: 15px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--color-navy);">Save password</button>',
  '                  <div style="text-align: center; font-size: 14px; color: #494949;"><a href="#signin" onClick="{{ goSignin }}">Back to sign in</a></div>',
  '                </div>',
  '              </div>',
  '            </sc-if>',
  '',
  '            <sc-if value="{{ gateAnswer }}" hint-placeholder-val="{{ false }}">',
  '              <div style="background: var(--color-white); border: 1px solid var(--rf-line); border-radius: 10px; box-shadow: var(--shadow-md); overflow: hidden;">',
  '                <div style="padding: 22px 26px; background: var(--rf-band);">',
  '                  <div style="font-family: var(--rf-display); font-size: 20px; font-weight: 800; color: var(--color-navy); text-transform: uppercase; letter-spacing: .02em;">More information requested</div>',
  '                  <div style="font-size: 13px; line-height: 1.5; color: #494949; margin-top: 4px;">{{ answerForm.note }}</div>',
  '                </div>',
  '                <div style="padding: 24px 26px 26px; display: flex; flex-direction: column; gap: 16px;">',
  '                  <label style="display: flex; flex-direction: column; gap: 6px;">',
  '                    <span style="font-size: 12px; font-weight: 500; color: var(--color-steel);">Your answer</span>',
  '                    <textarea value="{{ answerForm.text }}" onChange="{{ setAnswer }}" rows="4" style="padding: 10px 13px; font-size: 14px; line-height: 1.5; color: var(--color-navy); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none; resize: vertical;"></textarea>',
  '                  </label>',
  '                  <sc-if value="{{ answerForm.error }}" hint-placeholder-val="{{ false }}">',
  '                    <div style="display: flex; gap: 9px; padding: 11px 13px; background: #f5f5f5; border-left: 3px solid var(--vf-text); border-radius: 4px; font-size: 13px; line-height: 1.5; color: #494949;">{{ answerForm.errorText }}</div>',
  '                  </sc-if>',
  '                  <button onClick="{{ submitAnswer }}" style="font-family: var(--rf-display); height: 48px; font-size: 15px; font-weight: 500; letter-spacing: .04em; text-transform: uppercase; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--color-navy);">Re-submit request</button>',
  '                  <div style="text-align: center; font-size: 14px; color: #494949;"><a href="#signout" onClick="{{ goSignOut }}">Sign out</a></div>',
  '                </div>',
  '              </div>',
  '            </sc-if>',
  '          </div>',
  '        </div>',
  '',
  '        <div style="background: var(--color-navy); color: var(--color-white); padding: 30px 34px;">'
].join('\n');
const A8_7: Amendment = { id: 'A8.7', ...S4, find: A8_7_FIND, replace: A8_7_REPLACE, count: 1 };

/** A8.8a/b — the prototype props the REFERENCE reaches the new states through. `startGate`'s
 *  enum grows to every gate value (A5.6 declared four); `startNotice` is new, and is the only
 *  way to photograph the five sign-in-card-with-a-notice states on a target that has no API to
 *  produce the outcome. Both are spliced into the escaped `data-props` JSON with the same
 *  `&quot;` escaping as their neighbours, and `app.setup.js` declares `startNotice` because
 *  `app-generated.test.ts` requires it to declare everything the design does. */
const A8_8a: Amendment = {
  id: 'A8.8a', ...S4,
  find: '&quot;options&quot;:[&quot;signin&quot;,&quot;apply&quot;,&quot;pending&quot;,&quot;rejected&quot;]',
  replace: '&quot;options&quot;:[&quot;signin&quot;,&quot;apply&quot;,&quot;pending&quot;,&quot;rejected&quot;,&quot;signup&quot;,&quot;check-email&quot;,&quot;verify-expired&quot;,&quot;forgot&quot;,&quot;reset&quot;,&quot;reset-expired&quot;,&quot;invite&quot;,&quot;answer&quot;,&quot;unavailable&quot;]',
  count: 1
};
const STARTNOTICE_ENTRY = '&quot;startNotice&quot;:{&quot;editor&quot;:&quot;text&quot;,&quot;default&quot;:&quot;&quot;,&quot;tsType&quot;:&quot;string&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Sign-in notice on load&quot;}';
const A8_8b: Amendment = {
  id: 'A8.8b', ...S4,
  find: ME_ENTRY, replace: `${ME_ENTRY},${STARTNOTICE_ENTRY}`, count: 1
};

// A8.9 — no amendment. `startGate: "reset"` and `startGate: "invite"` render their forms on the
// reference with no token at all: the token is read only when the form SUBMITS, which the
// reference never reaches (it has no adapter). Recorded here so the gap in the numbering is a
// decision rather than an omission.

// ---------------------------------------------------------------------------------------
// A9.1 — controller amendment A-S5 (2026-09-08), on the S5 implementer's NEEDS_CONTEXT.
//
// The applicant-answer card renders the reviewer's question as its own element
// (`{{ answerForm.note }}`, 13 px / line-height 1.5 / margin-top 4 px), and A8.3b feeds it from
// `GET /api/applications/me` — a call guarded by `this.props.auth`, which the REFERENCE does not
// have. Measured against the real `Component`: the app renders the seeded `info_request` and the
// reference renders `""`, so the two targets differ by one line of text and ~23.5 px of card
// height, and `maxDiffPixels: 0` can never pass. Nothing in the design's six prototype props
// carries an application, and the note is not an input, so no step could type it either.
//
// The ruling is the mechanism A8.8b already established for the sign-in notices rather than a
// fixture (which would put invented copy in the shipped app) or a demotion (which would drop an
// approved state John counted): one more DECLARED prop. It defaults to `""`, so every one of the
// 28 approved states renders exactly what it rendered before.
// ---------------------------------------------------------------------------------------
const S5 = {
  date: '2026-09-08',
  ruling: 'A-S5 (2026-09-08): the reference reaches the applicant-answer card\'s note through a declared prototype prop, `startAnswerNote`, exactly as `startNotice` reaches the sign-in notices; the app never passes it.'
};

/** A9.1a — the declaration, spliced immediately after A8.8b's `startNotice` with the same
 *  `&quot;` escaping as its neighbours. `app.setup.js` declares it too, because
 *  `app-generated.test.ts` requires this file to declare everything the design does; the app
 *  never passes it (D-I8-2). */
const STARTANSWERNOTE_ENTRY = '&quot;startAnswerNote&quot;:{&quot;editor&quot;:&quot;text&quot;,&quot;default&quot;:&quot;&quot;,&quot;tsType&quot;:&quot;string&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Applicant answer note on load&quot;}';
const A9_1a: Amendment = {
  id: 'A9.1a', ...S5,
  find: STARTNOTICE_ENTRY, replace: `${STARTNOTICE_ENTRY},${STARTANSWERNOTE_ENTRY}`, count: 1
};

/** A9.1b — `componentDidMount` writes it into the answer card's note, one line after the
 *  `startNotice` line it mirrors. It sets the NOTE only: the answer text, the error and the
 *  application id belong to a real applicant, and the reference never submits. It is also the
 *  last thing the bootstrap does with a prop, so the APP — which passes no `startAnswerNote` —
 *  keeps whatever `applicationsMe()` fetched. */
const A9_1b: Amendment = {
  id: 'A9.1b', ...S5,
  find: '    if (this.props.startNotice) this.setState({ screen: "gate", gate: "signin", formNotice: this.props.startNotice });\n'
    + '    if (this.state.gate === "verify"',
  replace: '    if (this.props.startNotice) this.setState({ screen: "gate", gate: "signin", formNotice: this.props.startNotice });\n'
    + '    if (this.props.startAnswerNote) this.setState({ answer: Object.assign({}, this.state.answer, { note: this.props.startAnswerNote }) });\n'
    + '    if (this.state.gate === "verify"',
  count: 1
};

/** A10 — the sign-in card's second gate point (John, 2026-09-08). A literal script edit, like A3:
 *  the `gatePoints[1]` object in the sign-in view. Ids A8 and A9 were RESERVED by the account-screens
 *  branch (feat/identity: A8 = the account screens, A9 = the answer-note prototype prop) while this
 *  family was ruled on `main`; both are above now, so the ordering here is history, not a gap.
 *  Revised the same day by A10.2, below. */
const A10: Amendment = {
  id: 'A10', date: '2026-09-08',
  ruling: 'update the text on login page for #2 Sellers control disclosure to "Sellers control location & disclosure Properties are mapped using precise coordinates, while the exact location details, financial packets, and floor plans are only revealed when the seller authorizes access."',
  find: '{ n: "2", title: "Sellers control disclosure", body: "General location by default. Financial packets and floor plans open only when the seller says yes." }',
  replace: '{ n: "2", title: "Sellers control location & disclosure", body: "Properties are mapped using precise coordinates, while the exact location details, financial packets, and floor plans are only revealed when the seller authorizes access." }',
  count: 1
};

/** A11 — the docked panel's other tabs take the Insights tab's wording (John, 2026-09-08: unify).
 *  A template text node, V3:717 — the only "Open full listing" in the pristine file. Same wiring
 *  as A3's button (`md.panel.openListing`); only the label changes. */
const A11: Amendment = {
  id: 'A11', date: '2026-09-08',
  ruling: 'UNIFY — Change all Browse V3 docked-panel CTAs to "View full listing", including the Insights tab.',
  find: 'border-radius: 6px; cursor: pointer;">Open full listing</button>',
  replace: 'border-radius: 6px; cursor: pointer;">View full listing</button>',
  count: 1
};

/** A10.2 — John revised A10's wording later the same day; A10 stays as the record of the first
 *  ruling and A10.2 applies after it (its `find` is A10's output). Verbatim copy: the comma after
 *  "information" and the U+2019 apostrophe in "seller’s" are his. */
const A10_2: Amendment = {
  id: 'A10.2', date: '2026-09-08',
  ruling: 'the text for #2 Sellers and control disclouse must be updated to the following text: Sellers control what buyers can see The property is accurately mapped, but financial information, and floor plans are only shared with the seller’s approval.',
  find: '{ n: "2", title: "Sellers control location & disclosure", body: "Properties are mapped using precise coordinates, while the exact location details, financial packets, and floor plans are only revealed when the seller authorizes access." }',
  replace: '{ n: "2", title: "Sellers control what buyers can see", body: "The property is accurately mapped, but financial information, and floor plans are only shared with the seller’s approval." }',
  count: 1
};

/** A12 — the design's script reads a LISTING's own name and photographs (Seed Listings, John
 *  2026-09-08; the plan's Task L6 STOP, resolved by option (iii) through the D15 engine rather
 *  than by hand-editing the ported `logic.js`, which `app-generated.test.ts` forbids byte for
 *  byte). Five literal script edits at the five sites the STOP note enumerates — `practiceName`,
 *  both `photoSet` branches, `heroSrc` and `thumbSrc` — each written so the design's OWN data
 *  still wins where it exists:
 *
 *    - `p.name` is consulted FIRST in `practiceName`, and the fixtures carry no `name`, so the
 *      `NAMES` map and the `p.area + " Veterinary"` fallback behave exactly as before;
 *    - `p.photos` is consulted AFTER `SRC` in `photoSet`'s `p2` branch (the three real
 *      photographs the design ships for that one practice stay where the design put them) and
 *      is the only source in the generic branch, which had none;
 *    - `heroSrc`/`thumbSrc` prefer `p.photos[0]` and otherwise return the design's own `p2`
 *      expression unchanged — the street view for the hero, the parking photograph for the
 *      thumbnail.
 *
 *  It is therefore PIXEL-SAFE by construction: no fixture practice carries either key, and
 *  `src/listings/load.ts`'s `toPractice` adds them only when the API actually sent them, which
 *  the D6 design-fixture stub never does. Proved twice over — `src/logic.test.ts` characterises
 *  both halves, and the 43 approved states keep their baseline hashes.
 */
const L6 = {
  date: '2026-09-08',
  ruling: 'Eighteen demo hospitals with real addresses and photos replace the design\'s fixture practices on QA (John, 2026-09-08 — Seed Listings launch)'
};

/** A12.1 — the title slot (D5/A-L5: the server decides what `p.name` is; a listing whose name is
 *  not disclosed is served the design's own anonymised label, so this one expression honours the
 *  disclosure flag without knowing about it). */
const A12_1: Amendment = {
  id: 'A12.1', ...L6,
  find: 'return NAMES[p.id] || p.area + " Veterinary";',
  replace: 'return p.name || NAMES[p.id] || p.area + " Veterinary";', count: 1
};

/** A12.2 — `photoSet`'s `p2` branch. `SRC` (the design's three committed photographs, keyed by
 *  slot id) keeps precedence; a seeded listing's photographs fill the slots in order behind it. */
const A12_2: Amendment = {
  id: 'A12.2', ...L6,
  find: 'src: SRC[id] || "", hasSrc: !!SRC[id], noSrc: !SRC[id] };',
  replace: 'src: SRC[id] || (p.photos && p.photos[i]) || "", hasSrc: !!(SRC[id] || (p.photos && p.photos[i])), noSrc: !(SRC[id] || (p.photos && p.photos[i])) };',
  count: 1
};

/** A12.3 — `photoSet`'s generic branch, which gave every practice but `p2` six empty slots by
 *  construction. The captions, their order and the placeholder text are the design's, untouched. */
const A12_3: Amendment = {
  id: 'A12.3', ...L6,
  find: '      src: "", hasSrc: false, noSrc: true',
  replace: '      src: (p.photos && p.photos[i]) || "", hasSrc: !!(p.photos && p.photos[i]), noSrc: !(p.photos && p.photos[i])',
  count: 1
};

/** A12.4 — the hero photograph (the detail screen's lead image). */
const A12_4: Amendment = {
  id: 'A12.4', ...L6,
  find: 'return p.id === "p2" ? "assets/photos/round-rock-exterior-street.webp" : "";',
  replace: 'return (p.photos && p.photos[0]) || (p.id === "p2" ? "assets/photos/round-rock-exterior-street.webp" : "");',
  count: 1
};

/** A12.5 — the thumbnail-safe variant (the results card). The design's own `p2` expression is a
 *  SECOND VIEW — the parking photograph, which reads at small sizes where the wide street view
 *  `heroSrc` returns does not — so a seeded listing takes its SECOND photograph where it has one
 *  and its first otherwise, rather than repeating the hero (L6 ruling, 2026-09-08). */
const A12_5: Amendment = {
  id: 'A12.5', ...L6,
  find: 'return p.id === "p2" ? "assets/photos/round-rock-exterior-parking.jpeg" : "";',
  replace: 'return (p.photos && (p.photos[1] || p.photos[0])) || (p.id === "p2" ? "assets/photos/round-rock-exterior-parking.jpeg" : "");',
  count: 1
};

/** A12.6 / A12.7 — the detail tolerates the community figures the API does not have yet (L6
 *  ruling, 2026-09-08, on the implementer's blocking finding).
 *
 *  Spec D4 leaves `pop`, `growth`, `income` and `hh` null for every seeded listing until the
 *  Census plan supplies them, and `app/api/listings.py` serves all four as null with the comment
 *  "the UI shows its existing empty state for them". It did not have one: `detail()` called
 *  `.replace` on two of the four, and `renderVals()` computes `detail()` on EVERY render — so an
 *  unguarded null was not a blank card but a blank APP, on every screen including the signed-out
 *  gate (measured against the real eighteen).
 *
 *  `pop` and `income` need no guard: they are interpolated, and Vue renders `null` as the empty
 *  string. These two are the only member accesses on the four figures anywhere in the design.
 *  Pixel-safe: every design fixture carries a non-empty string, so `||` never fires for them and
 *  all 43 approved states keep their hashes. */
const A12_6: Amendment = {
  id: 'A12.6', ...L6,
  find: '{ k: "Growth", v: p.growth.replace(" since 2015", ""), sub: "Since 2015" },',
  replace: '{ k: "Growth", v: (p.growth || "").replace(" since 2015", ""), sub: "Since 2015" },',
  count: 1
};

const A12_7: Amendment = {
  id: 'A12.7', ...L6,
  find: '{ k: "Households", v: p.hh.replace(" households", ""), sub: "In the community" }',
  replace: '{ k: "Households", v: (p.hh || "").replace(" households", ""), sub: "In the community" }',
  count: 1
};

/** A12.8 / A12.9 — the detail names the listing's OWN state, not Texas (final review C1).
 *  The design's twenty-one fixtures are all in the Austin metro — `logic.js:26` normalises the
 *  nine that carry no market of their own — so the hard-coded `", TX"` was right for every one of
 *  them. The eighteen seeded hospitals span seven states, and thirteen of them would have told a
 *  stakeholder, on the detail screen of a release whose stated purpose is real addresses, that a
 *  New York or Denver or Los Angeles practice is in Texas. `stateOf(market)` is the design's own
 *  helper for exactly this, called as `this.stateOf(...)` by the Browse card (V3 script) and the
 *  docked panel; these two sites now call it the same way. Pixel-safe: every approved `detail` and
 *  `mobile-detail` state captures an Austin fixture, and `stateOf("Austin, TX")` is `"TX"`. */
const A12_8: Amendment = {
  id: 'A12.8', ...L6,
  find: 'subtitle: p.area + ", TX · Established " + p.est,',
  replace: 'subtitle: p.area + ", " + this.stateOf(p.market) + " · Established " + p.est,',
  count: 1
};

/** A12.9 — the Overview section's "General location" row, the same literal a second time. The
 *  seller wizard's own `{ k: "General location", v: (w.city || "—") + (w.city ? ", TX" : "") }` is
 *  a different string and is fixture-driven; `count: 1` proves this does not reach it. */
const A12_9: Amendment = {
  id: 'A12.9', ...L6,
  find: '{ k: "General location", v: p.area + ", TX" },',
  replace: '{ k: "General location", v: p.area + ", " + this.stateOf(p.market) },',
  count: 1
};

/** A12.10 / A12.11 — Community Context reaches the design's OWN empty state when the figures are
 *  absent (final review I1). D4 leaves `pop`, `growth`, `income` and `hh` null for every seeded
 *  listing until the Census plan lands, and `p.id === "p8"` can only ever be true of a design
 *  fixture — so a seeded listing rendered the POPULATED four-tile grid with every value blank,
 *  directly under "Source: U.S. Census Bureau…", which reads as attributing an empty panel to the
 *  Bureau. The design already ships the honest alternative: the dashed "Community data unavailable
 *  for this location" card. A12.6/A12.7 stopped the TypeError; these two reach the state.
 *  Pixel-safe: `p8` keeps `noDemo` because its id still matches, and every other design fixture
 *  carries a non-null `pop`, so no approved state moves. */
const A12_10: Amendment = {
  id: 'A12.10', ...L6,
  find: 'hasDemo: p.id !== "p8",',
  replace: 'hasDemo: p.id !== "p8" && p.pop != null,', count: 1
};

const A12_11: Amendment = {
  id: 'A12.11', ...L6,
  find: 'noDemo: p.id === "p8",',
  replace: 'noDemo: p.id === "p8" || p.pop == null,', count: 1
};

/** A13 — the metro selector is a DROPDOWN LIST in the design's own popover style, not the
 *  operating system's popup (John, 2026-09-08).
 *
 *  `<select>` on macOS opens the OS popup menu — a large dark panel drawn over the page by the
 *  window server, which no page style reaches. The design already ships the alternative twice
 *  over: the Market data card's layer select (V3:431 trigger, V3:523 panel, script V3:2091–2122)
 *  and Compare's identical control (V3:477/482). A13 composes the metro picker from those
 *  elements — trigger + `aria-haspopup="listbox"` + rotating `sub-chevron.svg`, a
 *  `role="listbox"` panel of `role="option"` buttons with the tick glyph — reusing every inline
 *  style verbatim and taking the panel's anchoring (`top: 46px; z-index: 700`, the offset for a
 *  40 px control) from the "More filters" popover in the same toolbar row (V3:382).
 *
 *  `setMarket`'s state transition is unchanged, so filters, pins, the rail, `mapCenter`,
 *  `marketLabel`, `emptyNote` and the 320 ms loading skeleton behave exactly as before; it moves
 *  to a class property beside `setF` (V3:1906) so the option rows can call it, and takes `setF`'s
 *  own "an event OR a bare value" line (V3:1907) so the old contract still holds. Its orphaned
 *  `renderVals()` key goes with the `<select>` that was its only reader, under the same dead-code
 *  rule A2.3/A2.5 applied to the `browseSel` helpers.
 *
 *  Two behaviours the design has NEVER had are added, because a dropdown a keyboard cannot drive
 *  and a click cannot dismiss is not "a normal dropdown": Arrow/Home/End/Enter on the trigger
 *  (A13.2's `marketMenuKeys`) and Escape + outside-click on `document` (A13.4's
 *  `trackMenuDismiss`, modelled line for line on `trackWidth`, V3:1864–1869, and torn down in the
 *  same `componentWillUnmount`). They live in the DESIGN's script, so the reference and the app
 *  get them together and the oracles stay comparable. Scope is the metro selector: the five
 *  filter selects, the sort select and the wizard's field selects stay native.
 */
const A13 = {
  date: '2026-09-08',
  ruling: 'must fix this drop-down to be an acutal drop-down vs the popup following the same design logic of a normal dropdown'
};

/** A13.1 — `setMarket` becomes a class property beside `setF`, so the option rows can call it and
 *  there is exactly one implementation of the transition. The first line is `setF`'s own
 *  event-or-value idiom (V3:1907), verbatim; the `setState` body is the old `setMarket`'s
 *  (V3:3173–3176), verbatim, plus the two keys that close the menu on a choice and the focus
 *  return that keeps the user on the control the choice was made from (round 4 ruling). */
const A13_1: Amendment = {
  id: 'A13.1', ...A13,
  find: [
    '  setF = (key) => (e) => {',
    '    const v = e && e.target ? e.target.value : e;',
    '    this.setState((s) => ({ f: Object.assign({}, s.f, { [key]: v }), loading: true }));',
    '    clearTimeout(this._t);',
    '    this._t = setTimeout(() => this.setState({ loading: false }), 320);',
    '  };',
    ''
  ].join('\n'),
  replace: [
    '  setF = (key) => (e) => {',
    '    const v = e && e.target ? e.target.value : e;',
    '    this.setState((s) => ({ f: Object.assign({}, s.f, { [key]: v }), loading: true }));',
    '    clearTimeout(this._t);',
    '    this._t = setTimeout(() => this.setState({ loading: false }), 320);',
    '  };',
    '',
    '  // The metro choice. One implementation, called by the dropdown rows and still accepting a',
    '  // change event the way setF does, so the transition below is the one the <select> had.',
    '  setMarket = (e) => {',
    '    const v = e && e.target ? e.target.value : e;',
    '    this.setState({ market: v, activeId: null, hoverId: null, loading: true, marketMenu: false, marketMenuAt: -1 }, () => {',
    '      clearTimeout(this._t);',
    '      this._t = setTimeout(() => this.setState({ loading: false }), 320);',
    '    });',
    '    // The choice unmounts the row the pointer or the keyboard was on, so focus would land on',
    '    // <body>. A native select leaves the user on the control; so does this one.',
    '    const host = this._marketMenuEl;',
    '    const trigger = host && host.querySelector(\'button[aria-haspopup="listbox"]\');',
    '    if (trigger) trigger.focus();',
    '  };',
    '',
    '  // Bringing a row into view. The panel scrolls at its max-height as soon as the market list',
    '  // is longer than the design\'s four, so both the arrow keys and the panel\'s own mount need',
    '  // this: one while the rows are already there, one at the moment they arrive. The row is',
    '  // resolved through the field this component recorded, not across the document: the id is',
    '  // one this component mints, and setMarket\'s own trigger lookup is scoped the same way.',
    '  scrollMarketOption = (i) => {',
    '    const host = this._marketMenuEl;',
    '    const row = host && host.querySelector("#market-opt-" + i);',
    '    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });',
    '  };',
    '',
    '  // Moving the keyboard highlight. The rows are all in the DOM while the menu is open, so the',
    '  // one being highlighted is scrolled into view here rather than after a re-render.',
    '  moveMarketHighlight = (i) => {',
    '    this.setState({ marketMenuAt: i });',
    '    this.scrollMarketOption(i);',
    '  };',
    ''
  ].join('\n'),
  count: 1
};

/** A13.2 — `renderVals()`: the menu's open state, its trigger and caret styles, its keyboard
 *  handler, its callback ref, and the option rows. Modelled key for key on the layer menu
 *  (V3:2091–2122): `marketMenuOpen` ↔ `layerMenuOpen`, `toggleMarketMenu` ↔ `toggleLayerMenu`,
 *  `marketCaretStyle` ↔ `layerMenuCaretStyle`, `marketTriggerLabel` ↔ `compareTriggerLabel`
 *  (V3:2135), `marketMenuRef` ↔ `compareMenuRef` (V3:2137), `rowStyle`/`tickStyle` verbatim from
 *  V3:2112–2120 with the highlight taking the row's own hover grey (V3:525). The orphaned
 *  `setMarket:` key is dropped — the `<select>` was its only reader (A2.3/A2.5's dead-code rule);
 *  the class property A13.1 added is what the rows call. */
const A13_2: Amendment = {
  id: 'A13.2', ...A13,
  find: [
    '      marketOptions: Object.keys(MARKETS).map((m) => ({ v: m, label: m + " metro" })),',
    '      setMarket: (e) => this.setState({ market: e.target.value, activeId: null, hoverId: null, loading: true }, () => {',
    '        clearTimeout(this._t);',
    '        this._t = setTimeout(() => this.setState({ loading: false }), 320);',
    '      }),',
    ''
  ].join('\n'),
  replace: [
    '      // The metro SELECT is a dropdown list in this design\'s own style, not the operating',
    '      // system\'s popup: the same trigger + role="listbox" panel the Market data card uses.',
    '      marketMenuOpen: !!s.marketMenu,',
    '      // `giveMenu: false`: opening one menu closes the others, in every direction (final',
    '      // review m7). The global pointerdown and focusout listeners covered a pointer and a',
    '      // Tab; a pure-keyboard user could hold this listbox and the header\'s Give menu open',
    '      // at once, and then shut both with one Escape.',
    '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false }),',
    '      // On the TRIGGER, which is always rendered: a shut menu has no active descendant, and',
    '      // null is what both renderers omit the attribute for (a string would spell a dead id).',
    '      marketActiveId: s.marketMenu ? "market-opt-" + s.marketMenuAt : null,',
    '      marketTriggerLabel: (s.market || "Austin, TX") + " metro",',
    '      marketFieldStyle: "position: relative; display: flex; align-items: center; gap: 9px; height: 40px; padding: 0 8px 0 15px; min-width: 300px; background: var(--vf-neutral); border: 1px solid " +',
    '        (s.marketMenu ? "var(--vf-accent)" : "var(--border-subtle)") + "; border-radius: 6px;",',
    '      marketSelectStyle: "display: flex; align-items: center; gap: 8px; flex: 1; height: 36px; padding: 0; border: 0; outline: none; background: none; font-size: 14px; font-weight: 500; color: var(--vf-navy); cursor: pointer;",',
    '      marketCaretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +',
    '        (s.marketMenu ? "180deg" : "0deg") + ");",',
    '      marketMenuRef: (el) => { this._marketMenuEl = el || null; },',
    '      // The panel\'s own mount is when the option rows first exist, so it is where OPENING',
    '      // scrolls the highlighted row into view — the arrow keys cannot, having seeded the',
    '      // highlight while the panel was still unrendered. Same callback-ref idiom the compare',
    '      // menu already ships (md.compareMenuRef), and it fires on mount on both targets.',
    '      marketPanelRef: (el) => { if (el) this.scrollMarketOption(this.state.marketMenuAt); },',
    '      marketMenuKeys: (e) => {',
    '        const keys = Object.keys(MARKETS);',
    '        // Math.max: a market MARKETS no longer holds (Seed Listings drops a metro with no',
    '        // listings left) gives indexOf -1, and keys[-1] would reach setMarket as undefined.',
    '        const cur = Math.max(0, keys.indexOf(s.market || "Austin, TX"));',
    '        const at = s.marketMenuAt == null || s.marketMenuAt < 0 ? cur : s.marketMenuAt;',
    '        if (e.key === "ArrowDown" || e.key === "ArrowUp") {',
    '          e.preventDefault();',
    '          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur });',
    '          return this.moveMarketHighlight((at + (e.key === "ArrowDown" ? 1 : keys.length - 1)) % keys.length);',
    '        }',
    '        if (!s.marketMenu) return;',
    '        if (e.key === "Home" || e.key === "End") {',
    '          e.preventDefault();',
    '          return this.moveMarketHighlight(e.key === "Home" ? 0 : keys.length - 1);',
    '        }',
    '        if (e.key === "Enter" || e.key === " ") {',
    '          e.preventDefault();',
    '          return this.setMarket(keys[at]);',
    '        }',
    '      },',
    '      marketOptions: Object.keys(MARKETS).map((m, i) => {',
    '        const on = (s.market || "Austin, TX") === m;',
    '        const hi = s.marketMenuAt === i;',
    '        return {',
    '          v: m, label: m + " metro", selected: on,',
    '          go: () => this.setMarket(m),',
    '          optId: "market-opt-" + i,',
    '          rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +',
    '            (on ? "800" : "500") + "; color: var(--vf-navy); background: " +',
    '            (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",',
    '          tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +',
    '            (on ? "1" : "0") + ";"',
    '        };',
    '      }),',
    ''
  ].join('\n'),
  count: 1
};

/** A13.3 — the markup. The field wrapper keeps its own declarations (V3:363) and gains
 *  `position: relative` so the panel can anchor to it, exactly as the "More filters" wrapper does
 *  (V3:379); the search glyph is untouched; the `<select>` becomes the layer menu's trigger
 *  (V3:431–434) and its panel (V3:523–534) with the chip swatch left out — markets have no colour
 *  ramp, and absent beats faked. Each row carries an `id` and the TRIGGER carries
 *  `aria-activedescendant` — the focused element is the only place a screen reader reads it, and
 *  focus stays on the trigger throughout (round 3 ruling; it sat on the panel, inert, in round 2).
 *
 *  Widened by the final whole-branch review's I1 (ruled): the trigger is `role="combobox"`, and
 *  the option rows carry `tabindex="-1"`. ARIA 1.2 supports `aria-activedescendant` on
 *  `application`, `combobox`, `group`, `textbox` and the composite widget roles — NOT on
 *  `button` — so the whole attribute chain above hung off a role that does not carry it and was
 *  liable to be dropped on the way to the accessibility tree. This markup is the APG Select-Only
 *  Combobox in every other respect; saying so is one attribute. `tabindex="-1"` is the other half
 *  of the same pattern: a listbox driven by `aria-activedescendant` keeps focus on the element
 *  that holds it, and without it Tab from the trigger walked INTO the options, where
 *  `marketMenuKeys` is not bound and the arrow keys did nothing. Both are DOM-only; no pixel
 *  moves, and React 18 passes a lowercase `tabindex` through as a plain attribute, exactly as
 *  Vue does, so the two targets stay byte-identical to the DOM oracle. */
const A13_3: Amendment = {
  id: 'A13.3', ...A13,
  find: [
    '          <div style="display: flex; align-items: center; gap: 9px; height: 40px; padding: 0 8px 0 15px; min-width: 300px; background: var(--vf-neutral); border: 1px solid var(--border-subtle); border-radius: 6px;">',
    '            <img src="assets/icons/sub-search.svg" alt="" width="14" height="14" style="opacity: .45;">',
    '            <select value="{{ market }}" onChange="{{ setMarket }}" style="flex: 1; height: 36px; border: 0; outline: none; background: none; font-size: 14px; font-weight: 500; color: var(--vf-navy); cursor: pointer;">',
    '              <sc-for list="{{ marketOptions }}" as="m" hint-placeholder-count="4">',
    '                <option value="{{ m.v }}">{{ m.label }}</option>',
    '              </sc-for>',
    '            </select>',
    ''
  ].join('\n'),
  replace: [
    '          <div ref="{{ marketMenuRef }}" style="{{ marketFieldStyle }}">',
    '            <img src="assets/icons/sub-search.svg" alt="" width="14" height="14" style="opacity: .45;">',
    '            <button onClick="{{ toggleMarketMenu }}" onKeyDown="{{ marketMenuKeys }}" role="combobox" aria-label="Metro area" aria-haspopup="listbox" aria-controls="metro-listbox" aria-expanded="{{ marketMenuOpen }}" aria-activedescendant="{{ marketActiveId }}" style="{{ marketSelectStyle }}">',
    '              <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ marketTriggerLabel }}</span>',
    '              <img src="assets/icons/sub-chevron.svg" alt="" width="14" height="14" style="{{ marketCaretStyle }}">',
    '            </button>',
    '            <sc-if value="{{ marketMenuOpen }}" hint-placeholder-val="{{ false }}">',
    '              <div role="listbox" aria-label="Metro area" id="metro-listbox" ref="{{ marketPanelRef }}" style="position: absolute; left: 0; top: 46px; z-index: 700; width: 300px; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;" class="rf-scroll">',
    '                <sc-for list="{{ marketOptions }}" as="m" hint-placeholder-count="4">',
    '                  <button onClick="{{ m.go }}" id="{{ m.optId }}" role="option" tabindex="-1" aria-selected="{{ m.selected }}" style="{{ m.rowStyle }}" style-hover="background: var(--vf-neutral);">',
    '                    <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ m.label }}</span>',
    '                    <img src="assets/icons/sub-check-filled.svg" alt="" width="11" height="11" style="{{ m.tickStyle }}">',
    '                  </button>',
    '                </sc-for>',
    '              </div>',
    '            </sc-if>',
    ''
  ].join('\n'),
  count: 1
};

/** A13.4 — `trackMenuDismiss()`, and the two removals that pair with it. Modelled line for line
 *  on `trackWidth` (V3:1864–1869) / `componentWillUnmount` (V3:1871–1873), which is the design's
 *  only global listener and its only teardown. Escape and outside-click are the two dismissals a
 *  normal dropdown has and this design has never had; they live here, once, for the one menu the
 *  ruling names. */
const A13_4: Amendment = {
  id: 'A13.4', ...A13,
  find: [
    '  componentWillUnmount() {',
    '    if (this._onResize) window.removeEventListener("resize", this._onResize);',
    '  }',
    ''
  ].join('\n'),
  replace: [
    '  trackMenuDismiss() {',
    '    const down = (e) => {',
    '      if (!this.state.marketMenu) return;',
    '      const host = this._marketMenuEl;',
    '      if (host && e.target && host.contains(e.target)) return;',
    '      this.setState({ marketMenu: false, marketMenuAt: -1 });',
    '    };',
    '    const key = (e) => {',
    '      if (!this.state.marketMenu || e.key !== "Escape") return;',
    '      this.setState({ marketMenu: false, marketMenuAt: -1 });',
    '    };',
    '    this._onDocDown = down;',
    '    this._onDocKey = key;',
    '    document.addEventListener("pointerdown", down, true);',
    '    document.addEventListener("keydown", key, true);',
    '  }',
    '',
    '  componentWillUnmount() {',
    '    if (this._onResize) window.removeEventListener("resize", this._onResize);',
    '    if (this._onDocDown) document.removeEventListener("pointerdown", this._onDocDown, true);',
    '    if (this._onDocKey) document.removeEventListener("keydown", this._onDocKey, true);',
    '  }',
    ''
  ].join('\n'),
  count: 1
};

/** A13.5 — `componentDidMount` arms them, immediately after `trackWidth()`, which is the line it
 *  mirrors. */
const A13_5: Amendment = {
  id: 'A13.5', ...A13,
  find: [
    '  componentDidMount() {',
    '    this.trackWidth();',
    ''
  ].join('\n'),
  replace: [
    '  componentDidMount() {',
    '    this.trackWidth();',
    '    this.trackMenuDismiss();',
    ''
  ].join('\n'),
  count: 1
};

/** A13.6 — the first of the two render-value orphans the `<select>` left behind, deleted under the
 *  bundle's own dead-code rule, exactly as A2.2–A2.5 deleted the `browseSel` orphans C13 left.
 *  `market:` fed `<select value="{{ market }}">` and nothing else: after A13.3 the template holds
 *  no `{{ market }}` at all, and no module under `frontend/src` reads `v.market`. The trigger's
 *  own label comes from `marketTriggerLabel`, and every reader of the CHOICE goes through
 *  `s.market` in the script (review round 1, I2). */
const A13_6: Amendment = {
  id: 'A13.6', ...A13,
  find: '      market: s.market || "Austin, TX",\n',
  replace: '',
  count: 1
};

/** A13.7 — the second orphan, on the option rows A13.2 builds: `v: m` was the `<option value>` the
 *  listbox row does not have. The rows read `label`, `selected`, `go`, `rowStyle`, `tickStyle` and
 *  `optId`; `go` closes over `m` itself, so nothing needs the value on the object. Same rule, same
 *  ruling (review round 1, I2). */
const A13_7: Amendment = {
  id: 'A13.7', ...A13,
  find: '          v: m, label: m + " metro", selected: on,\n',
  replace: '          label: m + " metro", selected: on,\n',
  count: 1
};

/** A14 — the header's Give button IS the VIN Foundation site's Give dropdown (John, 2026-09-08:
 *  "match button design pixel-by-pixel").
 *
 *  Unlike A13, which composes from THIS design's popover pattern, every literal here was measured
 *  on https://vinfoundation.org/ on 2026-09-08 and is cited in the plan's measurement table by the
 *  stylesheet and selector it came from. Two of those values could not be taken from the bundle,
 *  and John ruled on both rather than either being guessed: the live face is Montserrat 600, which
 *  this design does not load and whose weight ProximaNova does not have (Q1 → A14.6 self-hosts it
 *  under the SIL Open Font Licence, scoped to this control and its menu and to nothing else), and
 *  the live navy is #07386f where `--vf-navy` is #003a70 (Q2 → the live literal, because
 *  "pixel-by-pixel" names the live site). The light blue needed no decision — `--vf-accent`
 *  (V3:22) is already #339dde, the same hex as the live pill.
 *
 *  Structure. The live control is `li.give-button > a.elementor-item > span.sub-arrow` with a
 *  sibling `ul.sub-menu`, and the pill/typography split across the li and the a. A14 folds the two
 *  boxes into one <button> whose padding is the li's vertical and the a's horizontal (`2px 22px`),
 *  which reproduces the measured 28.30 px height and the same text baseline, and wraps it in the
 *  header's own `position: relative` div (V3:88) so the underline and the panel can anchor.
 *
 *  Three mechanisms have no counterpart anywhere in this design and are composed, not measured
 *  (John's ruling: click-to-open, keyboard navigation, Escape, outside-click dismissal): Escape
 *  and outside-click (A14.4/A14.5, sharing A13's `trackMenuDismiss`), Arrow/Home/End movement
 *  (A14.1's `giveFocus` plus A14.2's per-row `keys`), and the CSS custom property
 *  `--rf-give-underline` that lets the wrapper's :hover drive a child element's transform. The
 *  last one exists because the live underline is an `::after` on the link and this design's only
 *  pseudo idiom is a flat `style-hover` (42 uses, no other kind) — it cannot express
 *  `:hover::after`. A single inherited variable, set by the wrapper's own hover rule and read by
 *  the underline's inline `scaleX()`, reproduces the live behaviour exactly: hovering anywhere on
 *  the control OR the open panel shows the bar, which is what `li:hover` does on the live site
 *  because the panel is inside the li there.
 *
 *  There is no keyboard HIGHLIGHT: focus is the highlight, exactly as on vinfoundation.org, which
 *  has no focus style of its own. That is also why no `style-focus` appears here — the design has
 *  never used a `style-` kind other than `hover`, and inventing one would be an untested path on
 *  the reference runtime.
 */
const A14 = {
  date: '2026-09-08',
  ruling: 'the Give button must be identical to the https://vinfoundation.org/ where the button is an actual drop down (match button design pixel-by-pixel)'
};

/** A14.1 — `giveFocus`, a class property beside the other class members, so the trigger's key
 *  handler and each row's key handler share one implementation. Anchored on `money(n) {`
 *  (script V3:1893, one occurrence), the first member after `componentDidMount`, so it does not
 *  collide with A13.1's `setF` anchor. Detached rows are filtered out: Vue calls a function ref
 *  with `null` on unmount, and the menu unmounts every time it closes. */
const A14_1: Amendment = {
  id: 'A14.1', ...A14,
  find: '  money(n) {\n',
  replace: [
    '  // Arrow-key movement inside the Give menu. Focus IS the highlight — vinfoundation.org has',
    '  // no focus style of its own either — so this moves focus and nothing else. Wraps both ways.',
    '  giveFocus = (i) => {',
    '    const els = (this._giveItemEls || []).filter(Boolean);',
    '    if (!els.length) return;',
    '    els[((i % els.length) + els.length) % els.length].focus();',
    '  };',
    '',
    '  money(n) {',
    ''
  ].join('\n'),
  count: 1
};

/** A14.2 — `renderVals()`: the menu's open state, the two refs, the trigger and underline styles,
 *  the four links with their row style, per-row ref, per-row key handler and dismiss-on-choose,
 *  and the trigger's own key handler. Anchored after `toggleUserMenu` (one occurrence), which is
 *  the header block's last key, so the Give keys sit with the header's other two menus. The two
 *  `'Montserrat'` declarations are the ONLY two in the design: A14.6's face reaches this control
 *  and its menu and nothing else, which is the scope John's ruling names.
 *
 *  Two widenings from the final whole-branch review, both ruled. m6: `giveMenuKeys` takes Home
 *  and End while the menu is open, which the per-row `keys` already had and the trigger — the one
 *  element a keyboard user starts from — did not; the guard is `marketMenuKeys`'s, so the two
 *  triggers answer the same keys in the same states. m7: the anchor line `toggleUserMenu` and both
 *  of Give's own open paths now clear the OTHER menus as well, so "opening me closes you" holds in
 *  every direction rather than only outward from Give. */
const A14_2: Amendment = {
  id: 'A14.2', ...A14,
  find: '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu }),\n',
  replace: [
    '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false }),',
    '      // The Give control, measured on vinfoundation.org (John, 2026-09-08). The literals are',
    '      // the live site\'s, not this design\'s tokens: #339dde is the idle pill, #07386f the',
    '      // hover/open pill and the panel border and the row text, 10px the pill radius, 4.34px',
    '      // the gap from the pill to the 3px underline, 28px the gap from the pill to the panel.',
    '      giveMenuOpen: !!s.giveMenu,',
    '      // `giveMenuAt: null` on every pointer open: the pending index below belongs to the',
    '      // KEYBOARD, and a stale one would drag a mouse user into the list on the next open.',
    '      // `marketMenu` too (final review m7): the invariant is that opening one menu closes',
    '      // the others, and Browse renders this control and the metro listbox on one screen.',
    '      toggleGiveMenu: () => this.setState({ giveMenu: !s.giveMenu, giveMenuAt: null, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1 }),',
    '      giveMenuRef: (el) => { this._giveMenuEl = el || null; },',
    '      giveButtonRef: (el) => { this._giveButtonEl = el || null; },',
    '      // The panel\'s own mount is the first moment its links exist, so it is where an arrow',
    '      // key that OPENED the menu spends its pending index — the arrow itself cannot, having',
    '      // seeded it while the sc-if was still unrendered. Same callback-ref idiom the compare',
    '      // menu ships (md.compareMenuRef) and A13 reuses for marketPanelRef, and it fires on',
    '      // mount on both targets, children before parent, so the row refs are already in.',
    '      // Spent once: a re-render mounts the panel again and must not re-steal focus.',
    '      givePanelRef: (el) => {',
    '        const at = this.state.giveMenuAt;',
    '        if (!el || at == null) return;',
    '        this.setState({ giveMenuAt: null });',
    '        this.giveFocus(at);',
    '      },',
    '      giveWrapStyle: "position: relative; display: flex; align-items: center;",',
    '      giveButtonStyle: "display: flex; align-items: center; padding: 2px 22px; font-family: \'Montserrat\', var(--rf-display); font-size: 18px; font-weight: 600; line-height: 24.3px; white-space: nowrap; color: #ffffff; background: " +',
    '        (s.giveMenu ? "#07386f" : "#339dde") + "; border: 0; border-radius: 10px; cursor: pointer; transition: background .4s;",',
    '      giveUnderlineStyle: "position: absolute; left: 0; right: 0; top: calc(100% + 4.34px); height: 3px; background: #339dde; transform-origin: center; transition: transform .3s cubic-bezier(.58,.3,.005,1); transform: scaleX(" +',
    '        (s.giveMenu ? "1" : "var(--rf-give-underline, 0)") + ");",',
    '      giveLinks: [',
    '        { label: "Annual Fund", href: "https://vinfoundation.org/give/" },',
    '        { label: "Cor Group", href: "https://vinfoundation.org/cor/" },',
    '        { label: "Legacy Giving", href: "https://vinfoundation.org/legacy-giving/" },',
    '        { label: "Dr. Sophia Yin Memorial Fund", href: "https://vinfoundation.org/resources/dr-sophia-yin-memorial-fund/" }',
    '      ].map((g, i) => Object.assign({}, g, {',
    '        rowStyle: "display: flex; align-items: center; padding: 8px 20px; border-left: 8px solid transparent; font-family: \'Montserrat\', var(--rf-display); font-size: 14px; font-weight: 600; line-height: 21px; color: #07386f; background: none; white-space: nowrap; text-decoration: none;",',
    '        ref: (el) => { const a = this._giveItemEls || (this._giveItemEls = []); a[i] = el || null; },',
    '        keys: (e) => {',
    '          if (e.key === "ArrowDown") { e.preventDefault(); return this.giveFocus(i + 1); }',
    '          if (e.key === "ArrowUp") { e.preventDefault(); return this.giveFocus(i - 1); }',
    '          if (e.key === "Home") { e.preventDefault(); return this.giveFocus(0); }',
    '          if (e.key === "End") { e.preventDefault(); return this.giveFocus(-1); }',
    '        },',
    '        pick: () => this.setState({ giveMenu: false })',
    '      })),',
    '      giveMenuKeys: (e) => {',
    '        // Home and End, on the TRIGGER as well as inside the menu, and only while the menu',
    '        // is open — exactly where marketMenuKeys has them (final review m6). With the menu',
    '        // shut there is no list for an end to be an end of.',
    '        if (s.giveMenu && (e.key === "Home" || e.key === "End")) {',
    '          e.preventDefault();',
    '          return this.giveFocus(e.key === "Home" ? 0 : -1);',
    '        }',
    '        if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;',
    '        e.preventDefault();',
    '        const at = e.key === "ArrowDown" ? 0 : -1;',
    '        if (s.giveMenu) return this.giveFocus(at);',
    '        // Already-open: the panel is mounted, so focus moves here and now. Opening CANNOT do',
    '        // that — the app\'s setState runs its callback synchronously (dc-logic.js) and Vue',
    '        // has not rendered the panel yet, so the index is seeded and givePanelRef spends it.',
    '        this.setState({ giveMenu: true, giveMenuAt: at, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1 });',
    '      },',
    ''
  ].join('\n'),
  count: 1
};

/** A14.3 — the markup. The inert <button> at V3:104 becomes the header's own wrapper/trigger/
 *  sc-if/panel shape (V3:88-98) carrying the measured live values. The chevron is Font Awesome
 *  Free 5.15.4's `solid/angle-down` inlined verbatim — the live glyph, at the live 11.25 x 18 px
 *  box (FA's .625em advance at 18px) — rather than a new icon file, so `icons.test.ts` and the
 *  bundle's asset folder are both untouched; inline <svg> with a camelCase viewBox is already a
 *  design idiom (V3:1416) and `parseDocument` runs with `lowerCaseAttributeNames: false`.
 *  `text-decoration: none` appears in the row's hover as well as its base because the design's own
 *  `a:hover { text-decoration: underline }` (V3:54) would otherwise underline every row; a
 *  generated `.sch…:hover` (0,2,0) beats `a:hover` (0,1,1) on both targets. The panel is
 *  `width: max-content` because an absolutely positioned box shrink-to-fits inside its ~106px
 *  containing block otherwise — the live site reaches the same 264px through SmartMenus' inline
 *  width, and `min-width: 130px` is its measured `subMenusMinWidth: "10em"` at the panel's 13px em. */
const A14_3: Amendment = {
  id: 'A14.3', ...A14,
  find: '        <button style="font-family: var(--rf-display); font-size: 14px; font-weight: 500; color: var(--color-white); background: var(--color-blue); border: 0; border-radius: 6px; padding: 10px 20px; cursor: pointer;" style-hover="background: var(--color-navy);">Give</button>\n',
  replace: [
    '        <div ref="{{ giveMenuRef }}" style="{{ giveWrapStyle }}" style-hover="--rf-give-underline: 1;">',
    '          <button ref="{{ giveButtonRef }}" onClick="{{ toggleGiveMenu }}" onKeyDown="{{ giveMenuKeys }}" aria-haspopup="menu" aria-controls="give-menu" aria-expanded="{{ giveMenuOpen }}" style="{{ giveButtonStyle }}" style-hover="background: #07386f;">Give<span style="display: flex; align-items: center; line-height: 1; padding: 10px 0 10px 10px; margin: -10px 0;"><svg width="11.25" height="18" viewBox="0 0 320 512" fill="currentColor" aria-hidden="true" style="display: block;"><path d="M143 352.3L7 216.3c-9.4-9.4-9.4-24.6 0-33.9l22.6-22.6c9.4-9.4 24.6-9.4 33.9 0l96.4 96.4 96.4-96.4c9.4-9.4 24.6-9.4 33.9 0l22.6 22.6c9.4 9.4 9.4 24.6 0 33.9l-136 136c-9.2 9.4-24.4 9.4-33.8 0z"></path></svg></span></button>',
    '          <div style="{{ giveUnderlineStyle }}"></div>',
    '          <sc-if value="{{ giveMenuOpen }}" hint-placeholder-val="{{ false }}">',
    '            <div role="menu" aria-label="Give" id="give-menu" ref="{{ givePanelRef }}" style="position: absolute; left: 0; top: calc(100% + 28px); z-index: 60; width: max-content; min-width: 130px; padding: 0; background: #ffffff; border: 1px solid #07386f; border-radius: 0;">',
    '              <sc-for list="{{ giveLinks }}" as="g" hint-placeholder-count="4">',
    '                <a href="{{ g.href }}" role="menuitem" ref="{{ g.ref }}" onClick="{{ g.pick }}" onKeyDown="{{ g.keys }}" style="{{ g.rowStyle }}" style-hover="background: #07386f; color: #ffffff; text-decoration: none;">{{ g.label }}</a>',
    '              </sc-for>',
    '            </div>',
    '          </sc-if>',
    '        </div>',
    ''
  ].join('\n'),
  count: 1
};

/** A14.4 — the Give branch of A13.4's `pointerdown` closure. Placed AHEAD of the metro guard and
 *  written so it changes nothing about it: if `giveMenu` is falsy the block is skipped entirely,
 *  and if it is open the click is tested against the Give wrapper alone. */
const A14_4: Amendment = {
  id: 'A14.4', ...A14,
  find: [
    '    const down = (e) => {',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  replace: [
    '    const down = (e) => {',
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && e.target && give.contains(e.target))) this.setState({ giveMenu: false });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  count: 1
};

/** A14.5 — the Give branch of A13.4's `keydown` closure. A13's single guard
 *  (`!marketMenu || key !== "Escape"`) becomes two with the same net effect for the metro menu —
 *  proved by `logic.test.ts`'s "A13's metro dismissals are unchanged" case — with the Give close,
 *  and the focus return the live site gets for free from the browser, in between. */
const A14_5: Amendment = {
  id: 'A14.5', ...A14,
  find: [
    '    const key = (e) => {',
    '      if (!this.state.marketMenu || e.key !== "Escape") return;',
    '      this.setState({ marketMenu: false, marketMenuAt: -1 });',
    '    };',
    ''
  ].join('\n'),
  replace: [
    '    const key = (e) => {',
    '      if (e.key !== "Escape") return;',
    '      if (this.state.giveMenu) {',
    '        this.setState({ giveMenu: false });',
    '        if (this._giveButtonEl) this._giveButtonEl.focus();',
    '      }',
    '      if (!this.state.marketMenu) return;',
    '      this.setState({ marketMenu: false, marketMenuAt: -1 });',
    '    };',
    ''
  ].join('\n'),
  count: 1
};

/** A14.6 — the face itself (John, 2026-09-08, ruling A14 GO: "Self-host Montserrat 600 under the
 *  SIL Open Font Licence, scoped exclusively to the Give button and its menu. Keep the rest of the
 *  design typography unchanged."). One `@font-face` in the helmet's own <style> block, beside the
 *  `:root` tokens — the design's only stylesheet of its own — pointing at the official Montserrat
 *  SemiBold woff2 the bundle now ships in `assets/fonts/`, with `OFL.txt` beside it.
 *
 *  It reaches the two targets by the two paths every other bundle asset does: the reference server
 *  serves the bundle root, so `assets/fonts/…` resolves there; the app carries the same rule in
 *  `frontend/src/styles/global.css` — the helmet's port, where the four Leaflet tooltip rules
 *  already live — under the platform spec's §3 rule-1 rewrite (`assets/` → `/assets/`), against a
 *  byte-identical copy in `frontend/public/assets/fonts/`. `frontend/tests/fonts.test.ts` derives
 *  the app's rule FROM this one and proves the two copies of the file are identical, so the pixel
 *  gate can never be comparing two different typefaces.
 *
 *  Nothing else changes face: `--rf-display` and `--rf-serif` are untouched, and the only two
 *  declarations naming the family in the whole design are A14.2's trigger and row styles
 *  (asserted both ways in `design-amendments.test.ts`). A1's ruling — "keep the V2 header and do
 *  not restyle header or fonts" — is why the scope is stated as a rule and machine-checked rather
 *  than left to review. */
const A14_6: Amendment = {
  id: 'A14.6', ...A14,
  find: '<style>\n  :root {\n',
  replace: [
    '<style>',
    '  /* Montserrat 600 — the face vinfoundation.org sets the Give button in, self-hosted under',
    '     the SIL Open Font Licence 1.1 (assets/fonts/OFL.txt, shipped beside the file). Scoped to',
    '     the Give control and its menu by A14.2; no other element names it. */',
    '  @font-face {',
    '    font-family: \'Montserrat\';',
    '    src: url(\'assets/fonts/Montserrat-SemiBold.woff2\') format(\'woff2\');',
    '    font-weight: 600; font-style: normal; font-display: swap;',
    '  }',
    '  :root {',
    ''
  ].join('\n'),
  count: 1
};

/** A14.7 — Tab out of the open menu closes it (review round 1, m2 — ruled). John's ruling named
 *  Escape and outside-click; Tab is the third way out of a menu the keyboard can now enter, and
 *  without it the panel stayed open behind the focus ring — the same "a dropdown a keyboard cannot
 *  dismiss is not shippable" reasoning A13 and A14.4/A14.5 already applied. The live site has no
 *  focusout dismissal either, because it has no keyboard entry to need one.
 *
 *  Modelled on A13.4's own two closures and registered and torn down beside them, so
 *  `trackMenuDismiss` keeps having exactly one shape. `relatedTarget` is where focus is GOING:
 *  anywhere inside the wrapper (the trigger, another row) is a move within the control, and `null`
 *  is the browser leaving the document — a window blur, which must not close anything. When this
 *  closure was written it read `giveMenu` and nothing else; A13.8 (applied last) later gave the metro
 *  listbox the same dismissal inside it. */
const A14_7: Amendment = {
  id: 'A14.7', ...A14,
  find: [
    '    this._onDocDown = down;',
    '    this._onDocKey = key;',
    '    document.addEventListener("pointerdown", down, true);',
    '    document.addEventListener("keydown", key, true);',
    '  }',
    '',
    '  componentWillUnmount() {',
    '    if (this._onResize) window.removeEventListener("resize", this._onResize);',
    '    if (this._onDocDown) document.removeEventListener("pointerdown", this._onDocDown, true);',
    '    if (this._onDocKey) document.removeEventListener("keydown", this._onDocKey, true);',
    '  }',
    ''
  ].join('\n'),
  replace: [
    '    const out = (e) => {',
    '      if (!this.state.giveMenu) return;',
    '      const give = this._giveMenuEl;',
    '      const to = e.relatedTarget;',
    '      if (!to || (give && give.contains(to))) return;',
    '      this.setState({ giveMenu: false });',
    '    };',
    '    this._onDocDown = down;',
    '    this._onDocKey = key;',
    '    this._onDocOut = out;',
    '    document.addEventListener("pointerdown", down, true);',
    '    document.addEventListener("keydown", key, true);',
    '    document.addEventListener("focusout", out, true);',
    '  }',
    '',
    '  componentWillUnmount() {',
    '    if (this._onResize) window.removeEventListener("resize", this._onResize);',
    '    if (this._onDocDown) document.removeEventListener("pointerdown", this._onDocDown, true);',
    '    if (this._onDocKey) document.removeEventListener("keydown", this._onDocKey, true);',
    '    if (this._onDocOut) document.removeEventListener("focusout", this._onDocOut, true);',
    '  }',
    ''
  ].join('\n'),
  count: 1
};

/** A14.8 — the last leg of the "opening me closes you" invariant (final review m7 — ruled).
 *  `toggleGiveMenu` and the arrow-open already cleared `navMenu` and `userMenu`, and A14.2 and
 *  A13.2 close Give from `toggleUserMenu` and `toggleMarketMenu`; `toggleNavMenu` is the one
 *  toggle no other amendment touches, so it gets its own literal. The design's own line already
 *  clears `userMenu`, which is the idiom this follows exactly. Nothing else about it changes. */
const A14_8: Amendment = {
  id: 'A14.8', ...A14,
  find: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false }),\n',
  replace: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false }),\n',
  count: 1
};

/** A13.8 — Tab out of the metro listbox closes it (final review m4 — ruled), on exactly the
 *  reasoning A14.7 was accepted on two commits earlier: Escape and outside-click were the two
 *  dismissals A13.4 gave the control, and Tab is the third way out of a dropdown the keyboard can
 *  now enter. Two dropdowns shipping in one branch with different dismissal sets is the
 *  inconsistency the whole-branch review exists to catch, and A13.3's `tabindex="-1"` makes Tab
 *  from the trigger leave the control outright, which is precisely when the panel would otherwise
 *  be left open behind the focus ring.
 *
 *  It applies LAST, after A14.7 — the `out` closure it edits is A14.7's own, and A13.4 cannot
 *  reach forward to a closure that does not exist when it runs. The shape is A14.4's: the shared
 *  guard first, then the Give branch, then the metro one, so the Give behaviour is bit-identical
 *  (a null `relatedTarget` returned before, and returns before, on both branches). */
const A13_8: Amendment = {
  id: 'A13.8', ...A13,
  find: [
    '    const out = (e) => {',
    '      if (!this.state.giveMenu) return;',
    '      const give = this._giveMenuEl;',
    '      const to = e.relatedTarget;',
    '      if (!to || (give && give.contains(to))) return;',
    '      this.setState({ giveMenu: false });',
    '    };',
    ''
  ].join('\n'),
  replace: [
    '    const out = (e) => {',
    '      // `relatedTarget` is where focus is GOING, and a null one is the browser leaving the',
    '      // document altogether — a window blur, which dismisses neither menu.',
    '      const to = e.relatedTarget;',
    '      if (!to) return;',
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && give.contains(to))) this.setState({ giveMenu: false });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    '      const host = this._marketMenuEl;',
    '      if (host && host.contains(to)) return;',
    '      this.setState({ marketMenu: false, marketMenuAt: -1 });',
    '    };',
    ''
  ].join('\n'),
  count: 1
};

/** A15 — every uploaded photograph renders, with its OWN description (A-L11, John 2026-09-09).
 *
 *  Root cause. `photoSet(p)` renders exactly SIX captioned slots per practice and the captions are
 *  the DESIGN's, fixed by practice type; the API sent no caption at all. So a photograph could
 *  only ever sit under a TRUE caption by being the one that shows that slot's subject — a ceiling
 *  of six per hospital that hotfix 2 (A-L10) turned into a floor of nothing: it left a slot empty
 *  wherever no image matched by eye, so of the 195 photographs in John's eighteen folders only 73
 *  were rendered (`def_veterinary_hospital`: nine down to three).
 *
 *  The rule is now the opposite, and these six literal script edits are it:
 *
 *    - a photograph carries its OWN description — `p.photoCaptions[i]`, the API's new
 *      `photo_captions` (`migrations/090_listing_photo_captions.sql`), the supplier's words today
 *      and the seller's in Wave 2b — and the design's fixed slot caption is the FALLBACK where
 *      there is none (A15.1, A15.2);
 *    - every photograph past the sixth gets a tile of its own, appended after the six slots, with
 *      "Photo N" as the last-resort caption because the design has no seventh caption to lend
 *      (A15.3a-A15.3d: the head and the tail of the generic branch's `return`, then the head and
 *      the tail of the `p2` branch's, four edits because the two ends of each are far apart).
 *
 *  No template edit is needed: the detail grid (`<sc-for list="{{ d.photos }}">`) and the docked
 *  panel's carousel (`withPhoto`, `counter`, `dots`) already iterate whatever `photoSet` returns,
 *  so eleven tiles wrap into more rows and the carousel counts 1/11 on their own.
 *
 *  PIXEL-SAFE by construction, and for the same reason A12 was: the design's fixtures carry no
 *  `photos` and no `photoCaptions` AT ALL — `p2`'s three photographs are the `SRC` map, keyed by
 *  slot id, not `p.photos` — so `p.photoCaptions &&` is falsey and every caption is the design's
 *  own, and `p.photos &&` is falsey so the extra arm is `[]` and no tile is appended anywhere.
 *  `src/listings/load.ts` adds `photoCaptions` only when the API actually sent one, which the D6
 *  design-fixture stub never does. Proved twice over — `src/logic.test.ts`
 *  characterises both halves, and the 43 approved states keep their baseline hashes.
 */
const L11 = {
  date: '2026-09-09',
  ruling: 'HAS FAILED and wiped out all the images - if the logic is trying to match and failing then surface all images uploaded and have the user articulate what it is and render ALL images - what was 9 images now are only showing 3 after this hotfix!!!'
};

/** A15.1 — `photoSet`'s `p2` branch: the tile's caption and its placeholder both prefer the
 *  photograph's own description. `SRC` and the three `p.photos` expressions A12.2 wrote are
 *  untouched — this edit is about the words, not the bytes. */
const A15_1: Amendment = {
  id: 'A15.1', ...L11,
  find: '        return { id, caption: v[1], index: i + 1, placeholder: name + " — " + v[1], src: SRC[id]',
  replace: '        return { id, caption: (p.photoCaptions && p.photoCaptions[i]) || v[1], index: i + 1, placeholder: name + " — " + ((p.photoCaptions && p.photoCaptions[i]) || v[1]), src: SRC[id]',
  count: 1
};

/** A15.2 — the same two substitutions in the generic branch, where they are three separate
 *  lines. The design's six captions stay exactly where they are: they are what a photograph with
 *  no description of its own still reads. */
const A15_2: Amendment = {
  id: 'A15.2', ...L11,
  find: '      caption: v[1],\n      index: i + 1,\n      placeholder: name + " — " + v[1],',
  replace: '      caption: (p.photoCaptions && p.photoCaptions[i]) || v[1],\n      index: i + 1,\n      placeholder: name + " — " + ((p.photoCaptions && p.photoCaptions[i]) || v[1]),',
  count: 1
};

/** A15.3a — the generic branch appends one tile per photograph beyond the sixth. `views.length`
 *  is the design's own slot count, so the six captioned slots keep their ids, their captions and
 *  their indices, and the extras continue the numbering the carousel counts on. Applied AFTER
 *  A15.2, whose output it matches. */
const A15_3a: Amendment = {
  id: 'A15.3a', ...L11,
  find: '    return views.map((v, i) => ({\n      id: "ph-" + p.id + "-" + v[0],\n      caption: (p.photoCaptions && p.photoCaptions[i]) || v[1],',
  replace: '    const tiles = views.map((v, i) => ({\n      id: "ph-" + p.id + "-" + v[0],\n      caption: (p.photoCaptions && p.photoCaptions[i]) || v[1],',
  count: 1
};

/** A15.3b — the tail of the same expression: the extras themselves, and the concatenation that
 *  returns them. Split from A15.3a only because the two ends of one `return` are far apart in the
 *  file; the `find` carries the generic branch's whole `src:`/`hasSrc`/`noSrc` line and
 *  `photoSet`'s own closing brace with it, so it cannot reach any other `}));`. */
const A15_3b: Amendment = {
  id: 'A15.3b', ...L11,
  find: '      src: (p.photos && p.photos[i]) || "", hasSrc: !!(p.photos && p.photos[i]), noSrc: !(p.photos && p.photos[i])\n    }));\n  }',
  replace: '      src: (p.photos && p.photos[i]) || "", hasSrc: !!(p.photos && p.photos[i]), noSrc: !(p.photos && p.photos[i])\n    }));\n'
    + '    const extra = ((p.photos && p.photos.length > views.length) ? p.photos.slice(views.length) : []).map((src, k) => {\n'
    + '      const i = views.length + k;\n'
    + '      const cap = (p.photoCaptions && p.photoCaptions[i]) || ("Photo " + (i + 1));\n'
    + '      return { id: "ph-" + p.id + "-extra" + (k + 1), caption: cap, index: i + 1, placeholder: name + " — " + cap, src: src || "", hasSrc: !!src, noSrc: !src };\n'
    + '    });\n'
    + '    return tiles.concat(extra);\n  }',
  count: 1
};

/** A15.3c / A15.3d — the same append in the `p2` branch, whose six slots are an inline array
 *  rather than `views`, so its slot count is `tiles.length`. A15.3d's `find` is anchored on the
 *  `const equine` line that follows the branch, which is what keeps it off the generic branch's
 *  own `});`. `p2` is a design fixture and will never carry a seventh photograph, but a branch
 *  that behaves differently from the one beside it is the kind of divergence the next reader
 *  pays for. */
const A15_3c: Amendment = {
  id: 'A15.3c', ...L11,
  find: '    if (p.id === "p2") {\n      const name = this.practiceName(p);\n      return [',
  replace: '    if (p.id === "p2") {\n      const name = this.practiceName(p);\n      const tiles = [',
  count: 1
};

const A15_3d: Amendment = {
  id: 'A15.3d', ...L11,
  find: '      });\n    }\n    const equine = p.type === "Large animal";',
  replace: '      });\n'
    + '      const extra = ((p.photos && p.photos.length > tiles.length) ? p.photos.slice(tiles.length) : []).map((src, k) => {\n'
    + '        const i = tiles.length + k;\n'
    + '        const cap = (p.photoCaptions && p.photoCaptions[i]) || ("Photo " + (i + 1));\n'
    + '        return { id: "ph-" + p.id + "-extra" + (k + 1), caption: cap, index: i + 1, placeholder: name + " — " + cap, src: src || "", hasSrc: !!src, noSrc: !src };\n'
    + '      });\n'
    + '      return tiles.concat(extra);\n    }\n    const equine = p.type === "Large animal";',
  count: 1
};

// ---------------------------------------------------------------------------------------
// A16 — the seller wizard and dashboard read and write the real API (spec 2026-09-08 D23,
// controller amendments A-SL17, A-SL20 and A-SL22).
//
// The precedent is A5 (sign-in through the `auth` adapter) and A12 (the design reads a listing's
// own name and photographs): literal script edits, each of which KEEPS THE DESIGN'S OWN PATH when
// no adapter is passed. The reference and the Claude Design preview pass no `listings` prop and
// take the fixture path unchanged, which is what keeps both targets on the same pixels.
//
// One prototype prop joins the seven, for the one state the fixtures cannot express: a real seller
// with no listings at all (A-SL17). `startMyListings` reaches it exactly as `startNotice` reaches
// the sign-in notices — declared in the design, injected per request from `?props=`, never passed
// by the app.
//
// None of these is markup. Step 6's per-tile controls, the four disclosure switches, a revenue
// range on the buyer detail, the document rows and an admin field editor are all Rev 3 (spec §14):
// the approved design has no slot for any of them and inventing one is forbidden. The two places
// the seller has to say something the design has no field for — WHICH file, and WHAT it shows —
// are asked through the browser's own dialogs by the adapter (`pick`, `describe`), which is not
// design surface at all.
// ---------------------------------------------------------------------------------------
const SL = {
  date: '2026-09-08',
  ruling: 'none of the existing Photes and Documents are being render4ed in the "EDIT" of an existing listing by hospital across all the data seeded on and also none of the actual inputs are appearing in the PREVIEW and SUBMIT, it appears to be stubs and not functional, this gap must be corrected and the UX true'
};

/** A16.1 — the dashboard's rows come from the seller's OWN listings, and from nowhere else once
 *  an adapter is present (A-SL22 (1) and A-SL23 (2), on John's A-SL17 ruling: "a real seller with
 *  zero listings should see the dashboard shell with no invented/sample listings").
 *
 *  Three states, not two. `!== undefined`, not `&& length`: a loaded EMPTY array is a real answer
 *  and must empty the table, which is the whole of A-SL17. And where the array is not there at
 *  all, WHO IS ASKING decides: the app has a `listings` adapter and gets zero rows, whatever the
 *  API answered and whether or not it answered — a real seller must never be shown four invented
 *  Austin listings because their load failed (SL7 review, Critical-2) — while the reference and
 *  the Claude Design preview pass no adapter and keep the design's own fixtures, which is what
 *  holds `seller-dash`'s frozen pixels on the reference side.
 *
 *  The APP holds the same pixels through the SUCCESS path: `frontend/tests/harness.ts` answers
 *  `GET /api/seller/listings` with those same four rows (`design-seller-listings.mjs`, derived
 *  from this very array), so the capture is a state the app can actually reach.
 *
 *  `s.myListings` is written by A16.9's bootstrap, by A16.8's transitions, by A16.7's submit and
 *  by A16.15's save-and-exit — and, on the reference alone, by A16.11b's prototype prop. */
const A16_1: Amendment = {
  id: 'A16.1', ...SL,
  find: '      listings: s.sellerListings.map((l) => {',
  replace: '      listings: (s.myListings !== undefined ? s.myListings : (this.props.listings ? [] : s.sellerListings)).map((l) => {',
  count: 1
};

/** A16.2 — Continue and Edit hydrate `w` from the fetched draft and record which listing is being
 *  edited, through A16.17's `openDraft` — the ONE place a `WizardDraft` becomes `editingId`, `w`
 *  and `wizAssets`, shared with A16.14's create (A-SL25 (1)).
 *
 *  A-SL25 (2), on the re-review's Major-A: the REJECTION arm resets what the success arm sets. It
 *  used to switch to the wizard and reset nothing, so a seller who pressed Edit on Cedar Park and
 *  got a 500 or a 429 on `LISTING_READ` landed on step 1 still holding the listing they had edited
 *  BEFORE — its `editingId`, its fields and its photographs, under an error banner. Every Continue
 *  then patched that one, Submit submitted it, and a published one went off the market on the way:
 *  Critical-1's exact failure, on the sibling handler A-SL23 (1) did not name. John's finding, exactly: both handlers were `setState({ sellerView: "wizard", step: 1 })`
 *  and nothing else, so `w` stayed at its empty initial value and every `w.x || "—"` in
 *  `previewRows` rendered an em dash — the "stubs and not functional" in the ruling above. With no
 *  adapter the design's own path runs unchanged, which is why `wizard-step-1`'s baseline does not
 *  move. A refusal lands in `wizErr`, the design's own single error slot (A-SL22 (5): the design's
 *  existing surfaces, never an invented banner). */
const A16_2: Amendment = {
  id: 'A16.2', ...SL,
  find: '        if (l.status === "draft") actions.push({ label: "Continue", go: () => this.setState({ sellerView: "wizard", step: 1 }) });\n'
    + '        else actions.push({ label: "Edit", go: () => this.setState({ sellerView: "wizard", step: 1 }) });',
  replace: '        const openWizard = () => {\n'
    + '          if (!this.props.listings) return this.setState({ sellerView: "wizard", step: 1 });\n'
    + '          return this.props.listings.get(l.id).then(\n'
    + '            (d) => this.openDraft(l.id, d, ""),\n'
    + '            (e) => this.openDraft(null, null, (e && e.message) || "That listing could not be opened.")\n'
    + '          );\n'
    + '        };\n'
    + '        if (l.status === "draft") actions.push({ label: "Continue", go: openWizard });\n'
    + '        else actions.push({ label: "Edit", go: openWizard });',
  count: 1
};

/** A16.3 — View opens the listing the row is about. The design hard-coded `"p1"` because its four
 *  rows are fixtures with no listing behind them; a real row has an id. */
const A16_3: Amendment = {
  id: 'A16.3', ...SL,
  find: 'actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: "p1" }) });',
  replace: 'actions.push({ label: "View", go: () => this.setState({ screen: "detail", detailId: l.id || "p1" }) });',
  count: 1
};

/** A16.4 — step 6's tiles are the listing's real photographs and documents; the design's four-item
 *  literal is what shows with NO ADAPTER, and nothing else ever reaches it.
 *
 *  A-SL25 (1), on the re-review's Critical-A: the ternary keys on `this.props.listings`, exactly as
 *  A16.1's does on the dashboard, and not on whether `wizAssets` happens to be set. Keying on
 *  `s.wizAssets` put CRITICAL-2's defect — the app rendering the design's fixtures as if they were
 *  the seller's — on the wizard: the design's step rail jumps to any step with no patch and no
 *  asset read, so "Create a listing" then "6 Photos and documents" showed a brand-new listing
 *  three photographs that do not exist, and "8 Preview and submit" said "Photos attached 3" on the
 *  one screen whose whole job is to say what is about to be published. `wizAssets` is an ARRAY on
 *  every adapter path now (A16.16 declares it, A16.17 sets it, `[]` on both failure arms); the
 *  `|| []` is belt and braces for the render that happens before any wizard is opened.
 *
 *  `s.wizAssets` is set by A16.17's `openDraft`, by every upload and by every saved step.
 *
 *  The NAME is what the photograph shows, by A-SL20's rule and in this order: the seller's own
 *  caption, then the DESIGN's own slot caption at that position (`photoSet`'s list for the
 *  practice type being edited), then "Photo N" for a photograph past the six slots the design
 *  captions — `main`'s A15.3b's own last resort, so the two agree. Never a filename: `DSC_0431.jpg`
 *  says nothing about what a buyer is looking at, which is the failure John's ruling names.
 *
 *  The `.slice` stays on the FALLBACK only: a real listing's photographs must not be truncated to
 *  three by the counter the design used to fake progress with. */
const A16_4: Amendment = {
  id: 'A16.4', ...SL,
  find: '    const uploads = [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));',
  replace: '    const slots = this.photoSet({ id: "wiz", type: w.type, photos: [], name: w.name, area: w.city });\n'
    + '    const uploads = this.props.listings\n'
    + '      ? (s.wizAssets || []).map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)) }))\n'
    + '      : [{ kind: "Photo", name: "Exterior.jpg" }, { kind: "Photo", name: "Lobby.jpg" }, { kind: "Photo", name: "Treatment.jpg" }, { kind: "PDF", name: "Floor plan.pdf" }].slice(0, 3 + (w.photos || 0));',
  count: 1
};

/** A16.5 — "Add files" opens a real file dialog, puts what it returns where its type belongs and
 *  asks the seller what a photograph shows. UNCAPPED (A-SL20, John: "surface all images uploaded
 *  and have the user articulate what it is and render ALL images") — there is no `Math.min` on
 *  this path and the API's own four-photograph cap went with the same ruling.
 *
 *  ONE promise and ONE rejection handler (A-SL23 (4), on the review's Major-3). The four steps —
 *  choose, upload or store, describe, re-read — are chained inside the adapter's `attach`, so a
 *  refusal at ANY of them lands in `wizErr` instead of escaping as an unhandled rejection with the
 *  new photograph missing from the tiles. `null` is the seller dismissing the dialog: nothing was
 *  added, so nothing is redrawn. A document is routed to the document route by its own type and
 *  is never asked for a caption (A-SL23 (6) m7) — `Floor plan.pdf` is the design's own vocabulary
 *  for a document tile.
 *
 *  With no adapter the design's counter runs unchanged, so the reference's step 6 is byte-identical
 *  (it has no baseline either way — spec §14 item 7 asks Rev 3 for one). A refusal lands in
 *  `wizErr`, the design's own single error slot (logic.js:1197, App.vue:1216-1218).
 *
 *  A-SL25 (8), on the re-review's Info-B: the two guards are SEPARATE. With an adapter present the
 *  design's counter arm is unreachable — the disjunction let a failed `create()` (which leaves
 *  `editingId` null) bump `w.photos` and draw a fourth fixture tile on a listing that does not
 *  exist, which is A16.4's own fixture leak by another route. With no listing behind the wizard
 *  there is nothing to upload onto, so the press does nothing at all; the failed-create banner is
 *  already standing in `wizErr`. */
const A16_5: Amendment = {
  id: 'A16.5', ...SL,
  find: '      addPhoto: () => this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) })),',
  replace: '      addPhoto: () => {\n'
    + '        if (!this.props.listings) return this.setState((st) => ({ w: Object.assign({}, st.w, { photos: Math.min((st.w.photos || 0) + 1, 1) }) }));\n'
    + '        if (!s.editingId) return null;\n'
    + '        return this.props.listings.attach(s.editingId).then(\n'
    + '          (d) => (d ? this.setState({ wizAssets: d.assets, wizErr: "" }) : null),\n'
    + '          (e) => this.setState({ wizErr: (e && e.message) || "That file could not be uploaded." })\n'
    + '        );\n'
    + '      },',
  count: 1
};

/** A16.6 — Continue saves the step. The design's own three validations are untouched and run
 *  FIRST (they must refuse before spending a request against a rate-limited endpoint, which is
 *  A5.1's rule for the sign-in form); only the advance is wrapped. A refusal lands in `wizErr` and
 *  the step does NOT advance, so the seller never walks past a field the server rejected. */
const A16_6: Amendment = {
  id: 'A16.6', ...SL,
  find: '        this.setState({ step: Math.min(8, step + 1), wizErr: "" });',
  replace: '        if (!this.props.listings || !s.editingId) return this.setState({ step: Math.min(8, step + 1), wizErr: "" });\n'
    + '        return this.props.listings.patch(s.editingId, step, w).then(\n'
    + '          (d) => this.setState({ step: Math.min(8, step + 1), wizErr: "", wizAssets: d.assets }),\n'
    + '          (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })\n'
    + '        );',
  count: 1
};

/** A16.7 — Submit posts, then runs the design's own `setState` unchanged, so the "Submitted" card
 *  the design draws appears at once and the dashboard behind it is refreshed with the server's
 *  own rows.
 *
 *  A-SL23 (6) m8: the design's own `setState` also prepends an optimistic row to `sellerListings`,
 *  and with an adapter present that row is never rendered — A16.1 reads `myListings` there and
 *  `sellerListings` only where no adapter was passed. It is left in place because it is the
 *  DESIGN's line and the reference runs it; the reload is what the app shows.
 *
 *  A-SL25 (3), on the re-review's Major-B: the reload is A16.17's `reloadListings()`, which carries
 *  its own rejection arm. Spelled inline, the rejection handler was the SIBLING of the fulfilment
 *  handler and covered `submit()` only — so a 429 on `LISTING_LIST` after a successful submit
 *  escaped as an unhandled promise rejection, which is character for character the shape A-SL23 (4)
 *  had just fixed in `attach`. */
const A16_7: Amendment = {
  id: 'A16.7', ...SL,
  find: '      submit: () => this.setState({ wizSubmitted: true,',
  replace: '      submit: () => (this.props.listings && s.editingId\n'
    + '        ? this.props.listings.submit(s.editingId).then(() => this.reloadListings(), (e) => this.setState({ wizErr: (e && e.message) || "That could not be submitted." }))\n'
    + '        : Promise.resolve()) && this.setState({ wizSubmitted: true,',
  count: 1
};

/** A16.8 — Pause, Republish and Withdraw go through the adapter, then reload. The design's own
 *  optimistic `setState` is kept as the no-adapter path; with an adapter the server's own rows
 *  are what the dashboard shows (A16.1), so the reload is the feedback.
 *
 *  A REFUSAL goes in the row's own `note` (A-SL23 (5), on the review's Major-4). It used to go in
 *  `wizErr`, which only `wizardVals` reads — so a seller who pressed Withdraw on a listing the
 *  server refused (`409 STATE`, `429`) saw nothing at all, and the invisible message then
 *  surfaced later, out of context, in the wizard. `note` is the design's own field on the row the
 *  seller pressed, it needs no new markup, and the next successful load overwrites it. The
 *  dashboard has no error surface of its own; that gap is recorded for John (spec §14) rather
 *  than papered over with an invented banner. */
const A16_8: Amendment = {
  id: 'A16.8', ...SL,
  find: '  setListingStatus(id, status) {\n',
  replace: '  setListingStatus(id, status) {\n'
    + '    if (this.props.listings) {\n'
    + '      const action = status === "paused" ? "pause" : status === "withdrawn" ? "withdraw" : "republish";\n'
    + '      this.props.listings.setStatus(id, action).then(\n'
    + '        () => this.reloadListings(),\n'
    + '        (e) => this.setState((st) => ({ myListings: (st.myListings || []).map((l) => (l.id === id ? Object.assign({}, l, { note: (e && e.message) || "That could not be changed." }) : l)) }))\n'
    + '      );\n'
    + '    }\n',
  count: 1
};

/** A16.9 — the bootstrap loads the seller's own listings, in A5.4's own five-line shape and at the
 *  same seam. Gated on the account actually holding the seller role, so a buyer's session spends no
 *  request on an endpoint it would be refused from.
 *
 *  A refusal renders ZERO rows (A-SL23 (2)): `myListings: []`, never the design's four Austin
 *  fixtures. SL7 left it unset and A16.1 then fell back to those fixtures, so a seller whose load
 *  502'd behind Railway was shown four listings that were not theirs, with live Pause and
 *  Withdraw buttons bound to the fixture ids (review, Critical-2). A16.1's adapter arm answers
 *  zero rows on its own now; this says so at the point where the failure is actually known — and
 *  it is A16.17's `reloadListings()` that says it, the one loader every read of this collection
 *  goes through (A-SL25 (3)). */
const A16_9: Amendment = {
  id: 'A16.9', ...SL,
  find: '    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));\n  }',
  replace: '    else if (this.state.gate === "verify" && this.props.auth) this.props.auth.verify(this.state.gateToken).then(() => this.setState({ gate: "signin", gateToken: "", formNotice: "Your address is verified. Sign in to complete your access request." }), () => this.setState({ gate: "verify-expired", gateToken: "" }));\n'
    + '    if (this.props.listings && me && me.state === "active" && (me.roles || []).indexOf("seller") > -1) this.reloadListings();\n'
    + '  }',
  count: 1
};

/** A16.10 — the `declined` pill (John's ruled default, spec §16 Q1: the label "Declined" in the
 *  `bad` tone). Without it a declined row falls through `map[status] || map.draft` and reads
 *  "Draft" — a seller told their listing is a draft when the VIN Foundation has declined it.
 *  The three colours are `withdrawn`'s own triple, which IS the `bad` tone in `adminVals`'s table
 *  (`bad: ["#494949", "#ffffff", "#494949"]`), so no colour is invented. Pixel-safe: no approved
 *  state has a declined listing — the design's four fixtures are published, in_review, draft and
 *  paused. */
const A16_10: Amendment = {
  id: 'A16.10', ...SL,
  find: '      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"]\n    };',
  replace: '      withdrawn: ["Withdrawn", "#494949", "#ffffff", "#494949"],\n'
    + '      declined: ["Declined", "#494949", "#ffffff", "#494949"]\n    };',
  count: 1
};

/** A16.11a — the eighth declared prototype prop, spliced immediately after A9.1a's
 *  `startAnswerNote` with the same `&quot;` escaping as its neighbours, and with `me`'s own
 *  `json` editor because the value is an array rather than a line of text.
 *
 *  A-SL17 gave the oracle a state the design's fixtures cannot express — a real seller with no
 *  listings — and A-SL22 (1) ruled the mechanism: the same one A8.8b and A9.1a established.
 *  `app.setup.js` declares it too, because `app-generated.test.ts` requires that file to declare
 *  everything the design does; the app never passes it (D-I8-2). */
const STARTMYLISTINGS_ENTRY = '&quot;startMyListings&quot;:{&quot;editor&quot;:&quot;json&quot;,&quot;default&quot;:null,&quot;tsType&quot;:&quot;object&quot;,&quot;section&quot;:&quot;Prototype&quot;,&quot;label&quot;:&quot;Seller listings on load&quot;}';
const A16_11a: Amendment = {
  id: 'A16.11a', ...SL,
  find: STARTANSWERNOTE_ENTRY, replace: `${STARTANSWERNOTE_ENTRY},${STARTMYLISTINGS_ENTRY}`, count: 1
};

/** A16.11b — `componentDidMount` writes it into the dashboard's rows, one line after A16.9's,
 *  which is A9.1b's own shape. An empty ARRAY is truthy, which is the point: `[]` is what the
 *  `seller-dash-empty` state injects and what A16.1 renders as no rows at all, while the default
 *  `null` leaves `myListings` unset and the design's own four fixtures in place. Last, so the APP
 *  — which passes no `startMyListings` — keeps whatever A16.9 loaded. */
const A16_11b: Amendment = {
  id: 'A16.11b', ...SL,
  find: '    if (this.props.listings && me && me.state === "active" && (me.roles || []).indexOf("seller") > -1) this.reloadListings();\n  }',
  replace: '    if (this.props.listings && me && me.state === "active" && (me.roles || []).indexOf("seller") > -1) this.reloadListings();\n'
    + '    if (this.props.startMyListings) this.setState({ myListings: this.props.startMyListings });\n'
    + '  }',
  count: 1
};

/** A16.12 — "Photos attached" counts PHOTOGRAPHS. The design's own tile list is three photographs
 *  and a PDF, so `uploads.length` read four and called them all photographs; with a real listing
 *  behind it the row would tell a seller they had attached seven when five were pictures. A-SL22
 *  (4): every preview row is the truth about the draft.
 *
 *  Pixel-safe: the design's fallback list is `.slice(0, 3 + (w.photos || 0))` and `w.photos` is 0
 *  on every approved state, so the slice is the three Photo tiles and both spellings count 3. */
const A16_12: Amendment = {
  id: 'A16.12', ...SL,
  find: '        { k: "Photos attached", v: String(uploads.length) }',
  replace: '        { k: "Photos attached", v: String(uploads.filter((u) => u.kind === "Photo").length) }',
  count: 1
};

/** A16.13 — the preview names the listing's OWN state, not Texas. A12.8/A12.9's ruled edit, in the
 *  one place the wizard makes the same claim: the design's four fixtures are all in the Austin
 *  metro, so `", TX"` was true of every one of them and false of the Oregon hospital a seeded
 *  seller is editing. `w.state` is `serialise_draft`'s own column (the reviewer supplies it at the
 *  first publish, spec Q2 — there is no wizard field for it and inventing one is forbidden).
 *
 *  Pixel-safe: `wizard-preview` is one of the thirteen frozen screens and reaches this row with
 *  `w.city` empty, which is the em dash on both spellings. */
const A16_13: Amendment = {
  id: 'A16.13', ...SL,
  find: '        { k: "General location", v: (w.city || "\\u2014") + (w.city ? ", TX" : "") },',
  replace: '        { k: "General location", v: (w.city || "\\u2014") + (w.city && w.state ? ", " + w.state : "") },',
  count: 1
};

/** A16.14 — "Create a listing" CREATES one (A-SL23 (1), on the review's Critical-1 and Major-1).
 *
 *  Two defects, one line. `create()` was built, tested and never called, so the create path wrote
 *  nothing at all: with `editingId` unset every other handler took its no-adapter fallback and the
 *  wizard was a form over nothing — D23's "it appears to be stubs and not functional" surviving in
 *  the one place John would look first. Worse, the handler reset `step`, `wizSubmitted` and
 *  `wizErr` and NOTHING ELSE, so a seller who had just edited a listing and pressed Save and exit
 *  opened "Create a listing" on that listing's own `editingId`, its `w` and its photographs: every
 *  Continue patched it, every Add files uploaded onto it, Submit submitted it, and a published one
 *  was taken off the market on the way. They believed they were creating; they were overwriting.
 *
 *  So the new listing exists BEFORE the first step renders, and it is READ BACK: `create()` gives
 *  an id and nothing else, so the chain is `create → get → openDraft`, the same setter Edit's
 *  success arm uses (A16.17), which is what makes "a new listing shows no tiles and Photos
 *  attached 0" true rather than merely intended (A-SL25 (1)).
 *
 *  ONE rejection arm, over both requests: `.catch` rather than a sibling handler, which is A-SL23
 *  (4)'s rule applied here — a refused `create()` and a refused `get()` of the listing it just made
 *  land in the same place, and neither can escape unhandled. That place is `openDraft(null, …)`:
 *  the wizard opens with the message in `wizErr` — the design's own error slot — on `editingId`
 *  null, an empty `wizAssets` and the design's own initial `w`, which is the one state in which
 *  nothing can be written to the wrong listing.
 *
 *  `s.creating` guards the double-create (A-SL25 (5), the re-review's Minor-B): the adapter arm
 *  writes nothing visible until the POST answers, so on a slow link the button looks dead and a
 *  second press mints a second draft. The flag is declared in the design's own state literal
 *  (A16.16) and cleared by `openDraft` on both arms. No spinner and no busy copy: the design has
 *  no busy state to borrow and inventing one is forbidden — recorded for Rev 3 (spec §14).
 *
 *  With no adapter the design's own one-liner runs untouched, which is the reference and the
 *  Claude Design preview. On the APP the four `wizard-*` captures reach the wizard through here,
 *  so `prepare()` answers `POST /api/seller/listings` with a fixed id (`newListingBody`) and
 *  `GET /api/seller/listings/{that id}` with the DESIGN's own three photograph tiles as a real
 *  draft (`design-wizard-draft.mjs`, derived from `logic.js`'s own fallback literal): the captures
 *  stay deterministic, they hold their frozen hashes through the SUCCESS path — A-SL23 (2)'s
 *  precedent, the one this round's dashboard already set — and the seller persona gains no
 *  throwaway drafts. */
const A16_14: Amendment = {
  id: 'A16.14', ...SL,
  find: '      startWizard: () => this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, wizErr: "" }),',
  replace: '      startWizard: () => {\n'
    + '        if (!this.props.listings) return this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, wizErr: "" });\n'
    + '        if (s.creating) return null;\n'
    + '        this.setState({ creating: true });\n'
    + '        return this.props.listings.create()\n'
    + '          .then((id) => this.props.listings.get(id).then((d) => this.openDraft(id, d, "")))\n'
    + '          .catch((e) => this.openDraft(null, null, (e && e.message) || "A new listing could not be started."));\n'
    + '      },',
  count: 1
};

/** A16.15 — "Save and exit" SAVES (A-SL23 (3), on the review's Major-2).
 *
 *  `App.vue:1066` labels the wizard's exit button *Save and exit* and `exitWizard` only flipped
 *  the view. While the wizard was a prototype that was a harmless fiction; now that Continue
 *  genuinely `PATCH`es, a seller who filled in step 4 and pressed the button labelled *Save* lost
 *  the step. It patches the step it is on, with the same `patch(editingId, step, w)` Continue
 *  uses, and only then switches to the dashboard — reloading it, because the row's own meta line
 *  is one of the things that just changed.
 *
 *  A refusal keeps the seller IN the wizard with the message in `wizErr`: leaving would throw
 *  away the very fields the server refused to store. A refused RELOAD still exits — the step was
 *  saved, and the dashboard's own load failure is A16.17's business, not this button's, which is
 *  why the chain reads `patch → reloadListings → exit` with ONE rejection arm at the end: it can
 *  only ever be the patch's, because `reloadListings()` settles its own (A-SL25 (3)).
 *
 *  It saves in the adapter's PARTIAL mode — the fourth argument (A-SL27 (2), on the round-3
 *  re-review's MAJOR-D). Continue runs behind the design's own step guards, which make the seller
 *  type the year and the asking price before it advances; this button has no guard and saves
 *  whatever step the seller is on, half-filled, and a draft is incomplete by nature. Sent as `""`,
 *  a blank year was `400 est must be a number.` and the rejection arm — correctly — kept the
 *  seller in the wizard: trapped behind the button labelled *Save*. Partial mode leaves a blank
 *  required number out (the API reads a missing field as "unchanged"), so the arm now fires only on
 *  a genuine server refusal.
 *
 *  Pixel-safe: none of the four `wizard-*` captures presses it, and with no adapter the design's
 *  own one-liner runs untouched. */
const A16_15: Amendment = {
  id: 'A16.15', ...SL,
  find: '      exitWizard: () => this.setState({ sellerView: "dash", wizSubmitted: false }),',
  replace: '      exitWizard: () => {\n'
    + '        if (!this.props.listings || !s.editingId) return this.setState({ sellerView: "dash", wizSubmitted: false });\n'
    + '        return this.props.listings.patch(s.editingId, s.step, s.w, true)\n'
    + '          .then(() => this.reloadListings())\n'
    + '          .then(() => this.setState({ sellerView: "dash", wizSubmitted: false, wizErr: "" }), (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }));\n'
    + '      },',
  count: 1
};

/** A16.16 — the wizard's two adapter-era state keys are DECLARED in the design's own state
 *  literal, beside `step`, `wizErr` and `wizSubmitted` (A-SL25 (1) and (5)).
 *
 *  `wizAssets` is the listing's own asset list. A16.4 keys its tile source on the adapter now, so
 *  it reads `s.wizAssets` on every adapter render — including the very first, before any wizard
 *  has been opened, because `renderVals()` computes `wizardVals()` on every render whatever screen
 *  is showing. Declared `[]` it is an array from the first tick, which is A-SL25 (1)'s
 *  "`wizAssets` is an ARRAY on every adapter path" said at the one place that can guarantee it.
 *
 *  `creating` is A-SL25 (5)'s double-create guard, read and written by A16.14 alone.
 *
 *  Pixel-safe: with no adapter A16.4 never looks at `wizAssets` and nothing reads `creating`, so
 *  the reference and the Claude Design preview render exactly what they rendered before. */
const A16_16: Amendment = {
  id: 'A16.16', ...SL,
  find: '    step: 1, wizErr: "", wizSubmitted: false,',
  replace: '    step: 1, wizErr: "", wizSubmitted: false, wizAssets: [], creating: false,',
  count: 1
};

/** A16.17 — the two helpers the adapter paths share, as class methods beside the other seller
 *  helpers (A-SL25 (1) and (3)).
 *
 *  `openDraft(id, d, err)` is THE one place a `WizardDraft` becomes `editingId`, `w` and
 *  `wizAssets`. Create (A16.14) and Edit (A16.2) both go through it, on both of their arms, so a
 *  new listing and a re-opened one are hydrated identically and a refusal of either can never
 *  leave the listing that was open before it live under the wizard (Major-A). `w` starts from the
 *  DESIGN's own initial literal rather than from `st.w`, so no field of the previous listing —
 *  and not the design's fake `photos` counter either — survives into the next one; the draft's own
 *  values are laid over it, which is the shape A16.2's success arm already had.
 *
 *  `reloadListings()` is the one loader every read of the seller's collection goes through: the
 *  bootstrap (A16.9), the three dashboard transitions (A16.8), submit (A16.7) and save-and-exit
 *  (A16.15). It carries its own rejection arm — `myListings: []`, A-SL23 (2)'s "a failed load
 *  renders zero rows" — so no caller has to remember one, which is exactly what the callers did
 *  not do: spelled inline, each rejection handler was the SIBLING of its fulfilment handler and
 *  covered the transition or the submit but NOT the reload behind it, and a 429 on `LISTING_LIST`
 *  escaped as an unhandled promise rejection (Major-B, the same shape as Major-3 one round
 *  earlier).
 *
 *  Neither is called with no adapter, so the reference never runs either. */
const A16_17: Amendment = {
  id: 'A16.17', ...SL,
  find: '  statusPill(status) {\n',
  replace: '  openDraft(id, d, err) {\n'
    + '    this.setState({ sellerView: "wizard", step: 1, wizSubmitted: false, creating: false, wizErr: err || "", editingId: id, wizAssets: (d && d.assets) || [], w: Object.assign({ name: "", type: "Small animal", est: "", city: "", zip: "", anon: true, price: "", rev: "", revBand: false, docs: "", rooms: "", sqft: "", bldg: "Included", facility: "", desc: "", photos: 0, ownership: "Sole proprietor", hours: "", facilityType: "Standalone", docsLocked: true }, (d && d.w) || {}) });\n'
    + '  }\n'
    + '\n'
    + '  reloadListings() {\n'
    + '    return this.props.listings.list().then((rows) => this.setState({ myListings: rows }), () => this.setState({ myListings: [] }));\n'
    + '  }\n'
    + '\n'
    + '  statusPill(status) {\n',
  count: 1
};

/** A16.18 — the step rail SAVES the step it leaves before it moves (A-SL27 (3), on the round-3
 *  re-review's MAJOR-E — the round-3 implementer's own concern 1, graded Major).
 *
 *  The design gives every rail row `go: () => this.setState({ step: i + 1, wizErr: "" })` — a pure
 *  state move. In the prototype that was harmless: nothing was ever persisted, so nothing could
 *  be lost. This branch made persistence real and PER STEP, on Continue (A16.6) and on Save and
 *  exit (A16.15), and the rail became the one navigation control in the wizard that silently
 *  discarded work: type on step 5, jump to step 6 by the rail, press Save and exit, and step 5 is
 *  gone — under chrome that reads "Saved automatically" (`saveNote`). Silent, reachable by an
 *  ordinary click, no error, no recovery.
 *
 *  Shaped exactly like `next()`'s existing single rejection arm: with an adapter and a listing, the
 *  current step is PATCHed first — in the adapter's partial mode, since the rail has no guard and
 *  the step may be half-filled (A-SL27 (2)) — and only a success moves; a refusal keeps the seller
 *  on the step they were typing on with the message in `wizErr`. Steps 6 and 8 have no fields, so
 *  the adapter re-reads the draft and issues no PATCH (`patch()`'s own rule). `wizAssets` is
 *  re-set from the answer, as Continue's arm sets it.
 *
 *  With no adapter the design's own move runs untouched, which is the reference. On the APP three
 *  of the captures press the rail — `wizard-step-7`, `wizard-preview`, `wizard-done` — so
 *  `prepare()` answers `…/{WIZARD_LISTING_ID}?step=N` with the same design draft it answers the
 *  bare read with (`isDraftStepUrl`), and the render is identical: `baseline-manifest.json`
 *  unchanged is the acceptance. */
const A16_18: Amendment = {
  id: 'A16.18', ...SL,
  find: '        n: String(i + 1), label: n, go: () => this.setState({ step: i + 1, wizErr: "" }),',
  replace: '        n: String(i + 1), label: n, go: () => (!this.props.listings || !s.editingId\n'
    + '          ? this.setState({ step: i + 1, wizErr: "" })\n'
    + '          : this.props.listings.patch(s.editingId, step, w, true).then(\n'
    + '              (d) => this.setState({ step: i + 1, wizErr: "", wizAssets: d.assets }),\n'
    + '              (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }))),',
  count: 1
};

/** A16.19 — the wizard's BACK button saves the step it leaves before it moves (A-SL29 (1), on the
 *  round-4 re-review's MAJOR-F).
 *
 *  A16.18's defect on the other navigation control. Round 3 wrote that the rail was "the ONE
 *  navigation control in the wizard that silently discards work", and A-SL27 (3) was ruled from
 *  that sentence — which was wrong by one control. `back` was the design's own pure state move,
 *  `this.setState({ step: Math.max(1, step - 1), wizErr: "" })`, so: type on step 5 → Back → step 4
 *  → Save and exit wrote step 4 and step 5's typing was gone, under the same "Saved automatically"
 *  chrome, two clicks from the seller's hand.
 *
 *  Mechanically identical to A16.18: with an adapter and a listing the current step is PATCHed
 *  first, in the adapter's partial mode (the step may be half-filled, and Back has no guard),
 *  through Continue's own single rejection arm — a refusal keeps the seller on the step they were
 *  typing on with the message in `wizErr`; steps 6 and 8 have no fields, so the adapter re-reads
 *  and issues no PATCH; `wizAssets` is re-set from the answer — and only then the design's own
 *  `Math.max(1, step - 1)` move, which on step 1 saves and stays.
 *
 *  Pixel-free: no approved capture presses Back (`screens.ts` presses the rail, `/^7/` and `/^8/`),
 *  and with no adapter the design's one-liner runs untouched, so the reference is unmoved. On the
 *  app a Back press is answered by the `…/{id}?step=N` route A16.18 already gave `prepare()`. */
const A16_19: Amendment = {
  id: 'A16.19', ...SL,
  find: '      back: () => this.setState({ step: Math.max(1, step - 1), wizErr: "" }),',
  replace: '      back: () => (!this.props.listings || !s.editingId\n'
    + '        ? this.setState({ step: Math.max(1, step - 1), wizErr: "" })\n'
    + '        : this.props.listings.patch(s.editingId, step, w, true).then(\n'
    + '            (d) => this.setState({ step: Math.max(1, step - 1), wizErr: "", wizAssets: d.assets }),\n'
    + '            (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." }))),',
  count: 1
};

/** A16.20a — the header nav (`go`) saves the step the wizard is on before it navigates away
 *  (A-SL30 (3), on the round-5 re-review's Info-15).
 *
 *  A16.18/A16.19 gave the rail and Back this shape; Info-15 named the two doors that still did
 *  not — this one and Sign out (A16.20b) — both under the same "Saved automatically" chrome,
 *  neither a re-run of MAJOR-E/F because neither writes `step`: `go` only ever changed `screen`,
 *  so returning to Seller showed the typed values (nothing was lost from MEMORY) but nothing had
 *  been PERSISTED, and a tab closed between the two clicks lost it for good.
 *
 *  Mechanically identical to the rail and to Back: with an adapter, the wizard open and a listing
 *  being edited, `patch(editingId, step, w, true)` first — partial mode, since the destination is
 *  not a step and there is no guard to run first — through Continue's own single rejection arm; a
 *  refusal keeps the seller on the wizard with the message in `wizErr` and the navigation never
 *  happens. Steps 6 and 8 have no fields, so the adapter re-reads and issues no PATCH, exactly as
 *  it does for the rail and for Back. Outside the wizard — no adapter, not on `sellerView:
 *  "wizard"`, or a wizard with no `editingId` (the design's own fixture path) — `go` is the design's
 *  one-liner, unchanged, and spends no request.
 *
 *  Pixel-free: no approved capture presses a header nav item from inside the wizard (`screens.ts`
 *  reaches every `wizard-*` state through the rail alone), so no capture's `go` call takes the new
 *  branch at all. */
const A16_20a: Amendment = {
  id: 'A16.20a', ...SL,
  find: '    this.setState({ screen, interest: "closed", userMenu: false });',
  replace: '    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false });\n'
    + '    return this.props.listings.patch(this.state.editingId, this.state.step, this.state.w, true).then(\n'
    + '      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "" }),\n'
    + '      (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })\n'
    + '    );',
  count: 1
};

/** A16.20b — Sign out ATTEMPTS the same save, and ends the session regardless of the answer
 *  (A-SL30 (3), on Info-15).
 *
 *  Deliberately not A16.20a's shape: John's ruling is explicit that a session end is the seller's
 *  own explicit act and must never be held hostage to a save the seller did not ask for — "the
 *  attempt is the most the chrome's 'Saved automatically' can honestly offer". So the save (when
 *  there is one to attempt — an adapter, the wizard open, a listing being edited) is chained with
 *  its OWN swallowed rejection (`.catch(() => {})`, the shape the sign-out call beside it has
 *  always used) ahead of the existing `auth.signOut()` step, never inside its single rejection
 *  arm: whatever the save answers, sign-out proceeds. Outside the wizard, or with no adapter, the
 *  chain starts from `Promise.resolve()` exactly as the design's own one-liner did.
 *
 *  Pixel-free: no approved capture signs out from inside the wizard. */
const A16_20b: Amendment = {
  id: 'A16.20b', ...SL,
  find: '      signOut: () => (this.props.auth ? this.props.auth.signOut().catch(() => {}) : Promise.resolve()).then(() => this.setState({',
  replace: '      signOut: () => (this.props.listings && s.sellerView === "wizard" && s.editingId\n'
    + '          ? this.props.listings.patch(s.editingId, s.step, s.w, true).catch(() => {})\n'
    + '          : Promise.resolve()\n'
    + '        ).then(() => (this.props.auth ? this.props.auth.signOut().catch(() => {}) : Promise.resolve())).then(() => this.setState({',
  count: 1
};

/** A16.21 — the step-6 tile re-describes an EXISTING photograph, seeded ones included, by
 *  clicking it (A-SL25 (10): "click-to-caption for EXISTING photographs is its own task, SL7b").
 *
 *  SL7's `describe()` on upload wired the browser's own prompt to a NEW photograph; the tile
 *  itself had no handler at all, so all 195 seeded photographs — and every asset a seller had
 *  already uploaded — could be captioned once, on the way in, and never again. Each `uploads`
 *  entry gains `describe`, PHOTOGRAPHS ONLY (`a.kind !== "Photo"` is `null`) and only where there
 *  is a listing to save it to (`!s.editingId` is `null` too — the design's own fixture path, with
 *  no adapter, never reaches this branch at all and is untouched).
 *
 *  ONE chained promise, ONE rejection arm into `wizErr` (A-SL23 (4)'s `attach` shape), routed by
 *  the tile's own discriminator (A-SL25 (10)'s pre-flight fact) rather than by parsing the id:
 *  `caption(editingId, a.id, text)` for an ASSET, the positional route `describe(editingId,
 *  a.position, text)` for a SEED entry — the SAME adapter method the ask itself is, overloaded
 *  (`ListingsAdapter#describe`), because the tile's click chains ask-then-write exactly as "Add
 *  files" already does (A16.5): `describe(id, position, describe())`. The tiles refresh from the
 *  returned draft, exactly as `attach()`'s success arm does.
 *
 *  Pixel-safe: A16.22 is the ONLY markup change (one `onClick`, `cursor: pointer`, a `title`, none
 *  of which any approved capture's pixels can see), and no approved capture clicks a tile. */
const A16_21: Amendment = {
  id: 'A16.21', ...SL,
  find: '      ? (s.wizAssets || []).map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)) }))',
  replace: '      ? (s.wizAssets || []).map((a, i) => ({ kind: a.kind, name: a.name || (slots[i] ? slots[i].caption : "Photo " + (i + 1)), describe: a.kind !== "Photo" || !s.editingId ? null : () => (a.source === "asset" ? this.props.listings.caption(s.editingId, a.id, this.props.listings.describe()) : this.props.listings.describe(s.editingId, a.position, this.props.listings.describe())).then((d) => this.setState({ wizAssets: d.assets, wizErr: "" }), (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })) }))',
  count: 1
};

/** A16.22 — the step-6 tile's own markup, so A16.21's handler has something to click (A-SL25 (10)).
 *
 *  One template attribute (`onClick="{{ u.describe }}"`, the design's own way of wiring an
 *  already-bound handler — `wiz.addPhoto`'s own convention): `u.describe` is `null` for a document
 *  tile or when there is nothing to save to, and Vue attaches no listener for a falsy `onClick`,
 *  so the guard lives in the SCRIPT (A16.21) and the template stays a one-line, unconditional
 *  addition to the tile's existing `<div style="width: 92px;">` — one occurrence in the pristine
 *  file. `cursor: pointer` and a static `title` are cosmetic only (invisible to a screenshot and
 *  to the DOM oracle's own walk, which does not compare `title` or computed style) and cost the
 *  pixel budget nothing. */
const A16_22: Amendment = {
  id: 'A16.22', ...SL,
  find: '                            <div style="width: 92px;">',
  replace: '                            <div style="width: 92px; cursor: pointer;" title="Change what this photograph shows" onClick="{{ u.describe }}">',
  count: 1
};

// ---------------------------------------------------------------------------------------
// A17 — Admin › Listings reads the real table (Task SL8; D24 and John's standing rule,
// verbatim: "every Admin tab must show real database data, never dummy rows"). A13-A16 are
// the dropdown, photo-rendering and seller-lifecycle branches'; the family id is derived from
// the tree at branch time (A-SL4), never typed from the plan.
//
// The precedent is A16.1/A16.9 exactly: with an adapter present the tab renders the loaded
// rows or ZERO rows, never the design's own five literal rows, whatever the API answered; the
// reference and the Claude Design preview pass no `adminListings` prop and keep the design's
// fixture path unchanged, which is what holds `admin-listings`'s frozen pixels on that side.
// The APP holds the same pixels through the SUCCESS path: `frontend/tests/harness.ts` answers
// `GET /api/admin/listings` with ALL FIVE of the design's own Listings rows, "Flagged" included —
// A-SL24 (4)'s "the fifth fixture row is not reproduced" is the LIVE mapping's own limit (no
// `listing.status` value backs it, so `admin/listings.ts`'s `PILLS`/`ACTIONS` can never route a
// real row to it), not a limit on this oracle-only fixture — derived from this very fixture by
// `frontend/tests/design-admin-listings.mjs`.
// ---------------------------------------------------------------------------------------
const SL8 = {
  date: '2026-09-09',
  ruling: 'every Admin tab must show real database data, never dummy rows'
};

/** A17.1 — the Listings tab's rows come from the review queue, and from nowhere else once an
 *  adapter is present (A-SL24 (1)). The `!== undefined` test is A16.1's own reason: a LOADED
 *  empty queue is a real answer and must empty the table, and where the array is not there at
 *  all, who is asking decides — the app renders zero rows whatever the API answered (a load
 *  failure never shows a reviewer five listings that are not real), and the reference and the
 *  Claude Design preview keep the design's own fixture. `s.adminListingRows` is written by
 *  A17.2's bootstrap alone: nothing else in this branch sets it. */
const A17_1: Amendment = {
  id: 'A17.1', ...SL8,
  find: '        rows: [\n'
    + '          [cell("Mixed practice — Bastrop", "Submitted September 1"), cell("Dr. Susan Ortiz", "$860K asking · $1.2M revenue · 2 doctors · building leased"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],\n'
    + '          [cell("Specialty practice — Pflugerville", "Submitted August 30"), cell("Dr. Nathan Weiss", "$2.65M asking · $3.8M revenue · 6 doctors · unit available separately"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],\n'
    + '          [cell("Small animal practice — Cedar Park", "Published August 24"), cell("Dr. James Whitfield", "$1.45M asking · 34 views · 2 requests"), cell(null, null, "Published", "ok"), cell(null, null, null, null, [A("Unpublish"), A("Edit")])],\n'
    + '          [cell("Small animal practice — Buda", "Paused by seller August 12"), cell("Dr. Helen Park", "$1.1M asking · hidden from search"), cell(null, null, "Paused", "info"), cell(null, null, null, null, [A("Contact seller")])],\n'
    + '          [cell("Small animal practice — Temple", "Flagged by two members"), cell("Unverified seller", "Figures appear copied from a broker listing; contact details in the description."), cell(null, null, "Flagged", "bad"), cell(null, null, null, null, [A("Investigate", "primary"), A("Unpublish", "danger")])]\n'
    + '        ]\n'
    + '      },',
  replace: '        rows: s.adminListingRows !== undefined ? s.adminListingRows : (this.props.adminListings ? [] : [\n'
    + '          [cell("Mixed practice — Bastrop", "Submitted September 1"), cell("Dr. Susan Ortiz", "$860K asking · $1.2M revenue · 2 doctors · building leased"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],\n'
    + '          [cell("Specialty practice — Pflugerville", "Submitted August 30"), cell("Dr. Nathan Weiss", "$2.65M asking · $3.8M revenue · 6 doctors · unit available separately"), cell(null, null, "In review", "warn"), cell(null, null, null, null, [A("Publish", "primary"), A("Reject", "danger")])],\n'
    + '          [cell("Small animal practice — Cedar Park", "Published August 24"), cell("Dr. James Whitfield", "$1.45M asking · 34 views · 2 requests"), cell(null, null, "Published", "ok"), cell(null, null, null, null, [A("Unpublish"), A("Edit")])],\n'
    + '          [cell("Small animal practice — Buda", "Paused by seller August 12"), cell("Dr. Helen Park", "$1.1M asking · hidden from search"), cell(null, null, "Paused", "info"), cell(null, null, null, null, [A("Contact seller")])],\n'
    + '          [cell("Small animal practice — Temple", "Flagged by two members"), cell("Unverified seller", "Figures appear copied from a broker listing; contact details in the description."), cell(null, null, "Flagged", "bad"), cell(null, null, null, null, [A("Investigate", "primary"), A("Unpublish", "danger")])]\n'
    + '        ])\n'
    + '      },',
  count: 1
};

/** A17.2 — `componentDidMount` loads the review queue, gated on the account holding the staff
 *  or admin role (`page.admin`'s own `["admin","staff"]`, `useStateRouteSync.test.ts`) — A16.9's
 *  own shape and seam, one line after A16.11b's. A refusal renders ZERO rows (`adminListingRows:
 *  []`): leaving it unset would fall back to the design's five fixture rows, showing a reviewer
 *  five listings that are not theirs, with live Publish/Reject/Unpublish buttons on them. Called
 *  directly rather than through a new `reloadAdminListings` method: nothing else in this branch
 *  reloads the queue (the module note in `admin/listings.ts` records the reload-after-decide gap
 *  as a deliberate, recorded scope boundary), so a second call site does not yet exist to share
 *  one with. */
const A17_2: Amendment = {
  id: 'A17.2', ...SL8,
  find: '    if (this.props.startMyListings) this.setState({ myListings: this.props.startMyListings });\n  }',
  replace: '    if (this.props.startMyListings) this.setState({ myListings: this.props.startMyListings });\n'
    + '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n'
    + '  }',
  count: 1
};

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
 *  seeded listings (load.ts replaces `P` in place) resolve exactly as fixtures do.
 *
 *  Step 10 finding (live Chromium, both targets, 2026-09-09): a `focus()` call made synchronously
 *  on a node the SAME patch just mounted is silently dropped — the node has not yet had layout/
 *  style committed, so Chromium does not yet consider it "being rendered" and the call is a
 *  no-op; a manual `.focus()` on the identical element moments later succeeds. JSDOM has no such
 *  restriction, so the plain characterisation this amendment shipped with never caught it. Fixed
 *  by the design's own `setTimeout(…, 0)` idiom (2 pristine uses, `logic.js`'s `_t` debounce),
 *  deferring the call one macrotask — the same fix A19.10's original `focusout` trap needed for
 *  the identical reason, before A-LB3 removed that trap and moved Tab handling into the shared
 *  `keydown` closure instead. `lightboxFocus` is still spent
 *  synchronously; only the `focus()` call is deferred, so a second render before the timer fires
 *  cannot re-arm it. */
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
    '        setTimeout(() => el.focus(), 0);',
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
 *  under a modal scrim. `preventDefault` so an arrow does not also scroll the page behind.
 *
 *  A-LB3 (2026-09-09, ruling on fix round 1's NEEDS_CONTEXT): Tab is handled HERE too, not by a
 *  `focusout` trap (A19.10, below — removed). `box.querySelectorAll("button")` reads the dialog's
 *  own controls in DOM order — Close photo, then Previous/Next when `multiple` — the container
 *  itself is `tabindex="-1"` and is never one of them. On the last, Tab wraps to the first; on
 *  the first, or on the container (where the mount-ref idiom leaves focus right after opening),
 *  Shift+Tab wraps to the last. One code path, no timer, no `relatedTarget`: the browser's own
 *  Tab motion is prevented only at the two wrap points, and left alone everywhere in between. */
const A19_9: Amendment = {
  id: 'A19.9', ...A19,
  find: '    const key = (e) => {\n      if (e.key !== "Escape") return;\n',
  replace: [
    '    const key = (e) => {',
    '      if (this.state.lightbox) {',
    '        if (e.key === "Escape") { e.preventDefault(); this.closeLightbox(); }',
    '        else if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); this.stepLightbox(e.key === "ArrowLeft" ? -1 : 1); }',
    '        else if (e.key === "Tab") {',
    '          const box = this._lightboxEl;',
    '          const controls = box ? Array.from(box.querySelectorAll("button")) : [];',
    '          if (controls.length) {',
    '            const at = controls.indexOf(document.activeElement);',
    '            if (e.shiftKey) { if (at <= 0) { e.preventDefault(); controls[controls.length - 1].focus(); } }',
    '            else if (at === controls.length - 1) { e.preventDefault(); controls[0].focus(); }',
    '          }',
    '        }',
    '        return;',
    '      }',
    '      if (e.key !== "Escape") return;',
    ''
  ].join('\n'),
  count: 1
};

/** A19.10 — A-LB3 (2026-09-09, ruling on fix round 1's NEEDS_CONTEXT — the focus trap does not
 *  hold, and the implementer was right to stop). The `focusout` trap this amendment ORIGINALLY
 *  inserted here — deferring `box.focus()` via `setTimeout` whenever a non-null `relatedTarget`
 *  left the dialog — was tried live in Chromium (Step 10, fix round 1) and found not to hold,
 *  reproducibly: forward Tab off the last control lands on real page content for a keypress
 *  before self-correcting, and Shift+Tab from the first control never reaches the last at all.
 *  Root cause is structural, not a tuning error: a null `relatedTarget` means both "the window
 *  blurred" (must be ignored) and "focus left the dialog's own tabbable set" (must not), and the
 *  arm cannot tell its two cases apart. The mechanism is REMOVED — Tab is instead handled
 *  deterministically in the shared `keydown` closure, A19.9, above — so this closure carries no
 *  lightbox branch at all; the find is still the closure head A14.7 introduced and A13.8 rewrote
 *  (0 in the pristine file, so this still applies after A13.8), and the replace is that same head
 *  plus a comment recording why nothing else stands here, so a reader who finds this closure
 *  otherwise untouched by A19 knows a trap was tried and retracted rather than never attempted. */
const A19_10: Amendment = {
  id: 'A19.10', ...A19,
  find: '    const out = (e) => {\n',
  replace: [
    '    const out = (e) => {',
    '      // A19 (A-LB3, 2026-09-09): a focusout-based trap was tried here — deferring focus back',
    '      // into the dialog whenever it left for a non-null relatedTarget outside it — and found',
    '      // not to hold in real Chromium: a null relatedTarget also occurs at the edges of the',
    '      // dialog\'s own tabbable set, which the arm cannot tell apart from a window blur. Tab is',
    '      // instead handled deterministically in the shared keydown closure above (A19.9).',
    ''
  ].join('\n'),
  count: 1
};

/** A19.11 — `go()`: a screen change closes the lightbox, on the line that already closes the
 *  interest modal for the same reason. (The signed-out branch above it is unreachable with a
 *  lightbox open: a photograph is behind the sign-in gate on both targets.)
 *
 *  Adapted at the SL9 merge (2026-09-09): A16.20a, applied earlier in this list, already split
 *  `go()`'s one-liner into the adapter's save-before-navigate branches, so the original single
 *  `this.setState({ screen, interest: "closed", userMenu: false });` no longer occurs verbatim —
 *  every reachable exit still SETS `screen`/`interest`/`userMenu` together, so the anchor widens
 *  to A16.20a's own two such calls (the no-adapter/no-save early return, and the save's success
 *  arm) rather than shrinking the check. The refusal arm sets none of the three (no screen change
 *  happens on a failed save), so it is correctly left alone. */
const A19_11: Amendment = {
  id: 'A19.11', ...A19,
  find: '    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false });\n'
    + '    return this.props.listings.patch(this.state.editingId, this.state.step, this.state.w, true).then(\n'
    + '      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "" }),\n'
    + '      (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })\n'
    + '    );',
  replace: '    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false, lightbox: null, lightboxFocus: false });\n'
    + '    return this.props.listings.patch(this.state.editingId, this.state.step, this.state.w, true).then(\n'
    + '      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "", lightbox: null, lightboxFocus: false }),\n'
    + '      (e) => this.setState({ wizErr: (e && e.message) || "That could not be saved." })\n'
    + '    );',
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

// A21 — market-data layers do not render absence as zero (controller amendment A-C28, 2026-09-10; Task B8 review).
// Missing figures must be excluded from layers, not bucketed at zero, because a buyer reads zero as "nobody else practises here"
// when we actually have no data. Absence is not zero.

/** A21.1 — remove the `|| 0` defaults that rendered missing figures as zero; instead omit the entry entirely */
const A21_1: Amendment = {
  id: 'A21.1', date: '2026-09-10', ruling: 'a missing figure is omitted, never zeroed (controller amendment A-C28)',
  find: '        econ: (ECON_K[p.id] || 0) * 1000,\n        vets: VETS[p.id] || 0',
  replace: '        econ: ECON_K[p.id] != null ? ECON_K[p.id] * 1000 : undefined,\n        vets: VETS[p.id]',
  count: 1
};

/** A21.1b — at the assembly point, skip metrics with null or undefined values instead of bucketing them */
const A21_1b: Amendment = {
  id: 'A21.1b', date: '2026-09-10', ruling: 'a missing figure is omitted, never zeroed (controller amendment A-C28)',
  find: '        ["income", "pets", "growth", "households", "econ", "competition"].forEach((k) => {\n          const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];\n          const b = this.bucket(k, raw);',
  replace: '        ["income", "pets", "growth", "households", "econ", "competition"].forEach((k) => {\n          const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];\n          if (raw == null) return;\n          const b = this.bucket(k, raw);',
  count: 1
};

/** A21.3 — the growth layer stops naming "2015" in four places: the VALUE_LAYERS label, the
 *  LAYER_META sub-line, the Data Layers card's blurb and caption. The vintage is data-dependent
 *  (2018 today, not 2015) and hard-coded years belong nowhere user-facing (controller amendment A-C29,
 *  completing the incomplete A-C28 amendment A21.3).
 *
 *  Four separate amendments, not one, because they touch different strings in different contexts:
 *  A21.3a handles the VALUE_LAYERS label; A21.3b the LAYER_META sub-line; A21.3c the Data Layers
 *  card; and A21.3d the detail's Growth row (where the API's own vintage-carrying string is split
 *  into display parts, never hard-coded). All four move the vintage into the data itself, never
 *  hard-coded text. */

/** A21.3a — the VALUE_LAYERS growth label (the one A-C28's A21.3 did) */
const A21_3a: Amendment = {
  id: 'A21.3a', date: '2026-09-10', ruling: 'the growth layer stops naming a year it does not use (controller amendment A-C29)',
  find: 'growth: { label: "Population Growth Since 2015 (ACS)",',
  replace: 'growth: { label: "Population Growth (ACS)",',
  count: 1
};

/** A21.3b — the LAYER_META sub-line for the growth layer */
const A21_3b: Amendment = {
  id: 'A21.3b', date: '2026-09-10', ruling: 'the growth layer stops naming a year it does not use (same ruling)',
  find: 'sub: "Change since 2015 · ACS population estimates",',
  replace: 'sub: "Change · ACS population estimates",',
  count: 1
};

/** A21.3c — the Data Layers card's growth row: blurb and caption both need "since 2015" removed */
const A21_3c: Amendment = {
  id: 'A21.3c', date: '2026-09-10', ruling: 'the growth layer stops naming a year it does not use (same ruling)',
  find: '{ n: "4", title: "Population Growth", blurb: "Change since 2015", src: "Census ACS population estimates", metric: "growth", caption: "Growth since 2015",',
  replace: '{ n: "4", title: "Population Growth", blurb: "Change", src: "Census ACS population estimates", metric: "growth", caption: "Growth",',
  count: 1
};

/** A21.3d — the detail's Growth row splits the API string to extract the vintage */
const A21_3d: Amendment = {
  id: 'A21.3d', date: '2026-09-10', ruling: 'the detail Growth row extracts its vintage from the API string, never hard-coded (controller amendment A-C29)',
  find: '{ k: "Growth", v: (p.growth || "").replace(" since 2015", ""), sub: "Since 2015" },',
  replace: '{ k: "Growth", v: (() => { const g = (p.growth || "").split(" since "); return g[0]; })(), sub: (() => { const g = (p.growth || "").split(" since "); return g.length > 1 ? "Since " + g[1] : ""; })() },',
  count: 1
};

/** A21.2 (controller amendment A-C32, D-C32 ruling, Task B10): the docked panel fallback.
 *  When a listing has no place-band figures, it uses drive_10; when it has neither, the card
 *  says "Community data unavailable". The fallback label travels with the row from serve.py,
 *  and the panel reads it as `c.label`.
 *
 *  This amendment is REVERTED (controller amendment A-C29): the economic figure IS payroll
 *  per establishment, not revenue; the metric is merely misnamed `revenue_per_establishment` in the
 *  database, and the design's original labels "Average Practice Payroll (CBP)" / "Avg. payroll per
 *  practice" were correct. The naming stays in the database for schema stability; no code changes. */

/** A21.2b (Task B10, D-C31): the panel's fallback renders no undefined/NaN.
 *  When there are no figures for a listing, the panel should render nothing for competition,
 *  income index, and growth indicators, never a verdict based on undefined data. The `per10k`
 *  ratio becomes undefined when households or vets is undefined; the verdict and bars are only
 *  rendered when per10k is a number. */
const A21_2b: Amendment = {
  id: 'A21.2b', date: '2026-09-10', ruling: 'render no verdict, NaN or undefined for listings without figures (Task B10, D-C31)',
  find: '    const per10k = c.hh ? (c.vets / (c.hh / 10000)) : 0;\n    const incomeNat = 75149; // ACS 2023 U.S. median household income\n    const incomeIdx = Math.round(((c.income - incomeNat) / incomeNat) * 100);\n    const compLevel = per10k < 1.4 ? "Low" : per10k < 2.2 ? "Moderate" : "High";\n    const compFill = per10k < 1.4 ? 1 : per10k < 2.2 ? 2 : 3;',
  replace: '    const per10k = (c.hh && c.vets) ? (c.vets / (c.hh / 10000)) : undefined;\n    const incomeNat = 75149; // ACS 2023 U.S. median household income\n    const incomeIdx = c.income ? Math.round(((c.income - incomeNat) / incomeNat) * 100) : undefined;\n    const compLevel = (per10k !== undefined && per10k < 1.4) ? "Low" : (per10k !== undefined && per10k < 2.2) ? "Moderate" : (per10k !== undefined) ? "High" : undefined;\n    const compFill = (per10k !== undefined && per10k < 1.4) ? 1 : (per10k !== undefined && per10k < 2.2) ? 2 : (per10k !== undefined) ? 3 : 0;',
  count: 1
};

/** A21.2c (Task B10, D-C31): compEstab renders the vets count or nothing.
 *  When c.vets is undefined, compEstab must be undefined, not "undefined". */
const A21_2c: Amendment = {
  id: 'A21.2c', date: '2026-09-10', ruling: 'compEstab renders vets count or nothing, never "undefined" (Task B10, D-C31)',
  find: '      compEstab: String(c.vets),',
  replace: '      compEstab: (c.vets !== undefined) ? String(c.vets) : undefined,',
  count: 1
};

/** A21.2d (Task B10, D-C31): overviewTiles renders only populated tiles.
 *  When c.pop, c.hh or c.income is undefined the tile renders no value, and — since the fix
 *  round of 2026-09-10 — no SUB-LINE either: the sub-lines were built by concatenation, so an
 *  absent growth or income index left the unit behind and the tile read a bare "% (5 yrs)" or
 *  "% vs US" (F-2). The fourth tile (pets) is left verbatim here and guarded by A21.2i. */
const A21_2d: Amendment = {
  id: 'A21.2d', date: '2026-09-10', ruling: 'overviewTiles renders only populated tiles (Task B10, D-C31)',
  find: 'overviewTiles: [\n        { v: this.fmtMetric("households", c.pop), k: "Population", sub: (c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)" },\n        { v: this.fmtMetric("households", c.hh), k: "Households", sub: "ACS 5-year" },\n        { v: "$" + Math.round(c.income / 1000) + "K", k: "Median Income", sub: (incomeIdx > 0 ? "+" : "") + incomeIdx + "% vs US" },\n        { v: this.fmtMetric("households", c.pets), k: "Est. Pet Households", sub: "derived estimate" }\n      ],',
  replace: 'overviewTiles: [\n        { v: (c.pop !== undefined) ? this.fmtMetric("households", c.pop) : undefined, k: "Population", sub: (c.growth !== undefined) ? ((c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)") : undefined },\n        { v: (c.hh !== undefined) ? this.fmtMetric("households", c.hh) : undefined, k: "Households", sub: "ACS 5-year" },\n        { v: (c.income !== undefined) ? "$" + Math.round(c.income / 1000) + "K" : undefined, k: "Median Income", sub: (incomeIdx !== undefined) ? ((incomeIdx > 0 ? "+" : "") + incomeIdx + "% vs US") : undefined },\n        { v: this.fmtMetric("households", c.pets), k: "Est. Pet Households", sub: "derived estimate" }\n      ],',
  count: 1
};

/** A21.2e (Task B10, D-C31): oppTiles checks for undefined before rendering.
 *  The third tile checks c.econ (payroll per establishment). All three should only show
 *  their verdict and "on" status when their metric is defined and passes the threshold. */
const A21_2e: Amendment = {
  id: 'A21.2e', date: '2026-09-10', ruling: 'oppTiles renders verdicts only when metrics are defined (Task B10, D-C31)',
  find: 'oppTiles: [\n        { icon: "$", label: incomeIdx > 25 ? "High" : incomeIdx > 0 ? "Above avg." : "Median", sub: "Affluence", on: incomeIdx > 0 },\n        { icon: "↗", label: c.growth > 20 ? "Strong" : c.growth > 8 ? "Steady" : "Flat", sub: "Population Growth", on: c.growth > 8 },\n        { icon: "⌂", label: c.econ > 650000 ? "Strong" : c.econ > 450000 ? "Typical" : "Lean", sub: "Sector Payroll", on: c.econ > 450000 },',
  replace: 'oppTiles: [\n        { icon: "$", label: (incomeIdx !== undefined) ? (incomeIdx > 25 ? "High" : incomeIdx > 0 ? "Above avg." : "Median") : "", sub: "Affluence", on: (incomeIdx !== undefined) && incomeIdx > 0 },\n        { icon: "↗", label: (c.growth !== undefined) ? (c.growth > 20 ? "Strong" : c.growth > 8 ? "Steady" : "Flat") : "", sub: "Population Growth", on: (c.growth !== undefined) && c.growth > 8 },\n        { icon: "⌂", label: (c.econ !== undefined) ? (c.econ > 650000 ? "Strong" : c.econ > 450000 ? "Typical" : "Lean") : "", sub: "Sector Payroll", on: (c.econ !== undefined) && c.econ > 450000 },',
  count: 1
};

/** A21.2i–A21.2l (Task B10, D-C31): the last four readers of a figure that may be absent. The
 *  guards at the derivation are not enough — every place the value is CONSUMED has to say
 *  nothing rather than say "undefined". Hand-editing logic.js for these was tried and reverted:
 *  the design carries them, so the reference and the app stay identical (A-C29's lesson). */
const A21_2i: Amendment = {
  id: 'A21.2i', date: '2026-09-10', ruling: 'an absent pet-household estimate renders nothing, not "undefined" (Task B10, D-C31)',
  find: '{ v: this.fmtMetric("households", c.pets), k: "Est. Pet Households", sub: "derived estimate" }',
  replace: '{ v: (c.pets !== undefined) ? this.fmtMetric("households", c.pets) : undefined, k: "Est. Pet Households", sub: "derived estimate" }',
  count: 1
};

const A21_2j: Amendment = {
  id: 'A21.2j', date: '2026-09-10', ruling: 'no competition figure, no verdict — never "undefined Competition" (Task B10, D-C31)',
  find: 'compLevel: compLevel + " Competition",',
  replace: 'compLevel: (compLevel !== undefined) ? compLevel + " Competition" : undefined,',
  count: 1
};

const A21_2k: Amendment = {
  id: 'A21.2k', date: '2026-09-10', ruling: 'no score, no number in the ring (Task B10, D-C31)',
  find: 'score: String(score),',
  replace: 'score: (score !== undefined) ? String(score) : undefined,',
  count: 1
};

const A21_2l: Amendment = {
  id: 'A21.2l', date: '2026-09-10', ruling: 'no score, no ring — a conic gradient of undefined is a broken circle (Task B10, D-C31)',
  find: 'scoreRing: "width: 46px; height: 46px; border-radius: 999px; display: grid; place-items: center; background: conic-gradient(#4c9a6a " +\n        score + "%, #e6ecf1 0); font-family: var(--rf-display);",',
  replace: 'scoreRing: (score === undefined) ? undefined : "width: 46px; height: 46px; border-radius: 999px; display: grid; place-items: center; background: conic-gradient(#4c9a6a " +\n        score + "%, #e6ecf1 0); font-family: var(--rf-display);",',
  count: 1
};


/** A21.1c / A21.2m–A21.2p / A21.4a–A21.4d / A21.5a–A21.5d (Task B10, D-C31 and D-C32,
 *  2026-09-10) — the docked panel stops fabricating, and the card says which area it describes.
 *
 *  THE ROOT CAUSE the earlier A21.2 entries could not reach. `communities()` coerced every
 *  absent figure to zero (`num()` returns 0 for null, and `parseFloat(...) || 0` did the same for
 *  growth), so every guard that asks `!== undefined` was satisfied by a 0 and the panel rendered
 *  "0" Population, "0.0% (5 yrs)", "$0K" Median Income and a "Flat" growth verdict for a listing
 *  we have no figures for. A21.1c fixes it at the source, which is what makes the guards live.
 *  D-C31: where a figure is absent the UI renders NOTHING — never zero, never "undefined", never
 *  NaN, and never a verdict derived from a missing figure. A bar drawn at minimum height is a
 *  reading, not an absence, so the competition bars, the strip-card bars and the compare bars are
 *  omitted rather than drawn at their floor.
 *
 *  D-C32: a listing with no `place`-band FIGURES falls back to its `drive_10` band, and the card
 *  SAYS SO — `community_label` travels with the row from `app/census/serve.py` and the design
 *  reads it as `p.communityLabel`. Where the label is absent every string is the design's own,
 *  byte for byte, which is what keeps the approved states on their pixels: the design's own
 *  fixtures carry no `communityLabel` key at all. */

/** A21.1c — `communities()` yields `undefined`, not 0, for an absent figure. A21.1 did this for
 *  `econ` and `vets`; the other five expressions kept their coercion. `num()` itself is untouched
 *  — it is read elsewhere — and a figure that IS present keeps exactly the parse it had, so a
 *  fixture practice produces the same numbers it always did. */
const A21_1c: Amendment = {
  id: 'A21.1c', date: '2026-09-10', ruling: 'a missing figure is omitted, never zeroed (D-C31, Task B10)',
  find: '      const hh = num(p.hh);\n      return {\n        id: p.id, name: p.area, lat: p.lat, lng: p.lng,\n        pop: num(p.pop), hh: hh, income: num(p.income),\n        growth: parseFloat(String(p.growth).replace(/[^0-9.\\-]/g, "")) || 0,\n        pets: Math.round(hh * 0.57),',
  replace: '      const hh = p.hh != null ? num(p.hh) : undefined;\n      return {\n        id: p.id, name: p.area, lat: p.lat, lng: p.lng,\n        pop: p.pop != null ? num(p.pop) : undefined, hh: hh, income: p.income != null ? num(p.income) : undefined,\n        growth: p.growth != null ? (parseFloat(String(p.growth).replace(/[^0-9.\\-]/g, "")) || 0) : undefined,\n        pets: hh !== undefined ? Math.round(hh * 0.57) : undefined,',
  count: 1
};

/** A21.2m — no competition figure, no bars. Three bars painted at the floor read as "the lowest
 *  competition there is", which is a reading of data we do not have. */
const A21_2m: Amendment = {
  id: 'A21.2m', date: '2026-09-10', ruling: 'three bars at the floor are a reading, not an absence (D-C31, Task B10)',
  find: '      compBars: [1, 2, 3].map((i) => ({',
  replace: '      compBars: (per10k === undefined) ? [] : [1, 2, 3].map((i) => ({',
  count: 1
};

/** A21.2n — the Market data strip cards take their median over the DEFINED values only. `num(raw)`
 *  turned every absent figure into a 0, so six cards printed `$0K` / `0` / `+0.0%` under the words
 *  "metro median". A metro where nobody has that figure now yields `undefined`, and no bars. */
const A21_2n: Amendment = {
  id: 'A21.2n', date: '2026-09-10', ruling: 'a metro median is the median of what we know, never of zeros we invented (D-C31, Task B10)',
  find: '          const vals = comms.map((c) => {\n            const raw = k === "households" ? c.hh : k === "competition" ? c.vets : c[k];\n            return { raw: num(raw), t: this.bucket(k, num(raw)).t };\n          });\n          const mid = vals.map((v) => v.raw).sort((a, b) => a - b)[Math.floor(vals.length / 2)] || 0;',
  replace: '          const vals = comms.map((c) => (k === "households" ? c.hh : k === "competition" ? c.vets : c[k]))\n            .filter((raw) => raw != null)\n            .map((raw) => ({ raw: num(raw), t: this.bucket(k, num(raw)).t }));\n          const mid = vals.length ? vals.map((v) => v.raw).sort((a, b) => a - b)[Math.floor(vals.length / 2)] : undefined;',
  count: 1
};

/** A21.2o — and the card then keeps its title, source and link and renders no value (controller
 *  ruling on F-6). `bars` needs no guard: `vals` is empty when `mid` is undefined. */
const A21_2o: Amendment = {
  id: 'A21.2o', date: '2026-09-10', ruling: 'a strip card with no figure keeps its title, source and link and shows no value (D-C31, Task B10)',
  find: '            value: this.fmtMetric(k, mid),',
  replace: '            value: (mid !== undefined) ? this.fmtMetric(k, mid) : undefined,',
  count: 1
};

/** A21.2p — the Compare rows: a community with no figure for a layer carries no bar for it. The
 *  two bars were drawn from `num(raw)`, so an absent figure became a minimum-width bar — the same
 *  false reading A21.2m removes from the competition row. One `bar(k)` helper replaces the four
 *  `bucket()` calls and returns the design's own style string byte for byte when the figure is
 *  there, `undefined` when it is not. */
const A21_2p: Amendment = {
  id: 'A21.2p', date: '2026-09-10', ruling: 'a compare row with no figure carries no bar (D-C31, Task B10)',
  find: '        const raw = (k) => (k === "households" ? c.hh : k === "competition" ? c.vets : c[k]);\n        const ta = this.bucket(valueLayer, num(raw(valueLayer))).t;\n        const tb = this.bucket(s.mdCompare, num(raw(s.mdCompare))).t;\n        const fillA = this.bucket(valueLayer, num(raw(valueLayer))).color;\n        const fillB = this.bucket(s.mdCompare, num(raw(s.mdCompare))).color;\n        return {\n          name: c.name,\n          aStyle: "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + ta * 92) + "%; background: " + fillA + ";",\n          bStyle: "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + tb * 92) + "%; background: " + fillB + ";"\n        };',
  replace: '        const raw = (k) => (k === "households" ? c.hh : k === "competition" ? c.vets : c[k]);\n        const bar = (k) => {\n          const v = raw(k);\n          if (v == null) return undefined;\n          const b = this.bucket(k, num(v));\n          return "display: block; height: 7px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14); width: " + Math.round(8 + b.t * 92) + "%; background: " + b.color + ";";\n        };\n        return {\n          name: c.name,\n          aStyle: bar(valueLayer),\n          bStyle: bar(s.mdCompare)\n        };',
  count: 1
};

/** A21.4a — the panel gains the detail's own `hasDemo`/`noDemo` pair, keyed on `p.pop != null`
 *  exactly as A12.10/A12.11 keyed the detail's, plus the Insights heading D-C32 needs. */
const A21_4a: Amendment = {
  id: 'A21.4a', date: '2026-09-10', ruling: 'a listing with no figures reaches the design’s own "Community data unavailable" card on the panel too (D-C31, A-C31 (2))',
  find: '      isInsights: (s.mdTab || "insights") === "insights",',
  replace: '      hasDemo: sel.pop != null,\n      noDemo: sel.pop == null,\n      overviewTitle: sel.communityLabel || "Market Overview (10 min drive)",\n      isInsights: (s.mdTab || "insights") === "insights",',
  count: 1
};

/** A21.4b — the Insights tab body opens the `hasDemo` branch. */
const A21_4b: Amendment = {
  id: 'A21.4b', date: '2026-09-10', ruling: 'a listing with no figures reaches the design’s own "Community data unavailable" card on the panel too (same ruling)',
  find: '              <sc-if value="{{ md.panel.isInsights }}" hint-placeholder-val="{{ true }}">\n                <div style="padding: 16px;">\n',
  replace: '              <sc-if value="{{ md.panel.isInsights }}" hint-placeholder-val="{{ true }}">\n                <div style="padding: 16px;">\n                  <sc-if value="{{ md.panel.hasDemo }}" hint-placeholder-val="{{ true }}">\n',
  count: 1
};

/** A21.4c — …and closes it before the CTA, with the design’s OWN unavailable card between. The
 *  markup is the detail’s, element for element (V3:884-888): no second card is invented. The
 *  "View full listing" button stays outside both branches, because navigation is not data. */
const A21_4c: Amendment = {
  id: 'A21.4c', date: '2026-09-10', ruling: 'a listing with no figures reaches the design’s own "Community data unavailable" card on the panel too (same ruling)',
  find: '\n                  <button onClick="{{ md.panel.openListing }}" style="display: flex; align-items: center; justify-content: center; gap: 9px; width: 100%; height: 44px; margin-top: 16px; font-family: var(--rf-display); font-size: 13.5px; font-weight: 500; color: var(--vf-white); background: var(--vf-accent); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--vf-navy);">',
  replace: '\n                  </sc-if>\n                  <sc-if value="{{ md.panel.noDemo }}" hint-placeholder-val="{{ false }}">\n                    <div style="padding: 22px; background: var(--color-off-white); border: 1px dashed var(--border-subtle); border-radius: 10px;">\n                      <div style="font-size: 14px; font-weight: 500; color: var(--color-navy);">Community data unavailable for this location</div>\n                      <p style="font-size: 13px; line-height: 1.6; color: #494949; margin: 6px 0 0; max-width: 60ch;">The Census geography for this address has not been matched yet. Everything else on this listing is seller-provided and unaffected.</p>\n                    </div>\n                  </sc-if>\n                  <button onClick="{{ md.panel.openListing }}" style="display: flex; align-items: center; justify-content: center; gap: 9px; width: 100%; height: 44px; margin-top: 16px; font-family: var(--rf-display); font-size: 13.5px; font-weight: 500; color: var(--vf-white); background: var(--vf-accent); border: 0; border-radius: 6px; cursor: pointer;" style-hover="background: var(--vf-navy);">',
  count: 1
};

/** A21.4d — the footnote describes figures, so it goes with them. */
const A21_4d: Amendment = {
  id: 'A21.4d', date: '2026-09-10', ruling: 'a listing with no figures reaches the design’s own "Community data unavailable" card on the panel too (same ruling)',
  find: '                  <p style="font-size: 10.5px; line-height: 1.55; color: var(--vf-text); margin: 10px 0 0;">Drive-time figures are approximated from a straight-line catchment around the practice. Pet-household counts are derived from ACS households, not measured. Score weights income, growth and competition; the formula ships in the data specification.</p>',
  replace: '                  <sc-if value="{{ md.panel.hasDemo }}" hint-placeholder-val="{{ true }}">\n                    <p style="font-size: 10.5px; line-height: 1.55; color: var(--vf-text); margin: 10px 0 0;">Drive-time figures are approximated from a straight-line catchment around the practice. Pet-household counts are derived from ACS households, not measured. Score weights income, growth and competition; the formula ships in the data specification.</p>\n                  </sc-if>',
  count: 1
};

/** A21.5a — the panel’s Insights heading names the area its figures describe. With no label it
 *  is the design’s own "Market Overview (10 min drive)", byte for byte. */
const A21_5a: Amendment = {
  id: 'A21.5a', date: '2026-09-10', ruling: 'a buyer is never shown a drive-time area disguised as a named city (D-C32)',
  find: '<div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);">Market Overview (10 min drive)</div>',
  replace: '<div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);">{{ md.panel.overviewTitle }}</div>',
  count: 1
};

/** A21.5b — the detail’s Community Context card: the attribution sentence and the Population
 *  tile’s sub-line both name the area. `demoScope` lower-cases the label’s first letter so the
 *  sentence reads "Figures describe the area within 10 minutes of the practice, not the practice
 *  itself."; with no label it is the design’s own sentence, byte for byte. */
const A21_5b: Amendment = {
  id: 'A21.5b', date: '2026-09-10', ruling: 'a buyer is never shown a drive-time area disguised as a named city (same ruling)',
  find: '      demo: [\n        { k: "Population", v: p.pop, sub: "Community, 2023" },',
  replace: '      demoScope: "Figures describe " + (p.communityLabel ? "the area " + p.communityLabel.charAt(0).toLowerCase() + p.communityLabel.slice(1) : "the community around the practice") + ", not the practice itself.",\n      demo: [\n        { k: "Population", v: p.pop, sub: p.communityLabel || "Community, 2023" },',
  count: 1
};

/** A21.5c — …and the Households tile’s sub-line, the other one that says "the community".
 *
 *  CHAINED, like A21.3d on A12.6: the `find` is A12.7's whole `replace`, not the pristine row, so
 *  it does not occur in the pristine bundle at all. It has to be: A12.7 already rewrote this row
 *  (`p.hh.replace(…)` → `(p.hh || "").replace(…)`), and a `find` that took only the `sub:` clause
 *  would leave A12.7's own output unreachable from `LOCAL_AMENDMENTS.md`'s V3-line check, which
 *  follows the chain by asking which later `find` swallowed an amendment's `replace` WHOLE. */
const A21_5c: Amendment = {
  id: 'A21.5c', date: '2026-09-10', ruling: 'a buyer is never shown a drive-time area disguised as a named city (same ruling)',
  find: '{ k: "Households", v: (p.hh || "").replace(" households", ""), sub: "In the community" }',
  replace: '{ k: "Households", v: (p.hh || "").replace(" households", ""), sub: p.communityLabel || "In the community" }',
  count: 1
};

/** A21.5d — the attribution paragraph reads `demoScope`. The Census attribution itself is legally
 *  load-bearing and is untouched: only the trailing sentence, which describes the AREA, moves into
 *  the data. */
const A21_5d: Amendment = {
  id: 'A21.5d', date: '2026-09-10', ruling: 'a buyer is never shown a drive-time area disguised as a named city (same ruling)',
  find: 'attribution requested). Figures describe the community around the practice, not the practice itself.</p>',
  replace: 'attribution requested). {{ d.demoScope }}</p>',
  count: 1
};


/** A22 (John, 2026-09-10 — Task SL10: "Preserve existing seed wording/detail"): the wizard's
 *  ownership select widens from four options (the design's four) to ten, adding the seeds' own six
 *  phrasings alongside the design's four. The API's `OWNERSHIPS` tuple and the design's option
 *  array are identical and pinned two-way by pytest (step 1 of the task's own test cases). */
/** A21.2f (Task B10, D-C31): compPer10k guards the .toFixed() call.
 *  When per10k is undefined, compPer10k must be undefined, not throw. */
const A21_2f: Amendment = {
  id: 'A21.2f', date: '2026-09-10', ruling: 'compPer10k renders the ratio or undefined, never throws (Task B10, D-C31)',
  find: '      compPer10k: per10k.toFixed(1),',
  replace: '      compPer10k: (per10k !== undefined) ? per10k.toFixed(1) : undefined,',
  count: 1
};

/** A21.2g (Task B10, D-C31): score and scoreLabel are omitted when inputs are missing.
 *  A composite of unknowns is not a low score; it is not a score. */
const A21_2g: Amendment = {
  id: 'A21.2g', date: '2026-09-10', ruling: 'a composite of unknowns is not a low score; it is not a score (Task B10, D-C31)',
  find: 'const score = Math.max(0, Math.min(100, Math.round(\n      40 * Math.min(c.income / 140000, 1) + 35 * Math.min(c.growth / 40, 1) + 25 * Math.max(0, 1 - per10k / 3)\n    )));',
  replace: 'const score = (c.income === undefined || c.growth === undefined || per10k === undefined) ? undefined : Math.max(0, Math.min(100, Math.round(\n      40 * Math.min(c.income / 140000, 1) + 35 * Math.min(c.growth / 40, 1) + 25 * Math.max(0, 1 - per10k / 3)\n    )));',
  count: 1
};

/** A21.2h (Task B10, D-C31): scoreLabel renders only when score is defined. */
const A21_2h: Amendment = {
  id: 'A21.2h', date: '2026-09-10', ruling: 'no score, no label — the ring says nothing rather than "Challenging" (Task B10, D-C31)',
  find: 'scoreLabel: score >= 75 ? "Attractive" : score >= 55 ? "Balanced" : "Challenging",',
  replace: 'scoreLabel: score === undefined ? undefined : score >= 75 ? "Attractive" : score >= 55 ? "Balanced" : "Challenging",',
  count: 1
};

const A22: Amendment = {
  id: 'A22', date: '2026-09-10',
  ruling: 'Preserve existing seed wording/detail — widen the ownership dropdown to carry the seeds\' six phrasings beside the design\'s four (Task SL10)',
  find: 'sel("ownership", "Current ownership", ["Sole proprietor", "Two-doctor partnership", "Multi-doctor LLC", "Other"])',
  replace: 'sel("ownership", "Current ownership", ["Sole proprietor", "Sole proprietor (LLC)", "Sole proprietor (S-corp)", "Two-doctor partnership", "Three-doctor LLC", "Four-doctor partnership", "Four-doctor LLC", "Five-doctor LLC", "Multi-doctor LLC", "Other"])',
  count: 1
};

/** A23 (John, 2026-09-10 — Task MD1: "the collapse widget top left expand/collapse is disconnected to the drop down"):
 *  collapsing the Market data card leaves its LAYER dropdown floating over the map with no card above it.
 *  Exactly one of the card's two menus escapes the collapse, and it is the one John reported: the layer
 *  menu's panel (`frontend/src/App.vue:475-476`) is `position: absolute; left: 16px; top: 118px;
 *  z-index: 620` and sits OUTSIDE both of the card's `v-if="v.md?.legendOpen"` templates (`:382-410` and
 *  `:413-472`, the card div closing at `:411`), so nothing unmounts it. The comparison listbox never
 *  floated: its panel (`:434-435`) is nested inside the second `legendOpen` template in normal flow
 *  (`margin-top: 6px`) and has always unmounted with the card. `toggleLegend` clears `mdCompareMenu` all
 *  the same, for a weaker and different reason — a menu left open in state reappears already-open when
 *  the card is expanded again, which is its own surprise — not because it escapes the card's region.
 *  The clear is UNCONDITIONAL: the one `setState` runs on expand exactly as on collapse, so neither menu
 *  can come back open in either direction (the four-quadrant characterisation in `logic.test.ts` pins
 *  both). The fix mirrors the design's own idiom where `insightOpen` gates the "What this means" panel on
 *  `s.mdLegendOff !== true`, which is why that panel behaves correctly. */
const A23: Amendment = {
  id: 'A23', date: '2026-09-10', ruling: 'collapsing or expanding the Market data card closes both its menus (Task MD1)',
  find: 'toggleLegend: () => this.setState({ mdLegendOff: s.mdLegendOff !== true }),',
  replace: 'toggleLegend: () => this.setState({ mdLegendOff: s.mdLegendOff !== true, mdLayerMenu: false, mdCompareMenu: false }),',
  count: 1
};

/* ------------------------------------------------------------------------------------------
 * A25 — Task MP1 (John's ruling, 2026-09-10): "a listing with no coordinates keeps its place in
 * the results and does not get a pin."
 *
 * `app/api/listings.py`'s `serialise` emits `lat`/`lng` as null whenever `location_disclosed`
 * is false, and `migrations/016_listing.sql` declares that column `NOT NULL DEFAULT false` — so
 * the nulls are the DEFAULT, not an edge case. `load.ts` carries them through unchanged (its own
 * `centroid()` already filters unlocated practices, which is the codebase saying it knows they
 * exist), and the design handed them straight to Leaflet.
 *
 * Leaflet 1.9.4's `toLatLng([null, null])` returns `null`: the array branch is gated on
 * `typeof a[0] !== 'object'` and `typeof null === 'object'`, so it falls through. `Marker._latlng`
 * is then null and `_setPos(map.latLngToLayerPoint(null))` reads `.lat` off it — measured in real
 * Chromium as `pageerror: Cannot read properties of null (reading 'lat')`, no pins. ONE listing
 * was enough: `drawPins`' `forEach` has no try/catch, so pin drawing stopped there for every
 * later listing, and `LayerGroup.addLayer` had already stored the marker before `map.addLayer`
 * threw, so the poisoned layer re-threw from inside Leaflet's own event loop on every later zoom
 * pass. Under the Vite dev server Vue's `logError` re-throws out of `flushJobs` and the screen
 * stops responding; the production build logs instead, so QA and production lose the pins from
 * that listing onward and break zoom.
 *
 * The listing itself is real — a buyer may open it, request access and read it — and the missing
 * point is the seller's own choice, so it stays in the rail, the count, the sort and the filters
 * and only the MAP skips it. Nothing is drawn at [0, 0] and nothing at the metro centre: the
 * design has no treatment for "somewhere in this metro" and inventing one is out of scope.
 * ------------------------------------------------------------------------------------------ */

/** A25.1 — the pin list. `Number.isFinite` rather than `!= null` because `NaN` reaches
 *  `toLatLng` intact and produces the same broken marker one step further on. */
const A25_1: Amendment = {
  id: 'A25.1', date: '2026-09-10', ruling: 'a listing with no coordinates keeps its place in the results and does not get a pin (Task MP1)',
  find: '      practices: list.map((p) => ({',
  replace: '      practices: list.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng)).map((p) => ({',
  count: 1
};

/** A25.2 — the second leg into the same trap: the drive-time ring's centre. `MarketMapView`
 *  guards on `props.driveCenter` being truthy, and `[null, null]` is an array, so it passed —
 *  `engine.ring([null, null], …)` is `L.circle`, which calls the same `toLatLng`. The fallback
 *  is the expression's OWN else-branch (the metro centre); no new centre is invented. */
const A25_2: Amendment = {
  id: 'A25.2', date: '2026-09-10', ruling: 'a listing with no coordinates keeps its place in the results and does not get a pin (Task MP1)',
  find: '      driveCenter: sel ? [sel.lat, sel.lng] : cfg.center,',
  replace: '      driveCenter: (sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng)) ? [sel.lat, sel.lng] : cfg.center,',
  count: 1
};

/** A25.3 — the third leg, and the worst of them. The map's community list is what
 *  `mosaicBbox` takes `Math.min`/`Math.max` over, and `null` coerces to 0: measured on the real
 *  producer, one unlocated Austin community stretched the metro box from [29.86, -98.24] to
 *  [-0.13, 0.15], which is 100,482,513 mosaic cells to iterate — a hung tab, not a missing
 *  shape. A community with no centroid cannot be shaded, so it leaves the MAP's list.
 *
 *  Only the map's list. `comms` itself is untouched, so the Market data strip cards still take
 *  their metro medians over the listing's figures and the docked panel still reads its own
 *  community: a figure is not a point, and A21.2n's rule (median of what we know) is unchanged. */
const A25_3: Amendment = {
  id: 'A25.3', date: '2026-09-10', ruling: 'a listing with no coordinates keeps its place in the results and does not get a pin (Task MP1)',
  find: '      communities: comms.map((c) => {',
  replace: '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {',
  count: 1
};

/** A25.4 — the last place in the docked panel where a zero stood in for an absence, and the one
 *  A21.1c/A21.2* could not reach: `marketPanel`'s last-resort community object, taken when the
 *  selection has no community of its own AND the market has no communities at all. Measured on
 *  the real producer it rendered "0" Population, "0.0% (5 yrs)", "$0K" Median Income, "0"
 *  Veterinary Establishments and a "Flat" growth verdict — exactly the fabrication D-C31 rules
 *  out. The arm is KEPT rather than removed (it is the guard that stops the panel throwing on an
 *  empty market) and its values become `undefined`, which every A21 guard downstream already
 *  reads as "we have no figure". */
const A25_4: Amendment = {
  id: 'A25.4', date: '2026-09-10', ruling: 'a missing figure is omitted, never zeroed — the panel’s last-resort community too (D-C31, Task MP1)',
  find: '    const c = selComm || comms[0] || { pop: 0, hh: 0, income: 0, growth: 0, pets: 0, vets: 0 };',
  replace: '    const c = selComm || comms[0] || { pop: undefined, hh: undefined, income: undefined, growth: undefined, pets: undefined, vets: undefined };',
  count: 1
};

/** A25.5 — the panel and the detail disagreed about p8. The detail reads
 *  `p.id !== "p8" && p.pop != null` (the design's own first term, which A12.10 widened); A21.4a
 *  ported the idiom to the panel and dropped that first term, so the DESIGN's own fixture for
 *  "Community data unavailable" showed a full profile in the docked panel and the unavailable
 *  card on the detail behind it.
 *
 *  The p8 term is what is kept, on both, rather than dropped from both: p8 carries `pop`,
 *  `growth`, `income` and `hh` in the fixture, so the id test is the DESIGN's deliberate way of
 *  demonstrating the unavailable state, and removing it would delete that demonstration. It can
 *  only ever be true of a design fixture — a real listing's id is a uuid — so nothing the API
 *  serves is affected either way.
 *
 *  Applied after A21.4a, whose output is this `find`. No approved state opens the panel on p8
 *  (`browse-market-panel` and `interest-modal` use Cedar Park and Round Rock), so no pixel moves. */
const A25_5: Amendment = {
  id: 'A25.5', date: '2026-09-10', ruling: 'the docked panel and the detail must not disagree about whether a listing has community data (Task MP1)',
  find: '      hasDemo: sel.pop != null,\n      noDemo: sel.pop == null,',
  replace: '      hasDemo: sel.id !== "p8" && sel.pop != null,\n      noDemo: sel.id === "p8" || sel.pop == null,',
  count: 1
};

/** A25.6 — fix round 1, Important-1 (controller ruling, 2026-09-10: "no point, no ring"). The
 *  FOURTH leg into the same trap, and the only one that asserts something false rather than
 *  omitting something true.
 *
 *  `showDrive` is `!!sel` with no coordinate term, and `MarketMapView.vue:91` draws the C7
 *  drive-time ring on `showDrive && driveCenter`. Before A25.2, selecting an unlocated listing
 *  reached `engine.ring([null, null], 16000, …)` — `L.circle`, the same `toLatLng` — and threw,
 *  so no ring was ever painted. A25.2 gave the expression its own else-branch back, which made
 *  that branch PAINTABLE for the first time: a 16 km dashed "roughly ten minutes' drive" circle
 *  centred on the middle of Austin, around a place the practice is not.
 *
 *  A missing pin omits; this fabricates. `showDrive` takes the same finite-coordinate test the
 *  pin list uses, and nothing else changes — no substitute copy, no note, no empty state, and a
 *  located listing's ring is untouched (a characterisation case pins both directions). */
const A25_6: Amendment = {
  id: 'A25.6', date: '2026-09-10', ruling: 'no point, no ring — the drive-time ring is not painted around the metro for a listing whose location is withheld (Task MP1, fix round 1)',
  find: '      showDrive: !!sel,',
  replace: '      showDrive: !!(sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng)),',
  count: 1
};

/** A26 — the Browse filter bar's native `<select>`s become dropdowns in this design's own style
 *  (John, 2026-09-11: "the dropdown 'more filters' is correct implementation while everything
 *  else on the filter bar is implemented incorrectly and not using the site design, this must be
 *  corrected").
 *
 *  This is the SECOND report about this toolbar row. On 2026-09-08 he made the identical
 *  complaint about the metro picker sitting immediately to the left of these five, and it was
 *  fixed as A13; A13's scope note left "the five filter selects" native, and that clause is what
 *  he has now overruled. So A26 reuses A13's idiom verbatim rather than authoring a second one:
 *  a trigger plus a `role="listbox"` panel composed from the Market data card's layer menu,
 *  anchored with the "More filters" popover's own `top: 46px; z-index: 700` and
 *  `box-shadow: 0 6px 20px rgba(0,58,112,.16)`, rows carrying the generated hover class the
 *  layer-menu and compare-menu rows already get. Every declaration is one the pristine bundle
 *  already carries — asserted, declaration by declaration, in `design-amendments.test.ts`.
 *
 *  A `<select>`'s popup is drawn by the OPERATING SYSTEM, not by the page: on macOS Chromium it
 *  is the dark menu in his screenshots, it ignores every declaration in `fl.style`, and it renders
 *  above every in-page `z-index`. No CSS reaches it; only replacing the element does.
 *
 *  The one thing A13 did not have to solve is multiplicity — it converted ONE control. A26's five
 *  (eight, with the three inside the popover Task F2 added) are not eight menus: they are TWO
 *  `.map()` body, so the family is one state slot, one open path, one set of closures and five
 *  instances. `Object.assign` semantics mean writing `fMenu` closes whichever sibling was open,
 *  so the invariant INSIDE the family is structural and there is nothing to forget; only the
 *  edges across the family boundary are written by hand, and they are named in A26.4/A26.8/A26.9.
 *
 *  Two keys, both minted by their first `setState` exactly as `marketMenu`/`marketMenuAt`,
 *  `giveMenu`, `navMenu`, `userMenu`, `moreFilters`, `mdLayerMenu` and `mdCompareMenu` are —
 *  none of those is in the state literal either: `fMenu` (null, or the open dropdown's own filter
 *  key) and `fMenuAt` (a rendered highlight in A13's shape, guarded BY THE KEY so a stale index
 *  can never paint on a sibling). It is not shared with `giveMenuAt`, which is an unrendered
 *  one-shot focus token with a `null` sentinel; sharing the slot was measured to drop a mouse
 *  user on "Dr. Sophia Yin Memorial Fund", the exact defect the comment at V3's `givePanelRef`
 *  says that `null` exists to prevent.
 *
 *  Task F1 converts the five on the toolbar (A26.10). The three inside the "More filters"
 *  popover were converted by Task F2, so the family's two `.map()` bodies are both done.
 */
const A26 = {
  date: '2026-09-11',
  ruling: 'the dropdown "more filters" is correct implementation while everything else on the filter bar is implemented incorrectly and not using the site design, this must be corrected'
};

/** A26.1 — four class members beside `setMarket`, so the five instances share one implementation
 *  of everything that is not per-instance. Anchored on `moveMarketHighlight`, A13.1's own last
 *  member, which is where the metro dropdown's machinery already lives.
 *
 *  `openFilterMenu` is the family's ONE open path, and the only place it names the four overlay
 *  menus John's m7 ruling governs — the toggle and the arrow key both call it, so the six
 *  cross-close keys are written once rather than once per instance. `setFilter` is the choice:
 *  it calls the design's OWN `setF` (V3:1907), so the 320 ms loading settle and the filter
 *  transition are byte-for-byte the ones the `<select>`'s `onChange` had, and then shuts the
 *  panel and returns focus the way `setMarket` does. `scrollFilterOption` and
 *  `moveFilterHighlight` are A13.1's two, taking the instance's key as their first argument. */
const A26_1: Amendment = {
  id: 'A26.1', ...A26,
  find: [
    '  moveMarketHighlight = (i) => {',
    '    this.setState({ marketMenuAt: i });',
    '    this.scrollMarketOption(i);',
    '  };',
    ''
  ].join('\n'),
  replace: [
    '  moveMarketHighlight = (i) => {',
    '    this.setState({ marketMenuAt: i });',
    '    this.scrollMarketOption(i);',
    '  };',
    '',
    '  // Opening a filter dropdown. ONE open path for the whole family: the trigger and the arrow',
    '  // keys both come here, so the cross-menu invariant (final review m7) is written once rather',
    '  // than once per instance. Writing `fMenu` is what closes whichever sibling was open —',
    '  // Object.assign semantics — so inside the family there is nothing to forget; the four keys',
    '  // below are the only edges that leave it.',
    '  openFilterMenu = (key, at) => {',
    '    this.setState({ fMenu: key, fMenuAt: at, navMenu: false, userMenu: false, giveMenu: false, marketMenu: false, marketMenuAt: -1 });',
    '  };',
    '',
    '  // The filter choice. It calls the design\'s own setF, so the state transition and the 320 ms',
    '  // loading settle are the ones the <select>\'s onChange had, to the byte.',
    '  setFilter = (key, v) => {',
    '    this.setF(key)(v);',
    '    this.setState({ fMenu: null, fMenuAt: -1 });',
    '    // The choice unmounts the row the pointer or the keyboard was on, so focus would land on',
    '    // <body>. A native select leaves the user on the control; so does this one.',
    '    const host = this._fMenuEls && this._fMenuEls[key];',
    '    const trigger = host && host.querySelector(\'button[aria-haspopup="listbox"]\');',
    '    if (trigger) trigger.focus();',
    '  };',
    '',
    '  // Bringing a row into view, scoped to the dropdown that owns it. Both the arrow keys and the',
    '  // panel\'s own mount need this: one while the rows are already there, one at the moment they',
    '  // arrive. The row is resolved through the field this component recorded, not across the',
    '  // document — the ids are ones this component mints, as scrollMarketOption\'s are.',
    '  scrollFilterOption = (key, i) => {',
    '    const host = this._fMenuEls && this._fMenuEls[key];',
    '    const row = host && host.querySelector("#f-opt-" + key + "-" + i);',
    '    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });',
    '  };',
    '',
    '  // Moving the keyboard highlight. The rows are all in the DOM while the panel is open, so the',
    '  // one being highlighted is scrolled into view here rather than after a re-render.',
    '  moveFilterHighlight = (key, i) => {',
    '    this.setState({ fMenuAt: i });',
    '    this.scrollFilterOption(key, i);',
    '  };',
    ''
  ].join('\n'),
  count: 1
};

/** A26.2 — the `filters:` map body. The five ARRAY LITERALS above it are untouched: the keys, the
 *  option values and every one of the design's own labels are exactly as approved. Only the
 *  `.map()` that turns each into render values changes, key for key on A13.2's metro menu —
 *  `open` <-> `marketMenuOpen`, `toggle` <-> `toggleMarketMenu`, `caretStyle` <->
 *  `marketCaretStyle`, `triggerLabel` <-> `marketTriggerLabel`, `hostRef` <-> `marketMenuRef`,
 *  `panelRef` <-> `marketPanelRef`, `keys` <-> `marketMenuKeys`, and `rowStyle`/`tickStyle`
 *  verbatim.
 *
 *  `style` is the `<select>`'s own string with three declarations prefixed — `display:
 *  inline-flex; align-items: center; gap: 8px;`, which the "More filters" button in the same row
 *  already carries — because a `<button>` has to lay out a label and a chevron where the
 *  `<select>` had the user agent draw its own arrow. Nothing else about the closed box changes.
 *
 *  `aria` is derived from the design's OWN first option (all five read "<name>: Any") rather than
 *  authoring five new strings. It is required, not cosmetic: today these five have no `<label>`
 *  and no `aria-label`, and a `<label>` cannot name a `<button>` anyway; and `screens.ts`'s
 *  `layerTrigger` addresses the Market data card's two listbox triggers as the UNLABELLED ones,
 *  so an unlabelled trigger here would break `browse-layer-menu` and `browse-compare-open`.
 *
 *  The `<select>`'s two orphaned render keys go with it under the bundle's own dead-code rule,
 *  exactly as A13.6/A13.7 dropped `market:` and `v: m`: `value:` fed `value="{{ fl.value }}"`
 *  and `v:` fed `<option value="{{ o.v }}">`, and after A26.10 the template holds neither. Both
 *  choices go through `setFilter(fl.key, …)`, which closes over the value itself. `set:` goes the
 *  same way — `onChange="{{ fl.set }}"` was its only reader — while `setF` itself, and its
 *  event-or-value line, are untouched and still what `setFilter` calls. */
const A26_2: Amendment = {
  id: 'A26.2', ...A26,
  find: [
    '      ].map((fl) => ({',
    '        value: s.f[fl.key],',
    '        set: this.setF(fl.key),',
    '        options: fl.options.map((o) => ({ v: o[0], label: o[1] })),',
    '        style: "height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: " +',
    '          (s.f[fl.key] === "Any" ? "var(--color-white)" : "var(--rf-band)") + "; border: 1px solid " +',
    '          (s.f[fl.key] === "Any" ? "var(--border-subtle)" : "var(--color-blue)") + "; border-radius: 6px; cursor: pointer;"',
    '      })),',
    ''
  ].join('\n'),
  replace: [
    '      ].map((fl) => {',
    '        // Each toolbar filter is a dropdown list in this design\'s own style, not the operating',
    '        // system\'s popup: the same trigger + role="listbox" panel A13 gave the metro control',
    '        // beside it. One .map() body, five instances, one state slot.',
    '        //',
    '        // The comment sits INSIDE the map body, not between the array rows and `].map(`:',
    '        // `tests/seeds/test_hospitals_json.py`\'s `_BAR_BLOCK` reads the five option arrays',
    '        // out of the design and requires `      ]` to follow the last row directly, and it',
    '        // fails loudly rather than silently testing nothing when it does not.',
    '        const cur = s.f[fl.key];',
    '        const open = s.fMenu === fl.key;',
    '        // Math.max: a value `f` holds that this option list does not would give indexOf -1 and',
    '        // index the array out of bounds — the guard marketMenuKeys carries for a dropped metro.',
    '        const sel = Math.max(0, fl.options.findIndex((o) => o[0] === cur));',
    '        const at = open && s.fMenuAt >= 0 ? s.fMenuAt : sel;',
    '        return {',
    '          // The accessible name, taken from the design\'s OWN first option — all five read',
    '          // "<name>: Any" — rather than authoring five new strings. A <select> with no <label>',
    '          // is named by nothing, and a <label> cannot name a <button>, so the trigger needs one.',
    '          aria: fl.options[0][1].split(":")[0],',
    '          open,',
    '          listId: "f-listbox-" + fl.key,',
    '          // On the TRIGGER, which is always rendered: a shut dropdown has no active descendant,',
    '          // and null is what both renderers omit the attribute for (a string would spell a dead',
    '          // id). Keyed on fl.key as well, so a sibling never claims another\'s highlight.',
    '          activeId: open ? "f-opt-" + fl.key + "-" + s.fMenuAt : null,',
    '          // What the closed <select> displayed: the current option\'s own label.',
    '          triggerLabel: fl.options[sel][1],',
    '          toggle: () => (open ? this.setState({ fMenu: null, fMenuAt: -1 }) : this.openFilterMenu(fl.key, sel)),',
    '          hostRef: (el) => { const m = this._fMenuEls || (this._fMenuEls = {}); m[fl.key] = el || null; },',
    '          // The panel\'s own mount is when the option rows first exist, so it is where OPENING',
    '          // scrolls the highlighted row into view — the arrow keys cannot, having seeded the',
    '          // highlight while the panel was still unrendered. Same callback-ref idiom the compare',
    '          // menu ships (md.compareMenuRef) and A13 reuses for marketPanelRef.',
    '          panelRef: (el) => { if (el) this.scrollFilterOption(fl.key, this.state.fMenuAt); },',
    '          keys: (e) => {',
    '            const n = fl.options.length;',
    '            if (e.key === "ArrowDown" || e.key === "ArrowUp") {',
    '              e.preventDefault();',
    '              if (!open) return this.openFilterMenu(fl.key, sel);',
    '              return this.moveFilterHighlight(fl.key, (at + (e.key === "ArrowDown" ? 1 : n - 1)) % n);',
    '            }',
    '            if (!open) return;',
    '            if (e.key === "Home" || e.key === "End") {',
    '              e.preventDefault();',
    '              return this.moveFilterHighlight(fl.key, e.key === "Home" ? 0 : n - 1);',
    '            }',
    '            if (e.key === "Enter" || e.key === " ") {',
    '              e.preventDefault();',
    '              return this.setFilter(fl.key, fl.options[at][0]);',
    '            }',
    '          },',
    '          // The <select>\'s own box, byte for byte, plus the three declarations a label and a',
    '          // chevron need where the user agent used to draw its own arrow (V3:382\'s own trio).',
    '          style: "display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 13px; font-size: 13px; font-weight: 500; color: var(--color-navy); background: " +',
    '            (cur === "Any" ? "var(--color-white)" : "var(--rf-band)") + "; border: 1px solid " +',
    '            (cur === "Any" ? "var(--border-subtle)" : "var(--color-blue)") + "; border-radius: 6px; cursor: pointer;",',
    '          caretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +',
    '            (open ? "180deg" : "0deg") + ");",',
    '          options: fl.options.map((o, i) => {',
    '            const on = o[0] === cur;',
    '            const hi = open && s.fMenuAt === i;',
    '            return {',
    '              label: o[1], selected: on,',
    '              go: () => this.setFilter(fl.key, o[0]),',
    '              optId: "f-opt-" + fl.key + "-" + i,',
    '              rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +',
    '                (on ? "800" : "500") + "; color: var(--vf-navy); background: " +',
    '                (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",',
    '              tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +',
    '                (on ? "1" : "0") + ";"',
    '            };',
    '          })',
    '        };',
    '      }),',
    ''
  ].join('\n'),
  count: 1
};

/** A26.3 — the `moreFilters:` map body, Task F2. The three ARRAY LITERALS above it are untouched:
 *  the keys, the option values and every one of the design's own labels are exactly as approved.
 *
 *  John called "More filters" the CORRECT implementation, so his words do not reach the three
 *  under it — the user's experience does. A `<select>`'s popup is an OPERATING SYSTEM window and
 *  renders above this popover's own `z-index: 700`, so converting only the toolbar five would
 *  have put the dark menu he photographed on top of his own exemplar, one click deeper, rather
 *  than removed it. They are also the cheapest three in the tree: no approved state had ever
 *  clicked "More filters", so no committed pixel moves — and that missing oracle is itself the
 *  gap this task closes (`browse-more-filters`, `browse-more-filters-menu`).
 *
 *  Key for key on A26.2, because it IS A26.2's loop with three instances instead of five: one
 *  state slot, one open path, one set of closures, no new machinery. The eight filter keys are
 *  disjoint (`est`/`ownership`/`sqft` against `type`/`price`/`revenue`/`doctors`/`building`), so
 *  `fMenu` still names exactly one dropdown across BOTH loops and the invariant stays structural.
 *
 *  Two things differ, and both are the design's own. `label:` stays — it is the caption the
 *  popover renders above the field — and it also NAMES the trigger, because a `<label>` does not
 *  name a `<button>` (a button takes its accessible name from its own contents before the host
 *  language's label), so the string is spelled again as an `aria-label` rather than an `aria:`
 *  key being invented as A26.2 had to. And `cur` keeps the `|| "Any"` guard the `<select>`'s
 *  `value:` carried and the toolbar's does not: the design's state literal seeds the five toolbar
 *  keys and none of these three, so `s.f.est` is undefined on first render and the trigger would
 *  otherwise open on a blank box.
 *
 *  The `<select>`'s three orphaned render keys go with it under the bundle's own dead-code rule,
 *  exactly as A13.6/A13.7 and A26.2 dropped theirs: `value:` fed `value="{{ mf.value }}"`, `set:`
 *  fed `onChange="{{ mf.set }}"`, and the rows' `v:` fed `<option value="{{ o.v }}">`. After
 *  A26.11 the template holds none of the three. `setF` itself is untouched and is still what
 *  `setFilter` calls. */
const A26_3: Amendment = {
  id: 'A26.3', ...A26,
  find: [
    '      ].map((fl) => ({',
    '        label: fl.label,',
    '        value: s.f[fl.key] || "Any",',
    '        set: this.setF(fl.key),',
    '        options: fl.options.map((o) => ({ v: o[0], label: o[1] }))',
    '      })),',
    ''
  ].join('\n'),
  replace: [
    '      ].map((fl) => {',
    '        // Each additional filter is a dropdown list in this design\'s own style, not the',
    '        // operating system\'s popup: the SAME trigger + role="listbox" panel A26.2 gives the',
    '        // five on the toolbar, and the same state slot — the eight filter keys are disjoint,',
    '        // so `fMenu` still names exactly one dropdown across both loops.',
    '        //',
    '        // The comment sits INSIDE the map body, not between the array rows and `].map(`:',
    '        // `tests/seeds/test_hospitals_json.py`\'s `_MORE_BLOCK` reads the three option arrays',
    '        // out of the design and requires `      ]` to follow the last row directly, and it',
    '        // fails loudly rather than silently testing nothing when it does not. A26.2 learned',
    '        // that on its sibling `_BAR_BLOCK`.',
    '        const cur = s.f[fl.key] || "Any";',
    '        const open = s.fMenu === fl.key;',
    '        // Math.max: a value `f` holds that this option list does not would give indexOf -1 and',
    '        // index the array out of bounds — the guard marketMenuKeys carries for a dropped metro.',
    '        const sel = Math.max(0, fl.options.findIndex((o) => o[0] === cur));',
    '        const at = open && s.fMenuAt >= 0 ? s.fMenuAt : sel;',
    '        return {',
    '          // The popover\'s own caption, unchanged — and it is the trigger\'s accessible name',
    '          // too: a <label> does not name a <button>, which takes its name from its own',
    '          // contents first, so the same string is spelled again rather than a new one invented.',
    '          label: fl.label,',
    '          open,',
    '          listId: "f-listbox-" + fl.key,',
    '          // On the TRIGGER, which is always rendered: a shut dropdown has no active descendant,',
    '          // and null is what both renderers omit the attribute for (a string would spell a dead',
    '          // id). Keyed on fl.key as well, so a sibling never claims another\'s highlight.',
    '          activeId: open ? "f-opt-" + fl.key + "-" + s.fMenuAt : null,',
    '          // What the closed <select> displayed. `cur` keeps the design\'s own `|| "Any"` guard:',
    '          // the state literal seeds the five TOOLBAR keys and none of these three.',
    '          triggerLabel: fl.options[sel][1],',
    '          toggle: () => (open ? this.setState({ fMenu: null, fMenuAt: -1 }) : this.openFilterMenu(fl.key, sel)),',
    '          hostRef: (el) => { const m = this._fMenuEls || (this._fMenuEls = {}); m[fl.key] = el || null; },',
    '          // The panel\'s own mount is when the option rows first exist, so it is where OPENING',
    '          // scrolls the highlighted row into view — the arrow keys cannot, having seeded the',
    '          // highlight while the panel was still unrendered (A13/A14 review round 1, C1).',
    '          panelRef: (el) => { if (el) this.scrollFilterOption(fl.key, this.state.fMenuAt); },',
    '          keys: (e) => {',
    '            const n = fl.options.length;',
    '            if (e.key === "ArrowDown" || e.key === "ArrowUp") {',
    '              e.preventDefault();',
    '              if (!open) return this.openFilterMenu(fl.key, sel);',
    '              return this.moveFilterHighlight(fl.key, (at + (e.key === "ArrowDown" ? 1 : n - 1)) % n);',
    '            }',
    '            if (!open) return;',
    '            if (e.key === "Home" || e.key === "End") {',
    '              e.preventDefault();',
    '              return this.moveFilterHighlight(fl.key, e.key === "Home" ? 0 : n - 1);',
    '            }',
    '            if (e.key === "Enter" || e.key === " ") {',
    '              e.preventDefault();',
    '              return this.setFilter(fl.key, fl.options[at][0]);',
    '            }',
    '          },',
    '          caretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +',
    '            (open ? "180deg" : "0deg") + ");",',
    '          options: fl.options.map((o, i) => {',
    '            const on = o[0] === cur;',
    '            const hi = open && s.fMenuAt === i;',
    '            return {',
    '              label: o[1], selected: on,',
    '              go: () => this.setFilter(fl.key, o[0]),',
    '              optId: "f-opt-" + fl.key + "-" + i,',
    '              rowStyle: "display: flex; align-items: center; gap: 9px; width: 100%; padding: 8px 8px; font-family: var(--rf-display); font-size: 13px; font-weight: " +',
    '                (on ? "800" : "500") + "; color: var(--vf-navy); background: " +',
    '                (on ? "var(--vf-accent-bg)" : hi ? "var(--vf-neutral)" : "none") + "; border: 0; border-radius: 6px; cursor: pointer;",',
    '              tickStyle: "flex: none; display: block; filter: brightness(0) saturate(100%) invert(23%) sepia(89%) saturate(1352%) hue-rotate(184deg) brightness(94%) contrast(101%); opacity: " +',
    '                (on ? "1" : "0") + ";"',
    '            };',
    '          })',
    '        };',
    '      }),',
    ''
  ].join('\n'),
  count: 1
};

/** A26.4 — the "More filters" popover is the three inner dropdowns' PARENT, not their peer, so it
 *  is not one of the cross-close edges: opening one of the three inside it must not close it. Its
 *  own toggle instead clears the family's keys unconditionally, which is one edit covering both
 *  needed directions — closing the popover shuts any dropdown inside it, so a child cannot latch
 *  behind an unmounted parent, and opening the popover shuts a toolbar dropdown. (Task F2 adds
 *  the three; the second direction is live from F1, the first from F2.) */
const A26_4: Amendment = {
  id: 'A26.4', ...A26,
  find: '      toggleMore: () => this.setState({ moreFilters: !s.moreFilters }),\n',
  replace: '      toggleMore: () => this.setState({ moreFilters: !s.moreFilters, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

/** A26.5 — outside-click, in `trackMenuDismiss`'s existing shared `pointerdown` closure. No new
 *  listener: A13.4 armed this one and A19 already shares it.
 *
 *  PLACEMENT. The ruling asks for the branch "after the existing ones", and it is placed after
 *  Give's and BEFORE the metro's, because the metro branch's guard is an early `return` — a
 *  branch appended after it would be dead whenever the metro menu is closed, which is almost
 *  always. Both existing branches keep their own bytes, which is the invariant A14.4 established
 *  and `design-amendments.test.ts` pins for each of the five. The host is resolved through the
 *  keyed collection this component records (A14's `_giveItemEls` idiom), never across the
 *  document — A13's deliberate rule (final review m5). */
const A26_5: Amendment = {
  id: 'A26.5', ...A26,
  find: [
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && e.target && give.contains(e.target))) this.setState({ giveMenu: false });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  replace: [
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && e.target && give.contains(e.target))) this.setState({ giveMenu: false });',
    '      }',
    '      if (this.state.fMenu) {',
    '        const fh = this._fMenuEls[this.state.fMenu];',
    '        if (!(fh && e.target && fh.contains(e.target))) this.setState({ fMenu: null, fMenuAt: -1 });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  count: 1
};

/** A26.6 — Escape, in the same function's shared `keydown` closure, in the same position and for
 *  the same reason. No focus return is needed and none is written: the option rows carry
 *  `tabindex="-1"` (A13.3), so focus never leaves the trigger, which is exactly why A13's own
 *  Escape branch does not return focus either where A14's Give branch has to. */
const A26_6: Amendment = {
  id: 'A26.6', ...A26,
  find: [
    '      if (this.state.giveMenu) {',
    '        this.setState({ giveMenu: false });',
    '        if (this._giveButtonEl) this._giveButtonEl.focus();',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  replace: [
    '      if (this.state.giveMenu) {',
    '        this.setState({ giveMenu: false });',
    '        if (this._giveButtonEl) this._giveButtonEl.focus();',
    '      }',
    '      if (this.state.fMenu) this.setState({ fMenu: null, fMenuAt: -1 });',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  count: 1
};

/** A26.7 — Tab out, in the same function's shared `focusout` closure, in the same position. The
 *  window-blur rule above it (a null `relatedTarget` dismisses nothing — A19, A-LB3) is the
 *  closure's own early return and covers this branch unchanged. */
const A26_7: Amendment = {
  id: 'A26.7', ...A26,
  find: [
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && give.contains(to))) this.setState({ giveMenu: false });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  replace: [
    '      if (this.state.giveMenu) {',
    '        const give = this._giveMenuEl;',
    '        if (!(give && give.contains(to))) this.setState({ giveMenu: false });',
    '      }',
    '      if (this.state.fMenu) {',
    '        const fh = this._fMenuEls[this.state.fMenu];',
    '        if (!(fh && fh.contains(to))) this.setState({ fMenu: null, fMenuAt: -1 });',
    '      }',
    '      if (!this.state.marketMenu) return;',
    ''
  ].join('\n'),
  count: 1
};

/** A26.8a–A26.8f — the six inbound cross-close edges. Each existing menu open path gains the
 *  family's two keys, so opening any other menu shuts an open filter dropdown. The four overlay
 *  menus' own OUTBOUND edge is written once, in A26.1's `openFilterMenu`. */
const A26_8a: Amendment = {
  id: 'A26.8a', ...A26,
  find: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false }),\n',
  replace: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

const A26_8b: Amendment = {
  id: 'A26.8b', ...A26,
  find: '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false }),\n',
  replace: '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

const A26_8c: Amendment = {
  id: 'A26.8c', ...A26,
  find: '      toggleGiveMenu: () => this.setState({ giveMenu: !s.giveMenu, giveMenuAt: null, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1 }),\n',
  replace: '      toggleGiveMenu: () => this.setState({ giveMenu: !s.giveMenu, giveMenuAt: null, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

const A26_8d: Amendment = {
  id: 'A26.8d', ...A26,
  find: '        this.setState({ giveMenu: true, giveMenuAt: at, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1 });\n',
  replace: '        this.setState({ giveMenu: true, giveMenuAt: at, navMenu: false, userMenu: false, marketMenu: false, marketMenuAt: -1, fMenu: null, fMenuAt: -1 });\n',
  count: 1
};

const A26_8e: Amendment = {
  id: 'A26.8e', ...A26,
  find: '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false }),\n',
  replace: '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

const A26_8f: Amendment = {
  id: 'A26.8f', ...A26,
  find: '          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur });\n',
  replace: '          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur, fMenu: null, fMenuAt: -1 });\n',
  count: 1
};

/** A26.9 — `go()`'s three arms clear the family's keys, so navigating away cannot leave a panel
 *  latched over the next screen. This matters because the design's existing menu keys DO latch —
 *  `go("detail")` after opening the metro listbox leaves `marketMenu: true` — and A26 declines to
 *  ship a ninth instance of a known defect while also declining to fix the existing ones here
 *  (reported separately as D-F2, which is not authorised by this ruling). */
const A26_9a: Amendment = {
  id: 'A26.9a', ...A26,
  find: '    if (screen !== "gate" && !this.state.auth) return this.setState({ screen: "gate", gate: "signin", userMenu: false });\n',
  replace: '    if (screen !== "gate" && !this.state.auth) return this.setState({ screen: "gate", gate: "signin", userMenu: false, fMenu: null, fMenuAt: -1 });\n',
  count: 1
};

const A26_9b: Amendment = {
  id: 'A26.9b', ...A26,
  find: '    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false, lightbox: null, lightboxFocus: false });\n',
  replace: '    if (!this.props.listings || this.state.sellerView !== "wizard" || !this.state.editingId) return this.setState({ screen, interest: "closed", userMenu: false, lightbox: null, lightboxFocus: false, fMenu: null, fMenuAt: -1 });\n',
  count: 1
};

const A26_9c: Amendment = {
  id: 'A26.9c', ...A26,
  find: '      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "", lightbox: null, lightboxFocus: false }),\n',
  replace: '      (d) => this.setState({ screen, interest: "closed", userMenu: false, wizAssets: d.assets, wizErr: "", lightbox: null, lightboxFocus: false, fMenu: null, fMenuAt: -1 }),\n',
  count: 1
};

/** A26.10 — the markup for the five. A13.3's shape, per instance: the `<select>` becomes the
 *  layer menu's trigger and its panel, wrapped in the `position: relative` div the "More filters"
 *  control in this same row already uses so the panel can anchor beneath the field. Each row
 *  carries an `id` and the TRIGGER carries `aria-activedescendant`, because the focused element
 *  is the only place a screen reader reads it and focus stays on the trigger throughout; the
 *  trigger is `role="combobox"` (ARIA 1.2 supports `aria-activedescendant` on `combobox`, not on
 *  `button` — A13's final review I1) and the rows carry `tabindex="-1"`, the other half of the
 *  same pattern.
 *
 *  The panel carries NO width declaration. A13's metro panel is `width: 300px` because its field
 *  is `min-width: 300px`; these five are five different widths, `min-width: 100%` appears nowhere
 *  in the pristine bundle, and an absolutely positioned box with no width shrink-wraps its widest
 *  row — which is always at least the current label, since the label IS one of the rows. Absent
 *  beats invented. */
const A26_10: Amendment = {
  id: 'A26.10', ...A26,
  find: [
    '          <sc-for list="{{ filters }}" as="fl" hint-placeholder-count="5">',
    '            <select value="{{ fl.value }}" onChange="{{ fl.set }}" style="{{ fl.style }}">',
    '              <sc-for list="{{ fl.options }}" as="o" hint-placeholder-count="3">',
    '                <option value="{{ o.v }}">{{ o.label }}</option>',
    '              </sc-for>',
    '            </select>',
    '          </sc-for>',
    ''
  ].join('\n'),
  replace: [
    '          <sc-for list="{{ filters }}" as="fl" hint-placeholder-count="5">',
    '            <div ref="{{ fl.hostRef }}" style="position: relative;">',
    '              <button onClick="{{ fl.toggle }}" onKeyDown="{{ fl.keys }}" role="combobox" aria-label="{{ fl.aria }}" aria-haspopup="listbox" aria-controls="{{ fl.listId }}" aria-expanded="{{ fl.open }}" aria-activedescendant="{{ fl.activeId }}" style="{{ fl.style }}">',
    '                <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ fl.triggerLabel }}</span>',
    '                <img src="assets/icons/sub-chevron.svg" alt="" width="14" height="14" style="{{ fl.caretStyle }}">',
    '              </button>',
    '              <sc-if value="{{ fl.open }}" hint-placeholder-val="{{ false }}">',
    '                <div role="listbox" aria-label="{{ fl.aria }}" id="{{ fl.listId }}" ref="{{ fl.panelRef }}" style="position: absolute; left: 0; top: 46px; z-index: 700; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;" class="rf-scroll">',
    '                  <sc-for list="{{ fl.options }}" as="o" hint-placeholder-count="3">',
    '                    <button onClick="{{ o.go }}" id="{{ o.optId }}" role="option" tabindex="-1" aria-selected="{{ o.selected }}" style="{{ o.rowStyle }}" style-hover="background: var(--vf-neutral);">',
    '                      <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ o.label }}</span>',
    '                      <img src="assets/icons/sub-check-filled.svg" alt="" width="11" height="11" style="{{ o.tickStyle }}">',
    '                    </button>',
    '                  </sc-for>',
    '                </div>',
    '              </sc-if>',
    '            </div>',
    '          </sc-for>',
    ''
  ].join('\n'),
  count: 1
};

/** A26.11 — the markup for the three inside the "More filters" popover, Task F2. A26.10's shape
 *  per instance, dropped into the design's own `<label>` without disturbing it: the caption
 *  `<span>` is byte-unchanged and the `<select>` becomes the layer menu's trigger and its panel,
 *  wrapped in the `position: relative` div the popover's own parent already uses so the panel can
 *  anchor beneath the field.
 *
 *  The trigger carries `width: 100%`, which the popover's own "Done" button carries and is
 *  therefore the design's own declaration. It is load-bearing rather than decorative: the
 *  `<select>` was a flex item of the column `<label>` and stretched to the popover's width by
 *  `align-items: stretch`, while a button inside the new wrapper is not a flex item and would
 *  shrink-wrap — and A26.16's `min-width: 100%` resolves against that wrapper, so a trigger
 *  narrower than its wrapper would leave the panel wider than the trigger, which is the opposite
 *  of what John ruled.
 *
 *  `aria-label` is `mf.label`, the caption the popover already shows. A `<label>` does not name a
 *  `<button>` — a button's accessible name is computed from its own contents before the host
 *  language's label is consulted — so without it the trigger would be named by its current
 *  option, exactly the problem A26.2 fixed for the unlabelled five. It is also what keeps
 *  `screens.ts`'s `layerTrigger` (`button[aria-haspopup="listbox"]:not([aria-label])`) pointing
 *  at the Market data card's two.
 *
 *  Clicking the caption still reaches the control, as it did with the `<select>`: a `<label>`'s
 *  activation behaviour forwards to its first labelable descendant, and does nothing for a click
 *  that lands on an interactive descendant — so an option row's own click is not forwarded. */
const A26_11: Amendment = {
  id: 'A26.11', ...A26,
  find: [
    '                  <sc-for list="{{ moreFilters }}" as="mf" hint-placeholder-count="3">',
    '                    <label style="display: flex; flex-direction: column; gap: 5px;">',
    '                      <span style="font-size: 12px; font-weight: 500; color: var(--vf-text);">{{ mf.label }}</span>',
    '                      <select value="{{ mf.value }}" onChange="{{ mf.set }}" style="height: 38px; padding: 0 10px; font-size: 13px; font-weight: 500; color: var(--vf-navy); background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;">',
    '                        <sc-for list="{{ mf.options }}" as="o" hint-placeholder-count="3">',
    '                          <option value="{{ o.v }}">{{ o.label }}</option>',
    '                        </sc-for>',
    '                      </select>',
    '                    </label>',
    '                  </sc-for>',
    ''
  ].join('\n'),
  replace: [
    '                  <sc-for list="{{ moreFilters }}" as="mf" hint-placeholder-count="3">',
    '                    <label style="display: flex; flex-direction: column; gap: 5px;">',
    '                      <span style="font-size: 12px; font-weight: 500; color: var(--vf-text);">{{ mf.label }}</span>',
    '                      <div ref="{{ mf.hostRef }}" style="position: relative;">',
    '                        <button onClick="{{ mf.toggle }}" onKeyDown="{{ mf.keys }}" role="combobox" aria-label="{{ mf.label }}" aria-haspopup="listbox" aria-controls="{{ mf.listId }}" aria-expanded="{{ mf.open }}" aria-activedescendant="{{ mf.activeId }}" style="display: inline-flex; align-items: center; gap: 8px; width: 100%; height: 38px; padding: 0 10px; font-size: 13px; font-weight: 500; color: var(--vf-navy); background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;">',
    '                          <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ mf.triggerLabel }}</span>',
    '                          <img src="assets/icons/sub-chevron.svg" alt="" width="14" height="14" style="{{ mf.caretStyle }}">',
    '                        </button>',
    '                        <sc-if value="{{ mf.open }}" hint-placeholder-val="{{ false }}">',
    '                          <div role="listbox" aria-label="{{ mf.label }}" id="{{ mf.listId }}" ref="{{ mf.panelRef }}" style="position: absolute; left: 0; top: 46px; z-index: 700; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;" class="rf-scroll">',
    '                            <sc-for list="{{ mf.options }}" as="o" hint-placeholder-count="3">',
    '                              <button onClick="{{ o.go }}" id="{{ o.optId }}" role="option" tabindex="-1" aria-selected="{{ o.selected }}" style="{{ o.rowStyle }}" style-hover="background: var(--vf-neutral);">',
    '                                <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ o.label }}</span>',
    '                                <img src="assets/icons/sub-check-filled.svg" alt="" width="11" height="11" style="{{ o.tickStyle }}">',
    '                              </button>',
    '                            </sc-for>',
    '                          </div>',
    '                        </sc-if>',
    '                      </div>',
    '                    </label>',
    '                  </sc-for>',
    ''
  ].join('\n'),
  count: 1
};

/** A26.12–A26.14 — John's 2026-09-08 m7 ruling, RESTORED (controller ruling on the A26 plan's
 *  Q2, 2026-09-11). Its own three ids, on three lines A26.8 is already editing, so the widening
 *  can be lifted out without touching the rest of the family.
 *
 *  m7 reads "opening any one of the four menus closes the other three", and three of the twelve
 *  ordered directions among `navMenu`, `userMenu`, `giveMenu` and `marketMenu` were never
 *  written: the account toggle closed neither the nav menu nor the metro listbox, the nav toggle
 *  closed no metro listbox, and the metro trigger closed neither of the header's two. Give's own
 *  six were complete, which is why the gap survived that review — and why it is a real defect and
 *  not a theoretical one: Give and the metro listbox ALSO carry global pointerdown and focusout
 *  dismissal (A13.4/A13.8), so their pointer paths were covered by accident, while `navMenu` and
 *  `userMenu` have no outside-click, Escape or Tab dismissal of any kind. Two mouse clicks reach
 *  it: open the account menu, click the metro trigger, and both stand open.
 *
 *  That wider menu-hygiene gap is reported as D-F2 and is NOT built here — it is its own piece of
 *  work and this ruling does not authorise it. These three edits restore exactly the invariant
 *  John already ruled on, and nothing else.
 *
 *  No pixel moves: each writes `false` over a flag that is already `false` in every approved
 *  state, since no state opens two menus at once. */
const A26_12: Amendment = {
  id: 'A26.12', ...A26,
  find: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  replace: '      toggleNavMenu: () => this.setState({ navMenu: !s.navMenu, userMenu: false, giveMenu: false, fMenu: null, fMenuAt: -1, marketMenu: false, marketMenuAt: -1 }),\n',
  count: 1
};

const A26_13: Amendment = {
  id: 'A26.13', ...A26,
  find: '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  replace: '      toggleUserMenu: () => this.setState({ userMenu: !s.userMenu, giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, marketMenu: false, marketMenuAt: -1 }),\n',
  count: 1
};

const A26_14: Amendment = {
  id: 'A26.14', ...A26,
  find: '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false, fMenu: null, fMenuAt: -1 }),\n',
  replace: '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")), giveMenu: false, fMenu: null, fMenuAt: -1, navMenu: false, userMenu: false }),\n',
  count: 1
};

/** A26.15 — the fourth direction, found by the Q2 characterisation case rather than by reading.
 *
 *  A26.12–A26.14 fixed the three the A26 ruling's section 8 named, all of them PONTER paths. The
 *  exhaustive enumeration of ordered pairs then failed on `nav then metro (arrow)`: the metro
 *  listbox's ARROW-key open path (`marketMenuKeys`) closes none of the other three, where its
 *  click path (`toggleMarketMenu`) closes all three after A26.14.
 *
 *  It is the same defect and the same ruling. A14's own m7 fix had to cover BOTH of Give's open
 *  paths for exactly this reason, and m7's own comment names this user: "a pure-keyboard user
 *  could hold this listbox and the header's Give menu open at once". The account menu has no
 *  focusout dismissal (D-F2), so Shift+Tab from it to the metro trigger and one ArrowDown reaches
 *  the state with a keyboard alone. Its own id, like A26.12–A26.14, and it changes no pixel: it
 *  writes `false` over three flags that are already `false` in every approved state. */
const A26_15: Amendment = {
  id: 'A26.15', ...A26,
  find: '          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur, fMenu: null, fMenuAt: -1 });\n',
  replace: '          if (!s.marketMenu) return this.setState({ marketMenu: true, marketMenuAt: cur, fMenu: null, fMenuAt: -1, navMenu: false, userMenu: false, giveMenu: false });\n',
  count: 1
};

/** A26.16 — the panel takes the width of the trigger that opened it (John, 2026-09-11, Task F1b).
 *  Its OWN ruling and therefore its own id, and it edits BOTH panels in one entry (count: 2), so
 *  Task F2's three are born with the width rather than acquiring it in a third pass.
 *
 *  Task F1's review measured the newly approved `browse-filter-menu` capture: the Practice type
 *  trigger is 155 px and its panel 153 px, so the panel's right edge sat 2 px INSIDE the button
 *  that opened it. It is structural rather than per-control — the row's chrome is 4 px narrower
 *  than the trigger's and the widest row claws about 2 px back — so four of the five sat ~2 px
 *  narrow and Property inverted, opening far wider than its 129 px collapsed trigger. The family
 *  had no consistent panel-to-trigger relationship at all.
 *
 *  Why this needed a ruling rather than a default: A26.10's panel string is A13's metro panel
 *  string with `width: 300px` DELETED and nothing else changed, so "the design is silent here"
 *  was never the honest description — and the design is not silent. Six of six absolutely
 *  positioned menu panels in the pristine bundle carry a width (account 208 px, the other header
 *  menu 236 px, More filters 262 px, the layer menu 300 px, A13's listbox 300 px, A14's Give
 *  panel `width: max-content; min-width: 130px`); the compare menu has none only because it is in
 *  normal flow and fills its trigger by construction. A13 additionally pins its panel and its
 *  field to the same 300 px deliberately, so their edges land together — the design's own stated
 *  intent for this exact idiom.
 *
 *  The mechanism invents no number for any of the eight controls: each trigger already sits in a
 *  `position: relative` wrapper with its panel absolutely positioned inside it, so `min-width:
 *  100%` resolves against the wrapper — the trigger — and makes the panel at least as wide as it.
 *  It is a NEW declaration, and this family's own gate otherwise requires every declaration to
 *  appear in the pristine bundle; John's ruling makes it the SECOND named exception, after the
 *  More-filters anchoring pair. `design-amendments.test.ts` retires the two
 *  `not.toContain('min-width: 100%')` trip-wires Task F1 left for exactly this moment and asserts
 *  instead that the declaration is on these two panels and nowhere else.
 *
 *  Rejected, and why: A14's `width: max-content; min-width: <px>` would mean inventing eight
 *  numbers; one shared fixed width would mean choosing for the longest option across all eight
 *  and leaving seven panels wider than they need to be. A13's metro panel keeps its own measured
 *  300 px and is untouched here — its `find` carries `width: 300px` and this one does not. */
const A26_16: Amendment = {
  id: 'A26.16', date: '2026-09-11',
  ruling: 'the panel takes the width of the trigger that opened it, so their edges line up',
  find: 'top: 46px; z-index: 700; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;',
  replace: 'top: 46px; z-index: 700; min-width: 100%; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;',
  count: 2
};

/** A27 (John, 2026-09-11 — rulings D-C38 and D-C39). PER-FIGURE GEOGRAPHY on the Community
 *  Context card, and the ring described by DISTANCE rather than by time.
 *
 *  What John was shown: a Dallas practice headed "Specialty practice — Highland Park / affluent
 *  central" whose card read the same four numbers as every other Dallas listing, South Dallas
 *  included — median income $67,760 on all twelve — because all twelve sit inside one Census
 *  place and `serve.py` served the place band to every one of them. He chose the option in which
 *  EACH TILE NAMES WHERE ITS OWN NUMBER COMES FROM, against the cheaper one that relabels every
 *  tile uniformly, and the reason he rejected that one is worth keeping: it moves the defect one
 *  tile over rather than fixing it, because the Growth number would still be the whole City of
 *  Dallas under a caption saying otherwise.
 *
 *  THE HONEST MEASURE, which no comment here may soften: three of the card's four tiles gain
 *  neighbourhood detail. The fourth gains an honest label and nothing more — `population_growth_pct`
 *  cannot vary below place-or-county until the 2010->2020 tract crosswalk is loaded, a registered
 *  Phase C deferral (`materialize.py` computes it once per listing OUTSIDE the band loop and
 *  writes that one value into all three bands, plan D12). On the Browse map two of the three fill
 *  layers still paint one flat colour per city or county. This is not "per-neighbourhood market
 *  data" and may not be described as such.
 *
 *  D-C39: the band is an 8 km straight-line buffer from the practice point (spec §8), not a
 *  routed drive time, and spec §15 still lists true drive-time isochrones as OPEN for V1. So the
 *  card says "within about 5 miles of the practice", and the two live sentences that said
 *  otherwise over PLACE-band figures — the docked panel's Insights heading and its footnote — are
 *  corrected in the same release rather than left to contradict it. He took the largest of the
 *  three wording options knowingly, and it touches approved copy: A27.3 and A27.4 re-base the
 *  Browse states that render the panel. None of `baseline-manifest.json`'s thirteen frozen hashes
 *  is a Browse capture, and none of them moves.
 *
 *  THE NULL BRANCH OF EVERY ENTRY IS BYTE-IDENTICAL IN WHAT IT RENDERS — the A21.5 pattern
 *  (`design-amendments.ts`'s A21.5b/A21.5c), and the reason no approved state outside those two
 *  Browse captures moves: `frontend/tests/design-listings.mjs` sends `null` for `growth_scope` and
 *  `income_note` exactly as it sends it for `community_label`, so the reference, the app and every
 *  baseline take the design's own literal.
 *
 *  A27.3 is the ONE entry whose null branch does change, and deliberately: the design's own
 *  "Market Overview (10 min drive)" is the false sentence D-C39 names, so there is no null branch
 *  to preserve — it is the thing being corrected. A27.4 is the same. The third such sentence,
 *  the Browse "Market data" card's "Figures describe the community around each practice…",
 *  IS corrected too, as A27.5 — its own id and its own ruling, not a silent widening of A27.4:
 *  the figures it describes are the ones this release moves to the catchment, so leaving it
 *  would have made it false by this release's own act. It sits inside the strip behind
 *  `md.stripOpen`, which no approved state opened until `browse-market-strip` was appended
 *  to `screens.ts` in the same release (D-C40). */

/** A27.1 — the Median income tile's sub-line. The design hard-codes "Household, 2023", and
 *  A21.5b/A21.5c deliberately took only the two sub-lines that said "the community" — so this was
 *  the one area figure on the card whose caption could not follow its own geography. With no note
 *  the design's literal stands, byte for byte. */
const A27_1: Amendment = {
  id: 'A27.1', date: '2026-09-11', ruling: 'each tile names where its own number comes from, and a ring median says it is approximate (D-C38)',
  find: '{ k: "Median income", v: p.income, sub: "Household, 2023" },',
  replace: '{ k: "Median income", v: p.income, sub: p.incomeNote || "Household, 2023" },',
  count: 1
};

/** A27.2 — the Growth tile's sub-line, which is where D-C38 actually lands: the figure stays the
 *  city's or the county's and the caption SAYS so, beside a population that is the ring's.
 *
 *  CHAINED on A21.3d, like A21.5c on A12.7: the `find` is A21.3d's whole `replace`, not the
 *  pristine row, because A21.3d already rewrote this row to take the vintage from the API's own
 *  string instead of hard-coding 2015. The null branch returns exactly what A21.3d returns —
 *  "Since <year>", or "" where the API sent no vintage — so a listing with no named geography
 *  renders the same bytes it does today. */
const A27_2: Amendment = {
  id: 'A27.2', date: '2026-09-11', ruling: 'growth keeps its city-or-county figure and its own sub-line says so (D-C38)',
  find: '{ k: "Growth", v: (() => { const g = (p.growth || "").split(" since "); return g[0]; })(), sub: (() => { const g = (p.growth || "").split(" since "); return g.length > 1 ? "Since " + g[1] : ""; })() },',
  replace: '{ k: "Growth", v: (() => { const g = (p.growth || "").split(" since "); return g[0]; })(), sub: (() => { const g = (p.growth || "").split(" since "); const y = g.length > 1 ? g[1] : ""; if (!p.growthScope) return y ? "Since " + y : ""; return y ? p.growthScope + " · since " + y : p.growthScope; })() },',
  count: 1
};

/** A27.3 — the docked panel's Insights heading. D-C39 names this sentence: it reads "Market
 *  Overview (10 min drive)" over PLACE-band figures on 28 of 29 listings today, and the band it
 *  names is not a drive time even on the one listing it describes. The parenthetical goes and the
 *  design's own two words stay; `communityLabel` still overrides the whole heading when the
 *  figures came from the catchment, which is A21.5a's mechanism unchanged.
 *
 *  CHAINED on A21.4a, which introduced the line. */
const A27_3: Amendment = {
  id: 'A27.3', date: '2026-09-11', ruling: 'the ring is described by distance, not by time, and the sentences that said otherwise are corrected in the same release (D-C39)',
  find: 'overviewTitle: sel.communityLabel || "Market Overview (10 min drive)",',
  replace: 'overviewTitle: sel.communityLabel || "Market Overview",',
  count: 1
};

/** A27.4 — the docked panel's footnote, the second sentence D-C39 names. "Drive-time figures are
 *  approximated from a straight-line catchment around the practice" is two claims, and the first
 *  is false: there is no drive time anywhere in the pipeline. The straight-line catchment IS the
 *  measurement, so the corrected sentence keeps it and says how far it reaches. The other two
 *  sentences in the paragraph are untouched, byte for byte.
 *
 *  CHAINED on A21.4d, which wrapped this paragraph in the `hasDemo` branch. */
const A27_4: Amendment = {
  id: 'A27.4', date: '2026-09-11', ruling: 'the ring is described by distance, not by time, and the sentences that said otherwise are corrected in the same release (same ruling)',
  find: 'Drive-time figures are approximated from a straight-line catchment around the practice. ',
  replace: 'A catchment figure is a straight-line area of about 5 miles around the practice, not a driving route. ',
  count: 1
};

/** A27.5 (controller ruling on the implementer's own concern, 2026-09-11). D-C39 named TWO
 *  sentences that describe the ring by time; the implementer found a THIRD and, correctly,
 *  did not widen its own scope. The Browse "Market data" card says "Figures describe the
 *  community around each practice" — which was already loose over place-band figures and
 *  becomes plainly wrong once D-C38 serves most of them from the catchment. Leaving it would
 *  have shipped a change that fixes two false sentences and makes a third one worse in the
 *  same release. "Area" is true whichever band answered, which is why it is the word chosen
 *  over naming either geography here: this sentence covers every listing on the screen at
 *  once, and they no longer all come from the same band. */
const A27_5: Amendment = {
  id: 'A27.5', date: '2026-09-11', ruling: 'the third sentence that described the figures as the community is corrected too (D-C39, extended on the implementer\'s report)',
  find: 'Figures describe the community around each practice, not the practice itself. ',
  replace: 'Figures describe the area around each practice, not the practice itself. ',
  count: 1
};

/** A27.6 (John, 2026-09-11 — ruling D-C42). THE HEADING KEEPS ITS NAME; THE GEOGRAPHY GOES TO A
 *  SUB-LINE. A21.5a let `communityLabel` REPLACE the docked panel's Insights heading, and D-C38
 *  gives 28 of 29 QA listings a label — so on QA the heading read "Within about 5 miles of the
 *  practice" and the words "Market Overview" appeared NOWHERE. A27.3's own correction was
 *  invisible for the same reason: the default it corrected was never reached. The cost was named
 *  in the ruling that produced Option C, as a cost of the Option B John REJECTED; it landed under
 *  Option C too and had never been put to him. It was, and he ruled: the section gets its name
 *  back and the label moves beneath it.
 *
 *  He took the reasoning that this is the card's OWN established idiom — A21.5b, A21.5c, A27.1
 *  and A27.2 all put the geography on a sub-line under the value it describes, and the heading
 *  was the only place on the card where the label replaced the thing it was meant to qualify.
 *
 *  CHAINED on A27.3, whose `replace` this `find` is, exactly as A27.2 chains on A21.3d and A21.5c
 *  on A12.7. A21.5a's own edit — the template interpolation — STAYS: it is what put a render value
 *  in the heading at all, and the heading is still data. What is retired is its BEHAVIOUR, the
 *  `||` that let the label stand in for the title, and it is retired by a later entry rather than
 *  by editing an earlier one's `find`/`replace`.
 *
 *  `hasOverviewScope` is a boolean because the design's own way to omit an element is `sc-if` over
 *  one (A21.4a's `hasDemo`/`noDemo`, this same panel). With no label the sub-line is not in the
 *  DOM and the heading is A27.3's literal byte for byte, which is what keeps every approved state
 *  and all thirteen frozen hashes where they are. */
const A27_6: Amendment = {
  id: 'A27.6', date: '2026-09-11', ruling: 'the Insights heading keeps its name and the geography moves to its own sub-line beneath it (D-C42)',
  find: 'overviewTitle: sel.communityLabel || "Market Overview",',
  replace: 'overviewTitle: "Market Overview",\n      hasOverviewScope: !!sel.communityLabel,\n      overviewScope: sel.communityLabel || "",',
  count: 1
};

/** A27.7 — the sub-line itself, beneath the heading A27.6 gave back its name.
 *
 *  COMPOSED FROM THE DESIGN'S OWN ELEMENT, not invented: the declaration is the docked panel's
 *  own `md.panel.place` line — `font-size: 12.5px; color: var(--vf-text); margin-top: 2px;` —
 *  which sits eight lines above this one in the same panel, under `md.panel.name`, and is the
 *  design's only existing heading-and-geography pair: a title in the display face with the place
 *  it describes on a quieter line directly beneath. It occurs exactly once in the pristine bundle,
 *  so nothing else can be picked up by mistake. Type, colour and spacing are taken whole; none of
 *  the three is chosen here.
 *
 *  Rejected, and why: the overview tiles' own sub-line (`9.5px`, `var(--vf-accent)`) qualifies a
 *  FIGURE and is accent-coloured for it, and the footnote's `10.5px` closes the section rather
 *  than opening one. Neither is a heading's sub-line; the place line is.
 *
 *  CHAINED on A21.5a, whose `replace` this `find` is — the interpolation A21.5a introduced. The
 *  `sc-if` carries `hint-placeholder-val="{{ false }}"` for the same reason A21.4c's `noDemo`
 *  branch does: the design's own fixtures carry no `communityLabel`, so the branch the Claude
 *  Design preview should show is the one without it. */
const A27_7: Amendment = {
  id: 'A27.7', date: '2026-09-11', ruling: 'the Insights heading keeps its name and the geography moves to its own sub-line beneath it (same ruling)',
  find: '<div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);">{{ md.panel.overviewTitle }}</div>',
  replace: '<div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);">{{ md.panel.overviewTitle }}</div>\n'
    + '                  <sc-if value="{{ md.panel.hasOverviewScope }}" hint-placeholder-val="{{ false }}">\n'
    + '                    <div style="font-size: 12.5px; color: var(--vf-text); margin-top: 2px;">{{ md.panel.overviewScope }}</div>\n'
    + '                  </sc-if>',
  count: 1
};

/** A27.8 (John, 2026-09-11 — ruling D-C48, on the whole-branch review of this branch). THE
 *  DOCKED PANEL'S POPULATION TILE NAMES THE GEOGRAPHY ITS OWN SUB-LINE CAME FROM.
 *
 *  A27.7 places ONE geography sub-line above the whole four-tile grid, and three of the four
 *  tiles are the area group it describes. The fourth is not: the Population tile's SUB-LINE is
 *  not a population figure at all — it is GROWTH, which `serve.py` measures at place-or-county
 *  and serves with its own `growth_scope`, and which reads −1.5% for the whole of Dallas. So the
 *  panel printed a city number under a caption describing a ring, on 28 of 29 QA listings: the
 *  defect D-C38 removed, one card over, live in front of the stakeholder.
 *
 *  John ruled it is named ON THE TILE, so the heading's sub-line honestly covers only the
 *  figures it describes. The idiom is the detail card's own Growth tile (A27.2) and the API's own
 *  `income_note` (A27.1): the design's ` · ` joins a figure to the thing that qualifies it. The
 *  figure and its period lead and the geography follows, because unlike A27.2's sub-line — where
 *  the whole line is a qualifier and the scope opens it — this line BEGINS with the number.
 *
 *  CHAINED on A21.2d, whose `replace` this `find` is part of: A21.2d already rewrote this tile
 *  to render nothing rather than a dangling unit where the API sent no growth. That guard is
 *  what the new term sits inside, so no figure still means no sub-line — a geography with no
 *  number beside it is a caption for something that is not there.
 *
 *  `sel` is the panel's own selected listing, already read four lines above for `hasDemo`; the
 *  scope is the LISTING's (`growth_scope`), not the community row's, because growth cannot vary
 *  by band (plan D12) and the community object carries no name. The design's own fixtures carry
 *  no `growthScope`, so the guard is falsey and every approved state keeps its pixels. */
const A27_8: Amendment = {
  id: 'A27.8', date: '2026-09-11', ruling: 'the panel\'s Population tile names the geography its growth sub-line was measured at (D-C48)',
  find: 'k: "Population", sub: (c.growth !== undefined) ? ((c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)") : undefined },',
  replace: 'k: "Population", sub: (c.growth !== undefined) ? ((c.growth > 0 ? "+" : "") + c.growth.toFixed(1) + "% (5 yrs)" + (sel.growthScope ? " \u00b7 " + sel.growthScope : "")) : undefined },',
  count: 1
};

/** A28.1 (John, 2026-09-11 — ruling D-C44). THE RING IS DRAWN AT THE DISTANCE THE CARD NAMES.
 *  `MarketMapV3.jsx:230-234` draws the C7 drive-time ring at `radius: 16000, color: "#003a70"`,
 *  and D-C38 gives the Community Context card the sentence "Within about 5 miles of the
 *  practice" — so a buyer reads one distance and is shown a circle twice its size, on every
 *  listing with a point.
 *
 *  Neither number is invented. V2 drew TWO rings
 *  (`design_handoff_practice_match_v2/MarketMap.jsx:160-169`): `drive10` at 16 000 m in
 *  `#339dde` and `drive5` at 8 000 m in `#003a70`. V3 replaced the panel that toggled them,
 *  kept ONE hard-coded ring, and kept the FAR radius in the NEAR ring's colour — a mash-up of
 *  V2's two rings rather than either of them. 8 000 m is the band the card describes, the band
 *  D-C38 serves the area figures from, and the band `#003a70` already belongs to, so the number
 *  and the colour agree for the first time since the V3 panel rewrite.
 *
 *  The FIRST entry in `amendments()` order to edit `MarketMapV3.jsx` — `file: 'jsx'`, the
 *  partition spec §9.2 put in place for A24 — and the first to LAND, because A28's branch merged
 *  first. A24's own four jsx entries are appended after this family, not before it. No visible control is added: John was offered V2's
 *  two toggleable rings, composed into V3's own "Market data layers" drawer, and chose against
 *  it. A25.6's "no point, no ring" is untouched — the radius moves, the finite-point test that
 *  decides whether anything is drawn at all does not. */
const A28_1: Amendment = {
  id: 'A28.1', date: '2026-09-11', file: 'jsx',
  ruling: 'the ring is drawn at the distance the card names — 8 000 m, keeping #003a70 (D-C44)',
  find: '        radius: 16000, color: "#003a70", weight: 1.5, dashArray: "4 4",',
  replace: '        radius: 8000, color: "#003a70", weight: 1.5, dashArray: "4 4",',
  count: 1
};

/** A28.2 (same ruling). THE LEGACY PANEL'S GROUP 1 ROWS, deleted under the bundle's own
 *  dead-code rule — the rule that removed the `browseSel` orphans (A2.3-A2.5) and the two
 *  `<select>` render-value orphans A13 left behind (A13.6-A13.7).
 *
 *  `layerHelp` and `fillRows` are read by NO template on either target: each occurs exactly once
 *  in the amended design — its own declaration — and zero times in the template region, and
 *  `grep fillRows frontend/src/App.vue` is empty. The design says so itself on the line this
 *  entry deletes with them: "GROUP 1 — retained for the legacy panel; the compact control above
 *  is canonical." V3 replaced that panel with `md.layerChoices` ("Market data layers · select
 *  any or all"), which is what `browse-layers-open` photographs. */
const A28_2: Amendment = {
  id: 'A28.2', date: '2026-09-11', ruling: 'the orphans are deleted under the bundle\'s own dead-code rule (D-C44)',
  find: '      // GROUP 1 — retained for the legacy panel; the compact control above is canonical.\n'
    + '      layerHelp: "Area shading: rates and medians shade the whole community, so only one can show at a time — two fills blend into a colour that means nothing. Overlays: counts drawn as sized circles, which stack freely on each other and on the shading.",\n'
    + '      fillRows: [radioRow("none", "No shading", !valueLayer, null, () => this.setState({ mdValue: null }))].concat(\n'
    + '        enabled("income") ? [radioRow("income", "Median Household Income", valueLayer === "income", ramp("income")[3], setValue("income"))] : [],\n'
    + '        enabled("growth") ? [radioRow("growth", "Population Growth", valueLayer === "growth", ramp("growth")[3], setValue("growth"))] : [],\n'
    + '        enabled("econ") ? [radioRow("econ", "Average Practice Payroll", valueLayer === "econ", ramp("econ")[3], setValue("econ"))] : []\n'
    + '      ),\n',
  replace: '',
  count: 1
};

/** A28.3 (same ruling). THE LEGACY PANEL'S GROUP 2 ROWS, on the same rule and the same
 *  measurement: `overlayRows` occurs exactly once in the amended design, its own declaration,
 *  and zero times in the template region; `grep overlayRows frontend/src/App.vue` is empty.
 *
 *  This is the entry that removes the LAST "drive time" strings in the product — "5–10 min drive
 *  time" and "10–20 min drive time", two rows nothing renders. A27.3/A27.4/A27.5 corrected every
 *  sentence a member can actually read; these two were all that was left, which is what D-C39 was
 *  reaching for and could not name correctly. */
const A28_3: Amendment = {
  id: 'A28.3', date: '2026-09-11', ruling: 'the orphans are deleted under the bundle\'s own dead-code rule (same ruling)',
  find: '      // GROUP 2 — everything that can coexist with a fill and with each other.\n'
    + '      overlayRows: [\n'
    + '        layerRow("practices", "Practice Listings", !!layers.practices, "#003a70", setLayer("practices")),\n'
    + '        layerRow("drive5", "5–10 min drive time", !!layers.drive5, "#003a70", setLayer("drive5")),\n'
    + '        layerRow("drive10", "10–20 min drive time", !!layers.drive10, "#339dde", setLayer("drive10"))\n'
    + '      ].concat(\n'
    + '        enabled("households") ? [layerRow("households", "Households", !!layers.households, ramp("households")[3], setLayer("households"))] : [],\n'
    + '        enabled("pets") ? [layerRow("pets", "Estimated Pet Households", !!layers.pets, ramp("pets")[3], setLayer("pets"))] : [],\n'
    + '        enabled("vets") ? [layerRow("competition", "Veterinary Establishments", !!layers.competition, ramp("competition")[3], setLayer("competition"))] : []\n'
    + '      ),\n',
  replace: '',
  count: 1
};

/** A28.4 (same ruling). THE TWO DRIVE-BAND STATE FLAGS. `drive5` and `drive10` are the only two
 *  members of `marketVals`'s layer defaults that A28.3's rows were the sole reader of: the other
 *  four are live — `practices`, `households`, `pets` and `competition` are what `SYMBOL_KEYS`
 *  filters `activeSymbols` by (`logic.js`), and `competition` is written by the Data Layers
 *  card's own source switch. Deleting the two that nothing reads leaves those four exactly as
 *  they are, including their order. */
const A28_4: Amendment = {
  id: 'A28.4', date: '2026-09-11', ruling: 'the drive5/drive10 state flags go with the rows that were their only reader (same ruling)',
  find: '      { practices: true, drive5: true, drive10: true, competition: true, households: false, pets: false },',
  replace: '      { practices: true, competition: true, households: false, pets: false },',
  count: 1
};

/** A28.5-A28.8 (controller amendment D-C45, 2026-09-11). THE HELPERS THE DELETION ORPHANED.
 *  D-C44 deleted the legacy panel's rows (`fillRows`, `overlayRows`) and the two state flags
 *  those rows were the sole reader of, but left the four helpers that BUILT the rows standing —
 *  the ruling named the rows and the flags and nothing else, and the D-C44 implementer added a
 *  case asserting the four were still present so that leaving them would read as a decision
 *  rather than an oversight. This closes it: `radioRow`, `layerRow`, `setValue` and `setLayer`
 *  are re-measured (as the brief required before deleting) and each occurs exactly ONCE in
 *  `logic.js` and once in the amended design — its own declaration — and ZERO times in
 *  `App.vue`. Same rule as A2.3-A2.5 and A13.6-A13.7: one entry per helper, in the file's own
 *  order, each entry taking its own trailing blank line so the block that follows (`s.mdOff`'s
 *  footer-card switch) ends up separated from `minLng` by exactly the one blank line the design
 *  had before any of GROUP 1/GROUP 2 existed. */
const A28_5: Amendment = {
  id: 'A28.5', date: '2026-09-11', ruling: 'the helpers the deletion orphaned go too (controller amendment D-C45)',
  find: '    const layerRow = (key, label, on, color, toggle) => ({\n      label, on,\n      toggle,\n      boxStyle: "flex: none; width: 17px; height: 17px; border-radius: 3px; display: grid; place-items: center; border: 1.5px solid " +\n        (on ? color : "#c4ccd6") + "; background: " + (on ? color : "var(--vf-white)") + ";",\n      tickStyle: "display: block; opacity: " + (on ? "1" : "0") + ";",\n      textStyle: "font-size: 13px; font-weight: " + (on ? "500" : "400") + "; color: " + (on ? "var(--vf-navy)" : "var(--vf-text)") + ";"\n    });\n\n',
  replace: '',
  count: 1
};

const A28_6: Amendment = {
  id: 'A28.6', date: '2026-09-11', ruling: 'the helpers the deletion orphaned go too (same amendment)',
  find: '    const radioRow = (key, label, on, color, toggle) => ({\n      label, on, toggle,\n      boxStyle: "flex: none; width: 15px; height: 15px; border-radius: 999px; display: grid; place-items: center; border: 1.5px solid " +\n        (on ? "var(--vf-navy)" : "#c3d4e2") + "; background: var(--vf-white);",\n      dotStyle: "width: 7px; height: 7px; border-radius: 999px; background: var(--vf-navy); opacity: " + (on ? "1" : "0") + ";",\n      swatchStyle: "flex: none; width: 12px; height: 12px; border-radius: 2px; background: " + (color || "transparent") +\n        "; opacity: " + (color ? (on ? "1" : ".4") : "0") + ";",\n      labelStyle: "font-size: 12.5px; font-weight: " + (on ? "500" : "400") + "; color: " + (on ? "var(--vf-navy)" : "var(--vf-text)") + ";"\n    });\n\n',
  replace: '',
  count: 1
};

const A28_7: Amendment = {
  id: 'A28.7', date: '2026-09-11', ruling: 'the helpers the deletion orphaned go too (same amendment)',
  find: '    const setValue = (k) => () => this.setState({ mdValue: s.mdValue === k ? null : k });\n',
  replace: '',
  count: 1
};

const A28_8: Amendment = {
  id: 'A28.8', date: '2026-09-11', ruling: 'the helpers the deletion orphaned go too (same amendment)',
  find: '    const setLayer = (k) => () => this.setState({ mdLayers: Object.assign({}, layers, { [k]: !layers[k] }) });\n\n',
  replace: '',
  count: 1
};

/** A28.9 (controller amendment, 2026-09-11, whole-branch review). THE LAST ORPHAN THE DELETION
 *  LEFT, under the rule D-C45 already applied to the four helpers — not a new product decision,
 *  and the same rule John has ruled the shape of twice (A2.2-A2.5 for `browseSel`, A13.6-A13.7
 *  for the `<select>` render values).
 *
 *  A28.2-A28.4 deleted `overlayRows` and the `drive5`/`drive10` flags. `overlayRows`'s own row
 *  `layerRow("practices", "Practice Listings", !!layers.practices, ...)` was the ONLY reader of
 *  the `practices` default in this literal: `SYMBOL_KEYS` is `["pets", "households",
 *  "competition"]`, so `activeSymbols` never asks for it, and the one other place `layers` is
 *  spread (`patch.mdLayers = Object.assign({}, layers, { competition: false })`) copies the key
 *  forward without reading it. `md.practices` — the pin list the map component is handed — is a
 *  different declaration entirely and is untouched.
 *
 *  The other three defaults STAY: `competition`, `households` and `pets` are exactly
 *  `SYMBOL_KEYS`, and each is read on every render. */
const A28_9: Amendment = {
  id: 'A28.9', date: '2026-09-11', ruling: 'the orphans are deleted under the bundle\'s own dead-code rule (D-C44/D-C45)',
  find: '      { practices: true, competition: true, households: false, pets: false },',
  replace: '      { competition: true, households: false, pets: false },',
  count: 1
};

// A24 -- real Census boundary polygons (John's rulings D-C34-D-C37 of 2026-09-10; spec
// docs/superpowers/specs/2026-09-10-neighbourhood-shading-design.md). Eleven `.dc.html` entries and
// four in `MarketMapV3.jsx`, the family the second-file partition was put in place for
// (controller ruling, §14 Q3); A28.1 reached that file first, by merging first. A24.1's payload is GENERATED --
// scripts/export_design_boundaries.py -- so the design carries real geometry and not one hand-typed
// coordinate. A24.13 is the family's OTHER ruling, D-C46, and rides here because it moves the same
// Browse captures.
//
// PUNCTUATION: measured, the pristine `.dc.html` carries only — → © · – ÷ … ≈ − ‹ › ↗ ⌂ outside
// ASCII and the pristine `.jsx` only — – …. No `replace` below introduces a character outside
// those sets — an apostrophe in an inserted comment is the straight one the bundle's own comments
// use. (`±` in A24.3's tip is the one addition, and it is unreachable on the design's fixture
// path: `areaSet` always writes `moe: null`, so no approved state can render it. It exists for the
// API path Task 10 wires.)
const NS = {
  date: '2026-09-10',
  ruling: 'the data is not to the granular level required at neighborhood level — right now it’s just a blob over the whole city and misses the entire point of what is required and the required level of detail and data per neighborhood required to make a decision to buy a practice'
};

const A24_1: Amendment = {
  id: 'A24.1', ...NS,
  find: '    adminTab: "users", sellerView: "dash",\n',
  replace: '    areas: ' + DESIGN_AREAS_LITERAL + ',\n'
    + '    adminTab: "users", sellerView: "dash",\n',
  count: 1
};

const A24_2: Amendment = {
  id: 'A24.2', ...NS,
  find: 'const FILL_KEYS = ["income", "growth", "econ"];\n',
  replace: 'const FILL_KEYS = ["income", "growth", "econ"];\n'
    + '// A24 (D-C35): each fill layer draws at the geography its figure is honest at, and the\n'
    + '// legend names it. `pets`, `households` and `competition` stay graduated symbols at the\n'
    + '// listing point - city-scale class breaks on small areas produce a picture with no\n'
    + '// information, and `households` first `< 10K` bucket would swallow essentially every one.\n'
    + 'const AREA_LEVEL = { income: "860", growth: "160", econ: "050" };\n'
    + 'const AREA_LABEL = { income: "ZIP Code Tabulation Area", growth: "Place (city/town)", econ: "County" };\n'
    + '// D-NS16 (John, 2026-09-10): a polygon with no usable figure is drawn in a neutral class\n'
    + '// and never omitted - a hole in a choropleth reads as a boundary, not as an absence. The\n'
    + '// colour is the design\'s own --border-subtle value at the same fillOpacity every other\n'
    + '// class uses, so this adds no style vocabulary. Grey means UNMEASURED and only that: a\n'
    + '// figure that WAS measured but whose margin spans a band is shown with its value (D-C36).\n'
    + 'const NO_DATA_FILL = "#e6e6e6";\n'
    + 'const NO_DATA_LABEL = "No data";\n',
  count: 1
};

const A24_3: Amendment = {
  id: 'A24.3', ...NS,
  find: '  communities() {\n',
  replace: '  // A24 (spec 9.4): the design\'s own boundary fixture, given the design\'s own figures.\n'
    + '  // Each polygon takes the value of the NEAREST community centroid - the one line of\n'
    + '  // `mosaicCells` that survives ("spatial ASSIGNMENT of existing community data, not\n'
    + '  // interpolation, and not new data"), applied to real Census boundaries instead of grid\n'
    + '  // cells, with longitude scaled by cos(lat) exactly as the mosaic scaled it.\n'
    + '  //\n'
    + '  // The value is taken as it comes and is NOT put through `num()`: that helper strips\n'
    + '  // everything but digits and a dot, so `num(-5.1)` is `5.1` - it would turn a declining\n'
    + '  // area into a growing one. Invisible until now, because every one of the design\'s own\n'
    + '  // nine communities grows; A24.13 (D-C46) makes a negative growth a first-class value.\n'
    + '  areaSet(layer) {\n'
    + '    const src = (this.state.areas || {})[AREA_LEVEL[layer]];\n'
    + '    if (!src) return { type: "FeatureCollection", features: [] };\n'
    + '    const comms = this.communities().filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng));\n'
    + '    return {\n'
    + '      type: "FeatureCollection",\n'
    + '      features: src.features.map((f) => {\n'
    + '        const p = f.properties;\n'
    + '        let best = null, bestD = Infinity;\n'
    + '        for (let i = 0; i < comms.length; i++) {\n'
    + '          const s = comms[i];\n'
    + '          const dLat = s.lat - p.c[0];\n'
    + '          const dLng = (s.lng - p.c[1]) * Math.cos((p.c[0] * Math.PI) / 180);\n'
    + '          const d = dLat * dLat + dLng * dLng;\n'
    + '          if (d < bestD) { bestD = d; best = s; }\n'
    + '        }\n'
    + '        const raw = best ? best[layer] : undefined;\n'
    + '        return {\n'
    + '          type: "Feature", id: p.geo_id, geometry: f.geometry,\n'
    + '          properties: {\n'
    + '            geo_id: p.geo_id, name: p.name,\n'
    + '            value: (raw === undefined || raw === null) ? null : raw,\n'
    + '            moe: null, suppressed: false, suppress_reason: null, band_ambiguous: false\n'
    + '          }\n'
    + '        };\n'
    + '      })\n'
    + '    };\n'
    + '  }\n'
    + '\n'
    + '  // The ONE door every polygon enters by, whichever side produced it (spec 2.2): the\n'
    + '  // colour is `bucket()`s and the label is `fmtMetric()`s, so the fill and the legend\n'
    + '  // cannot disagree. A value that is absent OR suppressed takes the no-data class; a value\n'
    + '  // that is present takes its band even when its margin spans one (D-C36).\n'
    + '  areaVals(fc, layer) {\n'
    + '    const feats = (fc && fc.features) || [];\n'
    + '    return {\n'
    + '      type: "FeatureCollection",\n'
    + '      features: feats.map((f) => {\n'
    + '        const p = f.properties;\n'
    + '        const shown = p.value !== null && p.value !== undefined && !p.suppressed;\n'
    + '        const b = shown ? this.bucket(layer, p.value) : null;\n'
    + '        return {\n'
    + '          type: "Feature", id: p.geo_id, geometry: f.geometry,\n'
    + '          properties: {\n'
    + '            geo_id: p.geo_id, name: p.name, value: p.value, moe: p.moe,\n'
    + '            suppressed: !!p.suppressed, suppressReason: p.suppress_reason || null,\n'
    + '            ambiguous: !!p.band_ambiguous,\n'
    + '            color: shown ? b.color : NO_DATA_FILL,\n'
    + '            label: shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL,\n'
    + '            tip: this.areaTip(p, layer, shown)\n'
    + '          }\n'
    + '        };\n'
    + '      })\n'
    + '    };\n'
    + '  }\n'
    + '\n'
    + '  // The hover tip, built ONCE. Every honesty line is the wording the market-data contract\n'
    + '  // already mandates, so the map says what the docked panel says. `growth` and `econ` carry\n'
    + '  // no published margin (D-NS17) and say why rather than being greyed.\n'
    + '  areaTip(p, layer, shown) {\n'
    + '    const meta = LAYER_META[layer] || {};\n'
    + '    const absent = p.suppressed\n'
    + '      ? (p.suppress_reason === "source_flag" ? "Not published for this county" : "Estimate too imprecise to show at this geography")\n'
    + '      : "No data for this area";\n'
    + '    const margin = (p.moe !== null && p.moe !== undefined)\n'
    + '      ? "\u00b1 " + this.fmtMetric(layer, p.moe) + (p.band_ambiguous ? " \u2014 this margin spans two legend bands." : "")\n'
    + '      : (layer === "growth"\n'
    + '          ? "Derived from two ACS 5-year periods. No combined margin of error is published."\n'
    + '          : layer === "econ"\n'
    + '            ? "Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies."\n'
    + '            : "");\n'
    + '    return \'<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">\' +\n'
    + '      \'<div style="font-size:12.5px;font-weight:800;color:#003a70">\' + p.name + "</div>" +\n'
    + '      \'<div style="font-size:11px;color:#494949;margin-top:3px">\' + (meta.title || "") + "</div>" +\n'
    + '      \'<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">\' + (shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL) + "</div>" +\n'
    + '      \'<div style="font-size:10.5px;color:#494949;margin-top:4px">\' + (shown ? margin : absent) + "</div>" +\n'
    + '      \'<div style="font-size:10px;color:#767676;margin-top:5px">\' + (meta.source || "") + "</div>" +\n'
    + '    "</div>";\n'
    + '  }\n'
    + '\n'
    + '  communities() {\n',
  count: 1
};

const A24_4: Amendment = {
  id: 'A24.4', ...NS,
  find: '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {\n',
  replace: '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),\n'
    + '      communities: comms.filter((c) => Number.isFinite(c.lat) && Number.isFinite(c.lng)).map((c) => {\n',
  count: 1
};

const A24_5: Amendment = {
  id: 'A24.5', ...NS,
  find: '          hasRamp: !!valueLayer,\n'
    + '          ramp: valueLayer\n'
    + '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: cfg.buckets[i]\n'
    + '              }))\n'
    + '            : []\n',
  replace: '          hasRamp: !!valueLayer,\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1,\n'
    + '          geoLine: AREA_LABEL[valueLayer] || "",\n'
    + '          ramp: valueLayer\n'
    + '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: cfg.buckets[i]\n'
    + '              })).concat(FILL_KEYS.indexOf(valueLayer) > -1\n'
    + '                ? [{ style: "flex: 1; height: 9px; background: " + NO_DATA_FILL + ";", label: NO_DATA_LABEL }]\n'
    + '                : [])\n'
    + '            : []\n',
  count: 1
};

const A24_6a: Amendment = {
  id: 'A24.6a', ...NS,
  find: ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ md.selectFromMap }}"',
  replace: ' practices="{{ md.practices }}" communities="{{ md.communities }}" areas="{{ md.areas }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ md.selectFromMap }}"',
  count: 1
};

const A24_6b: Amendment = {
  id: 'A24.6b', ...NS,
  find: ' practices="{{ md.practices }}" communities="{{ md.communities }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ mob.selectMarker }}"',
  replace: ' practices="{{ md.practices }}" communities="{{ md.communities }}" areas="{{ md.areas }}" active-layer="{{ md.activeLayer }}" basemap="{{ md.basemap }}" active-id="{{ md.activeId }}" on-select="{{ mob.selectMarker }}"',
  count: 1
};

const A24_7: Amendment = {
  id: 'A24.7', ...NS,
  find: 'Community areas on the map are approximate — production draws Census ZCTA boundaries.',
  replace: 'Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice.',
  count: 1
};

const A24_8a: Amendment = {
  id: 'A24.8a', ...NS,
  find: '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  replace: '                    <sc-if value="{{ md.active.hasGeo }}" hint-placeholder-val="{{ true }}">\n'
    + '                      <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.geoLine }}</div>\n'
    + '                    </sc-if>\n'
    + '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  count: 1
};

const A24_8b: Amendment = {
  id: 'A24.8b', ...NS,
  find: '                        <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  replace: '                        <sc-if value="{{ md.active.hasGeo }}" hint-placeholder-val="{{ true }}">\n'
    + '                          <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.geoLine }}</div>\n'
    + '                        </sc-if>\n'
    + '                        <div style="margin-top: 10px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  count: 1
};

/** A24.13 -- D-C46 (John, 2026-09-11), the family's other ruling and the reason it rides in this
 *  change: real polygons drawn on class breaks that cannot represent real data are still one
 *  colour, and the complaint this whole stream answers would have survived A24.
 *
 *  MEASURED, not invented. ACS 5-year place populations, 2014-2018 against 2019-2023 -- exactly the
 *  pair `app.census.metrics.population_growth_pct` divides -- read from the Census Bureau's keyless
 *  summary files for all 50 states, DC and Puerto Rico: 29,232 places carry both vintages.
 *
 *    universe                        declining   [10,20,35] bottom bucket
 *    US places, all                    47.1 %          70.5 %
 *    US places >= 10,000 people        30.5 %          79.9 %
 *    Texas places inside a CBSA        43.6 %          63.1 %
 *    Austin CBSA (the design's metro)  13.8 %          32.3 %
 *
 *  So the published breaks put four places in five into ONE class, and a place that LOST population
 *  was painted the same colour as one that grew 9 %. The new stops are the tertiles of the
 *  non-declining half of that distribution -- +3.3 / +8.8 nationally, +4.8 / +13.5 across Texas
 *  metro places, +6.6 / +22.6 over all US places -- rounded to numbers a 10.5 px legend can carry.
 *  On [0, 5, 15] the four classes take 30.5 / 32.3 / 25.3 / 11.9 % of US places over 10,000 people
 *  and 27.0 / 24.7 / 27.4 / 20.9 % of Texas metro places that size.
 *
 *  FOUR buckets, not five: the growth ramp has exactly four colours in all three palettes, and a
 *  fifth class would mean inventing a colour the design does not have. The below-zero swatch is
 *  therefore the ramp's own first colour, and it is labelled "Declining" rather than "< 0%" because
 *  the ruling is that a declining area READS as declining. */
const A24_13: Amendment = {
  id: 'A24.13',
  date: '2026-09-11',
  ruling: 'D-C46 (John, 2026-09-11): the growth class breaks are re-scaled to real ACS data, with a band below zero, so a declining area reads as declining rather than as the bottom of a growth scale',
  find: '  growth: { label: "Population Growth (ACS)", short: "Projected growth (5 yrs)", unit: "pct", buckets: ["< 10%", "10\u201320%", "20\u201335%", "> 35%"], stops: [10, 20, 35] },\n',
  replace: '  growth: { label: "Population Growth (ACS)", short: "Projected growth (5 yrs)", unit: "pct", buckets: ["Declining", "0\u20135%", "5\u201315%", "> 15%"], stops: [0, 5, 15] },\n',
  count: 1
};

/** A24.14-A24.18 -- the ADAPTER path (Task 10). The seam A16 and A17 established, a fourth time:
 *  an app-only prop the reference never receives, and a ternary keyed on adapter PRESENCE rather
 *  than on data (A16.1's exact shape, A-SL23 (2)). With `props.market` present the map draws the
 *  polygons the API answered or NONE at all, whatever it answered, and never the design's own
 *  fixture -- the design's fixture is the AUSTIN metro with the design's own nine figures assigned
 *  to it, so falling back to it over a real metro would draw the wrong city's boundaries carrying
 *  numbers nobody measured. The reference and the Claude Design preview pass no adapter, so every
 *  one of these five is inert there and both targets keep Task 4's pixels.
 *
 *  The plan allotted this task ids A24.13-A24.17; D-C46 took A24.13 inside Task 4, so the five
 *  are A24.14-A24.18 and family A24 totals twenty, exactly as the plan's arithmetic says.
 *
 *  What a member sees when the API cannot answer is written down in `src/market/boundaries.ts`:
 *  the shading is empty and nothing else is, because `MarketMapView.drawOverlay` paints the C7
 *  drive-time ring before it reaches the polygon layer and `drawPins()` is a separate call. */
const A24_14: Amendment = {
  id: 'A24.14', ...NS,
  find: '    adminTab: "users", sellerView: "dash",\n',
  replace: '    mdAreas: null,\n    adminTab: "users", sellerView: "dash",\n',
  count: 1
};

/** A24.15 -- the ONE loader (A16.17's lesson: every adapter path in this design shares one, and
 *  the rejection arm is the thing callers keep forgetting). Three properties beyond the plan's
 *  specimen, each because the alternative puts a FALSE map on screen rather than an empty one:
 *
 *  1. It CLEARS `mdAreas` before it asks. Without that, changing metro leaves the previous
 *     metro's polygons painted over the new metro's view until the answer lands -- real outlines,
 *     real figures, wrong city.
 *  2. It ignores an answer for a market the member has since left. Two fetches can resolve out of
 *     order, and last-write-wins would then leave the wrong metro's boundaries on screen
 *     indefinitely rather than transiently.
 *  3. A refused or empty load EMPTIES the map. It never restores the design's fixture, because a
 *     member must not be shown boundaries that are not the ones the API holds (A-SL23 (2)). */
const A24_15: Amendment = {
  id: 'A24.15', ...NS,
  find: '  componentDidMount() {\n',
  replace: '  loadAreas(market) {\n'
    + '    if (!this.props.market) return;\n'
    + '    const asked = market || "Austin, TX";\n'
    + '    const mine = () => (this.state.market || "Austin, TX") === asked;\n'
    + '    this.setState({ mdAreas: null });\n'
    + '    this.props.market.boundaries(asked).then(\n'
    + '      (areas) => { if (mine()) this.setState({ mdAreas: areas }); },\n'
    + '      () => { if (mine()) this.setState({ mdAreas: {} }); }\n'
    + '    );\n'
    + '  }\n'
    + '\n'
    + '  componentDidMount() {\n',
  count: 1
};

const A24_16: Amendment = {
  id: 'A24.16', ...NS,
  find: '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),\n',
  replace: '      areas: this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer),\n',
  count: 1
};

const A24_17: Amendment = {
  id: 'A24.17', ...NS,
  find: '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n',
  replace: '    if (this.props.adminListings && me && me.state === "active" && (me.roles || []).some((r) => r === "staff" || r === "admin")) this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] }));\n'
    + '    this.loadAreas(this.state.market);\n',
  count: 1
};

const A24_18: Amendment = {
  id: 'A24.18', ...NS,
  find: '  setMarket = (e) => {\n    const v = e && e.target ? e.target.value : e;\n',
  replace: '  setMarket = (e) => {\n    const v = e && e.target ? e.target.value : e;\n    this.loadAreas(v);\n',
  count: 1
};

/** A24.19-A24.20 -- the CENSUS TRACT ruling (controller, 2026-09-12). Both are CHAINED entries in
 *  the A21.5c / A12.7 shape: each `find` is a string an EARLIER A24 amendment produced, so neither
 *  occurs in the pristine bundle and both must run after the entry they read.
 *
 *  A24.19 reads A24.2's own output and A24.20 reads A24.7's. The ruling: the canonical granular
 *  unit is the Census tract (summary level 140), nationwide. Tracts are designed as neighbourhood
 *  approximations and ACS publishes the variable at tract level; calling a ZIP area a
 *  neighbourhood is a named prohibition. `growth` and `econ` are UNCHANGED here and that is the
 *  point -- growth cannot follow the tract (the 2010->2020 boundary change, plan D12), so each
 *  layer keeps its own label and the legend prints the geography the figure is really measured at.
 *  `tests/census/test_design_shading_labels.py` pins this half against `app.api.market.SHADING`,
 *  so the design and the route cannot disagree about a geography. */
const TRACT = { date: '2026-09-12', ruling: 'The canonical granular unit is the Census tract (summary level 140), nationwide. Not ZCTA. Census tract is an acceptable authoritative small-area geography, tracts are designed as neighbourhood approximations, and ACS publishes the needed variables at tract level. Calling a ZIP area a neighbourhood is a named prohibition. Exception, which must be labelled and never fabricated: population_growth_pct stays at place-or-county.' };

const A24_19: Amendment = {
  id: 'A24.19', ...TRACT,
  find: 'const AREA_LEVEL = { income: "860", growth: "160", econ: "050" };\n'
    + 'const AREA_LABEL = { income: "ZIP Code Tabulation Area", growth: "Place (city/town)", econ: "County" };\n',
  replace: 'const AREA_LEVEL = { income: "140", growth: "160", econ: "050" };\n'
    + 'const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County" };\n',
  count: 1
};

const A24_20: Amendment = {
  id: 'A24.20', ...TRACT,
  find: 'Community areas are Census ZIP Code Tabulation Areas (2023 boundaries); figures describe the area, not the practice.',
  replace: 'Community areas are Census tracts (2023 boundaries); figures describe the area, not the practice. Population growth is measured for the surrounding city or county, not the tract.',
  count: 1
};

/** A24.21-A24.23 -- the VIEWPORT BBOX (controller, 2026-09-12). `GET /api/markets/{cbsa}/boundaries`
 *  has taken a `bbox` since Task 9 and A24.15's loader never sent one, so every request was for the
 *  whole metro envelope. At Census-tract scale that is 5,935 tracts in New York where the Browse
 *  map's own zoom holds 3,706. When this amendment was written the caps were still the ZCTA era's
 *  (`MAX_FEATURES = 4000`) and the metro request was refused outright; they were re-measured for
 *  tracts the same day -- 12,000 features, 6,000,000 bytes -- so it is served now, and what the box
 *  buys is the size of the ANSWER rather than the difference between a map and a blank one. The
 *  RULING below is the controller's own words of the day and is left exactly as it was given.
 *
 *  All three are CHAINED, the A21.5c / A24.19 shape: A24.21 reads A24.15's whole output, A24.22
 *  reads A24.17's line and A24.23 reads A13.5's, so none occurs in the pristine bundle.
 *
 *  Four properties, each because the alternative puts a false or an empty map on screen:
 *
 *  1. `viewport()` is BOTH the box that is sent and the token an arriving answer is checked
 *     against -- one value read once, so the guard cannot drift from the request. A24.15's market
 *     guard is extended, not replaced: an answer is drawn only if the member is still on the same
 *     metro AND the same box.
 *  2. A pan KEEPS the polygons up while the new box loads (`keep`). A24.15's clear exists so one
 *     city is never drawn over another; a pan is the same city, and clearing would blank the map
 *     on every drag. A metro change still clears, because that is a different city.
 *  3. It asks for NOTHING until a map has published a box. `componentDidMount` runs before the map
 *     component has finished mounting Leaflet, so without this the boot would fire exactly the
 *     doomed whole-metro request this amendment exists to stop.
 *  4. An adapter with NO `viewport` -- the reference, the Claude Design preview, any older build --
 *     takes the old path unchanged, whole-metro and all, because both new terms are guarded on the
 *     method's presence. */
const BBOX = { date: '2026-09-12', ruling: 'The adapter sends the map\'s current viewport as bbox, re-fetches when the viewport changes enough to matter, and draws what the API answers for that box. New York whole-metro is 5,935 tracts and 422s; the viewport is 3,706 and is served.' };

const A24_21: Amendment = {
  id: 'A24.21', ...BBOX,
  find: '  loadAreas(market) {\n'
    + '    if (!this.props.market) return;\n'
    + '    const asked = market || "Austin, TX";\n'
    + '    const mine = () => (this.state.market || "Austin, TX") === asked;\n'
    + '    this.setState({ mdAreas: null });\n'
    + '    this.props.market.boundaries(asked).then(\n'
    + '      (areas) => { if (mine()) this.setState({ mdAreas: areas }); },\n'
    + '      () => { if (mine()) this.setState({ mdAreas: {} }); }\n'
    + '    );\n'
    + '  }\n',
  replace: '  loadAreas(market, keep) {\n'
    + '    if (!this.props.market) return;\n'
    + '    const asked = market || "Austin, TX";\n'
    + '    const at = this.props.market.viewport ? this.props.market.viewport() : null;\n'
    + '    if (!keep) this.setState({ mdAreas: null });\n'
    + '    if (this.props.market.viewport && at === null) return;\n'
    + '    const mine = () => (this.state.market || "Austin, TX") === asked && (this.props.market.viewport ? this.props.market.viewport() : null) === at;\n'
    + '    this.props.market.boundaries(asked, at).then(\n'
    + '      (areas) => { if (mine()) this.setState({ mdAreas: areas }); },\n'
    + '      () => { if (mine()) this.setState({ mdAreas: {} }); }\n'
    + '    );\n'
    + '  }\n',
  count: 1
};

const A24_22: Amendment = {
  id: 'A24.22', ...BBOX,
  find: '    this.loadAreas(this.state.market);\n',
  replace: '    this.loadAreas(this.state.market);\n'
    + '    if (this.props.market && this.props.market.onViewport) this._offViewport = this.props.market.onViewport(() => this.loadAreas(this.state.market, true));\n',
  count: 1
};

const A24_23: Amendment = {
  id: 'A24.23', ...BBOX,
  find: '    if (this._onDocOut) document.removeEventListener("focusout", this._onDocOut, true);\n  }\n',
  replace: '    if (this._onDocOut) document.removeEventListener("focusout", this._onDocOut, true);\n'
    + '    if (this._offViewport) this._offViewport();\n  }\n',
  count: 1
};

/** A24.24-A24.32 -- the FOUR LAYERS THAT PAINTED NOTHING (D-L1, 2026-09-12). The stakeholder saw
 *  median income and population growth render as real Census geography for the first time and
 *  said so; in the same message he reported that households, average practice payroll, veterinary
 *  competition and pet ownership (estimated) render NOTHING. Payroll was a backend defect (the CBP
 *  noise flag read as a withholding flag, all 392 counties suppressed); the other three had no
 *  writer row, no `SHADING` entry and no `AREA_LEVEL` entry, so the route answered
 *  `422 BAD_LAYER` and the app -- which draws what the API answered or nothing at all -- correctly
 *  drew nothing.
 *
 *  Every entry below is CHAINED on an earlier A24 entry's own output, so none occurs in the
 *  pristine bundle and each must run after the entry it reads.
 *
 *  THE CLASS BREAKS ARE MEASURED, NOT CHOSEN, and they are a SECOND table rather than a re-cut of
 *  the design's own (A24.25). `VALUE_LAYERS` classes the figures the design's community cards
 *  carry -- a city's households, a metro's establishment count -- and a polygon carries the same
 *  metric at a different GEOGRAPHY, where the same numbers mean something else: 1,480 households
 *  is an ordinary Census tract and an implausibly small city. Income, growth and payroll are
 *  scale-invariant (a median, a percentage, a per-establishment figure) and keep one table. The
 *  three COUNT layers get their own, measured over the distribution the map actually paints:
 *
 *    households / pets -- ACS 2019-2023 `B11001_001E`, the Census Bureau's own keyless
 *    table-based summary file, every Census tract in the United States: 85,381 tracts carry the
 *    variable. p25 1,054, p50 1,446, p75 1,897, max 10,466. The design's city-scale
 *    `[10000, 25000, 45000]` put **100.0 %** of them in ONE class -- the whole map one colour,
 *    which is the complaint this entire stream answers. `[1000, 1500, 2000]` takes
 *    21.9 / 31.4 / 26.0 / 20.7 %. Pets is that distribution times the design's own 0.57
 *    (p25 601, p50 824, p75 1,081), so `[600, 850, 1100]` takes 24.9 / 27.9 / 23.7 / 23.5 %.
 *
 *    competition -- ZIP Code Business Patterns 2022, NAICS 541940, the Census Bureau's own
 *    keyless `zbp22detail` file, every ZIP area in the United States: 4,720 carry a published
 *    count, min 3 (the file publishes no smaller cell), p50 4, p75 6, p90 8, p95 10, max 44. The
 *    design's `[3, 6, 10]` leaves its FIRST class **empty** and puts 73.1 % in one; `[4, 6, 10]`
 *    takes 37.0 / 36.1 / 21.4 / 5.5 %. The first bucket is labelled "1-3" rather than "3",
 *    because the label states the class's RANGE and must stay true if a smaller count is ever
 *    published.
 *
 *  Because `VALUE_LAYERS` itself is untouched, the snapshot strip's cards, the Compare rows, the
 *  graduated symbols and the docked panel keep their own community-scale classification and their
 *  own pixels, and the legend over a tract map reads tract-scale bands. */
const LAYERS_RULING = {
  date: '2026-09-12',
  ruling: 'households, average practice payroll, veterinary competition and pet ownership (estimated) render NOTHING (John, 2026-09-12, on QA). Each layer shades at the geography its figure is honest at and the legend names it; the estimate is identified as an estimate; the ZIP Code Tabulation Area is used for ZIP Code Business Patterns alone, because it is that dataset’s own authoritative geography.'
};

const A24_24: Amendment = {
  id: 'A24.24', ...LAYERS_RULING,
  find: 'const FILL_KEYS = ["income", "growth", "econ"];\n'
    + '// A24 (D-C35): each fill layer draws at the geography its figure is honest at, and the\n'
    + '// legend names it. `pets`, `households` and `competition` stay graduated symbols at the\n'
    + '// listing point - city-scale class breaks on small areas produce a picture with no\n'
    + '// information, and `households` first `< 10K` bucket would swallow essentially every one.\n'
    + 'const AREA_LEVEL = { income: "140", growth: "160", econ: "050" };\n'
    + 'const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County" };\n',
  replace: 'const FILL_KEYS = ["income", "growth", "econ", "households", "pets", "competition"];\n'
    + '// A24 (D-C35): each fill layer draws at the geography its figure is honest at, and the\n'
    + '// legend names it. `households` and `pets` joined income at the tract on 2026-09-12 and\n'
    + '// `competition` at the ZCTA (D-L1): they were graduated symbols at the listing point on the\n'
    + '// grounds that city-scale class breaks on small areas produce a picture with no information,\n'
    + '// which was true of the BREAKS and not of the geography - `AREA_LAYERS` below cuts them at\n'
    + '// the scale the map paints. `competition` is the one ZIP-area layer, and it is honest there\n'
    + '// rather than approximate: ZIP Code Business Patterns is published per ZIP code and exists\n'
    + '// at no other geography, so the ZCTA is where it was measured.\n'
    + 'const AREA_LEVEL = { income: "140", growth: "160", econ: "050", households: "140", pets: "140", competition: "860" };\n'
    + 'const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County", households: "Census tract", pets: "Census tract", competition: "ZIP Code Tabulation Area" };\n',
  count: 1
};

const A24_25: Amendment = {
  id: 'A24.25', ...LAYERS_RULING,
  find: 'const NO_DATA_FILL = "#e6e6e6";\nconst NO_DATA_LABEL = "No data";\n',
  replace: 'const NO_DATA_FILL = "#e6e6e6";\nconst NO_DATA_LABEL = "No data";\n'
    + '// A24 (D-L1): the CHOROPLETH\'s own class breaks, for the three layers whose figure is a\n'
    + '// COUNT and therefore means something different at a different geography. `VALUE_LAYERS`\n'
    + '// classes what the community cards carry (a city\'s households); these class what the map\n'
    + '// paints (a tract\'s). Measured over every US tract and every US ZIP area, not over Austin:\n'
    + '// households p25/p50/p75 = 1,054 / 1,446 / 1,897 across 85,381 tracts, pets the same times\n'
    + '// 0.57, competition p50/p75/p90 = 4 / 6 / 8 across 4,720 ZIP areas carrying a count. The\n'
    + '// design\'s own breaks put 100.0 % of tracts and 73.1 % of ZIP areas into ONE class.\n'
    + '// Income, growth and payroll are scale-invariant and are deliberately absent.\n'
    + 'const AREA_LAYERS = {\n'
    + '  households: { buckets: ["< 1,000", "1,000–1,500", "1,500–2,000", "> 2,000"], stops: [1000, 1500, 2000] },\n'
    + '  pets: { buckets: ["< 600", "600–850", "850–1,100", "> 1,100"], stops: [600, 850, 1100] },\n'
    + '  competition: { buckets: ["1–3", "4–5", "6–9", "10+"], stops: [4, 6, 10] }\n'
    + '};\n',
  count: 1
};

const A24_26: Amendment = {
  id: 'A24.26', ...LAYERS_RULING,
  find: '  bucket(metric, v) {\n    const cfg = VALUE_LAYERS[metric];\n',
  replace: '  bucket(metric, v, area) {\n'
    + '    // `area` asks for the CHOROPLETH\'s breaks. Everything else on the screen classes a\n'
    + '    // community-scale figure and must keep asking for the design\'s own (A24.25).\n'
    + '    const cfg = (area && AREA_LAYERS[metric]) || VALUE_LAYERS[metric];\n',
  count: 1
};

const A24_27: Amendment = {
  id: 'A24.27', ...LAYERS_RULING,
  find: '        const b = shown ? this.bucket(layer, p.value) : null;\n',
  replace: '        const b = shown ? this.bucket(layer, p.value, true) : null;\n',
  count: 1
};

const A24_28: Amendment = {
  id: 'A24.28', ...LAYERS_RULING,
  find: '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: cfg.buckets[i]\n'
    + '              })).concat(FILL_KEYS.indexOf(valueLayer) > -1\n',
  replace: '            ? ramp(valueLayer).map((c, i) => ({\n'
    + '                style: "flex: 1; height: 9px; background: " + c + ";",\n'
    + '                label: ((AREA_LAYERS[valueLayer] || cfg).buckets)[i]\n'
    + '              })).concat(FILL_KEYS.indexOf(valueLayer) > -1\n',
  count: 1
};

const A24_29: Amendment = {
  id: 'A24.29', ...LAYERS_RULING,
  find: '    return v >= 1000 ? Math.round(v / 1000) + "K" : String(v);\n',
  replace: '    // Abbreviated from ten thousand, not from one: a Census tract holds about 1,400\n'
    + '    // households and "1K" is the same label for 1,000 and for 1,499. `toLocaleString` is\n'
    + '    // the design\'s own separator, the one `p.sqft` already uses.\n'
    + '    return v >= 10000 ? Math.round(v / 1000) + "K" : Math.round(v).toLocaleString();\n',
  count: 1
};

const A24_30a: Amendment = {
  id: 'A24.30a', ...LAYERS_RULING,
  find: '      \'<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">\' + (shown ? this.fmtMetric(layer, p.value) : NO_DATA_LABEL) + "</div>" +\n',
  replace: '      \'<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">\' + (shown ? this.fmtMetric(layer, p.value) + (layer === "competition" ? " veterinary practices" : "") : NO_DATA_LABEL) + "</div>" +\n',
  count: 1
};

const A24_30b: Amendment = {
  id: 'A24.30b', ...LAYERS_RULING,
  find: '          : layer === "econ"\n'
    + '            ? "Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies."\n'
    + '            : "");\n',
  replace: '          : layer === "econ"\n'
    + '            ? "Payroll per establishment (NAICS 541940), county level. County Business Patterns is a census of establishments, not a sample; no margin of error applies."\n'
    + '            : layer === "competition"\n'
    + '              ? "within this " + AREA_LABEL[layer] + ". ZIP Code Business Patterns is published per ZIP code, which is this dataset’s own authoritative geography. Establishments include corporate-owned and specialty locations."\n'
    + '              : layer === "pets"\n'
    + '                ? "Modelled estimate: households × 0.57. Not an observed count."\n'
    + '                : "");\n',
  count: 1
};

const A24_31a: Amendment = {
  id: 'A24.31a', ...LAYERS_RULING,
  find: '    const selComm = sel ? comms.filter((c) => c.id === sel.id)[0] : null;\n',
  replace: '    const selComm = sel ? comms.filter((c) => c.id === sel.id)[0] : null;\n'
    + '    // Hoisted out of the returned object so the LEGEND can see how many polygons were\n'
    + '    // actually drawn (A24.32). One call, one collection, no second classification pass.\n'
    + '    const areaFc = this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer);\n',
  count: 1
};

const A24_31b: Amendment = {
  id: 'A24.31b', ...LAYERS_RULING,
  find: '      areas: this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer),\n',
  replace: '      areas: areaFc,\n',
  count: 1
};

/** A24.32 -- the legend must not claim a ramp the map does not carry (whole-branch review of
 *  `feat/tract`, finding 5). A practice in a metro that is in no CBSA -- Bozeman, deliberately --
 *  reaches the metro picker, because the client builds `MARKETS` from the listings’ own market
 *  strings while `/api/markets` INNER JOINs a `310` geography. `boundaries()` then rejects, the
 *  loader’s own rejection arm empties `mdAreas`, and the map draws no polygons at all -- while
 *  the legend went on printing the full colour ramp, the "No data" swatch and the geography name
 *  over an unshaded map, which reads as "every area here is unmeasured" rather than "nothing was
 *  drawn". No new copy and no new state: `hasRamp` and `hasGeo` already exist and already gate
 *  exactly the two blocks that would be lying. */
const A24_32: Amendment = {
  id: 'A24.32', ...LAYERS_RULING,
  find: '          hasRamp: !!valueLayer,\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1,\n',
  replace: '          hasRamp: !!valueLayer && areaFc.features.length > 0,\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1 && areaFc.features.length > 0,\n',
  count: 1
};

/** A24.33-A24.41 -- FIX ROUND 1 on the layers branch (review of e984c85..304b80f, 2026-09-12).
 *  Every entry is CHAINED on an earlier A24 entry's output. The findings, in the reviewer's own
 *  order, and what each entry does about it. */
const FIX1 = {
  date: '2026-09-12',
  ruling: 'Fix round 1 on the four-layer change (review of e984c85..304b80f, 2026-09-12): the shaded layers must draw the figures they name. `areaSet` learns the design’s own field aliases; the competition catalogue names the dataset, vintage and geography the route actually serves; a ZIP area the Census withheld under its three-establishment publication rule is SUPPRESSED with its own reason and says so, and no legend class promises a count the data cannot hold; a metric shading the map does not also draw its own symbols; and the legend stays mounted while a metro loads.'
};

/** A24.33 -- Important 1, and the defect of the round. `areaSet` read `best[layer]` while
 *  `communities()` names the field `hh` for households and `vets` for competition; the design's
 *  three OTHER readers of the same objects alias them (`marketVals`'s community values, the
 *  Compare rows, the strip cards). So on the reference path -- and in the app's own e2e oracle,
 *  which is derived from `areaSet` -- `households` drew 503 of 503 polygons in the no-data grey
 *  UNDER A FULL FOUR-CLASS RAMP that named a geography: a legend claiming a scale nothing on the
 *  map is drawn on, which is the exact statement A24.32 was written to prevent. The alias is the
 *  one `marketVals` already uses, verbatim, so there is one spelling of it and not a fourth. */
const A24_33: Amendment = {
  id: 'A24.33', ...FIX1,
  find: '        const raw = best ? best[layer] : undefined;\n',
  replace: '        // The design\'s own alias, verbatim from `marketVals`: `communities()` names\n'
    + '        // these two fields `hh` and `vets`, and a fill layer reads the same objects the\n'
    + '        // symbols and the Compare rows do.\n'
    + '        const raw = best ? (layer === "households" ? best.hh : layer === "competition" ? best.vets : best[layer]) : undefined;\n',
  count: 1
};

/** A24.34 -- Important 2. `competition` is served `source_dataset: "zbp"`, `value_vintage:
 *  "2022"`, `geo_label: "ZIP Code Tabulation Area"`, and its catalogue entry named County
 *  Business Patterns, a 2023 release and "community level" -- so `areaTip` printed A24.30b's ZBP
 *  sentence and this CBP source line in the same tooltip. A sentence a release makes false is
 *  corrected in that release (A27.4/A27.5's own precedent); none of this is new copy. */
const A24_34: Amendment = {
  id: 'A24.34', ...FIX1,
  find: '    sub: "Veterinary establishments · CBP, NAICS 541940",\n'
    + '    updated: "Updated: CBP 2023 release (Nov 2024)",\n'
    + '    source: "U.S. Census County Business Patterns (2023), NAICS 541940 · community level",\n',
  replace: '    sub: "Veterinary establishments · ZIP Code Business Patterns, NAICS 541940",\n'
    + '    updated: "Updated: ZIP Code Business Patterns 2022",\n'
    + '    source: "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940 · ZIP Code Tabulation Area",\n',
  count: 1
};

/** A24.35 / A24.36 -- Important 2's other half. Both layers shade the CENSUS TRACT and both
 *  source lines said "community level"; income's has said it since before the tract ruling and is
 *  corrected here rather than left as the one line on the card that names no geography at all. */
const A24_35: Amendment = {
  id: 'A24.35', ...FIX1,
  find: '    source: "U.S. Census ACS 5-year estimates (2023) · community level",\n'
    + '    means: "The count of occupied housing units in each community',
  replace: '    source: "U.S. Census ACS 5-year estimates (2023) · Census tract",\n'
    + '    means: "The count of occupied housing units in each community',
  count: 1
};

const A24_36: Amendment = {
  id: 'A24.36', ...FIX1,
  find: '    source: "U.S. Census ACS 5-year estimates (2023) · community level",\n'
    + '    means: "Higher-income areas may support stronger demand',
  replace: '    source: "U.S. Census ACS 5-year estimates (2023) · Census tract",\n'
    + '    means: "Higher-income areas may support stronger demand',
  count: 1
};

/** A24.37 -- Important 3's legend half, CHAINED on A24.25. The Census publishes ZIP-level
 *  INDUSTRY detail only where a category has three or more establishments ("if a given NAICS
 *  category has less than three business establishments, the number of establishments won't be
 *  reported for that category, but they will be included in the sum total"), so the served
 *  distribution has a FLOOR of 3 -- measured on QA: `zbp_industry` min 3, zero rows below it, and
 *  `geo_metric.establishments` min 3 across 4,719 ZCTAs. A first class labelled "1-3" therefore
 *  promises two counts the data cannot hold; it can only ever contain a 3, and it says so. The
 *  stops do not move: re-measured on the served distribution (`scripts/measure_area_breaks.py`),
 *  `[4, 6, 10]` takes 37.0 / 36.1 / 21.4 / 5.5 % of it. */
const A24_37: Amendment = {
  id: 'A24.37', ...FIX1,
  find: '  competition: { buckets: ["1–3", "4–5", "6–9", "10+"], stops: [4, 6, 10] }\n',
  replace: '  competition: { buckets: ["3", "4–5", "6–9", "10+"], stops: [4, 6, 10] }\n',
  count: 1
};

/** A24.38 -- Important 3's honesty half, CHAINED on A24.3. `geo_metric` now tells the three ZCTA
 *  states apart (`app/census/geo_metric.py`): a count, a ZIP area the Census WITHHELD under its
 *  own three-establishment rule (`suppressed: true, suppress_reason: "source_threshold"`), and a
 *  ZIP area ZIP Code Business Patterns does not cover at all. The design's `absent` line already
 *  branches on `suppress_reason`, so the third state needs one more arm and no new legend, no new
 *  colour and no new control: the polygon stays in the design's own no-data grey and the tip says
 *  which of the three it is. Before this, 393 of Dallas's 535 ZCTAs -- 73 % of the map -- said
 *  "No data for this area" over cells the Census had deliberately withheld. */
const A24_38: Amendment = {
  id: 'A24.38', ...FIX1,
  find: '      ? (p.suppress_reason === "source_flag" ? "Not published for this county" : "Estimate too imprecise to show at this geography")\n',
  replace: '      ? (p.suppress_reason === "source_flag" ? "Not published for this county"\n'
    + '        : p.suppress_reason === "source_threshold" ? "Fewer than three veterinary establishments here. The Census does not publish a ZIP-level count for a category with fewer than three establishments, though they are counted in its all-industry total."\n'
    + '        : "Estimate too imprecise to show at this geography")\n',
  count: 1
};

/** A24.39 -- Minor 5, CHAINED on A24.30b. The competition margin line was written as a lowercase
 *  fragment meant to be read as the continuation of the value line above it ("7 veterinary
 *  practices" / "within this ZIP Code Tabulation Area."), but it is its own `<div>` in its own
 *  declarations, so it read as a sentence beginning in the middle. It is a sentence now; the
 *  value line above keeps the noun it already names. */
const A24_39: Amendment = {
  id: 'A24.39', ...FIX1,
  find: '              ? "within this " + AREA_LABEL[layer] + ". ZIP Code Business Patterns is published per ZIP code, which is this dataset’s own authoritative geography. Establishments include corporate-owned and specialty locations."\n',
  replace: '              ? "Counted within this " + AREA_LABEL[layer] + ". ZIP Code Business Patterns is published per ZIP code, which is this dataset’s own authoritative geography. Establishments include corporate-owned and specialty locations."\n',
  count: 1
};

/** A24.40 -- Minor 4. `SYMBOL_KEYS` and `FILL_KEYS` now overlap completely for the three count
 *  layers, and `competition`'s symbols default ON -- so choosing Veterinary competition drew a
 *  ZCTA choropleth classed on `AREA_LAYERS` AND graduated symbols at the listing points classed
 *  on `VALUE_LAYERS`, two different scales for one metric under one legend that describes only
 *  the first. A metric that is SHADING the map does not also draw its own symbols. The design's
 *  own `layers` toggles are untouched: this narrows what is drawn for the active layer, it does
 *  not change what a member has turned on, and turning the fill to another layer brings the
 *  symbols straight back. */
const A24_40: Amendment = {
  id: 'A24.40', ...FIX1,
  find: '    const activeSymbols = SYMBOL_KEYS.filter(\n'
    + '      (k) => layers[k] && !(s.mdOff || {})[k === "competition" ? "vets" : k]\n'
    + '    );\n',
  replace: '    const activeSymbols = SYMBOL_KEYS.filter(\n'
    + '      (k) => k !== valueLayer && layers[k] && !(s.mdOff || {})[k === "competition" ? "vets" : k]\n'
    + '    );\n',
  count: 1
};

/** A24.41 -- Minor 7, CHAINED on A24.32. A24.32 unmounts the ramp and the geography line when no
 *  polygon was drawn, which is right for a metro the API cannot answer for and wrong for the
 *  moment between asking and being answered: `loadAreas` clears `mdAreas` on a METRO CHANGE, so
 *  the legend vanished and came back on every change of market. A pan already keeps it (A24.21's
 *  `keep`), and a legend that disappears and returns is a flicker rather than a state. `mdAreas
 *  === null` is the design's own "nothing has been loaded" value, distinct from `{}` ("the API
 *  answered, and it held nothing"), which is exactly the distinction this needs. */
const A24_41: Amendment = {
  id: 'A24.41', ...FIX1,
  find: '          hasRamp: !!valueLayer && areaFc.features.length > 0,\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1 && areaFc.features.length > 0,\n',
  replace: '          hasRamp: !!valueLayer && (areaFc.features.length > 0 || areasPending),\n'
    + '          hasGeo: FILL_KEYS.indexOf(valueLayer) > -1 && (areaFc.features.length > 0 || areasPending),\n',
  count: 1
};

/** A24.42 -- A24.41's own term, declared beside the collection it qualifies. It is true only with
 *  an adapter present and only while `mdAreas` is the design's own "nothing loaded yet" null, so
 *  the reference and the Claude Design preview never reach it. */
const A24_42: Amendment = {
  id: 'A24.42', ...FIX1,
  find: '    const areaFc = this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer);\n',
  replace: '    const areaFc = this.areaVals(this.props.market ? ((s.mdAreas || {})[valueLayer] || { type: "FeatureCollection", features: [] }) : this.areaSet(valueLayer), valueLayer);\n'
    + '    // "asked, not yet answered" — A24.41 keeps the legend mounted across it.\n'
    + '    const areasPending = !!this.props.market && s.mdAreas === null;\n',
  count: 1
};

/** A24.43 -- MS1 (ruling `2026-09-05-practice-match-census-data-layer/ruling-market-strip.md`,
 *  recorded and never fixed; re-found on 304b80f, 2026-09-12). The Market snapshot strip showed
 *  Dallas Population growth as "+1.5% metro median" while every Dallas listing's own figure is
 *  "-1.5% since 2018": one screen said the opposite of the other about the same city.
 *
 *  `num` stripped every character but digits and a dot, which loses a leading MINUS and
 *  CONCATENATES whatever number follows the figure -- "-1.5% since 2018" became "1.52018", a
 *  quantity nothing measured, of the wrong sign. `communities()` does not use it for growth (it
 *  parses with `parseFloat` and keeps the sign, A24.3's own note), which is exactly why the docked
 *  panel was right; `stripCards` is the one growth reader that does, and it classes with
 *  `bucket()`, so the lost sign was a wrong number AND a wrong colour -- D-C46 gave the growth
 *  ramp a band below zero precisely so a decline reads as one, and this put a declining metro in a
 *  growth class.
 *
 *  The replacement reads the FIRST number in the string and nothing after it, sign included, with
 *  thousands separators removed: "-1.5% since 2018" -> -1.5, "$101,721" -> 101721, "169,355
 *  households" -> 169355, "1,900 sq ft" -> 1900. The design's zero-for-null contract is kept
 *  deliberately -- `num(null)` and `num("no figure")` are still 0, and A21.1c's guards do not go
 *  through this helper, so nothing that must tell absence from zero asks it.
 *
 *  PIXEL-SAFE: every growth figure in the design's own fixtures is POSITIVE and carries one
 *  decimal, and `stripCards` reads growth as the number `communities()` already parsed, so the
 *  digits before the `%` are unchanged on every approved state; the other `num` readers are fed
 *  fixture strings whose first number is the whole figure ("81,900", "$118,400", "27,600
 *  households"), which this reads identically. */
const A24_43: Amendment = {
  id: 'A24.43',
  date: '2026-09-12',
  ruling: 'MS1: the Market snapshot strip reported a declining metro as growing. `num` dropped a leading minus and concatenated the year that followed the figure, so "-1.5% since 2018" became 1.52018 — the wrong sign and a quantity nothing measured, classed by `bucket` into a growth band. It reads the first number in the string and nothing after it, sign included, and keeps the design’s zero-for-null contract.',
  find: 'const num = (s) => (s == null ? 0 : Number(String(s).replace(/[^0-9.]/g, "")) || 0);\n',
  replace: '// MS1: the FIRST number in the string and nothing after it, sign included. Stripping every\n'
    + '// character but digits and a dot loses a leading minus and glues on whatever number follows\n'
    + '// the figure — "-1.5% since 2018" became "1.52018", which the snapshot strip then reported as\n'
    + '// "+1.5%" and `bucket` classed as growth. Zero for a null or for a string carrying no number\n'
    + '// at all is the design’s own contract and is kept.\n'
    + 'const num = (s) => { const m = s == null ? null : String(s).match(/[-+]?\\d[\\d,]*(?:\\.\\d+)?/); return m ? Number(m[0].replace(/,/g, "")) || 0 : 0; };\n',
  count: 1
};

/** A24.44-A24.52 -- FIX ROUND 2, B and E (2026-09-12). The Market snapshot strip states its OWN
 *  basis instead of borrowing the map's.
 *
 *  Measured on QA: the strip's Households card read "162K metro median · U.S. Census ACS 5-year
 *  estimates (2023) · Census tract". The 162K is the MEDIAN OF THE LISTINGS' OWN five-mile-ring
 *  totals -- `stripCards` reads `comms`, one row per listing -- and a Census tract holds about
 *  1,500 households, so the caption named a geography the number is not measured at. Nothing was
 *  wrong with A24.34-A24.36: they made `LAYER_META.*.source` truthfully name the MAP's geography,
 *  which is exactly right for the legend and exactly wrong for the strip, which borrows the same
 *  string. Ruling D-C50 (Task SNAP, 0.1.22) later makes the strip describe the MAP; until then it
 *  must describe what it IS.
 *
 *  ONE STRING PER FACT. The three layers whose source named the map's geography keep only the
 *  DATASET (`dataset:`), and `metaSource(k, basis)` composes the rest -- the map's geography for
 *  the legend, the tip and the map's own community notes; the practice-area basis for the strip.
 *  `growth` and `econ` describe place and county on BOTH surfaces and keep their wording, which is
 *  why they keep `source` and have no `dataset`; `pets` names no geography at all and keeps its.
 *
 *  The basis is what the API already serves: the listings' own `communityLabel` where every
 *  community in the metro carries the same one ("Within about 5 miles of the practice" on all
 *  twelve Dallas listings), and the design's own "community level" otherwise. The design's
 *  fixtures carry no `communityLabel`, so the reference path renders "community level" -- which
 *  is the string those cards carry today -- and every approved state keeps its pixels except the
 *  footnote sentence, which re-bases `browse-market-strip` alone. */
const FIX2 = {
  date: '2026-09-12',
  ruling: 'D-C50 (interim): the Market snapshot states the basis of its OWN figures — the practice-area label the API serves — rather than borrowing the map legend’s geography, which is false for a median of per-listing ring totals; the footnote is made true for both surfaces; and the threshold tip carries the ruled sentence and nothing else.'
};

/** A24.44 -- the basis has to reach the strip, and it reaches it the way every other figure does:
 *  as a field on the community objects `communities()` builds. One line, beside the fields it
 *  already copies off the listing. */
const A24_44: Amendment = {
  id: 'A24.44', ...FIX2,
  find: '        id: p.id, name: p.area, lat: p.lat, lng: p.lng,\n',
  replace: '        id: p.id, name: p.area, lat: p.lat, lng: p.lng, communityLabel: p.communityLabel,\n',
  count: 1
};

/** A24.45 -- `metaSource(k, basis)`: the ONE composer both surfaces read. A layer that names a
 *  geography carries the dataset alone and has the basis supplied by its caller; a layer whose
 *  source line names no geography at all keeps the sentence it has. */
const A24_45: Amendment = {
  id: 'A24.45', ...FIX2,
  find: '// One catalogue per market layer: what it is, where it comes from, and how to read it.\n',
  replace: '// A24 (D-C50 interim): the source line, composed for the surface that prints it. A layer\n'
    + '// whose line names a GEOGRAPHY carries the dataset alone (`dataset:`) and is given the basis\n'
    + '// by its caller - the map\'s own geography for the legend and the tip, the practice-area label\n'
    + '// for the snapshot strip, whose figures are per-listing and are not measured at either. A\n'
    + '// layer that names no geography (`growth`, `econ`, `pets`) keeps its own `source` sentence,\n'
    + '// which is true on both surfaces, and this returns it unchanged.\n'
    + 'const metaSource = (k, basis) => {\n'
    + '  const m = LAYER_META[k] || {};\n'
    + '  return m.dataset ? m.dataset + " \u00b7 " + basis : (m.source || "");\n'
    + '};\n'
    + '\n'
    + '// One catalogue per market layer: what it is, where it comes from, and how to read it.\n',
  count: 1
};

const A24_46: Amendment = {
  id: 'A24.46', ...FIX2,
  find: '    source: "U.S. Census ACS 5-year estimates (2023) \u00b7 Census tract",\n'
    + '    means: "Higher-income areas may support stronger demand',
  replace: '    dataset: "U.S. Census ACS 5-year estimates (2023)",\n'
    + '    means: "Higher-income areas may support stronger demand',
  count: 1
};

const A24_47: Amendment = {
  id: 'A24.47', ...FIX2,
  find: '    source: "U.S. Census ACS 5-year estimates (2023) \u00b7 Census tract",\n'
    + '    means: "The count of occupied housing units in each community',
  replace: '    dataset: "U.S. Census ACS 5-year estimates (2023)",\n'
    + '    means: "The count of occupied housing units in each community',
  count: 1
};

const A24_48: Amendment = {
  id: 'A24.48', ...FIX2,
  find: '    source: "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940 \u00b7 ZIP Code Tabulation Area",\n',
  replace: '    dataset: "U.S. Census ZIP Code Business Patterns (2022), NAICS 541940",\n',
  count: 1
};

/** A24.49-A24.51 -- the three MAP surfaces, each asking for the map's own geography. Their output
 *  is byte-identical to what they printed before: `metaSource` composes exactly the string the
 *  literal used to hold. */
const A24_49: Amendment = {
  id: 'A24.49', ...FIX2,
  find: '      \'<div style="font-size:10px;color:#767676;margin-top:5px">\' + (meta.source || "") + "</div>" +\n',
  replace: '      \'<div style="font-size:10px;color:#767676;margin-top:5px">\' + metaSource(layer, AREA_LABEL[layer] || "") + "</div>" +\n',
  count: 1
};

const A24_50: Amendment = {
  id: 'A24.50', ...FIX2,
  find: '          sourceNote: valueLayer ? LAYER_META[valueLayer].source : ""\n',
  replace: '          sourceNote: valueLayer ? metaSource(valueLayer, AREA_LABEL[valueLayer] || "") : ""\n',
  count: 1
};

const A24_51: Amendment = {
  id: 'A24.51', ...FIX2,
  find: '          sourceLine: meta.source ? "Source: " + meta.source : "",\n'
    + '          sourceShort: meta.source ? "Source: " + meta.source.split(" \u00b7 ")[0] : "",\n',
  replace: '          sourceLine: mapSource ? "Source: " + mapSource : "",\n'
    + '          sourceShort: mapSource ? "Source: " + mapSource.split(" \u00b7 ")[0] : "",\n',
  count: 1
};

const A24_52: Amendment = {
  id: 'A24.52', ...FIX2,
  find: '        const cfg = valueLayer ? VALUE_LAYERS[valueLayer] : null;\n',
  replace: '        const cfg = valueLayer ? VALUE_LAYERS[valueLayer] : null;\n'
    + '        const mapSource = valueLayer ? metaSource(valueLayer, AREA_LABEL[valueLayer] || "") : "";\n',
  count: 1
};

/** A24.53 -- the strip itself. The basis is the listings' OWN label where the whole metro agrees
 *  on one, and the design's own "community level" where it does not or where there is none at all
 *  (which is the reference path, and every approved state). */
const A24_53: Amendment = {
  id: 'A24.53', ...FIX2,
  find: '            src: meta.source,\n',
  replace: '            src: metaSource(k, stripBasis),\n',
  count: 1
};

const A24_54: Amendment = {
  id: 'A24.54', ...FIX2,
  find: '      stripCards: ["income", "pets", "competition", "growth", "households", "econ"]\n',
  replace: '      stripCards: (() => {\n'
    + '        // What the snapshot\'s own figures describe: `comms` is one row per LISTING, so the\n'
    + '        // basis is the practice-area label the API serves, and only where the whole metro\n'
    + '        // agrees on one. Otherwise the design\'s own words, which is what the reference path\n'
    + '        // and every approved state renders - the design\'s fixtures carry no label at all.\n'
    + '        const labels = comms.map((c) => c.communityLabel).filter(Boolean);\n'
    + '        const stripBasis = (labels.length === comms.length && labels.length > 0 && labels.every((l) => l === labels[0]))\n'
    + '          ? labels[0] : "community level";\n'
    + '        return ["income", "pets", "competition", "growth", "households", "econ"]\n',
  count: 1
};

/** A24.55 -- the strip's own IIFE closes where the array's `.map` did. */
const A24_55: Amendment = {
  id: 'A24.55', ...FIX2,
  find: '            cardStyle: "display: flex; flex-direction: column; height: 100%; padding: 13px 14px; background: var(--vf-white); border: 1px solid " +\n'
    + '              (on ? "var(--vf-accent)" : "#e6e6e6") + "; border-radius: 8px;"\n'
    + '          };\n'
    + '        })\n',
  replace: '            cardStyle: "display: flex; flex-direction: column; height: 100%; padding: 13px 14px; background: var(--vf-white); border: 1px solid " +\n'
    + '              (on ? "var(--vf-accent)" : "#e6e6e6") + "; border-radius: 8px;"\n'
    + '          };\n'
    + '        });\n'
    + '      })()\n',
  count: 1
};

/** A24.56 -- the footnote, true for BOTH surfaces. A24.20's FIRST sentence describes the map alone
 *  and sits under the strip, whose figures are per-practice, so it is the one that is rewritten.
 *  CHAINED on A24.20.
 *
 *  Its SECOND sentence -- "Population growth is measured for the surrounding city or county, not
 *  the tract." -- is restored here byte for byte (fix round 3, the re-review's Important). The
 *  first draft's `find` reached one sentence too far and took it out of the product, while
 *  `CLAUDE.md`'s A24.20 narrative went on asserting it was there. It is exactly the fact the
 *  snapshot cannot state for itself: growth is the one layer whose card still reads "· community
 *  level", because its basis is place-or-county on both surfaces and neither the map's geography
 *  nor the practice-area label describes it.
 *
 *  The new sentence also stops at "describe the area around each practice": the words that
 *  followed it -- "not the practice itself" -- are the paragraph's own opening clause, three
 *  sentences earlier. */
const A24_56: Amendment = {
  id: 'A24.56', ...FIX2,
  find: 'Community areas are Census tracts (2023 boundaries); figures describe the area, not the practice. Population growth is measured for the surrounding city or county, not the tract.',
  replace: 'The map shades Census tracts, places, counties or ZIP Code Tabulation Areas, as each layer’s legend names; the snapshot’s figures describe the area around each practice. Population growth is measured for the surrounding city or county, not the tract.',
  count: 1
};

/** A24.57 -- fix round 2, E. The ruling was ONE sentence, `app.api.market.THRESHOLD_RULE`, and no
 *  other new copy; A24.38 shipped a lead-in in front of it. The design's own headline above the
 *  line already says which layer and which polygon this is. CHAINED on A24.38. */
const A24_57: Amendment = {
  id: 'A24.57', ...FIX2,
  find: '        : p.suppress_reason === "source_threshold" ? "Fewer than three veterinary establishments here. The Census does not publish',
  replace: '        : p.suppress_reason === "source_threshold" ? "The Census does not publish',
  count: 1
};

/** A24.58 / A24.59 -- FIX ROUND 2, C and D (2026-09-12, found by the re-review of round 1).
 *
 *  C: `communities()` carries its OWN growth parser, and it had the same trap A24.43 took out of
 *  `num` -- stripping everything but digits, a dot and a minus leaves the YEAR glued to the
 *  figure, so "+14.2% since 2015" parsed as 14.22015 and "-1.5% since 2018" as -1.52018. Harmless
 *  today only because `toFixed(1)` rounds it away on the one surface that prints it and no fixture
 *  sits on a class boundary; it is still a number nothing measured, and the same defect in a
 *  second place is how the first one came back. One helper, two readers: this parses with
 *  `num()` itself. The sign survives because `num` keeps it (A24.43), which is the whole reason
 *  `communities()` had a parser of its own in the first place.
 *
 *  D: the comment above `areaSet` justified NOT using `num()` by saying `num(-5.1)` is `5.1`.
 *  A24.43 made that false. What still holds is the other half of the reason, so that is what it
 *  says now. */
const FIX2CD = {
  date: '2026-09-12',
  ruling: 'The design has one number parser, not two: `communities()` parsed a growth figure with a second regex that glued the trailing year onto the digits ("+14.2% since 2015" → 14.22015), and the comment justifying a third path cited behaviour A24.43 had already removed.'
};

const A24_58: Amendment = {
  id: 'A24.58', ...FIX2CD,
  find: '        growth: p.growth != null ? (parseFloat(String(p.growth).replace(/[^0-9.\\-]/g, "")) || 0) : undefined,\n',
  replace: '        growth: p.growth != null ? num(p.growth) : undefined,\n',
  count: 1
};

const A24_59: Amendment = {
  id: 'A24.59', ...FIX2CD,
  find: '  // The value is taken as it comes and is NOT put through `num()`: that helper strips\n'
    + '  // everything but digits and a dot, so `num(-5.1)` is `5.1` - it would turn a declining\n'
    + '  // area into a growing one. Invisible until now, because every one of the design\'s own\n'
    + '  // nine communities grows; A24.13 (D-C46) makes a negative growth a first-class value.\n',
  replace: '  // The value is taken as it comes and is NOT put through `num()`: by this point it is\n'
    + '  // already a number, parsed once by `communities()`, and a second pass would be a second\n'
    + '  // chance to lose something. (The older reason - that `num` stripped a leading minus, so\n'
    + '  // `num(-5.1)` was `5.1` and a decline read as growth - stopped being true with A24.43,\n'
    + '  // which taught it to read the first signed number and nothing after it.)\n',
  count: 1
};

/** A30 — a metro change closes the docked panel (Task PANEL-STALE, 2026-09-12). Root cause read
 *  from QA 0.1.21 (screenshot `screenshots/qa-0121-dallas.png`): with GHI Veterinary Hospital,
 *  Austin, selected and its docked panel open, switching the metro to Dallas left the panel OPEN
 *  with GHI's header ("GHI Veterinary Hospital · $2.76M · Austin, TX") over the FIRST Dallas
 *  listing's community figures — a false statement about a practice, reachable in two clicks and
 *  present on production since 0.1.20 (the design's own behaviour, not a regression this branch
 *  introduced).
 *
 *  `setMarket` (A13.1's class property) sets `market`, `activeId` and `hoverId` but never
 *  `mdSel`. `marketVals` resolves `sel` by id alone (`P.filter((x) => x.id === s.mdSel)[0]`,
 *  market-blind), so it survives a metro change, while `selComm` — filtered to `communities()`
 *  of the NEW market — no longer matches it and `marketPanel` falls back through its own chain
 *  (`selComm || comms[0] || { …all undefined }`, A25.4's own literal being the third link). With
 *  the design's OWN fixtures every other market still carries its own communities (Sacramento's
 *  `c1`-`c4`, Orlando's `o1`-`o4`, Atlanta's `g1`-`g4`), so the arm actually taken is `comms[0]`
 *  — the new market's FIRST community — never A25.4's empty-market literal, which stands in only
 *  when the market has no communities of its own at all and is left untouched here.
 *
 *  The design has no treatment for "the selected practice is not in this metro", and closing is
 *  the only honest state (John's ruling, `task-panel-stale-brief.md`, 2026-09-11): `setMarket`
 *  now clears `mdSel` too, in the same object literal A13.1 wrote. One literal edit. */
const A30: Amendment = {
  id: 'A30', date: '2026-09-12',
  ruling: 'a metro change closes the docked panel, so a practice is never captioned with another metro\'s figures — the design has no treatment for "the selected practice is not in this metro", and closing is the only honest state (Task PANEL-STALE)',
  find: 'market: v, activeId: null, hoverId: null, loading: true, marketMenu: false, marketMenuAt: -1',
  replace: 'market: v, activeId: null, hoverId: null, mdSel: null, loading: true, marketMenu: false, marketMenuAt: -1',
  count: 1
};

/** A32 — a metro change waits for the map to move before it asks (Task ADAPT-STALE-3, 2026-09-12).
 *
 *  Measured on QA `db8bf67` (New York, 1,912 x 1,228): switching metro pulled the whole metro
 *  TWICE — 24 requests, 7.85 MB gzipped. `setMarket` runs BEFORE the map has moved, so the request
 *  A24.18 put there carries the box the OLD metro is still settled on. On a wide screen that box
 *  is past the route's span cap, the adapter's ladder falls back to the whole metro and pays for
 *  it, and `loadAreas`'s own guard then DISCARDS the answer because the settled view is the new
 *  metro's by the time it lands. A24.22's settled-view listener then repeats the whole sequence,
 *  and that second answer is the one drawn. The first was never answerable.
 *
 *  So it is not made. With a viewport-publishing adapter AND a metro whose centre is somewhere
 *  else, `setMarket` marks the shading PENDING — `mdAreas: null`, the state A24.41 keeps the
 *  legend's ramp and geography line for, so nothing flickers — and A24.22's listener asks once,
 *  with the box the new metro has actually settled on.
 *
 *  THE COMPARISON IS THE CENTRE, not the name, and that is deliberate: what decides whether there
 *  is a move to wait for is whether the map is going to move. Re-selecting the metro already
 *  chosen moves nothing, so it keeps the design's immediate load; so does a metro `MARKETS` no
 *  longer holds (`load.ts` prunes it to what the API served, so a stale dropdown row can name one
 *  that is gone — `MARKETS[v]` is then undefined, no comparison is possible, and asking is the
 *  honest answer); and so does every path with no viewport adapter at all — the reference, the
 *  Claude Design preview, and any build whose adapter predates the bbox wiring — where there is no
 *  listener to wait for and waiting would mean never loading.
 *
 *  NOT a guess about which metro a box can see. That was tried (ADAPT-STALE-2, withdrawn): the
 *  boundaries route is bbox-scoped and metro-agnostic — `_BOUNDARY_SQL` filters on level, vintage
 *  and `ST_Intersects(geom, bbox)` and never on the CBSA, so the `cbsa` path segment only picks
 *  the whole-metro fallback box, the cache key and the 404 — which means shading has always
 *  FOLLOWED a member who pans off the selected metro, and a client refusing on geometry would
 *  blank exactly that. This changes the ORDER of the questions and not which ones are answerable.
 *
 *  CHAINED on A24.18, whose `this.loadAreas(v);` line is this entry's whole `find`. One literal
 *  edit. */
const A32: Amendment = {
  id: 'A32', date: '2026-09-12',
  ruling: 'the metro switch waits for the map to move before asking, so the box the previous metro settled on is never sent — and shading still follows a member who pans off the metro, because the route is bbox-scoped (Task ADAPT-STALE-3)',
  find: '    this.loadAreas(v);\n',
  replace: '    // A32: this runs BEFORE the map has moved, so the box the adapter would send is the one\n'
    + '    // the PREVIOUS metro is still settled on -- a question about ground nobody is looking at,\n'
    + '    // whose answer `loadAreas` own guard then discards. With a viewport-publishing adapter and\n'
    + '    // a metro whose centre is somewhere else it is not asked: the shading goes PENDING and the\n'
    + '    // settled-view listener asks once, with the box the new metro actually settles on. The same\n'
    + '    // metro re-selected, a metro MARKETS no longer holds, and every path with no viewport\n'
    + '    // adapter keep the immediate load -- there is no move to wait for.\n'
    + '    const from = MARKETS[this.state.market || "Austin, TX"], to = MARKETS[v];\n'
    + '    const willMove = !!(this.props.market && this.props.market.viewport && from && to\n'
    + '      && (from.center[0] !== to.center[0] || from.center[1] !== to.center[1]));\n'
    + '    if (willMove) this.setState({ mdAreas: null });\n'
    + '    else this.loadAreas(v);\n',
  count: 1
};

const A24_9: Amendment = {
  id: 'A24.9', ...NS, file: 'jsx',
  find: '// GEOMETRY NOTE: the prototype has no ZCTA boundary file, so community areas are\n// approximated as Voronoi cells around each community\'s centroid, clipped to the metro\n// bounding box. Cells are contiguous and non-overlapping, which is what a choropleth\n// requires, but they are NOT real Census boundaries — the UI labels them "approximate\n// community areas". Production must load tiger_cb ZCTA polygons per the Census Data\n// Source Specification and drop this approximation.\n',
  replace: '// GEOMETRY: real Census boundary polygons, handed in as `areas` - one GeoJSON\n'
    + '// FeatureCollection for the active fill layer, each feature already carrying the colour\n'
    + '// `bucket()` chose and the tooltip `areaVals()` built, so this component classes nothing\n'
    + '// and formats nothing. The approximation this file used to draw (grid cells nearest each\n'
    + '// community\'s centroid, clipped to the metro bounding box) is gone: amendment A24, spec\n'
    + '// 2026-09-10, John\'s rulings D-C34-D-C37 of 2026-09-10.\n',
  count: 1
};

/** A24.10 -- `mosaicCells` and its comment, deleted outright under the bundle's own dead-code rule
 *  (spec D8/D12, as A2.3-A2.5 and A13.6-A13.7 applied it): A24.12 removes its only caller. The
 *  `find` is the pristine file's own bytes, printed rather than transcribed -- 26 lines, not the 23
 *  the plan predicted, which is exactly why it is derived and not typed. */
const A24_10: Amendment = {
  id: 'A24.10', ...NS, file: 'jsx',
  find: '// ---- Fine-grained mosaic ---------------------------------------------------\n// Each cell is assigned the class of its nearest community centroid, which yields crisp\n// finite boundaries rather than overlapping discs. This is spatial ASSIGNMENT of existing\n// community data, not interpolation, and not new data — production replaces it with real\n// ZCTA polygons (tiger_cb) per the Census Data Source Specification.\nfunction mosaicCells(sites, bbox, step) {\n  const out = [];\n  for (let lat = bbox.minLat; lat < bbox.maxLat; lat += step) {\n    for (let lng = bbox.minLng; lng < bbox.maxLng; lng += step) {\n      const cLat = lat + step / 2, cLng = lng + step / 2;\n      let best = null, bestD = Infinity;\n      for (let i = 0; i < sites.length; i++) {\n        const s = sites[i];\n        const dLat = s.lat - cLat;\n        const dLng = (s.lng - cLng) * Math.cos((cLat * Math.PI) / 180);\n        const d = dLat * dLat + dLng * dLng;\n        if (d < bestD) { bestD = d; best = s; }\n      }\n      // Drop cells too far from every community rather than shading empty country.\n      if (!best || bestD > 0.016) continue;\n      out.push({ site: best, bounds: [[lat, lng], [lat + step, lng + step]] });\n    }\n  }\n  return out;\n}\n\n',
  replace: '',
  count: 1
};

const A24_11: Amendment = {
  id: 'A24.11', ...NS, file: 'jsx',
  find: '    communities = [],\n',
  replace: '    communities = [],\n    areas = null,\n',
  count: 1
};

/** A24.12 -- the area effect draws `props.areas` through `L.geoJSON` on the SAME shared canvas
 *  renderer the mosaic used, so `leaflet.ts:49-50`'s note ("ONE canvas renderer per mount") outlives
 *  the mosaic. 35 lines replaced; the drive-time ring above them is outside the `find` and is
 *  untouched. */
const A24_12: Amendment = {
  id: 'A24.12', ...NS, file: 'jsx',
  find: '    if (!activeLayer || !communities.length) return;\n\n    const lats = communities.map((c) => c.lat);\n    const lngs = communities.map((c) => c.lng);\n    const bbox = {\n      minLat: Math.min.apply(null, lats) - 0.13,\n      maxLat: Math.max.apply(null, lats) + 0.13,\n      minLng: Math.min.apply(null, lngs) - 0.15,\n      maxLng: Math.max.apply(null, lngs) + 0.15\n    };\n\n    const canvas = L.canvas({ padding: 0.3 });\n    mosaicCells(communities, bbox, 0.0055).forEach(({ site, bounds }) => {\n      const v = site.values[activeLayer];\n      if (v == null) return;\n      L.rectangle(bounds, {\n        renderer: canvas,\n        stroke: false,\n        fillColor: v.color,\n        fillOpacity: 0.5,\n        interactive: true\n      })\n        .bindTooltip(\n          \'<div style="font-family:ProximaNova,Arial,Helvetica,sans-serif;min-width:150px">\' +\n            \'<div style="font-size:12.5px;font-weight:800;color:#003a70">\' + site.name + "</div>" +\n            \'<div style="font-size:11px;color:#494949;margin-top:3px">\' + (site.metricName || "") + "</div>" +\n            \'<div style="font-size:15px;font-weight:800;color:#003a70;margin-top:1px">\' + v.label + "</div>" +\n            \'<div style="font-size:10px;color:#767676;margin-top:5px">\' + (site.sourceNote || "") + "</div>" +\n          "</div>",\n          { sticky: true, className: "rf-tip" }\n        )\n        .on("click", () => onArea && onArea(site.name))\n        .addTo(g);\n    });\n  }, [communities, activeLayer, showDrive, driveCenter && driveCenter[0], status]);\n',
  replace: '    if (!activeLayer || !areas || !areas.features.length) return;\n'
    + '\n'
    + '    const canvas = L.canvas({ padding: 0.3 });\n'
    + '    L.geoJSON(areas, {\n'
    + '      renderer: canvas,\n'
    + '      style: (f) => ({ renderer: canvas, stroke: false, fillColor: f.properties.color, fillOpacity: 0.5, interactive: true }),\n'
    + '      onEachFeature: (f, l) => {\n'
    + '        l.bindTooltip(f.properties.tip, { sticky: true, className: "rf-tip" });\n'
    + '        l.on("click", () => onArea && onArea(f.properties.name));\n'
    + '      }\n'
    + '    }).addTo(g);\n'
    + '  }, [areas, communities, activeLayer, showDrive, driveCenter && driveCenter[0], status]);\n',
  count: 1
};

/** A31 — THE MARKET SNAPSHOT HAS TWO MODES (Task SNAP; ruling D-C50 as revised by the
 *  stakeholder, 2026-09-12, in his own words: "if this needs 2 modes, for the 'AREA' / 'CITY' and
 *  when a user clicks a specific location it must render that facility market information — it
 *  should reflect boldly which is being viewed CITY/AREA vs LOCATION").
 *
 *  WHAT WAS WRONG. The Browse "Market snapshot" strip computed its "metro median" and its seven
 *  bars from `communities()` — one row per LISTING, each hospital's own five-mile ring — while
 *  the map beside it painted Census geography per layer. Audited on QA 304b80f, Dallas: the strip
 *  said Households **162K** where the map's tracts hold 0–5,988, and Competition **41** where its
 *  ZIP areas hold 3–16. The bars were the first seven hospitals in listing order
 *  (`vals.slice(0, 7)`), which is not a distribution at all. In the design's fixture era the map
 *  mosaic was built from those same listing figures, so both agreed by construction; the tract map
 *  broke that identity and nobody noticed, because the two surfaces are read separately.
 *  A24.44–A24.56 (D-C50's INTERIM) made the caption honest about that — "· community level", the
 *  practice-area label — which was the right holding fix and is what this supersedes.
 *
 *  THE TWO MODES.
 *    * **AREA** — nothing selected. Every card is the metro as the MAP paints it: the median and
 *      the distribution over the polygons of that layer's own geography, from the new
 *      `GET /api/markets/{cbsa}/summary`, with the geography and the count named ("metro median ·
 *      1,791 Census tracts").
 *    * **LOCATION** — a practice selected, its docked panel open. Every card is THAT practice's
 *      own community figure — the same `comms` row the panel and the Community Context card
 *      already read — and the bars stay the METRO's distribution with the class the practice
 *      falls in kept at full strength and the rest dimmed, so the two modes read against each
 *      other instead of the card repeating a number the panel already shows. Closing the panel
 *      returns to AREA.
 *  The mode is stated first and in the design's own 800-weight heading, and the two words are
 *  never shown at once.
 *
 *  WHERE THE SUMMARY COMES FROM is A24.14's ternary exactly: the adapter's where there is one,
 *  the design's own `summarySet()` where there is not. That is what keeps the reference and the
 *  app on the same pixels — the oracle answers the app with the design's own distribution
 *  (`frontend/tests/design-summary.mjs`, derived from `summarySet` as `design-boundaries.mjs` is
 *  derived from `areaSet`) — and it is why `browse-market-strip` re-bases and a second state,
 *  `browse-market-strip-location`, is appended: the AREA cards now read the fixture POLYGONS'
 *  median rather than the LISTINGS', which is the whole point of the ruling, and LOCATION mode
 *  had no approved state at all. */
const SNAP = {
  date: '2026-09-12',
  ruling: "if this needs 2 modes, for the 'AREA' / 'CITY' and when a user clicks a specific location it must render that facility market information — it should reflect boldly which is being viewed CITY/AREA vs LOCATION (D-C50 as revised, Task SNAP)"
};

/** A31.1 — the geography's own plural, for the one place on the strip that COUNTS areas. Four
 *  strings, the ruling's own words; a label this table does not carry is printed as it comes,
 *  because a pluralisation RULE would invent "Place (city/town)s". Beside `AREA_LABEL`, whose
 *  keys it answers. */
const A31_1: Amendment = {
  id: 'A31.1', ...SNAP,
  find: 'const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County", households: "Census tract", pets: "Census tract", competition: "ZIP Code Tabulation Area" };\n',
  replace: 'const AREA_LABEL = { income: "Census tract", growth: "Place (city/town)", econ: "County", households: "Census tract", pets: "Census tract", competition: "ZIP Code Tabulation Area" };\n'
    + '// A31 (D-C50 as revised): the same geographies in the plural, for the snapshot strip\'s own\n'
    + '// "metro median · 1,791 Census tracts". A label absent from this table is printed as it\n'
    + '// comes: a pluralisation RULE would produce "Place (city/town)s".\n'
    + 'const AREA_PLURAL = { "Census tract": "Census tracts", "Place (city/town)": "places", "County": "counties", "ZIP Code Tabulation Area": "ZIP areas" };\n',
  count: 1
};

/** A31.2 — the state key, beside A24.16's own `mdAreas`. `null` is "not asked yet"; `{}` is
 *  "asked and refused", which is what the strip's own fallback reads. */
const A31_2: Amendment = {
  id: 'A31.2', ...SNAP,
  find: '    mdAreas: null,\n',
  replace: '    mdAreas: null,\n    mdSummary: null,\n',
  count: 1
};

/** A31.3 — one loader, in `loadAreas`' own shape and beside it. Simpler than its twin in exactly
 *  one way, and deliberately: there is no viewport term, because the summary describes the METRO
 *  and a pan cannot change it — which is also why it is asked for once per metro rather than once
 *  per settled view. The market guard is `loadAreas`' own: an answer for a metro the member has
 *  left is discarded rather than painted over the one they are on. */
const A31_3: Amendment = {
  id: 'A31.3', ...SNAP,
  find: '  loadAreas(market, keep) {\n',
  replace: '  // A31 (D-C50 as revised): the metro-wide summary the snapshot strip\'s AREA mode reads.\n'
    + '  // `loadAreas`\' own shape, minus the viewport: this describes the METRO, so a pan cannot\n'
    + '  // change it and it is asked for once per metro. A refusal empties it rather than leaving\n'
    + '  // the previous metro\'s figures up, and an answer for a metro the member has already left\n'
    + '  // is discarded, which is the same rule for the same reason.\n'
    + '  loadSummary(market) {\n'
    + '    if (!this.props.market || !this.props.market.summary) return;\n'
    + '    const asked = market || "Austin, TX";\n'
    + '    this.setState({ mdSummary: null });\n'
    + '    const mine = () => (this.state.market || "Austin, TX") === asked;\n'
    + '    this.props.market.summary(asked).then(\n'
    + '      (rows) => { if (mine()) this.setState({ mdSummary: rows }); },\n'
    + '      () => { if (mine()) this.setState({ mdSummary: {} }); }\n'
    + '    );\n'
    + '  }\n'
    + '\n'
    + '  loadAreas(market, keep) {\n',
  count: 1
};

/** A31.4 — the boot, one line after A24.17's own. CHAINED on A24.17. */
const A31_4: Amendment = {
  id: 'A31.4', ...SNAP,
  find: '    this.loadAreas(this.state.market);\n',
  replace: '    this.loadAreas(this.state.market);\n    this.loadSummary(this.state.market);\n',
  count: 1
};

/** A31.5 — a metro change. CHAINED on **A32**, not on A24.18: ADAPT-STALE-3 replaced that line
 *  with a branch, so A24.18's own bytes no longer occur in the file and this entry reads A32's
 *  whole output instead.
 *
 *  The summary is asked AT ONCE, outside that branch, and deliberately: A32 waits because the box
 *  `loadAreas` would send is the one the PREVIOUS metro is still settled on, and this question
 *  carries no box at all — it is the METRO's own distribution, which the map moving cannot change.
 *  Waiting would leave the strip on the old metro's figures until the map settled, which is the
 *  stale-caption defect one surface over. Applied to the `setMarket` A13.1 wrote, whose
 *  `mdSel: null` A30 added, so a metro change now closes the panel AND re-reads the new metro's
 *  distribution — which is AREA mode arriving correct. */
const A31_5: Amendment = {
  id: 'A31.5', ...SNAP,
  find: '    // A32: this runs BEFORE the map has moved, so the box the adapter would send is the one\n    // the PREVIOUS metro is still settled on -- a question about ground nobody is looking at,\n    // whose answer `loadAreas` own guard then discards. With a viewport-publishing adapter and\n    // a metro whose centre is somewhere else it is not asked: the shading goes PENDING and the\n    // settled-view listener asks once, with the box the new metro actually settles on. The same\n    // metro re-selected, a metro MARKETS no longer holds, and every path with no viewport\n    // adapter keep the immediate load -- there is no move to wait for.\n    const from = MARKETS[this.state.market || "Austin, TX"], to = MARKETS[v];\n    const willMove = !!(this.props.market && this.props.market.viewport && from && to\n      && (from.center[0] !== to.center[0] || from.center[1] !== to.center[1]));\n    if (willMove) this.setState({ mdAreas: null });\n    else this.loadAreas(v);\n',
  replace: '    // A31: the summary is METRO-wide and carries no bbox, so a metro change asks for it at\n'
    + "    // once -- A32's wait below is about the BOX the map has not moved to yet, and this\n"
    + '    // question does not use one. Waiting would leave the strip on the previous metro.\n'
    + '    this.loadSummary(v);\n'
    + '    // A32: this runs BEFORE the map has moved, so the box the adapter would send is the one\n    // the PREVIOUS metro is still settled on -- a question about ground nobody is looking at,\n    // whose answer `loadAreas` own guard then discards. With a viewport-publishing adapter and\n    // a metro whose centre is somewhere else it is not asked: the shading goes PENDING and the\n    // settled-view listener asks once, with the box the new metro actually settles on. The same\n    // metro re-selected, a metro MARKETS no longer holds, and every path with no viewport\n    // adapter keep the immediate load -- there is no move to wait for.\n    const from = MARKETS[this.state.market || "Austin, TX"], to = MARKETS[v];\n    const willMove = !!(this.props.market && this.props.market.viewport && from && to\n      && (from.center[0] !== to.center[0] || from.center[1] !== to.center[1]));\n    if (willMove) this.setState({ mdAreas: null });\n    else this.loadAreas(v);\n',
  count: 1
};

/** A31.6 — the design's OWN answer to the summary endpoint, and the reference path's only source
 *  of one. It is to `summary()` exactly what `areaSet()` is to `boundaries()`: measured over the
 *  polygons `areaSet` draws, in the endpoint's own shape, so the two targets describe ONE
 *  distribution and `frontend/tests/design-summary.mjs` can hand the app the same numbers the
 *  reference computes for itself.
 *
 *  The quantile is `percentile_cont`'s, which is what the route computes: the fraction lands at
 *  `p * (n - 1)` and the answer is interpolated between the two values it falls between. A
 *  nearest-rank would name five members of the set instead of describing its shape, and the two
 *  sides would then disagree on real data. */
const A31_6: Amendment = {
  id: 'A31.6', ...SNAP,
  find: '  areaSet(layer) {\n',
  replace: '  // A31 (D-C50 as revised): the design\'s own metro summary - one row per shaded layer,\n'
    + '  // measured over the polygons `areaSet` draws, in `GET /api/markets/{cbsa}/summary`\'s own\n'
    + '  // shape. The reference and the Claude Design preview have no adapter, so this is what\n'
    + '  // their snapshot strip describes; the app has one and describes what the API answered.\n'
    + '  // `percentile_cont`\'s own rule, so both sides agree on real data as well as on fixtures:\n'
    + '  // the fraction lands at `p * (n - 1)` and is interpolated between the two values around it.\n'
    + '  summarySet() {\n'
    + '    const out = {};\n'
    + '    FILL_KEYS.forEach((k) => {\n'
    + '      const vals = this.areaSet(k).features.map((f) => f.properties.value).filter((v) => v != null).sort((a, b) => a - b);\n'
    + '      const at = (p) => {\n'
    + '        const i = p * (vals.length - 1);\n'
    + '        const lo = Math.floor(i);\n'
    + '        return vals[lo] + (vals[Math.min(vals.length - 1, lo + 1)] - vals[lo]) * (i - lo);\n'
    + '      };\n'
    + '      const quantiles = vals.length ? [0.1, 0.25, 0.5, 0.75, 0.9].map(at) : null;\n'
    + '      out[k] = {\n'
    + '        layer: k, geo_label: AREA_LABEL[k] || "", with_value: vals.length,\n'
    + '        median: quantiles ? quantiles[2] : null, quantiles: quantiles\n'
    + '      };\n'
    + '    });\n'
    + '    return out;\n'
    + '  }\n'
    + '\n'
    + '  areaSet(layer) {\n',
  count: 1
};

/** A31.7 — the mode, stated first and in the design's own 800-weight heading. Composed from the
 *  docked panel's own Insights heading and the `md.panel.place` sub-line beneath it — the one
 *  heading-and-geography pair the design already has, and the same declaration A27.7 composed the
 *  panel's own sub-line from. No new token, no new size, no new colour.
 *
 *  AREA names the metro in the design's own phrase (`mdSubline`'s "<market> metro"); LOCATION
 *  names the practice through `practiceName`, which is what the docked panel's header reads. The
 *  AREA sub-line is the ruling's own sentence; LOCATION's is the listing's `communityLabel`, and
 *  `hasStripModeSub` is false where there is none — an absent element rather than an empty one,
 *  A27.7's own rule. */
const A31_7: Amendment = {
  id: 'A31.7', ...SNAP,
  find: '      stripOpen: !!s.mdStrip,\n',
  replace: '      stripOpen: !!s.mdStrip,\n'
    + '      // A31 (D-C50 as revised): which of the two modes the six cards are in, first and in\n'
    + '      // the design\'s own display weight. AREA is the metro as the map paints it; LOCATION\n'
    + '      // is the selected practice\'s own community. Both words are never shown at once.\n'
    + '      stripMode: sel ? "LOCATION · " + this.practiceName(sel) : "AREA · " + market + " metro",\n'
    + '      hasStripModeSub: sel ? !!sel.communityLabel : true,\n'
    + '      stripModeSub: sel ? (sel.communityLabel || "") : "Census areas across the metro, as the map shades them",\n',
  count: 1
};

/** A31.8 — the strip's own cards, both modes. CHAINED on A24.53/A24.54/A24.55, whose whole block
 *  this replaces.
 *
 *  `stripBasis` goes with it: in AREA mode the basis is the MAP's geography (which is what the
 *  card now measures, so `metaSource` is asked the same question the legend and the tip ask it,
 *  A24.49/A24.50) and in LOCATION mode it is the practice's own label. Nothing reads the
 *  per-community `communityLabel` afterwards, which A31.9 then deletes under the bundle's own
 *  dead-code rule.
 *
 *  FIVE bars, not the design's seven: five is what the endpoint publishes (p10/p25/p50/p75/p90)
 *  and the bar row is `flex: 1` per bar, so it divides whatever space it has and neither count
 *  changes the card's approved layout — measured at the card's own 232 px minimum, 26.6 px per
 *  bar at seven and 38.4 px at five. p10/p90 rather than the extremes because one outlying tract
 *  is not a class a summary should draw. The dimming is `opacity: .6`, the value the strip's own
 *  caret already carries, applied to the classes the practice is NOT in: no colour is changed,
 *  because the colour IS the class, and nothing moves, because opacity is not layout. */
const A31_8: Amendment = {
  id: 'A31.8', ...SNAP,
  find: "      stripCards: (() => {\n"
    + "        // What the snapshot's own figures describe: `comms` is one row per LISTING, so the\n"
    + "        // basis is the practice-area label the API serves, and only where the whole metro\n"
    + "        // agrees on one. Otherwise the design's own words, which is what the reference path\n"
    + "        // and every approved state renders - the design's fixtures carry no label at all.\n"
    + "        const labels = comms.map((c) => c.communityLabel).filter(Boolean);\n"
    + "        const stripBasis = (labels.length === comms.length && labels.length > 0 && labels.every((l) => l === labels[0]))\n"
    + "          ? labels[0] : \"community level\";\n"
    + "        return [\"income\", \"pets\", \"competition\", \"growth\", \"households\", \"econ\"]\n"
    + "        .filter((k) => enabled(k === \"competition\" ? \"vets\" : k))\n"
    + "        .map((k) => {\n"
    + "          const meta = LAYER_META[k];\n"
    + "          const cfg = VALUE_LAYERS[k];\n"
    + "          const on = valueLayer === k;\n"
    + "          const vals = comms.map((c) => (k === \"households\" ? c.hh : k === \"competition\" ? c.vets : c[k]))\n"
    + "            .filter((raw) => raw != null)\n"
    + "            .map((raw) => ({ raw: num(raw), t: this.bucket(k, num(raw)).t }));\n"
    + "          const mid = vals.length ? vals.map((v) => v.raw).sort((a, b) => a - b)[Math.floor(vals.length / 2)] : undefined;\n"
    + "          return {\n"
    + "            title: meta.title,\n"
    + "            value: (mid !== undefined) ? this.fmtMetric(k, mid) : undefined,\n"
    + "            valueNote: \"metro median\",\n"
    + "            src: metaSource(k, stripBasis),\n"
    + "            bars: vals.slice(0, 7).map((v) => ({\n"
    + "              style: \"flex: 1; height: \" + Math.max(4, Math.round(6 + v.t * 24)) +\n"
    + "                \"px; border-radius: 2px 2px 0 0; background: \" + ramp(k)[Math.min(3, Math.round(v.t * 3))] + \";\"\n"
    + "            })),\n",
  replace: "      stripCards: (() => {\n"
    + "        // TWO MODES (D-C50 as revised, 2026-09-12). AREA - nothing selected - is the metro\n"
    + "        // as the MAP paints it: the median and the shape of the distribution over the\n"
    + "        // polygons of each layer's own geography. LOCATION - a practice selected, its docked\n"
    + "        // panel open - is that practice's own community figures, the same `comms` row the\n"
    + "        // panel and the Community Context card already read, shown AGAINST the metro's\n"
    + "        // distribution so the two modes read against each other.\n"
    + "        //\n"
    + "        // The summary is the adapter's where there is one and the design's own where there\n"
    + "        // is not, which is A24.14's ternary exactly: with an adapter the strip describes what\n"
    + "        // the API answered or nothing at all, and with none it describes the design's own\n"
    + "        // polygons - never the median of the LISTINGS, which is the figure this ruling\n"
    + "        // removed from the screen.\n"
    + "        const summary = this.props.market ? (s.mdSummary || {}) : this.summarySet();\n"
    + "        const locBasis = sel ? (sel.communityLabel || \"community level\") : \"\";\n"
    + "        return [\"income\", \"pets\", \"competition\", \"growth\", \"households\", \"econ\"]\n"
    + "        .filter((k) => enabled(k === \"competition\" ? \"vets\" : k))\n"
    + "        .map((k) => {\n"
    + "          const meta = LAYER_META[k];\n"
    + "          const cfg = VALUE_LAYERS[k];\n"
    + "          const on = valueLayer === k;\n"
    + "          const sum = summary[k];\n"
    + "          // The selected practice's own figure, through the design's own two field aliases.\n"
    + "          const own = (sel && selComm) ? (k === \"households\" ? selComm.hh : k === \"competition\" ? selComm.vets : selComm[k]) : undefined;\n"
    + "          const shown = sel ? (own != null ? num(own) : undefined) : ((sum && sum.median != null) ? num(sum.median) : undefined);\n"
    + "          // The metro's shape, as five bars, classed on the MAP's OWN breaks - `bucket`'s\n"
    + "          // third argument, which is what the choropleth asks for (A24.25). These are the\n"
    + "          // map's polygons, so they take the map's classes: the strip and the legend then\n"
    + "          // agree about what colour a tract's figure is. Measured, not preferred - a Census\n"
    + "          // tract holds about 1,500 households and the community breaks start at 10,000, so\n"
    + "          // the community scale puts ALL FIVE quantiles in one class and draws five identical\n"
    + "          // 6 px stubs, which is the same collapse A24.25 was cut to remove on the map.\n"
    + "          const cls = (v) => Math.min(3, Math.round(this.bucket(k, num(v), true).t * 3));\n"
    + "          const dist = ((sum && sum.quantiles) || []).filter((q) => q != null).map((q) => this.bucket(k, num(q), true).t);\n"
    + "          // …and in LOCATION mode the class the practice's own figure falls in keeps its\n"
    + "          // colour while the rest take the caret's own .6, so the card says WHERE in the\n"
    + "          // metro the practice sits rather than repeating its number. ONLY where the two are\n"
    + "          // one measurement: the practice's figure is its five-mile ring's and the metro's is\n"
    + "          // a tract's, a place's or a county's, and those are the same scale only for a RATE\n"
    + "          // or a MEDIAN - exactly the layers `AREA_LAYERS` does not re-scale. Marking a ring's\n"
    + "          // household COUNT inside a distribution of tract counts would be this ruling's own\n"
    + "          // defect, one card over, so the three count layers carry the distribution undimmed.\n"
    + "          const here = (sel && own != null && !AREA_LAYERS[k]) ? cls(own) : null;\n"
    + "          return {\n"
    + "            title: meta.title,\n"
    + "            value: (shown !== undefined) ? this.fmtMetric(k, shown) : undefined,\n"
    + "            valueNote: sel ? locBasis : (sum ? \"metro median · \" + Math.round(sum.with_value).toLocaleString() + \" \" + (AREA_PLURAL[sum.geo_label] || sum.geo_label) : \"metro median\"),\n"
    + "            src: metaSource(k, sel ? locBasis : (AREA_LABEL[k] || \"\")),\n"
    + "            bars: dist.map((t) => ({\n"
    + "              style: \"flex: 1; height: \" + Math.max(4, Math.round(6 + t * 24)) +\n"
    + "                \"px; border-radius: 2px 2px 0 0; background: \" + ramp(k)[Math.min(3, Math.round(t * 3))] + \";\" +\n"
    + "                ((here !== null && Math.min(3, Math.round(t * 3)) !== here) ? \" opacity: .6;\" : \"\")\n"
    + "            })),\n",
  count: 1
};

/** A31.9 — the orphan A31.8 leaves: `communities()`'s own `communityLabel`, whose ONLY reader was
 *  A24.44's `stripBasis`. Deleted under the bundle's own dead-code rule (spec D8/D12, as A2.2–A2.5,
 *  A13.6/A13.7 and A28.2–A28.9 applied it), measured the same way — one declaration, zero readers
 *  in `logic.js`, in the amended design and in `App.vue` after A31.8. The PRACTICE's own
 *  `communityLabel` (`sel.communityLabel`, `p.communityLabel`) is a different field on a different
 *  object and is read in four places; it is untouched, and A31.7 and A31.8 are two of its readers.
 *  CHAINED on A24.44. */
const A31_9: Amendment = {
  id: 'A31.9', ...SNAP,
  find: '        id: p.id, name: p.area, lat: p.lat, lng: p.lng, communityLabel: p.communityLabel,\n',
  replace: '        id: p.id, name: p.area, lat: p.lat, lng: p.lng,\n',
  count: 1
};

/** A31.10 — the markup: the mode heading and its sub-line at the head of the strip's own body,
 *  above the six cards, and the grid takes the 9 px the docked panel's own tile grid takes under
 *  the same pair. Every declaration is copied from that pair (A27.7's own source), so the strip
 *  gains no style the design does not already carry. It sits INSIDE `md.stripOpen`, which is what
 *  keeps every Browse state but the two that open the strip on its own pixels. */
const A31_10: Amendment = {
  id: 'A31.10', ...SNAP,
  find: '            <div class="rf-scroll" style="max-height: 40vh; overflow-y: auto; padding: 0 22px 16px;">\n'
    + '              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(232px, 1fr)); gap: 10px;">\n',
  replace: '            <div class="rf-scroll" style="max-height: 40vh; overflow-y: auto; padding: 0 22px 16px;">\n'
    + '              <div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy);">{{ md.stripMode }}</div>\n'
    + '              <sc-if value="{{ md.hasStripModeSub }}" hint-placeholder-val="{{ true }}">\n'
    + '                <div style="font-size: 12.5px; color: var(--vf-text); margin-top: 2px;">{{ md.stripModeSub }}</div>\n'
    + '              </sc-if>\n'
    + '              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(232px, 1fr)); gap: 10px; margin-top: 9px;">\n',
  count: 1
};

/** A31.11 — the footnote, made true of BOTH modes. CHAINED on A24.20 and A24.56, whose sentences
 *  it replaces.
 *
 *  The sentence that goes is "Figures describe the area around each practice, not the practice
 *  itself" and A24.56's own restatement of it: in AREA mode the figures describe the metro's
 *  Census areas and no practice at all, so a release that moved them and left that sentence would
 *  be making its own copy false by its own act — the A27.5 rule. A24.20's growth caveat STAYS
 *  byte for byte: growth is still measured at place or county in both modes, and the paragraph is
 *  where that is said. */
const A31_11: Amendment = {
  id: 'A31.11', ...SNAP,
  find: 'Figures describe the area around each practice, not the practice itself. Pet-household counts and average practice payroll are derived estimates, not observed values. The map shades Census tracts, places, counties or ZIP Code Tabulation Areas, as each layer’s legend names; the snapshot’s figures describe the area around each practice. Population growth is measured for the surrounding city or county, not the tract.',
  replace: 'In AREA mode each card is the median across the metro’s Census tracts, places, counties or ZIP areas, as the card itself names; with a practice selected each card is that practice’s own community figure. Pet-household counts and average practice payroll are derived estimates, not observed values. Population growth is measured for the surrounding city or county, not the tract.',
  count: 1
};

/** Fix round 1 of Task SNAP (2026-09-13), the controller's rulings on the review of
 *  fb17325..19b26d7. Two entries, one ruling each, both CHAINED on A31.8 and A24.45. */
const SNAP1 = {
  date: '2026-09-13',
  ruling: 'A31.12 (controller, 2026-09-13, fix round 1 of Task SNAP; D-C48 applied to this surface): LOCATION mode never puts the ring caption over a figure that is not the ring\u2019s \u2014 growth is measured at place or county and carries its own `growth_scope`, payroll is the county CBP row everywhere and always \u2014 and in LOCATION mode the geography is named ONCE, on the card\u2019s own note, while the source line carries the dataset alone (A24.44\u2013A24.57\u2019s one-string-per-fact rule, measured on this surface: the basis printed TEN times on one strip). D-C51 (controller, 2026-09-13, the caption audit): the income card carries the API\u2019s own `income_note` where it serves one \u2014 a catchment median is a household-weighted median of tract medians, never published, and the detail card has qualified it since A27.1 while the strip printed the bare ring label beside the same number.'
};

/** A31.12 \u2014 the caption over a figure is that figure's own. CHAINED on A31.8, whose two
 *  adjacent lines this replaces.
 *
 *  MEASURED on the live path, which is the only place it can be seen: in LOCATION mode all six
 *  cards read the listing's `communityLabel` ("Within about 5 miles of the practice"), while
 *  `growth` is served at place-or-county with its own `growth_scope` (`app/census/serve.py`,
 *  D12 \u2014 `materialize.py` computes it ONCE per listing outside the band loop) and `econ` is the
 *  COUNTY CBP row everywhere and always (`serve.py`: "`econ_k` is county everywhere and always").
 *  On 28 of 29 QA listings the ring sentence was therefore false on two of the six cards \u2014 the
 *  exact defect D-C48 (John, 2026-09-11) removed from the docked panel's Population tile one day
 *  earlier, one surface over. Growth's fallback is A24.20's OWN phrase for the same fact
 *  ("the surrounding city or county"), which is what the reference and every approved state render:
 *  the design's fixtures carry no `growthScope` and `load.ts` leaves the key OFF where the API
 *  sends null.
 *
 *  And the `src` line drops the basis in LOCATION mode. One string per fact is A24.44\u2013A24.57's
 *  own rule; measured here it was broken ten times over \u2014 the basis printed on the mode sub-line,
 *  on each of the six `valueNote`s and on the three `src` lines that carry a `dataset`, four cards
 *  printing it twice. The card's note says WHERE the figure is measured; the source line says
 *  WHERE IT CAME FROM. AREA mode is untouched: there the card measures the map's own polygons and
 *  names them, exactly as the legend and the tip do (A24.49/A24.50). */
const A31_12: Amendment = {
  id: 'A31.12', ...SNAP1,
  find: "            valueNote: sel ? locBasis : (sum ? \"metro median \u00b7 \" + Math.round(sum.with_value).toLocaleString() + \" \" + (AREA_PLURAL[sum.geo_label] || sum.geo_label) : \"metro median\"),\n"
    + "            src: metaSource(k, sel ? locBasis : (AREA_LABEL[k] || \"\")),\n",
  replace: "            // A31.12 (fix round 1): the caption over a figure is THAT FIGURE's own\n"
    + "            // geography. `growth` is measured at place or county and the API names it\n"
    + "            // (`growth_scope`); `econ` is the county CBP row everywhere and always. The\n"
    + "            // other four ARE the ring the label describes. D-C48's ruling, one surface over.\n"
    + "            // D-C51: and the income card takes the API's own `income_note` where it is\n"
    + "            // served - a catchment median is a household-weighted median of tract\n"
    + "            // medians, never published, and the detail card has said so since A27.1.\n"
    + "            valueNote: sel\n"
    + "              ? (k === \"growth\" ? (sel.growthScope || \"surrounding city or county\")\n"
    + "                : k === \"econ\" ? \"surrounding county\"\n"
    + "                : k === \"income\" ? (sel.incomeNote || locBasis) : locBasis)\n"
    + "              : (sum ? \"metro median \u00b7 \" + Math.round(sum.with_value).toLocaleString() + \" \" + (AREA_PLURAL[sum.geo_label] || sum.geo_label) : \"metro median\"),\n"
    + "            // ONE STRING PER FACT (A24.44-A24.57). The note above carries the geography, so\n"
    + "            // this line carries the DATASET alone in LOCATION mode - measured, the basis\n"
    + "            // printed ten times on one strip before this, four cards printing it twice.\n"
    + "            src: metaSource(k, sel ? \"\" : (AREA_LABEL[k] || \"\")),\n",
  count: 1
};

/** A31.12b \u2014 `metaSource` composes a line for a surface that has no geography to name.
 *  CHAINED on A24.45, whose whole helper and comment this replaces.
 *
 *  A24.45 wrote it for two callers that both had a basis, so `dataset + " \u00b7 " + basis` was always
 *  right. A31.12 adds a third that deliberately has none, and `"" ` there would leave a dangling
 *  separator on the card. An empty basis now yields the dataset alone. The head comment's list of
 *  layers that "name no geography" is corrected in the same edit: A31.12c gives `growth` a
 *  `dataset`, so `econ` and `pets` are what is left. */
const A31_12b: Amendment = {
  id: 'A31.12b', ...SNAP1,
  find: '// A24 (D-C50 interim): the source line, composed for the surface that prints it. A layer\n'
    + '// whose line names a GEOGRAPHY carries the dataset alone (`dataset:`) and is given the basis\n'
    + "// by its caller - the map's own geography for the legend and the tip, the practice-area label\n"
    + '// for the snapshot strip, whose figures are per-listing and are not measured at either. A\n'
    + '// layer that names no geography (`growth`, `econ`, `pets`) keeps its own `source` sentence,\n'
    + '// which is true on both surfaces, and this returns it unchanged.\n'
    + 'const metaSource = (k, basis) => {\n'
    + '  const m = LAYER_META[k] || {};\n'
    + '  return m.dataset ? m.dataset + " \u00b7 " + basis : (m.source || "");\n'
    + '};\n',
  replace: '// A24 (D-C50 interim): the source line, composed for the surface that prints it. A layer\n'
    + '// whose line names a GEOGRAPHY carries the dataset alone (`dataset:`) and is given the basis\n'
    + "// by its caller - the map's own geography for the legend and the tip, the map's community\n"
    + "// notes, and the snapshot strip's AREA mode, which measures those same polygons. A layer\n"
    + '// that names no geography (`econ`, `pets`) keeps its own `source` sentence, which is true on\n'
    + '// every surface, and this returns it unchanged.\n'
    + '//\n'
    + '// A31.12b (fix round 1): a caller with NO geography to name gets the dataset alone. The\n'
    + "// strip's LOCATION mode is one - the card's own note carries the geography there, and one\n"
    + '// string per fact is this helper\'s whole reason for existing - and an empty basis would\n'
    + '// otherwise leave a dangling " \u00b7 " on the card.\n'
    + 'const metaSource = (k, basis) => {\n'
    + '  const m = LAYER_META[k] || {};\n'
    + '  if (!m.dataset) return m.source || "";\n'
    + '  return basis ? m.dataset + " \u00b7 " + basis : m.dataset;\n'
    + '};\n',
  count: 1
};

/** Fix round 1's second ruling (2026-09-13). A31.8's comment claimed "the strip and the legend
 *  then agree about what colour a tract's figure is"; it was false for `income`, whose ramp is the
 *  one with FIVE colours. */
const SNAP1B = {
  date: '2026-09-13',
  ruling: 'A31.13 (controller, 2026-09-13, fix round 1 of Task SNAP): a strip bar takes its colour from the SAME door the polygons do \u2014 `bucket(k, v, true)`\u2019s own `color`, never `ramp(k)[Math.round(t * 3)]`, which can address only four classes and so collapsed two of income\u2019s five onto one colour and could never draw its top one. The height keeps its `t`, and the LOCATION comparison is made on the class the bucket itself reports.'
};

/** A31.13 \u2014 the two lines that class a quantile. CHAINED on A31.8.
 *
 *  MEASURED: `ramp(k)[Math.min(3, Math.round(t * 3))]` is the DESIGN's own pre-A31 expression and
 *  it is correct for a four-colour ramp, which five of the six are. `income`'s carries five
 *  (`PALETTES.*.income`, "green, 5 classes"), so `bucket` returns `t = i / 4`: classes 2 and 3
 *  (`t = .5`, `t = .75`) both round to index 2 and class 4 is unreachable. The approved
 *  `browse-market-strip` therefore drew income's five bars in four colours, two of them the same,
 *  beside a map painting five \u2014 the one thing A31.8's own comment said could not happen.
 *
 *  `cls` now returns the bucket itself rather than a re-derived index, so the colour and the class
 *  come from one call and cannot disagree. `bucket()`'s return is UNCHANGED: `t = i / (ramp.length
 *  - 1)` is injective in `i` within one ramp, so comparing two `t`s from the same layer IS
 *  comparing their classes, and no index had to be added to it. The `here` line is untouched,
 *  byte for byte \u2014 it already reads `cls(own)`. */
const A31_13: Amendment = {
  id: 'A31.13', ...SNAP1B,
  find: "          const cls = (v) => Math.min(3, Math.round(this.bucket(k, num(v), true).t * 3));\n"
    + "          const dist = ((sum && sum.quantiles) || []).filter((q) => q != null).map((q) => this.bucket(k, num(q), true).t);\n",
  replace: "          // A31.13 (fix round 1): the bucket ITSELF, not a re-derived index. `income`'s ramp\n"
    + "          // carries five colours, so `t` is i / 4 and `Math.round(t * 3)` collapsed classes 2\n"
    + "          // and 3 onto one colour and could never reach class 4 - the strip drew five classes\n"
    + "          // in four colours beside a map painting five. One call, one class, one colour.\n"
    + "          const cls = (v) => this.bucket(k, num(v), true);\n"
    + "          const dist = ((sum && sum.quantiles) || []).filter((q) => q != null).map((q) => cls(q));\n",
  count: 1
};

/** A31.13b \u2014 the bar's own style, reading that bucket. CHAINED on A31.8.
 *
 *  The colour is the bucket's `color`, which is the colour `areaVals` gives the polygon carrying
 *  that value; the height keeps its `t`, which is what makes the row a distribution; and the
 *  LOCATION comparison is `t` against `t` from the same ramp, which is class against class.
 *  A31.8's sentence about the strip and the legend agreeing is true from here. */
const A31_13b: Amendment = {
  id: 'A31.13b', ...SNAP1B,
  find: "            bars: dist.map((t) => ({\n"
    + '              style: "flex: 1; height: " + Math.max(4, Math.round(6 + t * 24)) +\n'
    + '                "px; border-radius: 2px 2px 0 0; background: " + ramp(k)[Math.min(3, Math.round(t * 3))] + ";" +\n'
    + '                ((here !== null && Math.min(3, Math.round(t * 3)) !== here) ? " opacity: .6;" : "")\n'
    + "            })),\n",
  replace: "            bars: dist.map((b) => ({\n"
    + '              style: "flex: 1; height: " + Math.max(4, Math.round(6 + b.t * 24)) +\n'
    + '                "px; border-radius: 2px 2px 0 0; background: " + b.color + ";" +\n'
    + '                ((here !== null && b.t !== here.t) ? " opacity: .6;" : "")\n'
    + "            })),\n",
  count: 1
};

export function amendments(): Amendment[] {
  return [...deriveTypographyB(readFileSync(V2, 'utf8'), readFileSync(PRISTINE, 'utf8')), A2, A2_2, A2_3, A2_4, A2_5, A3, A4, A5_1, A5_3a, A5_3b, A5_4, A5_6, A5_7,
    A6_1, A6_2, A6_3a, A6_3b, A6_3c, A6_4a, A6_4b, A6_4c, A6_4d, A6_5, A6_6a, A6_6b, A7_1, A7_2,
    A7_3, A7_4, A8_1a, A8_1b, A8_1c, A8_2, A8_3a, A8_3b, A8_4a, A8_4b, A8_5, A8_6, A8_7, A8_8a, A8_8b,
    A9_1a, A9_1b, A10, A11, A10_2, A12_1, A12_2, A12_3, A12_4, A12_5, A12_6, A12_7, A12_8, A12_9, A12_10, A12_11,
    A13_1, A13_2, A13_3, A13_4, A13_5, A13_6, A13_7,
    A14_1, A14_2, A14_3, A14_4, A14_5, A14_6, A14_7, A14_8,
    // A13.8 edits the `out` closure A14.7 introduces, so it is the one A13 entry that has to run
    // after A14's (final review m4). Definition order in this file matches this list (m8).
    A13_8,
    A15_1, A15_2, A15_3a, A15_3b, A15_3c, A15_3d,
    // A16 and A17 (the seller lifecycle, 2026-09-08/09) land here, between A15 and A18, in id
    // order — this branch's own families, merged 2026-09-09 (SL9, A-SL34 (3)) against main's A18
    // and A19. Neither family's `find` collides with A13/A14/A18/A19's: A16/A17 are wizard,
    // dashboard and Admin Listings script edits (a disjoint set of methods/state keys from the
    // metro dropdown, the Give button and the lightbox), confirmed by `design-amendments.test.ts`
    // applying the whole merged list against the pristine bundle without a single re-match.
    A16_1, A16_2, A16_3, A16_4, A16_5, A16_6, A16_7, A16_8, A16_9, A16_10, A16_11a, A16_11b, A16_12, A16_13, A16_14, A16_15, A16_16, A16_17, A16_18, A16_19,
    A16_20a, A16_20b, A16_21, A16_22, A17_1, A17_2,
    // A18 — the two arrow reversals (2026-09-09). Both finds are unique in the pristine file.
    A18_1, A18_2,
    // A19 — the photo lightbox (2026-09-09). A19.9 reads A14.5's output and A19.10 reads A13.8's,
    // so the family is last. Definition order in this file matches this list (m8).
    A19_1, A19_2, A19_3, A19_4, A19_5, A19_6, A19_7, A19_8, A19_9, A19_10, A19_11, A19_12,
    // A21 — market-data layers do not render absence as zero (A-C28); A21.2/A21.2b reverted (A-C29,
    // the figure is payroll); A21.3a–d take the year from the data instead of hard-coding 2015.
    // A21.2b-e handle the panel rendering when figures are undefined (Task B10, D-C31).
    A21_1, A21_1b, A21_2b, A21_2c, A21_2d, A21_2e, A21_2f, A21_2g, A21_2h, A21_3a, A21_3b, A21_3c, A21_3d, A21_2i, A21_2j, A21_2k, A21_2l,
    // Task B10 (D-C31/D-C32, 2026-09-10). A21.1c is the root cause the entries above could not
    // reach: `communities()` zeroed every absent figure, so every `!== undefined` guard was
    // satisfied by a 0. A21.2m–A21.2p omit the three families of bars and the strip-card median
    // that were drawn from those zeros; A21.4a–A21.4d put the design's own unavailable card on the
    // panel; A21.5a–A21.5d name the area the figures describe when the API says it is not the
    // listing's own community. A21.5c runs after A12.7, whose replace preserves its `find`.
    A21_1c, A21_2m, A21_2n, A21_2o, A21_2p, A21_4a, A21_4b, A21_4c, A21_4d, A21_5a, A21_5b, A21_5c, A21_5d,
    // A22 — the ownership vocabulary widens to the seeds' own wording (2026-09-10, Task SL10).
    A22,
    // A23 — collapsing the Market data card closes both its menus (2026-09-10, Task MD1).
    A23,
    // A25 — a listing with no coordinates keeps its place and gets no pin (2026-09-10, Task MP1).
    // A25.5 reads A21.4a's output, so the family is last. Definition order in this file matches
    // this list (m8). A20 is reserved by the image-identifiability plan and A24 by the
    // neighbourhood-shading spec, both in flight; A25 is the next free id in the ledger.
    A25_1, A25_2, A25_3, A25_4, A25_5, A25_6,
    // A26 — the Browse filter bar's native <select>s become in-design dropdowns (John,
    // 2026-09-11), on A13's own idiom. Task F1 converts the five on the toolbar; A26.5-A26.7
    // read A13.8's and A19's output in the three shared dismissal closures, and A26.8c/A26.8d
    // read A14.2's, so the family is appended last as every family is. Definition order in
    // this file matches this list (m8). A26.3 and A26.11 are Task F2 — the three inside the
    // "More filters" popover, on the same idiom and the same state slot; A20 stays reserved by
    // the image-identifiability plan and A24 by the neighbourhood-shading spec.
    A26_1, A26_2, A26_3, A26_4, A26_5, A26_6, A26_7, A26_8a, A26_8b, A26_8c, A26_8d, A26_8e, A26_8f,
    A26_9a, A26_9b, A26_9c, A26_10, A26_11,
    // A26.12-A26.14 — the Q2 widening (controller ruling, 2026-09-11): John's own m7
    // invariant, restored in the three directions that were never written. Each reads
    // A26.8a/A26.8b/A26.8e's output, so all three run after the family's own entries.
    A26_12, A26_13, A26_14, A26_15,
    // A26.16 — the panel width (John, 2026-09-11, Task F1b): "the panel takes the width of the
    // trigger that opened it, so their edges line up." Its `find` is A26.10's and A26.11's own
    // output — the panel style string they share — so it is applied last, and once, for both.
    A26_16,
    // A27 — per-figure geography on the Community Context card (John, 2026-09-11, D-C38/D-C39).
    // A27.2 reads A21.3d's output, A27.3 A21.4a's and A27.4 A21.4d's, so the family is appended
    // last as every family is. Definition order in this file matches this list (m8). A20 stays
    // reserved by the image-identifiability plan and A24 by the neighbourhood-shading spec, so
    // A27 is the next free id in the ledger after A26.
    A27_1, A27_2, A27_3, A27_4, A27_5,
    // D-C42 (John, 2026-09-11): the Insights heading keeps its name and the geography moves to a
    // sub-line. A27.6 reads A27.3's output and A27.7 A21.5a's, so both run after them.
    A27_6, A27_7,
    // D-C48 (John, 2026-09-11, on the whole-branch review): the Population tile's sub-line is
    // growth, which is place-level, so it names its own geography rather than being covered by
    // A27.7's ring caption. Chained on A21.2d, which runs far earlier.
    A27_8,
    // A28 — the ring is drawn at the distance the card names (John, 2026-09-11, ruling D-C44).
    // A28.1 is the FIRST entry in this list that edits `MarketMapV3.jsx` rather than the
    // `.dc.html` (`file: 'jsx'`, the partition spec §9.2 added for A24, whose own four jsx
    // entries are appended after this family); A28.2-A28.4
    // delete the legacy panel's orphan rows and the two state flags those rows were the only
    // reader of, under the bundle's own dead-code rule. A28.5-A28.8 (controller amendment
    // D-C45) finish it: the four helpers those rows called (`layerRow`, `radioRow`, `setValue`,
    // `setLayer`) are unreferenced now too, and go under the same rule. None of the eight reads
    // an earlier entry's output — every `find` occurs in the pristine file — but the family is
    // appended last as every family is, and definition order in this file matches this list
    // (m8). A20 stays reserved by the image-identifiability plan and A24 by the
    // neighbourhood-shading spec, so A28 is the next free id in the ledger after A27.
    // A28.9 (whole-branch review, 2026-09-11) is the last orphan the same deletion left: the
    // `practices` layer default, whose only reader was A28.2's own deleted row.
    A28_1, A28_2, A28_3, A28_4, A28_5, A28_6, A28_7, A28_8, A28_9,
    // A24 -- real Census boundary polygons (2026-09-10, John's D-C34-D-C37) and the
    // growth breaks that make them readable (A24.13, D-C46, 2026-09-11). Numerically
    // before A25 and A26 and applied after both: A24 was RESERVED by the ledger's own
    // A25.1 row while those two families were written and merged, so every A24 `find`
    // is measured against the file they leave behind. Definition order in this file
    // matches this list (m8). The four `MarketMapV3.jsx` entries sit last;
    // `amendmentsFor` partitions them, so their position here only decides their
    // order among themselves.
    A24_1, A24_2, A24_3, A24_4, A24_5, A24_6a, A24_6b, A24_7, A24_8a, A24_8b, A24_13,
    // A24.14-A24.18 -- the adapter path (Task 10). A24.14 reads A24.1's own output and A24.16
    // reads A24.4's, so they run after the family's first pass. Definition order in this file
    // matches this list (m8).
    A24_14, A24_15, A24_16, A24_17, A24_18,
    // A24.19-A24.20 -- the Census tract ruling (2026-09-12). Both CHAINED: A24.19 reads A24.2's
    // output and A24.20 reads A24.7's, so both must sit after those two.
    A24_19, A24_20,
    // A24.21-A24.23 -- the viewport bbox (2026-09-12). All three CHAINED: A24.21 reads
    // A24.15's whole output, A24.22 reads A24.17's line and A24.23 reads A13.5's, so each
    // must sit after the entry it reads.
    A24_21, A24_22, A24_23,
    // A24.24-A24.32 -- the four layers that painted nothing (D-L1, 2026-09-12). Every entry is
    // CHAINED on an earlier A24 entry's output, so each runs after the one it reads: A24.24 reads
    // A24.2's and A24.19's, A24.25 A24.2's, A24.27/A24.30a/A24.30b A24.3's, A24.28 and A24.32
    // A24.5's (A24.32 runs after A24.28, which edits the same block), and A24.31b A24.16's.
    // Definition order in this file matches this list (m8).
    A24_24, A24_25, A24_26, A24_27, A24_28, A24_29, A24_30a, A24_30b, A24_31a, A24_31b, A24_32,
    // A24.33-A24.42 -- fix round 1 (review of e984c85..304b80f, 2026-09-12). Every entry is
    // CHAINED: A24.33/A24.38 read A24.3's output, A24.37 A24.25's, A24.39 A24.30b's, A24.41
    // A24.32's and A24.42 A24.31a's, so each runs after the entry it reads. Definition order in
    // this file matches this list (m8).
    A24_33, A24_34, A24_35, A24_36, A24_37, A24_38, A24_39, A24_40, A24_41, A24_42,
    // A24.43 -- MS1, the snapshot strip's own sign (2026-09-12). Not chained: its `find` is the
    // pristine bundle's own `num` declaration.
    A24_43,
    // A24.44-A24.57 -- fix round 2 (2026-09-12). The snapshot states its own basis (B) and the
    // threshold tip carries the ruled sentence alone (E). A24.56 reads A24.20's output and A24.57
    // A24.38's, so both run after the entries they read; A24.52 declares the term A24.51 reads
    // and A24.54 the term A24.53 reads, so each pair is ordered.
    A24_44, A24_45, A24_46, A24_47, A24_48, A24_49, A24_50, A24_52, A24_51, A24_54, A24_53,
    A24_55, A24_56, A24_57,
    // A24.58/A24.59 -- fix round 2, C and D: one number parser, and a comment that stopped being
    // true when A24.43 fixed it. A24.59 reads A24.3's own output.
    A24_58, A24_59,
    A24_9, A24_10, A24_11, A24_12,
    // A30 -- a metro change closes the docked panel (Task PANEL-STALE, 2026-09-12). Reads
    // A13.1's own output (the `setMarket` object literal it wrote), so it is appended last, as
    // every family is.
    A30,
    // A32 -- the metro switch waits for the map to move before asking (Task ADAPT-STALE-3,
    // 2026-09-12). CHAINED on A24.18, whose `this.loadAreas(v);` line is its whole `find`, so it
    // runs after it.
    A32,
    // A31 -- the Market snapshot has two modes, AREA and LOCATION (Task SNAP, ruling D-C50 as
    // revised, 2026-09-12). Appended last, as every family is, and it has to be: A31.4 reads
    // A24.17's line, A31.8 the whole A24.53/A24.54/A24.55 block, A31.9 A24.44's and A31.11
    // A24.20's and A24.56's -- and A31.5 reads A32's OWN output, which is why this block runs
    // after A32 rather than beside it. Definition order in this file matches this list (m8).
    A31_1, A31_2, A31_3, A31_4, A31_5, A31_6, A31_7, A31_8, A31_9, A31_10, A31_11,
    // Fix round 1 (2026-09-13): A31.12 is CHAINED on A31.8's own two caption lines and
    // A31.12b on A24.45's whole helper, so both run after the entries they read.
    A31_12, A31_12b,
    // A31.13/A31.13b are CHAINED on A31.8 too, on lines A31.12 does not touch.
    A31_13, A31_13b];
}
