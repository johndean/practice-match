import type { Page } from '@playwright/test';

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
  // Rule C: only present on input/select/textarea — sorted [name, value] pairs from the
  // LIVE el.value/el.checked/el.selected, standing in for the value/checked/selected
  // attributes (which Vue mirrors onto the DOM but React does not set at all).
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
  // Rule C: only populated by the in-page walk for input/select/textarea, from the live
  // el.value/el.checked/el.selected properties (whichever exist on the element).
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
// The design's runtime hooks its own pseudo-class rules to `scp…` tokens; the app's
// generated pseudo.css does the same with `sch…` tokens (frontend/src/generated/pseudo.css).
// Both are hover-hook identifiers, not meaningful content, so both fold to one placeholder.
const PSEUDO_CLASS = /^sc[hp][0-9a-z]+$/;

const byString = ([a]: [string, string], [b]: [string, string]) => (a < b ? -1 : a > b ? 1 : 0);

// Rule C: only these three tags ever carry a `props` field (excluded attrs/live props).
const FORM_TAGS = new Set(['input', 'select', 'textarea']);

// Rule W: a text node with only spaces/tabs/newlines (or none at all) is dropped from its
// parent's child list entirely — not collapsed to a single space (that was an earlier,
// now-superseded draft of this rule). Vue's compiler removes/condenses these even under
// `whitespace: 'preserve'`, while the design's React runtime renders every source
// whitespace node, so no transpiler output can match them position-for-position.
const isWhitespaceOnlyText = (n: RawNode): boolean => kindOf(n) === 'text' && /^\s*$/.test((n as RawText).text);

// Rule B: on the design (reference) target only, a `src`/`href` value beginning `assets/`
// or `ds/` is read as if it began `/assets/`/`/ds/` (the plan's mandated path rewrite).
// Any other value — including one already starting `/assets/` — is left untouched, on
// either target, and this never applies to the app side at all.
function rewriteDesignAttr([name, value]: [string, string]): [string, string] {
  if (name !== 'src' && name !== 'href') return [name, value];
  if (value.startsWith('assets/') || value.startsWith('ds/')) return [name, `/${value}`];
  return [name, value];
}

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
      let attrs = el.attrs.filter(([name]) => !isDroppedAttr(name)).slice().sort(byString);
      if (opts.design) attrs = attrs.map(rewriteDesignAttr);
      const node: DomElement = {
        tag: el.tag,
        attrs,
        class: el.classList.map((c) => (PSEUDO_CLASS.test(c) ? '<pseudo>' : c)).sort(),
        style: el.style.slice().sort(byString),
        children: el.children.filter((n) => !isWhitespaceOnlyText(n)).map((n) => normalise(n, opts))
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
// lockstep and reports the first name whose value differs, or the first name present on
// only one side. `fmt` supplies the message shape, which differs slightly by kind: attrs
// and style use `label name: "a" ≠ "b"`; props use `prop name "a" ≠ "b"` (no colon after
// the name), per the brief's own example.
function firstPairDiff(a: [string, string][], b: [string, string][], fmt: PairFmt): string | null {
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const av = i < a.length ? a[i] : null;
    const bv = j < b.length ? b[j] : null;
    if (av && bv && av[0] === bv[0]) {
      if (av[1] !== bv[1]) return fmt(av[0], av, bv);
      i++;
      j++;
    } else if (bv === null || (av !== null && av[0] < bv[0])) {
      return fmt(av![0], av, null);
    } else {
      return fmt(bv![0], null, bv);
    }
  }
  return null;
}
const attrFmt: PairFmt = (name, av, bv) => `attr ${name}: ${show(av)} ≠ ${show(bv)}`;
const styleFmt: PairFmt = (name, av, bv) => `style ${name}: ${show(av)} ≠ ${show(bv)}`;
const propFmt: PairFmt = (name, av, bv) => `prop ${name} ${show(av)} ≠ ${show(bv)}`;
function classDiff(a: string[], b: string[]): string | null {
  if (a.length === b.length && a.every((c, i) => c === b[i])) return null;
  return `class [${a.join(' ')}] ≠ [${b.join(' ')}]`;
}

