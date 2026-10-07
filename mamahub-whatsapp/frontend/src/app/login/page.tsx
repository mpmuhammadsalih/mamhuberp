"use client";

import { FormEvent, useState } from "react";
import { saveAuth } from "@/lib/auth";

export default function LoginPage() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Login failed");
      if (!data.access_token) throw new Error("Login did not return a session token");
      saveAuth(data);
      window.location.replace("/inbox");
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      setError(aborted ? "Sign-in timed out. Check that the API is running on port 8090." : err instanceof Error ? err.message : "Login failed");
      setLoading(false);
    } finally {
      window.clearTimeout(timer);
    }
  }

  return (
    <div className="grid min-h-dvh place-content-center bg-[var(--forest)] px-4" style={{ paddingTop: "max(1rem, env(safe-area-inset-top))", paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
      <form onSubmit={onSubmit} className="crm-paper w-[min(100%,380px)] rounded-2xl p-8 shadow-xl">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 grid size-14 place-content-center rounded-full bg-[var(--mint)] text-lg font-extrabold text-[var(--forest)]">MH</div>
          <div className="text-sm font-semibold text-[var(--forest)]">MamaHub Trading</div>
          <h1 className="text-2xl font-semibold">WhatsApp CRM</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">Play · Learn · Grow</p>
        </div>
        <label className="mb-3 block text-sm">
          Username
          <input className="mt-1 w-full rounded-lg border border-[var(--line)] px-3 py-2" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label className="mb-4 block text-sm">
          Password
          <input type="password" className="mt-1 w-full rounded-lg border border-[var(--line)] px-3 py-2" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
        <button disabled={loading} className="btn-primary w-full py-2.5">
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
