import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { AdminState } from '../../components/admin/AdminState'
import { AdminPageTitle } from '../../components/admin/ui'
import { AdminPagination } from '../../components/admin/AdminPagination'
import { patchData, getDataWithMeta } from '../../lib/api'
import { metaFromResponse } from '../../hooks/usePaginationMeta'

interface PendingReview {
  review_id: number
  item_code: number
  rating: number
  title?: string
  review_text?: string
  reviewer_name?: string
  created_at?: string
}

export function AdminReviewsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const { data: response, isLoading, isError } = useQuery({
    queryKey: ['admin-reviews-pending', page, pageSize],
    queryFn: () =>
      getDataWithMeta<PendingReview[]>('/reviews/admin/pending', { page, page_size: pageSize }),
  })

  const moderate = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      patchData(`/reviews/admin/${id}/status`, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-reviews-pending'] }),
  })

  const reviews = response?.data ?? []
  const meta = metaFromResponse(response)

  return (
    <div>
      <AdminPageTitle title="Review moderation" description="Approve or reject customer product reviews." />

      <AdminState
        isLoading={isLoading}
        isError={isError}
        isEmpty={reviews.length === 0}
        emptyText="No pending reviews."
      >
        <div className="space-y-4">
          {reviews.map((r) => (
            <div key={r.review_id} className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="font-semibold text-slate-900">
                  Item {r.item_code} · {'★'.repeat(r.rating)}
                  {r.reviewer_name && <span className="ml-2 font-normal text-slate-500">by {r.reviewer_name}</span>}
                </p>
                {r.created_at && (
                  <span className="text-xs text-slate-400">{new Date(r.created_at).toLocaleDateString()}</span>
                )}
              </div>
              {r.title && <p className="mt-1 font-medium">{r.title}</p>}
              {r.review_text && <p className="mt-2 text-sm text-slate-600">{r.review_text}</p>}
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => moderate.mutate({ id: r.review_id, status: 'APPROVED' })}
                  disabled={moderate.isPending}
                  className="rounded-lg bg-green-600 px-3 py-1.5 text-sm font-medium text-white"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => moderate.mutate({ id: r.review_id, status: 'REJECTED' })}
                  disabled={moderate.isPending}
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white"
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>

        <AdminPagination
          page={page}
          totalPages={meta.total_pages}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      </AdminState>
    </div>
  )
}
