"use client";

import { useEffect, useState } from "react";

const DISMISS_KEY = "wa_crm_install_dismissed";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || Boolean((navigator as Navigator & { standalone?: boolean }).standalone);
}

function isIosDevice() {
  const ua = navigator.userAgent;
  const iPhone = /iphone|ipod/i.test(ua);
  const iPad = /ipad/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return iPhone || iPad;
}

export default function PwaRegister() {
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIos, setShowIos] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { updateViaCache: "none" })
        .then((registration) => {
          registration.waiting?.postMessage({ type: "SKIP_WAITING" });
          return registration.update();
        })
        .catch(() => undefined);
    }

    if (isStandalone() || localStorage.getItem(DISMISS_KEY) === "1") return;

    const onPrompt = (event: Event) => {
      event.preventDefault();
      setInstallEvent(event as BeforeInstallPromptEvent);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);

    if (isIosDevice()) {
      setShowIos(true);
      setVisible(true);
    }

    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  async function install() {
    if (!installEvent) return;
    await installEvent.prompt();
    const choice = await installEvent.userChoice;
    if (choice.outcome === "accepted") {
      setVisible(false);
      setInstallEvent(null);
    }
  }

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div className="pwa-banner" role="dialog" aria-label="Install MamaHub WhatsApp">
      <img src="/icons/icon-192.png" alt="" width={40} height={40} />
      <div className="pwa-banner-copy">
        <strong>Install MamaHub WhatsApp</strong>
        {showIos && !installEvent ? (
          <span>
            Tap <b>Share</b> then <b>Add to Home Screen</b>
          </span>
        ) : (
          <span>Add it to your phone like an app</span>
        )}
      </div>
      {installEvent ? (
        <button type="button" className="btn-primary pwa-banner-action" onClick={() => void install()}>
          Install
        </button>
      ) : null}
      <button type="button" className="pwa-banner-close" aria-label="Dismiss" onClick={dismiss}>
        ×
      </button>
    </div>
  );
}
