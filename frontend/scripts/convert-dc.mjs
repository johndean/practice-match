#!/usr/bin/env node
// Design template → Vue template. Mirrors the dc runtime (docs/design-reference/.../support.js) rule for rule; see the
// plan's Task 4a "Runtime rules mirrored". Output is deterministic: the same input always yields the same output.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseDocument } from 'htmlparser2';

const IDENT_RE = /^[A-Za-z_$][\w$]*/;
const NUMBER_RE = /^-?\d+(\.\d+)?$/;
const EVENTS = { onClick: 'click', onInput: 'input', onSubmit: 'submit', onKeyDown: 'keydown', onKeyUp: 'keyup', onKeyPress: 'keypress', onMouseDown: 'mousedown', onMouseUp: 'mouseup',
  onMouseEnter: 'mouseenter', onMouseLeave: 'mouseleave', onFocus: 'focus', onBlur: 'blur', onDoubleClick: 'dblclick', onContextMenu: 'contextmenu', onMouseMove: 'mousemove',
  onMouseOver: 'mouseover', onMouseOut: 'mouseout', onPointerDown: 'pointerdown', onPointerUp: 'pointerup', onPointerMove: 'pointermove', onPointerEnter: 'pointerenter', onPointerLeave: 'pointerleave' };
const COMPONENTS = { MarketMapV3: 'MarketMapView', 'image-slot': 'ImageSlot' };
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escAttr = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
const jsStr = (s) => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;

export function extractTemplate(html) {
  const open = /<x-dc(?:\s[^>]*)?>/.exec(html); const close = html.lastIndexOf('</x-dc>');
  if (!open || close < 0) throw new Error('no <x-dc> template');
  return html.slice(open.index + open[0].length, close).replace(/<helmet(?:\s[^>]*)?>[\s\S]*?<\/helmet\s*>/gi, '');
}

function parensWrapWhole(e) { let d = 0; for (let i = 0; i < e.length - 1; i++) { if (e[i] === '(') d++; else if (e[i] === ')') { d--; if (d === 0) return false; } } return true; }
function topEquality(e) {
  let d = 0;
  for (let i = 0; i < e.length; i++) {
    const c = e[i];
    if (c === '[' || c === '(') d++; else if (c === ']' || c === ')') d--;
    else if (d === 0 && (c === '=' || c === '!') && e[i + 1] === '=') {
      if (i > 0 && (e[i - 1] === '=' || e[i - 1] === '!')) continue;
      if (!e.slice(0, i).trim()) continue;
      const op = e[i + 2] === '=' ? c + '==' : c + '=';
      return { index: i, op };
    }
  }
  return null;
}
export function compileExpr(src, scope) {
  const e = String(src).trim();
  if (!e) return 'undefined';
  if (e[0] === '(' && e[e.length - 1] === ')' && parensWrapWhole(e)) return compileExpr(e.slice(1, -1), scope);
  const eq = topEquality(e);
  if (eq) return `(${compileExpr(e.slice(0, eq.index), scope)}) ${eq.op} (${compileExpr(e.slice(eq.index + eq.op.length), scope)})`;
  if (e[0] === '!') return `!(${compileExpr(e.slice(1), scope)})`;
  if (['true', 'false', 'null', 'undefined'].includes(e) || NUMBER_RE.test(e)) return e;
  if (e.length >= 2 && (e[0] === '"' || e[0] === "'") && e[e.length - 1] === e[0]) return e;
  const head = e.match(IDENT_RE); if (!head) return 'undefined';
  let out = scope.has(head[0]) ? head[0] : `v.${head[0]}`; let i = head[0].length;
  while (i < e.length) {
    if (e[i] === '.') { const m = e.slice(i + 1).match(IDENT_RE) || e.slice(i + 1).match(/^\d+/); if (!m) return 'undefined'; out += /^\d/.test(m[0]) ? `?.[${m[0]}]` : `?.${m[0]}`; i += 1 + m[0].length; }
    else if (e[i] === '[') { let d = 1, j = i + 1; while (j < e.length && d > 0) { if (e[j] === '[') d++; else if (e[j] === ']') { d--; if (d === 0) break; } j++; } if (d !== 0) return 'undefined'; out += `?.[${compileExpr(e.slice(i + 1, j), scope)}]`; i = j + 1; }
    else return 'undefined';
  }
  return out;
}

