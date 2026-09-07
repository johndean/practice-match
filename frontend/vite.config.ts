import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  // isCustomElement: ImageSlot.vue's root IS the design's <image-slot> element (the DOM
  // oracle compares tag names strictly), so the compiler must emit it as an element
  // rather than try to resolve a component of that name.
  plugins: [vue({ template: { compilerOptions: { whitespace: 'preserve', isCustomElement: (tag) => tag === 'image-slot' } } })],
  build: { assetsDir: '_app' },
  server: { port: 5173, strictPort: true },
  test: {
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      // MEASURED: every hand-written file under `src/` except the exclusions below, plus
      // `tests/design-amendments.ts` — the engine that edits the approved design derives 24 of
      // the 31 amendments and is held to the same 100 % as `src/` (re-review M7).
      include: ['src/**/*.{ts,js,vue}', 'tests/design-amendments.ts'],
      // NOT measured, and why: App.vue and pseudo.css are generated from the design; logic.js
      // and app.setup.js are the verbatim-ported prototype, never restructured — all four are
      // held instead by the byte-identity, pixel, DOM and characterisation gates; engine.ts is
      // types-only and map/testing/** is a test double, neither with runtime code to cover.
      // Two entries are NOT in that class and are listed only because this set is ratified:
      // see the note above them. (John, 2026-09-06: 100% on every hand-written file.)
      exclude: [
        'src/App.vue',
        // app.setup.js is the OTHER half of the same generated pair: convert-dc.mjs copies
        // its text verbatim into App.vue's <script setup> block at `npm run gen:app` time
        // (scripts/convert-dc.mjs's buildAppVue) — it is never imported or executed as its
        // own module at runtime (grepping the whole tree, its only other reference is
        // tests/app-generated.test.ts's byte-identity check, which reads it as text). The
        // code that actually runs lives inside App.vue, already excluded above; 100% here
        // would require fabricating an import nothing in production ever performs.
        'src/app.setup.js',
        'src/logic.js',
        // The two ratified exclusions that are neither generated nor ported: dc-logic.js is the
        // hand-written 13-line React-shaped base class every setState in the app runs through,
        // and lib/leaflet.js is a hand-written loader with a test file of its own. Both are
        // behaviour-tested as of 2026-09-07 (src/dc-logic.test.ts, src/lib/leaflet.test.ts) and
        // both measure 100 lines/branches/functions/statements when unexcluded, verified in the
        // final-review fix round. They stay listed because this exact set is ratified by John
        // (fix round 1, 2026-09-06) and asserted by pytest's
        // test_frontend_coverage_thresholds_are_100_and_exclude_is_the_ratified_set, and no
        // file under tests/ changes on this branch (Global Constraint (i)). Removing these two
        // lines is a one-line re-ratification for John, not an implementer's call (M10).
        'src/dc-logic.js',
        'src/generated/**',
        'src/lib/**',
        'src/map/engine.ts',
        'src/map/testing/**',
        'src/**/*.test.ts',
        'src/**/*.d.ts'
      ],
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 }
    }
  }
});
