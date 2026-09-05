import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { diff, normalise, readReferenceSnapshot, summarise, type DomElement, type DomNode, type RawElement, type RawNode } from './dom';

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
    expect(asEl(normalise(el({ classList: ['card', 'scp3'] }), { design: true })).class).toEqual(['<pseudo>', 'card']);
    expect(asEl(normalise(el({ classList: ['card', 'sch3'] }))).class).toEqual(['<pseudo>', 'card']);
  });

  // ---------------------------------------------------------------------------------------
  // Zero-gap audit, Phase 4 — oracle blind spot found and closed.
  //
  // The hook pattern used to be one loose `^sc[hp][0-9a-z]+$` applied to BOTH targets. Two
  // consequences, neither of which can make the oracle report something false, but both of
  // which let a real difference compare EQUAL — the only kind of oracle bug that matters:
  //
  //   (a) an ordinary content class that merely starts sch…/scp… — `school`, `scheme`,
  //       `schedule`, `scholar` are all `sc[hp]` + base-36 characters — folded to
  //       <pseudo> as well, so `class="schedule"` on one target and a generated hook on
  //       the other looked identical;
  //   (b) the app's prefix was accepted on the design side and vice versa, doubling the
  //       surface for (a).
  //
  // Both generators emit `prefix + (n++).toString(36)` for a small n — support.js l.1579
  // (scp) and convert-dc.mjs's pseudoClass() (sch). A live census of the design's Browse
  // screen finds scp0/scp1/scp3/scp6 and the app's generated/pseudo.css defines sch0…scha:
  // one base-36 character on both. Two characters is therefore an ample bound (1296 hooks)
  // and it excludes every English word that starts with the prefix. Each side now accepts
  // only its OWN generator's shape.
  // ---------------------------------------------------------------------------------------
  describe('pseudo-class hook substitution is side-aware and shape-bounded', () => {
    it('collapses only the design\'s own prefix on the design side', () => {
      expect(asEl(normalise(el({ classList: ['scp0'] }), { design: true })).class).toEqual(['<pseudo>']);
      expect(asEl(normalise(el({ classList: ['sch0'] }), { design: true })).class).toEqual(['sch0']);
    });

    it('collapses only the app\'s own prefix on the app side', () => {
      expect(asEl(normalise(el({ classList: ['sch0'] }))).class).toEqual(['<pseudo>']);
      expect(asEl(normalise(el({ classList: ['scp0'] }))).class).toEqual(['scp0']);
    });

    it('never collapses an ordinary content class that happens to start with the prefix', () => {
      for (const word of ['school', 'scheme', 'schedule', 'scholar', 'schema']) {
        expect(asEl(normalise(el({ classList: [word] }))).class, `app side: ${word}`).toEqual([word]);
        expect(asEl(normalise(el({ classList: [word] }), { design: true })).class, `design side: ${word}`).toEqual([word]);
      }
      expect(asEl(normalise(el({ classList: ['sc-host-x', 'sc-interp', 'scroll'] }))).class)
        .toEqual(['sc-host-x', 'sc-interp', 'scroll']);
    });

    it('accepts a two-character base-36 index — well past either generator\'s live count', () => {
      expect(asEl(normalise(el({ classList: ['schzz'] }))).class).toEqual(['<pseudo>']);
      expect(asEl(normalise(el({ classList: ['scpzz'] }), { design: true })).class).toEqual(['<pseudo>']);
    });

    // The blind spot itself, as a diff: a design content class against an app hook. Before
    // the fix both sides read `<pseudo>` and diff() returned [].
    it('now REPORTS a design content class sitting where the app has a generated hook', () => {
      const design = normalise(el({ tag: 'span', classList: ['schedule'] }), { design: true });
      const app = normalise(el({ tag: 'span', classList: ['sch0'] }));
      expect(diff(design, app)).toEqual(['(root): class [schedule] ≠ [<pseudo>]']);
    });
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

  // Fix round 2: whitespace = exactly the compiler's set (char codes 32, 9, 10, 13, 12 —
  // `@vue/compiler-core` `isWhitespace`), not JS's `\s` (which also matches U+00A0). A
  // non-breaking space is content and must be KEPT, not dropped as whitespace-only.
  it('rule W (fix round 2) — the whitespace set is exactly the compiler\'s; NBSP is content, not whitespace', () => {
    const NBSP = '\u00a0';
    const raw = el({
      children: [
        { text: NBSP }, // non-breaking space: content, must be KEPT
        { text: ' \n\t\r\f' }, // compiler whitespace set (space/tab/LF/CR/FF): dropped
        { text: '' }, // empty: dropped
        el({ tag: 'span' })
      ]
    });
    expect((normalise(raw) as DomElement).children).toEqual([{ text: NBSP }, domEl({ tag: 'span' })]);
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

  // Rule C (John, 2026-09-05), as NARROWED in fix round 2: live form state is recorded via
  // `props` rather than via the mirrored attributes — `value` on input/select/textarea, and
  // `checked` on an <input> whose type is checkbox or radio, and nothing else. `selected` is
  // never read: it belongs to <option>, which is not one of the three form tags. (The
  // pre-narrowing wording of this comment claimed el.value/el.checked/el.selected on all
  // three tags; walkPage has not behaved that way since b1aed38 — see dom.walk.test.ts.)
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

  // ---------------------------------------------------------------------------------------
  // Rule E (John, 2026-09-05, fix round 3): inside an `image-slot` shadow root, the DESIGN
  // side's editor nodes — `.spill`, `.ctl` and `input[type=file]` — are dropped before
  // comparison. The port no longer builds them (John's ruling: the design tool's image
  // editor is removed, not hidden — docs/decisions/2026-09-05-image-slot-editor-removed.md),
  // while the design's element still does, so without this rule every image-slot state would
  // report three phantom missing children.
  //
  // The rule is deliberately ONE-SIDED and deliberately SCOPED. One-sided: the app side is
  // never filtered, so if the port ever grows editor chrome again the oracle reports it
  // rather than quietly matching. Scoped: only the shadow root of an `image-slot` host, so a
  // `.ctl` anywhere else in either tree is ordinary content and is compared as such.
  // ---------------------------------------------------------------------------------------
  describe('rule E — the design\'s image-slot editor chrome', () => {
    const EDITOR = [
      el({ tag: 'div', classList: ['spill'], attrs: [['popover', 'manual']] }),
      el({ tag: 'div', classList: ['ctl'], attrs: [['popover', 'manual']] }),
      el({ tag: 'input', attrs: [['type', 'file'], ['hidden', '']] })
    ];
    const imageSlot = (extra: RawNode[] = []) =>
      el({
        tag: 'image-slot',
        children: [{ shadow: [el({ tag: 'style' }), el({ tag: 'div', classList: ['frame'] }), el({ tag: 'span', classList: ['credit'] }), ...extra] }]
      });
    const shadowOf = (n: DomNode) => ((n as DomElement).children[0] as { shadow: DomNode[] }).shadow;
    const label = (n: DomNode) => (n as DomElement).tag + ((n as DomElement).class.length ? '.' + (n as DomElement).class.join('.') : '');

    it('drops the design side\'s six-node image-slot shadow to the three display-only nodes', () => {
      const six = imageSlot(EDITOR);
      expect(shadowOf(normalise(six, { design: true })).map(label)).toEqual(['style', 'div.frame', 'span.credit']);
    });

    it('never filters the app side: an app-side .ctl survives normalisation and is REPORTED', () => {
      const design = normalise(imageSlot(EDITOR), { design: true });
      const appWithChrome = normalise(imageSlot([el({ tag: 'div', classList: ['ctl'] })]));

      expect(shadowOf(appWithChrome).map(label)).toEqual(['style', 'div.frame', 'span.credit', 'div.ctl']);
      // The image-slot is the diffed ROOT here, so its children start the path fresh.
      expect(diff(design, appWithChrome)).toEqual([
        'shadow: child count 3 ≠ 4',
        'shadow: child[3] (none) ≠ <div>'
      ]);
    });

    it('matches a compliant port exactly: design six nodes against app three, no diff', () => {
      expect(diff(normalise(imageSlot(EDITOR), { design: true }), normalise(imageSlot()))).toEqual([]);
    });

    it('is scoped to an image-slot shadow root: a .ctl elsewhere is ordinary content', () => {
      // …in the light DOM of an image-slot,
      const light = el({ tag: 'image-slot', children: [el({ tag: 'div', classList: ['ctl'] })] });
      expect(((normalise(light, { design: true }) as DomElement).children[0] as DomElement).class).toEqual(['ctl']);
      // …and in some other element's shadow root.
      const other = el({ tag: 'x-widget', children: [{ shadow: [el({ tag: 'div', classList: ['ctl'] })] }] });
      expect(shadowOf(normalise(other, { design: true })).map(label)).toEqual(['div.ctl']);
    });

    it('drops a file input only when it really is type=file', () => {
      const slot = imageSlot([el({ tag: 'input', attrs: [['type', 'text']] }), el({ tag: 'input', attrs: [['type', 'file']] })]);
      expect(shadowOf(normalise(slot, { design: true })).map(label)).toEqual(['style', 'div.frame', 'span.credit', 'input']);
    });
  });

  it('passes leaflet nodes through unchanged', () => {
    expect(normalise({ tag: 'div', leaflet: true })).toEqual({ tag: 'div', leaflet: true });
  });

  it('recurses into shadow content', () => {
    // App-side normalise(): the hook prefix that side generates is sch… (see the side-aware
    // substitution tests above); this test is about RECURSION, not about which prefix.
    const raw: RawNode = { shadow: [el({ tag: 'span', classList: ['sch1'] })] };
    expect(normalise(raw)).toEqual({ shadow: [domEl({ tag: 'span', class: ['<pseudo>'] })] });
  });
});

describe('diff', () => {
  it('reports nothing for two identical trees', () => {
    const tree = domEl({ children: [{ text: 'hi' }] });
    expect(diff(tree, tree)).toEqual([]);
  });

  it('reports a differing attribute, with path', () => {
    const a = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'x']] })] });
    const b = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'y']] })] });
    expect(diff(a, b)).toEqual(['span[0]: attr id: "x" ≠ "y"']);
  });

  // Zero-gap audit, Phase 4: "a mismatch in one property must NEVER prevent the oracle from
  // inspecting the remaining properties that can independently fail". The oracle used to
  // stop at the FIRST differing attribute (and the first style declaration, and the first
  // prop), so an element with three wrong attributes named one of them and the other two
  // only surfaced on the next run, after the first was fixed — one round trip per defect.
  it('reports EVERY differing attribute of one element, not just the first', () => {
    const a = domEl({ children: [domEl({ tag: 'img', attrs: [['alt', 'a'], ['src', 'x.png'], ['width', '10']] })] });
    const b = domEl({ children: [domEl({ tag: 'img', attrs: [['alt', 'b'], ['src', 'y.png'], ['width', '20']] })] });
    expect(diff(a, b)).toEqual([
      'img[0]: attr alt: "a" ≠ "b"',
      'img[0]: attr src: "x.png" ≠ "y.png"',
      'img[0]: attr width: "10" ≠ "20"'
    ]);
  });

  it('reports every attribute present on only one side, in both directions, in one pass', () => {
    const a = domEl({ attrs: [['alt', ''], ['id', 'x'], ['title', 't']] });
    const b = domEl({ attrs: [['id', 'x'], ['role', 'button']] });
    expect(diff(a, b)).toEqual([
      '(root): attr alt: "" ≠ (none)',
      '(root): attr role: (none) ≠ "button"',
      '(root): attr title: "t" ≠ (none)'
    ]);
  });

  it('reports every differing style declaration and every differing prop, not just the first', () => {
    const a = domEl({ children: [domEl({ tag: 'input', style: [['color', 'red'], ['width', '1px']], props: [['checked', 'true'], ['value', 'a']] })] });
    const b = domEl({ children: [domEl({ tag: 'input', style: [['color', 'blue'], ['width', '2px']], props: [['checked', 'false'], ['value', 'b']] })] });
    expect(diff(a, b)).toEqual([
      'input[0]: prop checked "true" ≠ "false"',
      'input[0]: prop value "a" ≠ "b"',
      'input[0]: style color: "red" ≠ "blue"',
      'input[0]: style width: "1px" ≠ "2px"'
    ]);
  });

  it('collects attr, prop, class and style faults on ONE element together, none masking another', () => {
    const a = domEl({ children: [domEl({ tag: 'input', attrs: [['id', 'x']], class: ['a'], style: [['color', 'red']], props: [['value', 'p']] })] });
    const b = domEl({ children: [domEl({ tag: 'input', attrs: [['id', 'y']], class: ['b'], style: [['color', 'blue']], props: [['value', 'q']] })] });
    expect(diff(a, b)).toEqual([
      'input[0]: attr id: "x" ≠ "y"',
      'input[0]: prop value "p" ≠ "q"',
      'input[0]: class [a] ≠ [b]',
      'input[0]: style color: "red" ≠ "blue"'
    ]);
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
    // Fix round 2: the text case gains the same child[i] index the node-kind-mismatch case
    // already had, so two differing text children of one parent are distinguishable (see
    // the next test) instead of colliding on one path.
    expect(diff(a, b)).toEqual(['div[0]/div[2]/span[1]: child[0] text "Approved buyer" ≠ "Approved buyer "']);
  });

  it('reports two differing text children of the same parent as distinguishable lines (fix round 2)', () => {
    const a = domEl({ children: [{ text: 'a' }, domEl({ tag: 'span' }), { text: 'c' }] });
    const b = domEl({ children: [{ text: 'A' }, domEl({ tag: 'span' }), { text: 'C' }] });
    expect(diff(a, b)).toEqual(['(root): child[0] text "a" ≠ "A"', '(root): child[2] text "c" ≠ "C"']);
  });

  // Zero-gap audit, Phase 4: the count alone said HOW MANY nodes were unaccounted for but
  // never WHICH — and the old fixture made the "still compares the children both sides
  // have" half of the title vacuous, because the shared child was identical. Both halves
  // are asserted now: the surviving child's own fault, and the missing node named.
  it('reports a child-count mismatch, names the missing node, and still compares the shared children', () => {
    const a = domEl({
      children: [domEl({ tag: 'span', attrs: [['id', 'a']] }), domEl({ tag: 'em', attrs: [['id', 'b']] })]
    });
    const b = domEl({ children: [domEl({ tag: 'span', attrs: [['id', 'DIFFERENT']] })] });
    expect(diff(a, b)).toEqual([
      '(root): child count 2 ≠ 1',
      'span[0]: attr id: "a" ≠ "DIFFERENT"',
      '(root): child[1] <em> ≠ (none)'
    ]);
  });

  it('reports an EXTRA node on the other side just as precisely', () => {
    const a = domEl({ children: [domEl({ tag: 'span' })] });
    const b = domEl({ children: [domEl({ tag: 'span' }), domEl({ tag: 'em' }), { text: 'tail' }] });
    expect(diff(a, b)).toEqual([
      '(root): child count 1 ≠ 3',
      '(root): child[1] (none) ≠ <em>',
      '(root): child[2] (none) ≠ text "tail"'
    ]);
  });

  it('names missing and extra nodes inside a shadow root too, at the /shadow path', () => {
    const host = (children: DomNode[]) => domEl({ children: [domEl({ tag: 'image-slot', children: [{ shadow: children }] })] });
    const a = host([domEl({ tag: 'style' }), domEl({ tag: 'div' }), domEl({ tag: 'input' })]);
    const b = host([domEl({ tag: 'style' })]);
    expect(diff(a, b)).toEqual([
      'image-slot[0]/shadow: child count 3 ≠ 1',
      'image-slot[0]/shadow: child[1] <div> ≠ (none)',
      'image-slot[0]/shadow: child[2] <input> ≠ (none)'
    ]);
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
    expect(diff(a, b)).toEqual([
      'image-slot[0]/shadow: child count 2 ≠ 1',
      'image-slot[0]/shadow: child[1] <span> ≠ (none)'
    ]);
  });

  it('reports the same shadow-root child-count mismatch when the shadow root is the diffed root itself', () => {
    const a: DomNode = { shadow: [domEl({ tag: 'img' }), domEl({ tag: 'span' })] };
    const b: DomNode = { shadow: [domEl({ tag: 'img' })] };
    expect(diff(a, b)).toEqual([
      'shadow: child count 2 ≠ 1',
      'shadow: child[1] <span> ≠ (none)'
    ]);
  });

  it('reports a differing props entry, with path (rule C)', () => {
    const a = domEl({
      children: [domEl({ tag: 'span' }), domEl({ tag: 'select', props: [['value', 'Austin, TX']] })]
    });
    const b = domEl({ children: [domEl({ tag: 'span' }), domEl({ tag: 'select', props: [['value', 'Any']] })] });
    expect(diff(a, b)).toEqual(['select[1]: prop value "Austin, TX" ≠ "Any"']);
  });

  // Fix round 2: a tag mismatch still reports that node's own attrs/class/style/props —
  // only its children stop being meaningful (structurally incompatible subtrees). The
  // mismatched `em`/`span` children below prove children really are skipped: if they
  // weren't, a third line (a child[0] tag or kind mismatch) would appear.
  it('reports a strict tag mismatch, still compares that node\'s own attrs, and skips only its children', () => {
    const a = domEl({
      children: [
        domEl({ tag: 'image-slot', attrs: [['placeholder', 'a']], children: [domEl({ tag: 'span' })] })
      ]
    });
    const b = domEl({
      children: [domEl({ tag: 'div', attrs: [['placeholder', 'b']], children: [domEl({ tag: 'em' })] })]
    });
    expect(diff(a, b)).toEqual([
      'image-slot[0]: tag <image-slot> ≠ <div>',
      'image-slot[0]: attr placeholder: "a" ≠ "b"'
    ]);
  });

  it('reports a leaflet subtree as equal to another leaflet subtree regardless of contents', () => {
    const a = domEl({ children: [{ tag: 'div', leaflet: true }] });
    const b = domEl({ children: [{ tag: 'div', leaflet: true }] });
    expect(diff(a, b)).toEqual([]);
  });
});

