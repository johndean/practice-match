import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // `_app` matches the marketplace build so app/static.py's immutable-cache rule applies.
  build: { assetsDir: '_app' },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.js'],
    coverage: {
      provider: 'v8',
      include: ['src/logic.js'],   // the hand-written logic; App.vue, dc-logic.js and hover.js are the delivered page (pixel gate)
      thresholds: { lines: 100, branches: 100, functions: 100, statements: 100 }
    }
  }
});
