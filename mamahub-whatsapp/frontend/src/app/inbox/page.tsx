"use client";

import { FormEvent, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import AppShell from "@/components/AppShell";
import BootSplash from "@/components/BootSplash";
import { Icon } from "@/components/Icons";
import { api, wsUrl } from "@/lib/api";
import { setOpenConversation } from "@/lib/notify";
import type { AdReferral, Agent, CartItem, Conversation, Customer, Message, Order, Product, QuickReply, Template } from "@/lib/types";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "unread", label: "Unread" },
  { id: "open", label: "Open" },
  { id: "pending", label: "Pending" },
  { id: "resolved", label: "Resolved" },
  { id: "assigned", label: "Assigned" },
  { id: "starred", label: "Starred" },
];

const EMOJIS = ["😀", "👍", "🙏", "❤️", "😊", "🎉", "🚗", "🧸", "✅", "📍"];
const RIGHT_TABS = [
  { id: "details", label: "Customer" },
  { id: "orders", label: "Orders" },
  { id: "products", label: "Products" },
  { id: "notes", label: "Notes" },
  { id: "history", label: "History" },
];

function initials(name: string) {
  return name.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-GB", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
}

function statusTicks(status: string) {
  if (status === "DELETED") return null;
  if (status === "FAILED") return <span className="chat-ticks is-failed">!</span>;
  if (status === "READ") return <span className="chat-ticks is-read" aria-label="Read">✓✓</span>;
  if (status === "DELIVERED") return <span className="chat-ticks is-delivered" aria-label="Delivered">✓✓</span>;
  return <span className="chat-ticks" aria-label="Sent">✓</span>;
}

function mapsLink(lat?: string | null, lng?: string | null) {
  if (!lat || !lng) return "";
  return `https://maps.google.com/?q=${encodeURIComponent(`${lat},${lng}`)}`;
}

function copyTextFor(message: Message) {
  if (message.status === "DELETED") return "This message was deleted";
  if (message.latitude && message.longitude) {
    return [message.message_text, mapsLink(message.latitude, message.longitude)].filter(Boolean).join("\n");
  }
  return (message.message_text || message.media_url || `[${message.message_type}]`).trim();
}

const SHOP_LOCATION = {
  latitude: 25.3165,
  longitude: 51.531,
  location_name: "MamaHub — West Bay, Doha",
};

function messagePreview(message: Message) {
  if (message.status === "DELETED") return "This message was deleted";
  return (message.message_text || `[${message.message_type}]`).slice(0, 160);
}

function prettyName(value: string) {
  return value
    .toLowerCase()
    .replace(/\b([a-z0-9])/g, (char) => char.toUpperCase());
}

function mediaSrc(path?: string | null) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${path}`;
}

function Avatar({ name, image }: { name: string; image?: string | null }) {
  const src = mediaSrc(image);
  return (
    <div className="inbox-avatar">
      {src ? <img src={src} alt="" /> : initials(name)}
    </div>
  );
}

function productImageSrc(path?: string | null) {
  if (!path) return "";
  if (path.startsWith("http") || path.startsWith("/api/")) return mediaSrc(path);
  const name = path.split("/").pop();
  return name ? `https://www.mamahub.store/api/v1/products/images/${name}` : "";
}

function AdCard({ ad }: { ad: AdReferral }) {
  const image = mediaSrc(ad.image_url);
  return (
    <div className="chat-row is-theirs">
      <div className="chat-bubble inbox-ad-card">
        <div className="inbox-ad-kicker">Facebook ad</div>
        {image ? <img className="chat-media inbox-ad-image" src={image} alt="" /> : null}
        {ad.headline ? <div className="inbox-ad-title">{ad.headline}</div> : null}
        {ad.body ? <div className="inbox-ad-body">{ad.body}</div> : null}
        {ad.source_url ? (
          <a className="inbox-ad-link" href={ad.source_url} target="_blank" rel="noreferrer">
            Open ad
          </a>
        ) : null}
      </div>
    </div>
  );
}

function productBadge(product: Product, collection: string) {
  if (collection === "trending") return "Best Seller";
  if (collection === "new") return "New";
  if (collection === "offers" || product.offer_price) return "Offer";
  return "";
}

function uniqueProducts(rows: Product[]) {
  const seen = new Set<string>();
  const out: Product[] = [];
  for (const row of rows || []) {
    const code = String(row.itemcode || "").trim();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    out.push(row);
  }
  return out;
}

function pickPayload(product: Product) {
  return {
    itemcode: product.itemcode,
    itemname: product.itemname,
    retailprice: product.retailprice,
    offer_price: product.offer_price,
    image_url: product.image_url,
    currentstock: product.currentstock,
  };
}

function ProductTile({
  product,
  picked,
  canPick,
  collection,
  sending,
  onToggle,
  onAdd,
  onSend,
}: {
  product: Product;
  picked: boolean;
  canPick: boolean;
  collection: string;
  sending?: boolean;
  onToggle: () => void;
  onAdd: () => void;
  onSend: () => void;
}) {
  const photo = productImageSrc(product.image_url);
  const badge = productBadge(product, collection);
  const price = product.offer_price || product.retailprice;

  return (
    <article className={`product-card${picked ? " is-picked" : ""}`}>
      <div className="product-card-frame">
        <button type="button" className="product-card-hit" onClick={onToggle} disabled={!picked && !canPick} aria-pressed={picked}>
          <div className="product-card-media">
            {badge ? <span className="product-card-badge">{badge}</span> : null}
            {picked ? <span className="product-card-check" aria-hidden>✓</span> : null}
            {photo ? (
              <img src={photo} alt="" />
            ) : (
              <img className="product-card-fallback" src="https://www.mamahub.store/mamahub-logo.png" alt="" />
            )}
          </div>
        </button>
        <div className="product-card-fabs">
          <button
            type="button"
            className="product-card-send"
            onClick={onSend}
            disabled={sending}
            aria-label={sending ? "Sending to chat" : "Send to chat"}
          >
            <Icon name="send" className="size-3.5" />
          </button>
          <button type="button" className="product-card-plus" onClick={onAdd} aria-label="Add to order">
            +
          </button>
        </div>
      </div>
      <div className="product-card-body">
        <div className="product-card-price">
          {product.offer_price ? (
            <>
              <span className="product-card-was">{product.currency} {Number(product.retailprice).toFixed(2)}</span>
              {product.currency} {Number(price).toFixed(2)}
            </>
          ) : (
            <>{product.currency} {Number(price).toFixed(2)}</>
          )}
        </div>
        <div className="product-card-name" title={prettyName(product.itemname)}>{prettyName(product.itemname)}</div>
      </div>
    </article>
  );
}

