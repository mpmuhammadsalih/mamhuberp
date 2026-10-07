type IconProps = { className?: string; size?: number }

function base(size: number, className?: string) {
  return { width: size, height: size, className, fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
}

export function IconBolt({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" fill="currentColor">
      <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />
    </svg>
  )
}

export function IconSearch({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path strokeLinecap="round" d="M20 20l-3.5-3.5" />
    </svg>
  )
}

export function IconCamera({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 8h3l1.2-2h7.6L17 8h3a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2v-8a2 2 0 012-2z" />
      <circle cx="12" cy="14" r="3.2" />
    </svg>
  )
}

export function IconCart({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3h2l1.6 9.2a2 2 0 002 1.8h8.2a2 2 0 001.9-1.4l1.5-5.6H7.2" />
      <circle cx="10" cy="19" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="17" cy="19" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconUser({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="4" />
      <path strokeLinecap="round" d="M5 20c1.5-3.5 4.5-5.5 7-5.5s5.5 2 7 5.5" />
    </svg>
  )
}

export function IconHeart({ className, size = 18, filled = false }: IconProps & { filled?: boolean }) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={filled ? 'currentColor' : 'none'}
        d="M12 20.5l-1.2-1.1C5.4 14.8 2 11.8 2 8.2 2 5.4 4.2 3.5 6.8 3.5c1.5 0 2.9.7 3.8 1.8.9-1.1 2.3-1.8 3.8-1.8 2.6 0 4.8 1.9 4.8 4.7 0 3.6-3.4 6.6-8.8 11.2L12 20.5z"
      />
    </svg>
  )
}

export function IconGift({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="10" width="18" height="11" rx="2" />
      <path strokeLinecap="round" d="M12 10V21M3 14h18" />
      <path strokeLinecap="round" d="M12 10c-2.5 0-4-1.2-4-3.5S9.5 3 12 3s4 1.5 4 3.5-1.5 3.5-4 3.5z" />
    </svg>
  )
}

export function IconCake({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 14h16v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4z" />
      <path strokeLinecap="round" d="M6 14V9a6 6 0 0112 0v5" />
      <path strokeLinecap="round" d="M12 5V3M8 7l-1-1.5M16 7l1-1.5" />
      <circle cx="12" cy="3" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconCalendar({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path strokeLinecap="round" d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  )
}

export function IconTag({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 12l-8 8-8-8V4h8l8 8z" />
      <circle cx="9" cy="9" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconAward({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="9" r="5" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 14l-2 7 6-3 6 3-2-7" />
    </svg>
  )
}

export function IconLock({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path strokeLinecap="round" d="M8 11V8a4 4 0 018 0v3" />
    </svg>
  )
}

export function IconList({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M9 6h12M9 12h12M9 18h12" />
      <circle cx="5" cy="6" r="1" fill="currentColor" stroke="none" />
      <circle cx="5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="5" cy="18" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconMenu({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

export function IconTicket({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 8h16v3a2 2 0 010 4v3H4v-3a2 2 0 010-4V8z" />
      <path strokeLinecap="round" d="M12 8v8" strokeDasharray="2 2" />
    </svg>
  )
}

export function IconTruck({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 7h11v9H3V7z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M14 10h4l3 3v3h-7v-6z" />
      <circle cx="7" cy="18" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="18" cy="18" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconShield({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" />
    </svg>
  )
}

export function IconHeadset({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 14v-2a8 8 0 0116 0v2" />
      <rect x="2" y="14" width="4" height="6" rx="2" />
      <rect x="18" y="14" width="4" height="6" rx="2" />
    </svg>
  )
}

export function IconStar({ className, size = 14, filled = true }: IconProps & { filled?: boolean }) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24">
      <path
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1.5"
        d="M12 2l2.9 6.5L22 9.5l-5 4.5 1.5 6.5L12 17.5 5.5 20.5 7 14 2 9.5l7.1-1L12 2z"
      />
    </svg>
  )
}

export function IconSparkle({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
    </svg>
  )
}

export function IconArrowRight({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

export function IconArrowUpRight({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 17L17 7M17 7H9M17 7v8" />
    </svg>
  )
}

export function IconChevronLeft({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 6l-6 6 6 6" />
    </svg>
  )
}

export function IconChevronRight({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" />
    </svg>
  )
}

export function IconChevronDown({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
    </svg>
  )
}

export function IconFilter({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 5h16l-5.5 7.5V18l-3 1.5V12.5L4 5z"
      />
    </svg>
  )
}

export function IconSort({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 6v12M8 18l-3-3M8 18l3-3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 18V6M16 6l-3 3M16 6l3 3" />
    </svg>
  )
}

export function IconSmile({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="8.5" />
      <path strokeLinecap="round" d="M8.5 10h.01M15.5 10h.01M8.2 14.2c1.1 1.4 2.5 2 3.8 2s2.7-.6 3.8-2" />
    </svg>
  )
}

export function IconMic({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="9" y="3.5" width="6" height="11" rx="3" />
      <path strokeLinecap="round" d="M6.5 11.5a5.5 5.5 0 0011 0M12 17v3.5" />
    </svg>
  )
}

export function IconSend({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" fill="currentColor" stroke="none">
      <path d="M3.4 11.2 20.2 3.6c.7-.3 1.4.4 1.1 1.1l-7.6 16.8c-.3.7-1.3.6-1.5-.2l-1.8-7.2-7.2-1.8c-.8-.2-.9-1.2-.2-1.5z" />
    </svg>
  )
}

export function IconPlus({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
      <path strokeLinecap="round" d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function IconMinus({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.2">
      <path strokeLinecap="round" d="M5 12h14" />
    </svg>
  )
}

export function IconTrash({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M9 7V5h6v2M10 11v6M14 11v6M6 7l1 12h10l1-12" />
    </svg>
  )
}

export function IconCheck({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12l5 5L20 7" />
    </svg>
  )
}

export function IconClose({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

export function IconMapPin({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 21s7-4.5 7-11a7 7 0 10-14 0c0 6.5 7 11 7 11z"
      />
      <circle cx="12" cy="10" r="2.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconRefresh({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 12a8 8 0 0113.66-5.66M20 12a8 8 0 01-13.66 5.66" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 4v4h-4M6 20v-4h4" />
    </svg>
  )
}

export function IconQatarFlag({ className, size = 18 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      className={className}
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="12" cy="12" r="12" fill="#8A1538" />
      <path
        fill="#fff"
        d="M3.2 4.4 8.4 6l-1.8 1.6 1.8 1.5-1.8 1.5 1.8 1.4-1.8 1.5 1.8 1.5-1.8 1.5 1.8 1.6-5.2 1.6z"
      />
    </svg>
  )
}

export function IconReturn({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 10h12a4 4 0 010 8H9"
      />
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 6L4 10l4 4" />
    </svg>
  )
}

export function IconLocate({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path strokeLinecap="round" d="M12 2v4M12 18v4M2 12h4M18 12h4" />
    </svg>
  )
}

export function IconGrid({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  )
}

export function IconHome({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 10.5L12 4l8 6.5V19a1.5 1.5 0 01-1.5 1.5H15v-5.5H9V20.5H5.5A1.5 1.5 0 014 19v-8.5z" />
    </svg>
  )
}

export function IconBlocks({ className, size = 28 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 32 32">
      <rect x="4" y="14" width="10" height="10" rx="2" fill="#F472B6" />
      <rect x="14" y="8" width="10" height="10" rx="2" fill="#38BDF8" />
      <rect x="18" y="18" width="10" height="10" rx="2" fill="#FBBF24" />
    </svg>
  )
}

export function IconBaby({ className, size = 40 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 64 64">
      <ellipse cx="32" cy="54" rx="18" ry="8" fill="#FFD54F" opacity="0.35" />
      <circle cx="32" cy="22" r="13" fill="#FFCCBC" />
      <path d="M19 34c2 10 26 10 28 0v16c0 6-6 10-14 10s-14-4-14-10V34z" fill="#FFC107" />
      <circle cx="27" cy="21" r="2" fill="#4E342E" />
      <circle cx="37" cy="21" r="2" fill="#4E342E" />
      <circle cx="28" cy="20" r="3.5" fill="#FFAB91" opacity="0.5" />
      <circle cx="38" cy="20" r="3.5" fill="#FFAB91" opacity="0.5" />
      <path d="M28 27c2 2 6 2 8 0" stroke="#E65100" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M32 14v-4" stroke="#FFB74D" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="32" cy="8" r="3" fill="#FFB74D" />
    </svg>
  )
}

export function IconTeddy({ className, size = 40 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 64 64">
      <ellipse cx="32" cy="56" rx="16" ry="5" fill="#8D6E63" opacity="0.25" />
      <circle cx="18" cy="18" r="8" fill="#A1887F" />
      <circle cx="46" cy="18" r="8" fill="#A1887F" />
      <circle cx="18" cy="18" r="5" fill="#BCAAA4" />
      <circle cx="46" cy="18" r="5" fill="#BCAAA4" />
      <ellipse cx="32" cy="34" rx="18" ry="16" fill="#8D6E63" />
      <ellipse cx="32" cy="38" rx="12" ry="10" fill="#A1887F" />
      <circle cx="26" cy="30" r="2.5" fill="#3E2723" />
      <circle cx="38" cy="30" r="2.5" fill="#3E2723" />
      <ellipse cx="32" cy="36" rx="4" ry="3" fill="#5D4037" />
      <path d="M32 36l-2 3h4l-2-3z" fill="#5D4037" />
    </svg>
  )
}

export function IconPlane({ className, size = 40 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 64 64">
      <path fill="#EF4444" d="M32 10 22 28h-8l18 10 18-10h-8L32 10z" />
      <path fill="#FBBF24" d="M28 38h8l-4 14-4-14z" />
      <path fill="#3B82F6" d="M14 28h36l-4 8H18l-4-8z" />
      <circle cx="32" cy="24" r="4" fill="#FDE68A" />
      <path fill="#2563EB" d="M8 30h8v4H8zM48 30h8v4H48z" />
    </svg>
  )
}

export function IconRobot({ className, size = 40 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 64 64">
      <rect x="16" y="22" width="32" height="28" rx="6" fill="#42A5F5" />
      <rect x="20" y="28" width="8" height="8" rx="2" fill="#E3F2FD" />
      <rect x="36" y="28" width="8" height="8" rx="2" fill="#E3F2FD" />
      <circle cx="24" cy="32" r="2.5" fill="#1565C0" />
      <circle cx="40" cy="32" r="2.5" fill="#1565C0" />
      <rect x="26" y="40" width="12" height="4" rx="2" fill="#1565C0" />
      <rect x="28" y="14" width="8" height="8" rx="2" fill="#90CAF9" />
      <circle cx="32" cy="10" r="4" fill="#FB923C" />
      <rect x="10" y="30" width="6" height="14" rx="3" fill="#64B5F6" />
      <rect x="48" y="30" width="6" height="14" rx="3" fill="#64B5F6" />
      <rect x="22" y="50" width="8" height="6" rx="2" fill="#1E88E5" />
      <rect x="34" y="50" width="8" height="6" rx="2" fill="#1E88E5" />
    </svg>
  )
}

export function HeroCloud({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 120 60" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="60" cy="35" rx="50" ry="22" fill="white" fillOpacity="0.85" />
      <ellipse cx="40" cy="30" rx="28" ry="18" fill="white" fillOpacity="0.9" />
      <ellipse cx="78" cy="28" rx="32" ry="20" fill="white" fillOpacity="0.9" />
    </svg>
  )
}

export function IconPlay({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5.14v13.72a1 1 0 001.52.85l10.26-6.86a1 1 0 000-1.7L9.52 4.29A1 1 0 008 5.14z" />
    </svg>
  )
}

export function IconPause({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" fill="currentColor">
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  )
}

export function IconVolume({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 10v4h3.5L14 18V6l-5.5 4H5z" fill="currentColor" />
      <path strokeLinecap="round" d="M17 9a4 4 0 010 6M19.5 7a7 7 0 010 10" />
    </svg>
  )
}

export function IconVolumeOff({ className, size = 18 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 10v4h3.5L14 18V6l-5.5 4H5z" fill="currentColor" />
      <path strokeLinecap="round" d="M17 10l5 5M22 10l-5 5" />
    </svg>
  )
}

export function IconFacebook({ className, size = 22 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#111827" d="M22 12.07C22 6.5 17.52 2 12 2S2 6.5 2 12.07c0 5.02 3.66 9.18 8.44 9.93v-7.03H8.08v-2.9h2.36V9.84c0-2.34 1.39-3.63 3.52-3.63.72 0 1.84.13 2.32.26v2.55h-1.3c-1.29 0-1.69.8-1.69 1.63v1.96h2.88l-.46 2.9h-2.42V22c4.78-.75 8.44-4.91 8.44-9.93z" />
    </svg>
  )
}

export function IconX({ className, size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#111827" d="M18.24 3H21l-6.52 7.45L22 21h-6.18l-4.84-6.32L5.4 21H2.62l6.97-7.97L2 3h6.32l4.37 5.8L18.24 3zm-1.08 16.16h1.72L6.92 4.75H5.08l12.08 14.41z" />
    </svg>
  )
}

export function IconInstagram({ className, size = 22 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" fill="none" stroke="#111827" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4" fill="none" stroke="#111827" strokeWidth="1.8" />
      <circle cx="17.2" cy="6.8" r="1.15" fill="#111827" />
    </svg>
  )
}

export function IconYouTube({ className, size = 22 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#111827" d="M23 12.2s-.2-3.3-.5-4.7c-.3-1.1-1.1-1.9-2.2-2.1C18.5 5 12 5 12 5s-6.5 0-8.3.4c-1.1.2-1.9 1-2.2 2.1C1.2 8.9 1 12.2 1 12.2s.2 3.3.5 4.7c.3 1.1 1.1 1.9 2.2 2.1 1.8.4 8.3.4 8.3.4s6.5 0 8.3-.4c1.1-.2 1.9-1 2.2-2.1.3-1.4.5-4.7.5-4.7z" />
      <path fill="#fff" d="M9.8 15.5V8.9l6.3 3.3-6.3 3.3z" />
    </svg>
  )
}

export function IconTikTok({ className, size = 22 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#111827" d="M14.6 3h2.3c.2 1.6 1.1 3 2.4 3.9 1 .7 2.1 1 3.3 1.1V10c-1.5 0-3-.4-4.3-1.1v6.6c0 3.4-2.7 6.2-6.1 6.5A6.4 6.4 0 016.6 11c.6 0 1.2.1 1.8.3v2.5a3.9 3.9 0 00-1.3.1 3.8 3.8 0 003.6 4.6 3.8 3.8 0 003.8-3.8V3z" />
    </svg>
  )
}

export function IconBabyFace({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="13" r="7" />
      <path strokeLinecap="round" d="M8.8 6.8C9.7 5.2 11 4.4 12 4.4s2.3.8 3.2 2.4" />
      <circle cx="9.6" cy="12.6" r="1" fill="currentColor" stroke="none" />
      <circle cx="14.4" cy="12.6" r="1" fill="currentColor" stroke="none" />
      <path strokeLinecap="round" d="M10.2 16.2c.6.7 2 .7 2.6 0" />
    </svg>
  )
}

export function IconGraduation({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7">
      <path strokeLinejoin="round" d="M3 10.5 12 6l9 4.5-9 4.5-9-4.5z" />
      <path strokeLinecap="round" d="M21 10.5v5.2" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.2 12.4v4c1.8 1.7 3.8 2.5 5.8 2.5s4-.8 5.8-2.5v-4" />
    </svg>
  )
}

export function IconTree({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7">
      <path strokeLinejoin="round" d="M12 3 6.2 11h3.1L5 17.8h14L14.7 11h3.1L12 3z" />
      <path strokeLinecap="round" d="M12 17.8V21" />
    </svg>
  )
}

export function IconPercent({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="7.5" cy="7.5" r="2.4" />
      <circle cx="16.5" cy="16.5" r="2.4" />
      <path strokeLinecap="round" d="M17 7 7 17" />
    </svg>
  )
}

export function IconChat({ className, size = 22 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M5 6.5A3.5 3.5 0 018.5 3h7A3.5 3.5 0 0119 6.5v6A3.5 3.5 0 0115.5 16H12l-4.2 3.1c-.7.5-1.8 0-1.8-.9V16H8.5A3.5 3.5 0 015 12.5v-6z"
      />
    </svg>
  )
}

export function IconWhatsApp({ className, size = 24 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" fill="currentColor">
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
    </svg>
  )
}

export function HeroBalloon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 80 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="40" cy="38" rx="28" ry="34" fill="#F9A8D4" />
      <ellipse cx="40" cy="38" rx="28" ry="34" fill="url(#balloonStripe)" />
      <path d="M40 72v30" stroke="#F472B6" strokeWidth="2" strokeLinecap="round" />
      <path d="M40 102c-6 4-10 4-10 4" stroke="#F472B6" strokeWidth="2" strokeLinecap="round" />
      <defs>
        <pattern id="balloonStripe" patternUnits="userSpaceOnUse" width="8" height="8">
          <rect width="4" height="8" fill="white" fillOpacity="0.25" />
        </pattern>
      </defs>
    </svg>
  )
}

export function HeroStar({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="#FBBF24" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2l2.5 5.5L20 8.5l-4 3.8 1.2 5.7L12 15.5 6.8 18l1.2-5.7-4-3.8 5.5-.9L12 2z" />
    </svg>
  )
}
