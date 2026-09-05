import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  build: { assetsDir: '_app' },
  server: { port: 5173, strictPort: true },
  test: { include: ['src/**/*.test.ts', 'tests/**/*.test.ts'] }
});
