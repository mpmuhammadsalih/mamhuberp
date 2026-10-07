"use client";

import { FormEvent, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Product } from "@/lib/types";

export default function ProductsPage() {
  const [query, setQuery] = useState("Hot Wheels");
  const [rows, setRows] = useState<Product[]>([]);
  const [error, setError] = useState("");

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    try {
      setRows(await api<Product[]>(`/api/products/search?q=${encodeURIComponent(query)}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Products</h1>
        <p className="mb-3 text-sm text-[var(--muted)]">Live search against Oracle ITEMMASTER.</p>
        <form onSubmit={onSearch} className="mb-4 flex max-w-xl gap-2">
          <input className="flex-1 rounded-lg border border-[var(--line)] px-3 py-2" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="btn-primary px-4">Search</button>
        </form>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((product) => (
            <article key={product.itemcode} className="crm-paper rounded-2xl p-4 shadow-sm">
              <div className="font-semibold">{product.itemname}</div>
              <div className="crm-paper-muted text-xs">{product.itemcode} · {product.brand || "—"}</div>
              <div className="mt-2 text-sm">Stock: {product.currentstock}</div>
              <div className="text-sm font-medium">QAR {product.retailprice}</div>
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
