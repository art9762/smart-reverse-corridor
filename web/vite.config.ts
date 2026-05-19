/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

const isDemo = process.env.VITE_DEMO === '1';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  build: {
    sourcemap: true,
    target: 'es2020',
    rollupOptions: isDemo
      ? {
          input: {
            demo: resolve(__dirname, 'demo.html'),
          },
        }
      : undefined,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    css: false,
  },
});
