/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath } from 'node:url';

const outDir = fileURLToPath(new URL('../src/tjapp/static/app', import.meta.url));
import pkg from './package.json' with { type: 'json' };
const devApi = process.env.FEPRA_DEV_API ?? 'http://127.0.0.1:8765';

export default defineConfig({
  base: '/app/',
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'FePra',
        short_name: 'FePra',
        description: 'Дневник тренировок и восстановления',
        lang: 'ru',
        start_url: '/app/',
        scope: '/app/',
        display: 'standalone',
        orientation: 'portrait',
        theme_color: '#0f6e56',
        background_color: '#f6f5f1',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      // свой service worker (src/sw.ts): предкэш оболочки + push и notificationclick
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.ts',
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'],
      },
    }),
  ],
  build: { outDir, emptyOutDir: true, sourcemap: false, chunkSizeWarningLimit: 700 },
  server: {
    port: 5173,
    proxy: { '/api': { target: devApi, changeOrigin: false } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['test/setup.ts'],
    include: ['test/**/*.test.{ts,tsx}'],
  },
});
