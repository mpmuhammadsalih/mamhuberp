"use client";

import { FormEvent, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type Agent = { user_id: number; username: string; full_name: string; email?: string; role: string; is_active: boolean };

export default function AgentsPage() {
  const [rows, setRows] = useState<Agent[]>([]);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", email: "", role: "SALES" });
  const [error, setError] = useState("");

  function load() {
    api<Agent[]>("/api/users").then(setRows).catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await api("/api/users", { method: "POST", body: JSON.stringify(form) });
    setForm({ username: "", password: "", full_name: "", email: "", role: "SALES" });
    load();
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Agents / Users</h1>
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <form onSubmit={onSubmit} className="mb-6 grid max-w-xl gap-2 rounded-2xl crm-paper p-4 shadow-sm">
          <input className="rounded-lg border px-3 py-2" placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input className="rounded-lg border px-3 py-2" placeholder="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <input className="rounded-lg border px-3 py-2" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input type="password" className="rounded-lg border px-3 py-2" placeholder="Password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <select className="rounded-lg border px-3 py-2" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option>SUPER_ADMIN</option><option>ADMIN</option><option>SALES</option><option>CUSTOMER_SERVICE</option>
          </select>
          <button className="btn-primary py-2">Create user</button>
        </form>
        <div className="rounded-2xl crm-paper shadow-sm">
          {rows.map((row) => (
            <div key={row.user_id} className="flex justify-between border-b border-[var(--line)] px-4 py-3 text-sm">
              <div>
                <div className="font-medium">{row.full_name}</div>
                <div className="text-[var(--muted)]">{row.username} · {row.email}</div>
              </div>
              <div>{row.role}</div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
