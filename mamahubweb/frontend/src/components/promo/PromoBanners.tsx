import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode, type TouchEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { IconChevronLeft, IconChevronRight, IconVolume, IconVolumeOff } from '../icons/Icons'
import { HOME_CONTAINER, HOME_GRID_GAP } from '../layout/homeLayout'
import { isVideoMediaUrl, resolveMediaUrl } from '../../lib/media'
import { useLocale } from '../../i18n/LocaleContext'
import { mediaCta, mediaSubtitle, mediaTitle } from '../../i18n/mediaText'
import type { SupportedLocale } from '../../i18n/types'
import { storefrontQueries, type MediaItem } from '../../lib/queries/storefront'
import { PROMO_ILLUSTRATIONS } from './PromoIllustrations'

const AUTOPLAY_MS = 6000
const SWIPE_THRESHOLD = 48
const PROMO_TILE_HEIGHT = 'h-[220px] sm:h-[280px] lg:h-[360px]'

type PromoSlot = 'strip' | 'main' | 'side'

interface PromoView {
  title: string
  subtitle: string
  cta: string
  href: string
  bg: string
  titleColor: string
  btnClass: string
  illustration: keyof typeof PROMO_ILLUSTRATIONS
  imageUrl?: string
  posterUrl?: string
  isVideo: boolean
  mediaId?: number | null
  slot: PromoSlot
  slideIndex?: number
  badgeText?: string
  imageOnly: boolean
}

interface PromoSlide {
  id: string
  main?: PromoView
  side?: PromoView
}

function resolveSlot(item: MediaItem): PromoSlot | undefined {
  const key = (item.ref_key ?? '').trim().toLowerCase()
  const layout = String(item.meta?.layout ?? '')
    .trim()
    .toLowerCase()
  const slot = String(item.meta?.slot ?? '')
    .trim()
    .toLowerCase()

  if (layout === 'strip' || slot === 'strip' || key === 'top-strip' || key === 'strip' || key.startsWith('strip-')) {
    return 'strip'
  }
  if (
    layout === 'main' ||
    slot === 'main' ||
    key === 'main' ||
    key.endsWith('-main') ||
    key === 'weekly-deals' ||
    key === 'primary'
  ) {
    return 'main'
  }
  if (
    layout === 'side' ||
    slot === 'side' ||
    key === 'side' ||
    key.endsWith('-side') ||
    key === 'free-delivery' ||
    key === 'secondary'
  ) {
    return 'side'
  }
  return undefined
}

function resolveSlideIndex(item: MediaItem): number | undefined {
  const meta = item.meta ?? {}
  const raw = meta.slide ?? meta.slide_index ?? meta.slide_group
  if (raw !== undefined && raw !== null && String(raw).trim() !== '') {
    const parsed = Number.parseInt(String(raw), 10)
    if (!Number.isNaN(parsed) && parsed > 0) return parsed
  }

  const key = (item.ref_key ?? '').trim().toLowerCase()
  const match = key.match(/^slide-(\d+)-(main|side)$/)
  if (match) return Number.parseInt(match[1], 10)

  return undefined
}

function mapPromo(
  item: MediaItem,
  slot: PromoSlot,
  slideIndex: number | undefined,
  locale: SupportedLocale,
  shopNowLabel: string,
): PromoView {
  const meta = item.meta ?? {}
  const illustration = (meta.illustration as PromoView['illustration']) ?? 'gift'
  const title = mediaTitle(item, locale)
  const subtitle = mediaSubtitle(item, locale)
  const imageUrl = resolveMediaUrl(item.image_url)
  const metaVideo = resolveMediaUrl(String(meta.video_url ?? ''))
  const posterUrl = resolveMediaUrl(String(meta.poster_url ?? ''))
  const videoUrl =
    metaVideo && isVideoMediaUrl(metaVideo)
      ? metaVideo
      : imageUrl && isVideoMediaUrl(imageUrl)
        ? imageUrl
        : undefined

  return {
    title,
    subtitle,
    cta: mediaCta(item, locale, shopNowLabel),
    href: item.link_url ?? '/products',
    bg: String(meta.bg ?? 'bg-gradient-to-br from-brand-cream-alt to-brand-tint'),
    titleColor: String(meta.title_color ?? 'text-brand-cocoa'),
    btnClass: String(meta.btn_class ?? 'bg-brand-cocoa hover:bg-brand-ink'),
    illustration,
    imageUrl: videoUrl ?? imageUrl,
    posterUrl: posterUrl ?? (imageUrl && !isVideoMediaUrl(imageUrl) ? imageUrl : undefined),
    isVideo: Boolean(videoUrl),
    mediaId: item.media_id,
    slot,
    slideIndex,
    badgeText: meta.badge_text ? String(meta.badge_text) : undefined,
    imageOnly: meta.image_only === true || meta.image_only === 'true' || (!title && !subtitle),
  }
}

