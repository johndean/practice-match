import { describe, expect, it } from 'vitest';
import { diff, normalise, type DomElement, type DomNode, type RawElement, type RawNode } from './dom';

// Minimal element fixtures. Every field the interface requires is present so the tests
// exercise normalise()/diff() exactly as serialize(page) would feed them, without a browser.
const el = (over: Partial<RawElement> = {}): RawElement => ({
  tag: 'div',
  attrs: [],
  classList: [],
  style: [],
  children: [],
  ...over
});
const domEl = (over: Partial<DomElement> = {}): DomElement => ({
  tag: 'div',
  attrs: [],
  class: [],
  style: [],
  children: [],
  ...over
});
// normalise()/diff() return the DomNode union; these fixtures are always elements, so
// narrow once here rather than casting at every call site.
const asEl = (n: DomNode): DomElement => n as DomElement;

describe('normalise', () => {
  it('maps both scp… (design) and sch… (app) pseudo-class hooks to the same placeholder', () => {
    expect(asEl(normalise(el({ classList: ['card', 'scp3'] }))).class).toEqual(['<pseudo>', 'card']);
    expect(asEl(normalise(el({ classList: ['card', 'sch3'] }))).class).toEqual(['<pseudo>', 'card']);
  });

  it('sorts attributes by name and drops data-dc-tpl, data-reactroot, data-v-*, key', () => {
    const raw = el({
      attrs: [
        ['id', 'p1'],
        ['data-dc-tpl', 'x'],
        ['aria-label', 'Cedar Park'],
        ['data-reactroot', ''],
        ['data-v-7ba5bd90', ''],
        ['key', '0']
      ]
    });
    expect(normalise(raw)).toMatchObject({
      attrs: [
        ['aria-label', 'Cedar Park'],
        ['id', 'p1']
      ]
    });
  });

  it('excludes class and style from attrs (they have their own fields already)', () => {
    const raw = el({ attrs: [['id', 'x']], classList: ['a', 'b'], style: [['color', 'red']] });
    const n = normalise(raw) as DomElement;
    expect(n.attrs).toEqual([['id', 'x']]);
    expect(n.class).toEqual(['a', 'b']);
    expect(n.style).toEqual([['color', 'red']]);
  });

  it('sorts style declarations by property', () => {
    const raw = el({
      style: [
        ['width', '10px'],
        ['color', 'red'],
        ['background', 'blue']
      ]
    });
    expect(normalise(raw)).toMatchObject({
      style: [
        ['background', 'blue'],
        ['color', 'red'],
        ['width', '10px']
      ]
    });
  });

  // Rule W (John, 2026-09-05): whitespace-only text nodes are DROPPED from child lists on
  // both targets (not collapsed to a single space, as an earlier draft of this rule had
  // it) — Vue's compiler removes/condenses them even under `whitespace: 'preserve'`, while
  // the design's React runtime renders every source whitespace node, so no transpiler
  // output can match them position-for-position. Text with any visible character is still
  // compared exactly, whitespace inside it untouched.
  it('drops whitespace-only and empty text nodes from children (rule W)', () => {
    const raw = el({
      children: [{ text: '\n  ' }, el({ tag: 'span' }), { text: '' }, el({ tag: 'em' })]
    });
    expect((normalise(raw) as DomElement).children).toEqual([domEl({ tag: 'span' }), domEl({ tag: 'em' })]);
  });

  it('drops whitespace-only and empty text nodes from shadow content too (rule W)', () => {
    const raw: RawNode = {
      shadow: [{ text: '\n  ' }, el({ tag: 'span' }), { text: '' }, el({ tag: 'em' })]
    };
    expect(normalise(raw)).toEqual({ shadow: [domEl({ tag: 'span' }), domEl({ tag: 'em' })] });
  });

  it('keeps text with any visible character verbatim, whitespace inside it untouched', () => {
    expect(normalise({ text: 'Approved buyer ' })).toEqual({ text: 'Approved buyer ' });
  });

  // Rule B (John, 2026-09-05): on the DESIGN side only, src/href values beginning
  // `assets/` or `ds/` are read as `/assets/…`/`/ds/…`; the app side (no options, or
  // `{ design: false }`) is unchanged; any other value (including one already starting
  // `/assets/`) is untouched either way.
  describe('rule B — design-side asset path rewrite', () => {
    it('rewrites design-side assets/ and ds/ src|href to /assets/ and /ds/', () => {
      const bySrc = el({ attrs: [['src', 'assets/x.png']] });
      expect((normalise(bySrc, { design: true }) as DomElement).attrs).toEqual([['src', '/assets/x.png']]);

      const byHref = el({ attrs: [['href', 'ds/icons.svg']] });
      expect((normalise(byHref, { design: true }) as DomElement).attrs).toEqual([['href', '/ds/icons.svg']]);
    });

    it('leaves a value already starting /assets/, or any other value, untouched', () => {
      const already = el({ attrs: [['src', '/assets/x.png']] });
      expect((normalise(already, { design: true }) as DomElement).attrs).toEqual([['src', '/assets/x.png']]);

      const unrelated = el({ attrs: [['src', 'https://example.com/x.png']] });
      expect((normalise(unrelated, { design: true }) as DomElement).attrs).toEqual([
        ['src', 'https://example.com/x.png']
      ]);
    });

    it('does not rewrite on the app side (no design option)', () => {
      const raw = el({ attrs: [['src', 'assets/x.png']] });
      expect((normalise(raw) as DomElement).attrs).toEqual([['src', 'assets/x.png']]);
    });
  });

  // Rule C (John, 2026-09-05): on input/select/textarea, live form state is recorded via
  // `props` (sorted [name, value] pairs from el.value/el.checked/el.selected), not via the
  // mirrored value/checked/selected attributes.
  describe('rule C — live form props', () => {
    it('carries a sorted props field through for a form tag', () => {
      const raw = el({ tag: 'select', attrs: [['id', 'city']], props: [['value', 'Austin, TX']] });
      const n = normalise(raw) as DomElement;
      expect(n.attrs).toEqual([['id', 'city']]);
      expect(n.props).toEqual([['value', 'Austin, TX']]);
    });

    it('does not attach a props field to a non-form tag', () => {
      expect((normalise(el({ tag: 'div' })) as DomElement).props).toBeUndefined();
    });
  });

  it('passes leaflet nodes through unchanged', () => {
    expect(normalise({ tag: 'div', leaflet: true })).toEqual({ tag: 'div', leaflet: true });
  });

  it('recurses into shadow content', () => {
    const raw: RawNode = { shadow: [el({ tag: 'span', classList: ['scp1'] })] };
    expect(normalise(raw)).toEqual({ shadow: [domEl({ tag: 'span', class: ['<pseudo>'] })] });
  });
});

