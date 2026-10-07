import { IconBlocks, IconTeddy } from '../icons/Icons'

function RingStacker() {
  return (
    <svg viewBox="0 0 64 80" className="h-16 w-16 sm:h-20 sm:w-20" aria-hidden>
      <ellipse cx="32" cy="74" rx="20" ry="4" fill="#94A3B8" opacity="0.2" />
      <rect x="28" y="58" width="8" height="16" rx="2" fill="#64748B" />
      <ellipse cx="32" cy="58" rx="22" ry="6" fill="#EF4444" />
      <ellipse cx="32" cy="48" rx="20" ry="6" fill="#F97316" />
      <ellipse cx="32" cy="38" rx="18" ry="6" fill="#EAB308" />
      <ellipse cx="32" cy="28" rx="16" ry="6" fill="#22C55E" />
      <ellipse cx="32" cy="18" rx="14" ry="6" fill="#3B82F6" />
      <circle cx="32" cy="10" r="8" fill="#A855F7" />
    </svg>
  )
}

function Sparkle({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" aria-hidden>
      <path
        d="M8 1 L9 5 L13 6 L9 7 L8 11 L7 7 L3 6 L7 5 Z"
        fill="#FBBF24"
      />
    </svg>
  )
}

export function TopBrandsDecorLeft() {
  return (
    <div className="pointer-events-none absolute bottom-6 left-4 hidden opacity-90 md:block lg:left-8 xl:left-12">
      <IconBlocks size={56} className="drop-shadow-md" />
      <div className="mt-2 ml-6 rotate-12">
        <IconBlocks size={40} className="opacity-80" />
      </div>
    </div>
  )
}

export function TopBrandsDecorRight() {
  return (
    <div className="pointer-events-none absolute bottom-4 right-4 hidden items-end gap-2 md:flex lg:right-8 xl:right-12">
      <Sparkle className="absolute -left-6 top-2 h-4 w-4" />
      <Sparkle className="absolute right-16 top-0 h-3 w-3 opacity-80" />
      <div className="flex flex-col items-center">
        <IconTeddy size={72} className="drop-shadow-md" />
        <RingStacker />
      </div>
    </div>
  )
}

export function TopBrandsWave() {
  return (
    <div className="pointer-events-none absolute bottom-0 left-0 w-full translate-y-px leading-none">
      <svg
        viewBox="0 0 1440 56"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="block w-full"
        preserveAspectRatio="none"
        aria-hidden
      >
        <path
          d="M0 40C180 12 360 12 540 28C720 44 900 44 1080 28C1260 12 1350 12 1440 32V56H0V40Z"
          fill="#fff8ee"
        />
      </svg>
    </div>
  )
}
