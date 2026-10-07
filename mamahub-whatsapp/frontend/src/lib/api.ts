import { getRefreshToken, getToken, getUser, logout, saveAuth } from "./auth";

const API = "";

let refreshPromise: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const data = await response.json();
      if (!data.access_token) return false;
      const current = getUser();
      saveAuth({
        access_token: data.access_token,
        refresh_token: data.refresh_token || refreshToken,
        role: data.role || current?.role || "",
        username: data.username || current?.username || "",
        full_name: data.full_name || current?.full_name || "",
        permissions: data.permissions || current?.permissions || [],
      });
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (response.status === 401) {
    if (retry && token && (await refreshSession())) {
      return api<T>(path, init, false);
    }
    logout();
    throw new Error("Please sign in");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function wsUrl() {
  const token = getToken();
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws?token=${encodeURIComponent(token)}`;
  }
  const base = process.env.NEXT_PUBLIC_WS_URL || "ws://127.0.0.1:8090/ws";
  return `${base}?token=${encodeURIComponent(token)}`;
}

