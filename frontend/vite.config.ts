// Vite config: React, Tailwind CSS, and a dev-server proxy that forwards /api to Django.

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Forward API calls to Django during development so the browser sees a single
    // origin (no CORS), exactly like production where Django serves the built app.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
