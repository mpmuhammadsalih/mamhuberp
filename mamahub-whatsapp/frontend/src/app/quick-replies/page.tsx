"use client";

import { FormEvent, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import type { QuickReply } from "@/lib/types";

export default function QuickRepliesPage() {
  const [rows, setRows] = useState<QuickReply[]>([]);
  const [form, setForm] = useState({ shortcut: "/", title: "", body: "" });

  function load() {
    api<QuickReply[]>("/api/quick-replies").then(setRows).catch(() => undefined);
  }
  useEffect(load, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await api("/api/quick-replies", { method: "POST", body: JSON.stringify({ ...form, is_active: true }) });
    setForm({ shortcut: "/", title: "", body: "" });
    load();
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Quick Replies</h1>
        <form onSubmit={onSubmit} className="mb-6 grid max-w-xl gap-2 rounded-2xl crm-paper p-4 shadow-sm">
          <input className="rounded-lg border px-3 py-2" placeholder="/delivery" value={form.shortcut} onChange={(e) => setForm({ ...form, shortcut: e.target.value })} />
          <input className="rounded-lg border px-3 py-2" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <textarea className="rounded-lg border px-3 py-2" placeholder="Message body" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
          <button className="btn-primary py-2">Add quick reply</button>
        </form>
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <article key={row.reply_id} className="rounded-2xl crm-paper p-4 shadow-sm">
              <div className="font-semibold">{row.shortcut} — {row.title}</div>
              <p className="mt-2 text-sm">{row.body}</p>
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
