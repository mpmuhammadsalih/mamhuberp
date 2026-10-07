import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AdminAvatar } from '../components/admin/ui'
import {
  IconCategories,
  IconCoupons,
  IconCustomers,
  IconDashboard,
  IconInventory,
  IconMedia,
  IconMenu,
  IconOrders,
  IconProducts,
  IconReports,
  IconReviews,
  IconSettings,
  IconUsers,
} from '../components/admin/AdminNavIcons'
import { IconClose } from '../components/icons/Icons'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'

const nav = [
  { to: '/admin', label: 'Dashboard', end: true, icon: IconDashboard },
  { to: '/admin/products', label: 'Products', icon: IconProducts },
  { to: '/admin/categories', label: 'Categories', icon: IconCategories },
  { to: '/admin/orders', label: 'Orders', icon: IconOrders },
  { to: '/admin/customers', label: 'Customers', icon: IconCustomers },
  { to: '/admin/inventory', label: 'Inventory', icon: IconInventory },
  { to: '/admin/promotions', label: 'Coupons', icon: IconCoupons },
  { to: '/admin/reviews', label: 'Reviews', icon: IconReviews },
  { to: '/admin/reports', label: 'Reports', icon: IconReports },
  { to: '/admin/settings', label: 'Settings', icon: IconSettings },
]

const secondaryNav = [
  { to: '/admin/media', label: 'Media', icon: IconMedia },
  { to: '/admin/users', label: 'Users & roles', icon: IconUsers },
]

function useDrawerDefault() {
  return typeof window !== 'undefined' && window.innerWidth >= 768
}

export function AdminLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(useDrawerDefault)

  const { data: profile } = useQuery({
    queryKey: ['admin-profile'],
    queryFn: () =>
      getData<{ first_name?: string; last_name?: string; email?: string; roles?: string[] }>('/admin/auth/me'),
  })

  const displayName = profile
    ? `${profile.first_name ?? 'Admin'} ${profile.last_name ?? 'User'}`.trim()
    : 'Admin User'
  const roleLabel = profile?.roles?.includes('SUPER_ADMIN') ? 'Super Admin' : 'Admin'

  useEffect(() => {
    if (window.innerWidth < 768) setDrawerOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!drawerOpen) return
    const isMobile = window.innerWidth < 768
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    if (isMobile) document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = ''
    }
  }, [drawerOpen])

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const onChange = () => {
      if (mq.matches) {
        setDrawerOpen(true)
        document.body.style.overflow = ''
      } else {
        setDrawerOpen(false)
      }
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  function closeDrawer() {
    setDrawerOpen(false)
  }

  function toggleDrawer() {
    setDrawerOpen((open) => !open)
  }

  function signOut() {
    storage.clearToken()
    navigate('/admin/login')
  }

  const navLinkClass = (isActive: boolean, secondary = false) =>
    `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
      isActive
        ? secondary
          ? 'bg-[#fff0f5] text-[#E91E63]'
          : 'bg-[#e91e63] text-white shadow-sm'
        : 'text-[#64748b] hover:bg-[#f8fafc] hover:text-[#0f172a]'
    }`

  return (
    <div className="admin-shell flex min-h-screen bg-[#f4f6fb]">
      {/* Backdrop — mobile only */}
      <button
        type="button"
        aria-label="Close menu"
        className={`fixed inset-0 z-40 bg-[#0f172a]/40 transition-opacity md:hidden ${
          drawerOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={closeDrawer}
      />

      {/* Drawer sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-[#e8ebf3] bg-white shadow-2xl transition-all duration-300 ease-out md:relative md:z-auto md:shrink-0 md:shadow-none ${
          drawerOpen
            ? 'w-72 max-w-[85vw] translate-x-0 md:w-64 md:max-w-none'
            : 'w-72 -translate-x-full md:w-0 md:translate-x-0 md:overflow-hidden md:border-r-0'
        }`}
        aria-hidden={!drawerOpen}
      >
        <div className="flex items-center justify-between border-b border-[#eef1f6] px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#E91E63] text-sm font-bold text-white">
              MH
            </div>
            <div>
              <p className="text-lg font-bold text-[#0f172a]">MamaHub</p>
              <p className="text-xs text-[#94a3b8]">Admin Panel</p>
            </div>
          </div>
          <button
            type="button"
            onClick={closeDrawer}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[#64748b] hover:bg-[#f8fafc] md:hidden"
            aria-label="Close sidebar"
          >
            <IconClose size={20} />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-4">
          {nav.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={closeDrawer}
                className={({ isActive }) => navLinkClass(isActive)}
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            )
          })}

          <div className="my-3 border-t border-[#eef1f6]" />
          {secondaryNav.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={closeDrawer}
                className={({ isActive }) => navLinkClass(isActive, true)}
              >
                <Icon size={18} />
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        <div className="border-t border-[#eef1f6] p-4">
          <div className="flex items-center gap-3 rounded-xl bg-[#f8fafc] p-3">
            <AdminAvatar name={displayName} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-[#0f172a]">{displayName}</p>
              <p className="truncate text-xs text-[#94a3b8]">{roleLabel}</p>
            </div>
          </div>
          <Link
            to="/"
            onClick={closeDrawer}
            className="mt-3 block px-2 text-sm text-[#64748b] hover:text-[#E91E63]"
          >
            ← Back to store
          </Link>
          <button
            type="button"
            className="mt-2 w-full rounded-xl px-2 py-2 text-left text-sm text-[#64748b] hover:bg-[#f8fafc] hover:text-[#0f172a]"
            onClick={signOut}
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-[#e8ebf3] bg-white px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={toggleDrawer}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#e8ebf3] bg-white text-[#334155] hover:bg-[#f8fafc]"
              aria-label={drawerOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={drawerOpen}
            >
              <IconMenu size={20} />
            </button>
            <div className="hidden sm:block">
              <p className="text-sm font-semibold text-[#0f172a]">MamaHub Admin</p>
              <p className="text-xs text-[#94a3b8]">{roleLabel}</p>
            </div>
          </div>
          <button type="button" className="text-sm font-medium text-[#64748b] hover:text-[#E91E63]" onClick={signOut}>
            Sign out
          </button>
        </header>

        <main className="flex-1 overflow-auto p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
