import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'

const MAX_TILT = 14

interface Props {
  children: ReactNode
  className?: string
}

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function canPointerTilt() {
  return window.matchMedia('(hover: hover) and (pointer: fine)').matches
}

export function Product3DViewer({ children, className = '' }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef(0)
  const [tilt, setTilt] = useState({ x: 0, y: 0, gx: 50, gy: 50, active: false })
  const [mode, setMode] = useState<'still' | 'pointer' | 'sway'>('still')

  useEffect(() => {
    function sync() {
      if (prefersReducedMotion()) setMode('still')
      else if (canPointerTilt()) setMode('pointer')
      else setMode('sway')
    }
    sync()
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const hover = window.matchMedia('(hover: hover) and (pointer: fine)')
    motion.addEventListener('change', sync)
    hover.addEventListener('change', sync)
    return () => {
      motion.removeEventListener('change', sync)
      hover.removeEventListener('change', sync)
    }
  }, [])

  useEffect(() => () => window.cancelAnimationFrame(frameRef.current), [])

  function applyFromEvent(event: PointerEvent<HTMLDivElement>) {
    if (mode !== 'pointer') return
    const el = rootRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return
    const px = (event.clientX - rect.left) / rect.width
    const py = (event.clientY - rect.top) / rect.height
    const next = {
      x: (0.5 - py) * MAX_TILT * 2,
      y: (px - 0.5) * MAX_TILT * 2,
      gx: px * 100,
      gy: py * 100,
      active: true,
    }
    window.cancelAnimationFrame(frameRef.current)
    frameRef.current = window.requestAnimationFrame(() => setTilt(next))
  }

  function reset() {
    window.cancelAnimationFrame(frameRef.current)
    setTilt({ x: 0, y: 0, gx: 50, gy: 50, active: false })
  }

  return (
    <div
      ref={rootRef}
      className={`relative h-full w-full [perspective:56rem] ${className}`}
      onPointerEnter={applyFromEvent}
      onPointerMove={applyFromEvent}
      onPointerLeave={reset}
      onPointerCancel={reset}
    >
      <div
        className={`relative h-full w-full overflow-hidden rounded-[28px] bg-white shadow-[0_10px_28px_rgba(15,23,42,0.06)] ring-1 ring-slate-200/80 [transform:rotateX(0deg)_rotateY(0deg)] [transform-style:preserve-3d] ${
          mode === 'sway' ? 'product-3d-sway' : ''
        }`}
        style={
          mode === 'pointer'
            ? {
                transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
                transition: tilt.active ? 'transform 80ms linear' : 'transform 320ms ease',
              }
            : undefined
        }
      >
        {children}
        {mode === 'pointer' ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-[28px]"
            style={{
              background: `radial-gradient(circle at ${tilt.gx}% ${tilt.gy}%, rgba(255,255,255,0.4), transparent 42%)`,
              opacity: tilt.active ? 1 : 0,
              transition: 'opacity 200ms ease',
            }}
          />
        ) : null}
      </div>
    </div>
  )
}
