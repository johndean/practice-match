import type { Page } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

// The DOM oracle: a normalised, element-by-element serialisation of the rendered DOM,
// so a structural/attribute/style/text difference between the app and the design is
// named by path (`div[0]/div[2]/span[1]: text "…" ≠ "…"`) rather than inferred from a
// pixel diff. Complements visual.spec.ts, which only proves the two targets render the
// same pixels — this proves they render the same tree.

// ---------------------------------------------------------------------------------------
// Canonical (normalised) shapes. `normalise()` turns a RawNode (below) into one of these;
// `diff()` only ever compares two DomNodes.
// ---------------------------------------------------------------------------------------
export interface DomText {
  text: string;
}
export interface DomShadow {
  shadow: DomNode[];
}
// `.leaflet-container` subtrees collapse to exactly this shape (maps are covered by
// pixels, not by this oracle) — no attrs/class/style/children, so two leaflet subtrees
// are always equal regardless of what Leaflet actually put inside them.
export interface DomLeaflet {
  tag: 'div';
  leaflet: true;
}
export interface DomElement {
  tag: string;
  attrs: [string, string][]; // sorted by name; excludes class, style and the dropped attrs
  class: string[]; // sorted tokens; scp…/sch… pseudo-class hooks collapse to '<pseudo>'
  style: [string, string][]; // sorted declarations read from el.style, not the attribute
  // Rule C, narrowed (fix round 2): sorted [name, value] pairs from the LIVE el.value on
  // input/select/textarea, plus el.checked on an input whose type is checkbox or radio —
  // standing in for the value/checked attributes (which Vue mirrors onto the DOM but React
  // does not set at all). `selected` is never read — it belongs to <option>, not to any of
  // these three tags.
  props?: [string, string][];
  children: DomNode[];
}
export type DomNode = DomText | DomShadow | DomLeaflet | DomElement;

// ---------------------------------------------------------------------------------------
// Raw shapes: exactly what the in-page walk (below) reads off the live DOM, before
// normalisation — attrs/class/style/text are not yet filtered, sorted, substituted or
// whitespace-collapsed. Kept as a separate type so `normalise()` stays a pure function,
// unit-testable without a browser (see dom.test.ts), and reusable for both targets.
export interface RawText {
  text: string;
}
export interface RawShadow {
  shadow: RawNode[];
}
export interface RawLeaflet {
  tag: 'div';
  leaflet: true;
}
export interface RawElement {
  tag: string;
  attrs: [string, string][];
  classList: string[];
  style: [string, string][];
  // Rule C, narrowed (fix round 2): populated by walkPage() for input/select/textarea
  // (value) and, additionally, a checkbox/radio input (checked). Not sorted at this stage —
  // that's normalise()'s job.
  props?: [string, string][];
  children: RawNode[];
}
export type RawNode = RawText | RawShadow | RawLeaflet | RawElement;

type Kind = 'text' | 'shadow' | 'leaflet' | 'element';
function kindOf(n: RawNode | DomNode): Kind {
  if ('text' in n) return 'text';
  if ('shadow' in n) return 'shadow';
  if ('leaflet' in n) return 'leaflet';
  return 'element';
}

// ---------------------------------------------------------------------------------------
// normalise()
// ---------------------------------------------------------------------------------------
const DROPPED_ATTRS = new Set(['data-dc-tpl', 'data-reactroot', 'key']);
const isDroppedAttr = (name: string) => DROPPED_ATTRS.has(name) || name.startsWith('data-v-');
// The design's runtime hooks its own pseudo-class rules to `scp…` tokens (support.js
// l.1579, `"scp" + (n++).toString(36)`); the app's generated pseudo.css does the same with
// `sch…` tokens (convert-dc.mjs's pseudoClass(), `'sch' + pseudo.size.toString(36)`). Both
// are hover-hook identifiers, not meaningful content, so both fold to one placeholder.
//
// Zero-gap audit, Phase 4 — this was one loose `^sc[hp][0-9a-z]+$` applied to both targets,
// which is a masking pattern: it also swallowed any ordinary content class beginning with
// either prefix (`school`, `scheme`, `schedule`, `scholar` are all sc[hp] + base-36
// characters), so such a class on one target compared EQUAL to a generated hook on the
// other. Each side now matches only its own generator's prefix, and the base-36 index is
// bounded at two characters — 1296 hooks, against the one character both generators
// actually use today (design: scp0/scp1/scp3/scp6 on Browse; app: sch0…scha, 11 rules).
// Anything longer is content, not an index, and is compared verbatim.
const PSEUDO_CLASS_APP = /^sch[0-9a-z]{1,2}$/;
const PSEUDO_CLASS_DESIGN = /^scp[0-9a-z]{1,2}$/;

