#!/usr/bin/env node
/**
 * The transform `npm run gen:logic` applies — `scripts/gen-logic.mjs` is the command, this is the
 * rule it runs — regenerating `frontend/src/logic.js` from the approved design file.
 *
 *   Practice Match V3.dc.html's <script data-dc-script> block
 *   + the provenance header and the DCLogic import
 *   + the platform spec §3 rule-1 asset rewrite ("assets/ -> "/assets/)
 *   + the trailing export
 *   = frontend/src/logic.js
 *
 * `logic.js` is NOT written by `gen:app`: it is the design's own script block, ported VERBATIM
 * and never restructured, with exactly the four normalisations the Browse V3 spec §3 lists. Two
 * implementers re-derived it on 2026-09-13 with throwaway scripts copied out of
 * `tests/app-generated.test.ts`, which is a second copy of the transform and the thing the
 * one-source-of-truth rule exists to prevent — so the transform lives HERE, this script applies
 * it, and `app-generated.test.ts` imports the same functions to prove the committed file is what
 * it produces. There is one HEADER, one FOOTER and one asset rewrite in the tree.
 *
 * Beside `gen:design` (pristine + ruled amendments -> the amended design) and `gen:app` (the
 * design's template -> App.vue + pseudo.css), this is the third leg: the design's script -> the
 * ported logic.
 */
/** The provenance header and the one import the port adds above the design's own bytes. */
export const HEADER = "// Ported verbatim from the approved prototype 'Practice Match V3.dc.html'.\n"
  + '// Do not restyle or restructure: every value here is design-approved.\n'
  + "import { DCLogic } from './dc-logic.js';\n";

/**
 * The one accepted edit point, the last line. It names the two fixture ARRAYS as well as the
 * class (Seed Listings L6, spec D6): `src/listings/load.ts` replaces `P` and `MARKETS` in place at
 * start-up, which is the one way to hand the API's listings to a script that is ported verbatim.
 */
export const FOOTER = '\nexport { Component, MARKETS, P, VETS, ECON_K };\n';

/** The design file's own `<script type="text/x-dc" data-dc-script>` block, byte for byte. */
export function designScript(html) {
  const open = /<script type="text\/x-dc" data-dc-script[^>]*>/.exec(html);
  if (open === null) throw new Error('no <script data-dc-script> block in the design file');
  const start = open.index + open[0].length;
  return html.slice(start, html.indexOf('</script>', start));
}

/**
 * The whole port. FOUR normalisations and no others, all four listed in the Browse V3 spec §3:
 * the HEADER, the FOOTER, the asset rewrite, and `\n+$` -> `\n` (the design's script block ends
 * with two newlines and the ported file with one).
 */
export function portLogic(html) {
  const body = designScript(html).replace(/"assets\//g, '"/assets/').replace(/\n+$/, '\n');
  return HEADER + body + FOOTER;
}
