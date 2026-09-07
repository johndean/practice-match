/**
 * `npm run gen:design` — regenerates the AMENDED design file from the pristine bundle copy
 * plus the ruled amendment list (spec D15; the generator itself is amendment A-I8).
 *
 *   Practice Match V3.rev2.dc.html  (pristine — the bundle's own bytes, never edited)
 *   + frontend/tests/design-amendments.ts's amendments()
 *   = Practice Match V3.dc.html     (the authority every oracle is generated from)
 *
 * Before this existed the amended file was produced by hand and `design-amendments.test.ts`
 * merely proved the two agreed — which meant a new amendment required an implementer to edit
 * the approved design by hand and get it byte-perfect. That is exactly the failure mode D15
 * was written to remove, so the equality is now produced rather than achieved: run this, then
 * `npm run gen:app`, and the test confirms rather than dictates.
 *
 * It is deliberately NOT idempotency-checked here: `applyAmendments` counts every `find` at the
 * point it is applied and throws, naming the amendment, if the count is wrong — which is what a
 * second run against an already-amended file would produce.
 *
 * Run by `vite-node` (it ships with vitest, so no new dependency) because the amendment list is
 * TypeScript and is imported by the test suite from the same module.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { AMENDED, PRISTINE, amendments, applyAmendments } from '../tests/design-amendments';

const list = amendments();
const out = applyAmendments(readFileSync(PRISTINE, 'utf8'), list);
writeFileSync(AMENDED, out);
console.log(`wrote ${AMENDED}\n  ${list.length} amendments applied, ${out.length} bytes`);
