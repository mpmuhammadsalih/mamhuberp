import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import {
  IconArrowRight,
  IconChevronLeft,
  IconChevronRight,
  IconGift,
  IconMapPin,
  IconPause,
  IconPlay,
  IconReturn,
  IconTruck,
} from './icons/Icons'
import { resolveMediaUrl, isVideoMediaUrl } from '../lib/media'
import { useLocale } from '../i18n/LocaleContext'
import { mediaSubtitle, mediaTitle } from '../i18n/mediaText'
import type { TranslationTree } from '../i18n/types'
import type { SupportedLocale } from '../i18n/types'
import { storefrontQueries, type MediaItem, type StorefrontHome } from '../lib/queries/storefront'

const HERO_POSTER = '/images/hero-child.jpg'
const HERO_MIXKIT_VIDEO =
  'https://assets.mixkit.co/videos/preview/mixkit-little-boy-playing-with-a-toy-43704-large.mp4'
const AUTOPLAY_MS = 6000

const PANEL_PRESETS = [
  'bg-gradient-to-br from-brand-purple via-violet-500 to-brand-accent',
  'bg-gradient-to-br from-brand-teal via-cyan-500 to-brand-yellow',
  'bg-gradient-to-br from-brand-orange via-amber-400 to-brand-accent',
  'bg-gradient-to-br from-sky-500 via-blue-500 to-brand-purple',
]

interface HeroSlideView {
  id: string
  panelClass: string
  panelImageUrl?: string
  posterUrl: string
  videoCandidates: string[]
  eyebrow?: string
  title: string
  subtitle: string
  primaryCta: { label: string; href: string }
  secondaryCta?: { label: string; href: string; icon?: 'gift' }
}

function resolvePanelClass(raw: string | undefined, index: number): string {
  const value = raw?.trim()
  if (value && (value.includes('gradient') || value.startsWith('bg-'))) {
    return value.includes('gradient') ? value : PANEL_PRESETS[index % PANEL_PRESETS.length]
  }
  return PANEL_PRESETS[index % PANEL_PRESETS.length]
}

function buildVideoCandidates(item: MediaItem, globalVideo?: string | null): string[] {
  const candidates: string[] = []
  const push = (url?: string | null) => {
    const resolved = resolveMediaUrl(url)
    if (resolved && !candidates.includes(resolved)) {
      candidates.push(resolved)
    }
  }

  const meta = item.meta ?? {}
  push(String(meta.video_url ?? ''))
  if (isVideoMediaUrl(item.image_url)) {
    push(item.image_url)
  }
  if (globalVideo && candidates.length === 0) {
    push(globalVideo)
  }

  return candidates
}

function mapSlide(
  item: MediaItem,
  index: number,
  fallbackPoster: string,
  globalVideo: string | null | undefined,
  t: TranslationTree,
  locale: SupportedLocale,
): HeroSlideView {
  const meta = item.meta ?? {}
  const posterUrl = resolveMediaUrl(item.image_url) ?? fallbackPoster
  const panelImageUrl = resolveMediaUrl(String(meta.panel_image ?? ''))

  return {
    id: String(item.ref_key ?? item.media_id ?? index),
    panelClass: resolvePanelClass(String(meta.panel_class ?? ''), index),
    panelImageUrl,
    posterUrl,
    videoCandidates: buildVideoCandidates(item, index === 0 ? globalVideo : null),
    eyebrow: meta.eyebrow ? String(meta.eyebrow) : undefined,
    title: mediaTitle(item, locale, t.hero.defaultTitle),
    subtitle: mediaSubtitle(item, locale, t.hero.defaultSubtitle),
    primaryCta: {
      label: String((meta.primary_cta as { label?: string })?.label ?? t.hero.shopNow),
      href: item.link_url ?? '/products',
    },
    secondaryCta: meta.secondary_cta as HeroSlideView['secondaryCta'],
  }
}

function getFallbackSlides(t: TranslationTree): HeroSlideView[] {
  return [
    {
      id: 'brand',
      panelClass: PANEL_PRESETS[0],
      posterUrl: HERO_POSTER,
      videoCandidates: [HERO_MIXKIT_VIDEO],
      eyebrow: t.hero.slide1Eyebrow,
      title: t.hero.defaultTitle,
      subtitle: t.hero.defaultSubtitle,
      primaryCta: { label: t.hero.shopNow, href: '/products' },
      secondaryCta: { label: t.hero.giftFinder, href: '/gift-finder', icon: 'gift' },
    },
    {
      id: 'gifts',
      panelClass: PANEL_PRESETS[1],
      posterUrl: HERO_POSTER,
      videoCandidates: [],
      eyebrow: t.hero.slide2Eyebrow,
      title: t.hero.slide2Title,
      subtitle: t.hero.slide2Subtitle,
      primaryCta: { label: t.hero.giftFinder, href: '/gift-finder' },
      secondaryCta: { label: t.hero.shopToys, href: '/products', icon: undefined },
    },
    {
      id: 'outdoor',
      panelClass: PANEL_PRESETS[2],
      posterUrl: HERO_POSTER,
      videoCandidates: [],
      eyebrow: t.hero.slide3Eyebrow,
      title: t.hero.slide3Title,
      subtitle: t.hero.slide3Subtitle,
      primaryCta: { label: t.hero.shopOutdoor, href: '/products?q=outdoor' },
      secondaryCta: { label: t.hero.shopByAge, href: '/products', icon: undefined },
    },
  ]
}

