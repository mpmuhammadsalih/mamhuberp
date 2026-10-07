import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { IconChevronDown } from '../icons/Icons'

interface Item {
  href: string
  label: string
}

interface Props {
  label: string
  items: Item[]
  footerHref?: string
  footerLabel?: string
  active?: boolean
  icon?: ReactNode
  onHover?: () => void
}

export function HeaderNavMenu({
  label,
  items,
  footerHref,
  footerLabel,
  active = false,
  icon,
  onHover,
}: Props) {
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0, width: 224 })
  const rootRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const closeTimer = useRef<number>(0)

  function cancelClose() {
    window.clearTimeout(closeTimer.current)
  }

  function scheduleClose() {
    cancelClose()
    closeTimer.current = window.setTimeout(() => setOpen(false), 160)
  }

  function openMenu() {
    cancelClose()
    onHover?.()
    setOpen(true)
  }

  function updatePosition() {
    const el = rootRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const width = Math.max(224, rect.width)
    const rtl = document.documentElement.dir === 'rtl'
    const left = rtl ? Math.max(8, rect.right - width) : Math.min(rect.left, window.innerWidth - width - 8)
    setCoords({
      top: rect.bottom + 4,
      left: Math.max(8, left),
      width,
    })
  }

  useLayoutEffect(() => {
    if (!open) return
    updatePosition()
  }, [open])

  useEffect(() => {
    if (!open) return undefined

    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setOpen(false)
    }

    function onEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    function onReposition() {
      updatePosition()
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onEscape)
    window.addEventListener('resize', onReposition)
    window.addEventListener('scroll', onReposition, true)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onEscape)
      window.removeEventListener('resize', onReposition)
      window.removeEventListener('scroll', onReposition, true)
    }
  }, [open])

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  const menu =
    open && typeof document !== 'undefined'
      ? createPortal(
          <div
            ref={menuRef}
            className="fixed z-[220]"
            style={{ top: coords.top, left: coords.left, width: coords.width }}
            onMouseEnter={openMenu}
            onMouseLeave={scheduleClose}
          >
            <div className="max-h-[min(70vh,22rem)] overflow-y-auto rounded-xl bg-white py-1 shadow-lg ring-1 ring-black/10">
              {items.length === 0 ? (
                <p className="px-3 py-2 text-sm text-slate-400">—</p>
              ) : (
                items.map((item) => (
                  <MenuLink key={item.href} href={item.href} onClick={() => setOpen(false)}>
                    {item.label}
                  </MenuLink>
                ))
              )}
              {footerHref && footerLabel ? (
                <MenuLink href={footerHref} onClick={() => setOpen(false)} emph>
                  {footerLabel}
                </MenuLink>
              ) : null}
            </div>
          </div>,
          document.body,
        )
      : null

  return (
    <div
      className="relative shrink-0"
      ref={rootRef}
      onMouseEnter={openMenu}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        onClick={() => {
          cancelClose()
          if (open) setOpen(false)
          else openMenu()
        }}
        className={`flex min-w-[3.5rem] flex-col items-center gap-1 rounded-2xl px-2 py-1.5 text-[12px] font-medium transition lg:min-w-[4.25rem] lg:px-3 lg:text-[13px] ${
          active || open ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-700 hover:bg-white/70 hover:text-slate-900'
        }`}
        aria-expanded={open}
        aria-haspopup="true"
      >
        {icon}
        <span className="inline-flex items-center gap-0.5 leading-none">
          {label}
          <IconChevronDown size={12} className={`text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {menu}
    </div>
  )
}

function MenuLink({
  href,
  onClick,
  children,
  emph = false,
}: {
  href: string
  onClick: () => void
  children: ReactNode
  emph?: boolean
}) {
  return (
    <Link
      to={href}
      onClick={onClick}
      className={`block px-3 py-2 text-sm transition hover:bg-brand-cream-alt hover:text-brand-accent ${
        emph ? 'font-semibold text-brand-accent' : 'text-slate-700'
      }`}
    >
      {children}
    </Link>
  )
}
