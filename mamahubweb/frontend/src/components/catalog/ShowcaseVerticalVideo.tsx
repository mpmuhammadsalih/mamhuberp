import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { IconPause, IconPlay } from '../icons/Icons'

const SHOWCASE_FALLBACK_POSTER = '/images/showcase-new-arrivals.jpg'
const SHOWCASE_FALLBACK_VIDEO =
  'https://assets.mixkit.co/videos/preview/mixkit-little-girl-playing-with-a-plush-toy-43703-large.mp4'
export interface ShowcaseBannerConfig {
  title: string
  href: string
  imageSrc?: string
  videoSrc?: string
  posterSrc?: string
  gradientFrom?: string
  gradientTo?: string
}

function ShowcaseMedia({
  banner,
  className = '',
  videoClassName = '',
}: {
  banner: ShowcaseBannerConfig
  className?: string
  videoClassName?: string
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(true)
  const [usePoster, setUsePoster] = useState(false)

  const poster = banner.posterSrc ?? banner.imageSrc ?? SHOWCASE_FALLBACK_POSTER
  const videoSrc = banner.videoSrc ?? SHOWCASE_FALLBACK_VIDEO

  useEffect(() => {
    setUsePoster(false)
    setPlaying(true)
  }, [videoSrc])

  function handleCanPlay() {
    const video = videoRef.current
    if (!video || usePoster) return
    void video.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
  }

  function togglePlayback() {    const video = videoRef.current
    if (!video || usePoster) return
    if (video.paused) {
      void video.play()
      setPlaying(true)
    } else {
      video.pause()
      setPlaying(false)
    }
  }

  if (usePoster || !banner.videoSrc) {    return (
      <img
        src={poster}
        alt=""
        className={className}
        loading="lazy"
        onError={(event) => {
          event.currentTarget.onerror = null
          event.currentTarget.src = SHOWCASE_FALLBACK_POSTER
        }}
      />
    )
  }

  return (
    <>
      <video
        key={videoSrc}
        ref={videoRef}
        className={videoClassName || className}
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        poster={poster}
        onCanPlay={handleCanPlay}
        onError={() => setUsePoster(true)}
      >
        <source src={videoSrc} />
      </video>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          togglePlayback()
        }}
        className="absolute right-2.5 top-2.5 z-20 flex h-8 w-8 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/60"
        aria-label={playing ? 'Pause video' : 'Play video'}
      >
        {playing ? <IconPause size={14} /> : <IconPlay size={14} />}
      </button>
    </>
  )
}

export function ShowcaseMobileBanner({ banner }: { banner: ShowcaseBannerConfig }) {
  const from = banner.gradientFrom ?? 'from-brand-accent'
  const to = banner.gradientTo ?? 'to-brand-purple'

  return (
    <Link
      to={banner.href}
      className={`relative mb-4 flex min-h-[180px] overflow-hidden rounded-2xl bg-gradient-to-br ${from} ${to} lg:hidden`}
    >
      <div className="relative z-10 flex w-[42%] flex-col justify-end p-4">
        <p className="text-base font-bold leading-snug text-white">{banner.title}</p>
      </div>
      <div className="relative ml-auto w-[58%] min-w-[140px]">
        <ShowcaseMedia
          banner={banner}
          className="absolute inset-0 h-full w-full object-cover"
          videoClassName="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-black/35 via-transparent to-transparent" />
      </div>
    </Link>
  )
}

export function ShowcaseVerticalVideo({
  banner,
  className = '',
}: {
  banner: ShowcaseBannerConfig
  className?: string
}) {
  const from = banner.gradientFrom ?? 'from-brand-accent'
  const to = banner.gradientTo ?? 'to-brand-purple'

  return (
    <Link
      to={banner.href}
      className={`group relative hidden min-h-0 flex-col overflow-hidden rounded-2xl bg-gradient-to-b ${from} ${to} shadow-sm ring-1 ring-black/5 lg:flex ${className}`}
    >
      <div className="relative z-10 shrink-0 p-4 pb-3">
        <p className="text-lg font-bold leading-[1.2] tracking-tight text-white xl:text-xl">
          {banner.title}
        </p>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        <ShowcaseMedia
          banner={banner}
          className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          videoClassName="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-black/10 to-transparent" />
      </div>
    </Link>
  )
}

export { SHOWCASE_FALLBACK_POSTER, SHOWCASE_FALLBACK_VIDEO }
