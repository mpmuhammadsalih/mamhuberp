"use client";

import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { Icon } from "@/components/Icons";
import { api } from "@/lib/api";
import type { Customer } from "@/lib/types";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1 && /^\d+$/.test(parts[0])) return parts[0].slice(-2);
  return parts.map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function mediaSrc(path?: string | null) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${path}`;
}

function tone(value: string) {
  let hash = 0;
  for (const ch of value) hash = (hash + ch.charCodeAt(0)) % 6;
  return hash;
}

function money(value: number) {
  return `QAR ${value.toFixed(2)}`;
}

function shortDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
}

function Avatar({ name, image }: { name: string; image?: string | null }) {
  const src = mediaSrc(image);
  return (
    <div className={`cust-avatar is-${tone(name)}`} aria-hidden={src ? true : undefined}>
      {src ? <img src={src} alt="" /> : initials(name)}
    </div>
  );
}

export default function CustomersPage() {
  const [rows, setRows] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      api<Customer[]>(`/api/customers${search ? `?search=${encodeURIComponent(search)}` : ""}`)
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setReady(true));
    }, search ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [search]);

  const totals = useMemo(() => ({
    count: rows.length,
    orders: rows.reduce((sum, row) => sum + (row.total_orders || 0), 0),
    spend: rows.reduce((sum, row) => sum + (row.total_purchases || 0), 0),
  }), [rows]);

  return (
    <AppShell>
      <div className="cust-page">
        <header className="cust-hero">
          <div>
            <p className="cust-kicker">Directory</p>
            <h1>Customers</h1>
            <p>
              {ready ? `${totals.count} customer${totals.count === 1 ? "" : "s"}` : "Loading…"}
              {ready ? ` · ${totals.orders} orders · ${money(totals.spend)}` : ""}
            </p>
          </div>
          <label className="cust-search">
            <Icon name="search" className="size-3.5" />
            <input
              type="search"
              placeholder="Search name or WhatsApp"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        </header>

        {!ready && <p className="cust-empty">Loading customers…</p>}
        {ready && !rows.length && (
          <p className="cust-empty">
            {search ? "No customers match that search." : "No customers yet."}
          </p>
        )}

        {ready && rows.length > 0 && (
          <div className="cust-grid">
            {rows.map((customer) => (
              <article key={customer.customer_id} className="cust-card">
                <div className="cust-card-top">
                  <Avatar name={customer.customer_name || customer.whatsapp_number} image={customer.profile_image_url} />
                  <div className="cust-card-copy">
                    <div className="cust-card-name">{customer.customer_name || customer.whatsapp_number}</div>
                    <div className="cust-card-phone">{customer.whatsapp_number}</div>
                    <div className="cust-card-meta">
                      <span className="cust-pill">{customer.source_channel || "WhatsApp"}</span>
                      <span className="cust-pill">{customer.customer_type || "Retail"}</span>
                      {customer.erp_customer_code || customer.customer_code ? (
                        <span className="cust-code">{customer.erp_customer_code || customer.customer_code}</span>
                      ) : null}
                    </div>
                  </div>
                </div>

                {(customer.location_label || customer.address) && (
                  <p className="cust-card-place">{customer.location_label || customer.address}</p>
                )}

                <dl className="cust-stats">
                  <div>
                    <dt>Orders</dt>
                    <dd>{customer.total_orders}</dd>
                  </div>
                  <div>
                    <dt>Spent</dt>
                    <dd>{money(customer.total_purchases)}</dd>
                  </div>
                  <div>
                    <dt>Last buy</dt>
                    <dd>{shortDate(customer.last_purchase_date)}</dd>
                  </div>
                </dl>

                {customer.outstanding_balance > 0 && (
                  <p className="cust-due">Due {money(customer.outstanding_balance)}</p>
                )}

                {customer.tags?.length > 0 && (
                  <div className="cust-tags">
                    {customer.tags.slice(0, 3).map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
