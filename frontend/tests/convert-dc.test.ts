import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildAppVue, compileExpr, convert, extractTemplate } from '../scripts/convert-dc.mjs';

const S = new Set<string>();

describe('compileExpr — the runtime resolve() grammar', () => {
  it('prefixes root identifiers with v., leaves loop aliases and $index alone, and never throws on missing paths', () => {
    expect(compileExpr('showPrototypeBar', S)).toBe('v.showPrototypeBar');
    expect(compileExpr('md.panel.photos.currentId', S)).toBe('v.md?.panel?.photos?.currentId');
    expect(compileExpr('j.go', new Set(['j']))).toBe('j?.go');
    expect(compileExpr('$index', new Set(['$index']))).toBe('$index');
    expect(compileExpr('rows[$index].label', new Set(['$index']))).toBe('v.rows?.[$index]?.label');
    expect(compileExpr('a[b.c]', S)).toBe('v.a?.[v.b?.c]');
  });
  it('translates equality, negation, literals and parentheses', () => {
    expect(compileExpr("gate === 'signin'", S)).toBe("(v.gate) === ('signin')");
    expect(compileExpr('!(auth == true)', S)).toBe('!((v.auth) == (true))');
    expect(compileExpr('count != 0', S)).toBe('(v.count) != (0)');
    expect(compileExpr('null', S)).toBe('null'); expect(compileExpr('12.5', S)).toBe('12.5'); expect(compileExpr('"x"', S)).toBe('"x"');
  });
});

