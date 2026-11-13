import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8080',
        '/oauth2': env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8080',
        '/login/oauth2': env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8080',
        '/agent': {
          target: env.VITE_AGENT_PROXY_TARGET || 'http://localhost:8000',
          rewrite: (path) => path.replace(/^\/agent/, ''),
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
    },
  }
})
