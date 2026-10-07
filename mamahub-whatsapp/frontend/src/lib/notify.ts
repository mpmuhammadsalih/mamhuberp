let audioCtx: AudioContext | null = null;
let ringing = false;

type WindowWithWebkit = Window & { webkitAudioContext?: typeof AudioContext };

function getCtx() {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext || (window as WindowWithWebkit).webkitAudioContext;
  if (!Ctor) return null;
  if (!audioCtx) audioCtx = new Ctor();
  if (audioCtx.state === "suspended") void audioCtx.resume();
  return audioCtx;
}

export function unlockNotifySound() {
  try {
    getCtx();
  } catch {
    /* browsers block audio until a gesture */
  }
}

export function startNotifyUnlock() {
  const unlock = () => {
    unlockNotifySound();
    document.removeEventListener("click", unlock);
    document.removeEventListener("keydown", unlock);
    document.removeEventListener("touchstart", unlock);
  };
  document.addEventListener("click", unlock);
  document.addEventListener("keydown", unlock);
  document.addEventListener("touchstart", unlock);
  return () => {
    document.removeEventListener("click", unlock);
    document.removeEventListener("keydown", unlock);
    document.removeEventListener("touchstart", unlock);
  };
}

/** Same two-tone restaurant alarm as MamaHub web orders. */
export function playNewChatAlert() {
  if (typeof window === "undefined" || ringing) return;
  ringing = true;
  window.setTimeout(() => {
    ringing = false;
  }, 8000);
  try {
    const ctx = getCtx();
    if (!ctx) return;
    const tone = (type: OscillatorType, freq: number, start: number, dur: number, vol: number) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = type;
      osc.frequency.setValueAtTime(freq, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(vol, start + 0.02);
      gain.gain.setValueAtTime(vol, start + dur - 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      osc.start(start);
      osc.stop(start + dur + 0.02);
    };
    const t = ctx.currentTime;
    for (let i = 0; i < 10; i += 1) {
      const at = t + i * 0.72;
      tone("square", 880, at, 0.28, 0.85);
      tone("sawtooth", 880, at, 0.28, 0.35);
      tone("square", 1320, at + 0.32, 0.32, 0.9);
      tone("sawtooth", 1320, at + 0.32, 0.32, 0.4);
    }
  } catch {
    /* ignore */
  }
}

type NotifyWindow = Window & { __waOpenConversationId?: number | null };

function asConversationId(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function setOpenConversation(id: number | null) {
  const next = asConversationId(id);
  if (typeof window !== "undefined") {
    (window as NotifyWindow).__waOpenConversationId = next;
  }
}

export function getOpenConversation() {
  if (typeof window === "undefined") return null;
  return asConversationId((window as NotifyWindow).__waOpenConversationId);
}

export function inboundConversationIds(raw: string) {
  try {
    const data = JSON.parse(raw) as {
      event?: string;
      payload?: { conversation_ids?: unknown; conversation_id?: unknown };
    };
    if (data.event !== "message.created") return [];
    const ids = Array.isArray(data.payload?.conversation_ids) ? data.payload.conversation_ids : [];
    return ids.map(asConversationId).filter((id): id is number => id != null);
  } catch {
    return [];
  }
}

export function isInboundChatEvent(raw: string) {
  return inboundConversationIds(raw).length > 0;
}

export function shouldPlayNewChatAlert(raw: string) {
  const ids = inboundConversationIds(raw);
  if (!ids.length) return false;
  const openId = getOpenConversation();
  if (openId && ids.every((id) => id === openId)) return false;
  return true;
}

export function inboundAlertPayload(raw: string) {
  try {
    const data = JSON.parse(raw) as {
      event?: string;
      payload?: {
        conversation_ids?: unknown;
        alerts?: { title?: string; body?: string; url?: string; conversation_id?: unknown }[];
      };
    };
    const first = data.payload?.alerts?.[0];
    const ids = inboundConversationIds(raw);
    return {
      title: first?.title || "MamaHub WhatsApp",
      body: first?.body || "New WhatsApp message",
      url: first?.url || (ids[0] ? `/inbox?c=${ids[0]}` : "/inbox"),
      conversation_id: first?.conversation_id || ids[0] || "",
    };
  } catch {
    return { title: "MamaHub WhatsApp", body: "New WhatsApp message", url: "/inbox", conversation_id: "" };
  }
}
