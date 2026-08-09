import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Keeps the browser on a single origin (http://localhost:5173) so the
      // backend's auth cookie can be SameSite=Lax without ever needing CORS
      // or SameSite=None - the browser never sees localhost:8000 directly.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
