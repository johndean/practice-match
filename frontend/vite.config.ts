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
      include: ['src/**/*.{ts,js,vue}'],
      // Generated or untouched-prototype files stay under the pixel/DOM/characterisation
      // gates instead (App.vue is generated from the design; logic.js/dc-logic.js are the
      // ported prototype, never restructured); type-only files and test helpers have no
      // runtime code to cover. (John, 2026-09-06: 100% on every hand-written file.)
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