const byString = ([a]: [string, string], [b]: [string, string]) => (a < b ? -1 : a > b ? 1 : 0);

// Rule C: only these three tags ever carry a `props` field (excluded attrs/live props).
const FORM_TAGS = new Set(['input', 'select', 'textarea']);

// Rule W: a text node with only whitespace (or none at all) is dropped from its parent's
// child list entirely — not collapsed to a single space (that was an earlier,
// now-superseded draft of this rule). Vue's compiler removes/condenses these even under
// `whitespace: 'preserve'`, while the design's React runtime renders every source
// whitespace node, so no transpiler output can match them position-for-position.
//
// Fix round 2: "whitespace" is exactly the compiler's set, not JS's `\s` — `@vue/compiler-
// core`'s `isWhitespace` matches only char codes 32 (space), 9 (tab), 10 (LF), 13 (CR), 12
// (FF). JS's `\s` additionally matches U+00A0 (non-breaking space) and other Unicode space
// separators, which are real content the compiler does NOT strip — so `\s` would wrongly
// drop a lone NBSP text node that the compiler (and thus both targets) actually renders.
const isWhitespaceOnlyText = (n: RawNode): boolean =>
  kindOf(n) === 'text' && /^[ \t\n\r\f]*$/.test((n as RawText).text);

// Rule B: on the design (reference) target only, a `src`/`href` value beginning `assets/`
// or `ds/` is read as if it began `/assets/`/`/ds/` (the plan's mandated path rewrite).
// Any other value — including one already starting `/assets/` — is left untouched, on
// either target, and this never applies to the app side at all.
function rewriteDesignAttr([name, value]: [string, string]): [string, string] {
  if (name !== 'src' && name !== 'href') return [name, value];
  if (value.startsWith('assets/') || value.startsWith('ds/')) return [name, `/${value}`];
  return [name, value];
}

// Rule E (John, 2026-09-05, fix round 3 — docs/decisions/2026-09-05-image-slot-editor-
// removed.md): the design tool's image editor is REMOVED from the port, not hidden, because
// the design's own `.ctl{…display:flex…}` beats the UA's `[popover]:not(:popover-open)` rule
// and left the Replace/Edit buttons keyboard-focusable and named in the accessibility tree
// in every browser. The design's element still builds them, so inside an `image-slot` shadow
// root the DESIGN side's `.spill`, `.ctl` and `input[type=file]` are dropped before
// comparison — otherwise every image-slot state would report three phantom missing children.
//
// One-sided on purpose: the app side is NEVER filtered, so a re-introduced `.ctl` in the
// port is still reported. Scoped on purpose: only an `image-slot` host's own shadow root, so
// a `.ctl` anywhere else in either tree stays ordinary content.
const isDesignEditorChrome = (n: RawNode): boolean => {
  if (kindOf(n) !== 'element') return false;
  const el = n as RawElement;
  if (el.classList.includes('spill') || el.classList.includes('ctl')) return true;
  return el.tag === 'input' && el.attrs.some(([name, value]) => name === 'type' && value === 'file');
};

export interface NormaliseOptions {
  design?: boolean;
}

