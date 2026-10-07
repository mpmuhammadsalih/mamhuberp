import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AdminState } from '../../components/admin/AdminState'
import {
  AdminButton,
  AdminCard,
  AdminField,
  AdminSelect,
  AdminTableWrap,
  AdminTextarea,
  StatusBadge,
} from '../../components/admin/ui'
import { getData, patchData } from '../../lib/api'
import { formatMoney } from '../../lib/currency'
import type { OrderDetail } from '../../types/api'

const STATUS_OPTIONS = [
  'CONFIRMED',
  'PROCESSING',
  'PICKING',
  'PACKED',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
  'CANCELLED',
] as const

const thClass = 'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#94a3b8]'
const tdClass = 'px-4 py-4 text-sm text-[#334155]'

function formatDate(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-QA', { dateStyle: 'medium', timeStyle: 'short' })
}

export function AdminOrderDetailPage() {
  const { orderId } = useParams()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  const [notes, setNotes] = useState('')

  const { data: order, isLoading, isError } = useQuery({
    queryKey: ['admin-order', orderId],
    queryFn: () => getData<OrderDetail>(`/admin/orders/${orderId}`),
    enabled: Boolean(orderId),
  })

  useEffect(() => {
    if (order?.order_status) setStatus(order.order_status)
  }, [order?.order_status])

  const updateStatus = useMutation({
    mutationFn: () =>
      patchData(`/admin/orders/${orderId}/status`, { status, notes: notes.trim() || undefined }),
    onSuccess: () => {
      setNotes('')
      queryClient.invalidateQueries({ queryKey: ['admin-order', orderId] })
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] })
    },
  })

  return (
    <div>
      <Link to="/admin/orders" className="text-sm font-medium text-[#E91E63] hover:underline">
        ← Back to orders
      </Link>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={!order}>
        {order && (
          <>
            <AdminCard className="mt-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl font-bold text-[#0f172a]">{order.order_number}</h1>
                    <StatusBadge status={order.order_status} />
                  </div>
                  <p className="mt-2 text-sm text-[#64748b]">
                    {formatDate(order.created_at)} · Payment: {order.payment_status ?? '—'}
                  </p>
                </div>
              </div>
            </AdminCard>

            <div className="mt-6 grid gap-6 lg:grid-cols-3">
              <div className="space-y-6 lg:col-span-2">
                <AdminCard>
                  <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Order Items</h2>
                  <AdminTableWrap>
                    <table className="w-full min-w-[560px]">
                      <thead className="bg-[#fafbfd]">
                        <tr>
                          <th className={thClass}>Product</th>
                          <th className={thClass}>Price</th>
                          <th className={thClass}>Qty</th>
                          <th className={thClass}>Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(order.items ?? []).map((item) => (
                          <tr key={item.order_item_id ?? item.item_code} className="border-t border-[#eef1f6]">
                            <td className={tdClass}>
                              <div className="flex items-center gap-3">
                                <div className="h-10 w-10 rounded-lg bg-[#f8fafc]" />
                                <span className="font-medium text-[#0f172a]">{item.item_name}</span>
                              </div>
                            </td>
                            <td className={tdClass}>{formatMoney(item.unit_price, order.currency_code)}</td>
                            <td className={tdClass}>{item.quantity}</td>
                            <td className={tdClass}>{formatMoney(item.line_total, order.currency_code)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </AdminTableWrap>

                  <dl className="mt-6 space-y-2 border-t border-[#eef1f6] pt-4 text-sm">
                    <div className="flex justify-between text-[#64748b]">
                      <dt>Subtotal</dt>
                      <dd>{formatMoney(order.subtotal ?? 0, order.currency_code)}</dd>
                    </div>
                    {(order.discount_total ?? 0) > 0 && (
                      <div className="flex justify-between text-green-600">
                        <dt>Discount</dt>
                        <dd>-{formatMoney(order.discount_total ?? 0, order.currency_code)}</dd>
                      </div>
                    )}
                    <div className="flex justify-between text-[#64748b]">
                      <dt>Shipping</dt>
                      <dd>{formatMoney(order.delivery_fee ?? 0, order.currency_code)}</dd>
                    </div>
                    {!!order.gift_wrap && (
                      <div className="flex justify-between text-[#64748b]">
                        <dt>{order.gift_wrap.label || 'Gift wrap'}</dt>
                        <dd>
                          {formatMoney(
                            order.gift_wrap_fee ?? order.gift_wrap.fee ?? 0,
                            order.currency_code,
                          )}
                        </dd>
                      </div>
                    )}
                    <div className="flex justify-between text-[#64748b]">
                      <dt>Tax</dt>
                      <dd>{formatMoney(order.tax_total ?? 0, order.currency_code)}</dd>
                    </div>
                    <div className="flex justify-between border-t border-[#eef1f6] pt-2 text-lg font-bold text-[#0f172a]">
                      <dt>Total</dt>
                      <dd>{formatMoney(order.grand_total, order.currency_code)}</dd>
                    </div>
                  </dl>
                </AdminCard>
              </div>

              <div className="space-y-6">
                <AdminCard>
                  <h2 className="mb-3 font-semibold text-[#0f172a]">Shipping Address</h2>
                  <p className="text-sm leading-relaxed text-[#64748b]">
                    Delivery order
                    <br />
                    {order.fulfillment_type?.replace(/_/g, ' ') ?? 'Home delivery'}
                    <br />
                    Qatar
                  </p>
                </AdminCard>

                <AdminCard>
                  <h2 className="mb-3 font-semibold text-[#0f172a]">Update Status</h2>
                  <AdminField label="Status">
                    <AdminSelect value={status} onChange={setStatus}>
                      {STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                      ))}
                    </AdminSelect>
                  </AdminField>
                  <AdminField label="Notes" className="mt-3">
                    <AdminTextarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional note" />
                  </AdminField>
                  <AdminButton
                    className="mt-4 w-full"
                    onClick={() => updateStatus.mutate()}
                    disabled={updateStatus.isPending || status === order.order_status}
                  >
                    {updateStatus.isPending ? 'Saving…' : 'Save status'}
                  </AdminButton>
                </AdminCard>

                {order.customer_notes && (
                  <AdminCard>
                    <h2 className="mb-2 font-semibold text-[#0f172a]">Customer notes</h2>
                    <p className="text-sm text-[#64748b]">{order.customer_notes}</p>
                  </AdminCard>
                )}
              </div>
            </div>

            {(order.status_history?.length ?? 0) > 0 && (
              <AdminCard className="mt-6">
                <h2 className="mb-4 font-semibold text-[#0f172a]">Status history</h2>
                <ol className="space-y-3">
                  {order.status_history!.map((entry, index) => (
                    <li key={`${entry.created_at}-${index}`} className="flex gap-4 text-sm">
                      <span className="w-32 shrink-0 text-[#94a3b8]">{formatDate(entry.created_at)}</span>
                      <div>
                        <StatusBadge status={entry.order_status ?? entry.status ?? '—'} />
                        {(entry.status_notes ?? entry.notes) && (
                          <p className="mt-1 text-[#64748b]">{entry.status_notes ?? entry.notes}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </AdminCard>
            )}
          </>
        )}
      </AdminState>
    </div>
  )
}
