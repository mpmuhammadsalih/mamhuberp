import type { ShowcaseBannerConfig } from '../components/catalog/ShowcaseVerticalVideo'
import { isVideoMediaUrl, resolveMediaUrl } from './media'
import type { MediaItem } from './queries/storefront'

export function pickShowcaseMedia(
  banners: Record<string, MediaItem> | undefined,
  refKey: string,
): MediaItem | undefined {
  if (!banners) return undefined
  return banners[refKey] ?? banners.default ?? Object.values(banners)[0]
}

export function buildShowcaseBannerConfig(
  item: MediaItem | undefined,
  defaults: {
    title: string
    href: string
    posterFallback: string
    gradientFrom?: string
    gradientTo?: string
  },
): ShowcaseBannerConfig {
  const meta = item?.meta ?? {}
  const imageUrl = resolveMediaUrl(item?.image_url)
  const metaVideo = resolveMediaUrl(String(meta.video_url ?? ''))
  const metaPoster = resolveMediaUrl(String(meta.poster_url ?? ''))
  const imageIsVideo = isVideoMediaUrl(item?.image_url) || isVideoMediaUrl(imageUrl)
  const videoSrc = metaVideo ?? (imageIsVideo ? imageUrl : undefined)
  const posterSrc =
    metaPoster ??
    (imageIsVideo ? defaults.posterFallback : imageUrl) ??
    defaults.posterFallback

  return {
    title: item?.title ?? defaults.title,
    href: item?.link_url ?? defaults.href,
    imageSrc: posterSrc,
    videoSrc,
    posterSrc,
    gradientFrom: String(meta.gradient_from ?? defaults.gradientFrom ?? 'from-brand-accent'),
    gradientTo: String(meta.gradient_to ?? defaults.gradientTo ?? 'to-brand-purple'),
  }
}