function groupPromos(items: MediaItem[], locale: SupportedLocale, shopNowLabel: string) {
  const sorted = [...items].sort(
    (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.media_id ?? 0) - (b.media_id ?? 0),
  )

  const strips: PromoView[] = []
  const slideMap = new Map<number, PromoSlide>()
  const unassigned: MediaItem[] = []

  for (const item of sorted) {
    const slot = resolveSlot(item)
    if (slot === 'strip') {
      strips.push(mapPromo(item, 'strip', undefined, locale, shopNowLabel))
      continue
    }

    const slideIndex = resolveSlideIndex(item)
    if (slideIndex !== undefined && slot) {
      const slide = slideMap.get(slideIndex) ?? { id: `slide-${slideIndex}` }
      if (slot === 'main') slide.main = mapPromo(item, 'main', slideIndex, locale, shopNowLabel)
      if (slot === 'side') slide.side = mapPromo(item, 'side', slideIndex, locale, shopNowLabel)
      slideMap.set(slideIndex, slide)
      continue
    }

    unassigned.push(item)
  }

  if (unassigned.length > 0 && slideMap.size === 0) {
    let autoSlide = 1
    for (let index = 0; index < unassigned.length; index += 2) {
      const mainItem = unassigned[index]
      const sideItem = unassigned[index + 1]
      const slide: PromoSlide = { id: `auto-${autoSlide}` }

      if (mainItem) {
        slide.main = mapPromo(mainItem, 'main', autoSlide, locale, shopNowLabel)
      }
      if (sideItem) {
        slide.side = mapPromo(sideItem, 'side', autoSlide, locale, shopNowLabel)
      }

      if (slide.main || slide.side) {
        slideMap.set(1000 + autoSlide, slide)
        autoSlide += 1
      }
    }
  }

  const slides = [...slideMap.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, slide]) => slide)
    .filter((slide) => slide.main || slide.side)

  return { strips, slides }
}

function PromoMedia({
  imageUrl,
  posterUrl,
  isVideo = false,
  illustration: Illustration,
  className = '',
  eager = false,
  alt = '',
  active = true,
}: {
  imageUrl?: string
  posterUrl?: string
  isVideo?: boolean
  illustration: ComponentType
  className?: string
  eager?: boolean
  alt?: string
  active?: boolean
}) {
  const { t } = useLocale()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [failed, setFailed] = useState(false)
  const [muted, setMuted] = useState(true)

  useEffect(() => {
    setFailed(false)
    setMuted(true)
  }, [imageUrl])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !isVideo || failed) return
    video.muted = muted
    if (!active) {
      video.pause()
      video.muted = true
      setMuted(true)
      return
    }
    void video.play().catch(() => {})
  }, [active, failed, imageUrl, isVideo, muted])

  if (!imageUrl || failed) {
    return (
      <div className={`absolute inset-0 flex items-center justify-center bg-brand-tint/40 ${className}`}>
        <Illustration />
      </div>
    )
  }

  if (isVideo) {
    return (
      <>
        <video
          key={imageUrl}
          ref={videoRef}
          className="absolute inset-0 h-full w-full object-cover object-center"
          autoPlay={active}
          muted={muted}
          loop
          playsInline
          preload={active || eager ? 'metadata' : 'none'}
          poster={posterUrl}
          onError={() => setFailed(true)}
        >
          <source src={imageUrl} />
        </video>
        {active ? (
          <button
            type="button"
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setMuted((current) => !current)
            }}
            className="absolute right-3 top-3 z-20 flex h-9 w-9 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/60"
            aria-label={muted ? t.hero.unmuteVideo : t.hero.muteVideo}
          >
            {muted ? <IconVolumeOff size={16} /> : <IconVolume size={16} />}
          </button>
        ) : null}
      </>
    )
  }

  return (
    <img
      src={imageUrl}
      alt={alt}
      className={`absolute inset-0 h-full w-full object-cover object-center ${className}`}
      loading={eager ? 'eager' : 'lazy'}
      fetchPriority={eager ? 'high' : undefined}
      draggable={false}
      onError={() => setFailed(true)}
    />
  )
}

