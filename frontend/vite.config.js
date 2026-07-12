import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端 5173，/api 代理到 Flask 后端 5000
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    test: {
      environment: 'jsdom',
      setupFiles: './src/test/setup.js',
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:5000',
          changeOrigin: true,
        },
      },
    },
  }
})
