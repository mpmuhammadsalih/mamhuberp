import { useEffect, useState } from 'react'
import {
  categoryFormHint,
  categoryFormTitle,
  type CategoryFormIntent,
} from './categoryFormTypes'

interface Props {
  intent: CategoryFormIntent | null
  saving?: boolean
  error?: string | null
  onClose: () => void
  onSave: (name: string) => void
}

export function CategoryFormModal({ intent, saving, error, onClose, onSave }: Props) {
  const [name, setName] = useState('')

  useEffect(() => {
    if (!intent) {
      setName('')
      return
    }
    setName(intent.action === 'edit' ? intent.name : '')
  }, [intent])

  if (!intent) return null

  const showCode = intent.action === 'edit'

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || saving) return
    onSave(trimmed)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <button
        type="button"
        className="absolute inset-0 bg-black/40"
        aria-label="Close"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md rounded-lg border border-[#e2e8f0] bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-[#e2e8f0] px-5 py-4">
          <h3 className="text-base font-semibold text-[#111827]">{categoryFormTitle(intent)}</h3>
          <button
            type="button"
            className="text-xl leading-none text-[#64748b] hover:text-[#0f172a]"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="space-y-4 px-5 py-4">
            <p className="text-sm text-[#64748b]">{categoryFormHint(intent)}</p>

            {showCode && (
              <div>
                <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#64748b]">
                  Code
                </label>
                <input
                  type="text"
                  readOnly
                  value={intent.code}
                  className="w-full rounded border border-[#e2e8f0] bg-[#f8fafc] px-3 py-2 text-sm text-[#334155]"
                  tabIndex={-1}
                />
              </div>
            )}

            <div>
              <label htmlFor="cm-name" className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#64748b]">
                Name *
              </label>
              <input
                id="cm-name"
                type="text"
                maxLength={200}
                autoComplete="off"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-[#cbd5e1] px-3 py-2 text-sm outline-none focus:border-[#2563eb] focus:ring-1 focus:ring-[#2563eb]/20"
                autoFocus
              />
            </div>

            {error && (
              <p className="rounded border border-[#fecaca] bg-[#fef2f2] px-3 py-2 text-sm text-[#b91c1c]">
                {error}
              </p>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t border-[#e2e8f0] px-5 py-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-[#cbd5e1] bg-white px-4 py-2 text-sm text-[#334155] hover:bg-[#f8fafc]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || saving}
              className="rounded bg-[#2563eb] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1d4ed8] disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
