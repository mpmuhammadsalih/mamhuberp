import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AdminCard, AdminButton, AdminField, AdminInput, AdminPageTitle } from '../../components/admin/ui'

const SETTINGS_SECTIONS = [
  { id: 'general', label: 'General' },
  { id: 'store', label: 'Store Settings' },
  { id: 'payment', label: 'Payment Methods' },
  { id: 'shipping', label: 'Shipping Settings' },
  { id: 'media', label: 'Content & Media', href: '/admin/media' },
  { id: 'users', label: 'Users & Roles', href: '/admin/users' },
] as const

const STORAGE_KEY = 'mamahub_admin_settings'

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as Record<string, string>
  } catch {
    /* ignore */
  }
  return {
    storeName: 'MamaHub',
    storeEmail: 'hello@mamahub.store',
    storePhone: '+974 0000 0000',
    storeAddress: 'Doha, Qatar',
    currency: 'QAR',
    timezone: 'Asia/Qatar',
  }
}

export function AdminSettingsPage() {
  const [active, setActive] = useState('general')
  const [form, setForm] = useState(loadSettings)
  const [saved, setSaved] = useState(false)

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(form))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div>
      <AdminPageTitle title="Settings" description="Configure your store preferences and admin options." />

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <AdminCard padding="p-3">
          <nav className="space-y-1">
            {SETTINGS_SECTIONS.map((section) =>
              'href' in section && section.href ? (
                <Link
                  key={section.id}
                  to={section.href}
                  className="block rounded-xl px-3 py-2.5 text-sm font-medium text-[#64748b] hover:bg-[#f8fafc] hover:text-[#0f172a]"
                >
                  {section.label}
                </Link>
              ) : (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActive(section.id)}
                  className={`w-full rounded-xl px-3 py-2.5 text-left text-sm font-medium transition ${
                    active === section.id
                      ? 'bg-[#fff0f5] text-[#E91E63]'
                      : 'text-[#64748b] hover:bg-[#f8fafc]'
                  }`}
                >
                  {section.label}
                </button>
              ),
            )}
          </nav>
        </AdminCard>

        <AdminCard>
          <h2 className="mb-5 text-lg font-semibold text-[#0f172a]">General Settings</h2>
          <div className="grid gap-5 md:grid-cols-2">
            <AdminField label="Store Name">
              <AdminInput value={form.storeName} onChange={(e) => setForm({ ...form, storeName: e.target.value })} />
            </AdminField>
            <AdminField label="Store Email">
              <AdminInput value={form.storeEmail} onChange={(e) => setForm({ ...form, storeEmail: e.target.value })} />
            </AdminField>
            <AdminField label="Store Phone">
              <AdminInput value={form.storePhone} onChange={(e) => setForm({ ...form, storePhone: e.target.value })} />
            </AdminField>
            <AdminField label="Currency">
              <AdminInput value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
            </AdminField>
            <AdminField label="Store Address" className="md:col-span-2">
              <AdminInput value={form.storeAddress} onChange={(e) => setForm({ ...form, storeAddress: e.target.value })} />
            </AdminField>
            <AdminField label="Timezone" className="md:col-span-2">
              <AdminInput value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
            </AdminField>
          </div>
          <div className="mt-6 flex items-center justify-end gap-3">
            {saved && <span className="text-sm text-green-600">Settings saved</span>}
            <AdminButton onClick={save}>Save Changes</AdminButton>
          </div>
        </AdminCard>
      </div>
    </div>
  )
}
