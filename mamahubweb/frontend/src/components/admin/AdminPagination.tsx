import { Pagination } from '../Pagination'

interface AdminPaginationProps {
  page: number
  totalPages: number
  pageSize?: number
  onPageChange: (page: number) => void
  onPageSizeChange?: (size: number) => void
}

export function AdminPagination({
  page,
  totalPages,
  pageSize = 20,
  onPageChange,
  onPageSizeChange,
}: AdminPaginationProps) {
  return (
    <Pagination
      page={page}
      totalPages={totalPages}
      pageSize={pageSize}
      pageSizeOptions={[10, 20, 50]}
      onPageChange={onPageChange}
      onPageSizeChange={onPageSizeChange}
    />
  )
}
