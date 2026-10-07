import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { AdminState } from '../../components/admin/AdminState'
import { AdminPageTitle } from '../../components/admin/ui'
import { getData, patchData, postData } from '../../lib/api'
import { DEFAULT_CURRENCY, formatMoney } from '../../lib/currency'

interface Promo {
  promotion_id: number
  coupon_id: number
  coupon_code: string
  promotion_code: string
  promotion_name: string
  promotion_type: string
  discount_value: number
  min_order_amount: number
  max_discount_amount?: number | null
  start_date?: string
  end_date?: string
  usage_limit?: number | null
  usage_per_customer?: number
  promotion_active?: number
  coupon_active?: number
}

const emptyForm = {
  promotion_code: '',
  promotion_name: '',
  promotion_type: 'PERCENTAGE' as const,
  discount_value: 10,
  min_order_amount: 100,
  max_discount_amount: '' as number | '',
  coupon_code: '',
  start_date: new Date().toISOString().slice(0, 16),
  end_date: new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 16),
  usage_limit: '' as number | '',
  usage_per_customer: 1,
}

function toLocalDatetime(value?: string) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString().slice(0, 16)
}

function formatPromoDates(start?: string, end?: string) {
  if (!start || !end) return null
  return `${new Date(start).toLocaleDateString()} – ${new Date(end).toLocaleDateString()}`
}

