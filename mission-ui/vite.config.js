import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.VITE_API_URL || process.env.VITE_API_URL || 'http://127.0.0.1:8005';
  return {
    base: '/mission-control/',
    build: { outDir: '../dist/mission-control', emptyOutDir: true },
    worker: { format: 'es' },
    server: {
      proxy: {
        '/api': target,
        '/health': target,
        '/openapi.json': target
      }
    },
    preview: {
      proxy: {
        '/api': target,
        '/health': target,
        '/openapi.json': target
      }
    }
  };
});
