import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useInboxWidget } from '../context/InboxWidgetContext'
import { useLocale } from '../i18n/LocaleContext'
import { getApiErrorMessage, getData, postData, postForm } from '../lib/api'
import { resolveMediaUrl } from '../lib/media'
import { storage } from '../lib/storage'
import type { InboxConversation, InboxMessage, NotificationItem } from '../types/api'
import { IconCamera, IconMic, IconPlus, IconSend, IconSmile } from './icons/Icons'

const EMOJIS = [
  '😀', '😁', '😂', '🤣', '😊', '😍', '😘', '😎', '🤩', '😇', '😉', '🙂',
  '🙌', '👏', '👍', '❤️', '🔥', '🎉', '🙏', '💯', '😢', '😮', '😡', '🤔',
  '😴', '🤝', '✅', '⭐', '📌', '📷', '📎', '🎵',
]

function formatMessageWhen(value?: string | null, locale: 'en' | 'ar' = 'en') {
  if (!value) return ''
  const raw = value.trim()
  const parsed = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? raw : raw.replace(' ', 'T'))
  if (Number.isNaN(parsed.getTime())) return raw
  return new Intl.DateTimeFormat(locale === 'ar' ? 'ar-QA' : 'en-GB', {
    timeZone: 'Asia/Qatar',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(parsed)
}

function isAudioFile(name?: string | null, mime?: string | null) {
  const n = (name || '').toLowerCase()
  const m = (mime || '').toLowerCase()
  return m.startsWith('audio/') || ['.webm', '.ogg', '.wav', '.mp3', '.m4a'].some((ext) => n.endsWith(ext))
}

function isVideoFile(name?: string | null, mime?: string | null) {
  const n = (name || '').toLowerCase()
  const m = (mime || '').toLowerCase()
  return m.startsWith('video/') || ['.mp4', '.webm', '.mov', '.m4v'].some((ext) => n.endsWith(ext))
}

export function InboxClearChatButton({ className }: { className?: string }) {
  const { t } = useLocale()
  const queryClient = useQueryClient()
  const { tab, conversationId } = useInboxWidget()
  const loggedIn = storage.hasSession()

  const { data: conversations = [] } = useQuery({
    queryKey: ['inbox-conversations'],
    queryFn: () => getData<InboxConversation[]>('/inbox/conversations'),
    enabled: loggedIn,
  })

  const clearChat = useMutation({
    mutationFn: (id: number) => postData(`/inbox/conversations/${id}/clear`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inbox-messages'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-conversations'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-unread'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-latest'] })
    },
  })

  const activeId = conversationId || (conversations.length === 1 ? conversations[0].conversation_id : null)
  if (tab !== 'chat' || !activeId) return null

  return (
    <button
      type="button"
      className={className}
      disabled={clearChat.isPending}
      onClick={() => {
        if (window.confirm(t.inbox.clearConfirm)) {
          clearChat.mutate(activeId)
        }
      }}
    >
      {clearChat.isPending ? '…' : t.inbox.clear}
    </button>
  )
}

