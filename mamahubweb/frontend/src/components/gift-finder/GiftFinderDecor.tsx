import { IconBlocks, IconTeddy } from '../icons/Icons'

function RingStacker() {
  return (
    <svg viewBox="0 0 48 60" className="h-14 w-11" aria-hidden>
      <rect x="20" y="44" width="8" height="12" rx="2" fill="#64748B" />
      <ellipse cx="24" cy="44" rx="16" ry="4" fill="#EF4444" />
      <ellipse cx="24" cy="36" rx="14" ry="4" fill="#F97316" />
      <ellipse cx="24" cy="28" rx="12" ry="4" fill="#EAB308" />
      <ellipse cx="24" cy="20" rx="10" ry="4" fill="#22C55E" />
      <circle cx="24" cy="12" r="7" fill="#A855F7" />
    </svg>
  )
}

function ToyCar() {
  return (
    <svg viewBox="0 0 56 40" className="h-10 w-14" aria-hidden>
      <rect x="8" y="18" width="36" height="12" rx="4" fill="#3B82F6" />
      <rect x="14" y="12" width="18" height="10" rx="3" fill="#60A5FA" />
      <circle cx="16" cy="32" r="5" fill="#334155" />
      <circle cx="40" cy="32" r="5" fill="#334155" />
    </svg>
  )
}

export function GiftFinderDecor() {
  return (
    <div className="pointer-events-none relative hidden shrink-0 lg:block lg:w-[280px] xl:w-[320px]">
      <div className="absolute -right-2 top-0 flex items-end justify-end gap-2">
        <div className="flex flex-col items-center gap-1">
          <IconBlocks size={40} className="drop-shadow-md" />
          <div className="ml-4">
            <IconBlocks size={28} className="opacity-90" />
          </div>
        </div>
        <IconTeddy size={80} className="drop-shadow-lg" />
        <div className="flex flex-col items-center pb-2">
          <RingStacker />
          <ToyCar />
        </div>
      </div>
    </div>
  )
}

export function GiftFinderPaperPlane() {
  return (
    <svg viewBox="0 0 120 32" className="hidden h-8 w-28 sm:block" aria-hidden>
      <path
        d="M4 16 Q30 8 60 16 T116 12"
        stroke="#E91E63"
        strokeWidth="2"
        strokeDasharray="4 4"
        fill="none"
        opacity="0.5"
      />
      <path d="M110 10 L118 14 L110 18 Z" fill="#E91E63" opacity="0.7" />
    </svg>
  )
}
