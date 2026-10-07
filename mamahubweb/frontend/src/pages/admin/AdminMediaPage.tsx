import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { AdminState } from '../../components/admin/AdminState'
import { AdminPageTitle } from '../../components/admin/ui'
import { deleteData, getApiErrorMessage, getData, postData, uploadFile } from '../../lib/api'
import { resolveMediaUrl, isVideoMediaUrl } from '../../lib/media'

const PLACEMENTS = [
  { value: '', label: 'All placements' },
  { value: 'storefront_logo', label: 'Storefront logo' },
  { value: 'hero_bg', label: 'Hero background' },
  { value: 'hero', label: 'Hero slides' },
  { value: 'promo', label: 'Promo tiles' },
  { value: 'showcase_banner', label: 'Showcase banners' },
  { value: 'category', label: 'Category images' },
  { value: 'explore_category', label: 'Explore category tiles' },
  { value: 'brand', label: 'Brand logos' },
] as const

const PROMO_SIZE_HINT =
  'Banner sizes: strip-* → 1560×72 px · slide-*-main → 1040×220 px · slide-*-side → 520×220 px (JPG, PNG, WebP, SVG).'

const SHOWCASE_SIZE_HINT =
  'New Arrivals showcase: ref key new-arrivals · portrait image 560×720 px (or MP4 video + poster in meta).'

interface MediaRow {
  media_id: number | null
  placement: string
  ref_key?: string | null
  title?: string | null
  subtitle?: string | null
  title_ar?: string | null
  subtitle_ar?: string | null
  image_url: string
  link_url?: string | null
  alt_text?: string | null
  sort_order: number
  meta?: Record<string, unknown>
  is_active?: boolean
}

const emptyForm = {
  media_id: null as number | null,
  placement: 'hero',
  ref_key: '',
  title: '',
  subtitle: '',
  title_ar: '',
  subtitle_ar: '',
  image_url: '',
  link_url: '',
  alt_text: '',
  sort_order: 0,
  is_active: true,
  meta_json: '{}',
}

