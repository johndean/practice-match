/**
 * AMEND-GUARD's own unit, on a FIXTURE ledger (task review, Important-2).
 *
 * The guard runs over the real 303-entry ledger in `design-amendments.test.ts`, where it finds
 * nothing — which is the point, and also the problem: deleting either tier's `findings.push` left
 * that case green, because a gate that asserts `[] === []` cannot tell a working detector from a
 * deleted one. Every case below is MUTATION-SHAPED: it hands the same pure functions a small
 * synthetic ledger that CONTAINS the defect, so removing a tier, loosening a token or dropping a
 * branch turns one of these red.
 *
 * The fixture is a two-line design and three entries, which is enough to express every shape the
 * real ledger has: an entry that adds a line, a later entry that swallows it, and a row that either
 * declares the consumption or does not.
 */
import { describe, expect, it } from 'vitest';
import type { Amendment } from './design-amendments';
import {
  citationFindings, consumerOf, declaresConsumption, declaresSupersededBy, declaresSupersession,
  introducedLines, ruledSentences, ruledTextFindings,
} from './amend-guard';

const entry = (id: string, find: string, replace: string): Amendment =>
  ({ id, date: '2026-09-13', ruling: `fixture ${id}`, find, replace, count: 1 });

/** A ledger whose second entry swallows the line the first introduced. `final` is what the design
 *  looks like after both have run, so the first entry's line is genuinely gone. */
const consumedLine = {
  first: entry('F1', 'const a = 1;', 'const a = 1;\n  keep: "kept",\n  gone: "taken later",'),
  second: entry('F2', 'gone: "taken later",', 'gone: "replaced",'),
  final: 'const a = 1;\n  keep: "kept",\n  gone: "replaced",\n',
};

/** The same shape one tier up: what the first entry introduced is a SENTENCE of ruled prose. */
const consumedSentence = {
  first: entry('F1', 'note: "",', 'note: "Population growth is measured for the surrounding city, not the tract.",'),
  second: entry('F2', 'note: "Population growth is measured for the surrounding city, not the tract.",', 'note: "Something else entirely, in different words.",'),
  final: 'note: "Something else entirely, in different words.",\n',
};

const run = (fixture: { first: Amendment; second: Amendment; final: string }, rows: Record<string, string>) =>
  ruledTextFindings({
    list: [fixture.first, fixture.second],
    final: fixture.final,
    rowOf: (id) => rows[id] ?? '',
  });

