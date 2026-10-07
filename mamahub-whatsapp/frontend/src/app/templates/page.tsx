"use client";

import { FormEvent, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Template } from "@/lib/types";

export default function TemplatesPage() {
  const [rows, setRows] = useState<Template[]>([]);
  const [form, setForm] = useState({ template_name: "", category: "UTILITY", language: "en", status: "APPROVED", body_text: "" });

  function load() {
    api<Template[]>("/api/templates").then(setRows).catch(() => undefined);
  }
  useEffect(load, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await api("/api/templates", { method: "POST", body: JSON.stringify(form) });
    setForm({ template_name: "", category: "UTILITY", language: "en", status: "APPROVED", body_text: "" });
    load();
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-2 text-2xl font-semibold">Message Templates</h1>
        <p className="mb-4 text-sm text-[var(--muted)]">Store Meta-approved templates. Outside the 24-hour service window, send templates only.</p>
        <form onSubmit={onSubmit} className="mb-6 grid max-w-xl gap-2 rounded-2xl crm-paper p-4 shadow-sm">
          <input className="rounded-lg border px-3 py-2" placeholder="template name" value={form.template_name} onChange={(e) => setForm({ ...form, template_name: e.target.value })} />
          <textarea className="rounded-lg border px-3 py-2" placeholder="body" value={form.body_text} onChange={(e) => setForm({ ...form, body_text: e.target.value })} />
          <button className="btn-primary py-2">Save template</button>
        </form>
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <article key={row.template_id} className="rounded-2xl crm-paper p-4 shadow-sm">
              <div className="font-semibold">{row.template_name}</div>
              <div className="text-xs text-[var(--muted)]">{row.category} · {row.language} · {row.status}</div>
              <p className="mt-2 text-sm">{row.body_text}</p>
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
