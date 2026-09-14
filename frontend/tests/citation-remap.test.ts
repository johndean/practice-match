import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { AMENDED, LOCAL_AMENDMENTS_MD, type Amendment, amendments } from './design-amendments';
import { DISTINCTIVENESS_K, citationFindings } from './amend-guard';
import {
  CITATION_PINS, CITATION_PINS_FILE, type PinTable,
  anchorLines, entriesFor, homeLine, nearest, onAnchor, outputOf, remapCitations,
} from './citation-remap';

/**
 * `npm run remap:citations` (Task HOUSEKEEPING-C item 1).
 *
 * The tool exists because three merges on 2026-09-13 re-mapped roughly 130 citations apiece by
 * hand, each with a throwaway script nobody kept. These cases are what make it trustworthy enough
 * to run unattended: it changes NOTHING on a correct ledger, it moves exactly what an insertion
 * moved, and every number it writes is one the citation gate accepts.
 *
 * THE DESIGN LINE NUMBERS IN THESE FIXTURES ARE RE-TAKEN, NOT EDITED TO PASS (feat/one-vocabulary
 * merging main, 2026-09-14). They are measured properties of the amended design — `areas: areaFc,`
 * and A24.7's and A3's own anchors — and A34 (ruling D-C51) moved them: its five dead-value
 * deletions took ten lines out above `areas: areaFc,` (V3:2542 -> 2532) while its earlier edits
 * put three lines in above A24.7 (919 -> 922) and A3 (858/872 -> 861/875). Task A39's fix round 1
 * (2026-09-14) then put A39.4's ONE line in at V3:2159, which is BELOW A24.7's anchor and ABOVE
 * the `areas:`/`communities:` pair — so that pair moved once more (2532 -> 2533) and A24.7's 922
 * did not, which is the whole reason each of these is measured rather than assumed to shift
 * together. SNAP-METRO's own A31.14g then put three comment lines into `metaSource`'s head and
 * A36 put its Users-tab edits in, both above the pair and both below A24.7, so the pair moved a
 * third time and A24.7 again did not. Each number below was
 * re-derived from the merged design through `anchorLines` itself rather than read off a failure,
 * and the relative offsets the fixtures feed in (anchor + 1, + 3, + 12) are unchanged, so every
 * rung is still exercised on the same shape it was written for. This is the merge hazard
 * HOUSEKEEPING-C item 8 un-pinned the distinctiveness table for, one file over.
 */
