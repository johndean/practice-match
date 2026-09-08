import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const V3_DIR = new URL('../../docs/design-reference/design_handoff_practice_match_v3/', import.meta.url);
export const PRISTINE = fileURLToPath(new URL('Practice Match V3.rev2.dc.html', V3_DIR));
export const AMENDED = fileURLToPath(new URL('Practice Match V3.dc.html', V3_DIR));
export const V2 = fileURLToPath(new URL('../../docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html', import.meta.url));
export const LOCAL_AMENDMENTS_MD = fileURLToPath(new URL('LOCAL_AMENDMENTS.md', V3_DIR));

export type Amendment = { id: string; date: string; ruling: string; find: string; replace: string; count: number; text?: string };

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
 *  (V3:3173–3176), verbatim, plus the two keys that close the menu on a choice. */
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
    '  };',
    '',
    '  // Moving the keyboard highlight. The rows are all in the DOM while the menu is open, so the',
    '  // one being highlighted is scrolled into view here rather than after a re-render: the panel',
    '  // scrolls at its max-height as soon as the market list is longer than the design\'s four.',
    '  moveMarketHighlight = (i) => {',
    '    this.setState({ marketMenuAt: i });',
    '    const row = document.getElementById("market-opt-" + i);',
    '    if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });',
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
    '      toggleMarketMenu: () => this.setState({ marketMenu: !s.marketMenu, marketMenuAt: Math.max(0, Object.keys(MARKETS).indexOf(s.market || "Austin, TX")) }),',
    '      marketActiveId: "market-opt-" + s.marketMenuAt,',
    '      marketTriggerLabel: (s.market || "Austin, TX") + " metro",',
    '      marketFieldStyle: "position: relative; display: flex; align-items: center; gap: 9px; height: 40px; padding: 0 8px 0 15px; min-width: 300px; background: var(--vf-neutral); border: 1px solid " +',
    '        (s.marketMenu ? "var(--vf-accent)" : "var(--border-subtle)") + "; border-radius: 6px;",',
    '      marketSelectStyle: "display: flex; align-items: center; gap: 8px; flex: 1; height: 36px; padding: 0; border: 0; outline: none; background: none; font-size: 14px; font-weight: 500; color: var(--vf-navy); cursor: pointer;",',
    '      marketCaretStyle: "flex: none; display: block; transition: transform 150ms var(--easing-out); transform: rotate(" +',
    '        (s.marketMenu ? "180deg" : "0deg") + ");",',
    '      marketMenuRef: (el) => { this._marketMenuEl = el || null; },',
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
 *  ramp, and absent beats faked. */
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
    '            <button onClick="{{ toggleMarketMenu }}" onKeyDown="{{ marketMenuKeys }}" aria-label="Metro area" aria-haspopup="listbox" aria-expanded="{{ marketMenuOpen }}" style="{{ marketSelectStyle }}">',
    '              <span style="flex: 1; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ marketTriggerLabel }}</span>',
    '              <img src="assets/icons/sub-chevron.svg" alt="" width="14" height="14" style="{{ marketCaretStyle }}">',
    '            </button>',
    '            <sc-if value="{{ marketMenuOpen }}" hint-placeholder-val="{{ false }}">',
    '              <div role="listbox" aria-label="Metro area" aria-activedescendant="{{ marketActiveId }}" style="position: absolute; left: 0; top: 46px; z-index: 700; width: 300px; padding: 4px; background: var(--vf-white); border: 1px solid var(--border-subtle); border-radius: 8px; box-shadow: 0 6px 20px rgba(0,58,112,.16); max-height: 232px; overflow-y: auto;" class="rf-scroll">',
    '                <sc-for list="{{ marketOptions }}" as="m" hint-placeholder-count="4">',
    '                  <button onClick="{{ m.go }}" id="{{ m.optId }}" role="option" aria-selected="{{ m.selected }}" style="{{ m.rowStyle }}" style-hover="background: var(--vf-neutral);">',
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

export function amendments(): Amendment[] {
  return [...deriveTypographyB(readFileSync(V2, 'utf8'), readFileSync(PRISTINE, 'utf8')), A2, A2_2, A2_3, A2_4, A2_5, A3, A4, A5_1, A5_3a, A5_3b, A5_4, A5_6, A5_7,
    A6_1, A6_2, A6_3a, A6_3b, A6_3c, A6_4a, A6_4b, A6_4c, A6_4d, A6_5, A6_6a, A6_6b, A7_1, A7_2,
    A7_3, A7_4, A8_1a, A8_1b, A8_1c, A8_2, A8_3a, A8_3b, A8_4a, A8_4b, A8_5, A8_6, A8_7, A8_8a, A8_8b,
    A9_1a, A9_1b, A10, A11, A10_2, A12_1, A12_2, A12_3, A12_4, A12_5, A12_6, A12_7, A12_8, A12_9, A12_10, A12_11,
    A13_1, A13_2, A13_3, A13_4, A13_5, A13_6, A13_7];
}
