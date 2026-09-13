/**
 * `npm run remap:citations` — the committed citation re-mapper (Task HOUSEKEEPING-C item 1).
 *
 * HOUSEKEEPING-B made every `V3:<line>` in `LOCAL_AMENDMENTS.md` a checked claim. It did not say
 * how to RE-TAKE one. Insert an entry whose `replace` is longer than its `find` and every design
 * line below it moves, so every citation below it goes stale at once — A33 shifted 132 rows,
 * ADMIN-GATE and SCREEN-LABELS each shifted their own, and on 2026-09-13 three merges re-mapped
 * roughly 130 citations apiece BY HAND, each with a throwaway script nobody kept. This is that
 * script, kept.
 *
 * ONE DEFINITION OF "ANCHOR", and it is the GATE'S. A citation is correct when the cited line, or
 * one either side of it, carries a DISTINCTIVE line of what that amendment put there — distinctive
 * meaning a word token of two or more characters occurring at most K times in the whole amended
 * design (`amend-guard.ts`'s `DISTINCTIVENESS_K`, re-derived on every run). So this tool computes
 * exactly that set of lines — the ANCHOR LINES — from the same `outputOf` chain the gate walks,
 * and every number it writes lands on one. It cannot produce a citation the gate then refuses,
 * which is the property that makes it safe to run unattended; the first draft of it derived its
 * own notion of "where the output starts" and broke four rows the gate immediately caught.
 *
 * WHICH anchor, when an entry has several — three rungs, most specific first.
 *
 *   1. A PIN. `citation-pins.json` names the line by a neighbouring distinctive anchor plus an
 *      offset. This is the residue the brief anticipated and it is small: A24.35 (households) and
 *      A24.36 (income) write BYTE-IDENTICAL `source:` lines, and so do their consumers A24.47 and
 *      A24.46, so the TEXT cannot say which entry stands where and only the `find` anchor each
 *      carries can. Nothing else in this ledger needs one today.
 *   2. THE ONLY ANCHOR. Where the entry has exactly ONE anchor line in the whole design, that is
 *      the answer whatever the row currently says — POSITION-INDEPENDENT, so a shift of any size
 *      is re-mapped correctly. A24.4 (`areas: areaFc,`) and A25.3 (the map's community list) are
 *      this case, and they are the pair that has collided on every renumbering since A24 landed:
 *      they write ADJACENT lines and the row above cited its neighbour's, so a ±1 slip made two
 *      rows point at one line. Re-mapped, each points at its own.
 *   3. THE NEAREST ANCHOR to the number the row already carries. An entry with several anchors —
 *      a block of its own output, plus the odd line the design repeats elsewhere — is disambiguated
 *      by the citation itself, which is EVIDENCE: it was correct when it was written, and an
 *      insertion moves it by a known small amount relative to the gaps between an entry's own
 *      anchors. THE LIMIT, stated rather than hidden: an insertion larger than half the distance
 *      between two of one entry's anchors can pick the wrong one. That is what rung 1 is for, and
 *      it is why every run prints what it moved.
 *
 * WHAT IT DOES NOT RE-DERIVE. A range's END is editorial — the ledger's own rule is that a range
 * "stops where your text does and the row says so", which is a judgement about how much of a
 * multi-line edit survived — so the SPAN is carried forward and only the base moves. A second
 * citation in the same row is carried the same way, which is what lets A3's row cite `V3:858` for
 * the text node it changed and `V3:872` for the sibling button it deliberately did not. Any number
 * the shift leaves off an anchor is then SNAPPED to the nearest one, which is the last line of
 * defence against a range whose tail a later entry rewrote.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Amendment } from './design-amendments';

/** One committed pin: the line is named by a neighbouring DISTINCTIVE anchor, plus how many lines
 *  below it the entry's own output begins. `why` is required — a pin is a judgement and the file
 *  is where the judgement is recorded. */
export type CitationPin = { anchor: string; offset: number; why: string };
export type PinTable = Record<string, CitationPin>;

/** The committed pins. JSON rather than TypeScript so the judgement calls are data a reviewer can
 *  read in one screen, beside `baseline-manifest.json`, which is the same kind of file. */
export const CITATION_PINS_FILE = fileURLToPath(new URL('citation-pins.json', import.meta.url));
export const CITATION_PINS: PinTable = JSON.parse(readFileSync(CITATION_PINS_FILE, 'utf8'));

export type RemapInput = {
  /** `LOCAL_AMENDMENTS.md`, whole. */
  md: string;
  /** The amended `.dc.html`, whole. */
  design: string;
  /** Every amendment, in application order (`amendments()`) — the chain in `outputOf` needs them all. */
  list: Amendment[];
  /** The committed pins, keyed by amendment id. */
  pins: PinTable;
  /** HOUSEKEEPING-B's measured distinctiveness threshold. */
  maxOccurrences: number;
};

