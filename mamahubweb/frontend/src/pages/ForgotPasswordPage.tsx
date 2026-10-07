import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { HOME_CONTAINER } from '../components/layout/homeLayout'
import { getApiErrorMessage, postData } from '../lib/api'
import { useLocale } from '../i18n/LocaleContext'

const inputClass =
  'font-catalog w-full rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-800 outline-none transition placeholder:text-gray-400 focus:border-brand-tan focus:ring-2 focus:ring-brand-tint'

export function ForgotPasswordPage() {
  const { t } = useLocale()
  const [email, setEmail] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [sentMessage, setSentMessage] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: async () => {
      setFormError(null)
      setSentMessage(null)
      const result = await postData<{ sent: boolean }>('/customer/auth/forgot-password', {
        email: email.trim(),
      })
      return result
    },
    onSuccess: () => {
      setSentMessage(t.auth.resetSent)
    },
    onError: (error) => setFormError(getApiErrorMessage(error)),
  })

  return (
    <div className={`${HOME_CONTAINER} max-w-md py-10 md:py-16`}>
      <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-brand-border sm:p-8">
        <h1 className="font-display text-2xl font-bold text-[#1A1C2E]">{t.auth.forgotTitle}</h1>
        <p className="mt-1 font-catalog text-sm text-slate-500">{t.auth.forgotInstructions}</p>

        {sentMessage ? (
          <div className="mt-6 space-y-4">
            <p className="rounded-xl bg-emerald-50 px-4 py-3 font-catalog text-sm text-emerald-800 ring-1 ring-emerald-100">
              {sentMessage}
            </p>
            <Link
              to="/login"
              className="inline-block font-catalog text-sm font-semibold text-brand-accent hover:underline"
            >
              {t.shared.backToSignIn}
            </Link>
          </div>
        ) : (
          <form
            className="mt-6 space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              submit.mutate()
            }}
          >
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
              {submit.isPending ? t.shared.sending : t.auth.sendResetLink}
            </button>

            <Link
              to="/login"
              className="block text-center font-catalog text-sm font-semibold text-brand-accent hover:underline"
            >
              {t.shared.backToSignIn}
            </Link>
          </form>
        )}
      </div>
    </div>
  )
}