function ProductFilters({
  categories,
  ages,
  category,
  age,
  collection,
  inStock,
  onCategory,
  onAge,
  onCollection,
  onInStock,
}: {
  categories: string[];
  ages: { slug: string; name: string }[];
  category: string;
  age: string;
  collection: string;
  inStock: boolean;
  onCategory: (value: string) => void;
  onAge: (value: string) => void;
  onCollection: (value: string) => void;
  onInStock: (value: boolean) => void;
}) {
  const chips = [
    { id: "", label: "All" },
    { id: "new", label: "New" },
    { id: "trending", label: "Trending" },
    { id: "offers", label: "Offers" },
  ];
  return (
    <div className="inbox-product-filters">
      <div className="inbox-filter-chips" role="tablist" aria-label="Product collections">
        {chips.map((chip) => (
          <button
            key={chip.id || "all"}
            type="button"
            role="tab"
            aria-selected={collection === chip.id}
            className={`inbox-filter-chip${collection === chip.id ? " is-active" : ""}`}
            onClick={() => onCollection(chip.id)}
          >
            {chip.label}
          </button>
        ))}
        <button
          type="button"
          className={`inbox-filter-chip${inStock ? " is-active" : ""}`}
          onClick={() => onInStock(!inStock)}
        >
          In stock
        </button>
      </div>
      <div className="inbox-filter-selects">
        <label>
          Category
          <select className="inbox-select" value={category} onChange={(e) => onCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Ages
          <select className="inbox-select" value={age} onChange={(e) => onAge(e.target.value)}>
            <option value="">All ages</option>
            {ages.map((item) => (
              <option key={item.slug} value={item.slug}>{item.name}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

function tagClass(tag: string) {
  const key = tag.toLowerCase();
  if (key.includes("vip")) return "bg-purple-100 text-purple-700";
  if (key.includes("toy")) return "bg-pink-100 text-pink-700";
  return "bg-[var(--mint)] text-[var(--forest)]";
}

function InboxInner() {
  const params = useSearchParams();
  const initialFilter = params.get("filter") || "all";
  const openFromLink = Number(params.get("c") || 0) || null;
  const [filter, setFilter] = useState(initialFilter);
  const [search, setSearch] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [counts, setCounts] = useState({ all: 0, unread: 0, open: 0, pending: 0, starred: 0 });
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [notes, setNotes] = useState<{ note_id: number; note_text: string }[]>([]);
  const [noteDraft, setNoteDraft] = useState("");
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [editingNoteText, setEditingNoteText] = useState("");
  const [tab, setTab] = useState("details");
  const [draft, setDraft] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [productQuery, setProductQuery] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [productAge, setProductAge] = useState("");
  const [productCollection, setProductCollection] = useState("");
  const [productInStock, setProductInStock] = useState(false);
  const [productFilters, setProductFilters] = useState<{ categories: string[]; ages: { slug: string; name: string }[] }>({ categories: [], ages: [] });
  const [replies, setReplies] = useState<QuickReply[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [picked, setPicked] = useState<Product[]>([]);
  const [aiText, setAiText] = useState("");
  const [aiAutoReply, setAiAutoReply] = useState(false);
  const [showEmoji, setShowEmoji] = useState(false);
  const [showProducts, setShowProducts] = useState(false);
  const [showReplies, setShowReplies] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showOrder, setShowOrder] = useState(false);
  const [address, setAddress] = useState("");
  const [payment, setPayment] = useState("Cash");
  const [error, setError] = useState("");
  const [sendingSku, setSendingSku] = useState("");
  const [sendingLabel, setSendingLabel] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [showThreadSearch, setShowThreadSearch] = useState(false);
  const [threadQuery, setThreadQuery] = useState("");
  const [threadMatch, setThreadMatch] = useState(0);
  const [showLocation, setShowLocation] = useState(false);
  const [recording, setRecording] = useState(false);
  const [pane, setPane] = useState<"list" | "chat" | "details">("list");
  const [showNewChat, setShowNewChat] = useState(false);
  const [newPhone, setNewPhone] = useState("");
  const [newName, setNewName] = useState("");
  const [menuMessage, setMenuMessage] = useState<Message | null>(null);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [editMessage, setEditMessage] = useState<Message | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const imageInput = useRef<HTMLInputElement>(null);
  const pdfInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const menuRef = useRef<HTMLDialogElement>(null);
  const pressTimer = useRef<number | null>(null);
  const messagesPane = useRef<HTMLDivElement>(null);
  const chunksRef = useRef<Blob[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);

  function beginSend(label: string) {
    if (sendingRef.current) return false;
    sendingRef.current = true;
    setSendingLabel(label);
    return true;
  }

  function endSend() {
    sendingRef.current = false;
    setSendingSku("");
    setSendingLabel("");
  }

  const active = conversations.find((row) => row.conversation_id === activeId) || null;
  const isNewCustomer = (customer?.total_orders || 0) === 0;
  const threadHits = useMemo(() => {
    const q = threadQuery.trim().toLowerCase();
    if (!q) return [];
    return messages.filter((row) => {
      const hay = `${row.message_text || ""} ${row.reply_to_text || ""} ${row.message_type}`.toLowerCase();
      return hay.includes(q);
    });
  }, [messages, threadQuery]);

  async function loadConversations() {
    const query = new URLSearchParams();
    if (filter === "unread") query.set("unread", "true");
    else if (filter === "assigned") query.set("assigned_to_me", "true");
    else if (filter === "starred") query.set("starred", "true");
    else if (filter !== "all") query.set("status", filter.toUpperCase());
    if (search) query.set("search", search);
    const rows = await api<Conversation[]>(`/api/conversations?${query.toString()}`);
    setConversations(rows);
    if (!rows.length) {
      setActiveId(null);
    } else if (openFromLink && rows.some((row) => row.conversation_id === openFromLink)) {
      setActiveId(openFromLink);
      setPane("chat");
    } else if (!activeId || !rows.some((row) => row.conversation_id === activeId)) {
      setActiveId(rows[0].conversation_id);
    }
  }

  async function loadCounts() {
    try {
      const rows = await api<Conversation[]>("/api/conversations");
      setCounts({
        all: rows.length,
        unread: rows.filter((row) => row.unread_count > 0).length,
        open: rows.filter((row) => row.status === "OPEN").length,
        pending: rows.filter((row) => row.status === "PENDING").length,
        starred: rows.filter((row) => row.is_starred).length,
      });
    } catch {
      /* ignore */
    }
  }

  async function loadThread(id: number) {
    const [msgs, conv] = await Promise.all([
      api<Message[]>(`/api/conversations/${id}/messages`),
      api<Conversation>(`/api/conversations/${id}`),
    ]);
    setMessages(msgs);
    const cust = await api<Customer>(`/api/customers/${conv.customer_id}`);
    setCustomer(cust);
    setAddress(cust.address || "");
    const [orderRows, noteRows] = await Promise.all([
      api<Order[]>(`/api/orders?customer_id=${conv.customer_id}`),
      api<{ note_id: number; note_text: string }[]>(`/api/customers/${conv.customer_id}/notes`),
    ]);
    setOrders(orderRows);
    setNotes(noteRows);
    setEditingNoteId(null);
    setEditingNoteText("");
    try {
      const basket = await api<{ items: CartItem[] }>(`/api/conversations/${id}/cart`);
      setCart(basket.items || []);
      if (basket.items?.length) setShowOrder(true);
    } catch {
      /* cart table may still be creating */
    }
  }

  useEffect(() => {
    setFilter(initialFilter);
  }, [initialFilter]);

  useEffect(() => {
    loadConversations().catch((err) => setError(err.message));
    loadCounts();
    api<QuickReply[]>("/api/quick-replies").then(setReplies).catch(() => undefined);
    api<Template[]>("/api/templates").then(setTemplates).catch(() => undefined);
    api<{ auto_reply: boolean }>("/api/ai/status").then((row) => setAiAutoReply(!!row.auto_reply)).catch(() => undefined);
    api<Agent[]>("/api/users/agents").then(setAgents).catch(() => undefined);
  }, [filter]);

  useEffect(() => {
    setOpenConversation(activeId);
    setShowThreadSearch(false);
    setThreadQuery("");
    setThreadMatch(0);
    setShowLocation(false);
  }, [activeId]);

  useEffect(() => {
    if (!threadHits.length) return;
    const safe = Math.min(threadMatch, threadHits.length - 1);
    if (safe !== threadMatch) setThreadMatch(safe);
    jumpToMessage(threadHits[safe]?.id);
  }, [threadQuery, threadHits, threadMatch]);

  useEffect(() => {
    return () => setOpenConversation(null);
  }, []);

  useEffect(() => {
    setPicked([]);
    setReplyTo(null);
    setEditMessage(null);
    setMenuMessage(null);
    setConfirmDelete(false);
    if (activeId) loadThread(activeId).catch((err) => setError(err.message));
  }, [activeId]);

  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    if (menuMessage) {
      if (!el.open) el.showModal();
    } else if (el.open) {
      el.close();
    }
  }, [menuMessage]);

  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const onClose = () => {
      setMenuMessage(null);
      setConfirmDelete(false);
    };
    const onClick = (event: MouseEvent) => {
      if ("closedBy" in HTMLDialogElement.prototype) return;
      if (event.target !== el) return;
      const rect = el.getBoundingClientRect();
      const inside =
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom &&
        event.clientX >= rect.left &&
        event.clientX <= rect.right;
      if (!inside) el.close();
    };
    el.addEventListener("close", onClose);
    el.addEventListener("click", onClick);
    return () => {
      el.removeEventListener("close", onClose);
      el.removeEventListener("click", onClick);
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    try {
      socket = new WebSocket(wsUrl());
      socket.onmessage = () => {
        loadConversations().catch(() => undefined);
        loadCounts();
        if (activeId) loadThread(activeId).catch(() => undefined);
      };
    } catch {
      /* ignore */
    }
    return () => socket?.close();
  }, [activeId, filter]);

  async function send(payload: Record<string, unknown>, options?: { busy?: string | false }) {
    if (!activeId) {
      setError("Start or select a chat first.");
      return;
    }
    const ownBusy = options?.busy !== false;
    const label = typeof options?.busy === "string" ? options.busy : "Sending…";
    if (ownBusy && !beginSend(label)) return;
    try {
      const body = { ...payload };
      if (replyTo && body.reply_to_id == null) body.reply_to_id = replyTo.id;
      const message = await api<Message>(`/api/conversations/${activeId}/messages`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMessages((prev) => [...prev, message]);
      setDraft("");
      setReplyTo(null);
      if (message.status === "FAILED") {
        setError(message.error_message || "WhatsApp did not accept this message.");
      } else {
        setError("");
      }
      loadConversations().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      if (ownBusy) endSend();
    }
  }

  function openMessageMenu(message: Message) {
    if (message.status === "DELETED") return;
    setConfirmDelete(false);
    setMenuMessage(message);
  }

  function startPress(message: Message) {
    if (pressTimer.current) window.clearTimeout(pressTimer.current);
    pressTimer.current = window.setTimeout(() => {
      openMessageMenu(message);
      pressTimer.current = null;
    }, 450);
  }

  function cancelPress() {
    if (pressTimer.current) {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
  }

  function startReply(message: Message) {
    setEditMessage(null);
    setReplyTo(message);
    setMenuMessage(null);
  }

  function startEdit(message: Message) {
    setReplyTo(null);
    setEditMessage(message);
    setDraft(message.message_text || "");
    setMenuMessage(null);
  }

  function cancelComposerAction() {
    setReplyTo(null);
    setEditMessage(null);
  }

  function jumpToMessage(id?: number | null) {
    if (!id) return;
    const node = messagesPane.current?.querySelector(`#msg-${id}`);
    node?.scrollIntoView({ behavior: "smooth", block: "center" });
    node?.classList.add("is-flash");
    window.setTimeout(() => node?.classList.remove("is-flash"), 1200);
  }

  async function saveEdit() {
    if (!activeId || !editMessage || !draft.trim()) return;
    if (!beginSend("Saving…")) return;
    try {
      const updated = await api<Message>(`/api/conversations/${activeId}/messages/${editMessage.id}`, {
        method: "PATCH",
        body: JSON.stringify({ text: draft.trim() }),
      });
      setMessages((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      setDraft("");
      setEditMessage(null);
      setError("");
      loadConversations().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not edit message");
    } finally {
      endSend();
    }
  }

  async function removeMessage(message: Message) {
    if (!activeId) return;
    try {
      const updated = await api<Message>(`/api/conversations/${activeId}/messages/${message.id}`, {
        method: "DELETE",
      });
      setMessages((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      if (replyTo?.id === message.id) setReplyTo(null);
      if (editMessage?.id === message.id) {
        setEditMessage(null);
        setDraft("");
      }
      setMenuMessage(null);
      setConfirmDelete(false);
      setError("");
      loadConversations().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete message");
    }
  }

  async function startChat(event: FormEvent) {
    event.preventDefault();
    if (!newPhone.trim()) return;
    try {
      const created = await api<Conversation>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ phone: newPhone.trim(), name: newName.trim() || undefined }),
      });
      setNewPhone("");
      setNewName("");
      setShowNewChat(false);
      setActiveId(created.conversation_id);
      setPane("chat");
      setError("");
      if (filter !== "all") {
        setFilter("all");
      } else {
        await loadConversations();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start chat");
    }
  }

  async function onSend(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim()) return;
    if (editMessage) {
      await saveEdit();
      return;
    }
    const shortcut = replies.find((row) => draft.trim() === row.shortcut);
    await send({ text: shortcut ? shortcut.body : draft, message_type: "text" });
  }

  async function uploadFile(file: File, messageType: string) {
    if (!activeId) return;
    if (!beginSend(messageType === "image" ? "Sending image…" : "Sending file…")) return;
    try {
      const data = new FormData();
      data.append("file", file);
      const uploaded = await api<{ url: string }>(`/api/conversations/${activeId}/upload`, { method: "POST", body: data });
      await send({
        message_type: messageType,
        media_url: mediaSrc(uploaded.url),
        caption: draft,
      }, { busy: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send file");
    } finally {
      endSend();
    }
  }

  async function toggleStar() {
    if (!active) return;
    try {
      const updated = await api<Conversation>(`/api/conversations/${active.conversation_id}/star`, {
        method: "POST",
        body: JSON.stringify({ starred: !active.is_starred }),
      });
      setConversations((prev) => prev.map((row) => (
        row.conversation_id === updated.conversation_id ? { ...row, is_starred: updated.is_starred } : row
      )));
      loadCounts().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not star chat");
    }
  }

  async function uploadPhoto(file: File) {
    if (!customer) return;
    try {
      const data = new FormData();
      data.append("file", file);
      const updated = await api<Customer>(`/api/customers/${customer.customer_id}/photo`, { method: "POST", body: data });
      setCustomer(updated);
      setConversations((prev) => prev.map((row) => (
        row.customer_id === updated.customer_id ? { ...row, profile_image_url: updated.profile_image_url } : row
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload photo");
    }
  }

  async function toggleVoice() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")
        ? "audio/ogg;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "";
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const type = recorder.mimeType || "audio/webm";
        const ext = type.includes("ogg") ? "ogg" : "webm";
        const file = new File([new Blob(chunksRef.current, { type })], `voice-${Date.now()}.${ext}`, { type });
        try {
          await uploadFile(file, "audio");
        } catch (err) {
          setError(err instanceof Error ? err.message : "Voice note failed");
        }
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone permission denied");
    }
  }

  async function searchProducts(query = productQuery) {
    const q = query.trim();
    const filtered = Boolean(productCategory || productAge || productCollection || productInStock);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (productCategory) params.set("category", productCategory);
    if (productAge) params.set("age", productAge);
    if (productCollection) params.set("collection", productCollection);
    if (productInStock) params.set("in_stock", "true");
    if (productCollection === "offers") params.set("offers", "true");
    if (q.length < 2 && !filtered) params.set("collection", "new");
    params.set("limit", "60");
    const rows = await api<Product[]>(`/api/products/search?${params.toString()}`);
    setProducts(uniqueProducts(rows));
  }

  useEffect(() => {
    if (!showProducts && tab !== "products") return;
    api<{ categories: string[]; ages: { slug: string; name: string }[] }>("/api/products/filters")
      .then((data) => setProductFilters({ categories: data.categories || [], ages: data.ages || [] }))
      .catch(() => undefined);
  }, [showProducts, tab]);

  useEffect(() => {
    if (!showProducts && tab !== "products") return;
    const q = productQuery.trim();
    const timer = window.setTimeout(() => {
      searchProducts(q).catch(() => undefined);
    }, 220);
    return () => window.clearTimeout(timer);
  }, [productQuery, productCategory, productAge, productCollection, productInStock, showProducts, tab]);

  async function suggestAi() {
    if (!activeId) return;
    const latest = [...messages].reverse().find((row) => row.sender_type === "CUSTOMER")?.message_text || "";
    const result = await api<{ suggestion: string; products: Product[] }>("/api/ai/suggest-reply", {
      method: "POST",
      body: JSON.stringify({ conversation_id: activeId, latest_message: latest }),
    });
    setAiText(result.suggestion);
    if (result.products?.length) {
      setProducts(uniqueProducts(result.products));
      setShowProducts(true);
    }
  }

  const cartTotal = useMemo(
    () => cart.reduce((sum, item) => sum + item.quantity * item.unit_price, 0),
    [cart]
  );

  function persistCart(items: CartItem[]) {
    if (!activeId) return;
    api(`/api/conversations/${activeId}/cart`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }).catch(() => undefined);
  }

  function addToCart(product: Product) {
    setCart((prev) => {
      const existing = prev.find((row) => row.itemcode === product.itemcode);
      const next = existing
        ? prev.map((row) => (row.itemcode === product.itemcode ? { ...row, quantity: row.quantity + 1 } : row))
        : [...prev, {
          itemcode: product.itemcode,
          itemname: product.itemname,
          quantity: 1,
          unit_price: product.retailprice,
          image_url: product.image_url,
        }];
      persistCart(next);
      return next;
    });
    setShowOrder(true);
  }

  function setCartQty(itemcode: string, quantity: number) {
    const nextQty = Number.isFinite(quantity) ? Math.max(1, Math.floor(quantity)) : 1;
    setCart((prev) => {
      const next = prev.map((row) => (row.itemcode === itemcode ? { ...row, quantity: nextQty } : row));
      persistCart(next);
      return next;
    });
  }

  function removeFromCart(itemcode: string) {
    setCart((prev) => {
      const next = prev.filter((row) => row.itemcode !== itemcode);
      if (!next.length) setShowOrder(false);
      persistCart(next);
      return next;
    });
  }

  function togglePicked(product: Product) {
    setPicked((prev) => {
      const exists = prev.some((row) => row.itemcode === product.itemcode);
      if (exists) return prev.filter((row) => row.itemcode !== product.itemcode);
      if (prev.length >= 10) return prev;
      return [...prev, product];
    });
  }

  async function sendPicked(imagesOnly = false) {
    if (!activeId || !picked.length) return;
    if (!beginSend(imagesOnly ? "Sending images…" : "Sending catalog…")) return;
    try {
      await api(`/api/conversations/${activeId}/cart/send-picker`, {
        method: "POST",
        body: JSON.stringify({
          images_only: imagesOnly,
          products: picked.slice(0, 10).map(pickPayload),
        }),
      });
      setPicked([]);
      setError("");
      await loadThread(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : imagesOnly ? "Could not send images" : "Could not send catalog");
    } finally {
      endSend();
    }
  }

  async function sendProductToChat(product: Product) {
    if (!activeId) {
      setError("Start or select a chat first.");
      return;
    }
    if (!beginSend("Sending catalog…")) return;
    setSendingSku(product.itemcode);
    try {
      await api(`/api/conversations/${activeId}/cart/send-picker`, {
        method: "POST",
        body: JSON.stringify({
          products: [pickPayload(product)],
        }),
      });
      setError("");
      await loadThread(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send to chat");
    } finally {
      endSend();
    }
  }

  function cancelOrder() {
    setCart([]);
    setShowOrder(false);
    if (activeId) api(`/api/conversations/${activeId}/cart`, { method: "DELETE" }).catch(() => undefined);
  }

  async function confirmOrder() {
    if (!customer || !activeId || !cart.length) return;
    try {
      const created = await api<Order>("/api/orders", {
        method: "POST",
        body: JSON.stringify({
          customer_id: customer.customer_id,
          conversation_id: activeId,
          items: cart.map((item) => ({
            itemcode: item.itemcode,
            itemname: item.itemname,
            quantity: item.quantity,
            unit_price: item.unit_price,
          })),
          payment_method: payment,
          delivery_address: address,
          send_confirmation: true,
          order_status: "Confirmed",
        }),
      });
      setCart([]);
      setShowOrder(false);
      api(`/api/conversations/${activeId}/cart`, { method: "DELETE" }).catch(() => undefined);
      if (created.erp_post_status === "FAILED") {
        setError(created.erp_post_error || "Order saved, but website order failed.");
      }
      loadThread(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm order");
    }
  }

  async function saveCustomer() {
    if (!customer) return;
    const updated = await api<Customer>(`/api/customers/${customer.customer_id}`, {
      method: "PUT",
      body: JSON.stringify(customer),
    });
    setCustomer(updated);
  }

  async function assignChat(userId: number | null) {
    if (!active) return;
    try {
      await api(`/api/conversations/${active.conversation_id}/assign`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
      await loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign failed");
    }
  }

  async function copyMessage(message: Message) {
    const text = copyTextFor(message);
    try {
      await navigator.clipboard.writeText(text);
      setMenuMessage(null);
      setConfirmDelete(false);
    } catch {
      setError("Could not copy this message");
    }
  }

  async function sendShopLocation() {
    setShowLocation(false);
    await send({
      message_type: "location",
      latitude: SHOP_LOCATION.latitude,
      longitude: SHOP_LOCATION.longitude,
      location_name: SHOP_LOCATION.location_name,
      location_address: "West Bay, Doha, Qatar",
    }, { busy: "Sending location…" });
  }

  function sendMyLocation() {
    if (!navigator.geolocation) {
      setError("This browser cannot share location.");
      return;
    }
    setShowLocation(false);
    if (!beginSend("Sending location…")) return;
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          await send({
            message_type: "location",
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            location_name: "My location",
          }, { busy: false });
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not send location");
        } finally {
          endSend();
        }
      },
      () => {
        endSend();
        setError("Location permission was denied.");
      },
      { enableHighAccuracy: true, timeout: 12000 },
    );
  }

  async function reloadNotes(customerId: number) {
    const noteRows = await api<{ note_id: number; note_text: string }[]>(`/api/customers/${customerId}/notes`);
    setNotes(noteRows);
  }

  async function addNote() {
    if (!customer || !noteDraft.trim()) return;
    try {
      await api(`/api/customers/${customer.customer_id}/notes`, {
        method: "POST",
        body: JSON.stringify({ note_text: noteDraft }),
      });
      setNoteDraft("");
      await reloadNotes(customer.customer_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save note");
    }
  }

  async function saveNoteEdit(noteId: number) {
    if (!customer || !editingNoteText.trim()) return;
    try {
      await api(`/api/customers/${customer.customer_id}/notes/${noteId}`, {
        method: "PUT",
        body: JSON.stringify({ note_text: editingNoteText }),
      });
      setEditingNoteId(null);
      setEditingNoteText("");
      await reloadNotes(customer.customer_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update note");
    }
  }

  async function deleteNote(noteId: number) {
    if (!customer) return;
    if (!window.confirm("Delete this note?")) return;
    try {
      await api(`/api/customers/${customer.customer_id}/notes/${noteId}`, { method: "DELETE" });
      if (editingNoteId === noteId) {
        setEditingNoteId(null);
        setEditingNoteText("");
      }
      await reloadNotes(customer.customer_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete note");
    }
  }

  async function sendCatalog() {
    await send({
      text: "MamaHub catalog: Hot Wheels, dolls, puzzles, outdoor toys, and party items. Tell us the age and we will suggest products.",
      message_type: "text",
    });
  }

  function filterCount(id: string) {
    if (id === "all") return counts.all;
    if (id === "unread") return counts.unread;
    if (id === "open") return counts.open;
    if (id === "pending") return counts.pending;
    if (id === "starred") return counts.starred;
    return 0;
  }

  return (
    <AppShell>
      <div className="inbox-layout" data-pane={pane}>
        <section className="inbox-list">
          <div className="inbox-toolbar">
            <div className="inbox-toolbar-row">
              <label className="inbox-search">
                <span>
                  <Icon name="search" className="size-4" />
                </span>
                <input
                  className="inbox-field"
                  placeholder="Search name, number, message…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadConversations()}
                />
              </label>
              <button type="button" className="crm-icon-btn" aria-label="Refresh chats" onClick={loadConversations}>
                <Icon name="refresh" />
              </button>
              <button type="button" className="btn-primary" onClick={() => setShowNewChat((v) => !v)}>
                New
              </button>
            </div>
            {showNewChat && (
              <form onSubmit={startChat} className="inbox-sheet" style={{ margin: 0 }}>
                <div className="inbox-label">
                  WhatsApp number
                  <input className="inbox-field" placeholder="974xxxxxxxx" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} />
                </div>
                <div className="inbox-label">
                  Name (optional)
                  <input className="inbox-field" placeholder="Customer name" value={newName} onChange={(e) => setNewName(e.target.value)} />
                </div>
                <button type="submit" className="btn-primary w-full">Start chat</button>
              </form>
            )}
            <div className="inbox-filters">
              {FILTERS.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setFilter(item.id)}
                  className={`chip ${filter === item.id ? "is-active" : ""}`}
                >
                  {item.label}
                  {["all", "unread", "open", "pending"].includes(item.id) ? ` (${filterCount(item.id)})` : ""}
                </button>
              ))}
            </div>
          </div>
          <div className="scroll-pane flex-1">
            {conversations.map((row) => (
              <button
                key={row.conversation_id}
                type="button"
                onClick={() => {
                  setActiveId(row.conversation_id);
                  setOpenConversation(row.conversation_id);
                  setPane("chat");
                }}
                className={`inbox-thread${activeId === row.conversation_id ? " is-active" : ""}`}
              >
                <div className="inbox-avatar">
                  {row.profile_image_url ? (
                    <img src={row.profile_image_url} alt="" />
                  ) : (
                    initials(row.customer_name || row.whatsapp_number)
                  )}
                  <span className="inbox-wa">
                    <Icon name="whatsapp" />
                  </span>
                </div>
                <div className="inbox-thread-copy">
                  <div className="inbox-thread-top">
                    <div className="inbox-thread-name">{row.customer_name}</div>
                    <div className="inbox-thread-time">{formatTime(row.last_message_at)}</div>
                  </div>
                  <div className="inbox-thread-mid">
                    <div className="inbox-thread-preview">{row.last_message_text}</div>
                    {row.unread_count > 0 && <span className="inbox-unread">{row.unread_count}</span>}
                  </div>
                  <div className="inbox-thread-meta">
                    {row.ad_referral ? "Facebook Ad · " : ""}{row.status}{row.assigned_user_name ? ` · ${row.assigned_user_name}` : ""}
                  </div>
                </div>
              </button>
            ))}
            {!conversations.length && (
              <div className="inbox-empty">
                <strong>No chats yet</strong>
                <p>Incoming WhatsApp messages appear here, or tap New to start one.</p>
              </div>
            )}
          </div>
        </section>

        <section className="inbox-chat">
          <header className="inbox-head">
            <div className="inbox-head-user">
              <button type="button" className="crm-icon-btn inbox-back" aria-label="Back to chats" onClick={() => setPane("list")}>
                <Icon name="back" />
              </button>
              {active && (
                <Avatar
                  name={active.customer_name || active.whatsapp_number}
                  image={active.profile_image_url}
                />
              )}
              <div className="inbox-head-copy">
                <div className="inbox-head-name">
                  <span>{active?.customer_name || "Select a chat"}</span>
                  {active && isNewCustomer && <span className="tag bg-sky-100 text-sky-700">New</span>}
                  {active?.ad_referral && <span className="tag bg-blue-100 text-blue-700">Facebook Ad</span>}
                  {aiAutoReply && <span className="tag bg-emerald-100 text-emerald-700">AI on</span>}
                </div>
                <div className="inbox-head-sub">{active?.whatsapp_number || "Choose a conversation from the list"}</div>
              </div>
            </div>
            {active && (
              <div className="inbox-head-actions">
                <select
                  className="inbox-select"
                  value={active.status}
                  onChange={(e) => api(`/api/conversations/${active.conversation_id}/status`, { method: "PATCH", body: JSON.stringify({ status: e.target.value }) }).then(() => loadConversations())}
                >
                  {["OPEN", "PENDING", "RESOLVED", "CLOSED"].map((status) => <option key={status}>{status}</option>)}
                </select>
                <button
                  type="button"
                  className={`crm-icon-btn${active.is_starred ? " is-starred" : ""}`}
                  aria-label={active.is_starred ? "Unstar chat" : "Star chat"}
                  onClick={toggleStar}
                >
                  <Icon name="star" />
                </button>
                <button
                  type="button"
                  className={`crm-icon-btn${showThreadSearch ? " is-active" : ""}`}
                  aria-label="Search this chat"
                  onClick={() => setShowThreadSearch((v) => !v)}
                >
                  <Icon name="search" />
                </button>
                <button
                  type="button"
                  className="crm-icon-btn inbox-cart-open"
                  aria-label={cart.length ? `Open cart, ${cart.length} items` : "Open cart"}
                  onClick={() => { setShowOrder(true); setPane("details"); }}
                >
                  <Icon name="orders" />
                  {cart.length > 0 && <span className="inbox-cart-badge">{cart.length}</span>}
                </button>
                <button type="button" className="crm-icon-btn" aria-label="Customer profile" onClick={() => { setTab("details"); setPane("details"); }}>
                  <Icon name="user" />
                </button>
                <select
                  className="inbox-select inbox-assign-select"
                  aria-label="Assign chat"
                  value={active.assigned_user_id || ""}
                  onChange={(e) => assignChat(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">Unassigned</option>
                  {active.assigned_user_id && !agents.some((agent) => agent.user_id === active.assigned_user_id) ? (
                    <option value={active.assigned_user_id}>{active.assigned_user_name || "Assigned"}</option>
                  ) : null}
                  {agents.map((agent) => (
                    <option key={agent.user_id} value={agent.user_id}>{agent.full_name}</option>
                  ))}
                </select>
              </div>
            )}
          </header>
          {showThreadSearch && active && (
            <div className="inbox-thread-search">
              <label className="inbox-search">
                <span><Icon name="search" className="size-4" /></span>
                <input
                  autoFocus
                  placeholder="Search this chat…"
                  value={threadQuery}
                  onChange={(e) => { setThreadQuery(e.target.value); setThreadMatch(0); }}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setShowThreadSearch(false);
                    if (e.key === "Enter" && threadHits.length) {
                      e.preventDefault();
                      setThreadMatch((i) => (i + (e.shiftKey ? threadHits.length - 1 : 1)) % threadHits.length);
                    }
                  }}
                />
              </label>
              <span className="inbox-thread-search-count">
                {threadQuery.trim() ? `${threadHits.length ? threadMatch + 1 : 0}/${threadHits.length}` : ""}
              </span>
              <button type="button" className="crm-icon-btn" aria-label="Previous match" disabled={!threadHits.length} onClick={() => setThreadMatch((i) => (i + threadHits.length - 1) % threadHits.length)}>‹</button>
              <button type="button" className="crm-icon-btn" aria-label="Next match" disabled={!threadHits.length} onClick={() => setThreadMatch((i) => (i + 1) % threadHits.length)}>›</button>
              <button type="button" className="crm-icon-btn" aria-label="Close search" onClick={() => { setShowThreadSearch(false); setThreadQuery(""); }}>
                <Icon name="close" />
              </button>
            </div>
          )}
          <div className="scroll-pane inbox-messages" ref={messagesPane}>
            {error && <p className="inbox-sheet" style={{ color: "#b42318" }}>{error}</p>}
            {!active && (
              <div className="inbox-empty">
                <strong>Select a chat</strong>
                <p>Pick a conversation to read and reply.</p>
              </div>
            )}
            {active?.ad_referral && <AdCard ad={active.ad_referral} />}
            {messages.map((message) => {
              const mine = message.sender_type !== "CUSTOMER";
              const failed = message.status === "FAILED";
              const deleted = message.status === "DELETED";
              const showMessageAd = Boolean(message.referral?.image_url || message.referral?.headline) && !active?.ad_referral;
              const hit = threadHits.some((row) => row.id === message.id);
              const currentHit = threadHits[threadMatch]?.id === message.id;
              return (
                <div
                  key={message.id}
                  id={`msg-${message.id}`}
                  className={`chat-row ${mine ? "is-mine" : "is-theirs"}${hit ? " is-search-hit" : ""}${currentHit ? " is-search-current" : ""}`}
                >
                  <div
                    className={`chat-bubble${failed ? " is-failed" : ""}${deleted ? " is-deleted" : ""}`}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      openMessageMenu(message);
                    }}
                    onTouchStart={() => startPress(message)}
                    onTouchEnd={cancelPress}
                    onTouchMove={cancelPress}
                    onTouchCancel={cancelPress}
                  >
                    {deleted ? (
                      <div className="chat-deleted-text">This message was deleted</div>
                    ) : (
                      <>
                        {message.reply_to_text ? (
                          <button
                            type="button"
                            className="chat-quote"
                            onClick={() => jumpToMessage(message.reply_to_id)}
                          >
                            {message.reply_to_text}
                          </button>
                        ) : null}
                        {showMessageAd && message.referral ? (
                          <div className="inbox-ad-inline">
                            <div className="inbox-ad-kicker">Facebook ad</div>
                            {message.referral.image_url ? <img className="chat-media inbox-ad-image" src={mediaSrc(message.referral.image_url)} alt="" /> : null}
                            {message.referral.headline ? <div className="inbox-ad-title">{message.referral.headline}</div> : null}
                          </div>
                        ) : null}
                        {message.message_type === "audio" && message.media_url ? (
                          <audio className="chat-audio" controls src={mediaSrc(message.media_url)} />
                        ) : message.message_type === "video" && message.media_url ? (
                          <video className="chat-media" controls src={mediaSrc(message.media_url)} playsInline />
                        ) : message.message_type === "image" && message.media_url ? (
                          <img className="chat-media" src={mediaSrc(message.media_url)} alt="" />
                        ) : message.message_type === "sticker" && message.media_url ? (
                          <img className="chat-media chat-sticker" src={mediaSrc(message.media_url)} alt="" />
                        ) : message.message_type === "location" && message.latitude && message.longitude ? (
                          <a className="chat-location" href={mapsLink(message.latitude, message.longitude)} target="_blank" rel="noreferrer">
                            <span className="chat-location-pin" aria-hidden><Icon name="pin" /></span>
                            <span className="chat-location-copy">
                              <strong>{message.message_text || "Location"}</strong>
                              <em>Open in Maps</em>
                            </span>
                          </a>
                        ) : (
                          <div className="whitespace-pre-wrap">{message.message_text || `[${message.message_type}]`}</div>
                        )}
                        {failed && (
                          <div className="chat-fail">{message.error_message || "Not delivered"} · send a Template</div>
                        )}
                        {message.media_url && !["audio", "image", "video", "sticker"].includes(message.message_type) && (
                          <a className="mt-1 block text-xs text-[var(--accent)]" href={mediaSrc(message.media_url)} target="_blank">Open media</a>
                        )}
                      </>
                    )}
                    <div className="chat-bubble-foot">
                      {!deleted && (
                        <button
                          type="button"
                          className="chat-more"
                          aria-label="Message actions"
                          onClick={() => openMessageMenu(message)}
                        >
                          ⋯
                        </button>
                      )}
                      <div className={`chat-meta${failed ? " is-failed" : ""}`}>
                        <span>{formatTime(message.created_at)}</span>
                        {message.edited && !deleted && <span>edited</span>}
                        {message.sender_type === "AI" && <span>AI</span>}
                        {mine && !deleted && statusTicks(message.status)}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>
          {aiText && (
            <div className="inbox-sheet inbox-ai-reply">
              <div className="inbox-ai-reply-label">AI suggested reply</div>
              <div className="inbox-ai-reply-text">{aiText}</div>
              <div className="inbox-ai-reply-actions">
                <button className="btn-primary" onClick={() => send({ text: aiText, message_type: "text" }).then(() => setAiText(""))}>Send</button>
                <button type="button" onClick={() => setAiText("")}>Dismiss</button>
              </div>
            </div>
          )}
          {showProducts && (
            <div className="inbox-sheet inbox-sheet-products">
              <div className="inbox-products-tools">
                <div className="inbox-products-head">
                  <div className="inbox-products-title">Products</div>
                  <button
                    type="button"
                    className="crm-icon-btn inbox-products-close"
                    aria-label="Close product search"
                    onClick={() => setShowProducts(false)}
                  >
                    <Icon name="close" />
                  </button>
                </div>
                <div className="inbox-products-search-row">
                  <label className="inbox-products-search">
                    <Icon name="search" className="size-4" />
                    <input
                      className="inbox-field"
                      placeholder="Search products…"
                      value={productQuery}
                      onChange={(e) => setProductQuery(e.target.value)}
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Escape") setShowProducts(false);
                      }}
                    />
                  </label>
                </div>
                <ProductFilters
                  categories={productFilters.categories}
                  ages={productFilters.ages}
                  category={productCategory}
                  age={productAge}
                  collection={productCollection}
                  inStock={productInStock}
                  onCategory={setProductCategory}
                  onAge={setProductAge}
                  onCollection={setProductCollection}
                  onInStock={setProductInStock}
                />
              </div>
              <div className="inbox-sheet-body">
              {products.length === 0 && (
                <p className="inbox-empty" style={{ minBlockSize: "80px", padding: 12 }}>No products found. Try another name or filter.</p>
              )}
              {picked.length > 0 && (
                <div className="inbox-pick-bar">
                  <span>{picked.length} selected</span>
                  <div className="inbox-pick-actions">
                    <button type="button" className="btn-ghost" disabled={Boolean(sendingLabel)} onClick={() => sendPicked(true)}>Send images</button>
                    <button type="button" className="btn-primary" disabled={Boolean(sendingLabel)} onClick={() => sendPicked(false)}>Send catalog</button>
                  </div>
                </div>
              )}
              <div className="product-grid">
                {products.map((product, index) => (
                  <ProductTile
                    key={`${product.itemcode}-${index}`}
                    product={product}
                    picked={picked.some((row) => row.itemcode === product.itemcode)}
                    canPick={picked.length < 10}
                    collection={productCollection}
                    onToggle={() => togglePicked(product)}
                    onAdd={() => addToCart(product)}
                    onSend={() => sendProductToChat(product)}
                    sending={Boolean(sendingLabel) || sendingSku === product.itemcode}
                  />
                ))}
              </div>
              </div>
            </div>
          )}
          {showReplies && (
            <div className="inbox-sheet">
              <div className="inbox-sheet-search">
                <div className="inbox-sheet-title">Quick replies</div>
                <button type="button" className="crm-icon-btn" aria-label="Close quick replies" onClick={() => setShowReplies(false)}>
                  <Icon name="close" />
                </button>
              </div>
              <div className="inbox-sheet-body">
                {replies.map((reply) => (
                  <button key={reply.reply_id} className="chip mr-2 mt-1" onClick={() => send({ text: reply.body, message_type: "text" }).then(() => setShowReplies(false))}>
                    {reply.shortcut}
                  </button>
                ))}
              </div>
            </div>
          )}
          {showTemplates && (
            <div className="inbox-sheet">
              <div className="inbox-sheet-search">
                <div className="inbox-sheet-title">Templates</div>
                <button type="button" className="crm-icon-btn" aria-label="Close templates" onClick={() => setShowTemplates(false)}>
                  <Icon name="close" />
                </button>
              </div>
              <div className="inbox-sheet-body">
                {templates.map((tpl) => (
                  <button key={tpl.template_id} className="chip mr-2 mt-1" onClick={() => send({ message_type: "template", template_name: tpl.template_name, language: tpl.language }).then(() => setShowTemplates(false))}>
                    {tpl.template_name}
                  </button>
                ))}
              </div>
            </div>
          )}
          <form onSubmit={onSend} className="inbox-composer">
            <div className="inbox-composer-tools">
              <button type="button" className="crm-icon-btn tool-emoji" aria-label="Emoji" onClick={() => setShowEmoji((v) => !v)}><Icon name="emoji" /></button>
              <button type="button" className="crm-icon-btn tool-file" aria-label="Attach file" onClick={() => fileInput.current?.click()}><Icon name="clip" /></button>
              <button type="button" className="crm-icon-btn tool-image" aria-label="Attach image" onClick={() => imageInput.current?.click()}><Icon name="image" /></button>
              <button type="button" className="crm-icon-btn tool-pdf" aria-label="Attach PDF" onClick={() => pdfInput.current?.click()}><Icon name="pdf" /></button>
              <button type="button" className={`crm-icon-btn tool-location${showLocation ? " is-active" : ""}`} aria-label="Send location" onClick={() => setShowLocation((v) => !v)}><Icon name="pin" /></button>
              <button type="button" className="btn-ghost text-xs tool-product" onClick={() => setShowProducts((v) => !v)}>+ Product</button>
              <button type="button" className="btn-ghost text-xs tool-reply" onClick={() => setShowReplies((v) => !v)}>Quick Reply</button>
              <button type="button" className="btn-ghost text-xs tool-template" onClick={() => setShowTemplates((v) => !v)}>Template</button>
              <button type="button" className="btn-ghost text-xs tool-ai" onClick={suggestAi}>+ AI draft</button>
            </div>
            {showEmoji && (
              <div className="flex flex-wrap gap-1">
                {EMOJIS.map((emoji) => (
                  <button type="button" key={emoji} onClick={() => setDraft((v) => v + emoji)}>{emoji}</button>
                ))}
              </div>
            )}
            {showLocation && (
              <div className="inbox-location-sheet">
                <button type="button" className="btn-ghost" onClick={sendMyLocation}>Send my location</button>
                <button type="button" className="btn-primary" onClick={sendShopLocation}>Send shop (West Bay)</button>
              </div>
            )}
            {(replyTo || editMessage) && (
              <div className={`inbox-reply-bar${editMessage ? " is-edit" : ""}`}>
                <div className="inbox-reply-copy">
                  <strong>{editMessage ? "Edit message" : "Replying"}</strong>
                  <span>{editMessage ? messagePreview(editMessage) : replyTo ? messagePreview(replyTo) : ""}</span>
                </div>
                <button type="button" className="crm-icon-btn" aria-label="Cancel" onClick={cancelComposerAction}>
                  <Icon name="close" />
                </button>
              </div>
            )}
            <div className={`inbox-composer-row${editMessage ? " is-edit" : ""}`}>
              <textarea
                placeholder={editMessage ? "Edit message…" : "Type a message…"}
                rows={1}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  if (e.target.value.startsWith("/")) setShowReplies(true);
                }}
              />
              {!editMessage && (
                <button
                  type="button"
                  className={`crm-icon-btn${recording ? " is-recording" : ""}`}
                  aria-label={recording ? "Stop voice note" : "Record voice note"}
                  onClick={toggleVoice}
                >
                  <Icon name="mic" />
                </button>
              )}
              <button type="submit" className="btn-primary inbox-send-btn" disabled={Boolean(sendingLabel)} aria-label={editMessage ? "Save edit" : "Send"}>
                <Icon name="send" className="size-4" />
              </button>
            </div>
            <input ref={imageInput} type="file" accept="image/*" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadFile(file, "image"); }} />
            <input ref={pdfInput} type="file" accept=".pdf,application/pdf" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadFile(file, "document"); }} />
            <input ref={fileInput} type="file" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadFile(file, "document"); }} />
          </form>
          <dialog
            ref={menuRef}
            className="chat-msg-dialog"
            closedby="any"
            aria-labelledby="chat-msg-dialog-title"
            onCancel={() => setMenuMessage(null)}
          >
            {menuMessage && (
              <>
                <div className="chat-msg-preview" id="chat-msg-dialog-title">
                  {messagePreview(menuMessage)}
                </div>
                {confirmDelete ? (
                  <div className="chat-msg-confirm">
                    <p>
                      {menuMessage.sender_type === "CUSTOMER"
                        ? "Remove this message from the inbox?"
                        : "Delete this message for everyone on WhatsApp?"}
                    </p>
                    <div className="chat-msg-confirm-actions">
                      <button type="button" className="btn-ghost" onClick={() => setConfirmDelete(false)}>Cancel</button>
                      <button type="button" className="btn-primary chat-msg-danger-btn" onClick={() => removeMessage(menuMessage)}>Delete</button>
                    </div>
                  </div>
                ) : (
                  <div className="chat-msg-actions">
                    <button type="button" className="chat-msg-action" onClick={() => copyMessage(menuMessage)}>
                      <Icon name="copy" />
                      Copy
                    </button>
                    <button type="button" className="chat-msg-action" onClick={() => startReply(menuMessage)}>
                      <Icon name="replies" />
                      Reply
                    </button>
                    {menuMessage.sender_type !== "CUSTOMER" && menuMessage.message_type === "text" && (
                      <button type="button" className="chat-msg-action" onClick={() => startEdit(menuMessage)}>
                        <Icon name="edit" />
                        Edit
                      </button>
                    )}
                    <button type="button" className="chat-msg-action is-danger" onClick={() => setConfirmDelete(true)}>
                      <Icon name="trash" />
                      Delete
                    </button>
                  </div>
                )}
              </>
            )}
          </dialog>
        </section>

        <aside className="inbox-details">
          <div className="inbox-details-tabs">
            <button type="button" className="crm-icon-btn inbox-details-close" aria-label="Close customer panel" onClick={() => setPane(activeId ? "chat" : "list")}>
              <Icon name="close" />
            </button>
            {RIGHT_TABS.map((item) => (
              <button key={item.id} onClick={() => setTab(item.id)} className={`chip ${tab === item.id ? "is-active" : ""}`}>{item.label}</button>
            ))}
            <button
              type="button"
              className={`chip inbox-cart-tab${showOrder ? " is-active" : ""}`}
              onClick={() => setShowOrder(true)}
            >
              Cart{cart.length ? ` (${cart.length})` : ""}
            </button>
          </div>
          <div className="scroll-pane inbox-details-body">
            {tab === "details" && customer && (
              <div>
                <div className="inbox-profile">
                  <button type="button" className="inbox-profile-photo" onClick={() => photoInput.current?.click()}>
                    <Avatar name={customer.customer_name} image={customer.profile_image_url} />
                  </button>
                  <input
                    ref={photoInput}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) uploadPhoto(file);
                      e.target.value = "";
                    }}
                  />
                  <div>
                    <div className="font-semibold">{customer.customer_name}</div>
                    <div className="inbox-head-sub">{customer.whatsapp_number}</div>
                    <button type="button" className="inbox-photo-link" onClick={() => photoInput.current?.click()}>
                      {customer.profile_image_url ? "Change photo" : "Add photo"}
                    </button>
                  </div>
                </div>
                <dl className="inbox-meta">
                  {active?.ad_referral && (
                    <div className="inbox-ad-panel">
                      <div className="inbox-section-label">Facebook ad</div>
                      {active.ad_referral.image_url ? <img className="inbox-ad-image" src={mediaSrc(active.ad_referral.image_url)} alt="" /> : null}
                      <div className="font-medium">{active.ad_referral.headline || "Click to WhatsApp ad"}</div>
                      {active.ad_referral.body ? <div className="inbox-head-sub">{active.ad_referral.body}</div> : null}
                    </div>
                  )}
                  <div className="inbox-meta-row"><dt>Code</dt><dd>{customer.customer_code || "—"}</dd></div>
                  <div className="inbox-meta-row"><dt>Email</dt><dd>{customer.email || "—"}</dd></div>
                  <div className="inbox-meta-row"><dt>Type</dt><dd>{customer.customer_type || "Retail"}</dd></div>
                  <div className="inbox-meta-row"><dt>Location</dt><dd>{customer.location_label || customer.address || "—"}</dd></div>
                  <div className="inbox-meta-row"><dt>Orders</dt><dd>{customer.total_orders}</dd></div>
                  <div className="inbox-meta-row"><dt>Purchases</dt><dd>QAR {customer.total_purchases.toFixed(2)}</dd></div>
                  <div className="inbox-meta-row"><dt>Last purchase</dt><dd>{customer.last_purchase_date ? formatTime(customer.last_purchase_date) : "—"}</dd></div>
                  <div className="inbox-meta-row"><dt>Outstanding</dt><dd className="font-semibold text-[var(--accent)]">QAR {customer.outstanding_balance.toFixed(2)}</dd></div>
                </dl>
                {customer.tags?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {customer.tags.map((tag) => (
                      <span key={tag} className={`tag ${tagClass(tag)}`}>{tag}</span>
                    ))}
                  </div>
                )}
                <div className="inbox-edit">
                  <div className="inbox-section-label">Quick actions</div>
                  <div className="inbox-actions">
                    <button type="button" className="btn-ghost" onClick={() => setShowOrder(true)}>
                      {cart.length ? `Open cart (${cart.length})` : "Create order"}
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setTab("orders")}>View orders</button>
                    <button type="button" className="btn-ghost" onClick={sendCatalog}>Send catalog</button>
                    <button type="button" className="btn-ghost" onClick={() => setTab("notes")}>Add note</button>
                  </div>
                {orders.length > 0 && (
                  <div>
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Recent orders</div>
                    {orders.slice(0, 4).map((order) => (
                      <div key={order.order_id} className="mb-2 flex items-center justify-between rounded-xl bg-[var(--bg)] px-3 py-2">
                        <div>
                          <div className="font-medium">{order.order_number}</div>
                          <div className="text-xs text-[var(--muted)]">{formatTime(order.order_date)}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs font-semibold">QAR {order.total_amount.toFixed(2)}</div>
                          <span className="tag bg-[var(--mint)] text-[var(--forest)]">{order.order_status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                  <div className="inbox-section-label">Edit customer</div>
                  <label className="inbox-label">
                    Email
                    <input className="inbox-field" value={customer.email || ""} onChange={(e) => setCustomer({ ...customer, email: e.target.value })} />
                  </label>
                  <label className="inbox-label">
                    Address
                    <input className="inbox-field" value={customer.address || ""} onChange={(e) => setCustomer({ ...customer, address: e.target.value })} />
                  </label>
                  <button type="button" onClick={saveCustomer} className="btn-primary inbox-save">Save customer</button>
                </div>
              </div>
            )}
            {tab === "orders" && orders.map((order) => (
              <div key={order.order_id} className="mb-3 rounded-xl border border-[var(--line)] p-3">
                <div className="font-medium">{order.order_number}</div>
                <div className="text-xs text-[var(--muted)]">{order.order_status} · QAR {order.total_amount.toFixed(2)}</div>
                <div className="inbox-order-erp">
                  {order.mh_order_id || order.erp_post_status === "ORDERED"
                    ? `Website order ${order.order_number}`
                    : order.erp_bill_no
                      ? `ERP bill ${order.erp_bill_no}`
                      : order.erp_post_status === "FAILED"
                        ? `Website order failed${order.erp_post_error ? `: ${order.erp_post_error}` : ""}`
                        : "Website order pending"}
                </div>
                {!order.mh_order_id && order.erp_post_status !== "ORDERED" && order.order_status !== "Cancelled" && (
                  <button
                    type="button"
                    className="btn-ghost inbox-erp-retry"
                    onClick={() => api<Order>(`/api/orders/${order.order_id}/sync-erp`, { method: "POST" }).then((updated) => {
                      setOrders((prev) => prev.map((row) => (row.order_id === updated.order_id ? updated : row)));
                    }).catch((err) => setError(err instanceof Error ? err.message : "Website order sync failed"))}
                  >
                    Create website order
                  </button>
                )}
                {!order.erp_bill_no && order.order_status !== "Cancelled" && (
                  <button
                    type="button"
                    className="btn-ghost inbox-erp-retry"
                    onClick={() => {
                      if (!window.confirm(`Remove ${order.order_number}? Only allowed before a sales invoice is created.`)) return;
                      api<Order>(`/api/orders/${order.order_id}/remove`, { method: "POST" }).then((updated) => {
                        setOrders((prev) => prev.map((row) => (row.order_id === updated.order_id ? updated : row)));
                      }).catch((err) => setError(err instanceof Error ? err.message : "Could not remove order"));
                    }}
                  >
                    Remove order
                  </button>
                )}
              </div>
            ))}
            {tab === "products" && (
              <div className="inbox-products-pane">
                <div className="inbox-products-tools">
                  <label className="inbox-products-search">
                    <Icon name="search" className="size-4" />
                    <input className="inbox-field" placeholder="Search products…" value={productQuery} onChange={(e) => setProductQuery(e.target.value)} />
                  </label>
                  <ProductFilters
                    categories={productFilters.categories}
                    ages={productFilters.ages}
                    category={productCategory}
                    age={productAge}
                    collection={productCollection}
                    inStock={productInStock}
                    onCategory={setProductCategory}
                    onAge={setProductAge}
                    onCollection={setProductCollection}
                    onInStock={setProductInStock}
                  />
                </div>
                {products.length === 0 && (
                  <p className="inbox-empty" style={{ minBlockSize: "80px", padding: 12 }}>No products found. Try another name or filter.</p>
                )}
                {picked.length > 0 && (
                  <div className="inbox-pick-bar">
                    <span>{picked.length} selected</span>
                    <div className="inbox-pick-actions">
                      <button type="button" className="btn-ghost" disabled={Boolean(sendingLabel)} onClick={() => sendPicked(true)}>Send images</button>
                      <button type="button" className="btn-primary" disabled={Boolean(sendingLabel)} onClick={() => sendPicked(false)}>Send catalog</button>
                    </div>
                  </div>
                )}
              <div className="product-grid">
                {products.map((product, index) => (
                  <ProductTile
                    key={`${product.itemcode}-${index}`}
                      product={product}
                      picked={picked.some((row) => row.itemcode === product.itemcode)}
                      canPick={picked.length < 10}
                      collection={productCollection}
                      onToggle={() => togglePicked(product)}
                      onAdd={() => addToCart(product)}
                      onSend={() => sendProductToChat(product)}
                      sending={Boolean(sendingLabel) || sendingSku === product.itemcode}
                    />
                  ))}
                </div>
              </div>
            )}
            {tab === "notes" && (
              <div className="inbox-notes">
                <textarea className="inbox-field inbox-notes-draft" rows={2} placeholder="Add a note" value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} />
                <button type="button" className="btn-primary inbox-notes-save" onClick={addNote}>Save note</button>
                {notes.map((note) => (
                  <article key={note.note_id} className="inbox-note">
                    {editingNoteId === note.note_id ? (
                      <>
                        <textarea
                          className="inbox-field inbox-notes-draft"
                          rows={2}
                          value={editingNoteText}
                          onChange={(e) => setEditingNoteText(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Escape") {
                              setEditingNoteId(null);
                              setEditingNoteText("");
                            }
                          }}
                          autoFocus
                        />
                        <div className="inbox-note-actions">
                          <button type="button" className="btn-primary" onClick={() => saveNoteEdit(note.note_id)}>Save</button>
                          <button type="button" className="btn-ghost" onClick={() => { setEditingNoteId(null); setEditingNoteText(""); }}>Cancel</button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="inbox-note-text">{note.note_text}</p>
                        <div className="inbox-note-actions">
                          <button
                            type="button"
                            className="crm-icon-btn"
                            aria-label="Edit note"
                            onClick={() => {
                              setEditingNoteId(note.note_id);
                              setEditingNoteText(note.note_text);
                            }}
                          >
                            <Icon name="edit" />
                          </button>
                          <button
                            type="button"
                            className="crm-icon-btn"
                            aria-label="Delete note"
                            onClick={() => deleteNote(note.note_id)}
                          >
                            <Icon name="trash" />
                          </button>
                        </div>
                      </>
                    )}
                  </article>
                ))}
              </div>
            )}
            {tab === "history" && messages.slice().reverse().map((message) => (
              <p key={message.id} className="mb-2 text-xs"><strong>{message.sender_type}</strong> {message.message_text}</p>
            ))}
          </div>
          {showOrder && (
            <div className="inbox-cart">
              <div className="inbox-cart-head">
                <div className="inbox-cart-title">Order cart</div>
                <button type="button" className="crm-icon-btn" aria-label="Close cart" onClick={() => setShowOrder(false)}>
                  <Icon name="close" />
                </button>
              </div>
              <div className="inbox-cart-items">
                {cart.map((item) => (
                  <article key={item.itemcode} className="inbox-cart-item">
                    {item.image_url ? (
                      <img className="inbox-cart-photo" src={productImageSrc(item.image_url)} alt="" />
                    ) : (
                      <div className="inbox-cart-photo is-empty">No image</div>
                    )}
                    <div className="inbox-cart-copy">
                      <div className="inbox-cart-name">{prettyName(item.itemname)}</div>
                      <div className="inbox-cart-meta">QAR {item.unit_price.toFixed(2)} · {(item.quantity * item.unit_price).toFixed(2)}</div>
                    </div>
                    <div className="inbox-cart-qtybox">
                      <button type="button" aria-label="Decrease quantity" disabled={item.quantity <= 1} onClick={() => setCartQty(item.itemcode, item.quantity - 1)}>−</button>
                      <input
                        type="number"
                        min={1}
                        inputMode="numeric"
                        value={item.quantity}
                        onChange={(e) => setCartQty(item.itemcode, Number(e.target.value))}
                      />
                      <button type="button" aria-label="Increase quantity" onClick={() => setCartQty(item.itemcode, item.quantity + 1)}>+</button>
                    </div>
                    <button
                      type="button"
                      className="crm-icon-btn"
                      aria-label={`Remove ${prettyName(item.itemname)}`}
                      onClick={() => removeFromCart(item.itemcode)}
                    >
                      <Icon name="trash" />
                    </button>
                  </article>
                ))}
              </div>
              <div className="inbox-cart-checkout">
                <label className="inbox-cart-field">
                  Address
                  <input className="inbox-field" placeholder="Delivery address" value={address} onChange={(e) => setAddress(e.target.value)} />
                </label>
                <label className="inbox-cart-field">
                  Payment
                  <select className="inbox-select" value={payment} onChange={(e) => setPayment(e.target.value)}>
                    <option>Cash</option><option>Card</option><option>Tap</option><option>Bank Transfer</option>
                  </select>
                </label>
                <div className="inbox-cart-footer">
                  <div className="inbox-cart-total">Total QAR {cartTotal.toFixed(2)}</div>
                  <div className="inbox-cart-actions">
                    <button type="button" className="btn-ghost" onClick={cancelOrder}>Cancel order</button>
                    <button type="button" onClick={confirmOrder} className="btn-primary" disabled={!cart.length}>Order</button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </aside>
        {sendingLabel ? (
          <div className="inbox-send-overlay" role="status" aria-live="polite" aria-busy="true">
            <div className="inbox-send-overlay-card">
              <span className="inbox-send-spinner" aria-hidden />
              <strong>{sendingLabel}</strong>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}

export default function InboxPage() {
  return (
    <Suspense fallback={<BootSplash />}>
      <InboxInner />
    </Suspense>
  );
}
