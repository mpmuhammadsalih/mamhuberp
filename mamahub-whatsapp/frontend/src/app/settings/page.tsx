"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type Setting = { key: string; value: string; group: string };

export default function SettingsPage() {
  const [rows, setRows] = useState<Setting[]>([]);
  const [tab, setTab] = useState("company");
  const [setup, setSetup] = useState<{
    callback_url?: string;
    verify_token?: string;
    display_phone_number?: string;
    last_webhook_at?: string | null;
    inbound_ready?: boolean;
  } | null>(null);

  useEffect(() => {
    api<Setting[]>("/api/settings").then(setRows).catch(() => undefined);
    api<typeof setup>("/api/whatsapp/setup").then(setSetup).catch(() => undefined);
  }, []);

  const groups = [
    { id: "whatsapp", label: "WhatsApp API" },
    { id: "ai", label: "AI Configuration" },
    { id: "company", label: "Company Settings" },
    { id: "webhook", label: "Webhook Settings" },
  ];

  async function save() {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ items: rows }) });
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Settings</h1>
        <div className="mb-4 flex gap-2">
          {groups.map((group) => (
            <button key={group.id} onClick={() => setTab(group.id)} className={`chip ${tab === group.id ? "is-active" : "crm-paper"}`}>{group.label}</button>
          ))}
        </div>
        {tab === "whatsapp" && (
          <div className="max-w-xl rounded-2xl crm-paper p-5 text-sm shadow-sm">
            WhatsApp tokens live in the server <code>.env</code> only: <code>WHATSAPP_ACCESS_TOKEN</code>,
            <code> WHATSAPP_PHONE_NUMBER_ID</code>, <code>WHATSAPP_VERIFY_TOKEN</code>. They are never sent to the browser.
          </div>
        )}
        {tab === "webhook" && (
          <div className="max-w-xl space-y-3 rounded-2xl crm-paper p-5 text-sm shadow-sm">
            <p>
              Incoming chats only appear after Meta is pointed at this callback. Until then the inbox
              can send, but replies will not arrive.
            </p>
            <p>
              Reply to <strong>{setup?.display_phone_number || "+974 7132 2553"}</strong> — not the shop
              number +974 7235 2255.
            </p>
            <p>
              Status:{" "}
              {setup?.inbound_ready
                ? `Meta reached us at ${setup.last_webhook_at}`
                : "Meta has not sent any webhook yet"}
            </p>
            <label className="block">
              Callback URL
              <input className="mt-1 w-full rounded-lg border px-3 py-2" readOnly value={setup?.callback_url || "https://whatsapp.mamahub.store/api/whatsapp/webhook"} />
            </label>
            <label className="block">
              Verify token
              <input className="mt-1 w-full rounded-lg border px-3 py-2" readOnly value={setup?.verify_token || ""} />
            </label>
            <p>
              In Meta Developer → WhatsApp → Configuration, paste those two values, click Verify and save,
              then subscribe to <code>messages</code>, <code>message_deliveries</code>, and <code>message_reads</code>.
            </p>
          </div>
        )}
        {tab === "ai" && (
          <div className="max-w-xl space-y-3 rounded-2xl crm-paper p-5 shadow-sm">
            <p className="text-sm text-[var(--muted)]">
              When auto-reply is on, incoming WhatsApp messages are answered like a sales person.
              Matching products are sent automatically.
            </p>
            {rows.filter((row) => row.group === "ai" && row.key !== "ai_agent_v1").map((row) => (
              <label key={row.key} className="block text-sm">
                {row.key === "ai_auto_reply" ? "WhatsApp auto-reply"
                  : row.key === "ai_pause_when_human" ? "Pause 15 minutes after a staff reply"
                  : row.key === "ai_agent_name" ? "Agent name"
                  : row.key === "ai_model" ? "AI model"
                  : row.key}
                {row.key === "ai_auto_reply" || row.key === "ai_pause_when_human" ? (
                  <select
                    className="mt-1 w-full rounded-lg border px-3 py-2"
                    value={row.value === "1" || row.value === "true" ? "1" : "0"}
                    onChange={(e) => setRows((prev) => prev.map((item) => item.key === row.key ? { ...item, value: e.target.value } : item))}
                  >
                    <option value="1">On</option>
                    <option value="0">Off</option>
                  </select>
                ) : (
                  <input className="mt-1 w-full rounded-lg border px-3 py-2" value={row.value || ""} onChange={(e) => setRows((prev) => prev.map((item) => item.key === row.key ? { ...item, value: e.target.value } : item))} />
                )}
              </label>
            ))}
            <button onClick={save} className="btn-primary px-4 py-2">Save</button>
          </div>
        )}
        {tab === "company" && (
          <div className="max-w-xl space-y-3 rounded-2xl crm-paper p-5 shadow-sm">
            {rows.filter((row) => row.group === "company").map((row) => (
              <label key={row.key} className="block text-sm">
                {row.key}
                <input className="mt-1 w-full rounded-lg border px-3 py-2" value={row.value || ""} onChange={(e) => setRows((prev) => prev.map((item) => item.key === row.key ? { ...item, value: e.target.value } : item))} />
              </label>
            ))}
            <button onClick={save} className="btn-primary px-4 py-2">Save</button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
