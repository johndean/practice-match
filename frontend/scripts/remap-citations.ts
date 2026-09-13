/**
 * `npm run remap:citations` — re-takes every `V3:<line>` citation in `LOCAL_AMENDMENTS.md`
 * against the amended design as it stands now (Task HOUSEKEEPING-C item 1).
 *
 * Run it after inserting, removing or re-sizing any amendment: an entry whose `replace` is longer
 * than its `find` moves every design line below it, and every citation below it with them. The
 * rules, the three rungs and why a range's END is carried rather than re-derived are documented in
 * `frontend/tests/citation-remap.ts`; the judgement calls are in `frontend/tests/citation-pins.json`.
 *
 * It REFUSES rather than guesses: an id whose home line cannot be resolved is printed and the file
 * is still written for every row that could be, with a non-zero exit so a run in a script stops.
 * The answer to a refusal is a pin, not a hand edit — a hand edit is what this replaces.
 *
 * Run by `vite-node` for the same reason `apply-amendments.ts` is: the amendment list is
 * TypeScript and is imported by the test suite from the same module.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { AMENDED, LOCAL_AMENDMENTS_MD, amendments } from '../tests/design-amendments';
import { DISTINCTIVENESS_K } from '../tests/amend-guard';
import { CITATION_PINS, remapCitations } from '../tests/citation-remap';

const md = readFileSync(LOCAL_AMENDMENTS_MD, 'utf8');
const { md: next, moves, unresolved, rows } = remapCitations({
  md,
  design: readFileSync(AMENDED, 'utf8'),
  list: amendments(),
  pins: CITATION_PINS,
  maxOccurrences: DISTINCTIVENESS_K,
});

writeFileSync(LOCAL_AMENDMENTS_MD, next);
console.log(`wrote ${LOCAL_AMENDMENTS_MD}\n  ${rows} cited row(s), ${moves.length} re-mapped`);
for (const m of moves) console.log(`  ${m.id}: V3:${m.from} -> V3:${m.to} (${m.rung})`);
for (const u of unresolved) console.log(`  UNRESOLVED ${u}`);
if (unresolved.length > 0) process.exitCode = 1;
