import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端 5173，/api 代理到 Flask 后端 5000
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