export function InboxPanel() {
  const { t, locale } = useLocale()
  const queryClient = useQueryClient()
  const { tab, setTab, conversationId, setConversationId, closeInbox } = useInboxWidget()
  const loggedIn = storage.hasSession()
  const [draft, setDraft] = useState('')
  const [sendError, setSendError] = useState<string | null>(null)
  const [attachment, setAttachment] = useState<File | null>(null)
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [recording, setRecording] = useState(false)
  const [voiceReady, setVoiceReady] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const threadRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const composeRef = useRef<HTMLFormElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const { data: conversations = [] } = useQuery({
    queryKey: ['inbox-conversations'],
    queryFn: () => getData<InboxConversation[]>('/inbox/conversations'),
    enabled: loggedIn,
    refetchInterval: 8000,
  })

  const { data: messages = [] } = useQuery({
    queryKey: ['inbox-messages', conversationId],
    queryFn: () => getData<InboxMessage[]>('/inbox/messages', { conversation_id: conversationId }),
    enabled: loggedIn && !!conversationId,
    refetchInterval: conversationId ? 4000 : false,
  })

  const { data: notifications = [] } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => getData<NotificationItem[]>('/notifications'),
    enabled: loggedIn && tab === 'alerts',
  })

  const send = useMutation({
    mutationFn: () => {
      const text = draft.trim()
      if (attachment) {
        const form = new FormData()
        form.append('message_text', text)
        if (conversationId) form.append('conversation_id', String(conversationId))
        form.append('attachment', attachment)
        return postForm<InboxMessage>('/inbox/messages', form, 45_000)
      }
      return postData<InboxMessage>('/inbox/messages', {
        message_text: text,
        conversation_id: conversationId || undefined,
      })
    },
    onSuccess: (row) => {
      setDraft('')
      setAttachment(null)
      setVoiceReady(false)
      setEmojiOpen(false)
      setSendError(null)
      if (row.conversation_id) setConversationId(row.conversation_id)
      queryClient.invalidateQueries({ queryKey: ['inbox-conversations'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-messages'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-unread'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-latest'] })
    },
    onError: (error) => setSendError(getApiErrorMessage(error)),
  })

  const editMessage = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) =>
      postData(`/inbox/messages/${id}/edit`, { message_text: text }),
    onSuccess: () => {
      setEditingId(null)
      setEditDraft('')
      queryClient.invalidateQueries({ queryKey: ['inbox-messages'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-conversations'] })
    },
    onError: (error) => setSendError(getApiErrorMessage(error)),
  })

  const deleteMessage = useMutation({
    mutationFn: (id: number) => postData(`/inbox/messages/${id}/delete`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inbox-messages'] })
      queryClient.invalidateQueries({ queryKey: ['inbox-conversations'] })
    },
    onError: (error) => setSendError(getApiErrorMessage(error)),
  })

  useEffect(() => {
    if (!conversationId && conversations.length === 1) {
      setConversationId(conversations[0].conversation_id)
    }
  }, [conversations, conversationId, setConversationId])

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, conversationId])

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (composeRef.current && !composeRef.current.contains(event.target as Node)) {
        setEmojiOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [])

  useEffect(() => {
    return () => {
      const rec = recorderRef.current
      if (rec && rec.state === 'recording') rec.stop()
    }
  }, [])

  const selected = useMemo(
    () => conversations.find((c) => c.conversation_id === conversationId) || null,
    [conversations, conversationId],
  )

  const showList = conversations.length > 1 && !conversationId
  const canSend = Boolean(draft.trim() || attachment) && !send.isPending && !recording

  function pickFile(file?: File | null) {
    if (!file) return
    setAttachment(file)
    setVoiceReady(false)
    setSendError(null)
  }

  async function toggleVoice() {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop()
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setSendError(t.inbox.voice)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : ''
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        const ext = (recorder.mimeType || '').includes('mp4') ? 'm4a' : 'webm'
        setAttachment(new File([blob], `voice_note_${Date.now()}.${ext}`, { type: blob.type }))
        setVoiceReady(true)
        setRecording(false)
        recorderRef.current = null
      }
      recorder.start()
      recorderRef.current = recorder
      setRecording(true)
      setVoiceReady(false)
      setSendError(null)
    } catch {
      setSendError(t.inbox.voice)
    }
  }

  function submitCompose() {
    if (!canSend) return
    send.mutate()
  }

  if (!loggedIn) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
        <p className="text-sm text-slate-600">{t.account.signInInbox}</p>
        <Link
          to="/login"
          onClick={closeInbox}
          className="rounded-full bg-brand-accent px-4 py-2 text-sm font-semibold text-white"
        >
          {t.auth.signIn}
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 gap-1.5 border-b border-brand-border px-3 py-2">
        <button
          type="button"
          onClick={() => setTab('chat')}
          className={`flex-1 rounded-full px-3 py-1.5 text-xs font-semibold ${
            tab === 'chat' ? 'bg-brand-accent text-white' : 'bg-brand-cream text-slate-700'
          }`}
        >
          {t.inbox.messages}
        </button>
        <button
          type="button"
          onClick={() => setTab('alerts')}
          className={`flex-1 rounded-full px-3 py-1.5 text-xs font-semibold ${
            tab === 'alerts' ? 'bg-brand-accent text-white' : 'bg-brand-cream text-slate-700'
          }`}
        >
          {t.inbox.alerts}
        </button>
      </div>

      {tab === 'alerts' ? (
        <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {notifications.map((n) => (
            <li key={n.notification_id} className={n.is_read ? 'text-slate-500' : 'text-slate-800'}>
              <p className="text-sm font-semibold">{n.title}</p>
              {n.body ? <p className="mt-1 text-xs text-slate-500">{n.body}</p> : null}
              {n.created_at ? (
                <p className="mt-1 text-[10px] text-slate-400">{formatMessageWhen(n.created_at, locale)}</p>
              ) : null}
              {n.notification_type === 'ASSIST_CHAT' ? (
                <button
                  type="button"
                  className="mt-2 text-xs font-semibold text-brand-accent"
                  onClick={() => {
                    if (n.ref_entity_id) setConversationId(Number(n.ref_entity_id))
                    setTab('chat')
                  }}
                >
                  {t.inbox.messages}
                </button>
              ) : null}
            </li>
          ))}
          {!notifications.length ? (
            <li className="py-8 text-center text-sm text-slate-500">{t.account.noNotifications}</li>
          ) : null}
        </ul>
      ) : showList ? (
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {conversations.map((c) => (
            <li key={c.conversation_id}>
              <button
                type="button"
                onClick={() => setConversationId(c.conversation_id)}
                className="flex w-full flex-col items-start gap-1 px-4 py-3 text-start hover:bg-slate-50"
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-800">{c.display_name || t.inbox.mamahub}</span>
                  {c.unread_count > 0 ? (
                    <span className="rounded-full bg-brand-accent px-1.5 text-[10px] font-bold text-white">
                      {c.unread_count}
                    </span>
                  ) : null}
                </span>
                <span className="line-clamp-1 text-xs text-slate-500">{c.last_text || t.inbox.empty}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <>
          <div className="flex shrink-0 items-center gap-2 border-b border-brand-border px-3 py-2">
            {conversations.length > 1 ? (
              <button
                type="button"
                className="text-xs font-semibold text-brand-accent"
                onClick={() => setConversationId(null)}
              >
                {t.inbox.backToList}
              </button>
            ) : null}
            <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800">
              {selected?.display_name || t.inbox.mamahub}
            </p>
            <InboxClearChatButton className="shrink-0 rounded-full bg-brand-cream px-2.5 py-1 text-[11px] font-semibold text-brand-accent disabled:opacity-50" />
          </div>

          <div ref={threadRef} className="min-h-0 flex-1 space-y-2.5 overflow-y-auto bg-[#FFF8EE] px-3 py-3">
            {messages.map((m) => {
              const imageSrc = resolveMediaUrl(m.image_url)
              const fileSrc = resolveMediaUrl(m.file_url)
              return (
                <div key={m.message_id} className={`flex ${m.is_own ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-3 py-1.5 text-sm ${
                      m.is_own ? 'bg-brand-accent text-white' : 'bg-white text-slate-800 shadow-sm'
                    }`}
                  >
                    {imageSrc ? (
                      <a href={imageSrc} target="_blank" rel="noopener noreferrer">
                        <img src={imageSrc} alt={t.inbox.photo} className="mb-2 max-h-40 rounded-xl object-cover" />
                      </a>
                    ) : null}
                    {fileSrc && isAudioFile(m.file_name, m.file_mime) ? (
                      <audio className="mb-2 w-full" controls src={fileSrc} />
                    ) : null}
                    {fileSrc && isVideoFile(m.file_name, m.file_mime) && !isAudioFile(m.file_name, m.file_mime) ? (
                      <video className="mb-2 max-h-40 w-full rounded-xl" controls src={fileSrc} />
                    ) : null}
                    {fileSrc && !isAudioFile(m.file_name, m.file_mime) && !isVideoFile(m.file_name, m.file_mime) ? (
                      <a
                        href={fileSrc}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`mb-2 block text-xs underline ${m.is_own ? 'text-white' : 'text-brand-accent'}`}
                      >
                        {m.file_name || t.inbox.file}
                      </a>
                    ) : null}
                    {editingId === m.message_id ? (
                      <div className="space-y-2">
                        <textarea
                          value={editDraft}
                          onChange={(e) => setEditDraft(e.target.value)}
                          className="w-full rounded-xl border border-white/40 bg-white/15 px-3 py-2 text-sm text-white outline-none"
                          rows={3}
                        />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-brand-accent"
                            disabled={editMessage.isPending}
                            onClick={() => {
                              const text = editDraft.trim()
                              if (!text) {
                                setSendError(t.inbox.editEmpty)
                                return
                              }
                              editMessage.mutate({ id: m.message_id, text })
                            }}
                          >
                            {t.inbox.saveEdit}
                          </button>
                          <button
                            type="button"
                            className="rounded-full px-3 py-1 text-xs font-semibold text-white/90"
                            onClick={() => {
                              setEditingId(null)
                              setEditDraft('')
                            }}
                          >
                            {t.inbox.cancelEdit}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        {m.message_text ? <p className="whitespace-pre-wrap">{m.message_text}</p> : null}
                        {m.created_at || m.edited ? (
                          <p className={`mt-1 text-[10px] ${m.is_own ? 'text-white/80' : 'text-slate-400'}`}>
                            {[formatMessageWhen(m.created_at, locale), m.edited ? t.inbox.edited : '']
                              .filter(Boolean)
                              .join(' · ')}
                          </p>
                        ) : null}
                      </>
                    )}
                    {m.is_own && editingId !== m.message_id ? (
                      <div className="mt-1.5 flex gap-3 text-[11px] font-semibold text-white/90">
                        {m.message_text ? (
                          <button
                            type="button"
                            onClick={() => {
                              setEditingId(m.message_id)
                              setEditDraft(m.message_text || '')
                              setSendError(null)
                            }}
                          >
                            {t.inbox.edit}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(t.inbox.deleteConfirm)) {
                              deleteMessage.mutate(m.message_id)
                            }
                          }}
                        >
                          {t.inbox.delete}
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
              )
            })}
            {!messages.length ? (
              <p className="py-8 text-center text-xs text-slate-500">{t.inbox.empty}</p>
            ) : null}
          </div>

          <form
            ref={composeRef}
            className="relative shrink-0 border-t border-brand-border bg-white p-2.5"
            onSubmit={(e) => {
              e.preventDefault()
              submitCompose()
            }}
          >
            <input
              ref={fileRef}
              type="file"
              className="sr-only"
              accept="image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.zip,.rar,.7z,.ppt,.pptx,.mp3,.wav,.ogg,.m4a,.webm"
              onChange={(e) => {
                pickFile(e.target.files?.[0] || null)
                e.target.value = ''
              }}
            />
            <input
              ref={cameraRef}
              type="file"
              className="sr-only"
              accept="image/*"
              capture="environment"
              onChange={(e) => {
                pickFile(e.target.files?.[0] || null)
                e.target.value = ''
              }}
            />

            {emojiOpen ? (
              <div className="absolute inset-x-2 bottom-full mb-2 grid grid-cols-8 gap-1 rounded-2xl bg-white p-2 shadow-lg ring-1 ring-brand-border">
                {EMOJIS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    className="rounded-lg p-1 text-base hover:bg-brand-tint"
                    onClick={() => {
                      setDraft((value) => value + emoji)
                      setSendError(null)
                    }}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            ) : null}

            {attachment ? (
              <div className="mb-2 flex items-center justify-between gap-2 rounded-xl bg-[#FFF8EE] px-3 py-1.5 text-[11px] text-slate-600">
                <span className="truncate">
                  {voiceReady ? t.inbox.voiceReady : attachment.name} · {t.inbox.attachmentReady}
                </span>
                <button
                  type="button"
                  className="shrink-0 font-semibold text-brand-accent"
                  onClick={() => {
                    setAttachment(null)
                    setVoiceReady(false)
                  }}
                >
                  {t.inbox.removeAttachment}
                </button>
              </div>
            ) : null}
            {recording ? <p className="mb-2 text-[11px] font-semibold text-red-600">{t.inbox.recording}</p> : null}

            <div className="flex items-end gap-1">
              <button
                type="button"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-50 hover:text-brand-accent"
                aria-label={t.inbox.attach}
                onClick={() => fileRef.current?.click()}
              >
                <IconPlus size={18} />
              </button>
              <button
                type="button"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-50 hover:text-brand-accent"
                aria-label={t.inbox.camera}
                onClick={() => cameraRef.current?.click()}
              >
                <IconCamera size={18} />
              </button>
              <button
                type="button"
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full hover:bg-slate-50 ${
                  emojiOpen ? 'text-brand-accent' : 'text-slate-500 hover:text-brand-accent'
                }`}
                aria-label={t.inbox.emoji}
                aria-expanded={emojiOpen}
                onClick={() => setEmojiOpen((open) => !open)}
              >
                <IconSmile size={18} />
              </button>
              <label className="sr-only" htmlFor="inbox-widget-draft">
                {t.inbox.placeholder}
              </label>
              <textarea
                id="inbox-widget-draft"
                rows={1}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value)
                  setSendError(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitCompose()
                  }
                }}
                placeholder={t.inbox.placeholder}
                className="min-h-10 flex-1 resize-none rounded-full border border-gray-200 px-3 py-2 text-sm outline-none focus:border-brand-tan focus:ring-2 focus:ring-brand-tint"
              />
              {canSend ? (
                <button
                  type="submit"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-accent text-white disabled:opacity-50"
                  aria-label={t.inbox.send}
                  disabled={!canSend}
                >
                  <IconSend size={15} />
                </button>
              ) : (
                <button
                  type="button"
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
                    recording ? 'bg-red-500 text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-brand-accent'
                  }`}
                  aria-label={recording ? t.inbox.stopRecording : t.inbox.voice}
                  onClick={() => void toggleVoice()}
                >
                  <IconMic size={18} />
                </button>
              )}
            </div>
            {sendError ? <p className="px-1 pt-2 text-xs text-red-600">{sendError}</p> : null}
          </form>
        </>
      )}
    </div>
  )
}
