/** Decorative teddy + toys for the desktop header, matching the toy-shop reference. */
export function HeaderMascot({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 168 112"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <ellipse cx="118" cy="104" rx="36" ry="6" fill="#F8D7E4" />
      <g>
        <circle cx="96" cy="38" r="11" fill="#C4A484" />
        <circle cx="140" cy="38" r="11" fill="#C4A484" />
        <circle cx="96" cy="38" r="6.5" fill="#E8D5C4" />
        <circle cx="140" cy="38" r="6.5" fill="#E8D5C4" />
        <ellipse cx="118" cy="62" rx="28" ry="26" fill="#C4A484" />
        <ellipse cx="118" cy="70" rx="18" ry="14" fill="#E8D5C4" />
        <circle cx="108" cy="56" r="3.2" fill="#4E342E" />
        <circle cx="128" cy="56" r="3.2" fill="#4E342E" />
        <ellipse cx="118" cy="64" rx="5" ry="3.6" fill="#6D4C41" />
        <path d="M118 67.2c-3 3.4-7.2 3.6-9.2 2.2" stroke="#6D4C41" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M118 67.2c3 3.4 7.2 3.6 9.2 2.2" stroke="#6D4C41" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M104 46c6-10 22-10 28 0" stroke="#E91E63" strokeWidth="5" strokeLinecap="round" />
        <circle cx="118" cy="41" r="4.2" fill="#E91E63" />
      </g>
      <g>
        <ellipse cx="38" cy="86" rx="22" ry="8" fill="#7C4DFF" />
        <ellipse cx="38" cy="80" rx="18" ry="7" fill="#FFCA28" />
        <ellipse cx="38" cy="74" rx="14" ry="6" fill="#26C6DA" />
        <ellipse cx="38" cy="68" rx="10" ry="5" fill="#EF5350" />
        <rect x="35.2" y="46" width="5.6" height="22" rx="2.8" fill="#90A4AE" />
        <circle cx="38" cy="46" r="5.5" fill="#42A5F5" />
        <circle cx="38" cy="46" r="2.4" fill="#BBDEFB" />
      </g>
      <rect x="58" y="86" width="16" height="16" rx="3" fill="#29B6F6" />
      <rect x="62" y="90" width="8" height="8" rx="1.5" fill="#E3F2FD" />
      <rect x="148" y="78" width="14" height="14" rx="3" fill="#FFCA28" />
      <path d="M155 81.5v7.2M151.4 85.1h7.2" stroke="#F9A825" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