export function normalise(raw: RawNode, opts: NormaliseOptions = {}): DomNode {
  switch (kindOf(raw)) {
    case 'text': {
      // Whitespace-only filtering happens in the PARENT (element/shadow) case below, by
      // dropping such children before recursing — a lone text node handed to normalise()
      // directly (as in a unit test, or the diff root) is returned verbatim either way.
      return { text: (raw as RawText).text };
    }
    case 'shadow': {
      const shadow = (raw as RawShadow).shadow;
      return { shadow: shadow.filter((n) => !isWhitespaceOnlyText(n)).map((n) => normalise(n, opts)) };
    }
    case 'leaflet':
      return { tag: 'div', leaflet: true };
    default: {
      const el = raw as RawElement;
      const pseudoHook = opts.design ? PSEUDO_CLASS_DESIGN : PSEUDO_CLASS_APP;
      let attrs = el.attrs.filter(([name]) => !isDroppedAttr(name)).slice().sort(byString);
      if (opts.design) attrs = attrs.map(rewriteDesignAttr);
      // Rule E applies at the image-slot HOST, because that is the only place the shadow
      // root's owner is known — `normalise()`'s shadow case sees a bare { shadow: [...] }.
      const dropEditorChrome = !!opts.design && el.tag === 'image-slot';
      const node: DomElement = {
        tag: el.tag,
        attrs,
        class: el.classList.map((c) => (pseudoHook.test(c) ? '<pseudo>' : c)).sort(),
        style: el.style.slice().sort(byString),
        children: el.children
          .filter((n) => !isWhitespaceOnlyText(n))
          .map((n) =>
            normalise(
              dropEditorChrome && kindOf(n) === 'shadow'
                ? { shadow: (n as RawShadow).shadow.filter((c) => !isDesignEditorChrome(c)) }
                : n,
              opts
            )
          )
      };
      if (FORM_TAGS.has(el.tag) && el.props) {
        node.props = el.props.slice().sort(byString);
      }
      return node;
    }
  }
}

// ---------------------------------------------------------------------------------------
// diff()
// ---------------------------------------------------------------------------------------
function joinPath(base: string, segment: string): string {
  return base ? `${base}/${segment}` : segment;
}
function show(pair: [string, string] | null): string {
  return pair ? `"${pair[1]}"` : '(none)';
}
type PairFmt = (name: string, av: [string, string] | null, bv: [string, string] | null) => string;
// Walks two sorted [name, value] arrays (attrs, style declarations, or — rule C — props) in
// lockstep and reports EVERY name whose value differs, plus every name present on only one
// side. `fmt` supplies the message shape, which differs slightly by kind: attrs and style
// use `label name: "a" ≠ "b"`; props use `prop name "a" ≠ "b"` (no colon after the name),
// per the brief's own example.
//
// Zero-gap audit, Phase 4: this used to return on the first difference. A first-error walk
// never reports a WRONG result — the diff is non-empty either way, so the gate still fails —
// but it hides the rest of the actionable evidence behind however many fix-and-rerun cycles
// the element has faults, which is exactly the "failures must be diagnostic and complete,
// not merely first-error" requirement. Names come back in sorted order because both inputs
// are sorted by normalise().
function pairDiffs(a: [string, string][], b: [string, string][], fmt: PairFmt): string[] {
  const out: string[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const av = i < a.length ? a[i] : null;
    const bv = j < b.length ? b[j] : null;
    if (av && bv && av[0] === bv[0]) {
      if (av[1] !== bv[1]) out.push(fmt(av[0], av, bv));
      i++;
      j++;
    } else if (bv === null || (av !== null && av[0] < bv[0])) {
      out.push(fmt(av![0], av, null));
      i++;
    } else {
      out.push(fmt(bv![0], null, bv));
      j++;
    }
  }
  return out;
}
const attrFmt: PairFmt = (name, av, bv) => `attr ${name}: ${show(av)} ≠ ${show(bv)}`;
const styleFmt: PairFmt = (name, av, bv) => `style ${name}: ${show(av)} ≠ ${show(bv)}`;
const propFmt: PairFmt = (name, av, bv) => `prop ${name} ${show(av)} ≠ ${show(bv)}`;
function classDiff(a: string[], b: string[]): string | null {
  if (a.length === b.length && a.every((c, i) => c === b[i])) return null;
  return `class [${a.join(' ')}] ≠ [${b.join(' ')}]`;
}

// How a node is named when it exists on one side only. Phase 4: "missing node must be
// reported precisely" / "extra node must be reported" — a bare count says how many are
// unaccounted for, never which, and a big missing subtree then reads as one anonymous
// number instead of a list of names to go and look for.
function nodeLabel(n: DomNode): string {
  switch (kindOf(n)) {
    case 'text':
      return `text "${(n as DomText).text}"`;
    case 'shadow':
      return 'shadow';
    case 'leaflet':
      return '<div leaflet>';
    default:
      return `<${(n as DomElement).tag}>`;
  }
}

