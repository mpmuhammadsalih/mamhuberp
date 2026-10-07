import { api } from "@/lib/api";
import { getToken } from "@/lib/auth";

function urlBase64ToUint8Array(value: string) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

export function canUsePush() {
  return (
    typeof window !== "undefined" &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

export async function subscribePushAlerts() {
  if (!canUsePush() || !getToken() || Notification.permission !== "granted") return false;
  const registration = await navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" });
  registration.waiting?.postMessage({ type: "SKIP_WAITING" });
  await registration.update().catch(() => undefined);
  await navigator.serviceWorker.ready;
  const { public_key } = await api<{ public_key: string }>("/api/push/public-key");
  if (!public_key) return false;
  const key = urlBase64ToUint8Array(public_key);
  let subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    const current = subscription.options.applicationServerKey
      ? new Uint8Array(subscription.options.applicationServerKey)
      : null;
    const sameKey = current && current.length === key.length && current.every((value, index) => value === key[index]);
    if (!sameKey) {
      await subscription.unsubscribe().catch(() => undefined);
      subscription = null;
    }
  }
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    });
  }
  await api("/api/push/subscribe", {
    method: "POST",
    body: JSON.stringify(subscription.toJSON()),
  });
  return true;
}

export async function enablePushAlerts() {
  if (!canUsePush()) return false;
  const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
  if (permission !== "granted") return false;
  return subscribePushAlerts();
}

export async function testPushAlert() {
  if (!(await enablePushAlerts())) return false;
  await api("/api/push/test", { method: "POST" });
  return true;
}

export async function showChatNotification(alert: {
  title?: string;
  body?: string;
  url?: string;
  conversation_id?: number | string;
}) {
  if (typeof window === "undefined" || Notification.permission !== "granted") return false;
  const registration = await navigator.serviceWorker.ready.catch(() => undefined);
  const payload = {
    title: alert.title || "MamaHub WhatsApp",
    body: alert.body || "New WhatsApp message",
    url: alert.url || "/inbox",
    conversation_id: alert.conversation_id || "",
  };
  if (registration?.showNotification) {
    await registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: `wa-live-${payload.conversation_id || "chat"}-${Date.now()}`,
      renotify: true,
      silent: false,
      data: payload,
    });
    return true;
  }
  return false;
}