function compareElements(a: DomElement, b: DomElement, selfPath: string, childBasePath: string, out: string[]): void {
  if (a.tag !== b.tag) {
    out.push(`${selfPath}: tag <${a.tag}> ≠ <${b.tag}>`);
    return; // structurally different subtrees below here — nothing further is meaningful
  }
  const attr = firstPairDiff(a.attrs, b.attrs, attrFmt);
  if (attr) out.push(`${selfPath}: ${attr}`);
  const prop = firstPairDiff(a.props ?? [], b.props ?? [], propFmt);
  if (prop) out.push(`${selfPath}: ${prop}`);
  const cls = classDiff(a.class, b.class);
  if (cls) out.push(`${selfPath}: ${cls}`);
  const style = firstPairDiff(a.style, b.style, styleFmt);
  if (style) out.push(`${selfPath}: ${style}`);
  if (a.children.length !== b.children.length) {
    out.push(`${selfPath}: child count ${a.children.length} ≠ ${b.children.length}`);
  }
  compareChildren(a.children, b.children, childBasePath, out);
}

function compareChildren(a: DomNode[], b: DomNode[], basePath: string, out: string[]): void {
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) compareChild(a[i], b[i], i, basePath, out);
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
      if (ta !== tb) out.push(`${displayPath}: text "${ta}" ≠ "${tb}"`);
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
// serialize(page) — the in-page walk is intentionally dumb (no filtering beyond which
// node types exist at all, no sorting, no substitution): it only reads the live DOM into
// a RawNode tree. All of the normalisation rules live in normalise() above, shared by
// both this wrapper and dom.test.ts's unit tests.
// ---------------------------------------------------------------------------------------
export async function serialize(page: Page, opts: NormaliseOptions = {}): Promise<DomNode> {
  const raw = await page.evaluate<RawNode>(() => {
    // Rule C: only these tags get value/checked/selected excluded from attrs and a `props`
    // field of the live properties instead (Vue's runtime-dom mirrors form state onto the
    // attribute; React sets only the property, so the attribute-based comparison can never
    // agree — the live property is the thing that's actually true on both targets).
    const FORM_TAGS = new Set(['input', 'select', 'textarea']);

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
      const isFormTag = FORM_TAGS.has(tag);
      const attrs: [string, string][] = [];
      for (const attr of Array.from(el.attributes)) {
        if (attr.name === 'class' || attr.name === 'style') continue;
        if (isFormTag && (attr.name === 'value' || attr.name === 'checked' || attr.name === 'selected')) continue;
        attrs.push([attr.name, attr.value]);
      }
      const style: [string, string][] = [];
      const decl = (el as HTMLElement).style;
      for (let i = 0; i < decl.length; i++) {
        const prop = decl[i];
        style.push([prop, decl.getPropertyValue(prop)]);
      }
      let props: [string, string][] | undefined;
      if (isFormTag) {
        // Feature-detect rather than hard-code per tag: `checked` only exists on
        // HTMLInputElement, `selected` on neither input/select/textarea today (it's an
        // <option> property) but is read defensively in case that ever changes.
        const live = el as unknown as { value?: unknown; checked?: unknown; selected?: unknown };
        props = [];
        if ('value' in live) props.push(['value', String(live.value)]);
        if ('checked' in live) props.push(['checked', String(live.checked)]);
        if ('selected' in live) props.push(['selected', String(live.selected)]);
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

    const root = document.querySelector('div[style*="min-height: 100vh"]');
    if (!root) throw new Error('dom oracle: root not found (div[style*="min-height: 100vh"])');
    const walked = walk(root);
    if (!walked) throw new Error('dom oracle: root failed to serialise');
    return walked;
  });
  return normalise(raw, opts);
}
