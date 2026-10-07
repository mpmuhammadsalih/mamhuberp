import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { HOME_CONTAINER } from '../components/layout/homeLayout'
import { getApiErrorMessage, postData } from '../lib/api'
import { useLocale } from '../i18n/LocaleContext'

const inputClass =
  'font-catalog w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-brand-tan focus:ring-2 focus:ring-brand-tint'

export function ResetPasswordPage() {
  const { t } = useLocale()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: async () => {
      setFormError(null)
      if (!token) {
        throw new Error(t.auth.errResetInvalid)
      }
      if (password !== confirmPassword) {
        throw new Error(t.auth.errPasswordMismatch)
      }
      if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        throw new Error(t.auth.errPasswordRules)
      }
      await postData('/customer/auth/reset-password', { token, password })
    },
    onSuccess: () => navigate('/login', { replace: true, state: { resetSuccess: true } }),
    onError: (error) => setFormError(getApiErrorMessage(error)),
  })

  if (!token) {
    return (
      <div className={`${HOME_CONTAINER} max-w-md py-10 md:py-16`}>
        <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border sm:p-8">
          <h1 className="font-display text-2xl font-bold text-[#1A1C2E]">{t.auth.invalidResetLink}</h1>
          <p className="mt-2 font-catalog text-sm text-slate-500">{t.auth.invalidResetLinkDesc}</p>
          <Link
            to="/forgot-password"
            className="mt-6 inline-block font-catalog text-sm font-semibold text-brand-accent hover:underline"
          >
            {t.auth.requestNewLink}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className={`${HOME_CONTAINER} max-w-md py-10 md:py-16`}>
      <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border sm:p-8">
        <h1 className="font-display text-2xl font-bold text-[#1A1C2E]">{t.auth.chooseNewPassword}</h1>
        <p className="mt-1 font-catalog text-sm text-slate-500">{t.auth.newPasswordSubtitle}</p>

        <form
          className="mt-6 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit.mutate()
          }}
        >
          <div>
            <label htmlFor="password" className="mb-1.5 block font-catalog text-xs font-semibold text-slate-600">
              {t.auth.newPassword}
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t.auth.passwordMinPlaceholder}
              autoComplete="new-password"
              className={inputClass}
            />
            <p className="mt-1.5 font-catalog text-xs text-slate-400">{t.auth.passwordRulesHint}</p>
          </div>

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
            {submit.isPending ? t.shared.saving : t.auth.updatePassword}
          </button>

          <Link
            to="/login"
            className="block text-center font-catalog text-sm font-semibold text-brand-accent hover:underline"
          >
            {t.shared.backToSignIn}
          </Link>
        </form>
      </div>
    </div>
  )
}
