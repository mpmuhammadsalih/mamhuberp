type IconProps = { className?: string; size?: number }

function base(size: number, className?: string) {
  return { width: size, height: size, className, fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
}

export function IconDashboard({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="8" height="8" rx="2" />
      <rect x="13" y="3" width="8" height="5" rx="2" />
      <rect x="13" y="10" width="8" height="11" rx="2" />
      <rect x="3" y="13" width="8" height="8" rx="2" />
    </svg>
  )
}

export function IconProducts({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 7l8-4 8 4-8 4-8-4z" />
      <path strokeLinecap="round" d="M4 12l8 4 8-4M4 17l8 4 8-4" />
    </svg>
  )
}

export function IconCategories({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  )
}

export function IconOrders({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M7 4h10l2 4v11a2 2 0 01-2 2H7a2 2 0 01-2-2V4z" />
      <path strokeLinecap="round" d="M7 4v4h14M9 14h6M9 18h4" />
    </svg>
  )
}

export function IconCustomers({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="9" cy="8" r="3" />
      <path strokeLinecap="round" d="M3 20c1.5-3 3.8-4.5 6-4.5s4.5 1.5 6 4.5" />
      <circle cx="17" cy="9" r="2.5" />
      <path strokeLinecap="round" d="M15.5 20c.8-2 2.2-3 3.5-3s2.7 1 3.5 3" />
    </svg>
  )
}

export function IconInventory({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 7h16v12H4z" />
      <path strokeLinecap="round" d="M4 11h16M8 7V4h8v3" />
    </svg>
  )
}

export function IconCoupons({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 9a2 2 0 012-2h12a2 2 0 012 2v1a2 2 0 010 4v1a2 2 0 01-2 2H6a2 2 0 01-2-2v-1a2 2 0 010-4V9z" />
      <path strokeLinecap="round" d="M12 7v10" strokeDasharray="2 2" />
    </svg>
  )
}

export function IconReviews({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 5h16v11H8l-4 4V5z" />
      <path strokeLinecap="round" d="M8 10h8M8 13h5" />
    </svg>
  )
}

export function IconReports({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M5 19V5M12 19V9M19 19V13" />
    </svg>
  )
}

export function IconSettings({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path strokeLinecap="round" d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4" />
    </svg>
  )
}

export function IconMedia({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="8.5" cy="10.5" r="1.5" fill="currentColor" stroke="none" />
      <path strokeLinecap="round" d="M21 15l-5-5-4 4-3-3-6 6" />
    </svg>
  )
}

export function IconUsers({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="8" r="4" />
      <path strokeLinecap="round" d="M5 20c1.5-3.5 4.5-5.5 7-5.5s5.5 2 7 5.5" />
    </svg>
  )
}

export function IconMenu({ className, size = 20 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  )
}

export function IconPlus({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function IconEdit({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" d="M4 20h4l10-10-4-4L4 16v4z" />
    </svg>
  )
}

export function IconTrendUp({ className, size = 16 }: IconProps) {
  return (
    <svg {...base(size, className)} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" d="M4 16l5-5 4 4 7-8" />
      <path strokeLinecap="round" d="M15 7h5v5" />
    </svg>
  )
}
