export interface AdminCategoryNode {
  id?: number
  code: number
  name: string
  flag?: string
  level_name?: string
  image_url?: string | null
  parent_main_code?: number
  parent_category_code?: number
  location_code?: number
  children?: AdminCategoryNode[]
}

export interface ErpFlatCategoryRow {
  id?: number
  code: number
  name: string
  flag: string
  level_name: string
  level: number
  parent_main_code?: number | null
  parent_category_code?: number | null
  image_url?: string | null
  search_text: string
}

const FLAG_META: Record<string, { label: string; level: number }> = {
  M: { label: 'Main category', level: 0 },
  D: { label: 'Category', level: 1 },
  C: { label: 'Micro category', level: 2 },
}

export function erpLevelName(flag?: string, level_name?: string) {
  if (level_name) return level_name
  if (flag === 'M') return 'Main category'
  if (flag === 'D') return 'Category'
  if (flag === 'C') return 'Micro category'
  return 'Category'
}

export function flattenErpCategoryTree(
  nodes: AdminCategoryNode[],
  parentMainCode?: number,
  parentCategoryCode?: number,
): ErpFlatCategoryRow[] {
  const rows: ErpFlatCategoryRow[] = []

  for (const node of nodes) {
    const flag = node.flag ?? 'M'
    const meta = FLAG_META[flag] ?? FLAG_META.M
    const mainCode = flag === 'M' ? node.code : (node.parent_main_code ?? parentMainCode ?? null)

    rows.push({
      id: node.id,
      code: node.code,
      name: node.name,
      flag,
      level_name: erpLevelName(flag, node.level_name),
      level: meta.level,
      parent_main_code: flag === 'M' ? null : mainCode,
      parent_category_code: flag === 'C' ? (node.parent_category_code ?? parentCategoryCode ?? null) : null,
      image_url: node.image_url,
      search_text: `${node.code} ${node.name} ${flag} ${node.id ?? ''}`.trim(),
    })

    if (node.children?.length) {
      const nextMain = flag === 'M' ? node.code : mainCode ?? undefined
      const nextDept = flag === 'D' ? node.code : parentCategoryCode
      rows.push(...flattenErpCategoryTree(node.children, nextMain, nextDept))
    }
  }

  return rows
}

export function filterErpFlatRows(rows: ErpFlatCategoryRow[], search: string) {
  const q = search.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((row) => row.search_text.toLowerCase().includes(q))
}

export function filterErpTree(nodes: AdminCategoryNode[], search: string): AdminCategoryNode[] {
  const q = search.trim().toLowerCase()
  if (!q) return nodes

  const walk = (items: AdminCategoryNode[]): AdminCategoryNode[] =>
    items
      .map((node) => {
        const hay = `${node.code} ${node.name} ${node.flag ?? ''} ${node.id ?? ''}`.toLowerCase()
        const children = node.children?.length ? walk(node.children) : []
        if (hay.includes(q) || children.length) return { ...node, children }
        return null
      })
      .filter(Boolean) as AdminCategoryNode[]

  return walk(nodes)
}

export function countErpTreeNodes(nodes: AdminCategoryNode[]): number {
  return nodes.reduce((sum, node) => sum + 1 + countErpTreeNodes(node.children ?? []), 0)
}