function compareElements(a: DomElement, b: DomElement, selfPath: string, childBasePath: string, out: string[]): void {
  // Fix round 2: a tag mismatch no longer short-circuits the WHOLE node — its own
  // attrs/props/class/style are still meaningful (e.g. a wrong `<image-slot>`-vs-`<div>`
  // host that ALSO has a wrong `placeholder` attr should report both), only the CHILDREN
  // stop being comparable, since the two subtrees are structurally incompatible below the
  // mismatched tag itself.
  const tagMismatch = a.tag !== b.tag;
  if (tagMismatch) out.push(`${selfPath}: tag <${a.tag}> ≠ <${b.tag}>`);
  for (const m of pairDiffs(a.attrs, b.attrs, attrFmt)) out.push(`${selfPath}: ${m}`);
  for (const m of pairDiffs(a.props ?? [], b.props ?? [], propFmt)) out.push(`${selfPath}: ${m}`);
  const cls = classDiff(a.class, b.class);
  if (cls) out.push(`${selfPath}: ${cls}`);
  for (const m of pairDiffs(a.style, b.style, styleFmt)) out.push(`${selfPath}: ${m}`);
  if (tagMismatch) return; // nothing below a structurally incompatible tag is meaningful
  if (a.children.length !== b.children.length) {
    out.push(`${selfPath}: child count ${a.children.length} ≠ ${b.children.length}`);
  }
  compareChildren(a.children, b.children, childBasePath, out);
}

function compareChildren(a: DomNode[], b: DomNode[], basePath: string, out: string[]): void {
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) compareChild(a[i], b[i], i, basePath, out);
  // Phase 4: the positions past the shorter side are exactly the missing/extra nodes. They
  // are named individually, at their own index, after the shared prefix has been compared —
  // so a count line, the faults among the children both sides have, AND the identity of
  // every unmatched node all arrive from one run.
  const displayPath = basePath || '(root)';
  for (let i = len; i < a.length; i++) out.push(`${displayPath}: child[${i}] ${nodeLabel(a[i])} ≠ (none)`);
  for (let i = len; i < b.length; i++) out.push(`${displayPath}: child[${i}] (none) ≠ ${nodeLabel(b[i])}`);
}

// Reviewer finding (Important #1, fix round 1): compareChildren alone only ever walks
// min(a.length, b.length), so a shadow-root child-count mismatch was silently swallowed —
// nothing was reported about the missing/extra nodes. Both call sites that recurse into a
// shadow root (compareChild below, and diff()'s root-is-shadow branch) go through this
// helper instead, so the count is always reported at the `.../shadow` path before recursing.
function compareShadowChildren(a: DomNode[], b: DomNode[], shadowPath: string, out: string[]): void {
  if (a.length !== b.length) {
    out.push(`${shadowPath}: child count ${a.length} ≠ ${b.length}`);
  }
  compareChildren(a, b, shadowPath, out);
}

// Text-node (and node-kind) mismatches are reported at the PARENT's own path — they never
// get a path segment of their own (`div[0]/div[2]/span[1]: text …`, not
// `div[0]/div[2]/span[1]/#text[0]: …`). Only element children extend the path, with
// `<tag>[<index>]`.
function compareChild(a: DomNode, b: DomNode, index: number, parentPath: string, out: string[]): void {
  // parentPath is '' when comparing the root's own children (see diff() below); the join
  // base for element children must stay '' (so the first child reads `div[0]`, not
  // `(root)/div[0]`), but a message ABOUT this position still needs a readable label.
  const displayPath = parentPath || '(root)';
  const ka = kindOf(a);
  const kb = kindOf(b);
  if (ka !== kb) {
    out.push(`${displayPath}: child[${index}] ${ka} ≠ ${kb}`);
    return;
  }
  switch (ka) {
    case 'text': {
      const ta = (a as DomText).text;
      const tb = (b as DomText).text;
      // Fix round 2: carries the same child[i] index the node-kind-mismatch case above
      // already had, so two differing text children of one parent are distinguishable
      // instead of colliding on one identical-looking path.
      if (ta !== tb) out.push(`${displayPath}: child[${index}] text "${ta}" ≠ "${tb}"`);
      return;
    }
    case 'leaflet':
      return; // both reduced identically by construction — nothing further to compare
    case 'shadow':
      compareShadowChildren((a as DomShadow).shadow, (b as DomShadow).shadow, joinPath(parentPath, 'shadow'), out);
      return;
    default: {
      const ea = a as DomElement;
      const eb = b as DomElement;
      const path = joinPath(parentPath, `${ea.tag}[${index}]`);
      compareElements(ea, eb, path, path, out);
    }
  }
}