// Fix round 2: two items are test-only additions — the brief's own instruction for proving
// a test that passes on the first write actually bites: write it, run it, and if it's green
// immediately, break the branch it exercises once, watch it go red, then restore. Both are
// recorded that way in the report; the deliberate-break step is not left in this file.
describe('normalise recursion into element children (fix round 2 — explicitly asserted)', () => {
  it('recurses into nested element children, substituting a pseudo-class several levels down', () => {
    const raw = el({
      children: [el({ tag: 'section', children: [el({ tag: 'span', classList: ['sch4'] })] })]
    });
    const result = normalise(raw) as DomElement;
    const section = result.children[0] as DomElement;
    const span = section.children[0] as DomElement;
    expect(span.class).toEqual(['<pseudo>']);
  });
});

describe('rule W + shadow + props combined (fix round 2 — explicitly asserted)', () => {
  it('drops whitespace-only shadow text while a sibling form element keeps its props intact', () => {
    const raw: RawNode = {
      shadow: [
        { text: '\n' },
        el({ tag: 'input', attrs: [['type', 'text']], props: [['value', 'x']] }),
        { text: '' }
      ]
    };
    expect(normalise(raw)).toEqual({
      shadow: [domEl({ tag: 'input', attrs: [['type', 'text']], props: [['value', 'x']] })]
    });
  });
});