describe('the LINE tier', () => {
  it('reports a consumed line no later row declares', () => {
    const out = run(consumedLine, {});
    expect(out.findings).toHaveLength(1);
    expect(out.findings[0]).toContain('F1 -> F2');
    expect(out.findings[0]).toContain('taken later');
    expect(out.findings[0]).toContain('says it consumes F1');
  });

  // The loophole this round closes (task review, Minor): 44 of the 68 real consumed-line pairs were
  // "named" by an id that happened to appear in the row for an unrelated reason, and that is how
  // A24.46's row came to state a false predecessor. A mention is not a statement.
  it('is NOT satisfied by a bare mention of the consumed entry\'s id', () => {
    const out = run(consumedLine, { F2: '| F2 | 2026-09-13 | fixture | Written the way F1 was, for the same reason. |' });
    expect(out.findings, 'a bare id mention still satisfies the line tier').toHaveLength(1);
  });

  it('is satisfied by the explicit `consumes <id>` token', () => {
    expect(run(consumedLine, { F2: '| F2 | … | Consumes F1 — its own line, replaced here. |' }).findings).toEqual([]);
  });

  // `supersedes` is the stronger of the two words and satisfies the weaker claim, so a sentence-tier
  // row never has to say both.
  it('is satisfied by `supersedes <id>` too', () => {
    expect(run(consumedLine, { F2: '| F2 | … | Supersedes F1. |' }).findings).toEqual([]);
  });

  // A later entry that does NOT take this line cannot speak for the one that does (fix round 2).
  // F3 takes what F2 left, so F2 owes the declaration for F1's line and F3 owes one for F2's.
  it('refuses a token from a later entry that did not take this line', () => {
    const third = entry('F3', 'gone: "replaced",', 'gone: "replaced once more",');
    const out = ruledTextFindings({
      list: [consumedLine.first, consumedLine.second, third],
      final: 'const a = 1;\n  keep: "kept",\n  gone: "replaced once more",\n',
      rowOf: (id) => (id === 'F3' ? '| F3 | … | Consumes F1. Consumes F2. |' : ''),
    });
    expect(out.findings).toHaveLength(1);
    expect(out.findings[0]).toContain('F1 -> F2');
  });

  // Fix round 2 (controller, 2026-09-13, ruled a defect on the re-review's observation). The first
  // draft asked "does SOME later row declare this id?", so one token covered every line the entry
  // ever lost: removing two of the three `Consumes A14.2` tokens left the real ledger green,
  // because a THIRD consumer still declared. Every consumer declares its OWN consumption, so the
  // question is asked of the entries that took THIS line.
  it('asks each consumer for its own token, not the entry\'s id anywhere later', () => {
    const first = entry('F1', 'a', 'a\n  one: "taken by F2",\n  two: "taken by F3",');
    const second = entry('F2', 'one: "taken by F2",', 'one: "replaced",');
    const third = entry('F3', 'two: "taken by F3",', 'two: "replaced",');
    const out = ruledTextFindings({
      list: [first, second, third],
      final: 'a\n  one: "replaced",\n  two: "replaced",\n',
      // F2 declares; F3 does not. F3's silence is the finding — the old rule let F2's token cover it.
      rowOf: (id) => (id === 'F2' ? '| F2 | … | Consumes F1. |' : ''),
    });
    expect(out.findings).toHaveLength(1);
    expect(out.findings[0]).toContain('F1 -> F3');
  });

  // …and the ONE narrowing that keeps: where two entries introduced byte-identical lines (A24.35's
  // and A24.36's `source:` lines), the same text has TWO consumers and the guard cannot tell which
  // took which. Either consumer's token counts for that line, which is what lets A24.46 declare
  // A24.36 and A24.47 declare A24.35 — each the one its own `find` anchor addresses — instead of
  // one row being made to state a falsehood.
  it('accepts the token from any entry that consumes THAT line, when a line has several', () => {
    const alpha = entry('F1', 'a', 'a\n  same: "identical",');
    const beta = entry('F2', 'b', 'b\n  same: "identical",');
    const consumerA = entry('F3', 'a\n  same: "identical",', 'a\n  same: "A took it",');
    const consumerB = entry('F4', 'b\n  same: "identical",', 'b\n  same: "B took it",');
    const out = ruledTextFindings({
      list: [alpha, beta, consumerA, consumerB],
      final: 'a\n  same: "A took it",\nb\n  same: "B took it",\n',
      rowOf: (id) => (id === 'F3' ? '| F3 | … | Consumes F1. |' : id === 'F4' ? '| F4 | … | Consumes F2. |' : ''),
    });
    expect(out.findings).toEqual([]);
  });

  it('does not mistake a longer id for the one it names', () => {
    expect(run(consumedLine, { F2: '| F2 | … | Consumes F10. |' }).findings).toHaveLength(1);
  });

  it('reports a line that vanished with no later entry touching it', () => {
    const out = ruledTextFindings({ list: [consumedLine.first], final: 'const a = 1;\n', rowOf: () => '' });
    expect(out.findings).toHaveLength(2);
    expect(out.findings.every((f) => f.includes('no later entry\'s find touches it'))).toBe(true);
  });

  // The message truncates a long line so a run of findings stays readable.
  it('elides a consumed line longer than 120 characters', () => {
    const long = `gone: "${'x'.repeat(140)}",`;
    const out = ruledTextFindings({
      list: [entry('F1', 'a', `a\n  ${long}`), entry('F2', long, 'gone: "",')],
      final: 'a\n  gone: "",\n',
      rowOf: () => '',
    });
    expect(out.findings[0]).toContain('…');
    expect(out.findings[0].length).toBeLessThan(long.length + 200);
  });

  it('counts what it walked, and says nothing about a line that is still there', () => {
    const out = ruledTextFindings({
      list: [consumedLine.first],
      final: 'const a = 1;\n  keep: "kept",\n  gone: "taken later",\n',
      rowOf: () => '',
    });
    expect(out.findings).toEqual([]);
    expect(out.lines).toBe(2);
    expect(out.sentences).toBe(0);
  });
});

