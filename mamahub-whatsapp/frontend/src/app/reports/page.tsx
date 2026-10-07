"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

export default function ReportsPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    api<Record<string, unknown>>("/api/reports").then(setData).catch(() => undefined);
  }, []);

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Reports</h1>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {["conversations", "unread", "orders", "sales", "missed_conversations"].map((key) => (
            <div key={key} className="crm-paper rounded-2xl p-4 shadow-sm">
              <div className="crm-paper-muted text-sm capitalize">{key.replaceAll("_", " ")}</div>
              <div className="mt-2 text-2xl font-semibold">{String(data?.[key] ?? "—")}</div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
