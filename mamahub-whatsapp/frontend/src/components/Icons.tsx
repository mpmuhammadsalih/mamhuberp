export function Icon({ name, className = "size-4" }: { name: string; className?: string }) {
  const common = {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (name) {
    case "dashboard":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="8" height="8" rx="1.5" />
          <rect x="13" y="3" width="8" height="5" rx="1.5" />
          <rect x="13" y="10" width="8" height="11" rx="1.5" />
          <rect x="3" y="13" width="8" height="8" rx="1.5" />
        </svg>
      );
    case "inbox":
      return (
        <svg {...common}>
          <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z" />
        </svg>
      );
    case "orders":
      return (
        <svg {...common}>
          <path d="M6 6h15l-1.5 9h-12z" />
          <circle cx="9" cy="20" r="1.4" />
          <circle cx="18" cy="20" r="1.4" />
          <path d="M6 6 5 3H2" />
        </svg>
      );
    case "customers":
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
          <circle cx="17" cy="8" r="2.2" />
          <path d="M16 14.5a4.5 4.5 0 0 1 4.5 4.5" />
        </svg>
      );
    case "products":
      return (
        <svg {...common}>
          <path d="M12 3 4 7v10l8 4 8-4V7z" />
          <path d="M12 12 4 8m8 4 8-4M12 12v10" />
        </svg>
      );
    case "templates":
      return (
        <svg {...common}>
          <rect x="5" y="3" width="14" height="18" rx="2" />
          <path d="M8 8h8M8 12h8M8 16h5" />
        </svg>
      );
    case "replies":
      return (
        <svg {...common}>
          <path d="m4 12 6-7v4h10v6H10v4z" />
        </svg>
      );
    case "ai":
      return (
        <svg {...common}>
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M6.2 6.2l2.1 2.1M15.7 15.7l2.1 2.1M17.8 6.2l-2.1 2.1M8.3 15.7l-2.1 2.1" />
          <circle cx="12" cy="12" r="3.2" />
        </svg>
      );
    case "agents":
      return (
        <svg {...common}>
          <circle cx="12" cy="8" r="3.2" />
          <path d="M5 19a7 7 0 0 1 14 0" />
        </svg>
      );
    case "reports":
      return (
        <svg {...common}>
          <path d="M4 19V5M4 19h16" />
          <path d="M8 16v-5M12 16V8M16 16v-7" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.5 1.5M16.9 16.9l1.5 1.5M18.4 5.6l-1.5 1.5M7.1 16.9l-1.5 1.5" />
        </svg>
      );
    case "search":
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      );
    case "copy":
      return (
        <svg {...common}>
          <rect x="8" y="8" width="12" height="12" rx="2" />
          <path d="M6 16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      );
    case "pin":
      return (
        <svg {...common}>
          <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
          <circle cx="12" cy="10" r="2.2" />
        </svg>
      );
    case "filter":
      return (
        <svg {...common}>
          <path d="M4 6h16M7 12h10M10 18h4" />
        </svg>
      );
    case "refresh":
      return (
        <svg {...common}>
          <path d="M20 12a8 8 0 1 1-2.2-5.5" />
          <path d="M20 4v5h-5" />
        </svg>
      );
    case "bell":
      return (
        <svg {...common}>
          <path d="M6 9a6 6 0 1 1 12 0c0 7 2 7 2 9H4c0-2 2-2 2-9" />
          <path d="M10 21h4" />
        </svg>
      );
    case "moon":
      return (
        <svg {...common}>
          <path d="M15 3.5A8 8 0 1 0 20.5 14 6.2 6.2 0 0 1 15 3.5z" />
        </svg>
      );
    case "sun":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" />
        </svg>
      );
    case "star":
      return (
        <svg {...common}>
          <path d="m12 3 2.4 5.6L20 9.2l-4 4.2.9 6.1L12 16.8 7.1 19.5 8 13.4 4 9.2l5.6-.6z" />
        </svg>
      );
    case "user":
      return (
        <svg {...common}>
          <circle cx="12" cy="8" r="3.2" />
          <path d="M5 19a7 7 0 0 1 14 0" />
        </svg>
      );
    case "send":
      return (
        <svg {...common} fill="currentColor" stroke="none">
          <path d="M3.4 11.2 20.2 3.6a1 1 0 0 1 1.3 1.3l-7.6 16.8a1 1 0 0 1-1.9.1l-2.4-6.6-6.6-2.4a1 1 0 0 1 .1-1.9z" />
        </svg>
      );
    case "mic":
      return (
        <svg {...common}>
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M6 11a6 6 0 0 0 12 0M12 17v4" />
        </svg>
      );
    case "emoji":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8" />
          <path d="M8 10h.01M16 10h.01M8.5 14.5s1.5 2 3.5 2 3.5-2 3.5-2" />
        </svg>
      );
    case "clip":
      return (
        <svg {...common}>
          <path d="m16 8-7.5 7.5a2.5 2.5 0 0 1-3.5-3.5L14 5.5a4 4 0 0 1 5.6 5.6l-9 9a5.5 5.5 0 0 1-7.8-7.8L12 3" />
        </svg>
      );
    case "image":
      return (
        <svg {...common}>
          <rect x="4" y="5" width="16" height="14" rx="2" />
          <circle cx="9" cy="10" r="1.5" />
          <path d="m4 16 5-4 4 3 3-2 4 3" />
        </svg>
      );
    case "pdf":
      return (
        <svg {...common}>
          <path d="M8 3h7l5 5v13H8z" />
          <path d="M15 3v5h5M10 14h4M10 17h6" />
        </svg>
      );
    case "plus":
      return (
        <svg {...common}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case "menu":
      return (
        <svg {...common}>
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      );
    case "back":
      return (
        <svg {...common}>
          <path d="M15 6 8 12l7 6" />
        </svg>
      );
    case "close":
      return (
        <svg {...common}>
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
      );
    case "edit":
      return (
        <svg {...common}>
          <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17z" />
          <path d="m13.5 6.5 3 3" />
        </svg>
      );
    case "trash":
      return (
        <svg {...common}>
          <path d="M4 7h16M9 7V5h6v2M8 7l1 12h6l1-12" />
        </svg>
      );
    case "whatsapp":
      return (
        <svg className={className} viewBox="0 0 24 24" aria-hidden>
          <circle cx="12" cy="12" r="12" fill="#25D366" />
          <path
            fill="#fff"
            d="M16.7 13.9c-.2-.1-1.3-.6-1.5-.7s-.3-.1-.5.1-.5.7-.7.8-.3.2-.5 0a5.9 5.9 0 0 1-1.7-1.1 6.4 6.4 0 0 1-1.2-1.5c-.1-.2 0-.4.1-.5l.4-.4.1-.3v-.3c0-.1 0-.3-.1-.4s-.5-1.1-.6-1.5-.4-.3-.5-.3h-.4c-.2 0-.4.1-.5.3a1.8 1.8 0 0 0-.6 1.3 3.1 3.1 0 0 0 .7 1.7 7.2 7.2 0 0 0 2.8 2.6 9 9 0 0 0 2 .8 1.9 1.9 0 0 0 1.8-.4 1.6 1.6 0 0 0 .4-1.1c0-.1 0-.2-.1-.3z"
          />
        </svg>
      );
    default:
      return <svg {...common} />;
  }
}