describe('the citation re-mapper', () => {
  const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
  const design = readFileSync(AMENDED, 'utf8');
  const list = amendments();
  const input = { md, design, list, pins: CITATION_PINS, maxOccurrences: DISTINCTIVENESS_K };

  // ---------------------------------------------------------------------------------------
  // THE IDEMPOTENCE CASE. A tool that rewrites a file every time it runs cannot be run as a
  // habit — the diff is noise and a reviewer stops reading it. RED was the committed ledger at
  // 75f0221: the first run moved TWENTY-THREE rows (twenty normalisations onto the first line of
  // the entry's own output, and three the pins corrected), and this case went green only once
  // those twenty-three were committed.
  // ---------------------------------------------------------------------------------------
  it('changes nothing on the committed ledger', () => {
    const { md: next, moves, unresolved, rows } = remapCitations(input);
    expect(unresolved).toEqual([]);
    expect(moves).toEqual([]);
    expect(next).toBe(md);
    // Not a vacuous pass: the row and citation patterns must still be matching something.
    expect(rows).toBeGreaterThan(150);
  });

  // ---------------------------------------------------------------------------------------
  // THE SYNTHETIC-INSERTION CASE — the job the tool is for, on the pair the brief names.
  //
  // A24.4 wrote `areas:` and A25.3 wrote `communities:` on the next line, a later entry's `find`
  // swallowed both, and `outputOf` therefore resolves the two ids to ONE block of which only
  // A25.3's line survives — which is why both rows cited one line and why every renumbering moved
  // them together. Pinned, they move independently and by exactly the insertion.
  //
  // The numbers below are a MEASUREMENT of this design, not constants — re-take them whenever the
  // ledger grows above them. What the case asserts, that a pinned row moves by exactly what was
  // inserted above it, never changes.
  // ---------------------------------------------------------------------------------------
  it('moves A24.4 and A25.3 by exactly what an insertion above them inserted', () => {
    const before = design.split('\n');
    expect(before[2535]).toContain('areas: areaFc,');
    expect(before[2536]).toContain('communities: comms.filter');
    for (const inserted of [1, 7, 400]) {
      const shifted = [...before.slice(0, 2000), ...Array.from({ length: inserted }, (_, i) => `// synthetic line ${i}`), ...before.slice(2000)].join('\n');
      const { md: next, unresolved } = remapCitations({ ...input, design: shifted });
      expect(unresolved).toEqual([]);
      const cited = (id: string) => Number(/V3:(\d+)/.exec(next.split('\n').find((r) => r.startsWith(`| ${id} |`)) ?? '')?.[1]);
      expect(cited('A24.4'), `A24.4 after ${inserted} inserted line(s)`).toBe(2536 + inserted);
      expect(cited('A25.3'), `A25.3 after ${inserted} inserted line(s)`).toBe(2537 + inserted);
    }
  });

  // ---------------------------------------------------------------------------------------
  // THE INVARIANT that makes the tool safe to run unattended: whatever it writes, the citation
  // gate accepts. Proved on a ledger every one of whose ROW citations has been knocked out of
  // place, so the assertion is about the tool's OUTPUT and not about the committed file already
  // being right. It is NOT asserted byte-for-byte back to the committed file, and deliberately:
  // a citation may legally name the anchor line, the one above or the one below, so an entry
  // whose own output is several adjacent lines has several correct answers and a shift of a few
  // lines can land on a different one. What must hold — the whole contract — is that the gate
  // accepts every number, and the RED for it is one line: drop the snap in `remapCitations` and
  // THIRTY-TWO of these come back stale, measured.
  // ---------------------------------------------------------------------------------------
  it('every citation it writes lands where the gate accepts it', () => {
    const bump = (line: string) => line.replace(/V3:(\d+)(?:([–-])(\d+))?/g, (_m, a: string, dash: string | undefined, b: string | undefined) =>
      `V3:${Number(a) + 9}${dash === undefined ? '' : `${dash}${Number(b) + 9}`}`);
    const scrambled = md.split('\n').map((line) => (/^\|\s*A[\w.]+\s*\|/.test(line) ? bump(line) : line)).join('\n');
    expect(scrambled, 'the scramble moved nothing — the row pattern stopped matching').not.toBe(md);
    const { md: next, unresolved, moves } = remapCitations({ ...input, md: scrambled });
    expect(unresolved).toEqual([]);
    expect(moves.length, 'a 9-line scramble must move rows back').toBeGreaterThan(150);
    const { findings, checked } = citationFindings({
      rows: next.split('\n'),
      lines: design.split('\n'),
      outputFor: (id) => {
        const own = entriesFor(id, list);
        return own.length === 0 ? null : own.flatMap((a) => outputOf(a, list));
      },
      occurrences: (piece) => design.split(piece).length - 1,
      maxOccurrences: DISTINCTIVENESS_K,
    });
    expect(findings, 'the re-mapper wrote a citation its own gate refuses').toEqual([]);
    expect(checked).toBeGreaterThan(200);
  });

  // Every pin is a JUDGEMENT and has to earn its place: it must name a line that exists, exactly
  // once, and it must belong to an id the ledger carries. A pin nobody can resolve is worse than
  // no pin, because it silently takes the row out of the derivation.
  it('every committed pin names one real line of an amendment that exists', () => {
    expect(Object.keys(CITATION_PINS).length, 'the pin file is empty — the two shared-line cases need it').toBeGreaterThan(0);
    expect(CITATION_PINS_FILE.endsWith('/tests/citation-pins.json')).toBe(true);
    for (const [id, pin] of Object.entries(CITATION_PINS)) {
      expect(entriesFor(id, list).length, `${id}: pinned but no amendment carries that id`).toBeGreaterThan(0);
      expect(design.split(pin.anchor).length - 1, `${id}: the pinned anchor is not unique`).toBe(1);
      expect(pin.why.length, `${id}: a pin must say why`).toBeGreaterThan(40);
      const home = homeLine(id, 0, input);
      expect(home.line, `${id}: the pin resolves to nothing`).not.toBeNull();
    }
  });

  // ---------------------------------------------------------------------------------------
  // The rungs, one case each, on fixtures rather than on the ledger — a rung that only ever runs
  // against real data cannot be shown to REFUSE, and refusing correctly is most of its job.
  // ---------------------------------------------------------------------------------------
  const entry = (over: Partial<Amendment>): Amendment => ({ id: 'X1', date: '2026-09-13', ruling: 'r', find: 'f', replace: 'r', count: 1, ...over });
  const row = (id: string, cite: string) => `| ${id} | 2026-09-13 | ruling | what changes (${cite}) |`;

  it('refuses a row whose id no amendment carries, and leaves the row alone', () => {
    const { md: next, unresolved, moves } = remapCitations({ ...input, md: row('A99.9', 'V3:12') });
    expect(unresolved).toEqual(['A99.9: the row cites a V3 line but no amendment carries that id']);
    expect(moves).toEqual([]);
    expect(next).toBe(row('A99.9', 'V3:12'));
  });

  it('refuses an entry whose output is nowhere distinctive in the design', () => {
    const ghost = [entry({ id: 'A98.1', replace: '\n' })];
    const { unresolved } = remapCitations({ ...input, md: row('A98.1', 'V3:5'), list: ghost, pins: {} });
    expect(unresolved).toEqual(['A98.1: nothing this amendment wrote is still distinctive in the design — pin it']);
  });

  it('refuses a pin whose anchor is not exactly one line of the design', () => {
    const pins: PinTable = { 'A24.4': { anchor: 'nowhere-at-all-in-the-design', offset: 0, why: 'fixture' } };
    const { unresolved } = remapCitations({ ...input, md: row('A24.4', 'V3:5'), pins });
    expect(unresolved).toEqual(['A24.4: the pinned anchor occurs 0 times, so it names no line — pin a distinctive one']);
  });

  it('a line the design carries twice is no anchor either', () => {
    const pins: PinTable = { 'A24.4': { anchor: '</div>', offset: 0, why: 'fixture' } };
    const { unresolved } = remapCitations({ ...input, md: row('A24.4', 'V3:5'), pins });
    expect(unresolved[0]).toMatch(/^A24\.4: the pinned anchor occurs \d+ times/);
  });

  // ---------------------------------------------------------------------------------------
  // A PIN IS AUTHORITATIVE (review, HOUSEKEEPING-C fix round 1, Important-1/Important-2). The
  // unconditional snap in `remapCitations` re-derived `anchors` for every row, pinned or not, and
  // applied `nearest` to the pin's own resolved line as if it were just another candidate — which
  // crashes outright when the entry has no anchor at all (`nearest([])`, the case a pin exists
  // FOR) and silently overrides a pin that lands more than one line from an anchor the entry does
  // have (the log said one line, the file said another).
  // ---------------------------------------------------------------------------------------
  it('a pin for an entry with no distinctive anchor of its own writes the pinned line as-is', () => {
    // Nothing this entry wrote is still distinctive anywhere — the fully-superseded case rung 1
    // exists for. Before the fix this reduces() an empty anchor array and throws.
    const ghost = [entry({ id: 'A98.2', replace: '\n' })];
    expect(anchorLines('A98.2', { design, list: ghost, maxOccurrences: DISTINCTIVENESS_K })).toEqual([]);
    const pins: PinTable = { 'A98.2': { anchor: '      areas: areaFc,', offset: 3, why: 'fixture: fully-superseded, pinned beside a neighbouring anchor' } };
    const { md: next, unresolved, moves } = remapCitations({ ...input, md: row('A98.2', 'V3:1'), list: ghost, pins });
    expect(unresolved).toEqual([]);
    expect(moves).toEqual([{ id: 'A98.2', from: 1, to: 2539, rung: 'pin' }]);
    expect(next).toBe(row('A98.2', 'V3:2539'));
  });

  it('a pin more than one line from every one of the entry\'s own anchors is refused, not silently moved', () => {
    // A24.7's own output stands once, at 922 (the "ONE anchor" case below). A pin naming a
    // completely unrelated line is not evidence of anything — silently snapping it onto 922 would
    // make the printed move log ("to: 2536") disagree with the file it wrote, which is the exact
    // defect measured on the review's own probe.
    expect(anchorLines('A24.7', input)).toEqual([922]);
    const pins: PinTable = { 'A24.7': { anchor: '      areas: areaFc,', offset: 0, why: 'fixture: nowhere near A24.7\'s own anchor at 922' } };
    const { unresolved, moves, md: next } = remapCitations({ ...input, md: row('A24.7', 'V3:1'), pins });
    expect(moves).toEqual([]);
    expect(next).toBe(row('A24.7', 'V3:1'));
    expect(unresolved[0]).toMatch(/^A24\.7: the pin resolves to V3:2536, which is not within ±1 of any of this entry's own anchors \(922\) — check the pin's anchor and offset$/);
  });

  it('an entry with ONE anchor is re-mapped whatever the row says, and a range keeps its span', () => {
    // A24.7's own output stands once in the design, so the rung never consults the number.
    const one = remapCitations({ ...input, md: row('A24.7', 'V3:1') });
    expect(one.moves).toEqual([{ id: 'A24.7', from: 1, to: 922, rung: 'only' }]);
    expect(one.md).toBe(row('A24.7', 'V3:922'));
    // A range whose SPAN the shift would carry off the end of the entry's own output is snapped
    // back onto it: A24.7 wrote ONE line, so a five-line range collapses onto that line rather
    // than pointing four lines into somebody else's edit.
    const span = remapCitations({ ...input, md: row('A24.7', 'V3:100–104') });
    expect(span.md).toBe(row('A24.7', 'V3:922–922'));
  });

  it('an entry with SEVERAL anchors takes the one nearest what the row already says', () => {
    // A3's "View full listing" stands twice: its own text node and A11's sibling button, which
    // A3's row cites deliberately. Each number keeps the anchor it was written for.
    expect(anchorLines('A3', input)).toEqual([861, 875]);
    // Both numbers move by the FIRST one's delta, and the second is snapped onto its own anchor
    // when that leaves it off one — which is what keeps A3's two citations on two lines.
    expect(remapCitations({ ...input, md: row('A3', 'V3:862 and V3:876') }).md).toBe(row('A3', 'V3:861 and V3:875'));
    expect(remapCitations({ ...input, md: row('A3', 'V3:864 and V3:887') }).md).toBe(row('A3', 'V3:861 and V3:875'));
  });

  it('A1\'s 24 derived edits are one row, and a row with no citation is untouched', () => {
    expect(entriesFor('A1', list).length).toBe(24);
    expect(entriesFor('A3', list).map((a) => a.id)).toEqual(['A3']);
    const plain = '| A3 | 2026-09-13 | ruling | no citation here |\nnot a row at all';
    expect(remapCitations({ ...input, md: plain }).md).toBe(plain);
    expect(remapCitations({ ...input, md: plain }).rows).toBe(0);
  });

  it('outputOf follows a swallowed replace forward, and stops where nothing swallowed it', () => {
    const first = entry({ id: 'X1', find: 'a', replace: 'the ruled line\n' });
    const second = entry({ id: 'X2', find: 'the ruled line\n', replace: 'what stands there now\n' });
    expect(outputOf(first, [first, second])).toEqual(['what stands there now']);
    expect(outputOf(second, [first, second])).toEqual(['what stands there now']);
    expect(outputOf(first, [first])).toEqual(['the ruled line']);
  });

  // ---------------------------------------------------------------------------------------
  // Review, HOUSEKEEPING-C fix round 1, Minor-4: `anchorLines` — an O(entries × design-lines)
  // scan with a `design.split` per candidate piece — was recomputed for every resolved row, once
  // inside `homeLine` and again immediately after for the snap. A `design.split('\n')` subclass
  // proves it: one resolved row must cost at most one scan of the whole design, not two.
  // ---------------------------------------------------------------------------------------
  it('anchorLines is computed at most once per resolved row', () => {
    let splits = 0;
    class CountingDesign extends String {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- String.split's overloads
      // do not narrow through a subclass override; the counting is what this fixture is for.
      split(separator?: any, limit?: number): string[] {
        if (separator === '\n') splits++;
        return super.split(separator, limit);
      }
    }
    // A24.7 ('only') and A3 ('nearest') between them exercise every non-pin rung that resolves.
    const md = [row('A24.7', 'V3:1'), row('A3', 'V3:859 and V3:873')].join('\n');
    const counting = new CountingDesign(design) as unknown as string;
    const { unresolved } = remapCitations({ ...input, md, design: counting });
    expect(unresolved).toEqual([]);
    expect(splits, 'anchorLines\' own design.split(\'\\n\') scan ran more than once per resolved row').toBe(2);
  });

  it('nearest takes the lower of two equidistant anchors, and onAnchor is the gate\'s own window', () => {
    expect(nearest([10, 20], 15)).toBe(10);
    expect(nearest([10, 20], 16)).toBe(20);
    expect(nearest([10], 900)).toBe(10);
    expect([9, 10, 11].map((n) => onAnchor([10], n))).toEqual([true, true, true]);
    expect([8, 12].map((n) => onAnchor([10], n))).toEqual([false, false]);
  });
});
