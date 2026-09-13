/**
 * AMEND-GUARD (Task HOUSEKEEPING-B) — no ruled text leaves the design unnamed.
 *
 * `design-amendments.test.ts` proves pristine + amendments == the amended file byte for byte, and
 * pins the count and the ids. What it CANNOT see is one entry's `find` eating text an EARLIER
 * entry's `replace` put there: the equality still holds, the counts still hold, and the sentence
 * is simply gone. That is not hypothetical — it is how A24.20's "Population growth is measured for
 * the surrounding city or county, not the tract." left the product on 2026-09-12: A24.56's `find`
 * spanned two ruled sentences of the Browse Market-data footnote and its `replace` returned one.
 * CLAUDE.md went on asserting the sentence was there; the pixel gate re-based
 * `browse-market-strip` and asked no question.
 *
 * TWO TIERS, because two different things can go missing and they do not deserve the same answer.
 * Both are ruled (Task HOUSEKEEPING-B fix round 1, 2026-09-13: the two tiers ARE the rule).
 *
 *   LINE tier — every line an entry's `replace` introduced is still in the final amended file, or a
 *   later entry's `LOCAL_AMENDMENTS.md` row says **`consumes <id>`** (or the stronger
 *   `supersedes <id>`). Most of these are lawful: a later ruling extends a handler's `setState` and
 *   the line it was written on changes shape. A written declaration is all that is asked.
 *
 *   SENTENCE tier — a ruled SENTENCE (prose: a design string literal or a text node, not code) may
 *   only leave the design if a row says **`supersedes <id>`**, or the entry that put it there says
 *   **`superseded by <id>`** — the exact shape A10 and A10.2 already carry.
 *
 * WHY A TOKEN AND NOT A MENTION. The first draft accepted the id appearing anywhere in the row.
 * This ledger's rows routinely name other ids for unrelated reasons, so 44 of the 68 consumed-line
 * pairs were "named" before anyone looked, and one row (A24.46's) was given a clause naming the
 * wrong predecessor to satisfy the guard rather than to state the fact. An incidental mention is
 * the same loophole class as the substring-matching citation gate this task closed: it certifies
 * "an id appears", not "the supersession is stated". A citation is not a declaration either — at
 * `db8bf67` A24.56's row both cited A24.20 and QUOTED the sentence it was dropping, and the
 * sentence still left the product unremarked.
 *
 * WHO MUST DECLARE: the entry that TAKES the text, and only ever one of the entries that take THAT
 * text. The first draft asked whether the id appeared in any later row at all, which meant one
 * token covered every line the entry ever lost — remove two of the three `Consumes A14.2` tokens
 * and the ledger stayed green, because a third consumer still declared (fix round 2, ruled a defect
 * on the re-review, 2026-09-13). Every consumer declares its own consumption.
 *
 * The one narrowing that keeps: two entries can introduce byte-identical lines — A24.35
 * (households) and A24.36 (income) both write
 * `source: "U.S. Census ACS 5-year estimates (2023) · Census tract",` — so that text has TWO
 * consumers and the text alone cannot say which took which. Either consumer's token counts for it,
 * which is what lets A24.46 declare A24.36 and A24.47 declare A24.35, each the one its own `find`
 * anchor addresses, instead of one row being made to state a falsehood (which is what happened at
 * A24.46 before the task review caught it).
 *
 * The logic lives here rather than inline in the test so that it can be run against a HISTORICAL
 * tree — the same code, an older ledger — which is how its RED was proved, and so that
 * `amend-guard.test.ts` can drive it over a fixture ledger that CONTAINS the defect: a guard whose
 * only gate asserts `[] === []` over a clean ledger cannot tell a working detector from a deleted
 * one (task review, Important-2).
 */
import type { Amendment } from './design-amendments';

export type GuardInput = {
  /** The entries that edit ONE bundle file, in the order they are applied (`amendmentsFor`). */
  list: Amendment[];
  /** That file's final amended text. */
  final: string;
  /** That entry's `LOCAL_AMENDMENTS.md` row, or '' where it has none. */
  rowOf: (id: string) => string;
};

/** An id, matched whole: `A24.2` must not be found inside `A24.20`, while `A10's` and a sentence
 *  ending `A10.` both still count — the boundary rejects a CONTINUATION of the id (another word
 *  character, or a dot followed by one), never the punctuation a row is written with. */
const bounded = (id: string) => `${id.replace(/\./g, '\\.')}(?!\\w|\\.\\w)`;

/** The LINE tier's token: this row declares that it took `id`'s line. `supersedes` is the stronger
 *  word and satisfies the weaker claim, so a sentence-tier row never has to say both. */
export function declaresConsumption(row: string, id: string): boolean {
  return new RegExp(`(?:consumes|supersedes)\\s+${bounded(id)}`, 'i').test(row);
}

/** The SENTENCE tier's token, on the entry that took the sentence out. */
export function declaresSupersession(row: string, id: string): boolean {
  return new RegExp(`supersedes\\s+${bounded(id)}`, 'i').test(row);
}