const RAINBOW = [
  'bg-brand-yellow',
  'bg-brand-teal',
  'bg-brand-accent',
  'bg-brand-purple',
  'bg-brand-orange',
  'bg-sky-400',
]

function HeroPattern() {
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full text-white/20"
      aria-hidden
      preserveAspectRatio="xMidYMid slice"
    >
      <defs>
        <pattern id="hero-shapes" width="120" height="120" patternUnits="userSpaceOnUse">
          <circle cx="24" cy="24" r="14" fill="currentColor" opacity="0.35" />
          <rect x="72" y="16" width="28" height="28" rx="4" fill="currentColor" opacity="0.25" />
          <path d="M16 78h28v28H16z" fill="currentColor" opacity="0.2" />
          <circle cx="88" cy="88" r="10" fill="currentColor" opacity="0.3" />
          <path
            d="M58 58h8v24h-8zM46 70h32v8H46z"
            fill="currentColor"
            opacity="0.22"
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#hero-shapes)" />
    </svg>
  )
}

function HeroMediaPanel({
  posterUrl,
  videoCandidates,
  active,
}: {
  posterUrl: string
  videoCandidates: string[]
  active: boolean
}) {
  const { t } = useLocale()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(true)
  const [candidateIndex, setCandidateIndex] = useState(0)
  const [usePoster, setUsePoster] = useState(false)

  const videoUrl = videoCandidates[candidateIndex] ?? videoCandidates[0] ?? ''
  const showVideo = Boolean(videoUrl) && !usePoster

  useEffect(() => {
    setUsePoster(false)
    setPlaying(true)
    setCandidateIndex(0)
  }, [posterUrl, videoCandidates.join('|')])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !showVideo || !active) {
      video?.pause()
      return
    }
    void video.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
  }, [showVideo, active, videoUrl])

  function handleCanPlay() {
    const video = videoRef.current
    if (!video || usePoster || !active) return
    void video.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
  }

  function handleVideoError() {
    if (candidateIndex + 1 < videoCandidates.length) {
      setCandidateIndex((index) => index + 1)
      return
    }
    setUsePoster(true)
  }

  function togglePlayback() {
    const video = videoRef.current
    if (!video || !showVideo) return
    if (video.paused) {
      void video.play()
      setPlaying(true)
    } else {
      video.pause()
      setPlaying(false)
    }
  }

  return (
    <div
      className={`absolute inset-0 overflow-hidden transition-opacity duration-700 ${active ? 'z-10 opacity-100' : 'z-0 opacity-0'}`}
      aria-hidden={!active}
    >
      <img
        src={posterUrl}
        alt=""
        aria-hidden
        className="absolute inset-0 h-full w-full scale-105 object-cover blur-xl opacity-60"
      />

      {showVideo ? (
        <video
          key={videoUrl}
          ref={videoRef}
          className="absolute inset-0 z-[1] h-full w-full object-cover object-center"
          autoPlay={active}
          muted
          loop
          playsInline
          preload={active ? 'metadata' : 'none'}
          poster={posterUrl}
          onCanPlay={handleCanPlay}
          onError={handleVideoError}
        >
          <source src={videoUrl} type="video/mp4" />
        </video>
      ) : (
        <img
          src={posterUrl}
          alt=""
          className="absolute inset-0 z-[1] h-full w-full object-cover object-center"
          loading={active ? 'eager' : 'lazy'}
          fetchPriority={active ? 'high' : 'low'}
        />
      )}

      {showVideo && active && (
        <button
          type="button"
          onClick={togglePlayback}
          className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/60"
          aria-label={playing ? t.hero.pauseVideo : t.hero.playVideo}
        >
          {playing ? <IconPause size={16} /> : <IconPlay size={16} />}
        </button>
      )}
    </div>
  )
}