const WHOLE = /^\s*\{\{([\s\S]+?)\}\}\s*$/; const PARTS = /\{\{([\s\S]+?)\}\}/g;
function attrValue(raw, scope) {   // → { kind: 'static'|'expr', js }
  const whole = raw.match(WHOLE);
  if (whole) return { kind: 'expr', js: compileExpr(whole[1], scope) };
  if (!raw.includes('{{')) return { kind: 'static', js: raw };
  const parts = raw.split(PARTS);
  return { kind: 'expr', js: '`' + parts.map((s, i) => (i & 1) ? `\${(${compileExpr(s, scope)}) ?? ''}` : s.replace(/`/g, '\\`')).join('') + '`' };
}
function importantify(css) {
  const decls = []; let start = 0, depth = 0, quote = '';
  for (let i = 0; i < css.length; i++) { const c = css[i]; if (quote) { if (c === '\\') i++; else if (c === quote) quote = ''; } else if (c === '"' || c === "'") quote = c; else if (c === '(') depth++; else if (c === ')') depth--; else if (c === ';' && depth === 0) { decls.push(css.slice(start, i)); start = i + 1; } }
  decls.push(css.slice(start));
  return decls.map((d) => d.trim()).filter(Boolean).map((d) => /!important$/i.test(d) ? d : `${d} !important`).join(';');
}

export function convert(templateHtml) {
  const doc = parseDocument(templateHtml, { lowerCaseTags: false, lowerCaseAttributeNames: false, recognizeSelfClosing: true, decodeEntities: true });
  const pseudo = new Map(); const rules = [];
  const pseudoClass = (kind, css) => { const k = `${kind}|${css}`; if (!pseudo.has(k)) { const cls = 'sch' + pseudo.size.toString(36); pseudo.set(k, cls); const pe = kind === 'before' || kind === 'after'; rules.push(`.${cls}${pe ? '::' : ':'}${kind}{${pe ? css : importantify(css)}}`); } return pseudo.get(k); };
  const text = (t, scope) => t.split(PARTS).map((s, i) => (i & 1) ? `<span v-if="__s(${compileExpr(s, scope)}) !== null" class="sc-interp">{{ __s(${compileExpr(s, scope)}) }}</span>` : esc(s)).join('');
  const element = (el, scope) => {
    const tag = el.name; const a = el.attribs;
    if (tag === 'sc-if') return `<template v-if="${escAttr(compileExpr(a.value.match(WHOLE)?.[1] ?? a.value, scope))}">${kids(el, scope)}</template>`;
    if (tag === 'sc-for') { const alias = a.as || 'item'; const inner = new Set([...scope, alias, '$index']); return `<template v-for="(${alias}, $index) in __arr(${escAttr(compileExpr(a.list.match(WHOLE)?.[1] ?? a.list, scope))})" :key="$index">${kids(el, inner)}</template>`; }
    let out = tag; const attrs = []; let classStatic = null, classExpr = null; const pseudos = [];
    if (tag === 'x-import') out = COMPONENTS[a.component]; else if (tag === 'image-slot') out = COMPONENTS['image-slot'];
    if (!out) throw new Error(`unknown x-import component ${a.component}`);
    // support.js `walkXImport`: the component is always rendered inside a host div, since
    // `wrap` is `tplId != null || styleGet != null` and compileTemplate stamps data-dc-tpl
    // on every element. Its style is hostPositionStyle(style) || { display: 'contents' };
    // no x-import here carries a style attribute, so the host style is always the latter —
    // and rather than half-implement hostPositionStyle, an x-import style is refused.
    if (tag === 'x-import' && 'style' in a) throw new Error(`x-import with a style attribute is unsupported (support.js hostPositionStyle): ${a.component}`);
    for (const [name, raw] of Object.entries(a)) {
      if (name.startsWith('hint-') || name === 'sc-name' || name === 'data-dc-tpl' || (tag === 'x-import' && (name === 'component' || name === 'from'))) continue;
      if (name.startsWith('style-')) { pseudos.push(pseudoClass(name.slice(6), raw)); continue; }
      if (name in EVENTS || name === 'onChange') {
        const js = compileExpr(raw.match(WHOLE)?.[1] ?? raw, scope);
        const ev = name === 'onChange' ? ((tag === 'select' || (tag === 'input' && /^(checkbox|radio)$/i.test(a.type || ''))) ? 'change' : 'input') : EVENTS[name];
        attrs.push(`@${ev}="${escAttr(js)}"`); continue;
      }
      const v = attrValue(raw, scope);
      if (name === 'class') { if (v.kind === 'static') classStatic = v.js; else classExpr = v.js; continue; }
      if (v.kind === 'static') attrs.push(raw === '' ? name : `${name}="${escAttr(raw.replace(/^(assets|ds)\//, '/$1/'))}"`);
      else if (name === 'value') attrs.push(`:value="${escAttr(`(${v.js}) ?? ''`)}"`);
      else if (name === 'checked') attrs.push(`:checked="${escAttr(`(${v.js}) ?? false`)}"`);
      else attrs.push(`:${name}="${escAttr(v.js)}"`);
    }
    if (classExpr) attrs.unshift(`:class="${escAttr(pseudos.length ? `[${classExpr}, ${pseudos.map(jsStr).join(', ')}]` : classExpr)}"`);
    else if (classStatic !== null || pseudos.length) attrs.unshift(`class="${escAttr([classStatic, ...pseudos].filter(Boolean).join(' '))}"`);
    const open = `<${out}${attrs.length ? ' ' + attrs.join(' ') : ''}>`;
    const self = VOID.has(tag) ? open : `${open}${kids(el, scope)}</${out}>`;
    return tag === 'x-import' ? `<div class="sc-host-x" style="display: contents">${self}</div>` : self;
  };
  const kids = (node, scope) => node.children.map((c) => c.type === 'text' ? text(c.data, scope) : c.type === 'tag' || c.type === 'script' || c.type === 'style' ? element(c, scope) : '').join('');
  return { template: kids(doc, new Set()), pseudoCss: rules.map((r) => r + '\n').join('') };
}

export function buildAppVue(template, setupJs, pseudoCssImport) {
  return `<!-- GENERATED by frontend/scripts/convert-dc.mjs from docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html — do not edit; run \`npm run gen:app\` -->\n<template>\n${template}\n</template>\n\n<script setup>\nimport '${pseudoCssImport}';\n${setupJs}</script>\n`;
}

if (fileURLToPath(import.meta.url) === resolve(process.argv[1] ?? '')) {
  const [dc, setup, outVue, outCss] = process.argv.slice(2);
  const { template, pseudoCss } = convert(extractTemplate(readFileSync(dc, 'utf8')));
  writeFileSync(outVue, buildAppVue(template, readFileSync(setup, 'utf8'), './generated/pseudo.css'));
  writeFileSync(outCss, pseudoCss);
  console.log(`wrote ${outVue} (${template.length} chars) and ${outCss} (${pseudoCss.split('\n').length - 1} rules)`);
}