describe('readReferenceSnapshot', () => {
  it('throws a message naming the fix when the snapshot file is missing', () => {
    const dir = mkdtempSync(join(tmpdir(), 'dom-snap-'));
    expect(() => readReferenceSnapshot(dir, 'gate-signin')).toThrow(
      `Missing DOM snapshot "gate-signin" in ${dir} — run: npx playwright test --config=tests/playwright.config.ts --project=reference`
    );
  });

  it('reads and parses an existing snapshot file', () => {
    const dir = mkdtempSync(join(tmpdir(), 'dom-snap-'));
    const node = domEl({ tag: 'div' });
    writeFileSync(join(dir, 'gate-signin.json'), JSON.stringify(node));
    expect(readReferenceSnapshot(dir, 'gate-signin')).toEqual(node);
  });
});

// ---------------------------------------------------------------------------------------
// summarise() — re-review minor 4. `diff()` returns EVERY actionable line by design (fix
// round 2's Phase 4 requirement), which on a badly diverged state can be hundreds. The data
// is not capped; only the message a failing assertion PRINTS is, so a real regression stays
// readable in CI instead of scrolling the whole run out of the buffer. dom.spec.ts passes
// the summary as the assertion message while still asserting on the full array.
// ---------------------------------------------------------------------------------------
describe('summarise', () => {
  it('returns nothing for an empty list', () => {
    expect(summarise([])).toBe('');
  });

  it('joins every line unchanged when there are no more than max', () => {
    const lines = ['a: 1', 'b: 2', 'c: 3'];
    expect(summarise(lines, 3)).toBe('a: 1\nb: 2\nc: 3');
  });

  it('prints the first max lines and an exact tail line when there are more', () => {
    const lines = Array.from({ length: 10 }, (_, i) => `line ${i}`);
    expect(summarise(lines, 4)).toBe('line 0\nline 1\nline 2\nline 3\n… and 6 more (10 total)');
  });

  it('defaults to 40 lines', () => {
    const lines = Array.from({ length: 41 }, (_, i) => `line ${i}`);
    const out = summarise(lines).split('\n');
    expect(out).toHaveLength(41);
    expect(out[39]).toBe('line 39');
    expect(out[40]).toBe('… and 1 more (41 total)');
  });
});
