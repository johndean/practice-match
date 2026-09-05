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
