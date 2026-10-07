"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type AiStatus = {
  auto_reply: boolean;
  pause_when_human: boolean;
  agent_name: string;
  model: string;
  openai_configured: boolean;
};

export default function AiPage() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setStatus(await api<AiStatus>("/api/ai/status"));
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "Could not load AI"));
  }, []);

  async function setFlag(field: "auto_reply" | "pause_when_human", on: boolean) {
    setSaving(true);
    setError("");
    try {
      setStatus(await api<AiStatus>("/api/ai/settings", { method: "PATCH", body: JSON.stringify({ [field]: on }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-3 text-2xl font-semibold">WhatsApp AI</h1>
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <div className="max-w-2xl space-y-4">
          <div className="rounded-2xl crm-paper p-5 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-semibold">Auto-reply on WhatsApp</div>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  When a customer messages +974 7132 2553, the bot answers like a sales person
                  and can send matching products.
                </p>
              </div>
              <button
                type="button"
                className={`btn-primary px-4 ${status?.auto_reply ? "" : "btn-ghost"}`}
                disabled={saving || !status}
                onClick={() => setFlag("auto_reply", !status?.auto_reply)}
              >
                {status?.auto_reply ? "On" : "Off"}
              </button>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--line)] pt-4">
              <div>
                <div className="font-semibold">Pause when staff replies</div>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  Stay quiet for 15 minutes after a human sends a message.
                </p>
              </div>
              <button
                type="button"
                className={`btn-primary px-4 ${status?.pause_when_human ? "" : "btn-ghost"}`}
                disabled={saving || !status}
                onClick={() => setFlag("pause_when_human", !status?.pause_when_human)}
              >
                {status?.pause_when_human ? "On" : "Off"}
              </button>
            </div>
          </div>
          <div className="rounded-2xl crm-paper p-5 text-sm shadow-sm">
            <div>OpenAI: {status?.openai_configured ? "connected" : "missing API key in server .env"}</div>
            <div className="mt-1 text-[var(--muted)]">Model: {status?.model || "—"} · Name: {status?.agent_name || "MamaHub"}</div>
            <p className="mt-3 text-[var(--muted)]">
              In a chat you can still tap <strong>+ AI draft</strong> to write a reply yourself.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
