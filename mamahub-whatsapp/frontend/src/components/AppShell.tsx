"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icons";
import { getUser, logout } from "@/lib/auth";
import { api, wsUrl } from "@/lib/api";
import { inboundAlertPayload, playNewChatAlert, shouldPlayNewChatAlert, startNotifyUnlock } from "@/lib/notify";
import BootSplash from "@/components/BootSplash";
import PushEnable from "@/components/PushEnable";
import { showChatNotification, testPushAlert } from "@/lib/push";
import type { Dashboard } from "@/lib/types";

const NAV = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  {
    href: "/inbox",
    label: "WhatsApp Inbox",
    icon: "inbox",
    children: [
      { href: "/inbox", label: "All Chats", filter: "all" },
      { href: "/inbox?filter=unread", label: "Unread", filter: "unread" },
      { href: "/inbox?filter=open", label: "Open", filter: "open" },
      { href: "/inbox?filter=pending", label: "Pending", filter: "pending" },
      { href: "/inbox?filter=assigned", label: "Assigned", filter: "assigned" },
      { href: "/inbox?filter=resolved", label: "Resolved", filter: "resolved" },
    ],
  },
  { href: "/orders", label: "Orders", icon: "orders" },
  { href: "/customers", label: "Customers", icon: "customers" },
  { href: "/products", label: "Products", icon: "products" },
  { href: "/templates", label: "Message Templates", icon: "templates" },
  { href: "/quick-replies", label: "Quick Replies", icon: "replies" },
  { href: "/ai", label: "AI Assistant", icon: "ai" },
  { href: "/agents", label: "Agents / Users", icon: "agents" },
  { href: "/reports", label: "Reports", icon: "reports" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

function initials(name: string) {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function AppShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const currentFilter = params.get("filter") || "all";
  const [name, setName] = useState("Staff");
  const [role, setRole] = useState("");
  const [ready, setReady] = useState(false);
  const [unread, setUnread] = useState(0);
  const [dark, setDark] = useState(false);
  const [phone, setPhone] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
  const query = params.toString();

  useEffect(() => {
    const user = getUser();
    if (!user?.access_token) {
      window.location.replace("/login");
      return;
    }
    setName(user.full_name);
    setRole(user.role);
    setReady(true);
    api<Dashboard>("/api/dashboard")
      .then((data) => setUnread(data.unread_conversations || 0))
      .catch(() => undefined);
    api<{ configured?: boolean; display_phone_number?: string; verified_name?: string }>("/api/whatsapp/health")
      .then((data) => {
        if (data.display_phone_number) setPhone(data.display_phone_number);
      })
      .catch(() => undefined);
    const saved = localStorage.getItem("wa_crm_theme") === "dark";
    setDark(saved);
    document.documentElement.dataset.theme = saved ? "dark" : "light";
    document.documentElement.style.colorScheme = saved ? "dark" : "light";
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname, query]);

  useEffect(() => startNotifyUnlock(), []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let ping = 0;
    try {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => {
        ping = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
        }, 25000);
      };
      socket.onmessage = (event) => {
        const raw = String(event.data);
        if (!shouldPlayNewChatAlert(raw)) return;
        const hidden = document.visibilityState !== "visible";
        if (hidden) {
          void showChatNotification(inboundAlertPayload(raw));
        } else {
          playNewChatAlert();
        }
        api<Dashboard>("/api/dashboard")
          .then((data) => setUnread(data.unread_conversations || 0))
          .catch(() => undefined);
      };
    } catch {
      /* ignore */
    }
    return () => {
      if (ping) window.clearInterval(ping);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return;
    if (menuOpen && !drawer.open) drawer.showModal();
    if (!menuOpen && drawer.open) drawer.close();
  }, [menuOpen]);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    document.documentElement.style.colorScheme = next ? "dark" : "light";
    localStorage.setItem("wa_crm_theme", next ? "dark" : "light");
  }

  if (!ready) {
    return <BootSplash />;
  }

  return (
    <div className="crm-shell">
      <dialog
        ref={drawerRef}
        className="crm-sidebar"
        id="crm-navigation"
        aria-label="Main menu"
        onClose={() => setMenuOpen(false)}
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          const outside =
            event.clientX < box.left ||
            event.clientX > box.right ||
            event.clientY < box.top ||
            event.clientY > box.bottom;
          if (outside) setMenuOpen(false);
        }}
      >
        <div className="crm-brand">
          <div className="crm-logo">MH</div>
          <div className="crm-brand-copy">
            <div className="crm-brand-name">MamaHub WhatsApp CRM</div>
            <div className="crm-brand-tag">Play · Learn · Grow</div>
          </div>
          <button type="button" className="crm-drawer-close" aria-label="Close menu" onClick={() => setMenuOpen(false)}>
            <Icon name="close" />
          </button>
        </div>
        <nav className="crm-nav">
          {NAV.map((item) => {
            const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <div key={item.href} className="relative mb-1">
                <Link href={item.href} className={`crm-nav-link ${active ? "is-active" : ""}`}>
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                  {item.href === "/inbox" && unread > 0 && (
                    <span className="crm-nav-badge">{unread}</span>
                  )}
                </Link>
                {item.children && active && (
                  <div className="crm-nav-sub">
                    {item.children.map((child) => (
                      <Link
                        key={child.href}
                        href={child.href}
                        className={currentFilter === child.filter && pathname.startsWith("/inbox") ? "is-active" : ""}
                      >
                        {child.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="crm-user">
          <div className="crm-user-avatar">{initials(name)}</div>
          <div className="crm-user-copy min-w-0 flex-1">
            <div className="truncate text-sm font-semibold">{name}</div>
            <div className="text-xs text-[var(--sidebar-muted)]">{role}</div>
            <button onClick={logout} className="mt-1 text-xs text-[var(--mint-strong)]">Sign out</button>
          </div>
        </div>
      </dialog>
      <div className="crm-main">
        <header className="crm-topbar">
          <div className="crm-topbar-side">
            <button
              type="button"
              className="crm-icon-btn crm-menu-btn"
              aria-label="Open menu"
              aria-expanded={menuOpen}
              aria-controls="crm-navigation"
              onClick={() => setMenuOpen(true)}
            >
              <Icon name="menu" />
            </button>
            <div className="crm-connected" title={phone || "WhatsApp Cloud API"}>
              <span className="crm-dot" />
              <strong>Connected</strong>
              <span className="crm-connected-phone">{phone || "WhatsApp Cloud API"}</span>
            </div>
          </div>
          <div className="crm-topbar-title">
            <span className="crm-topbar-title-full">MamaHub WhatsApp CRM</span>
            <span className="crm-topbar-title-short">MamaHub</span>
          </div>
          <div className="crm-topbar-side is-end">
            <button
              type="button"
              className="crm-icon-btn"
              aria-label="Test message alerts"
              onClick={() => {
                void testPushAlert();
              }}
            >
              <Icon name="bell" />
              {unread > 0 && <span className="crm-icon-dot" />}
            </button>
            <button
              type="button"
              className="crm-icon-btn"
              aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
              onClick={toggleTheme}
            >
              <Icon name={dark ? "sun" : "moon"} />
            </button>
          </div>
        </header>
        <div className="crm-page">{children}</div>
      </div>
      <PushEnable />
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<BootSplash />}>
      <AppShellInner>{children}</AppShellInner>
    </Suspense>
  );
}
