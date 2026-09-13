/**
 * AMEND-GUARD (Task HOUSEKEEPING-B, item 2) — no ruled text leaves the design unnamed.
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
 *
 *   LINE tier — every line an entry's `replace` introduced is still in the final amended file, or
 *   the later entry that consumed it NAMES the superseded entry in its own `LOCAL_AMENDMENTS.md`
 *   row. Most of these are lawful: a later ruling extends a handler's `setState` and the line it
 *   was written on changes shape. Naming is all that is asked, so the chain is one a reader of the
 *   ledger can follow rather than something only the diff knows.
 *
 *   SENTENCE tier — a ruled SENTENCE (prose: a design string literal or a text node, not code) may
 *   only leave the design if the removal is stated in the ledger's own supersession vocabulary:
 *   `supersedes <id>` on the entry that took it out, or `superseded by <id>` on the entry that put
 *   it there — the exact shape A10 and A10.2 already carry. A citation alone is NOT enough here,
 *   and that is the whole lesson of A24.56: its row said "CHAINED on A24.20" and even QUOTED the
 *   sentence it was dropping, and the sentence still left the product unremarked. A sentence is a
 *   ruling in the member's own words; taking one out is a decision, never a side effect.
 *
 * The logic lives here rather than inline in the test so that it can be run against a HISTORICAL
 * tree — the same code, an older ledger — which is how its RED was proved (see the task report).
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

/** Does `row` name `id` — and not merely a longer id that starts with it (`A24.2` ≠ `A24.20`)? */
export function namesAmendment(row: string, id: string): boolean {
  return new RegExp(`${id.replace(/\./g, '\\.')}(?![\\w.])`).test(row);
}

/** The ledger's own supersession vocabulary, in either direction: the entry that took the text out
 *  says `supersedes <id>`, or the entry that put it there says `superseded by <id>` (A10/A10.2). */
export function statesSupersession(consumerRow: string, supersededRow: string, id: string, consumerId: string): boolean {
  const bound = (s: string) => `${s.replace(/\./g, '\\.')}(?![\\w.])`;
  return new RegExp(`supersedes\\s+${bound(id)}`, 'i').test(consumerRow)
    || new RegExp(`superseded\\s+by\\s+${bound(consumerId)}`, 'i').test(supersededRow);
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

/** The later entry that took `ruled` out, or undefined if nothing did. Two directions, because an
 *  entry's `find` may span the whole line (it rewrites it) or sit INSIDE it (it edits part of it);
 *  in the first direction an entry whose `replace` carries the text forward has not consumed it.
 *  `count` is checked at application time by `applyAmendments`, so an overlapping `find` is an
 *  overlapping EDIT — there is no other occurrence it could have matched instead. */
export function consumerOf(ruled: string, later: Amendment[]): Amendment | undefined {
  return later.find((f) => (f.find.includes(ruled) && !f.replace.includes(ruled)) || ruled.includes(f.find.trim()));
}

/** Every ruled line and ruled sentence that left the design with no entry naming the supersession,
 *  plus how many of each were examined (so a pass cannot be vacuous). */
export function ruledTextFindings({ list, final, rowOf }: GuardInput): { findings: string[]; lines: number; sentences: number } {
  const findings: string[] = [];
  let lines = 0;
  let sentences = 0;
  const quote = (s: string) => JSON.stringify(s.length > 120 ? `${s.slice(0, 120)}…` : s);
  list.forEach((e, i) => {
    const later = list.slice(i + 1);
    for (const ruled of introducedLines(e)) {
      // The SENTENCE tier first: a line may be rewritten lawfully and still carry its sentences
      // forward, which is the A24.20/A24.56 pair as it stands on `main` today.
      for (const sentence of ruledSentences(ruled)) {
        sentences++;
        if (final.includes(sentence)) continue;
        const by = consumerOf(sentence, later) ?? consumerOf(ruled, later);
        if (by === undefined) {
          findings.push(`${e.id}: the ruled sentence ${quote(sentence)} is not in the amended design and no later entry's find touches it`);
        } else if (!statesSupersession(rowOf(by.id), rowOf(e.id), e.id, by.id)) {
          findings.push(`${e.id} -> ${by.id}: the ruled sentence ${quote(sentence)} left the design and no row says so — ${by.id}'s row must say it supersedes ${e.id}, or ${e.id}'s row that it is superseded by ${by.id}`);
        }
      }
      lines++;
      if (final.includes(ruled)) continue;
      const by = consumerOf(ruled, later);
      if (by === undefined) {
        findings.push(`${e.id}: ${quote(ruled)} is not in the amended design and no later entry's find touches it`);
      } else if (!namesAmendment(rowOf(by.id), e.id)) {
        findings.push(`${e.id} -> ${by.id}: ${quote(ruled)} left the design and ${by.id}'s LOCAL_AMENDMENTS.md row does not name ${e.id}`);
      }
    }
  });
  return { findings, lines, sentences };
}
