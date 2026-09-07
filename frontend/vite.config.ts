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
      // the 31 amendments and is held to the same 100 % as `src/` (re-review M7). The set is
      // whatever `src/**` holds, so it grows with the code and no count here stays true for
      // long: it was 14 files when F1 landed on main (2026-09-07), the two most recent
      // additions being `src/dc-logic.js` and `src/lib/leaflet.js`, which moved out of the
      // exclusions below once Browse V3's final-review fix round gave them behaviour tests.
      include: ['src/**/*.{ts,js,vue}', 'tests/design-amendments.ts'],
      // NOT measured, and why — every entry is generated, verbatim-ported, types-only or a test
      // double, with nothing left that is merely inconvenient to test: App.vue and pseudo.css
      // are generated from the design; logic.js and app.setup.js are the verbatim-ported
      // prototype, never restructured — all four are held instead by the byte-identity, pixel,
      // DOM and characterisation gates; engine.ts is types-only and map/testing/** is a test
      // double, neither with runtime code to cover. (John, 2026-09-06: 100% on every
      // hand-written file; set re-ratified 2026-09-07, F1.)
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
        'src/generated/**',
        'src/map/engine.ts',
        'src/map/testing/**',
        'src/**/*.test.ts',
        'src/**/*.d.ts'
      ],
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 }
    }
  }
});
