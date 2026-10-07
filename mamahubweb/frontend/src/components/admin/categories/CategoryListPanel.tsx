import { Link } from 'react-router-dom'
import { ErpFlagBadge } from './ErpFlagBadge'
import { CategoryImageThumb } from './CategoryImageThumb'
import type { CategoryFormIntent } from './categoryFormTypes'
import type { ErpFlatCategoryRow } from './categoryUtils'

interface Props {
  rows: ErpFlatCategoryRow[]
  onAction: (intent: CategoryFormIntent) => void
}

export function CategoryListPanel({ rows, onAction }: Props) {
  if (!rows.length) {
    return (
      <div className="overflow-hidden rounded border border-[#e2e8f0] bg-white">
        <p className="py-5 text-center text-sm italic text-[#6b7280]">No rows.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded border border-[#e2e8f0] bg-white">
      <table className="w-full min-w-[960px] border-collapse text-[13px]">
        <thead className="bg-[#f8fafc] text-left text-xs font-semibold uppercase tracking-wide text-[#64748b]">
          <tr className="border-b border-[#e2e8f0]">
            <th className="w-[52px] px-3 py-2.5 text-center">Sl.</th>
            <th className="w-[56px] px-3 py-2.5 text-center">Image</th>
            <th className="px-3 py-2.5">Flag</th>
            <th className="px-3 py-2.5">Level</th>
            <th className="px-3 py-2.5">ID</th>
            <th className="px-3 py-2.5">Code</th>
            <th className="px-3 py-2.5">Name</th>
            <th className="px-3 py-2.5">Main (code)</th>
            <th className="px-3 py-2.5">Category (code)</th>
            <th className="px-3 py-2.5 text-center">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={`${row.flag}-${row.code}`}
              className={`cat-row border-b border-[#f1f5f9] hover:bg-[#f8fafc] ${
                row.level === 0 ? 'font-semibold' : row.level === 1 ? 'bg-white' : 'bg-white'
              }`}
              data-search={row.search_text}
            >
              <td className="sl-no px-3 py-2 text-center text-[#64748b]">{index + 1}</td>
              <td className="px-3 py-2">
                <div className="flex justify-center">
                  <CategoryImageThumb name={row.name} imageUrl={row.image_url} size="sm" />
                </div>
              </td>
              <td className="px-3 py-2">
                <ErpFlagBadge flag={row.flag} />
              </td>
              <td className="px-3 py-2 text-[#334155]">{row.level_name}</td>
              <td className="px-3 py-2 text-[#334155]">{row.id ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-[#1a56a4]">{row.code}</td>
              <td
                className="px-3 py-2 text-[#0f172a]"
                style={{ paddingLeft: `${12 + row.level * 19}px` }}
              >
                {row.name}
              </td>
              <td className="px-3 py-2 font-mono text-[#334155]">{row.parent_main_code ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-[#334155]">{row.parent_category_code ?? '—'}</td>
              <td className="whitespace-nowrap px-3 py-2 text-center">
                <button
                  type="button"
                  onClick={() =>
                    onAction({
                      action: 'edit',
                      flag: row.flag as 'M' | 'D' | 'C',
                      code: row.code,
                      name: row.name,
                    })
                  }
                  className="rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs hover:bg-[#f8fafc]"
                >
                  Edit
                </button>
                {row.flag === 'M' && (
                  <button
                    type="button"
                    onClick={() => onAction({ action: 'create', flag: 'D', mainCode: row.code })}
                    className="ml-1.5 rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs hover:bg-[#f8fafc]"
                  >
                    + Category
                  </button>
                )}
                {row.flag === 'D' && (
                  <button
                    type="button"
                    onClick={() =>
                      onAction({
                        action: 'create',
                        flag: 'C',
                        dCode: row.code,
                        mainCode: row.parent_main_code ?? undefined,
                      })
                    }
                    className="ml-1.5 rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs hover:bg-[#f8fafc]"
                  >
                    + Micro
                  </button>
                )}
                <Link
                  to={`/admin/media?placement=category&ref=${row.code}`}
                  className="ml-1.5 text-xs text-[#2563eb] hover:underline"
                  title="Manage category image in Media"
                >
                  Image
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
