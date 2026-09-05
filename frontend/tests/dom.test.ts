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

  it('collapses whitespace-only text to a single space, keeping other text verbatim', () => {
    expect(normalise({ text: '   \n\t ' })).toEqual({ text: ' ' });
    expect(normalise({ text: '' })).toEqual({ text: ' ' });
    expect(normalise({ text: 'Approved buyer ' })).toEqual({ text: 'Approved buyer ' });
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
