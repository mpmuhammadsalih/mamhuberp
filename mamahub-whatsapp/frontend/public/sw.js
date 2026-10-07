/* MamaHub WhatsApp CRM service worker v6 */
const SW_VERSION = "v6";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("push", (event) => {
  event.waitUntil(showPush(event));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/inbox";
  event.waitUntil(openChat(url));
});

self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(renewSubscription(event));
});

async function showPush(event) {
  let payload = { title: "MamaHub WhatsApp", body: "New WhatsApp message", url: "/inbox" };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    try {
      if (event.data) payload.body = event.data.text() || payload.body;
    } catch {
      /* ignore */
    }
  }
  const conversationId = payload.conversation_id || "new";
  return self.registration.showNotification(payload.title || "MamaHub WhatsApp", {
    body: payload.body || "New WhatsApp message",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: `wa-${SW_VERSION}-${conversationId}-${Date.now()}`,
    renotify: true,
    silent: false,
    requireInteraction: true,
    vibrate: [250, 120, 250, 120, 400, 120, 400],
    data: { url: payload.url || "/inbox", conversation_id: conversationId },
  });
}

async function renewSubscription(event) {
  try {
    const key = event.oldSubscription && event.oldSubscription.options
      ? event.oldSubscription.options.applicationServerKey
      : undefined;
    const subscription = await self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    });
    await fetch("/api/push/renew", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        old_endpoint: (event.oldSubscription && event.oldSubscription.endpoint) || "",
        ...subscription.toJSON(),
      }),
    });
  } catch {
    /* page will resubscribe on next open */
  }
}

async function openChat(url) {
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const client of windows) {
    if ("focus" in client) {
      await client.focus();
      if ("navigate" in client) await client.navigate(url);
      return;
    }
  }
  await self.clients.openWindow(url);
}
