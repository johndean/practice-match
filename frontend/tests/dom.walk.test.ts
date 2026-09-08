// @vitest-environment jsdom
//
// Fix round 2, item 3: the in-page walk used to live inline inside `page.evaluate(() => {
// … })` in serialize() and duplicated the FORM_TAGS set (Playwright stringifies the
// function, so it can't close over module scope). Extracted here as an exported,
// self-contained `walkPage(arg)` — it may reference only its own argument, its own inner
// functions, and browser globals — so it can be unit-tested directly under jsdom, without
// ever going through Playwright. `serialize()` in dom.ts calls it via
// `page.evaluate(walkPage, { rootSelector: ROOT_SELECTOR, formTags: [...FORM_TAGS] })`.
import { describe, expect, it } from 'vitest';
import { walkPage, type RawElement } from './dom';

const FORM_TAGS = ['input', 'select', 'textarea'];
const walk = (rootSelector: string) => walkPage({ rootSelector, formTags: FORM_TAGS });

describe('walkPage — structural (fix round 2, item 3: single unit-tested walk)', () => {
  it('returns null when the root selector matches nothing', () => {
    document.body.innerHTML = '<div id="not-the-root"></div>';
    expect(walk('#root')).toBeNull();
  });

  it('walks a simple element: attrs (excluding class/style) and a text child', () => {
    document.body.innerHTML = '<div id="root" class="card" style="color: red"><span id="s">hi</span></div>';
    const raw = walk('#root') as RawElement;
    expect(raw.tag).toBe('div');
    expect(raw.attrs).toEqual([['id', 'root']]); // class/style excluded — they get dedicated fields in normalise()
    expect(raw.classList).toEqual(['card']);
    expect(raw.style).toEqual([['color', 'red']]);
    expect(raw.children).toEqual([{ tag: 'span', attrs: [['id', 's']], classList: [], style: [], children: [{ text: 'hi' }] }]);
  });

  it('drops comment nodes from children entirely', () => {
    document.body.innerHTML = '<div id="root"><!-- v-if placeholder --><span id="s"></span></div>';
    const raw = walk('#root') as RawElement;
    expect(raw.children).toEqual([{ tag: 'span', attrs: [['id', 's']], classList: [], style: [], children: [] }]);
  });

  it('captures a shadow root as a `shadow` child inserted first, before light-DOM children', () => {
    document.body.innerHTML = '<div id="root"></div>';
    const root = document.getElementById('root')!;
    const host = document.createElement('image-slot');
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = '<img id="pic">';
    root.appendChild(host);
    const raw = walk('#root') as RawElement;
    const hostRaw = raw.children[0] as RawElement;
    expect(hostRaw.tag).toBe('image-slot');
    expect(hostRaw.children[0]).toEqual({
      shadow: [{ tag: 'img', attrs: [['id', 'pic']], classList: [], style: [], children: [] }]
    });
  });

  it('collapses a .leaflet-container element to the reduced leaflet shape, regardless of contents', () => {
    document.body.innerHTML = '<div id="root"><div class="leaflet-container"><div class="leaflet-pane"></div></div></div>';
    const raw = walk('#root') as RawElement;
    expect(raw.children).toEqual([{ tag: 'div', leaflet: true }]);
  });
});

