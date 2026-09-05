import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue({ template: { compilerOptions: { whitespace: 'preserve' } } })],
  build: { assetsDir: '_app' },
  server: { port: 5173, strictPort: true },
  test: { include: ['src/**/*.test.ts', 'tests/**/*.test.ts'] }
});