/** The SENTENCE tier's other direction, on the entry that put the sentence there (A10's own row). */
export function declaresSupersededBy(row: string, consumerId: string): boolean {
  return new RegExp(`superseded\\s+by\\s+${bounded(consumerId)}`, 'i').test(row);
}

/** The lines an entry's `replace` PUT there: every non-blank line of the output that is not also
 *  a line of the input it kept. A first or last fragment of a line counts, which is deliberate —
 *  many entries replace part of a line, and that part is the ruled text. */
export function introducedLines(a: Amendment): string[] {
  const kept = a.find.split('\n').map((s) => s.trim());
  return [...new Set(a.replace.split('\n').map((s) => s.trim()).filter((s) => s !== '' && !kept.includes(s)))];
}

/** The PROSE sentences in one line of design source: the contents of its double-quoted string
 *  literals (the design writes its copy in them) plus, where the line carries no code at all, the
 *  line itself (a template text node or a comment). Split at sentence ends, then kept only where
 *  the piece reads as a sentence rather than as an expression — six words or more, a full stop at
 *  the end, and none of the punctuation that only ever appears in code. */
export function ruledSentences(line: string): string[] {
  const CODE = /[{}<>=`?]|=>|\bthis\./;
  const sources = [...line.matchAll(/"([^"\\]{12,})"/g)].map((m) => m[1]);
  if (!CODE.test(line)) sources.push(line.replace(/^\/\/\s*/, ''));
  const out: string[] = [];
  for (const source of sources) {
    for (const piece of source.split(/(?<=\.)\s+/)) {
      const s = piece.trim();
      if (!/^[A-Z]/.test(s) || !s.endsWith('.') || CODE.test(s)) continue;
      if (s.split(/\s+/).length < 6) continue;
      out.push(s);
    }
  }
  return [...new Set(out)];
}

/** EVERY later entry that takes `ruled` out. Two directions, because an entry's `find` may span the
 *  whole line (it rewrites it) or sit INSIDE it (it edits part of it); in the first direction an
 *  entry whose `replace` carries the text forward has not consumed it. `count` is checked at
 *  application time by `applyAmendments`, so an overlapping `find` is an overlapping EDIT — there
 *  is no other occurrence it could have matched instead.
 *
 *  All of them, not the first: where two entries introduced byte-identical lines, the same text has
 *  two consumers and the text alone cannot say which took which. */
export function consumersOf(ruled: string, later: Amendment[]): Amendment[] {
  return later.filter((f) => (f.find.includes(ruled) && !f.replace.includes(ruled)) || ruled.includes(f.find.trim()));
}

/** The FIRST entry that takes `ruled` out — the one a finding names, since it is the one that
 *  reached the text first. */
export function consumerOf(ruled: string, later: Amendment[]): Amendment | undefined {
  return consumersOf(ruled, later)[0];
}

/** Every ruled line and ruled sentence that left the design with no entry declaring it, plus how
 *  many of each were examined (so a pass cannot be vacuous). */
export function ruledTextFindings({ list, final, rowOf }: GuardInput): { findings: string[]; lines: number; sentences: number } {
  const findings: string[] = [];
  let lines = 0;
  let sentences = 0;
  const quote = (s: string) => JSON.stringify(s.length > 120 ? `${s.slice(0, 120)}…` : s);
  list.forEach((e, i) => {
    const later = list.slice(i + 1);
    /** Did one of the entries that took THIS text declare taking it? Keyed on the (text, consumer)
     *  pair rather than on the id alone: asking whether the id appears in ANY later row let one
     *  token cover every line an entry ever lost, so a consumer that swallowed a line in silence
     *  passed because a different consumer had declared (fix round 2, ruled 2026-09-13). */
    const declaredBy = (takers: Amendment[], test: (row: string, id: string) => boolean) =>
      takers.some((f) => test(rowOf(f.id), e.id));
    for (const ruled of introducedLines(e)) {
      // The SENTENCE tier first: a line may be rewritten lawfully and still carry its sentences
      // forward, which is the A24.20/A24.56 pair as it stands on `main` today.
      for (const sentence of ruledSentences(ruled)) {
        sentences++;
        if (final.includes(sentence)) continue;
        const takers = consumersOf(sentence, later).length > 0 ? consumersOf(sentence, later) : consumersOf(ruled, later);
        const by = takers[0];
        if (by === undefined) {
          findings.push(`${e.id}: the ruled sentence ${quote(sentence)} is not in the amended design and no later entry's find touches it`);
        } else if (!declaredBy(takers, declaresSupersession) && !declaresSupersededBy(rowOf(e.id), by.id)) {
          findings.push(`${e.id} -> ${by.id}: the ruled sentence ${quote(sentence)} left the design and no row says so — a later row must say it supersedes ${e.id}, or ${e.id}'s row that it is superseded by ${by.id}`);
        }
      }
      lines++;
      if (final.includes(ruled)) continue;
      const takers = consumersOf(ruled, later);
      const by = takers[0];
      if (by === undefined) {
        findings.push(`${e.id}: ${quote(ruled)} is not in the amended design and no later entry's find touches it`);
      } else if (!declaredBy(takers, declaresConsumption)) {
        findings.push(`${e.id} -> ${by.id}: ${quote(ruled)} left the design and no LOCAL_AMENDMENTS.md row of an entry that TAKES it declares it — the entry that takes a line says it consumes ${e.id}`);
      }
    }
  });
  return { findings, lines, sentences };
}

