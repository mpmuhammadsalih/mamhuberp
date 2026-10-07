const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.m4v']

/** True when the URL/path points at a video asset. */
export function isVideoMediaUrl(url?: string | null): boolean {
  if (!url?.trim()) return false
  const value = url.trim().toLowerCase().split('?', 1)[0]
  return VIDEO_EXTENSIONS.some((ext) => value.endsWith(ext))
}

/** Resolve API media URLs for use in img src. */
export function resolveMediaUrl(url?: string | null): string | undefined {
  if (!url?.trim()) return undefined
  const value = url.trim()
  if (value.startsWith('http://') || value.startsWith('https://') || value.startsWith('data:')) {
    return value
  }
  if (value.startsWith('/api/')) return value
  if (value.startsWith('/media/files/') || value.startsWith('/ecommerce/media/files/')) {
    const filename = value.split('/').pop()
    if (filename) return `/api/v1/media/files/${filename}`
  }
  if (value.startsWith('uploads/itemmaster/') || value.startsWith('static/uploads/itemmaster/')) {
    const filename = value.split('/').pop()
    if (filename) return `/api/v1/products/images/${filename}`
  }
  if (value.startsWith('/')) return value
  return `/api/v1/media/files/${value}`
}
