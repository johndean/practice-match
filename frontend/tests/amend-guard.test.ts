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
  citationFindings, commentCitations, consumerOf, declaresConsumption, declaresSupersededBy,
  declaresSupersession, introducedLines, ruledSentences, ruledTextFindings,
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

  // …and the ONE narrowing that keeps, as CODED: where a consumed line has SEVERAL takers, any one
  // of them may declare it. Four consumed lines in this ledger have more than one, of two kinds —
  // this case is the FIRST kind, byte-identical lines introduced by two entries (A24.35's and
  // A24.36's `source:` lines), where the guard cannot tell which taker took which, so either
  // token counts and A24.46 declares A24.36 while A24.47 declares A24.35, each the id its own
  // `find` anchor addresses, instead of one row being made to state a falsehood. The second kind
  // — long lines several later finds sit inside — has its own case below.
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

  // The SECOND kind of multi-taker line (round-2 re-review, Minor): a line long enough that several
  // later `find`s sit INSIDE it, each addressing a different part. A5.6's and A5.7's escaped
  // `data-props` JSON lines are 614 and 528 characters and are taken that way — A5.6's by A5.7 and
  // A8.8a, A5.7's by A8.8a and A8.8b. The declaring taker need not be the first one the guard
  // finds, so the narrowing is asked of the SECOND here.
  it('accepts the token from a later taker when several finds sit inside one long line', () => {
    const long = `  props: { ${'alpha: "one", '.repeat(8)}beta: "two", gamma: "three" },`;
    const first = entry('F1', 'props: {},', long);
    const takerA = entry('F2', 'beta: "two"', 'beta: "TWO"');
    const takerB = entry('F3', 'gamma: "three"', 'gamma: "THREE"');
    const out = ruledTextFindings({
      list: [first, takerA, takerB],
      final: long.replace('beta: "two"', 'beta: "TWO"').replace('gamma: "three"', 'gamma: "THREE"'),
      // The SECOND taker declares; the first says nothing.
      rowOf: (id) => (id === 'F3' ? '| F3 | … | Consumes F1. |' : ''),
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

/**
 * `commentCitations` — the doc-comment half of the citation rule (Task HOUSEKEEPING-C item 4).
 *
 * The real file it guards carries NONE, which is again a gate that would pass with its detector
 * deleted, so every shape it has to tell apart is here on a fixture: a line comment, a block
 * comment, and the three kinds of string literal it must NOT read — one of which really does carry
 * a `V3:` reference in the live file, because that string is design bytes.
 */
describe('commentCitations', () => {
  it('reports a line number in a line comment and in a block comment, with its line', () => {
    expect(commentCitations('const a = 1;\n// see V3:2408 for this\n')).toEqual(['2: V3:2408']);
    expect(commentCitations('/** a\n *  b V3:10 and V3:20\n */')).toEqual(['1: V3:10', '1: V3:20']);
  });

  it('reads no string literal — the one live reference is an amendment\'s own design bytes', () => {
    expect(commentCitations('const s = "// V3:1";')).toEqual([]);
    expect(commentCitations("const s = '  // arrow (V3:382\\'s own trio).';")).toEqual([]);
    expect(commentCitations('const s = `V3:1 ${x} V3:2`;')).toEqual([]);
  });

  it('does not run off the end of an unterminated comment or string', () => {
    expect(commentCitations('// V3:7')).toEqual(['1: V3:7']);
    expect(commentCitations('/* V3:7')).toEqual(['1: V3:7']);
    expect(commentCitations('const s = "V3:7')).toEqual([]);
  });

  it('a division and a lone quote inside a comment are not comment openers', () => {
    expect(commentCitations('const a = b / c; // V3:9')).toEqual(['1: V3:9']);
    expect(commentCitations("// don't V3:9")).toEqual(['1: V3:9']);
  });

  // Review, HOUSEKEEPING-C fix round 1, Minor-1: `design-amendments.ts:34`'s own STYLED regex,
  // `/<(\w+)([^>]*?)style="([^"]*)"([^>]*)>([^<]{0,120})/g`, carries THREE `"` characters — one
  // in `style="`, one inside the character class `[^"]`, one closing it — and the scanner treats
  // every `"` as a string delimiter with no notion of a regex literal at all. The first pair reads
  // as a two-character "string" (`[^`) and is harmless; the THIRD `"` then opens a string with no
  // partner on the rest of the line, so the scanner hunts forward for the next literal `"`
  // anywhere in the file — past every `//` and `/*` it crosses on the way — and silently drops
  // every `V3:` a comment in between carries. Measured against the real file: lines 34-58.
  it('a regex literal carrying an odd number of quote characters does not desynchronise the scanner', () => {
    const styled = 'const STYLED = /<(\\w+)([^>]*?)style="([^"]*)"([^>]*)>([^<]{0,120})/g;';
    expect(commentCitations(`${styled}\n// V3:999\n`)).toEqual(['2: V3:999']);
  });

  it('a bare division is still not mistaken for the start of a regex literal', () => {
    // `/` after an identifier or a closing paren is division, not a regex — a scanner that opens a
    // regex here would swallow the rest of the line (and beyond) looking for a closing `/`.
    expect(commentCitations('const half = total / 2; // V3:1\n')).toEqual(['1: V3:1']);
  });

  it('division after a closing paren is not mistaken for a regex either', () => {
    // Neither an operator/bracket nor a word character precedes this `/` — a scanner that only
    // checked "is it a word character" would wrongly open a regex here, consume the FIRST `/` of
    // the following `//` comment as this "regex"'s own closing delimiter, and the comment (and its
    // V3:) would never be recognised as a comment at all.
    expect(commentCitations('const x = (a + b) / 2; // V3:2\n')).toEqual(['1: V3:2']);
  });

  it('a regex literal at the very start of the file is still recognised as one', () => {
    // Nothing precedes this `/` at all — the "walked back past the start of the file" case.
    expect(commentCitations('/^x$/.test(1);\n// V3:3\n')).toEqual(['2: V3:3']);
  });

  it('a `/` that opens a regex context but never closes before the line ends falls back to an ordinary character', () => {
    // `=` puts this `/` in regex context, but the line ends with no closing `/` — malformed, or a
    // division whose left-hand side just happens to be spelled like a pattern start. Either way
    // the scanner must not treat it as an unterminated regex and skip past everything after it.
    expect(commentCitations('const s = /never closes\n// V3:5\n')).toEqual(['2: V3:5']);
  });
});

// ---------------------------------------------------------------------------------------
// ONE DEFINITION (review, HOUSEKEEPING-C fix round 1, Important-4). `entriesFor`, `outputOf` and
// the distinctiveness predicate used to be a second copy in `citation-remap.ts` and a third in two
// closures inside `design-amendments.test.ts`'s own citation cases. They live here now, and
// `citation-remap.ts` imports and re-exports them rather than re-deriving its own — proved by
// identity, not merely by behaviour, since two functions can behave alike and still be two
// functions someone has to remember to change together.
// ---------------------------------------------------------------------------------------
// ---------------------------------------------------------------------------------------
// Round 2 (re-review, Minor, 2026-09-13): the first scan matched only `function outputOf(` /
// `function entriesFor(`, so a copy re-introduced in ARROW form (`const outputOf = (a: Amendment):
// string[] => …`) — or as a class/object METHOD — passed it silently: exactly the shape this
// task deleted, and the one most likely to come back, since nothing else in the toolchain objects
// to a second binding of the same name in a different file. Proved BEFORE the fix (the round's own
// RED): a real file at this path, carrying nothing but the one line
// `export const outputOf = (a: { replace: string }): string[] => a.replace.split('\n');`, left the
// old scan green — the escape this widened one closes.
//
// `declaresIdentifier` recognises the three shapes a JS/TS BINDING is created by — a function
// declaration, a const/let/var assignment (arrow or function expression), or a method (class or
// object literal) — and none of a call, an import or a re-export: a call is never followed
// immediately by `{` or `:` after its own closing paren, which is what keeps the method-shorthand
// half of the pattern from matching one.
// ---------------------------------------------------------------------------------------
function declaresIdentifier(src: string, name: string): boolean {
  const n = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`\\bfunction\\s+${n}\\s*\\(|\\b(?:const|let|var)\\s+${n}\\s*=|\\b${n}\\s*\\([^)]*\\)\\s*[:{]`).test(src);
}

describe('declaresIdentifier recognises every declaration shape, not just `function name(`', () => {
  it('matches a function declaration, a const/let arrow or function expression, and a method shorthand', () => {
    expect(declaresIdentifier('function outputOf(a) { return a; }', 'outputOf')).toBe(true);
    expect(declaresIdentifier('export function outputOf(a) { return a; }', 'outputOf')).toBe(true);
    expect(declaresIdentifier('const outputOf = (a: Amendment): string[] => a.replace.split("\\n");', 'outputOf')).toBe(true);
    expect(declaresIdentifier('export const outputOf = (a) => a;', 'outputOf')).toBe(true);
    expect(declaresIdentifier('let outputOf = (a) => a;', 'outputOf')).toBe(true);
    expect(declaresIdentifier('const outputOf = function (a) { return a; };', 'outputOf')).toBe(true);
    expect(declaresIdentifier('class X { outputOf(a) { return a; } }', 'outputOf')).toBe(true);
  });

  it('does not mistake a CALL, an IMPORT or a RE-EXPORT for a declaration', () => {
    expect(declaresIdentifier('own.flatMap((a) => outputOf(a, list))', 'outputOf')).toBe(false);
    expect(declaresIdentifier('export { entriesFor, outputOf };', 'outputOf')).toBe(false);
    expect(declaresIdentifier("import { outputOf } from './amend-guard';", 'outputOf')).toBe(false);
    expect(declaresIdentifier('const own = entriesFor(id, list);', 'entriesFor')).toBe(false);
    expect(declaresIdentifier('if (entriesFor(id, input.list).length === 0) { return null; }', 'entriesFor')).toBe(false);
  });

  it('RED reproduced: the old function-only pattern missed exactly this arrow-form copy', () => {
    const arrowCopy = 'const outputOf = (a: Amendment): string[] => a.replace.split("\\n");';
    expect(/\bfunction outputOf\(/.test(arrowCopy), 'the old pattern (kept here as documentation of the defect) really did miss this').toBe(false);
    expect(declaresIdentifier(arrowCopy, 'outputOf'), 'the widened scan catches it').toBe(true);
  });
});

describe('entriesFor, outputOf and isDistinctivePiece are shared, not duplicated', () => {
  it('citation-remap.ts re-exports the SAME function objects, not a second copy', async () => {
    const guard = await import('./amend-guard');
    const remap = await import('./citation-remap');
    expect(remap.entriesFor).toBe(guard.entriesFor);
    expect(remap.outputOf).toBe(guard.outputOf);
  });

  it('no other test file under frontend/tests declares entriesFor, outputOf or isDistinctivePiece — in ANY form', async () => {
    const { readdirSync, readFileSync } = await import('node:fs');
    const { join, basename } = await import('node:path');
    const { fileURLToPath } = await import('node:url');
    const dir = fileURLToPath(new URL('.', import.meta.url));
    // This file itself is excluded: its own fixture strings above are EXAMPLES of the declaration
    // shapes `declaresIdentifier` recognises, quoted as test data, not real bindings — a whole-file
    // text scan cannot tell the two apart, and it is the one file guaranteed to carry both.
    const self = basename(fileURLToPath(import.meta.url));
    const files = readdirSync(dir).filter((f) => f.endsWith('.ts') && f !== self);
    const contents = new Map(files.map((f) => [f, readFileSync(join(dir, f), 'utf8')]));
    const declaresIn = (name: string) => files.filter((f) => declaresIdentifier(contents.get(f)!, name));
    expect(declaresIn('entriesFor').sort()).toEqual(['amend-guard.ts']);
    expect(declaresIn('outputOf').sort()).toEqual(['amend-guard.ts']);
    expect(declaresIn('isDistinctivePiece').sort()).toEqual(['amend-guard.ts']);
    // The inline predicate itself is gone from everywhere but its one definition — a file could
    // still keep the OLD literal expression under a different name and pass the checks above.
    const declaresPattern = (pattern: RegExp) => files.filter((f) => pattern.test(contents.get(f)!));
    expect(declaresPattern(/\[\^A-Za-z0-9\]\{2,\}|A-Za-z0-9\]\{2,\}/).sort()).toEqual(['amend-guard.ts']);
  });
});
