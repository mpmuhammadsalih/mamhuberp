import fs from 'node:fs'
import path from 'node:path'
import type { Connect, Plugin, PreviewServer, ViteDevServer } from 'vite'

const PRODUCT_PATH = /^\/products\/(\d+)\/?$/
const SITE_NAME = 'MamaHub'

type ProductSeo = {
  title: string
  description: string
  image: string
  url: string
  name: string
  sku: string
  price: number
  inStock: boolean
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function upsertMeta(html: string, attr: 'name' | 'property', key: string, content: string): string {
  const re = new RegExp(`<meta\\s+${attr}=["']${key}["'][^>]*>`, 'i')
  const tag = `<meta ${attr}="${key}" content="${escapeHtml(content)}" />`
  if (re.test(html)) return html.replace(re, tag)
  return html.replace(/<\/head>/i, `    ${tag}\n  </head>`)
}

function injectProductSeoHtml(html: string, seo: ProductSeo): string {
  let out = html
  out = out.replace(/<title>[^<]*<\/title>/i, `<title>${escapeHtml(seo.title)}</title>`)
  out = upsertMeta(out, 'name', 'description', seo.description)
  out = upsertMeta(out, 'property', 'og:title', seo.title)
  out = upsertMeta(out, 'property', 'og:description', seo.description)
  out = upsertMeta(out, 'property', 'og:type', 'product')
  out = upsertMeta(out, 'property', 'og:url', seo.url)
  out = upsertMeta(out, 'property', 'og:site_name', SITE_NAME)
  out = upsertMeta(out, 'property', 'og:image', seo.image)
  out = upsertMeta(out, 'name', 'twitter:card', 'summary_large_image')
  out = upsertMeta(out, 'name', 'twitter:title', seo.title)
  out = upsertMeta(out, 'name', 'twitter:description', seo.description)
  out = upsertMeta(out, 'name', 'twitter:image', seo.image)
  const canonicalRe = /<link\s+rel=["']canonical["'][^>]*>/i
  const canonical = `<link rel="canonical" href="${escapeHtml(seo.url)}" />`
  out = canonicalRe.test(out)
    ? out.replace(canonicalRe, canonical)
    : out.replace(/<\/head>/i, `    ${canonical}\n  </head>`)
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: seo.name,
    description: seo.description,
    image: seo.image,
    sku: seo.sku,
    offers: {
      '@type': 'Offer',
      url: seo.url,
      priceCurrency: 'QAR',
      price: seo.price,
      availability: seo.inStock
        ? 'https://schema.org/InStock'
        : 'https://schema.org/OutOfStock',
    },
  }
  const script = `<script type="application/ld+json">${JSON.stringify(jsonLd)}</script>`
  out = out.replace(/<\/head>/i, `    ${script}\n  </head>`)
  return out
}

function absoluteUrl(siteUrl: string, value: string | null | undefined): string {
  const base = siteUrl.replace(/\/$/, '')
  const raw = String(value || '').trim()
  if (!raw) return `${base}/images/hero-banner.png`
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw
  return `${base}${raw.startsWith('/') ? raw : `/${raw}`}`
}

async function loadProductSeo(
  apiTarget: string,
  siteUrl: string,
  itemCode: string,
): Promise<ProductSeo | null> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 2500)
  try {
    const resp = await fetch(`${apiTarget.replace(/\/$/, '')}/api/v1/products/${itemCode}`, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    })
    if (!resp.ok) return null
    const json = (await resp.json()) as { data?: Record<string, unknown> }
    const product = json.data
    if (!product) return null
    const name = String(product.item_name || `Product ${itemCode}`).trim()
    const title = String(product.seo_title || `${name} | ${SITE_NAME}`).trim()
    const description = String(
      product.seo_description || `Buy ${name} online at MamaHub. Toys and gifts delivered in Qatar.`,
    ).trim()
    const offer = Number(product.offer_price)
    const retail = Number(product.retail_price)
    const price = offer > 0 && offer < retail ? offer : retail || 0
    return {
      title,
      description,
      image: absoluteUrl(siteUrl, String(product.primary_image_url || product.image_url || '')),
      url: `${siteUrl.replace(/\/$/, '')}/products/${itemCode}`,
      name,
      sku: String(product.item_code || itemCode),
      price,
      inStock: Number(product.current_stock || 0) > 0,
    }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

function attachMiddleware(
  server: ViteDevServer | PreviewServer,
  options: { apiTarget: string; siteUrl: string; preview: boolean },
) {
  const { apiTarget, siteUrl, preview } = options
  const handler: Connect.NextHandleFunction = async (req, res, next) => {
    try {
      if (req.method !== 'GET') return next()
      const pathname = String(req.url || '').split('?')[0]
      const match = PRODUCT_PATH.exec(pathname)
      if (!match) return next()
      const accept = String(req.headers.accept || '')
      if (accept && !accept.includes('text/html') && !accept.includes('*/*')) return next()

      const seo = await loadProductSeo(apiTarget, siteUrl, match[1])
      if (!seo) return next()

      const htmlPath = preview
        ? path.resolve(server.config.root, server.config.build.outDir, 'index.html')
        : path.resolve(server.config.root, 'index.html')
      if (!fs.existsSync(htmlPath)) return next()
      let html = fs.readFileSync(htmlPath, 'utf8')
      if (!preview && 'transformIndexHtml' in server) {
        html = await server.transformIndexHtml(pathname, html)
      }
      html = injectProductSeoHtml(html, seo)
      res.statusCode = 200
      res.setHeader('Content-Type', 'text/html; charset=utf-8')
      res.setHeader('Cache-Control', 'public, max-age=60')
      res.end(html)
    } catch {
      next()
    }
  }
  server.middlewares.use(handler)
}

export function productSeoHtmlPlugin(apiTarget: string, siteUrl: string): Plugin {
  return {
    name: 'mamahub-product-seo-html',
    configureServer(server) {
      attachMiddleware(server, { apiTarget, siteUrl, preview: false })
    },
    configurePreviewServer(server) {
      attachMiddleware(server, { apiTarget, siteUrl, preview: true })
    },
  }
}
