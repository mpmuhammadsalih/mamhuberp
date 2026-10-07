import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { productSeoHtmlPlugin } from './vite-plugins/productSeoHtml'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY || 'http://127.0.0.1:5002'
  const siteUrl = env.VITE_SITE_URL || 'https://www.mamahub.store'

  return {
    plugins: [react(), tailwindcss(), productSeoHtmlPlugin(apiTarget, siteUrl)],
    optimizeDeps: {
      exclude: ['maplibre-gl'],
    },
    server: {
      host: true,
      port: 5173,
      headers: {
        'Cache-Control': 'no-store',
      },
      allowedHosts: ['dev.mamahub.store', '.mamahub.store', 'localhost'],
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/sitemap.xml': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: () => '/api/v1/seo/sitemap.xml',
        },
      },
    },
    preview: {
      host: true,
      port: 5173,
      headers: {
        'Cache-Control': 'no-store',
      },
      allowedHosts: ['dev.mamahub.store', '.mamahub.store', 'localhost'],
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/sitemap.xml': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: () => '/api/v1/seo/sitemap.xml',
        },
      },
    },
  }
})
