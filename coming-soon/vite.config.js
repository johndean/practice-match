import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  // `_app` matches the marketplace build so app/static.py's immutable-cache rule applies.
  build: { assetsDir: '_app' }
});
