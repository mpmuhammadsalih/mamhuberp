import { useState, type FormEvent } from 'react'
import { IconHeadset, IconMapPin, IconTruck } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import { getApiErrorMessage, postData } from '../../lib/api'
import type { CmsPage } from '../../types/api'

const CARD_ICONS = [IconHeadset, IconMapPin, IconTruck]

interface Props {
  page: CmsPage
}

export function CmsContactPage({ page }: Props) {
  const { t } = useLocale()
  const meta = page.meta ?? {}
  const cards = meta.cards ?? t.cms.contact.cards
  const subjects = meta.form_subjects?.length ? meta.form_subjects : t.cms.contact.subjects
  const formEnabled = meta.form_enabled !== false
  const successMessage = meta.success_message || t.cms.contact.successMessage

  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    const form = new FormData(event.currentTarget)
    try {
      await postData('/cms/contact', {
        name: String(form.get('name') || ''),
        email: String(form.get('email') || ''),
        subject: String(form.get('subject') || 'General inquiry'),
        message: String(form.get('message') || ''),
      })
      setSubmitted(true)
    } catch (err) {
      setError(getApiErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto grid max-w-5xl gap-10 lg:grid-cols-[1fr_1.1fr]">
      <div className="space-y-4">
        {cards.map((card, index: number) => {
          const Icon = CARD_ICONS[index % CARD_ICONS.length]
          return (
            <div
              key={card.title}
              className="flex gap-4 rounded-2xl border border-brand-border bg-white p-5 shadow-sm"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-tint text-brand-tan">
                <Icon size={22} />
              </div>
              <div>
                <h2 className="font-bold text-brand-ink">{card.title}</h2>
                {card.lines.map((line) => (
                  <p key={line} className="mt-1 text-sm text-brand-sage">
                    {line.includes('@') ? (
                      <a href={`mailto:${line}`} className="text-brand-tan hover:text-brand-tan-dark">
                        {line}
                      </a>
                    ) : (
                      line
                    )}
                  </p>
                ))}
              </div>
            </div>
          )
        })}
        {page.content_html ? (
          <article className="cms-content" dangerouslySetInnerHTML={{ __html: page.content_html }} />
        ) : null}
      </div>

      {formEnabled ? (
        <div className="rounded-2xl border border-brand-border bg-white p-6 shadow-sm sm:p-8">
          <h2 className="text-lg font-bold text-brand-ink">{t.cms.contact.sendMessage}</h2>
          <p className="mt-1 text-sm text-brand-sage">{t.cms.contact.formHint}</p>

          {submitted ? (
            <div className="mt-6 rounded-xl bg-brand-tint px-4 py-5 text-sm text-brand-cocoa">{successMessage}</div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              {error ? <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
              <div>
                <label htmlFor="contact-name" className="mb-1 block text-sm font-semibold text-brand-cocoa">
                  {t.cms.contact.fullName}
                </label>
                <input
                  id="contact-name"
                  name="name"
                  required
                  className="w-full rounded-xl border border-brand-border px-4 py-2.5 text-sm outline-none focus:border-brand-tan focus:ring-2 focus:ring-brand-tint"
                />
              </div>
              <div>
                <label htmlFor="contact-email" className="mb-1 block text-sm font-semibold text-brand-cocoa">
                  {t.cms.contact.email}
                </label>
                <input
                  id="contact-email"
                  name="email"
                  type="email"
                  required
                  className="w-full rounded-xl border border-brand-border px-4 py-2.5 text-sm outline-none focus:border-brand-tan focus:ring-2 focus:ring-brand-tint"
                />
              </div>
              <div>
                <label htmlFor="contact-subject" className="mb-1 block text-sm font-semibold text-brand-cocoa">
                  {t.cms.contact.subject}
                </label>
                <select
                  id="contact-subject"
                  name="subject"
                  className="w-full rounded-xl border border-brand-border px-4 py-2.5 text-sm outline-none focus:border-brand-tan focus:ring-2 focus:ring-brand-tint"
                >
                  {subjects.map((subject) => (
                    <option key={subject}>{subject}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="contact-message" className="mb-1 block text-sm font-semibold text-brand-cocoa">
                  {t.cms.contact.message}
                </label>
                <textarea
                  id="contact-message"
                  name="message"
                  required
                  rows={5}
                  className="w-full resize-y rounded-xl border border-brand-border px-4 py-2.5 text-sm outline-none focus:border-brand-tan focus:ring-2 focus:ring-brand-tint"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-xl bg-brand-tan px-4 py-3 text-sm font-bold text-white transition hover:bg-brand-tan-dark disabled:opacity-60"
              >
                {submitting ? t.cms.contact.sending : t.cms.contact.send}
              </button>
            </form>
          )}
        </div>
      ) : null}
    </div>
  )
}