describe('convert — template constructs', () => {
  it('wraps text interpolations in sc-interp spans that vanish for null/undefined/boolean, keeping literal text and whitespace verbatim', () => {
    const { template } = convert('<p>Hello {{ name }} and {{ other }}!</p>');
    expect(template).toBe('<p>Hello <span v-if="__s(v.name) !== null" class="sc-interp">{{ __s(v.name) }}</span> and <span v-if="__s(v.other) !== null" class="sc-interp">{{ __s(v.other) }}</span>!</p>');
  });
  it('binds whole-interpolated attributes, joins mixed ones with ?? "", and defaults value/checked', () => {
    const { template } = convert('<input value="{{ form.email }}" placeholder="Hi {{ who }}!" onChange="{{ setEmail }}" checked="{{ on }}">');
    expect(template).toBe('<input :value="(v.form?.email) ?? \'\'" :placeholder="`Hi ${(v.who) ?? \'\'}!`" @input="v.setEmail" :checked="(v.on) ?? false">');
  });
  it('maps React events: onClick → @click; onChange → @input on text controls and @change on select/checkbox/radio', () => {
    expect(convert('<button onClick="{{ go }}">x</button>').template).toBe('<button @click="v.go">x</button>');
    expect(convert('<select onChange="{{ pick }}"></select>').template).toBe('<select @change="v.pick"></select>');
    expect(convert('<input type="checkbox" onChange="{{ toggle }}">').template).toBe('<input type="checkbox" @change="v.toggle">');
    expect(convert('<textarea onChange="{{ set }}"></textarea>').template).toBe('<textarea @input="v.set"></textarea>');
    expect(convert('<div onMouseEnter="{{ a }}" onMouseLeave="{{ b }}"></div>').template).toBe('<div @mouseenter="v.a" @mouseleave="v.b"></div>');
  });
  it('turns style-hover into a generated pseudo-class with !important declarations, deduplicated by css text', () => {
    const { template, pseudoCss } = convert('<button class="x" style-hover="background: rgba(255,255,255,.26); color: #fff"></button><a style-hover="background: rgba(255,255,255,.26); color: #fff"></a><i style-hover="opacity: .5"></i>');
    expect(template).toBe('<button class="x sch0"></button><a class="sch0"></a><i class="sch1"></i>');
    expect(pseudoCss).toBe('.sch0:hover{background: rgba(255,255,255,.26) !important;color: #fff !important}\n.sch1:hover{opacity: .5 !important}\n');
  });
  it('merges a pseudo class into a dynamic class binding', () => {
    expect(convert('<b class="{{ cls }}" style-hover="x: y"></b>').template).toBe('<b :class="[v.cls, \'sch0\']"></b>');
  });
  it('converts sc-if and sc-for (with $index and the array guard), scoping loop aliases', () => {
    const { template } = convert('<sc-if value="{{ isDesktop }}" hint-placeholder-val="{{ true }}"><sc-for list="{{ nav }}" as="n" hint-placeholder-count="4"><button onClick="{{ n.go }}" style="{{ n.style }}">{{ n.label }} {{ title }}</button></sc-for></sc-if>');
    expect(template).toBe('<template v-if="v.isDesktop"><template v-for="(n, $index) in __arr(v.nav)" :key="$index"><button @click="n?.go" :style="n?.style"><span v-if="__s(n?.label) !== null" class="sc-interp">{{ __s(n?.label) }}</span> <span v-if="__s(v.title) !== null" class="sc-interp">{{ __s(v.title) }}</span></button></template></template>');
  });
  it('maps x-import and image-slot to the Vue components with bound props and drops hint-* attributes', () => {
    const { template } = convert('<x-import component="AustinMap" from="./AustinMap.jsx" markers="{{ markers }}" active-id="{{ activeId }}" on-select="{{ selectMarker }}" hint-size="100%,100%"></x-import><image-slot id="{{ p.photoId }}" shape="rect" src="{{ p.photoSrc }}" placeholder="{{ p.photoLabel }}"></image-slot>');
    expect(template).toBe('<div class="sc-host-x" style="display: contents"><ListingsMap :markers="v.markers" :active-id="v.activeId" :on-select="v.selectMarker"></ListingsMap></div><ImageSlot :id="v.p?.photoId" shape="rect" :src="v.p?.photoSrc" :placeholder="v.p?.photoLabel"></ImageSlot>');
    expect(convert('<x-import component="MarketMap" from="./MarketMap.jsx" practices="{{ md.practices }}"></x-import>').template).toBe('<div class="sc-host-x" style="display: contents"><MarketMapView :practices="v.md?.practices"></MarketMapView></div>');
  });

  // support.js `walkXImport` wraps every <x-import> in a host div — `wrap` is
  // `tplId != null || styleGet != null` and compileTemplate stamps data-dc-tpl on every
  // element, so the wrapper is unconditional. Its style is `hostPositionStyle(style) ||
  // { display: 'contents' }`; no x-import in this template carries a style attribute, so
  // the host style is always exactly `display: contents`. Rather than half-implement
  // hostPositionStyle for a case the design never exercises, the transpiler refuses it.
  it('wraps every x-import in the runtime\'s sc-host-x display:contents host, and refuses an x-import style attribute', () => {
    expect(convert('<div><x-import component="MarketMap" from="./MarketMap.jsx"></x-import></div>').template)
      .toBe('<div><div class="sc-host-x" style="display: contents"><MarketMapView></MarketMapView></div></div>');
    expect(() => convert('<x-import component="MarketMap" from="./MarketMap.jsx" style="top: 0;"></x-import>'))
      .toThrow(/x-import .*style/);
    // An unknown component is the more fundamental fault: it must be reported first even
    // when the element also carries the unsupported style attribute.
    expect(() => convert('<x-import component="NoSuchThing" from="./NoSuchThing.jsx" style="top: 0;"></x-import>'))
      .toThrow('unknown x-import component NoSuchThing');
  });

  // Zero-gap audit, Phase 9: the guard-ordering fix was only ever exercised on ONE of the
  // six component × known × style combinations. All six, as a table — so a future edit that
  // reorders the two throws, or makes `out` truthy for an unknown component, is caught
  // wherever it lands rather than only on the single case someone happened to write down.
  describe('x-import guard order — every component/known/style combination', () => {
    const CASES: { name: string; src: string; expected: 'ok' | RegExp }[] = [
      { name: 'plain element, no style', src: '<div id="a"></div>', expected: 'ok' },
      { name: 'plain element, with style', src: '<div style="top: 0;"></div>', expected: 'ok' },
      { name: 'image-slot (known), no style', src: '<image-slot id="x"></image-slot>', expected: 'ok' },
      { name: 'image-slot (known), with style', src: '<image-slot id="x" style="top: 0;"></image-slot>', expected: 'ok' },
      { name: 'x-import known, no style', src: '<x-import component="MarketMap" from="./m.jsx"></x-import>', expected: 'ok' },
      { name: 'x-import known, with style', src: '<x-import component="MarketMap" from="./m.jsx" style="top: 0;"></x-import>', expected: /^x-import with a style attribute is unsupported/ },
      { name: 'x-import UNKNOWN, no style', src: '<x-import component="NoSuchThing" from="./n.jsx"></x-import>', expected: /^unknown x-import component NoSuchThing$/ },
      { name: 'x-import UNKNOWN, with style', src: '<x-import component="NoSuchThing" from="./n.jsx" style="top: 0;"></x-import>', expected: /^unknown x-import component NoSuchThing$/ },
      // The degenerate case: no `component` attribute at all is still an unknown component,
      // not a crash reading COMPONENTS[undefined].
      { name: 'x-import with no component attribute', src: '<x-import from="./n.jsx"></x-import>', expected: /^unknown x-import component undefined$/ }
    ];
    for (const c of CASES) {
      it(c.name, () => {
        if (c.expected === 'ok') expect(() => convert(c.src)).not.toThrow();
        else expect(() => convert(c.src)).toThrow(c.expected);
      });
    }

    // The reordering must not have changed what a *valid* conversion produces.
    it('leaves unrelated conversion output untouched', () => {
      expect(convert('<image-slot id="x" style="top: 0;"></image-slot>').template).toBe('<ImageSlot id="x" style="top: 0;"></ImageSlot>');
      expect(convert('<div style="top: 0;"><span>a</span></div>').template).toBe('<div style="top: 0;"><span>a</span></div>');
    });
  });
  it('drops HTML comments and the helmet block, escapes text, keeps attribute case', () => {
    expect(extractTemplate('<html><x-dc><helmet><style>a{}</style></helmet>\n<div aria-label="Go">a &amp; b</div></x-dc><script data-dc-script></script></html>')).toBe('\n<div aria-label="Go">a &amp; b</div>');
    expect(convert('<!-- note --><div>a &lt; b</div>').template).toBe('<div>a &lt; b</div>');
  });
  it('is idempotent and buildAppVue assembles the SFC from the generated template and the hand-maintained setup script', () => {
    const t = convert('<div>{{ a }}</div>');
    expect(convert('<div>{{ a }}</div>')).toEqual(t);
    const sfc = buildAppVue(t.template, "const x = 1;\n", './generated/pseudo.css');
    expect(sfc.startsWith('<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html — do not edit; run `npm run gen:app` -->\n<template>\n')).toBe(true);
    expect(sfc).toContain("<script setup>\nimport './generated/pseudo.css';\nconst x = 1;\n</script>");
  });
  it('rewrites the design\'s relative asset paths to the app\'s absolute public paths (Global Constraint (a)), static values only', () => {
    expect(convert('<img src="assets/vin-foundation-logo.png" alt="VIN"><link href="ds/kit.css"><img src="{{ p.photoSrc }}">').template)
      .toBe('<img src="/assets/vin-foundation-logo.png" alt="VIN"><link href="/ds/kit.css"><img :src="v.p?.photoSrc">');
  });
  it('the CLI runs from a path containing spaces (self-invocation guard compares file paths, not URL strings)', async () => {
    const { mkdtempSync, writeFileSync, readFileSync, existsSync } = await import('node:fs');
    const { execFileSync } = await import('node:child_process');
    const { join } = await import('node:path');
    const dir = mkdtempSync(join(process.env.TMPDIR ?? '/tmp', 'convert dc '));
    writeFileSync(join(dir, 'd.html'), '<html><x-dc><div>{{ a }}</div></x-dc></html>'); writeFileSync(join(dir, 'setup.js'), 'const x = 1;\n');
    execFileSync(process.execPath, [join(import.meta.dirname, '..', 'scripts', 'convert-dc.mjs'), join(dir, 'd.html'), join(dir, 'setup.js'), join(dir, 'App.vue'), join(dir, 'pseudo.css')]);
    expect(existsSync(join(dir, 'App.vue')) && readFileSync(join(dir, 'App.vue'), 'utf8').includes('sc-interp')).toBe(true);
  });

  // V3 (Rev 2) constructs. The bundle's README Task 6 flags three to check before
  // regenerating; all three already convert, and are pinned here so a future generator edit
  // cannot silently break the V3 reference. The fourth — the x-import component NAME — is
  // the one that actually throws, because the design's map component was renamed
  // AustinMap/MarketMap → MarketMapV3.
  describe('V3 reference constructs', () => {
    it('maps the V3 map component onto the same Vue component, with every kebab-case prop bound', () => {
      const { template } = convert('<x-import component="MarketMapV3" from="./MarketMapV3.jsx" on-basemap="{{ md.setBasemap }}" practices="{{ md.practices }}" active-layer="{{ md.activeLayer }}" show-drive="{{ md.showDrive }}" on-area="{{ md.selectArea }}" recenter-key="{{ md.recenterKey }}" hint-size="100%,100%"></x-import>');
      expect(template).toBe('<div class="sc-host-x" style="display: contents"><MarketMapView :on-basemap="v.md?.setBasemap" :practices="v.md?.practices" :active-layer="v.md?.activeLayer" :show-drive="v.md?.showDrive" :on-area="v.md?.selectArea" :recenter-key="v.md?.recenterKey"></MarketMapView></div>');
    });

    it('binds a ref callback (the compare menu scrolls itself into view on open)', () => {
      expect(convert('<div role="listbox" aria-label="Comparison layer" ref="{{ md.compareMenuRef }}"></div>').template)
        .toBe('<div role="listbox" aria-label="Comparison layer" :ref="v.md?.compareMenuRef"></div>');
    });

    it('binds aria-selected on a listbox option, keeping false as a rendered value rather than a dropped attribute', () => {
      expect(convert('<button onClick="{{ o.go }}" role="option" aria-selected="{{ o.selected }}">x</button>').template)
        .toBe('<button @click="v.o?.go" role="option" :aria-selected="v.o?.selected">x</button>');
    });

    it('converts a sibling sc-if pair switching an img between two static files into two independent v-if blocks with absolute asset paths', () => {
      const { template } = convert('<button><sc-if value="{{ md.compareOpen }}" hint-placeholder-val="{{ false }}"><img src="assets/icons/sub-close-thin.svg" alt="" width="14" height="14" style="{{ md.comparePlusStyle }}"></sc-if><sc-if value="{{ md.compareClosed }}" hint-placeholder-val="{{ true }}"><img src="assets/icons/sub-plus-thin.svg" alt="" width="14" height="14" style="{{ md.comparePlusStyle }}"></sc-if></button>');
      expect(template).toBe('<button><template v-if="v.md?.compareOpen"><img src="/assets/icons/sub-close-thin.svg" alt width="14" height="14" :style="v.md?.comparePlusStyle"></template><template v-if="v.md?.compareClosed"><img src="/assets/icons/sub-plus-thin.svg" alt width="14" height="14" :style="v.md?.comparePlusStyle"></template></button>');
    });
  });
});

describe('the whole V3 reference converts and compiles', () => {
  const DC = join(import.meta.dirname, '..', '..', 'docs', 'design-reference', 'design_handoff_practice_match_v3', 'Practice Match V3.dc.html');

  it('converts without throwing and produces a template the Vue SFC compiler accepts', async () => {
    const { template, pseudoCss } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(template.length).toBeGreaterThan(100_000);
    expect(pseudoCss).toContain(':hover{');
    const { compileTemplate } = await import('@vue/compiler-sfc');
    const out = compileTemplate({ source: template, filename: 'App.vue', id: 'app', compilerOptions: { whitespace: 'preserve', isCustomElement: (tag: string) => tag === 'image-slot' } });
    expect(out.errors).toEqual([]);
  });

  it('renders both V3 maps as MarketMapView and no ListingsMap — V3 has no listings map, on desktop or on mobile', () => {
    const { template } = convert(extractTemplate(readFileSync(DC, 'utf8')));
    expect(template.split('<MarketMapView').length - 1).toBe(2);
    expect(template).not.toContain('<ListingsMap');
  });
});
