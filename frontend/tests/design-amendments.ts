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
 *  sign-in gate. `verified → apply` is the D-I8-5 rider: an address that has never applied.
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

/** A10 — the sign-in card's second gate point (John, 2026-09-08). A literal script edit, like A3:
 *  the `gatePoints[1]` object in the sign-in view. Ids A8 and A9 are RESERVED by the account-screens
 *  branch (feat/identity: A8 = the account screens, A9 = the answer-note prototype prop), so this
 *  family is A10 — the gap is a reservation, not an omission. */
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

export function amendments(): Amendment[] {
  return [...deriveTypographyB(readFileSync(V2, 'utf8'), readFileSync(PRISTINE, 'utf8')), A2, A2_2, A2_3, A2_4, A2_5, A3, A4, A5_1, A5_3a, A5_3b, A5_4, A5_6, A5_7,
    A6_1, A6_2, A6_3a, A6_3b, A6_3c, A6_4a, A6_4b, A6_4c, A6_4d, A6_5, A6_6a, A6_6b, A7_1, A7_2, A10, A11];
}