describe('diff', () => {
  it('reports nothing for two identical trees', () => {
    const tree = domEl({ children: [{ text: 'hi' }] });
    expect(diff(tree, tree)).toEqual([]);
  });

  it('reports the first differing attribute, with path', () => {
    const a = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'x']] })] });
    const b = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'y']] })] });
    expect(diff(a, b)).toEqual(['span[0]: attr id: "x" ≠ "y"']);
  });

  it('reports an attribute present on only one side', () => {
    const a = domEl({ attrs: [['id', 'x']] });
    const b = domEl({ attrs: [] });
    expect(diff(a, b)).toEqual(['(root): attr id: "x" ≠ (none)']);
  });

  it('reports the first differing class-token set, with path', () => {
    const a = domEl({ children: [domEl({ tag: 'span', class: ['badge', 'lg'] })] });
    const b = domEl({ children: [domEl({ tag: 'span', class: ['badge'] })] });
    expect(diff(a, b)).toEqual(['span[0]: class [badge lg] ≠ [badge]']);
  });

  it('reports the first differing style declaration, with path', () => {
    const a = domEl({ children: [domEl({ tag: 'span', style: [['color', 'red']] })] });
    const b = domEl({ children: [domEl({ tag: 'span', style: [['color', 'blue']] })] });
    expect(diff(a, b)).toEqual(['span[0]: style color: "red" ≠ "blue"']);
  });

  it('reports differing text at the parent path, nested three levels deep', () => {
    const build = (text: string): DomNode =>
      domEl({
        children: [
          domEl({
            // div[0]'s children: two filler divs (div[0]/div[0], div[0]/div[1]), then the
            // div that holds the differing span at div[0]/div[2].
            children: [
              domEl(),
              domEl(),
              domEl({
                children: [
                  { text: 'x' }, // filler text sibling before the span
                  domEl({ tag: 'span', children: [{ text }] }) // div[0]/div[2]/span[1]
                ]
              })
            ]
          })
        ]
      });
    const a = build('Approved buyer');
    const b = build('Approved buyer ');
    expect(diff(a, b)).toEqual(['div[0]/div[2]/span[1]: text "Approved buyer" ≠ "Approved buyer "']);
  });

  it('reports a child-count mismatch, with path, and still compares the children both sides have', () => {
    const a = domEl({
      children: [domEl({ tag: 'span', attrs: [['id', 'a']] }), domEl({ tag: 'span', attrs: [['id', 'b']] })]
    });
    const b = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'a']] })] });
    expect(diff(a, b)).toEqual(['(root): child count 2 ≠ 1']);
  });

  it('labels a node-kind mismatch among the ROOT\'s own children "(root)", not a blank prefix', () => {
    const a = domEl({ children: [{ text: 'x' }] });
    const b = domEl({ children: [domEl({ tag: 'span' })] });
    expect(diff(a, b)).toEqual(['(root): child[0] text ≠ element']);
  });

  it('reports shadow content differences, with a /shadow path', () => {
    // A host element (like ImageSlot.vue's root div, or the design's <image-slot>) whose
    // shadow root holds the differing element — the shadow segment carries no index of
    // its own (there is at most one shadow root per host), so the path reads
    // <host>[i]/shadow/<tag>[j], not <host>[i]/shadow[k]/<tag>[j].
    const a = domEl({ children: [domEl({ tag: 'image-slot', children: [{ shadow: [domEl({ tag: 'img', attrs: [['src', 'a.png']] })] }] })] });
    const b = domEl({ children: [domEl({ tag: 'image-slot', children: [{ shadow: [domEl({ tag: 'img', attrs: [['src', 'b.png']] })] }] })] });
    expect(diff(a, b)).toEqual(['image-slot[0]/shadow/img[0]: attr src: "a.png" ≠ "b.png"']);
  });

  // Reviewer finding (Important #1, fix round 1): compareChildren alone only walks
  // min(a.length, b.length), so a shadow-root child-count mismatch was silently ignored.
  // The count must be reported at the `.../shadow` path before recursing.
  it('reports a shadow-root child-count mismatch before recursing further', () => {
    const shadowHost = (children: DomNode[]) =>
      domEl({ children: [domEl({ tag: 'image-slot', children: [{ shadow: children }] })] });
    const a = shadowHost([domEl({ tag: 'img' }), domEl({ tag: 'span' })]);
    const b = shadowHost([domEl({ tag: 'img' })]);
    expect(diff(a, b)).toEqual(['image-slot[0]/shadow: child count 2 ≠ 1']);
  });

  it('reports the same shadow-root child-count mismatch when the shadow root is the diffed root itself', () => {
    const a: DomNode = { shadow: [domEl({ tag: 'img' }), domEl({ tag: 'span' })] };
    const b: DomNode = { shadow: [domEl({ tag: 'img' })] };
    expect(diff(a, b)).toEqual(['shadow: child count 2 ≠ 1']);
  });

  it('reports a differing props entry, with path (rule C)', () => {
    const a = domEl({
      children: [domEl({ tag: 'span' }), domEl({ tag: 'select', props: [['value', 'Austin, TX']] })]
    });
    const b = domEl({ children: [domEl({ tag: 'span' }), domEl({ tag: 'select', props: [['value', 'Any']] })] });
    expect(diff(a, b)).toEqual(['select[1]: prop value "Austin, TX" ≠ "Any"']);
  });

  it('reports a strict tag mismatch and does not cascade further diffs below it', () => {
    const a = domEl({ children: [domEl({ tag: 'image-slot', attrs: [['id', 'p1']] })] });
    const b = domEl({ children: [domEl({ tag: 'div', attrs: [['id', 'different']] })] });
    expect(diff(a, b)).toEqual(['image-slot[0]: tag <image-slot> ≠ <div>']);
  });

  it('reports a leaflet subtree as equal to another leaflet subtree regardless of contents', () => {
    const a = domEl({ children: [{ tag: 'div', leaflet: true }] });
    const b = domEl({ children: [{ tag: 'div', leaflet: true }] });
    expect(diff(a, b)).toEqual([]);
  });
});