describe('walkPage — rule C narrowed (fix round 2, item 2): value on input/select/textarea; checked only on checkbox/radio; selected never read', () => {
  it('text input: props carries only value, not checked', () => {
    document.body.innerHTML = '<div id="root"><input id="t" type="text" value="a"></div>';
    const input = (walk('#root') as RawElement).children[0] as RawElement;
    expect(input.props).toEqual([['value', 'a']]);
  });

  it('checkbox input: props carries checked and value (both, sorted)', () => {
    document.body.innerHTML = '<div id="root"><input id="c" type="checkbox" checked></div>';
    const input = (walk('#root') as RawElement).children[0] as RawElement;
    expect(input.props).toEqual([
      ['checked', 'true'],
      ['value', 'on']
    ]);
  });

  it('radio input: props carries checked and value too', () => {
    document.body.innerHTML = '<div id="root"><input id="r" type="radio" value="x" checked></div>';
    const input = (walk('#root') as RawElement).children[0] as RawElement;
    expect(input.props).toEqual([
      ['checked', 'true'],
      ['value', 'x']
    ]);
  });

  it('select: props carries only value', () => {
    document.body.innerHTML = '<div id="root"><select id="s"><option value="a">A</option></select></div>';
    const select = (walk('#root') as RawElement).children[0] as RawElement;
    expect(select.props).toEqual([['value', 'a']]);
  });

  // ---------------------------------------------------------------------------------------
  // A-S5.2 (S-2): a <textarea> is compared by its VALUE, never by its children.
  //
  // A textarea's child text IS its default value, and the two runtimes materialise a filled one
  // differently: React writes `defaultValue` as well as `value` (so the text lands in the
  // element's children), Vue sets the property alone (so there are none). Measured on
  // `gate-reapply`, the one approved state with a non-empty textarea: pixel-identical on both
  // targets, and the DOM oracle reported `child count 1 ≠ 0` on that one node.
  //
  // Comparing the value instead is strictly STRONGER than what came before: `value` is already
  // excluded from `attrs` for every form tag, so before this the app's textarea value was
  // compared nowhere at all, and only the reference's framework artefact was.
  // ---------------------------------------------------------------------------------------
  it('textarea: props carries the value, and its children — the default value — are not recorded', () => {
    document.body.innerHTML = '<div id="root"><textarea id="a">typed by React</textarea></div>';
    const area = (walk('#root') as RawElement).children[0] as RawElement;
    expect(area.props).toEqual([['value', 'typed by React']]);
    expect(area.children, 'the child text IS the default value, and only one runtime writes it').toEqual([]);
  });

  it('textarea: the same value written two ways compares equal, children or no children', () => {
    // React's shape (value in the children) and Vue's shape (value in the property alone).
    document.body.innerHTML = '<div id="root"><textarea id="react">same words</textarea><textarea id="vue"></textarea></div>';
    (document.getElementById('vue') as HTMLTextAreaElement).value = 'same words';
    const [reactSide, vueSide] = (walk('#root') as RawElement).children as RawElement[];
    expect(reactSide.props).toEqual(vueSide.props);
    expect(reactSide.children).toEqual(vueSide.children);
    expect({ ...reactSide, attrs: [] }).toEqual({ ...vueSide, attrs: [] });
  });

  it('textarea: two DIFFERENT values still differ — the rule hides nothing', () => {
    document.body.innerHTML = '<div id="root"><textarea id="a">one</textarea><textarea id="b">two</textarea></div>';
    const [a, b] = (walk('#root') as RawElement).children as RawElement[];
    expect(a.props).not.toEqual(b.props);
  });

  it('textarea: an empty one is unchanged — no children, and an empty value', () => {
    document.body.innerHTML = '<div id="root"><textarea id="a"></textarea></div>';
    const area = (walk('#root') as RawElement).children[0] as RawElement;
    expect(area.props).toEqual([['value', '']]);
    expect(area.children).toEqual([]);
  });

  it('every OTHER tag still records its children, including the other two form tags', () => {
    document.body.innerHTML = '<div id="root"><p>kept</p><select id="s"><option value="a">A</option></select></div>';
    const [para, select] = (walk('#root') as RawElement).children as RawElement[];
    expect(para.children).toEqual([{ text: 'kept' }]);
    expect(select.children.length, 'a <select>\'s <option> children are real content').toBe(1);
  });

  it('never reads `selected` — an <option>, not a form tag, gets no props at all', () => {
    document.body.innerHTML = '<div id="root"><select id="s"><option id="o" value="a" selected>A</option></select></div>';
    const select = (walk('#root') as RawElement).children[0] as RawElement;
    expect(select.props).toEqual([['value', 'a']]); // no 'selected' key anywhere
    const option = select.children[0] as RawElement;
    expect(option.props).toBeUndefined(); // <option> isn't input/select/textarea
  });

  it('excludes the value attribute from attrs on form tags, and the checked attribute only for checkbox/radio', () => {
    document.body.innerHTML = '<div id="root"><input id="t" type="text" value="a"><input id="c" type="checkbox" checked></div>';
    const [text, checkbox] = (walk('#root') as RawElement).children as RawElement[];
    expect(text.attrs).toEqual([
      ['id', 't'],
      ['type', 'text']
    ]);
    expect(checkbox.attrs).toEqual([
      ['id', 'c'],
      ['type', 'checkbox']
    ]);
  });

  it('a non-form tag never gets a props field', () => {
    document.body.innerHTML = '<div id="root"><span id="s"></span></div>';
    const span = (walk('#root') as RawElement).children[0] as RawElement;
    expect(span.props).toBeUndefined();
  });
});

describe('walkPage — !important recorded (fix round 2, item 4)', () => {
  it('style pairs carry " !important" when the declaration has important priority', () => {
    document.body.innerHTML = '<div id="root"><div id="d" style="color: red !important"></div></div>';
    const child = (walk('#root') as RawElement).children[0] as RawElement;
    expect(child.style).toEqual([['color', 'red !important']]);
  });

  it('style pairs carry the bare value when there is no important priority', () => {
    document.body.innerHTML = '<div id="root"><div id="d" style="color: red"></div></div>';
    const child = (walk('#root') as RawElement).children[0] as RawElement;
    expect(child.style).toEqual([['color', 'red']]);
  });
});
