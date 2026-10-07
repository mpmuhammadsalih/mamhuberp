import type { ReactNode } from 'react'

export function AdminCard({
  children,
  className = '',
  padding = 'p-5',
}: {
  children: ReactNode
  className?: string
  padding?: string
}) {
  return (
    <div className={`rounded-2xl border border-[#eceef4] bg-white shadow-[0_8px_30px_rgba(15,23,42,0.04)] ${padding} ${className}`}>
      {children}
    </div>
  )
}

export function AdminKpiCard({
  label,
  value,
  trend,
  icon,
  accent = 'pink',
}: {
  label: string
  value: string | number
  trend?: string
  icon: ReactNode
  accent?: 'pink' | 'blue' | 'green' | 'orange'
}) {
  const accents = {
    pink: 'bg-[#fff0f5] text-[#E91E63]',
    blue: 'bg-[#eef4ff] text-[#4f7cff]',
    green: 'bg-[#ecfdf3] text-[#16a34a]',
    orange: 'bg-[#fff7ed] text-[#ea580c]',
  }

  return (
    <AdminCard className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-[#64748b]">{label}</p>
        <p className="mt-2 text-2xl font-bold tracking-tight text-[#0f172a]">{value}</p>
        {trend && <p className="mt-1 text-xs font-medium text-[#16a34a]">{trend}</p>}
      </div>
      <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${accents[accent]}`}>{icon}</div>
    </AdminCard>
  )
}

const STATUS_STYLES: Record<string, string> = {
  DELIVERED: 'bg-[#dcfce7] text-[#15803d]',
  CONFIRMED: 'bg-[#dbeafe] text-[#1d4ed8]',
  PROCESSING: 'bg-[#dbeafe] text-[#1d4ed8]',
  PICKING: 'bg-[#e0e7ff] text-[#4338ca]',
  PACKED: 'bg-[#e0e7ff] text-[#4338ca]',
  OUT_FOR_DELIVERY: 'bg-[#cffafe] text-[#0e7490]',
  SHIPPED: 'bg-[#cffafe] text-[#0e7490]',
  CANCELLED: 'bg-[#fee2e2] text-[#b91c1c]',
  ACTIVE: 'bg-[#dcfce7] text-[#15803d]',
  INACTIVE: 'bg-[#f1f5f9] text-[#64748b]',
  APPROVED: 'bg-[#dcfce7] text-[#15803d]',
  PENDING: 'bg-[#fef3c7] text-[#b45309]',
  REJECTED: 'bg-[#fee2e2] text-[#b91c1c]',
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = (status || 'UNKNOWN').toUpperCase().replace(/\s+/g, '_')
  const style = STATUS_STYLES[normalized] ?? 'bg-[#f1f5f9] text-[#475569]'
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}>
      {(status || 'Unknown').replace(/_/g, ' ')}
    </span>
  )
}

export function AdminButton({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
}) {
  const variants = {
    primary: 'bg-[#e91e63] text-white hover:bg-[#c2185b] shadow-sm',
    secondary: 'border border-[#e2e8f0] bg-white text-[#334155] hover:bg-[#f8fafc]',
    ghost: 'text-[#64748b] hover:bg-[#f8fafc]',
    danger: 'bg-[#ef4444] text-white hover:bg-[#dc2626]',
  }
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2.5 text-sm font-semibold',
  }
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-2 rounded-xl transition disabled:opacity-50 ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function AdminSearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}) {
  return (
    <div className={`relative ${className}`}>
      <svg
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#94a3b8]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="7" />
        <path strokeLinecap="round" d="M20 20l-3.5-3.5" />
      </svg>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-[#e2e8f0] bg-white py-2.5 pl-10 pr-4 text-sm text-[#0f172a] outline-none transition focus:border-[#E91E63] focus:ring-2 focus:ring-[#E91E63]/15"
      />
    </div>
  )
}

export function AdminSelect({
  value,
  onChange,
  children,
  className = '',
}: {
  value: string
  onChange: (value: string) => void
  children: ReactNode
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`rounded-xl border border-[#e2e8f0] bg-white px-3 py-2.5 text-sm text-[#334155] outline-none focus:border-[#E91E63] focus:ring-2 focus:ring-[#E91E63]/15 ${className}`}
    >
      {children}
    </select>
  )
}

export function AdminPageTitle({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-[#0f172a]">{title}</h1>
        {description && <p className="mt-1 text-sm text-[#64748b]">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function AdminTableWrap({ children }: { children: ReactNode }) {
  return (
    <AdminCard padding="p-0" className="overflow-hidden">
      <div className="overflow-x-auto">{children}</div>
    </AdminCard>
  )
}

export function AdminAvatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' | 'lg' }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
  const sizes = {
    sm: 'h-8 w-8 text-xs',
    md: 'h-10 w-10 text-sm',
    lg: 'h-16 w-16 text-xl',
  }
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-full bg-[#fce7f3] font-bold text-[#E91E63] ${sizes[size]}`}
    >
      {initials || '?'}
    </div>
  )
}

export function AdminField({
  label,
  children,
  className = '',
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="mb-1.5 block font-medium text-[#475569]">{label}</span>
      {children}
    </label>
  )
}

export function AdminInput({
  className = '',
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-xl border border-[#e2e8f0] px-3 py-2.5 text-sm text-[#0f172a] outline-none focus:border-[#E91E63] focus:ring-2 focus:ring-[#E91E63]/15 ${className}`}
      {...props}
    />
  )
}

export function AdminTextarea({
  className = '',
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`w-full rounded-xl border border-[#e2e8f0] px-3 py-2.5 text-sm text-[#0f172a] outline-none focus:border-[#E91E63] focus:ring-2 focus:ring-[#E91E63]/15 ${className}`}
      {...props}
    />
  )
}

export function AdminToggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label className="flex items-center gap-3 text-sm font-medium text-[#334155]">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 rounded-full transition ${checked ? 'bg-[#e91e63]' : 'bg-[#cbd5e1]'}`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${checked ? 'left-5' : 'left-0.5'}`}
        />
      </button>
      {label}
    </label>
  )
}
