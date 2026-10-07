import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { useLocale } from '../i18n/LocaleContext'
import { getApiErrorMessage, getData, patchData } from '../lib/api'
import { storage } from '../lib/storage'
import type { NotificationItem, UserProfile } from '../types/api'

const inputClass =
  'font-catalog w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-brand-tan focus:ring-2 focus:ring-brand-tint'

function isValidQatarMobile(value: string): boolean {
  const cleaned = value.trim().replace(/[\s-]/g, '')
  if (/^\+?974\d{8}$/.test(cleaned)) return true
  if (/^00?974\d{8}$/.test(cleaned)) return true
  return /^\d{8}$/.test(cleaned)
}

export function ProfilePage() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const { openInbox } = useInboxWidget()
  const queryClient = useQueryClient()
  const loggedIn = storage.hasSession()
  const [mobile, setMobile] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => getData<UserProfile>('/customer/auth/me'),
    enabled: loggedIn,
  })

  useEffect(() => {
    setMobile(profile?.mobile ?? '')
  }, [profile?.mobile])

  const updateMobile = useMutation({
    mutationFn: async () => {
      setFormError(null)
      setSaved(false)
      if (!isValidQatarMobile(mobile)) {
        throw new Error(t.auth.errMobile)
      }
      return patchData<UserProfile>('/customer/auth/me', { mobile: mobile.trim() })
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(['profile'], updated)
      setSaved(true)
    },
    onError: (error) => setFormError(getApiErrorMessage(error)),
  })

  const { data: unread } = useQuery({
    queryKey: ['notifications-unread'],
    queryFn: () => getData<{ count: number }>('/notifications/unread-count'),
    enabled: loggedIn,
  })

  const { data: notifications = [] } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getData<NotificationItem[]>('/notifications'),
    enabled: loggedIn,
  })

  function signOut() {
    storage.clearSession()
    queryClient.removeQueries({ queryKey: ['profile'] })
    queryClient.removeQueries({ queryKey: ['wishlist'] })
    queryClient.removeQueries({ queryKey: ['notifications'] })
    queryClient.removeQueries({ queryKey: ['notifications-unread'] })
    queryClient.removeQueries({ queryKey: ['inbox-unread'] })
    queryClient.removeQueries({ queryKey: ['inbox-conversations'] })
    queryClient.removeQueries({ queryKey: ['inbox-messages'] })
    queryClient.invalidateQueries({ queryKey: ['cart'] })
    navigate('/')
  }

  if (!loggedIn) {
    return (
      <div className={`${PAGE_CONTAINER} py-12 text-center`}>
        <p className="text-gray-600">{t.account.signInProfile}</p>
        <Link to="/login" className="mt-4 inline-block text-brand-accent hover:underline">
          {t.auth.signIn}
        </Link>
      </div>
    )
  }

  return (
    <div className={`${PAGE_CONTAINER} py-8`}>
      <h1 className="mb-6 text-3xl font-bold">{t.account.myAccount}</h1>
      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-2xl bg-white p-6 shadow-sm">
          <h2 className="font-semibold">{t.account.profile}</h2>
          {profile && (
            <>
              <dl className="mt-4 space-y-2 text-sm">
                <div>
                  <dt className="text-gray-500">{t.account.name}</dt>
                  <dd>
                    {profile.first_name} {profile.last_name}
                  </dd>
                </div>
                <div>
                  <dt className="text-gray-500">{t.auth.email}</dt>
                  <dd>{profile.email}</dd>
                </div>
              </dl>
              <form
                className="mt-4 space-y-3"
                onSubmit={(e) => {
                  e.preventDefault()
                  updateMobile.mutate()
                }}
              >
                <div>
                  <label
                    htmlFor="profile-mobile"
                    className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600"
                  >
                    {t.auth.mobile}
                  </label>
                  <input
                    id="profile-mobile"
                    type="tel"
                    required
                    value={mobile}
                    onChange={(e) => {
                      setMobile(e.target.value)
                      setSaved(false)
                    }}
                    placeholder="+974 5555 1234"
                    autoComplete="tel"
                    className={inputClass}
                  />
                  <p className="mt-1.5 font-catalog text-xs text-slate-400">{t.auth.mobileHint}</p>
                </div>
                {formError && (
                  <p className="rounded-xl bg-red-50 px-4 py-3 font-catalog text-sm text-red-600 ring-1 ring-red-100">
                    {formError}
                  </p>
                )}
                {saved && (
                  <p className="rounded-xl bg-emerald-50 px-4 py-3 font-catalog text-sm text-emerald-800 ring-1 ring-emerald-100">
                    {t.account.mobileSaved}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={updateMobile.isPending}
                  className="rounded-full bg-brand-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-accent-hover disabled:opacity-60"
                >
                  {updateMobile.isPending ? t.shared.saving : t.account.saveMobile}
                </button>
              </form>
            </>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link to="/addresses" className="text-sm text-brand-accent hover:underline">
              {t.account.manageAddresses}
            </Link>
            <Link to="/loyalty" className="text-sm text-brand-accent hover:underline">
              {t.account.loyaltyRewards}
            </Link>
            <Link to="/wishlist" className="text-sm text-brand-accent hover:underline">
              {t.account.wishlist}
            </Link>
            <Link to="/orders" className="text-sm text-brand-accent hover:underline">
              {t.account.orders}
            </Link>
            <button
              type="button"
              onClick={() => openInbox({ tab: 'chat' })}
              className="text-sm text-brand-accent hover:underline"
            >
              {t.account.messages}
            </button>
          </div>
          <div className="mt-6 border-t border-gray-100 pt-4">
            <button
              type="button"
              onClick={signOut}
              className="rounded-full border border-brand-border px-5 py-2.5 text-sm font-semibold text-brand-cocoa transition hover:border-brand-accent hover:text-brand-accent"
            >
              {t.account.signOut}
            </button>
          </div>
        </section>
        <section className="rounded-2xl bg-white p-6 shadow-sm">
          <h2 className="font-semibold">
            <button
              type="button"
              onClick={() => openInbox({ tab: 'alerts' })}
              className="hover:text-brand-accent"
            >
              {t.account.notifications}
            </button>
            {unread?.count ? ` (${unread.count} ${t.account.unread})` : ''}
          </h2>
          <ul className="mt-4 max-h-64 space-y-3 overflow-y-auto text-sm">
            {notifications.slice(0, 10).map((n) => (
              <li key={n.notification_id} className={n.is_read ? 'text-gray-500' : ''}>
                <p className="font-medium">{n.title}</p>
                {n.body && <p className="text-gray-500">{n.body}</p>}
              </li>
            ))}
            {!notifications.length && (
              <li className="text-gray-500">{t.account.noNotifications}</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}