describe('the SENTENCE tier', () => {
  it('reports a consumed ruled sentence no row declares', () => {
    const out = run(consumedSentence, {});
    expect(out.findings.filter((f) => f.includes('ruled sentence'))).toHaveLength(1);
    expect(out.findings[0]).toContain('Population growth is measured');
  });

  // A citation is not a supersession. At `db8bf67` A24.56's row both CITED A24.20 and QUOTED the
  // sentence it was dropping, and the sentence still left the product unremarked, so the sentence
  // tier takes only the ledger's own A10/A10.2 vocabulary.
  it('is NOT satisfied by `consumes <id>`, only by the supersession vocabulary', () => {
    const out = run(consumedSentence, { F2: '| F2 | … | Consumes F1. |' });
    expect(out.findings.filter((f) => f.includes('ruled sentence')), 'the weaker token satisfied the sentence tier').toHaveLength(1);
  });

  it('is satisfied by `supersedes <id>` on the entry that took it out', () => {
    expect(run(consumedSentence, { F2: '| F2 | … | Supersedes F1\'s own sentence. |' }).findings).toEqual([]);
  });

  // The sentence tier alone: the LINE the sentence sits on is consumed too, and the line tier asks
  // for its own token on a LATER row, which this fixture deliberately does not have.
  it('is satisfied by `superseded by <id>` on the entry that put it there (A10\'s own shape)', () => {
    const out = run(consumedSentence, { F1: '| F1 | … | Superseded by F2 (2026-09-13). |' });
    expect(out.findings.filter((f) => f.includes('ruled sentence'))).toEqual([]);
  });

  it('reports a sentence that vanished with no later entry touching it', () => {
    const out = ruledTextFindings({ list: [consumedSentence.first], final: 'note: "",\n', rowOf: () => '' });
    expect(out.findings.filter((f) => f.includes('ruled sentence'))).toHaveLength(1);
    expect(out.findings.some((f) => f.includes('no later entry\'s find touches it'))).toBe(true);
  });
});

describe('what counts as a ruled sentence', () => {
  it('reads the prose out of a string literal and leaves the code alone', () => {
    expect(ruledSentences('body: "The property is accurately mapped, but nothing else is shown.",'))
      .toEqual(['The property is accurately mapped, but nothing else is shown.']);
  });

  it('takes a whole line that is prose, comment marker and all', () => {
    expect(ruledSentences('// Every figure describes the area around the practice, never the practice.'))
      .toEqual(['Every figure describes the area around the practice, never the practice.']);
  });

  it('splits a literal carrying two sentences into two', () => {
    expect(ruledSentences('t: "Community areas here are Census tracts. Growth is measured for the city instead.",'))
      .toEqual(['Community areas here are Census tracts.', 'Growth is measured for the city instead.']);
  });

  it('rejects an expression, a fragment and anything too short to be a ruling', () => {
    // A ternary that happens to end in a full stop; a lower-case fragment; five words.
    expect(ruledSentences('valueNote: sel ? locBasis : (sum ? "metro median" : "none"),')).toEqual([]);
    expect(ruledSentences('x: "and then the rest of it follows.",')).toEqual([]);
    expect(ruledSentences('x: "Five short words end here.",')).toEqual([]);
    expect(ruledSentences('x: "A sentence with no full stop at the end",')).toEqual([]);
  });

  it('never returns the same sentence twice', () => {
    expect(ruledSentences('a: "One sentence that is repeated here.", b: "One sentence that is repeated here.",'))
      .toEqual(['One sentence that is repeated here.']);
  });
});

describe('the primitives', () => {
  it('introducedLines is the replace minus the lines the find kept, blanks dropped', () => {
    expect(introducedLines(entry('X', 'a\nb', 'a\n\nb\nc\nc'))).toEqual(['c']);
  });

  it('consumerOf takes an entry whose find spans the text, unless its replace carries it forward', () => {
    const keeps = entry('K', 'x\ngone\ny', 'x\ngone\nz');
    const takes = entry('T', 'x\ngone\ny', 'x\nz');
    expect(consumerOf('gone', [keeps, takes])?.id).toBe('T');
  });

  it('consumerOf takes an entry whose find sits INSIDE the text', () => {
    expect(consumerOf('  const a = 1, b = 2;', [entry('T', 'b = 2', 'b = 3')])?.id).toBe('T');
  });

  it('consumerOf finds nothing when nothing overlaps', () => {
    expect(consumerOf('untouched', [entry('T', 'elsewhere', 'other')])).toBeUndefined();
  });

  it('the three declarations read their own token and no other', () => {
    expect(declaresConsumption('Consumes A24.36 here.', 'A24.36')).toBe(true);
    expect(declaresConsumption('Supersedes A24.36 here.', 'A24.36')).toBe(true);
    expect(declaresConsumption('Chained on A24.36 here.', 'A24.36')).toBe(false);
    expect(declaresSupersession('Supersedes A10 outright.', 'A10')).toBe(true);
    expect(declaresSupersession('Consumes A10 outright.', 'A10')).toBe(false);
    expect(declaresSupersededBy('Superseded by A10.2 (2026-09-08).', 'A10.2')).toBe(true);
    expect(declaresSupersededBy('Superseded by A10.25 (2026-09-08).', 'A10.2')).toBe(false);
  });
});

