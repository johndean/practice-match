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
 *  deferring the call one macrotask — the same fix A19.10's trap needs for the identical reason,
 *  and the one the plan itself named for that closure (Step 10). `lightboxFocus` is still spent
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
    // A18 — the two arrow reversals (2026-09-09). Both finds are unique in the pristine file.
    A18_1, A18_2,
    // A19 — the photo lightbox (2026-09-09). A19.9 reads A14.5's output and A19.10 reads A13.8's,
    // so the family is last. Definition order in this file matches this list (m8).
    A19_1, A19_2, A19_3, A19_4, A19_5, A19_6, A19_7, A19_8, A19_9, A19_10, A19_11, A19_12];
}
