type IconProps = { className?: string }

export function IconCashOnDelivery({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2" y="6" width="20" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6 9h.01M18 15h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function IconVisa({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 48 32" aria-hidden="true">
      <rect width="48" height="32" rx="4" fill="#1A1F71" />
      <path
        fill="#fff"
        d="M19.5 20.5h-2.8l1.7-10.5h2.8L19.5 20.5zm11.2-10.2c-.6-.2-1.4-.5-2.5-.5-2.7 0-4.6 1.4-4.6 3.5 0 1.5 1.4 2.4 2.5 2.9 1.1.5 1.5.9 1.5 1.4 0 .8-.9 1.1-1.7 1.1-1.1 0-1.7-.2-2.6-.6l-.4-.2-.4 2.4c.7.3 1.9.6 3.2.6 2.9 0 4.8-1.4 4.8-3.6 0-1.2-.7-2.1-2.3-2.9-1-.5-1.6-.8-1.6-1.3 0-.4.5-.9 1.5-.9.9 0 1.5.2 2 .4l.3.1.4-2.3zm7.2 6.7h2.4l-1.2-10.5h-2.3c-.7 0-1.3.4-1.5 1l-4.3 9.5h2.9l.6-1.6h3.5l.3 1.6zm-3-3.7l1.4-3.9.8 3.9h-2.2zM16.2 10l-2.7 10.5h-2.7L9.3 12c-.2-.7-.4-.9-1-1.2-.9-.5-2.4-1-2.4-1l.1-.3h4.2c.5 0 1 .4 1.1.9l1.5 7.1 3.7-8h2.7z"
      />
    </svg>
  )
}

export function IconMastercard({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 48 32" aria-hidden="true">
      <rect width="48" height="32" rx="4" fill="#fff" />
      <circle cx="19" cy="16" r="8" fill="#EB001B" />
      <circle cx="29" cy="16" r="8" fill="#F79E1B" />
      <path
        fill="#FF5F00"
        d="M24 10.2a8 8 0 000 11.6 8 8 0 000-11.6z"
      />
    </svg>
  )
}

export function IconGooglePay({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 48 32" aria-hidden="true">
      <rect width="48" height="32" rx="4" fill="#fff" />
      <path
        fill="#4285F4"
        d="M24.5 16.3V19h6.8c-.3 1.6-1.2 3-2.5 3.9-1.5 1.1-3.5 1.7-5.8 1.7-5 0-9-4-9-9s4-9 9-9c2.7 0 5 1 6.8 2.6l-3.6 3.6c-1-.9-2.3-1.5-3.8-1.5-3.2 0-5.8 2.6-5.8 5.8s2.6 5.8 5.8 5.8c1.5 0 2.8-.6 3.7-1.5l-.1 1.5h3.5v-8.9h-9.2z"
      />
    </svg>
  )
}

export function IconApplePay({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 48 32" aria-hidden="true">
      <rect width="48" height="32" rx="4" fill="#000" />
      <path
        fill="#fff"
        d="M13.8 10.6c-.6.8-1.6 1.4-2.6 1.3-.1-1.1.4-2.2 1-2.9.6-.8 1.7-1.3 2.6-1.4.1 1.2-.3 2.2-1 2.9zm1 1.5c-1.4-.1-2.5.8-3.2.8-.7 0-1.7-.8-2.8-.8-1.4 0-2.8.9-3.5 2.2-1.5 2.6-.4 6.5 1.1 8.6.7 1.1 1.6 2.3 2.8 2.3 1.1 0 1.5-.7 2.8-.7 1.3 0 1.6.7 2.8.7 1.2 0 2-1.1 2.7-2.2.9-1.3 1.2-2.6 1.2-2.7-.1 0-2.4-1-2.4-3.5 0-2.2 1.8-3.2 1.9-3.3-1.1-.8-2.6-1.3-4.2-1.3z"
      />
      <path
        fill="#fff"
        d="M27.8 10.8c-2.8 0-4.7 1.5-4.7 3.7 0 2.4 2.2 3.1 3.9 3.7 1.7.6 2.2 1 2.2 1.6 0 .9-1.3 1.3-2.5 1.3-1.4 0-2.2-.2-3.4-.7l-.5-.2-.5 2.7c.9.4 2.1.7 3.5.7 3.1 0 5.2-1.5 5.2-3.9 0-1.9-1.1-3-3.8-3.8-1.6-.5-2.6-.8-2.6-1.4 0-.5.6-.9 1.5-.9.9 0 1.6.2 2.2.5l.3.1.4-2.4zm4.2 0h-2.1v11h2.1v-4.5h2.9c2.7 0 4.6-1.4 4.6-3.3 0-1.8-1.8-3.2-4.5-3.2h-3zm0 1.8h2.5c1.8 0 2.8 1 2.8 2.4 0 1.4-1 2.4-2.8 2.4h-2.5v-4.8z"
      />
    </svg>
  )
}

const badgeClass = 'h-7 w-10 shrink-0 overflow-hidden rounded border border-gray-200 shadow-sm'

export function OnlinePaymentBadges() {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" aria-label="Accepted payment methods">
      <IconVisa className={badgeClass} />
      <IconMastercard className={badgeClass} />
      <IconGooglePay className={badgeClass} />
      <IconApplePay className={badgeClass} />
    </div>
  )
}