function resolveGlobalHeroVideo(data: StorefrontHome | undefined): string | undefined {
  const bg = data?.hero_background
  if (!bg) return undefined
  const rawBgUrl = bg.image_url
  const bgUrl = resolveMediaUrl(rawBgUrl)
  const bgMeta = bg.meta ?? {}
  const metaVideoUrl = resolveMediaUrl(String(bgMeta.video_url ?? ''))
  if (isVideoMediaUrl(rawBgUrl) || isVideoMediaUrl(bgUrl)) {
    return bgUrl
  }
  return metaVideoUrl
}

function HeroSlideContent({ slide }: { slide: HeroSlideView }) {
  const giftCta = slide.secondaryCta?.icon === 'gift' ? slide.secondaryCta : undefined
  const shopCta = slide.primaryCta
  const altSecondary = slide.secondaryCta && slide.secondaryCta.icon !== 'gift' ? slide.secondaryCta : undefined

  return (
    <>
      {slide.eyebrow && (
        <span className="inline-block rounded-full bg-white/15 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-white ring-1 ring-white/25 backdrop-blur-sm">
          {slide.eyebrow}
        </span>
      )}

      <h1 className="mt-4 font-display text-3xl font-extrabold leading-[1.08] text-white sm:text-4xl lg:text-[2.85rem]">
        {slide.title}
      </h1>

      {slide.subtitle && (
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-white/90 sm:mt-4 sm:text-base">
          {slide.subtitle}
        </p>
      )}

      <div className="mt-6 flex flex-wrap gap-3 sm:mt-8">
        {giftCta ? (
          <>
            <Link
              to={giftCta.href}
              className="inline-flex items-center gap-2 rounded-full bg-brand-accent px-7 py-3 text-sm font-bold text-white shadow-md transition hover:bg-brand-accent-hover hover:shadow-lg"
            >
              <IconGift size={18} />
              {giftCta.label}
            </Link>
            <Link
              to={shopCta.href}
              className="inline-flex items-center gap-2 rounded-full border-2 border-white/80 bg-white/10 px-7 py-3 text-sm font-bold text-white backdrop-blur-sm transition hover:bg-white/20"
            >
              {shopCta.label}
              <IconArrowRight size={16} />
            </Link>
          </>
        ) : (
          <>
            <Link
              to={shopCta.href}
              className="inline-flex items-center gap-2 rounded-full bg-brand-accent px-7 py-3 text-sm font-bold text-white shadow-md transition hover:bg-brand-accent-hover hover:shadow-lg"
            >
              {shopCta.label}
              <IconArrowRight size={16} />
            </Link>
            {altSecondary && (
              <Link
                to={altSecondary.href}
                className="inline-flex items-center gap-2 rounded-full border-2 border-white/80 bg-white/10 px-7 py-3 text-sm font-bold text-white backdrop-blur-sm transition hover:bg-white/20"
              >
                {altSecondary.label}
              </Link>
            )}
          </>
        )}
      </div>
    </>
  )
}

