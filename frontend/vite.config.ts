import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

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
  }
})