/** Paths like `div[0]/div[2]/span[1]: text "Approved buyer" ≠ "Approved buyer "`. */
export function diff(a: DomNode, b: DomNode): string[] {
  const out: string[] = [];
  const ka = kindOf(a);
  const kb = kindOf(b);
  if (ka !== kb) {
    out.push(`(root): ${ka} ≠ ${kb}`);
    return out;
  }
  switch (ka) {
    case 'text': {
      const ta = (a as DomText).text;
      const tb = (b as DomText).text;
      if (ta !== tb) out.push(`(root): text "${ta}" ≠ "${tb}"`);
      return out;
    }
    case 'leaflet':
      return out;
    case 'shadow':
      // Dead in practice (serialize()'s root is always the app/design's outer <div>, never
      // a shadow host itself), but kept symmetric with compareChild's shadow branch above —
      // both go through compareShadowChildren so a count mismatch is never silently dropped.
      compareShadowChildren((a as DomShadow).shadow, (b as DomShadow).shadow, 'shadow', out);
      return out;
    default:
      // The root itself has no siblings/position, so its own attr/class/style/count issues
      // are reported under the synthetic label '(root)' — but its CHILDREN start the real
      // path fresh (basePath ''), so the first child is `div[0]`, not `(root)/div[0]`.
      compareElements(a as DomElement, b as DomElement, '(root)', '', out);
      return out;
  }
}

// ---------------------------------------------------------------------------------------
// summarise(lines, max) — re-review minor 4. `diff()` returns EVERY actionable line, which
// is the point (fix round 2's "diagnostic and complete, not merely first-error"); on a badly
// diverged state that can be hundreds. The DATA is never capped — dom.spec.ts still asserts
// `toEqual([])` on the whole array — but the message a failing assertion PRINTS is, so a real
// regression stays readable in CI instead of scrolling the run out of the buffer. The tail
// line always names how many were withheld and the true total, so nothing is hidden silently.
// ---------------------------------------------------------------------------------------
export function summarise(lines: string[], max = 40): string {
  if (lines.length <= max) return lines.join('\n');
  return [...lines.slice(0, max), `… and ${lines.length - max} more (${lines.length} total)`].join('\n');
}

