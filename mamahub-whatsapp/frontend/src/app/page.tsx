"use client";

import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Dashboard } from "@/lib/types";

type Point = { date: string; label: string; value: number };

function padDate(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function fillDays(rows: { date: string; value: number }[] | undefined, days = 7): Point[] {
  const map = new Map((rows || []).map((row) => [String(row.date).slice(0, 10), Number(row.value) || 0]));
  const points: Point[] = [];
  for (let i = days - 1; i >= 0; i -= 1) {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    date.setDate(date.getDate() - i);
    const key = padDate(date);
    points.push({
      date: key,
      label: date.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }),
      value: map.get(key) || 0,
    });
  }
  return points;
}

function LineChart({ points, color, fill }: { points: Point[]; color: string; fill: string }) {
  const width = 560;
  const height = 148;
  const pad = 22;
  const max = Math.max(...points.map((point) => point.value), 1);
  const coords = points.map((point, index) => {
    const x = pad + (index * (width - pad * 2)) / Math.max(points.length - 1, 1);
    const y = height - pad - (point.value / max) * (height - pad * 2);
    return { x, y, ...point };
  });
  const line = coords.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${pad},${height - pad} ${line} ${coords.at(-1)?.x || pad},${height - pad}`;
  return (
    <svg className="dash-svg" viewBox={`0 0 ${width} ${height}`} role="img">
      {[0.25, 0.5, 0.75, 1].map((step) => (
        <line key={step} className="dash-grid" x1={pad} x2={width - pad} y1={height - pad - step * (height - pad * 2)} y2={height - pad - step * (height - pad * 2)} />
      ))}
      <polygon points={area} fill={fill} />
      <polyline points={line} fill="none" stroke={color} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      {coords.map((point) => (
        <g key={point.date}>
          <circle cx={point.x} cy={point.y} r="4" fill={color} />
          <text x={point.x} y={height - 8} textAnchor="middle" className="dash-axis">{point.label}</text>
        </g>
      ))}
    </svg>
  );
}

function BarChart({ points, color }: { points: Point[]; color: string }) {
  const width = 560;
  const height = 148;
  const pad = 22;
  const max = Math.max(...points.map((point) => point.value), 1);
  const gap = 10;
  const barW = Math.max(12, (width - pad * 2) / points.length - gap);
  return (
    <svg className="dash-svg" viewBox={`0 0 ${width} ${height}`} role="img">
      {points.map((point, index) => {
        const h = (point.value / max) * (height - pad * 2);
        const x = pad + index * (barW + gap);
        const y = height - pad - h;
        return (
          <g key={point.date}>
            <rect x={x} y={y} width={barW} height={Math.max(h, 2)} rx="6" fill={color} />
            <text x={x + barW / 2} y={height - 8} textAnchor="middle" className="dash-axis">{point.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Donut({ slices }: { slices: { label: string; value: number; color: string }[] }) {
  const total = slices.reduce((sum, slice) => sum + slice.value, 0) || 1;
  const radius = 54;
  const circ = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="dash-donut">
      <svg viewBox="0 0 140 140" className="dash-donut-svg">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="var(--line)" strokeWidth="16" />
        {slices.map((slice) => {
          const len = (slice.value / total) * circ;
          const node = (
            <circle
              key={slice.label}
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              stroke={slice.color}
              strokeWidth="16"
              strokeDasharray={`${len} ${circ - len}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              transform="rotate(-90 70 70)"
            />
          );
          offset += len;
          return node;
        })}
        <text x="70" y="66" textAnchor="middle" className="dash-donut-total">{slices.reduce((sum, slice) => sum + slice.value, 0)}</text>
        <text x="70" y="84" textAnchor="middle" className="dash-donut-sub">chats</text>
      </svg>
      <ul className="dash-legend">
        {slices.map((slice) => (
          <li key={slice.label}>
            <span style={{ background: slice.color }} />
            {slice.label}
            <strong>{slice.value}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

const KPI = [
  { key: "today_messages", label: "Messages today", tone: "green", hint: "All inbound + outbound" },
  { key: "active_conversations", label: "Active chats", tone: "teal", hint: "Open and pending" },
  { key: "unread_conversations", label: "Unread", tone: "amber", hint: "Waiting for a reply" },
  { key: "orders_today", label: "Orders today", tone: "blue", hint: "CRM orders created" },
  { key: "whatsapp_orders_today", label: "WhatsApp orders", tone: "violet", hint: "From inbox cart" },
  { key: "sales_today", label: "Sales today", tone: "rose", hint: "Confirmed WhatsApp sales" },
  { key: "pending_orders", label: "Pending orders", tone: "orange", hint: "Not delivered yet" },
  { key: "resolved_conversations", label: "Resolved chats", tone: "mint", hint: "Closed this week" },
] as const;

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/api/dashboard").then(setData).catch((err) => setError(err.message));
  }, []);

  const conversations = useMemo(() => fillDays(data?.conversations_by_day), [data]);
  const sales = useMemo(() => fillDays(data?.sales_by_day), [data]);
  const orders = useMemo(() => fillDays(data?.orders_by_day), [data]);
  const agentMax = Math.max(1, ...(data?.agent_performance || []).map((row) => row.messages_sent));
  const productMax = Math.max(1, ...(data?.top_products || []).map((row) => row.qty));

  function kpiValue(key: (typeof KPI)[number]["key"]) {
    if (!data) return "—";
    if (key === "sales_today") return `QAR ${data.sales_today.toFixed(2)}`;
    return data[key];
  }

  return (
    <AppShell>
      <div className="dash-page">
        <div className="dash-hero">
          <p className="dash-kicker">MamaHub WhatsApp</p>
          <h1>Live sales dashboard</h1>
          <p>Last 7 days</p>
        </div>
        {error && <p className="dash-error">{error}</p>}

        <div className="dash-kpis">
          {KPI.map((item) => (
            <article key={item.key} className={`dash-kpi is-${item.tone}`}>
              <div className="dash-kpi-label">{item.label}</div>
              <div className="dash-kpi-value">{kpiValue(item.key)}</div>
              <div className="dash-kpi-hint">{item.hint}</div>
            </article>
          ))}
        </div>

        <div className="dash-grid">
          <section className="dash-card">
            <h2>Conversations by day</h2>
            <LineChart points={conversations} color="#128c5b" fill="rgba(18,140,91,0.16)" />
          </section>
          <section className="dash-card">
            <h2>Chat mix</h2>
            <Donut
              slices={[
                { label: "Active", value: data?.active_conversations || 0, color: "#128c5b" },
                { label: "Unread", value: data?.unread_conversations || 0, color: "#f59e0b" },
                { label: "Resolved", value: data?.resolved_conversations || 0, color: "#38bdf8" },
              ]}
            />
          </section>
          <section className="dash-card">
            <h2>Sales by day</h2>
            <BarChart points={sales} color="#f43f5e" />
          </section>
          <section className="dash-card">
            <h2>Orders by day</h2>
            <BarChart points={orders} color="#7c3aed" />
          </section>
          <section className="dash-card">
            <h2>Agent performance</h2>
            {(data?.agent_performance || []).slice(0, 4).map((row) => (
              <div key={row.name} className="dash-bar-row">
                <div className="dash-bar-copy">
                  <span>{row.name}</span>
                  <em>{row.messages_sent} sent · {row.assigned_chats} assigned</em>
                </div>
                <div className="dash-bar-track">
                  <i style={{ width: `${(row.messages_sent / agentMax) * 100}%`, background: "#0ea5e9" }} />
                </div>
              </div>
            ))}
            {!data?.agent_performance?.length && <p className="dash-empty">No agent activity yet</p>}
          </section>
          <section className="dash-card">
            <h2>Top products</h2>
            {(data?.top_products || []).slice(0, 4).map((row) => (
              <div key={row.itemname} className="dash-bar-row">
                <div className="dash-bar-copy">
                  <span>{row.itemname.toLowerCase().replace(/\b([a-z0-9])/g, (char) => char.toUpperCase())}</span>
                  <em>{row.qty}</em>
                </div>
                <div className="dash-bar-track">
                  <i style={{ width: `${(row.qty / productMax) * 100}%`, background: "#f59e0b" }} />
                </div>
              </div>
            ))}
            {!data?.top_products?.length && <p className="dash-empty">No WhatsApp orders yet</p>}
          </section>
        </div>
      </div>
    </AppShell>
  );
}
