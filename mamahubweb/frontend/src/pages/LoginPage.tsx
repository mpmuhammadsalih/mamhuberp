import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { HOME_CONTAINER } from '../components/layout/homeLayout'
import { SeoHead } from '../components/seo/SeoHead'
import { getApiErrorMessage, postData } from '../lib/api'
import { fetchCart, getCartItemCount } from '../lib/queries/cart'
import { useLocale } from '../i18n/LocaleContext'
import { storage } from '../lib/storage'

const inputClass =
  'font-catalog w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-brand-tan focus:ring-2 focus:ring-brand-tint'

function isValidQatarMobile(value: string): boolean {
  const cleaned = value.trim().replace(/[\s-]/g, '')
  if (/^\+?974\d{8}$/.test(cleaned)) return true
  if (/^00?974\d{8}$/.test(cleaned)) return true
  return /^\d{8}$/.test(cleaned)
}

async function resolvePostLoginPath(redirectTo: string): Promise<string> {
  if (redirectTo !== '/checkout') return redirectTo
  try {
    const cart = await fetchCart()
    const count = getCartItemCount(cart)
    if (count > 0) return '/checkout'
  } catch {
    // Fall through to home when cart cannot be loaded.
  }
  return '/'
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { locale, t } = useLocale()
  const [searchParams] = useSearchParams()
  const redirectTo = searchParams.get('redirect') || '/'
  const resetSuccess = (location.state as { resetSuccess?: boolean } | null)?.resetSuccess
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [mobile, setMobile] = useState('')
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [formError, setFormError] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: async () => {
      setFormError(null)

      if (mode === 'register') {
        if (password !== confirmPassword) {
          throw new Error(t.auth.errPasswordMismatch)
        }
        if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
          throw new Error(t.auth.errPasswordRules)
        }
        if (!isValidQatarMobile(mobile)) {
          throw new Error(t.auth.errMobile)
        }

        await postData('/customer/auth/register', {
          email: email.trim(),
          password,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          mobile: mobile.trim(),
          preferred_language: locale,
        })
      }

      const guest = storage.getGuestCartToken()
      const data = await postData<{ tokens: { access_token: string; refresh_token: string } }>(
        '/customer/auth/login',
        {
          email: email.trim(),
          password,
          guest_cart_token: guest,
        },
      )
      storage.setTokens(data.tokens.access_token, data.tokens.refresh_token)
    },
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['wishlist'] })
      navigate(await resolvePostLoginPath(redirectTo))
    },
    onError: (error) => setFormError(getApiErrorMessage(error)),
  })

  function switchMode(next: 'login' | 'register') {
    setMode(next)
    setFormError(null)
    setConfirmPassword('')
  }

  return (
    <div className={`${HOME_CONTAINER} max-w-md py-10 md:py-16`}>
      <SeoHead title={mode === 'login' ? t.auth.signIn : t.auth.createAccount} noIndex />
      <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border sm:p-8">
        <h1 className="font-display text-2xl font-bold text-[#1A1C2E]">
          {mode === 'login' ? t.auth.signIn : t.auth.createAccount}
        </h1>
        <p className="mt-1 font-catalog text-sm text-slate-500">
          {mode === 'login' ? t.auth.welcomeBack : t.auth.joinSubtitle}
        </p>

        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit.mutate()
          }}
        >
          {mode === 'register' && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="first-name" className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600">
                  {t.auth.firstName}
                </label>
                <input
                  id="first-name"
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder={t.auth.firstName}
                  autoComplete="given-name"
                  className={inputClass}
                />
              </div>
              <div>
                <label htmlFor="last-name" className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600">
                  {t.auth.lastName}
                </label>
                <input
                  id="last-name"
                  type="text"
                  required
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder={t.auth.lastName}
                  autoComplete="family-name"
                  className={inputClass}
                />
              </div>
            </div>
          )}

          <div>
            <label htmlFor="email" className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600">
              {t.auth.email}
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.auth.emailPlaceholder}
              autoComplete="email"
              className={inputClass}
            />
          </div>

          {mode === 'register' && (
            <div>
              <label htmlFor="mobile" className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600">
                {t.auth.mobile}
              </label>
              <input
                id="mobile"
                type="tel"
                required
                value={mobile}
                onChange={(e) => setMobile(e.target.value)}
                placeholder={t.auth.mobilePlaceholder}
                autoComplete="tel"
                className={inputClass}
              />
              <p className="mt-1.5 font-catalog text-xs text-slate-400">{t.auth.mobileHint}</p>
            </div>
          )}

          <div>
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <label htmlFor="password" className="block font-catalog text-xs font-semibold text-slate-600">
                {t.auth.password}
              </label>
              {mode === 'login' && (
                <Link
                  to="/forgot-password"
                  className="font-catalog text-xs font-semibold text-brand-accent hover:underline"
                >
                  {t.auth.forgotPassword}
                </Link>
              )}
            </div>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'register' ? t.auth.passwordMinPlaceholder : t.auth.password}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              className={inputClass}
            />
            {mode === 'register' && (
              <p className="mt-1.5 font-catalog text-xs text-slate-400">{t.auth.passwordRulesHint}</p>
            )}
          </div>

          {mode === 'register' && (
            <div>
              <label
                htmlFor="confirm-password"
                className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600"
              >
                {t.auth.confirmPassword}
              </label>
              <input
                id="confirm-password"
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t.auth.confirmPasswordPlaceholder}
                autoComplete="new-password"
                className={inputClass}
              />
            </div>
          )}

          {resetSuccess && mode === 'login' && (
            <p className="rounded-xl bg-emerald-50 px-4 py-3 font-catalog text-sm text-emerald-800 ring-1 ring-emerald-100">
              {t.auth.passwordUpdated}
            </p>
          )}

          {formError && (
            <p className="rounded-xl bg-red-50 px-4 py-3 font-catalog text-sm text-red-600 ring-1 ring-red-100">
              {formError}
            </p>
          )}

          <button
            type="submit"
            disabled={submit.isPending}
            className="w-full rounded-full bg-brand-accent py-3 font-catalog text-sm font-bold text-white transition hover:bg-brand-accent-hover disabled:opacity-60"
          >
            {submit.isPending
              ? t.shared.pleaseWait
              : mode === 'login'
                ? t.auth.signIn
                : t.auth.register}
          </button>
        </form>

        <button
          type="button"
          className="mt-4 w-full font-catalog text-sm font-semibold text-brand-accent hover:underline"
          onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login' ? t.auth.needAccount : t.auth.haveAccount}
        </button>
      </div>
    </div>
  )
}
