import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { CategoryFormModal } from '../../components/admin/categories/CategoryFormModal'

import { CategoryListPanel } from '../../components/admin/categories/CategoryListPanel'

import { CategoryTreePanel } from '../../components/admin/categories/CategoryTreePanel'

import type { CategoryFormIntent } from '../../components/admin/categories/categoryFormTypes'

import {

  countErpTreeNodes,

  flattenErpCategoryTree,

  filterErpFlatRows,

  type AdminCategoryNode,

} from '../../components/admin/categories/categoryUtils'

import { AdminState } from '../../components/admin/AdminState'

import { getApiErrorMessage, getData, postData } from '../../lib/api'



type ViewMode = 'tree' | 'list'



export function AdminCategoriesPage() {

  const queryClient = useQueryClient()

  const [view, setView] = useState<ViewMode>('tree')

  const [search, setSearch] = useState('')

  const [formIntent, setFormIntent] = useState<CategoryFormIntent | null>(null)

  const [saveError, setSaveError] = useState<string | null>(null)



  const { data: tree = [], isLoading, isError } = useQuery({

    queryKey: ['admin-category-tree'],

    queryFn: () => getData<AdminCategoryNode[]>('/categories/tree'),

  })



  const saveCategory = useMutation({

    mutationFn: (payload: {

      mode: 'create' | 'update'

      flag: 'M' | 'D' | 'C'

      name: string

      code?: number

      main_code?: number

      d_code?: number

    }) => postData<{ code: number; flag: string; name: string }>('/admin/categories', payload),

    onSuccess: () => {

      queryClient.invalidateQueries({ queryKey: ['admin-category-tree'] })

      setFormIntent(null)

      setSaveError(null)

    },

    onError: (err) => {

      setSaveError(getApiErrorMessage(err))

    },

  })



  const flatRows = useMemo(() => flattenErpCategoryTree(tree), [tree])

  const filteredListRows = useMemo(() => filterErpFlatRows(flatRows, search), [flatRows, search])



  const visibleTreeCount = useMemo(() => {

    if (!search.trim()) return countErpTreeNodes(tree)

    return filteredListRows.length

  }, [tree, search, filteredListRows.length])



  const countLabel =

    view === 'list'

      ? search.trim()

        ? `${filteredListRows.length} of ${flatRows.length} shown`

        : `${flatRows.length} rows`

      : search.trim()

        ? `${visibleTreeCount} of ${countErpTreeNodes(tree)} shown`

        : `${countErpTreeNodes(tree)} nodes`



  function openForm(intent: CategoryFormIntent) {

    setSaveError(null)

    setFormIntent(intent)

  }



  function handleSave(name: string) {

    if (!formIntent) return

    setSaveError(null)



    if (formIntent.action === 'edit') {

      saveCategory.mutate({

        mode: 'update',

        flag: formIntent.flag,

        code: formIntent.code,

        name,

      })

      return

    }



    if (formIntent.flag === 'M') {

      saveCategory.mutate({ mode: 'create', flag: 'M', name })

      return

    }



    if (formIntent.flag === 'D') {

      saveCategory.mutate({

        mode: 'create',

        flag: 'D',

        name,

        main_code: formIntent.mainCode,

      })

      return

    }



    saveCategory.mutate({

      mode: 'create',

      flag: 'C',

      name,

      d_code: formIntent.dCode,

      main_code: formIntent.mainCode,

    })

  }



  return (

    <div className="category-master-page mx-auto max-w-[1300px]">

      <div className="mb-4 flex flex-wrap items-start justify-between gap-4 border-b border-[#e2e8f0] pb-4">

        <div>

          <h1 className="text-xl font-bold text-[#111827]">Category Master</h1>

        </div>

        <div className="flex flex-wrap gap-2">

          <button

            type="button"

            onClick={() => openForm({ action: 'create', flag: 'M' })}

            className="rounded bg-[#2563eb] px-3 py-2 text-sm font-semibold text-white hover:bg-[#1d4ed8]"

          >

            + Main category

          </button>

          <a href="/admin/products" className="rounded border border-[#cbd5e1] bg-white px-3 py-2 text-sm text-[#334155] hover:bg-[#f8fafc]">

            Item Master list

          </a>

        </div>

      </div>



      <div className="mb-3 flex gap-1 border-b border-[#e2e8f0]">

        <button

          type="button"

          onClick={() => setView('tree')}

          className={`border-b-2 px-4 py-2 text-sm font-medium transition ${

            view === 'tree'

              ? 'border-[#2563eb] text-[#2563eb]'

              : 'border-transparent text-[#64748b] hover:text-[#0f172a]'

          }`}

        >

          Tree view

        </button>

        <button

          type="button"

          onClick={() => setView('list')}

          className={`border-b-2 px-4 py-2 text-sm font-medium transition ${

            view === 'list'

              ? 'border-[#2563eb] text-[#2563eb]'

              : 'border-transparent text-[#64748b] hover:text-[#0f172a]'

          }`}

        >

          List view

        </button>

      </div>



      <div className="mb-3 flex flex-wrap items-center gap-2">

        {view === 'tree' && (

          <span id="treeExpandBar" className="inline-flex items-center gap-1.5">

            {/* Expand/collapse live inside tree panel like ERP toolbar duplication — optional */}

          </span>

        )}

        <input

          type="text"

          value={search}

          onChange={(e) => setSearch(e.target.value)}

          placeholder="Search code or name…"

          className="min-w-[220px] max-w-xs rounded border border-[#cbd5e1] px-3 py-1.5 text-sm outline-none focus:border-[#2563eb] focus:ring-1 focus:ring-[#2563eb]/20"

        />

        <button

          type="button"

          onClick={() => setSearch('')}

          className="rounded border border-[#cbd5e1] bg-white px-2.5 py-1 text-[11px] text-[#334155] hover:bg-[#f8fafc]"

        >

          Clear

        </button>

        <span className="text-sm tabular-nums text-[#64748b]">{countLabel}</span>

      </div>



      <AdminState isLoading={isLoading} isError={isError} isEmpty={tree.length === 0} emptyText="No category rows (FLAG = M) found.">

        {view === 'tree' ? (

          <div>

            <div className="mb-2 text-sm font-semibold text-[#374151]">Category hierarchy</div>

            <CategoryTreePanel nodes={tree} search={search} onAction={openForm} />

          </div>

        ) : (

          <CategoryListPanel rows={filteredListRows} onAction={openForm} />

        )}

      </AdminState>



      <CategoryFormModal

        intent={formIntent}

        saving={saveCategory.isPending}

        error={saveError}

        onClose={() => {

          setFormIntent(null)

          setSaveError(null)

        }}

        onSave={handleSave}

      />

    </div>

  )

}