export function AdminMediaPage() {
  const queryClient = useQueryClient()
  const [placementFilter, setPlacementFilter] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [webCandidates, setWebCandidates] = useState<Array<{ url: string }>>([])
  const [downloadingUrl, setDownloadingUrl] = useState<string | null>(null)

  const { data: media = [], isLoading, isError } = useQuery({
    queryKey: ['admin-media', placementFilter],
    queryFn: () =>
      getData<MediaRow[]>('/admin/media', {
        placement: placementFilter || undefined,
      }),
  })

  const filtered = useMemo(() => {
    return [...media].sort((a, b) => {
      if (a.placement !== b.placement) return a.placement.localeCompare(b.placement)
      return (a.sort_order ?? 0) - (b.sort_order ?? 0)
    })
  }, [media])

  const saveMedia = useMutation({
    mutationFn: async () => {
      let meta: Record<string, unknown> = {}
      try {
        meta = JSON.parse(form.meta_json || '{}') as Record<string, unknown>
      } catch {
        throw new Error('Meta JSON is invalid.')
      }
      return postData('/admin/media', {
        media_id: form.media_id ?? undefined,
        placement: form.placement,
        ref_key: form.ref_key.trim() || null,
        title: form.title.trim() || null,
        subtitle: form.subtitle.trim() || null,
        title_ar: form.title_ar.trim() || null,
        subtitle_ar: form.subtitle_ar.trim() || null,
        image_url: form.image_url.trim(),
        link_url: form.link_url.trim() || null,
        alt_text: form.alt_text.trim() || null,
        sort_order: Number(form.sort_order) || 0,
        is_active: form.is_active,
        meta,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-media'] })
      setShowForm(false)
      setForm(emptyForm)
    },
  })

  const deactivate = useMutation({
    mutationFn: (mediaId: number) => deleteData(`/admin/media/${mediaId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-media'] }),
  })

  const upload = useMutation({
    mutationFn: (file: File) => uploadFile('/admin/media/upload', file),
    onSuccess: (result) => {
      setUploadError(null)
      setForm((prev) => ({ ...prev, image_url: result?.image_url ?? prev.image_url }))
    },
    onError: () => setUploadError('Upload failed. Use JPG/PNG/WebP/AVIF (5 MB) or MP4/WebM/MOV (50 MB).'),
  })

  const searchFromWeb = useMutation({
    mutationFn: () =>
      postData<{ query?: string; candidates: Array<{ url: string }> }>('/admin/media/search-from-web', {
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || undefined,
        ref_key: form.ref_key.trim() || undefined,
        placement: form.placement || undefined,
      }),
    onSuccess: (result) => {
      setFetchError(null)
      setWebCandidates(result?.candidates ?? [])
    },
    onError: (err) => {
      setWebCandidates([])
      setFetchError(getApiErrorMessage(err))
    },
  })

  const fetchFromWeb = useMutation({
    mutationFn: (sourceUrl: string) =>
      postData<{ image_url: string; query?: string }>('/admin/media/fetch-from-web', {
        title: form.title.trim(),
        subtitle: form.subtitle.trim() || undefined,
        ref_key: form.ref_key.trim() || undefined,
        placement: form.placement || undefined,
        source_url: sourceUrl,
      }),
    onSuccess: (result) => {
      setFetchError(null)
      setWebCandidates([])
      if (result?.image_url) {
        setForm((prev) => ({ ...prev, image_url: result.image_url }))
      }
    },
    onError: (err) => setFetchError(getApiErrorMessage(err)),
    onSettled: () => setDownloadingUrl(null),
  })

  function openCreate() {
    setForm(emptyForm)
    setWebCandidates([])
    setFetchError(null)
    setShowForm(true)
  }

  function openEdit(row: MediaRow) {
    setForm({
      media_id: row.media_id,
      placement: row.placement,
      ref_key: row.ref_key ?? '',
      title: row.title ?? '',
      subtitle: row.subtitle ?? '',
      title_ar: row.title_ar ?? '',
      subtitle_ar: row.subtitle_ar ?? '',
      image_url: row.image_url ?? '',
      link_url: row.link_url ?? '',
      alt_text: row.alt_text ?? '',
      sort_order: row.sort_order ?? 0,
      is_active: row.is_active !== false,
      meta_json: JSON.stringify(row.meta ?? {}, null, 2),
    })
    setWebCandidates([])
    setFetchError(null)
    setShowForm(true)
  }

  return (
    <div>
      <AdminPageTitle
        title="Storefront media"
        description="Manage homepage hero slides, promo tiles, banners, and category or brand images."
        action={
          <button
            type="button"
            onClick={openCreate}
            className="rounded-xl bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-hover"
          >
            Add media
          </button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-3">
        <select
          value={placementFilter}
          onChange={(e) => setPlacementFilter(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
        >
          {PLACEMENTS.map((p) => (
            <option key={p.value || 'all'} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      {showForm && (
        <form
          className="mb-6 grid gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            saveMedia.mutate()
          }}
        >
          <h2 className="md:col-span-2 text-lg font-semibold text-slate-900">
            {form.media_id ? 'Edit media' : 'New media'}
          </h2>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-600">Placement</span>
            <select
              required
              value={form.placement}
              onChange={(e) => setForm({ ...form, placement: e.target.value })}
              className="w-full rounded-lg border px-3 py-2"
            >
              {PLACEMENTS.filter((p) => p.value).map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-600">Ref key</span>
            <input
              value={form.ref_key}
              onChange={(e) => setForm({ ...form, ref_key: e.target.value })}
              placeholder={
                form.placement === 'promo'
                  ? 'strip-1, slide-1-main, slide-1-side'
                  : form.placement === 'showcase_banner'
                    ? 'new-arrivals'
                    : 'e.g. pink, new-arrivals, lego'
              }
              className="w-full rounded-lg border px-3 py-2"
            />
            {form.placement === 'promo' && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{PROMO_SIZE_HINT}</p>
            )}
            {form.placement === 'showcase_banner' && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{SHOWCASE_SIZE_HINT}</p>
            )}
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Title</span>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                className="min-w-0 flex-1 rounded-lg border px-3 py-2"
              />
              <button
                type="button"
                onClick={() => {
                  if (form.title.trim().length < 2) {
                    setFetchError('Enter a title first (at least 2 characters).')
                    return
                  }
                  setFetchError(null)
                  searchFromWeb.mutate()
                }}
                disabled={searchFromWeb.isPending}
                className="rounded-lg border border-pink-200 bg-pink-50 px-3 py-2 text-sm font-semibold text-brand-accent hover:bg-pink-100 disabled:opacity-50"
              >
                {searchFromWeb.isPending ? 'Searching…' : 'Search web'}
              </button>
            </div>
            {fetchError && <p className="mt-1 text-sm text-red-600">{fetchError}</p>}
            {webCandidates.length > 0 && (
              <div className="mt-3">
                <p className="mb-2 text-sm text-slate-500">Choose an image:</p>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                  {webCandidates.map((candidate, index) => (
                    <div
                      key={`${candidate.url}-${index}`}
                      className="overflow-hidden rounded-xl border border-slate-200 bg-white"
                    >
                      <img
                        src={candidate.url}
                        alt={`Option ${index + 1}`}
                        referrerPolicy="no-referrer"
                        loading="lazy"
                        className="h-24 w-full object-cover bg-slate-50"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setDownloadingUrl(candidate.url)
                          fetchFromWeb.mutate(candidate.url)
                        }}
                        disabled={fetchFromWeb.isPending}
                        className="w-full border-t border-slate-200 px-2 py-2 text-xs font-semibold text-brand-accent hover:bg-pink-50 disabled:opacity-50"
                      >
                        {downloadingUrl === candidate.url && fetchFromWeb.isPending
                          ? 'Saving…'
                          : 'Use this'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Subtitle</span>
            <input
              value={form.subtitle}
              onChange={(e) => setForm({ ...form, subtitle: e.target.value })}
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Title (Arabic)</span>
            <input
              value={form.title_ar}
              onChange={(e) => setForm({ ...form, title_ar: e.target.value })}
              dir="rtl"
              lang="ar"
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Subtitle (Arabic)</span>
            <input
              value={form.subtitle_ar}
              onChange={(e) => setForm({ ...form, subtitle_ar: e.target.value })}
              dir="rtl"
              lang="ar"
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">
              {form.placement === 'hero_bg' ? 'Video or image URL' : 'Image URL or path'}
            </span>
            <input
              required
              value={form.image_url}
              onChange={(e) => setForm({ ...form, image_url: e.target.value })}
              placeholder={
                form.placement === 'hero_bg'
                  ? '/media/files/hero.mp4 or upload below'
                  : '/images/hero-banner.png or /api/v1/media/files/...'
              }
              className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
            />
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <label className="cursor-pointer rounded-lg border border-dashed border-pink-300 px-3 py-2 text-sm text-brand-accent hover:bg-pink-50">
                {form.placement === 'hero_bg' ? 'Upload video or image' : 'Upload image'}
                <input
                  type="file"
                  accept={form.placement === 'hero_bg' ? 'image/*,video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v' : 'image/*'}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) upload.mutate(file)
                  }}
                />
              </label>
              {upload.isPending && <span className="text-sm text-slate-500">Uploading…</span>}
              {uploadError && <span className="text-sm text-red-600">{uploadError}</span>}
            </div>
            {form.placement === 'promo' && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{PROMO_SIZE_HINT}</p>
            )}
            {form.placement === 'showcase_banner' && (
              <p className="mt-2 text-xs leading-relaxed text-slate-500">{SHOWCASE_SIZE_HINT}</p>
            )}
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-600">Link URL</span>
            <input
              value={form.link_url}
              onChange={(e) => setForm({ ...form, link_url: e.target.value })}
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-600">Sort order</span>
            <input
              type="number"
              value={form.sort_order}
              onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })}
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Alt text</span>
            <input
              value={form.alt_text}
              onChange={(e) => setForm({ ...form, alt_text: e.target.value })}
              className="w-full rounded-lg border px-3 py-2"
            />
          </label>

          <label className="block text-sm md:col-span-2">
            <span className="mb-1 block font-medium text-slate-600">Meta JSON (overlay, colors, CTAs)</span>
            <textarea
              rows={5}
              value={form.meta_json}
              onChange={(e) => setForm({ ...form, meta_json: e.target.value })}
              className="w-full rounded-lg border px-3 py-2 font-mono text-xs"
            />
          </label>

          <label className="flex items-center gap-2 text-sm md:col-span-2">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Active on storefront
          </label>

          {saveMedia.isError && (
            <p className="md:col-span-2 text-sm text-red-600">
              {(saveMedia.error as Error)?.message || 'Save failed'}
            </p>
          )}

          <div className="flex gap-2 md:col-span-2">
            <button
              type="submit"
              disabled={saveMedia.isPending}
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
            >
              {saveMedia.isPending ? 'Saving…' : 'Save media'}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false)
                setForm(emptyForm)
              }}
              className="rounded-xl border px-4 py-2 text-sm text-slate-600"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <AdminState isLoading={isLoading} isError={isError} isEmpty={filtered.length === 0} emptyText="No media records yet.">
        <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3">Preview</th>
                <th className="px-4 py-3">Placement</th>
                <th className="px-4 py-3">Ref</th>
                <th className="px-4 py-3">Title</th>
                <th className="px-4 py-3">Title (AR)</th>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => {
                const src = resolveMediaUrl(row.image_url)
                const isVideo = isVideoMediaUrl(row.image_url)
                return (
                  <tr key={`${row.media_id ?? row.ref_key}-${row.placement}`} className="border-t border-slate-100">
                    <td className="px-4 py-3">
                      {src && isVideo ? (
                        <video src={src} muted playsInline className="h-12 w-20 rounded-lg object-cover ring-1 ring-slate-200" />
                      ) : src ? (
                        <img src={src} alt="" className="h-12 w-20 rounded-lg object-cover ring-1 ring-slate-200" />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{row.placement}</td>
                    <td className="px-4 py-3">{row.ref_key || '—'}</td>
                    <td className="px-4 py-3 max-w-[160px] truncate">{row.title || '—'}</td>
                    <td className="px-4 py-3 max-w-[160px] truncate">{row.title_ar || '—'}</td>
                    <td className="px-4 py-3">{row.sort_order}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          row.is_active !== false ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        {row.is_active !== false ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button type="button" onClick={() => openEdit(row)} className="text-brand-accent hover:underline">
                          Edit
                        </button>
                        {row.media_id && row.is_active !== false && (
                          <button
                            type="button"
                            onClick={() => deactivate.mutate(row.media_id!)}
                            className="text-red-600 hover:underline"
                          >
                            Deactivate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </AdminState>
    </div>
  )
}
