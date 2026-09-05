import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  // isCustomElement: ImageSlot.vue's root IS the design's <image-slot> element (the DOM
  // oracle compares tag names strictly), so the compiler must emit it as an element
  // rather than try to resolve a component of that name.
  plugins: [vue({ template: { compilerOptions: { whitespace: 'preserve', isCustomElement: (tag) => tag === 'image-slot' } } })],
  build: { assetsDir: '_app' },
  server: { port: 5173, strictPort: true },
  test: { include: ['src/**/*.test.ts', 'tests/**/*.test.ts'] }
});
