import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const hqPort = Number(process.env.ASSET_HQ_PORT ?? '5173')
const apiPort = process.env.ASSET_API_PORT ?? '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: hqPort,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
})
