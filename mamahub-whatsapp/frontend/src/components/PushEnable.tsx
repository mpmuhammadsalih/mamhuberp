"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { canUsePush, subscribePushAlerts } from "@/lib/push";

const DISMISS_KEY = "wa_crm_push_dismissed";

function isStandalone() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  );
}

function isIosDevice() {
  const ua = navigator.userAgent;
  return /iphone|ipod|ipad/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export default function PushEnable() {
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if (!getToken()) return;
    if (!canUsePush()) {
      if (isIosDevice() && !isStandalone()) setIosHint(true);
      return;
    }
    if (Notification.permission === "granted") {
      void subscribePushAlerts();
      const onVisible = () => {
        if (document.visibilityState === "visible") void subscribePushAlerts();
      };
      document.addEventListener("visibilitychange", onVisible);
      return () => document.removeEventListener("visibilitychange", onVisible);
    }
    if (localStorage.getItem(DISMISS_KEY) === "1") return;
    if (Notification.permission === "denied") return;
    if (isIosDevice() && !isStandalone()) {
      setIosHint(true);
      return;
    }
    setVisible(true);
  }, []);

  async function enable() {
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        localStorage.setItem(DISMISS_KEY, "1");
        setVisible(false);
        return;
      }
      await subscribePushAlerts();
      setVisible(false);
    } catch {
      setVisible(false);
    } finally {
      setBusy(false);
    }
  }

  if (iosHint) {
    return (
      <div className="pwa-banner pwa-notify" role="status">
        <img src="/icons/icon-192.png" alt="" width={40} height={40} />
        <div className="pwa-banner-copy">
          <strong>Alerts need the installed app</strong>
          <span>Add to Home Screen, open MamaHub WA, then allow notifications</span>
        </div>
        <button type="button" className="pwa-banner-close" aria-label="Dismiss" onClick={() => setIosHint(false)}>
          ×
        </button>
      </div>
    );
  }

  if (!visible) return null;

  return (
    <div className="pwa-banner pwa-notify" role="dialog" aria-label="Enable message alerts">
      <img src="/icons/icon-192.png" alt="" width={40} height={40} />
      <div className="pwa-banner-copy">
        <strong>Get message alerts</strong>
        <span>Notify this phone when a customer writes on WhatsApp</span>
      </div>
      <button type="button" className="btn-primary pwa-banner-action" disabled={busy} onClick={() => void enable()}>
        {busy ? "…" : "Allow"}
      </button>
      <button
        type="button"
        className="pwa-banner-close"
        aria-label="Dismiss"
        onClick={() => {
          localStorage.setItem(DISMISS_KEY, "1");
          setVisible(false);
        }}
      >
        ×
      </button>
    </div>
  );
}