// ---------------------------------------------------------------------------------------
// walkPage(arg) — fix round 2, item 3: extracted out of an inline page.evaluate(() => {…})
// closure so it can be unit-tested directly under jsdom (dom.walk.test.ts), without ever
// going through Playwright. Playwright stringifies this function and re-runs it inside the
// page, so it must be fully self-contained: it may reference only its own argument (`arg`),
// its own inner functions, and browser globals — never anything from dom.ts's module scope
// (that's also why FORM_TAGS above couldn't be reused directly; it's passed in instead).
//
// The walk itself is intentionally dumb (no filtering beyond which node types exist at
// all, no sorting, no substitution): it only reads the live DOM into a RawNode tree. All
// of the normalisation rules live in normalise() above, shared by both serialize() below
// and dom.test.ts's unit tests; the narrowed rule C (value/checked selection) and the
// !important read below are the two exceptions that must happen here, at the point the
// live DOM is actually being read — normalise() only ever sees what this function chose to
// record.
// ---------------------------------------------------------------------------------------
export function walkPage(arg: { rootSelector: string; formTags: string[] }): RawNode | null {
  const formTags = new Set(arg.formTags);

  // Comments (and any other non-element, non-text node) carry no rendered content and
  // have no counterpart in either target's markup; they are simply not one of the two
  // node shapes this oracle represents, so walk() returns null for them and callers
  // filter the null out rather than record it as a child.
  function walk(node: Node): RawNode | null {
    if (node.nodeType === Node.TEXT_NODE) {
      return { text: node.textContent ?? '' };
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const el = node as Element;
    if (el.classList.contains('leaflet-container')) {
      return { tag: 'div', leaflet: true };
    }
    const tag = el.tagName.toLowerCase();
    const isFormTag = formTags.has(tag);
    // Rule C, narrowed (fix round 2): `checked` is only meaningful on a checkbox/radio
    // <input> — reading it (as a property OR excluding its attribute) on a text/select/
    // textarea makes no sense, since those never have a `checked` property at all.
    // `selected` is never read here: it belongs to <option>, which isn't a form tag.
    const isCheckableInput = tag === 'input' && ((el as HTMLInputElement).type === 'checkbox' || (el as HTMLInputElement).type === 'radio');
    const attrs: [string, string][] = [];
    for (const attr of Array.from(el.attributes)) {
      if (attr.name === 'class' || attr.name === 'style') continue;
      if (isFormTag && attr.name === 'value') continue;
      if (isCheckableInput && attr.name === 'checked') continue;
      attrs.push([attr.name, attr.value]);
    }
    const style: [string, string][] = [];
    const decl = (el as HTMLElement).style;
    for (let i = 0; i < decl.length; i++) {
      const prop = decl[i];
      const value = decl.getPropertyValue(prop);
      // Fix round 2: an !important rule is invisible to getPropertyValue() alone — read
      // getPropertyPriority() too, so a design-only (or app-only) !important is reported
      // as a real style difference instead of silently comparing equal.
      const suffix = decl.getPropertyPriority(prop) === 'important' ? ' !important' : '';
      style.push([prop, value + suffix]);
    }
    let props: [string, string][] | undefined;
    if (isFormTag || isCheckableInput) {
      props = [];
      const live = el as unknown as { value?: unknown; checked?: unknown };
      // Pushed in name order ('checked' < 'value') so the raw walk already matches the
      // sorted shape normalise() would produce anyway — avoids depending on normalise()'s
      // sort to prove this function's own output, since walkPage is unit-tested directly.
      if (isCheckableInput && 'checked' in live) props.push(['checked', String(live.checked)]);
      if (isFormTag && 'value' in live) props.push(['value', String(live.value)]);
    }
    const children: RawNode[] = [];
    if (el.shadowRoot) {
      const shadowChildren: RawNode[] = [];
      for (const child of Array.from(el.shadowRoot.childNodes)) {
        const w = walk(child);
        if (w) shadowChildren.push(w);
      }
      children.push({ shadow: shadowChildren });
    }
    for (const child of Array.from(el.childNodes)) {
      const w = walk(child);
      if (w) children.push(w);
    }
    return { tag, attrs, classList: Array.from(el.classList), style, children, ...(props ? { props } : {}) };
  }

  const root = document.querySelector(arg.rootSelector);
  if (!root) return null;
  return walk(root);
}

const ROOT_SELECTOR = 'div[style*="min-height: 100vh"]';

// ---------------------------------------------------------------------------------------
// serialize(page) — evaluates walkPage in the page (self-contained: see above), then
// normalises the result in Node/Playwright context.
// ---------------------------------------------------------------------------------------
export async function serialize(page: Page, opts: NormaliseOptions = {}): Promise<DomNode> {
  const raw = await page.evaluate(walkPage, { rootSelector: ROOT_SELECTOR, formTags: [...FORM_TAGS] });
  if (!raw) throw new Error(`dom oracle: root not found (${ROOT_SELECTOR})`);
  return normalise(raw, opts);
}

// ---------------------------------------------------------------------------------------
// readReferenceSnapshot() — fix round 2 moved this out of dom.spec.ts (which just called
// it inline) so the missing-file error message lives with the rest of the oracle's logic,
// not duplicated/hand-rolled in a spec. A missing snapshot means `--project=reference`
// hasn't been run (or was run before this state existed) — name the fix, not just the
// symptom.
// ---------------------------------------------------------------------------------------
export function readReferenceSnapshot(dir: string, name: string): DomNode {
  const file = join(dir, `${name}.json`);
  if (!existsSync(file)) {
    throw new Error(
      `Missing DOM snapshot "${name}" in ${dir} — run: npx playwright test --config=tests/playwright.config.ts --project=reference`
    );
  }
  return JSON.parse(readFileSync(file, 'utf8')) as DomNode;
}