export type CitationMove = { id: string; from: number; to: number; rung: 'pin' | 'only' | 'nearest' };
export type RemapResult = { md: string; moves: CitationMove[]; unresolved: string[]; rows: number };

/** The entries a row's id owns. A1's 24 derived edits collapse to ONE row, exactly as the gate
 *  reads them. */
export function entriesFor(id: string, list: Amendment[]): Amendment[] {
  return id === 'A1' ? list.filter((a) => a.id.startsWith('A1.')) : list.filter((a) => a.id === id);
}

/** What stands at this amendment's site today, one trimmed line per entry line: its own `replace`,
 *  or — where a later entry's `find` swallowed that `replace` whole — whatever superseded it.
 *  `design-amendments.test.ts`'s `outputOf`, which is the gate's own walk. */
export function outputOf(a: Amendment, list: Amendment[]): string[] {
  const later = list.slice(list.indexOf(a) + 1).find((b) => b.find.includes(a.replace));
  return later === undefined ? a.replace.split('\n').map((s) => s.trim()).filter(Boolean) : outputOf(later, list);
}

/** Every line of the design a citation for `id` may legally name — the gate's own rule, read
 *  from one place so the tool and the gate cannot disagree about what "distinctive" means. */
export function anchorLines(id: string, { design, list, maxOccurrences }: Omit<RemapInput, 'md' | 'pins'>): number[] {
  const own = entriesFor(id, list);
  const occurrences = (piece: string) => design.split(piece).length - 1;
  const pieces = own.flatMap((a) => outputOf(a, list)).filter((p) => /[A-Za-z0-9]{2,}/.test(p) && occurrences(p) <= maxOccurrences);
  return design.split('\n').flatMap((line, i) => (pieces.some((p) => line.includes(p)) ? [i + 1] : []));
}

/** The anchor closest to `n`; the lower one where two tie. */
export function nearest(anchors: number[], n: number): number {
  return anchors.reduce((best, a) => (Math.abs(a - n) < Math.abs(best - n) ? a : best));
}

/** The gate's window: a citation is correct when an anchor is on the line, or one either side. */
export function onAnchor(anchors: number[], n: number): boolean {
  return anchors.some((a) => Math.abs(a - n) <= 1);
}

type Home = { line: number; rung: CitationMove['rung'] } | { line: null; why: string };

/** The three rungs, in order. */
export function homeLine(id: string, cited: number, input: Omit<RemapInput, 'md'>): Home {
  const pin = input.pins[id];
  if (pin !== undefined) {
    const occurrences = input.design.split(pin.anchor).length - 1;
    if (occurrences !== 1) return { line: null, why: `${id}: the pinned anchor occurs ${occurrences} times, so it names no line — pin a distinctive one` };
    return { line: input.design.slice(0, input.design.indexOf(pin.anchor)).split('\n').length + pin.offset, rung: 'pin' };
  }
  if (entriesFor(id, input.list).length === 0) return { line: null, why: `${id}: the row cites a V3 line but no amendment carries that id` };
  const anchors = anchorLines(id, input);
  if (anchors.length === 0) return { line: null, why: `${id}: nothing this amendment wrote is still distinctive in the design — pin it` };
  if (anchors.length === 1) return { line: anchors[0], rung: 'only' };
  return { line: nearest(anchors, cited), rung: 'nearest' };
}

/** Every `V3:<start>` or `V3:<start>–<end>` in one row. */
const CITATION = /V3:(\d+)(?:([–-])(\d+))?/g;

/**
 * Re-maps every citation in `md` against `design`. Pure: it returns the new text and what it did,
 * and the caller decides whether to write it.
 */
export function remapCitations(input: RemapInput): RemapResult {
  const moves: CitationMove[] = [];
  const unresolved: string[] = [];
  let rows = 0;
  const md = input.md.split('\n').map((row) => {
    const id = /^\|\s*(A[\w.]+)\s*\|/.exec(row)?.[1];
    if (id === undefined) return row;
    CITATION.lastIndex = 0;
    const first = CITATION.exec(row);
    if (first === null) return row;
    rows++;
    const cited = Number(first[1]);
    const home = homeLine(id, cited, input);
    if (home.line === null) {
      unresolved.push(home.why);
      return row;
    }
    const anchors = anchorLines(id, input);
    const delta = home.line - cited;
    // Carry every number by the same delta, then SNAP any that the shift left off an anchor — the
    // tail of a range a later entry rewrote is the case this catches.
    const move = (n: number) => (onAnchor(anchors, n + delta) ? n + delta : nearest(anchors, n + delta));
    const next = row.replace(CITATION, (_m, start: string, dash: string | undefined, end: string | undefined) =>
      `V3:${move(Number(start))}${dash === undefined ? '' : `${dash}${move(Number(end))}`}`);
    if (next !== row) moves.push({ id, from: cited, to: home.line, rung: home.rung });
    return next;
  }).join('\n');
  return { md, moves, unresolved, rows };
}
