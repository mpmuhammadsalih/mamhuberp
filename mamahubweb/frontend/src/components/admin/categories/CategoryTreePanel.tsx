import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import type { CategoryFormIntent } from './categoryFormTypes'
import type { AdminCategoryNode } from './categoryUtils'
import { CategoryImageThumb } from './CategoryImageThumb'
import { ErpFlagBadge } from './ErpFlagBadge'

interface Props {
  nodes: AdminCategoryNode[]
  search: string
  onAction: (intent: CategoryFormIntent) => void
}

function ErpCatItem({
  node,
  mainCode,
  deptCode,
  expanded,
  onToggle,
  onAction,
}: {
  node: AdminCategoryNode
  mainCode?: number
  deptCode?: number
  expanded: Set<string>
  onToggle: (key: string) => void
  onAction: (intent: CategoryFormIntent) => void
}) {
  const flag = (node.flag ?? 'M') as 'M' | 'D' | 'C'
  const hasChildren = (node.children?.length ?? 0) > 0
  const key = `${flag}-${node.code}`
  const isOpen = expanded.has(key)

  let meta = ''
  if (flag === 'M') meta = `ID ${node.id ?? '—'}`
  else if (flag === 'D') meta = `ID ${node.id ?? '—'} · under main ${mainCode ?? node.parent_main_code ?? '—'}`
  else meta = `ID ${node.id ?? '—'} · D ${deptCode ?? node.parent_category_code ?? '—'}`

  return (
    <li className="relative my-[3px]" data-search={`${node.code} ${node.name} ${flag} ${node.id ?? ''}`}>
      <div className="cat-item flex flex-wrap items-center gap-1.5 rounded border border-[#e2e8f0] bg-white px-2.5 py-[7px] transition hover:bg-[#f0f5ff]">
        {hasChildren ? (
          <button
            type="button"
            className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded bg-[#eef2f7] text-[10px] text-[#4b5563] hover:bg-[#dbeafe] hover:text-[#1a56a4]"
            aria-expanded={isOpen}
            onClick={() => onToggle(key)}
          >
            {isOpen ? '▼' : '▶'}
          </button>
        ) : (
          <span className="inline-block h-[22px] w-[22px] shrink-0" aria-hidden />
        )}
        <ErpFlagBadge flag={flag} />
        <CategoryImageThumb name={node.name} imageUrl={node.image_url} size="sm" />
        <span className="min-w-[64px] font-mono text-[13px] font-semibold text-[#1a56a4]">{node.code}</span>
        <span className="min-w-[120px] flex-1 text-[13px] text-[#0f172a]">{node.name}</span>
        <span className="text-xs text-[#6b7280]">{meta}</span>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => onAction({ action: 'edit', flag, code: node.code, name: node.name })}
            className="rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs text-[#334155] hover:bg-[#f8fafc]"
          >
            Edit
          </button>
          {flag === 'M' && (
            <button
              type="button"
              onClick={() => onAction({ action: 'create', flag: 'D', mainCode: node.code })}
              className="rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs text-[#334155] hover:bg-[#f8fafc]"
            >
              + Category
            </button>
          )}
          {flag === 'D' && (
            <button
              type="button"
              onClick={() =>
                onAction({
                  action: 'create',
                  flag: 'C',
                  dCode: node.code,
                  mainCode: mainCode ?? node.parent_main_code,
                })
              }
              className="rounded border border-[#cbd5e1] bg-white px-2 py-0.5 text-xs text-[#334155] hover:bg-[#f8fafc]"
            >
              + Micro
            </button>
          )}
          <Link to="/admin/media" className="text-xs text-[#2563eb] hover:underline" title="Manage in Media (placement: category)">
            Image
          </Link>
        </div>
      </div>

      {hasChildren && isOpen && (
        <ul className="cat-children m-0 list-none pl-5">
          {node.children!.map((child) => (
            <ErpCatItem
              key={`${child.flag ?? '?'}-${child.code}`}
              node={child}
              mainCode={flag === 'M' ? node.code : mainCode}
              deptCode={flag === 'D' ? node.code : deptCode}
              expanded={expanded}
              onToggle={onToggle}
              onAction={onAction}
            />
          ))}
        </ul>
      )}
    </li>
  )
}

export function CategoryTreePanel({ nodes, search, onAction }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const keys = new Set<string>()
    const walk = (items: AdminCategoryNode[]) => {
      for (const n of items) {
        if (n.children?.length) {
          keys.add(`${n.flag ?? 'M'}-${n.code}`)
          walk(n.children)
        }
      }
    }
    walk(nodes)
    return keys
  })

  const visible = useMemo(() => {
    if (!search.trim()) return nodes
    const q = search.trim().toLowerCase()
    const filter = (items: AdminCategoryNode[]): AdminCategoryNode[] =>
      items
        .map((node) => {
          const hay = `${node.code} ${node.name} ${node.flag ?? ''} ${node.id ?? ''}`.toLowerCase()
          const children = node.children?.length ? filter(node.children) : []
          if (hay.includes(q) || children.length) return { ...node, children }
          return null
        })
        .filter(Boolean) as AdminCategoryNode[]
    return filter(nodes)
  }, [nodes, search])

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function setAll(open: boolean) {
    if (!open) {
      setExpanded(new Set())
      return
    }
    const keys = new Set<string>()
    const walk = (items: AdminCategoryNode[]) => {
      for (const n of items) {
        if (n.children?.length) {
          keys.add(`${n.flag ?? 'M'}-${n.code}`)
          walk(n.children)
        }
      }
    }
    walk(nodes)
    setExpanded(keys)
  }

  if (!visible.length) {
    return <p className="p-3 text-sm italic text-[#6b7280]">No category rows (FLAG = M) found.</p>
  }

  return (
    <div>
      <div className="mb-2 flex gap-1.5">
        <button type="button" onClick={() => setAll(true)} className="rounded border border-[#cbd5e1] bg-white px-2.5 py-1 text-[11px] text-[#334155] hover:bg-[#f8fafc]">
          Expand all
        </button>
        <button type="button" onClick={() => setAll(false)} className="rounded border border-[#cbd5e1] bg-white px-2.5 py-1 text-[11px] text-[#334155] hover:bg-[#f8fafc]">
          Collapse all
        </button>
      </div>
      <div className="cat-tree max-h-[76vh] overflow-auto rounded border border-[#e2e8f0] bg-white p-2 text-[13px]">
        <ul className="m-0 list-none p-0">
          {visible.map((node) => (
            <ErpCatItem
              key={`${node.flag ?? 'M'}-${node.code}`}
              node={node}
              expanded={expanded}
              onToggle={toggle}
              onAction={onAction}
            />
          ))}
        </ul>
      </div>
    </div>
  )
}