function splitPromoParts(value: string) {
  return value
    .split(/\s*\|\s*/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function collectStripMessages(strips: PromoView[]) {
  const messages: { text: string; href: string }[] = []
  const seen = new Set<string>()

  for (const promo of strips) {
    const parts = [...splitPromoParts(promo.title), ...splitPromoParts(promo.subtitle)]
    if (parts.length === 0 && promo.badgeText) parts.push(promo.badgeText)
    for (const text of parts) {
      const key = `${promo.href}::${text.toLowerCase()}`
      if (seen.has(key)) continue
      seen.add(key)
      messages.push({ text, href: promo.href })
    }
  }

  return messages
}

function PromoStripTrack({
  items,
  hidden = false,
}: {
  items: { text: string; href: string }[]
  hidden?: boolean
}) {
  return (
    <div className={`flex shrink-0 items-center ${hidden ? 'promo-marquee-copy' : ''}`} aria-hidden={hidden || undefined}>
      {items.map((item, index) => (
        <span key={`${item.text}-${index}`} className="flex shrink-0 items-center">
          <Link
            to={item.href}
            tabIndex={hidden ? -1 : undefined}
            className="whitespace-nowrap px-3 text-xs font-semibold text-white transition hover:text-white sm:px-4 sm:text-sm"
          >
            {item.text}
          </Link>
          <span className="select-none text-brand-ink/40" aria-hidden>
            |
          </span>
        </span>
      ))}
    </div>
  )
}

function PromoStripMarquee({ strips }: { strips: PromoView[] }) {
  const messages = useMemo(() => collectStripMessages(strips), [strips])
  const loop = useMemo(() => {
    if (messages.length === 0) return []
    const copies = messages.length <= 2 ? 4 : 2
    return Array.from({ length: copies }, () => messages).flat()
  }, [messages])
  const duration = Math.max(18, Math.min(48, messages.reduce((total, item) => total + item.text.length, 0) / 4))

  if (messages.length === 0) return null

  return (
    <div className="promo-strip-marquee overflow-hidden rounded-full bg-brand-yellow text-brand-ink shadow-sm ring-1 ring-brand-orange/30">
      <ul className="sr-only">
        {messages.map((item) => (
          <li key={`${item.href}-${item.text}`}>{item.text}</li>
        ))}
      </ul>
      <div
        className="promo-marquee-track flex w-max min-h-[3.25rem] items-center py-2.5"
        style={{ ['--promo-marquee-duration' as string]: `${duration}s` }}
        aria-hidden
      >
        <PromoStripTrack items={loop} />
        <PromoStripTrack items={loop} hidden />
      </div>
    </div>
  )
}

function PromoMainCard({ promo, active = true }: { promo: PromoView; active?: boolean }) {
  const Illustration = PROMO_ILLUSTRATIONS[promo.illustration]

  if (promo.imageOnly && promo.imageUrl) {
    return (
      <Link
        to={promo.href}
        className={`group relative block overflow-hidden rounded-2xl ring-1 ring-black/[0.06] transition hover:shadow-lg ${PROMO_TILE_HEIGHT}`}
      >
        <PromoMedia
          imageUrl={promo.imageUrl}
          posterUrl={promo.posterUrl}
          isVideo={promo.isVideo}
          illustration={Illustration}
          alt={promo.title}
          eager
          active={active}
        />
      </Link>
    )
  }

  return (
    <Link
      to={promo.href}
      className={`group relative block overflow-hidden rounded-2xl ring-1 ring-black/[0.06] transition hover:shadow-lg ${PROMO_TILE_HEIGHT} ${promo.bg}`}
    >
      {promo.imageUrl ? (
        <div className="absolute inset-0 overflow-hidden">
          <PromoMedia
            imageUrl={promo.imageUrl}
            posterUrl={promo.posterUrl}
            isVideo={promo.isVideo}
            illustration={Illustration}
            alt={promo.title}
            eager
            active={active}
          />
          <div className="absolute inset-0 bg-gradient-to-r from-white/90 via-white/55 to-transparent" />
        </div>
      ) : (
        <div className="absolute inset-0 opacity-70">
          <Illustration />
        </div>
      )}

      <div className="relative flex h-full flex-col justify-center px-5 py-6 sm:px-8 lg:px-10">
        {promo.title ? (
          <h2
            className={`max-w-[14rem] font-display text-2xl font-bold leading-tight sm:max-w-xs sm:text-3xl lg:max-w-sm lg:text-4xl ${promo.titleColor}`}
          >
            {promo.title}
          </h2>
        ) : null}
        {promo.subtitle ? (
          <p className="mt-2 max-w-xs text-xs text-slate-600 sm:text-sm">{promo.subtitle}</p>
        ) : null}
        {promo.cta ? (
          <span
            className={`mt-4 inline-flex w-fit items-center rounded-lg px-4 py-2 text-[11px] font-bold uppercase tracking-wide text-white shadow-sm sm:px-5 sm:py-2.5 sm:text-xs ${promo.btnClass}`}
          >
            {promo.cta}
          </span>
        ) : null}
      </div>
    </Link>
  )
}

function PromoSideCard({ promo, active = true }: { promo: PromoView; active?: boolean }) {
  const Illustration = PROMO_ILLUSTRATIONS[promo.illustration]

  if (promo.imageOnly && promo.imageUrl) {
    return (
      <Link
        to={promo.href}
        className={`group relative block overflow-hidden rounded-2xl ring-1 ring-black/[0.06] transition hover:shadow-lg ${PROMO_TILE_HEIGHT}`}
      >
        <PromoMedia
          imageUrl={promo.imageUrl}
          posterUrl={promo.posterUrl}
          isVideo={promo.isVideo}
          illustration={Illustration}
          alt={promo.title}
          active={active}
        />
      </Link>
    )
  }

  return (
    <Link
      to={promo.href}
      className={`group relative block overflow-hidden rounded-2xl ring-1 ring-black/[0.06] transition hover:shadow-lg ${PROMO_TILE_HEIGHT} ${promo.bg}`}
    >
      {promo.imageUrl ? (
        <div className="absolute inset-0 overflow-hidden">
          <PromoMedia
            imageUrl={promo.imageUrl}
            posterUrl={promo.posterUrl}
            isVideo={promo.isVideo}
            illustration={Illustration}
            alt={promo.title}
            active={active}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/15 via-transparent to-transparent" />
        </div>
      ) : (
        <div className="absolute inset-0 flex items-end justify-center opacity-80">
          <Illustration />
        </div>
      )}

      <div className="relative flex h-full flex-col items-center justify-center px-4 py-5 text-center">
        {promo.title ? (
          <div className="space-y-1">
            {promo.title.split(/\s+/).map((word, index) => (
              <span
                key={`${word}-${index}`}
                className={`mx-auto block w-fit rounded-md px-2.5 py-0.5 font-display text-lg font-extrabold uppercase leading-none sm:text-xl ${
                  index === 0
                    ? 'bg-brand-accent text-white'
                    : index === 1
                      ? 'bg-white text-brand-ink'
                      : 'bg-brand-cocoa text-white'
                }`}
              >
                {word}
              </span>
            ))}
          </div>
        ) : null}
        {promo.subtitle ? (
          <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-brand-ink/80 sm:text-[11px]">
            {promo.subtitle}
          </p>
        ) : null}
        {promo.badgeText ? (
          <p className={`mt-1 font-display text-3xl font-extrabold sm:text-4xl ${promo.titleColor}`}>
            {promo.badgeText}
          </p>
        ) : null}
      </div>
    </Link>
  )
}

function PromoSlideRow({ slide, active = true }: { slide: PromoSlide; active?: boolean }) {
  const hasSide = Boolean(slide.side)

  return (
    <div className={`grid grid-cols-1 items-stretch ${HOME_GRID_GAP} ${hasSide ? 'lg:grid-cols-3' : ''}`}>
      {slide.main ? (
        <div className={hasSide ? 'min-w-0 lg:col-span-2' : 'min-w-0'}>
          <PromoMainCard promo={slide.main} active={active} />
        </div>
      ) : null}
      {slide.side ? (
        <div className="min-w-0">
          <PromoSideCard promo={slide.side} active={active} />
        </div>
      ) : null}
    </div>
  )
}

function CarouselDots({
  count,
  activeIndex,
  onSelect,
  label,
}: {
  count: number
  activeIndex: number
  onSelect: (index: number) => void
  label: string
}) {
  if (count <= 1) return null

  return (
    <div className="mt-3 flex items-center justify-center gap-2" role="tablist" aria-label={label}>
      {Array.from({ length: count }).map((_, index) => (
        <button
          key={index}
          type="button"
          role="tab"
          aria-selected={index === activeIndex}
          aria-label={`Go to ${label} ${index + 1}`}
          onClick={() => onSelect(index)}
          className={`h-2 rounded-full transition-all ${
            index === activeIndex ? 'w-6 bg-brand-accent' : 'w-2 bg-brand-border hover:bg-brand-rose'
          }`}
        />
      ))}
    </div>
  )
}

function useMovableCarousel(length: number) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const touchStartX = useRef<number | null>(null)

  const goTo = useCallback(
    (index: number) => {
      if (length <= 1) return
      setActiveIndex(((index % length) + length) % length)
    },
    [length],
  )

  const goNext = useCallback(() => {
    if (length <= 1) return
    setActiveIndex((index) => (index + 1) % length)
  }, [length])

  const goPrev = useCallback(() => {
    if (length <= 1) return
    setActiveIndex((index) => (index - 1 + length) % length)
  }, [length])

  useEffect(() => {
    setActiveIndex((index) => (index >= length ? 0 : index))
  }, [length])

  useEffect(() => {
    if (length <= 1 || paused) return undefined
    const timer = window.setInterval(goNext, AUTOPLAY_MS)
    return () => window.clearInterval(timer)
  }, [length, paused, goNext])

  const onTouchStart = (event: TouchEvent) => {
    touchStartX.current = event.touches[0]?.clientX ?? null
  }

  const onTouchEnd = (event: TouchEvent) => {
    const startX = touchStartX.current
    const endX = event.changedTouches[0]?.clientX
    touchStartX.current = null
    if (startX == null || endX == null) return
    const delta = endX - startX
    if (Math.abs(delta) < SWIPE_THRESHOLD) return
    if (delta < 0) goNext()
    else goPrev()
  }

  return {
    activeIndex,
    goTo,
    goNext,
    goPrev,
    paused,
    setPaused,
    onTouchStart,
    onTouchEnd,
  }
}

function MovableCarousel({
  items,
  renderItem,
  ariaLabel,
  className = '',
}: {
  items: unknown[]
  renderItem: (item: unknown, index: number, active: boolean) => ReactNode
  ariaLabel: string
  className?: string
}) {
  const { activeIndex, goTo, goNext, goPrev, setPaused, onTouchStart, onTouchEnd } =
    useMovableCarousel(items.length)

  if (items.length === 0) return null

  return (
    <div
      className={`relative ${className}`}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setPaused(false)
        }
      }}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <div className="overflow-hidden rounded-2xl">
        <div
          className="flex will-change-transform transition-transform duration-500 ease-out"
          style={{ transform: `translate3d(-${activeIndex * 100}%, 0, 0)` }}
        >
          {items.map((item, index) => (
            <div key={index} className="w-full min-w-0 shrink-0">
              {renderItem(item, index, index === activeIndex)}
            </div>
          ))}
        </div>
      </div>

      {items.length > 1 ? (
        <>
          <button
            type="button"
            aria-label={`Previous ${ariaLabel}`}
            onClick={goPrev}
            className="absolute left-2 top-1/2 z-10 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-white/80 bg-white/95 text-brand-ink shadow-sm transition hover:bg-white sm:left-3 sm:h-10 sm:w-10"
          >
            <IconChevronLeft size={18} />
          </button>
          <button
            type="button"
            aria-label={`Next ${ariaLabel}`}
            onClick={goNext}
            className="absolute right-2 top-1/2 z-10 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-white/80 bg-white/95 text-brand-ink shadow-sm transition hover:bg-white sm:right-3 sm:h-10 sm:w-10"
          >
            <IconChevronRight size={18} />
          </button>
        </>
      ) : null}

      <CarouselDots
        count={items.length}
        activeIndex={activeIndex}
        onSelect={goTo}
        label={ariaLabel}
      />
    </div>
  )
}

export function PromoBanners() {
  const { locale, t } = useLocale()
  const { data } = useQuery(storefrontQueries.home)
  const { strips, slides } = useMemo(
    () => groupPromos(data?.promos ?? [], locale, t.hero.shopNow),
    [data?.promos, locale, t.hero.shopNow],
  )

  if (strips.length === 0 && slides.length === 0) return null

  return (
    <section className={`${HOME_CONTAINER} pb-8 pt-4 lg:pb-10 lg:pt-6`}>
      <div className={`flex flex-col ${HOME_GRID_GAP}`}>
        {strips.length > 0 ? <PromoStripMarquee strips={strips} /> : null}

        {slides.length > 0 ? (
          <MovableCarousel
            items={slides}
            ariaLabel="promo banner"
            renderItem={(item, _index, active) => (
              <PromoSlideRow slide={item as PromoSlide} active={active} />
            )}
          />
        ) : null}
      </div>
    </section>
  )
}
