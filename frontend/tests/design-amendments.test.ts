import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AMENDED, LOCAL_AMENDMENTS_MD, PRISTINE, amendments, applyAmendments, deriveTypographyB, templateRegions, V2 } from './design-amendments';

describe('local design amendments (spec D15)', () => {
  const pristine = readFileSync(PRISTINE, 'utf8');
  // D15 makes the pristine copy the authority every amendment is measured from, so it needs an
  // oracle of its own: without one, a consistent edit to BOTH the pristine file and the amended
  // file keeps every other case green while "pristine, never edited" quietly stops being true.
  // This hash changes only when a re-issued bundle lands (and then the amendments retire with it).
  it('the pristine Rev 2 copy is the bundle\'s file, untouched', () => {
    expect(createHash('sha256').update(readFileSync(PRISTINE)).digest('hex')).toBe('335753c3164c10b80f9779de637a2358f40cde5c22d9195cc0a79f06bcf4f01d');
  });
  // The 24 elements V2 typed differently from V3 (measured in the V13 STOP reports and Step 5, 2026-09-07): 22 display headings, the
  // key-fact values `{{ m.v }}` (V2 set them uppercase .005em — one element in the template) and the 28 px mobile asking price
  // `{{ d.priceLabel }}` (V2: uppercase .005em; the 34 px desktop price is styled like V3 already). `{{ resultHeadline }}` is NOT among them:
  // V3's only occurrence is the mobile list's, byte-identical to V2's (the V7 review had paired it with V2's desktop Browse element).
  const A1_TEXTS = [
    'Veterinary Practice Transitions', "We're here to help connect veterinary practice owners", 'Member Sign In', 'Request Access',
    '{{ status.title }}', 'New to ownership? Start with the StartUp Club.', '{{ md.mdHeadline }}', '{{ d.title }}', '{{ sec.title }}',
    'Photos and Documents', 'Community Context', '{{ m.v }}', '{{ modal.title }}', 'My Requests', 'No requests yet', '{{ seller.heading }}',
    'My Listings', 'Buyer Interest', '{{ wiz.title }}', '{{ wiz.previewTitle }}', 'Your listing is with the VIN Foundation',
    'VIN Foundation Admin', '{{ d.priceLabel }}',
  ];
  it('A1 derives exactly the 24 V2-typography edits — value changes only, in place, none inside a script', () => {
    const a1 = deriveTypographyB(readFileSync(V2, 'utf8'), pristine);
    expect(a1).toHaveLength(24);
    expect(a1.filter((a) => a.text === '{{ d.priceLabel }}').map((a) => /font-size:\s*(\d+)px/.exec(a.find)?.[1])).toEqual(['28']);
    // `{{ d.title }}` occurs twice (34 px detail title, 19 px mobile title) — the key is (tag, text, size), so each pairs with its own V2 counterpart; the text list has one entry per distinct text.
    expect(new Set(a1.map((a) => a.text!.startsWith("We're here") ? "We're here to help connect veterinary practice owners" : a.text!))).toEqual(new Set(A1_TEXTS));
    for (const a of a1) {
      expect(a.replace, a.text).toContain('text-transform: uppercase');
      expect(a.replace, a.text).toMatch(/letter-spacing: \.0(2|05)em/);
      // M6 (re-review): this was `find.length - replace.length <= 0`, which only forbade the
      // replacement SHRINKING — it would have passed a `replace` that rewrote a colour or a font
      // size on the same tag, provided the string grew. Assert the real property instead: strip
      // the two declarations A1 is allowed to touch from both styles and everything left, plus
      // every byte outside the style attribute, must be identical.
      expect(withoutTypography(a.replace), `${a.text}: A1 changed something other than text-transform/letter-spacing`)
        .toBe(withoutTypography(a.find));
    }
    // The two elements the ruling leaves alone: `{{ c.value }}` is V3-only (no V2 counterpart, spec
    // D6) and `{{ resultHeadline }}` already equals V2's (V3's only occurrence is the mobile list's).
    for (const a of a1) {
      expect(a.text).not.toBe('{{ c.value }}');
      expect(a.text).not.toBe('{{ resultHeadline }}');
    }
    // "none inside a script", asserted rather than asserted-in-the-title: every `find` starts inside
    // one of the template regions — the spans OUTSIDE <script>/<style> — and ends before that region does.
    const regions = templateRegions(pristine);
    for (const a of a1) {
      const at = pristine.indexOf(a.find);
      expect(at, `${a.text}: find not present in the pristine file`).toBeGreaterThanOrEqual(0);
      expect(regions.some(([s, e]) => at >= s && at + a.find.length <= e), `${a.text}: find is not inside a template region`).toBe(true);
    }
  });
  it('the amended reference is the pristine Rev 2 file plus exactly the ruled edits', () => {
    expect(applyAmendments(pristine, amendments())).toBe(readFileSync(AMENDED, 'utf8'));
  });
  // D18 (John, 2026-09-07: "update across the application"). One occurrence in the pristine
  // file — the Insights-tab primary button of the docked panel (V3:705) opens the listing;
  // its label was wrong. The other tabs' "Open full listing" (V3:717) is untouched.
  it('A3 replaces the Insights tab\'s "View full market report" with "View full listing" (spec D18), exactly once', () => {
    expect(pristine.split('View full market report').length - 1).toBe(1);
    expect(readFileSync(AMENDED, 'utf8')).not.toContain('View full market report');
    expect(readFileSync(AMENDED, 'utf8')).toContain('View full listing');
  });
  it('after A1 every display-size heading in the template is uppercase with V2 tracking (19–22 px → .02em, ≥ 24 px → .005em)', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const figures = /p\.priceLabel|\{\{ c\.value \}\}/;   // `{{ m.v }}` and the 28 px `{{ d.priceLabel }}` are uppercase in V2 and return with A1; the 34 px price is not and V3 already matches it
    const re = /<(\w+)[^>]*?style="([^"]*font-size:\s*(\d+)px[^"]*)"[^>]*>([^<]{0,120})/g; let m: RegExpExecArray | null; let seen = 0;
    const body = amended.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, '');
    while ((m = re.exec(body))) {
      const px = Number(m[3]); if (px < 19 || m[1] === 'p' || figures.test(m[4]) || (m[4].includes('{{ d.priceLabel }}') && px === 34)) continue; seen++;
      expect(m[2], m[4]).toContain('text-transform: uppercase');
      expect(m[2], m[4]).toContain(`letter-spacing: ${px >= 24 ? '.005em' : '.02em'}`);
    }
    expect(seen).toBe(24);
  });
  // M4/M6 (re-review): the `find`-count contract had no explicit expectation anywhere — the
  // general guard is `applyAmendments`' own `throw`, reachable only through the byte-identity
  // case above, so a future refactor to a plain `replace` chain would drop it silently and the
  // failure would point at the wrong test. It is also the case that states spec D15's contract
  // as implemented: the count is measured at the point the amendment is APPLIED, in list order,
  // because A2.5's `find` is the text A2.4 produces and does not exist in the pristine file.
  it('every `find` occurs exactly `count` times at the point it is applied, in list order (spec D15)', () => {
    let out = pristine;
    for (const a of amendments()) {
      expect(out.split(a.find).length - 1, `${a.id}: find count at the point of application`).toBe(a.count);
      out = out.split(a.find).join(a.replace);
    }
    expect(out).toBe(readFileSync(AMENDED, 'utf8'));
    // The ordering dependency itself, named: A2.5 matches A2.4's output, so it cannot be counted
    // against the pristine file and the two may never be reordered.
    const list = amendments();
    const a24 = list.find((a) => a.id === 'A2.4')!; const a25 = list.find((a) => a.id === 'A2.5')!;
    expect(list.indexOf(a24)).toBeLessThan(list.indexOf(a25));
    expect(pristine.split(a25.find).length - 1, 'A2.5 is expected to be absent from the pristine file').toBe(0);
    expect(a24.replace.trim() + '\n', 'A2.5 must match what A2.4 leaves behind').toContain(a25.find.trim());
  });
  it('applyAmendments refuses a list whose `find` count does not match, naming the amendment', () => {
    const bogus = { id: 'A0', date: '2026-09-07', ruling: 'a fabricated entry', find: 'View full market report', replace: 'x', count: 2 };
    expect(() => applyAmendments(pristine, [bogus])).toThrow(/A0: expected 2 match\(es\).*found 1/);
  });
  // M7 (re-review): `setDecl`'s removal path (`value === null`) is never taken by A1 against the
  // two design files — V2 declares `text-transform`/`letter-spacing` wherever V3 does — so the
  // rule "take V2's VALUES, including its absence" was asserted by nothing. This is that case,
  // on two synthetic files: V2 lacks a declaration V3 has, so the amendment must delete it.
  it('A1 removes a declaration V3 has and V2 does not (setDecl\'s removal path)', () => {
    const v2 = '<div style="font-size: 24px; color: red">Heading</div>';
    const v3 = '<div style="font-size: 24px; text-transform: uppercase; color: red">Heading</div>';
    const a1 = deriveTypographyB(v2, v3);
    expect(a1, 'the removal path produced no amendment: V3 keeps a declaration V2 does not have').toHaveLength(1);
    expect(a1[0].find).toBe('style="font-size: 24px; text-transform: uppercase; color: red">Heading');
    expect(a1[0].replace, 'the declaration V2 does not carry must be gone').toBe('style="font-size: 24px; color: red">Heading');
    expect(applyAmendments(v3, a1)).toBe(v2);
  });
  // The other half of the same rule, and the other half of `setDecl`'s append path: V2 carries a
  // declaration V3 dropped, on a style that does NOT end in a semicolon, so the appended
  // declaration has to bring one with it. Every real A1 style ends in `;`, so this variant is
  // reachable only from a synthetic pair (M7: the engine is now inside the coverage gate).
  it('A1 adds a declaration V2 has and V3 dropped, semicolon and all', () => {
    const v2 = '<div style="font-size: 24px; color: red; text-transform: uppercase">Heading</div>';
    const v3 = '<div style="font-size: 24px; color: red">Heading</div>';
    const a1 = deriveTypographyB(v2, v3);
    expect(a1, 'V3 dropped a declaration V2 carries and no amendment was derived').toHaveLength(1);
    expect(a1[0].replace).toBe('style="font-size: 24px; color: red; text-transform: uppercase;">Heading');
    expect(applyAmendments(v3, a1)).toBe('<div style="font-size: 24px; color: red; text-transform: uppercase;">Heading</div>');
  });
  // M5 (re-review): the row regex was `^\|\s*(A\d+)\s*\|`, which required the pipe immediately
  // after the digits — it matched `| A1 |`, `| A2 |`, `| A3 |`, `| A4 |` and skipped all four
  // `| A2.2 |`–`| A2.5 |` rows. The file held eight rows and the test read four, so an `A2.6`
  // row with no code (or an `A2.6` amendment with no row) was invisible and the duplicate guard
  // covered only the top-level ids. The id set is now compared in full, both ways.
  it('LOCAL_AMENDMENTS.md carries exactly one table row per amendment id (A1 collapsed to one)', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    const rows = [...md.matchAll(/^\|\s*(A[\d.]+)\s*\|/gm)].map((m) => m[1]);
    expect(new Set(rows).size, 'an amendment is documented twice').toBe(rows.length);
    // A1 derives 24 edits (`A1.1`…`A1.24`) from ONE ruling and is documented as one row; every
    // other id is literal and must appear in the file exactly as `amendments()` spells it.
    expect(new Set(rows)).toEqual(new Set(amendments().map((a) => (a.id.startsWith('A1.') ? 'A1' : a.id))));
  });
});

/**
 * `a.find`/`a.replace` with the two declarations A1 is allowed to change removed, and the
 * whitespace those removals leave behind normalised — `setDecl` appends a declaration after a
 * space and deletes it with its leading space, so a legitimate edit differs from its source by
 * whitespace at the seam and by nothing else.
 */
function withoutTypography(s: string): string {
  return s.replace(/(text-transform|letter-spacing):\s*[^;"]*;?/g, '')
    .replace(/\s+/g, ' ').replace(/ ;/g, ';').replace(/ "/g, '"').trim();
}