export function HeroSection() {
  const { locale, t } = useLocale()
  const { data } = useQuery(storefrontQueries.home)
  const [activeIndex, setActiveIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [progressKey, setProgressKey] = useState(0)

  const heroPoster =
    resolveMediaUrl(String(data?.hero_background?.meta?.poster_url ?? '')) ??
    resolveMediaUrl(data?.hero_slides?.[0]?.image_url) ??
    HERO_POSTER

  const globalVideo = resolveGlobalHeroVideo(data)

  const trustItems = useMemo(
    () => [
      { icon: IconTruck, label: t.hero.trustFreeDelivery },
      { icon: IconMapPin, label: t.hero.trustFastDelivery },
      { icon: IconReturn, label: t.hero.trustEasyReturns },
    ],
    [t],
  )

  const slides = useMemo(() => {
    const apiSlides = data?.hero_slides ?? []
    if (apiSlides.length > 0) {
      return apiSlides.map((item, index) => mapSlide(item, index, heroPoster, globalVideo, t, locale))
    }
    return getFallbackSlides(t)
  }, [data?.hero_slides, heroPoster, globalVideo, t, locale])

  const slideCount = slides.length
  const activeSlide = slides[activeIndex] ?? slides[0]

  const goTo = useCallback(
    (index: number) => {
      if (slideCount <= 1) return
      setActiveIndex(((index % slideCount) + slideCount) % slideCount)
      setProgressKey((key) => key + 1)
    },
    [slideCount],
  )

  const goNext = useCallback(() => goTo(activeIndex + 1), [activeIndex, goTo])
  const goPrev = useCallback(() => goTo(activeIndex - 1), [activeIndex, goTo])

  useEffect(() => {
    setActiveIndex((index) => (index >= slideCount ? 0 : index))
  }, [slideCount])

  useEffect(() => {
    if (slideCount <= 1 || paused) return undefined
    const timer = window.setInterval(() => {
      goNext()
    }, AUTOPLAY_MS)
    return () => window.clearInterval(timer)
  }, [slideCount, paused, activeIndex, goNext])

  return (
    <section className="relative w-full overflow-hidden bg-brand-cream">
      <div className="border-b border-brand-border/70 bg-brand-tint/80">
        <div className="mx-auto flex max-w-[1560px] flex-wrap items-center justify-center gap-x-6 gap-y-2 px-4 py-2.5 text-[11px] font-semibold text-brand-cocoa sm:px-6 sm:text-xs lg:px-12">
          {trustItems.map((item, index) => {
            const Icon = item.icon
            return (
              <span key={index} className="inline-flex items-center gap-1.5">
                <Icon size={14} className="shrink-0 text-brand-accent" />
                {item.label}
              </span>
            )
          })}
        </div>
      </div>

      <div
        className="relative grid gap-0 overflow-hidden lg:grid-cols-2 lg:items-stretch"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocusCapture={() => setPaused(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setPaused(false)
          }
        }}
      >
        <div className="relative flex min-h-[280px] items-center overflow-hidden px-6 py-10 sm:px-10 sm:py-12 lg:min-h-[420px] lg:px-14">
          {slides.map((slide, index) => (
            <div
              key={slide.id}
              className={`absolute inset-0 transition-opacity duration-700 ${slide.panelClass} ${
                index === activeIndex ? 'opacity-100' : 'pointer-events-none opacity-0'
              }`}
              aria-hidden={index !== activeIndex}
            >
              {slide.panelImageUrl ? (
                <>
                  <img
                    src={slide.panelImageUrl}
                    alt=""
                    className="absolute inset-0 h-full w-full object-cover"
                  />
                  <div className="pointer-events-none absolute inset-0 bg-brand-purple/55" />
                </>
              ) : null}
              <HeroPattern />
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-black/10 via-transparent to-black/20" />
            </div>
          ))}

          <div
            key={activeSlide.id}
            className="relative z-10 max-w-lg animate-[fadeSlideIn_0.55s_ease-out]"
          >
            <HeroSlideContent slide={activeSlide} />
          </div>

          {slideCount > 1 && (
            <>
              <div className="absolute bottom-5 left-6 right-6 z-20 flex gap-2 sm:left-10 lg:left-14 lg:max-w-md">
                {slides.map((slide, index) => (
                  <button
                    key={slide.id}
                    type="button"
                    onClick={() => goTo(index)}
                    className="h-1 flex-1 overflow-hidden rounded-full bg-white/30 transition hover:bg-white/45"
                    aria-label={`${t.hero.showSlide} ${index + 1}: ${slide.title}`}
                    aria-current={index === activeIndex ? 'true' : undefined}
                  >
                    <span
                      key={index === activeIndex ? `progress-${progressKey}` : `bar-${index}`}
                      className={`block h-full rounded-full bg-white ${
                        index === activeIndex
                          ? paused
                            ? 'w-full opacity-70'
                            : 'hero-slide-progress'
                          : index < activeIndex
                            ? 'w-full'
                            : 'w-0'
                      }`}
                      style={
                        index === activeIndex && !paused
                          ? ({ '--hero-autoplay-ms': `${AUTOPLAY_MS}ms` } as CSSProperties)
                          : undefined
                      }
                    />
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={goPrev}
                className="absolute left-2 top-1/2 z-20 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/25 text-white backdrop-blur-sm transition hover:bg-black/40 sm:flex lg:left-4"
                aria-label={t.shared.previousSlide}
              >
                <IconChevronLeft size={20} />
              </button>
            </>
          )}
        </div>

        <div className="relative aspect-[5/4] min-h-[220px] sm:aspect-[16/11] sm:min-h-[280px] lg:aspect-auto lg:h-full lg:min-h-[420px]">
          {slides.map((slide, index) => (
            <HeroMediaPanel
              key={slide.id}
              posterUrl={slide.posterUrl}
              videoCandidates={slide.videoCandidates}
              active={index === activeIndex}
            />
          ))}

          {slideCount > 1 && (
            <button
              type="button"
              onClick={goNext}
              className="absolute right-2 top-1/2 z-20 hidden h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-black/25 text-white backdrop-blur-sm transition hover:bg-black/40 sm:flex lg:right-4"
              aria-label={t.shared.nextSlide}
            >
              <IconChevronRight size={20} />
            </button>
          )}
        </div>
      </div>

      <div className="flex h-2 w-full" aria-hidden>
        {RAINBOW.map((color, index) => (
          <span key={index} className={`flex-1 ${color}`} />
        ))}
      </div>
    </section>
  )
}
