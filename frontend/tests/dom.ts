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

export function normalise(raw: RawNode): DomNode {
  switch (kindOf(raw)) {
    case 'text': {
      const { text } = raw as RawText;
      return { text: /^\s*$/.test(text) ? ' ' : text };
    }
    case 'shadow':
      return { shadow: (raw as RawShadow).shadow.map(normalise) };
    case 'leaflet':
      return { tag: 'div', leaflet: true };
    default: {
      const el = raw as RawElement;
      return {
        tag: el.tag,
        attrs: el.attrs.filter(([name]) => !isDroppedAttr(name)).slice().sort(byString),
        class: el.classList.map((c) => (PSEUDO_CLASS.test(c) ? '<pseudo>' : c)).sort(),
        style: el.style.slice().sort(byString),
        children: el.children.map(normalise)
      };
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
// Walks two sorted [name, value] arrays (attrs or style declarations) in lockstep and
// reports the first name whose value differs, or the first name present on only one side.
function firstPairDiff(label: string, a: [string, string][], b: [string, string][]): string | null {
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    const av = i < a.length ? a[i] : null;
    const bv = j < b.length ? b[j] : null;
    if (av && bv && av[0] === bv[0]) {
      if (av[1] !== bv[1]) return `${label} ${av[0]}: ${show(av)} ≠ ${show(bv)}`;
      i++;
      j++;
    } else if (bv === null || (av !== null && av[0] < bv[0])) {
      return `${label} ${av![0]}: ${show(av)} ≠ ${show(null)}`;
    } else {
      return `${label} ${bv![0]}: ${show(null)} ≠ ${show(bv)}`;
    }
  }
  return null;
}
function classDiff(a: string[], b: string[]): string | null {
  if (a.length === b.length && a.every((c, i) => c === b[i])) return null;
  return `class [${a.join(' ')}] ≠ [${b.join(' ')}]`;
}

function compareElements(a: DomElement, b: DomElement, selfPath: string, childBasePath: string, out: string[]): void {
  if (a.tag !== b.tag) {
    out.push(`${selfPath}: tag <${a.tag}> ≠ <${b.tag}>`);
    return; // structurally different subtrees below here — nothing further is meaningful
  }
  const attr = firstPairDiff('attr', a.attrs, b.attrs);
  if (attr) out.push(`${selfPath}: ${attr}`);
  const cls = classDiff(a.class, b.class);
  if (cls) out.push(`${selfPath}: ${cls}`);
  const style = firstPairDiff('style', a.style, b.style);
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
      compareChildren((a as DomShadow).shadow, (b as DomShadow).shadow, joinPath(parentPath, 'shadow'), out);
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
      compareChildren((a as DomShadow).shadow, (b as DomShadow).shadow, 'shadow', out);
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
export async function serialize(page: Page): Promise<DomNode> {
  const raw = await page.evaluate<RawNode>(() => {
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
      const attrs: [string, string][] = [];
      for (const attr of Array.from(el.attributes)) {
        if (attr.name === 'class' || attr.name === 'style') continue;
        attrs.push([attr.name, attr.value]);
      }
      const style: [string, string][] = [];
      const decl = (el as HTMLElement).style;
      for (let i = 0; i < decl.length; i++) {
        const prop = decl[i];
        style.push([prop, decl.getPropertyValue(prop)]);
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
      return { tag: el.tagName.toLowerCase(), attrs, classList: Array.from(el.classList), style, children };
    }

    const root = document.querySelector('div[style*="min-height: 100vh"]');
    if (!root) throw new Error('dom oracle: root not found (div[style*="min-height: 100vh"])');
    const walked = walk(root);
    if (!walked) throw new Error('dom oracle: root failed to serialise');
    return walked;
  });
  return normalise(raw);
}