export function AdminPromotionsPage() {
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<'create' | 'edit' | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState(emptyForm)

  const { data: promos = [], isLoading, isError } = useQuery({
    queryKey: ['admin-promotions'],
    queryFn: () => getData<Promo[]>('/admin/promotions'),
  })

  const createPromo = useMutation({
    mutationFn: () =>
      postData('/admin/promotions', {
        promotion_code: form.promotion_code,
        promotion_name: form.promotion_name,
        promotion_type: form.promotion_type,
        discount_value: form.discount_value,
        min_order_amount: form.min_order_amount,
        max_discount_amount: form.max_discount_amount === '' ? undefined : form.max_discount_amount,
        coupon_code: form.coupon_code,
        usage_limit: form.usage_limit === '' ? undefined : form.usage_limit,
        usage_per_customer: form.usage_per_customer,
        start_date: new Date(form.start_date).toISOString(),
        end_date: new Date(form.end_date).toISOString(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-promotions'] })
      setMode(null)
      setForm(emptyForm)
    },
  })

  const updatePromo = useMutation({
    mutationFn: () =>
      patchData(`/admin/promotions/${editingId}`, {
        promotion_name: form.promotion_name,
        discount_value: form.discount_value,
        min_order_amount: form.min_order_amount,
        max_discount_amount: form.max_discount_amount === '' ? null : form.max_discount_amount,
        end_date: new Date(form.end_date).toISOString(),
        usage_limit: form.usage_limit === '' ? null : form.usage_limit,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-promotions'] })
      setMode(null)
      setEditingId(null)
      setForm(emptyForm)
    },
  })

  const toggleActive = useMutation({
    mutationFn: (p: Promo) =>
      patchData(`/admin/promotions/${p.promotion_id}`, {
        is_active: !(p.promotion_active ?? 1),
        coupon_is_active: !(p.coupon_active ?? 1),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-promotions'] }),
  })

  function openCreate() {
    setForm(emptyForm)
    setEditingId(null)
    setMode('create')
  }

  function openEdit(p: Promo) {
    setEditingId(p.promotion_id)
    setForm({
      promotion_code: p.promotion_code,
      promotion_name: p.promotion_name,
      promotion_type: p.promotion_type as typeof form.promotion_type,
      discount_value: p.discount_value,
      min_order_amount: p.min_order_amount,
      max_discount_amount: p.max_discount_amount ?? '',
      coupon_code: p.coupon_code,
      start_date: toLocalDatetime(p.start_date),
      end_date: toLocalDatetime(p.end_date),
      usage_limit: p.usage_limit ?? '',
      usage_per_customer: p.usage_per_customer ?? 1,
    })
    setMode('edit')
  }

  return (
    <div>
      <AdminPageTitle
        title="Promotions & coupons"
        description="Create discount campaigns and manage coupon codes."
        action={
          <button
            type="button"
            onClick={() => (mode === 'create' ? setMode(null) : openCreate())}
            className="rounded-xl bg-brand-accent px-4 py-2 text-sm font-semibold text-white hover:bg-brand-accent-hover"
          >
            {mode === 'create' ? 'Cancel' : 'New promotion'}
          </button>
        }
      />

      {mode === 'create' && (
        <form
          className="mb-6 grid gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            createPromo.mutate()
          }}
        >
          <h2 className="md:col-span-2 text-lg font-semibold">New promotion</h2>
          <input
            required
            placeholder="Promotion code"
            value={form.promotion_code}
            onChange={(e) => setForm({ ...form, promotion_code: e.target.value })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            required
            placeholder="Coupon code"
            value={form.coupon_code}
            onChange={(e) => setForm({ ...form, coupon_code: e.target.value })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            required
            placeholder="Promotion name"
            value={form.promotion_name}
            onChange={(e) => setForm({ ...form, promotion_name: e.target.value })}
            className="rounded-lg border px-3 py-2 md:col-span-2"
          />
          <select
            value={form.promotion_type}
            onChange={(e) =>
              setForm({ ...form, promotion_type: e.target.value as typeof form.promotion_type })
            }
            className="rounded-lg border px-3 py-2"
          >
            <option value="PERCENTAGE">Percentage off</option>
            <option value="FIXED">Fixed amount off</option>
            <option value="FREE_DELIVERY">Free delivery</option>
          </select>
          <input
            type="number"
            min={0}
            placeholder="Discount value"
            value={form.discount_value}
            onChange={(e) => setForm({ ...form, discount_value: Number(e.target.value) })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder={`Min order (${DEFAULT_CURRENCY})`}
            value={form.min_order_amount}
            onChange={(e) => setForm({ ...form, min_order_amount: Number(e.target.value) })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder={`Max discount (${DEFAULT_CURRENCY}, optional)`}
            value={form.max_discount_amount}
            onChange={(e) =>
              setForm({
                ...form,
                max_discount_amount: e.target.value === '' ? '' : Number(e.target.value),
              })
            }
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={1}
            placeholder="Usage limit (optional)"
            value={form.usage_limit}
            onChange={(e) =>
              setForm({ ...form, usage_limit: e.target.value === '' ? '' : Number(e.target.value) })
            }
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={1}
            placeholder="Usage per customer"
            value={form.usage_per_customer}
            onChange={(e) => setForm({ ...form, usage_per_customer: Number(e.target.value) })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="datetime-local"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="datetime-local"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className="rounded-lg border px-3 py-2"
          />
          <button
            type="submit"
            disabled={createPromo.isPending}
            className="rounded-xl bg-slate-900 py-2 font-semibold text-white md:col-span-2"
          >
            {createPromo.isPending ? 'Creating…' : 'Create promotion'}
          </button>
        </form>
      )}

      {mode === 'edit' && (
        <form
          className="mb-6 grid gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            updatePromo.mutate()
          }}
        >
          <h2 className="md:col-span-2 text-lg font-semibold">Edit {form.coupon_code}</h2>
          <input
            required
            placeholder="Promotion name"
            value={form.promotion_name}
            onChange={(e) => setForm({ ...form, promotion_name: e.target.value })}
            className="rounded-lg border px-3 py-2 md:col-span-2"
          />
          <input
            type="number"
            min={0}
            placeholder="Discount value"
            value={form.discount_value}
            onChange={(e) => setForm({ ...form, discount_value: Number(e.target.value) })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder={`Min order (${DEFAULT_CURRENCY})`}
            value={form.min_order_amount}
            onChange={(e) => setForm({ ...form, min_order_amount: Number(e.target.value) })}
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder={`Max discount (${DEFAULT_CURRENCY})`}
            value={form.max_discount_amount}
            onChange={(e) =>
              setForm({
                ...form,
                max_discount_amount: e.target.value === '' ? '' : Number(e.target.value),
              })
            }
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="number"
            min={1}
            placeholder="Usage limit"
            value={form.usage_limit}
            onChange={(e) =>
              setForm({ ...form, usage_limit: e.target.value === '' ? '' : Number(e.target.value) })
            }
            className="rounded-lg border px-3 py-2"
          />
          <input
            type="datetime-local"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className="rounded-lg border px-3 py-2 md:col-span-2"
          />
          <div className="flex gap-2 md:col-span-2">
            <button
              type="submit"
              disabled={updatePromo.isPending}
              className="rounded-xl bg-slate-900 px-4 py-2 font-semibold text-white"
            >
              {updatePromo.isPending ? 'Saving…' : 'Save changes'}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode(null)
                setEditingId(null)
              }}
              className="rounded-xl border px-4 py-2 text-slate-600"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <AdminState isLoading={isLoading} isError={isError} isEmpty={promos.length === 0}>
        <div className="grid gap-4 md:grid-cols-2">
          {promos.map((p) => {
            const active = (p.promotion_active ?? 1) === 1 && (p.coupon_active ?? 1) === 1
            const dates = formatPromoDates(p.start_date, p.end_date)
            return (
              <div key={p.coupon_code} className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-mono text-lg font-bold text-brand-accent">{p.coupon_code}</p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p className="mt-1 font-medium">{p.promotion_name}</p>
                <p className="mt-2 text-sm text-slate-500">
                  {p.promotion_type} · {p.discount_value}
                  {p.promotion_type === 'PERCENTAGE' ? '%' : ` ${DEFAULT_CURRENCY}`} off
                </p>
                <p className="text-sm text-slate-500">Min order: {formatMoney(p.min_order_amount)}</p>
                {dates && <p className="text-sm text-slate-500">{dates}</p>}
                {p.usage_limit != null && (
                  <p className="text-sm text-slate-500">Usage limit: {p.usage_limit}</p>
                )}
                <div className="mt-3 flex gap-3">
                  <button
                    type="button"
                    onClick={() => openEdit(p)}
                    className="text-sm text-slate-600 hover:underline"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleActive.mutate(p)}
                    className="text-sm text-brand-accent hover:underline"
                  >
                    {active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </AdminState>
    </div>
  )
}