// ---------------------------------------------------------------------------------------------
// THE CITATION RULE, on a fixture ledger. Three staleness classes were found on the real ledger
// when the rule first ran, and each is pinned here as a case the gate MUST reject — the real
// ledger is clean, so nothing about it can prove the detector still works (task review,
// Important-2's shape applied to the second gate).
// ---------------------------------------------------------------------------------------------
describe('the citation rule', () => {
  // A 40-line design: one distinctive line the entry produced, at line 10, and a brace-heavy
  // block of the kind that let a stale citation pass for days.
  // The filler is `</sc-if>`, the design's most repeated closing tag (114 real occurrences) and a
  // line the entry below genuinely produced — which is exactly how ten live citations came to be
  // anchored on nothing: it carries a word token, so the FIRST draft of the rule accepted it.
  const lines = Array.from({ length: 40 }, (_, i) =>
    i + 1 === 10 ? '      areas: this.areaVals(this.areaSet(valueLayer), valueLayer),'
      : i + 1 === 11 ? '      const asked = market;' : '  </sc-if>');
  const design = lines.join('\n');
  const cite = (row: string) => citationFindings({
    rows: [row],
    lines,
    outputFor: (id) => (id === 'A99' ? ['areas: this.areaVals(this.areaSet(valueLayer), valueLayer),', '</sc-if>'] : id === 'AREMOVAL' ? [] : null),
    occurrences: (p) => design.split(p).length - 1,
    maxOccurrences: 4,
  });

  it('accepts a citation that lands on a distinctive line of the entry\'s own output', () => {
    expect(cite('| A99 | … | One script literal (V3:10). |').findings).toEqual([]);
  });

  it('accepts the ANCHOR a multi-line edit starts from, one line either side', () => {
    expect(cite('| A99 | … | One script literal (V3:11). |').findings).toEqual([]);
  });

  // Class 1 — pointing into another block (A19.2 @ the `stripCards` bar line, A12.3's shape):
  // the cited line shares only a brace with the entry's output, and a brace is everywhere.
  it('rejects a citation anchored on a line the design repeats (the A19.2 class)', () => {
    const out = cite('| A99 | … | One script literal (V3:30). |');
    expect(out.findings).toHaveLength(1);
    expect(out.findings[0]).toContain('V3:30 is stale');
  });

  // Class 2 — pointing at a neighbouring function (A24.15/A24.21's shape): a real line, inside
  // the same file, a few lines from the edit — and nothing of the entry's own on it.
  it('rejects a citation on a neighbouring line that carries none of the entry\'s output', () => {
    expect(cite('| A99 | … | One script literal (V3:13). |').findings[0]).toContain('V3:13 is stale');
  });

  // Class 3 — a backwards range (A26.1's `V3:2221–2197`, A26.2's `V3:3973–3969`, A24.21's
  // `V3:2103–2073`): both ends can be valid lines and the range still be unreadable.
  it('rejects a range written backwards even when both ends are right', () => {
    const out = cite('| A99 | … | One script literal (V3:11–10). |');
    expect(out.findings.some((f) => f.includes('runs backwards'))).toBe(true);
  });

  it('reads BOTH ends of a range, not only the first', () => {
    expect(cite('| A99 | … | One script literal (V3:10–30). |').findings[0]).toContain('V3:30 is stale');
    expect(cite('| A99 | … | One script literal (V3:10–11). |').findings).toEqual([]);
  });

  it('refuses a citation on a row whose id carries no amendment, and on a pure removal', () => {
    expect(cite('| A98 | … | (V3:10) |').findings[0]).toContain('no amendment carries that id');
    expect(cite('| AREMOVAL | … | (V3:10) |').findings[0]).toContain('a removal amendment puts nothing at a line');
  });

  it('ignores a row with no citation, and anything that is not a row', () => {
    expect(cite('| A99 | … | no line named here. |').checked).toBe(0);
    expect(cite('some prose about V3:10 outside the table').checked).toBe(0);
  });

  it('rejects a citation past the end of the file rather than reading undefined', () => {
    expect(cite('| A99 | … | (V3:900) |').findings[0]).toContain('V3:900 is stale');
  });

  it('counts every citation it checked, so a pass cannot be vacuous', () => {
    expect(cite('| A99 | … | (V3:10) and (V3:10–11). |').checked).toBe(3);
  });
});
