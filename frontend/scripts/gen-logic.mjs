#!/usr/bin/env node
/**
 * `npm run gen:logic` — writes `frontend/src/logic.js` from the approved design file.
 *
 * The transform itself is `scripts/port-logic.mjs`, which `tests/app-generated.test.ts` imports:
 * the command and the gate apply the SAME function, so a re-derivation cannot drift from what the
 * gate measures. This file is the command and nothing else.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { portLogic } from './port-logic.mjs';

const [dc, out] = process.argv.slice(2);
const ported = portLogic(readFileSync(dc, 'utf8'));
writeFileSync(out, ported);
console.log(`wrote ${out} (${ported.length} bytes, ${ported.split('\n').length - 1} lines)`);
