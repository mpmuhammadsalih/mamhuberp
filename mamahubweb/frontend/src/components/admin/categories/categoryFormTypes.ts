export type CategoryFormIntent =
  | { action: 'create'; flag: 'M' }
  | { action: 'create'; flag: 'D'; mainCode: number }
  | { action: 'create'; flag: 'C'; dCode: number; mainCode?: number }
  | { action: 'edit'; flag: 'M' | 'D' | 'C'; code: number; name: string }

export function categoryFormTitle(intent: CategoryFormIntent | null): string {
  if (!intent) return 'Category'
  if (intent.action === 'edit') return 'Edit category'
  if (intent.flag === 'M') return 'New main category'
  if (intent.flag === 'D') return 'New category (under main)'
  return 'New micro category'
}

export function categoryFormHint(intent: CategoryFormIntent | null): string {
  if (!intent) return ''
  if (intent.action === 'edit') {
    return `Update name for code ${intent.code} (FLAG ${intent.flag}).`
  }
  if (intent.flag === 'M') return 'Code is assigned automatically.'
  if (intent.flag === 'D') return `Under main category ${intent.mainCode}. Code is assigned automatically.`
  return `Under category (D) ${intent.dCode}. Code is assigned automatically.`
}
