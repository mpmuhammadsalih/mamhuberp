import { useState } from 'react'
import { Link } from 'react-router-dom'
import { IconChevronDown } from '../icons/Icons'
import { useLocale } from '../../i18n/LocaleContext'
import type { CmsFaqItem, CmsFaqSection } from '../../types/api'

interface Props {
  sections?: CmsFaqSection[]
}

function FaqItem({ question, answer }: CmsFaqItem) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-brand-border/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-4 py-4 text-left"
        aria-expanded={open}
      >
        <span className="font-semibold text-brand-ink">{question}</span>
        <IconChevronDown
          className={`shrink-0 text-brand-sage transition-transform ${open ? 'rotate-180' : ''}`}
          size={18}
        />
      </button>
      {open ? <p className="pb-4 text-sm leading-relaxed text-brand-sage">{answer}</p> : null}
    </div>
  )
}

export function CmsFaqSections({ sections }: Props) {
  const { t } = useLocale()

  if (!sections?.length) {
    return <p className="text-sm text-brand-sage">{t.cms.faq.empty}</p>
  }

  return (
    <div className="space-y-8">
      {sections.map((section) => (
        <section key={section.title}>
          <h2 className="mb-3 text-lg font-bold text-brand-tan-dark">{section.title}</h2>
          <div className="rounded-2xl border border-brand-border bg-white px-5 shadow-sm">
            {section.items.map((item) => (
              <FaqItem key={item.question} question={item.question} answer={item.answer} />
            ))}
          </div>
        </section>
      ))}
      <p className="text-center text-sm text-brand-sage">
        {t.cms.faq.stillHaveQuestions}{' '}
        <Link to="/page/contact" className="font-semibold text-brand-tan hover:text-brand-tan-dark">
          {t.cms.faq.contactTeam}
        </Link>
        .
      </p>
    </div>
  )
}
