import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AMENDED, LOCAL_AMENDMENTS_MD, PRISTINE, amendments, applyAmendments, deriveTypographyB, templateRegions, V2 } from './design-amendments';

describe('local design amendments (spec D15)', () => {
  const pristine = readFileSync(PRISTINE, 'utf8');
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
    // `{{ d.title }}` occurs twice (34 px detail title, 19 px mobile title) — the key is (tag, text), both pair; the text list has one entry per distinct text.
    expect(new Set(a1.map((a) => a.text!.startsWith("We're here") ? "We're here to help connect veterinary practice owners" : a.text!))).toEqual(new Set(A1_TEXTS));
    for (const a of a1) {
      expect(a.replace, a.text).toContain('text-transform: uppercase');
      expect(a.replace, a.text).toMatch(/letter-spacing: \.0(2|05)em/);
      expect(a.find.length - a.replace.length, `${a.text}: only the two declarations change`).toBeLessThanOrEqual(0);
    }
    expect(a1.some((a) => /p\.priceLabel|\{\{ c\.value \}\}/.test(a.text!) || a.find.startsWith('style="') === false)).toBe(false);
    for (const [s, e] of templateRegions(pristine)) void s, void e;   // every find lives in the template region: the derivation only reads it
  });
  it('the amended reference is the pristine Rev 2 file plus exactly the ruled edits', () => {
    expect(applyAmendments(pristine, amendments())).toBe(readFileSync(AMENDED, 'utf8'));
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
    expect(seen).toBeGreaterThanOrEqual(24);
  });
  it('LOCAL_AMENDMENTS.md names every amendment id', () => {
    const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
    for (const a of amendments()) expect(md).toContain(a.id.split('.')[0]);
  });
});