/**
 * THE CITATION RULE (Task HOUSEKEEPING-B, tightened in fix round 1, 2026-09-13).
 *
 * Most `LOCAL_AMENDMENTS.md` rows cite the line their edit lands on (`V3:2407`), and until this
 * task NOTHING checked them: A15 inserted twelve lines into `photoSet` and every citation below it
 * silently became a pointer to the wrong line. A citation nobody can follow is worse than none.
 *
 * The rule: for every `V3:<line>` a row carries, that line of the AMENDED design — or one either
 * side of it, so a citation may name the anchor a multi-line edit starts from — must contain a
 * DISTINCTIVE line of what that amendment PUT there, and a range must not run backwards.
 *
 * DISTINCTIVE is measured against the amended design, not against the piece alone (task review,
 * Minor): the piece must carry a word token of two or more characters AND occur at most
 * `maxOccurrences` times in the whole file. The first draft asked only for the word token, which
 * let `</sc-if>` (114 occurrences), `</button>` (89), `</sc-for>` (68) and `return {` (39) anchor
 * ten live citations that could each have been dozens of lines out. `maxOccurrences` is MEASURED,
 * not chosen: at 4 every correct citation passes, at 3 four fail, at 2 seven, at 1 twenty-eight —
 * the residue being text the design genuinely repeats, like the three shared dismissal closures'
 * identical `if (this.state.giveMenu) {` heads, which the ledger cites one per closure. The table
 * is re-derived on every run rather than trusted here; to see it alone, run
 *   npx vitest run tests/design-amendments.test.ts -t "the distinctiveness threshold"
 *
 * EQUALITY was measured first and rejected. `line.trim() === piece` rejects 24 of the 211 correct
 * citations, because their entry's `replace` is a FRAGMENT of a line — A3's text node, A10's two
 * string literals, A26.16's one declaration — and a fragment can never equal a whole line of the
 * file. (47 is the figure the first draft quoted; it is what equality rejects on the PRE-FIX
 * ledger, where 23 of the rejections were stale citations rather than fragments, and it overstates
 * the population this argument rests on by 23.)
 *
 * Two shapes need care, and neither is skipped:
 *   * A SUPERSEDED amendment has no output of its own left in the file. Its row is validated
 *     against the text that stands at its site today — what a reader following the citation will
 *     actually see — by following the chain forward, which is what `outputFor` does.
 *   * A pure REMOVAL amendment has no output to point at and must not carry a citation at all.
 */
export type CitationInput = {
  /** Every line of `LOCAL_AMENDMENTS.md`; rows are recognised by their leading `| A<id> |`. */
  rows: string[];
  /** Every line of the amended design file. */
  lines: string[];
  /** What stands at that amendment's site today, one entry per line; `null` for an unknown id. */
  outputFor: (id: string) => string[] | null;
  /** How many times a piece occurs in the whole amended design. */
  occurrences: (piece: string) => number;
  /** The measured distinctiveness threshold. */
  maxOccurrences: number;
};

export function citationFindings({ rows, lines, outputFor, occurrences, maxOccurrences }: CitationInput): { findings: string[]; checked: number } {
  const findings: string[] = [];
  let checked = 0;
  for (const row of rows) {
    const id = /^\|\s*(A[\w.]+)\s*\|/.exec(row)?.[1];
    if (id === undefined) continue;
    // BOTH ENDS of a range, not only the first number: `V3:1974–1969` and `V3:2613-2431` both stood
    // in this file with an end left behind by an earlier re-map, and both passed.
    const spans = [...row.matchAll(/V3:(\d+)(?:[–-](\d+))?/g)].map((c) => [Number(c[1]), c[2] === undefined ? null : Number(c[2])] as const);
    if (spans.length === 0) continue;
    const output = outputFor(id);
    if (output === null) {
      findings.push(`${id}: the row cites a V3 line but no amendment carries that id`);
      continue;
    }
    if (output.length === 0) {
      findings.push(`${id}: a removal amendment puts nothing at a line, so its row may not cite one`);
      continue;
    }
    const distinctive = output.filter((p) => /[A-Za-z0-9]{2,}/.test(p) && occurrences(p) <= maxOccurrences);
    for (const [start, end] of spans) {
      if (end !== null && end < start) {
        findings.push(`${id}: V3:${start}–${end} runs backwards — a range ends at or after it starts`);
      }
      for (const n of end === null ? [start] : [start, end]) {
        checked++;
        const window = [n - 1, n, n + 1].map((k) => lines[k - 1] ?? '');
        if (!window.some((line) => distinctive.some((piece) => line.includes(piece)))) {
          findings.push(`${id}: V3:${n} is stale — no line of the amended design there carries a distinctive line of this amendment's own output`);
        }
      }
    }
  }
  return { findings, checked };
}
