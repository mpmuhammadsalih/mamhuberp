import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { useSearchParams } from 'react-router-dom'

import {
  CatalogCategoryToolbar,
  type CategoryPill,
} from '../components/catalog/CatalogCategoryToolbar'
import { categoryDisplayName } from '../i18n/categoryName'
import { ageGroupDisplayName } from '../i18n/ageGroupName'
import { brandDisplayName } from '../i18n/brandName'
import { useLocale } from '../i18n/LocaleContext'
import { getSortOptions } from '../i18n/sortOptions'

import { CatalogLayout } from '../components/catalog/CatalogLayout'

import { CatalogPageHero } from '../components/catalog/CatalogPageHero'

import { Pagination } from '../components/Pagination'

import { ProductCard } from '../components/ProductCard'

import { SeoHead } from '../components/seo/SeoHead'

import { PRODUCT_GRID, PRODUCT_GRID_SKELETON } from '../components/layout/homeLayout'

import { getDataWithMeta } from '../lib/api'

import { catalogQueries } from '../lib/queries/catalog'

import type { Product } from '../types/api'



export function ProductsPage() {
  const { locale, t } = useLocale()
  const [params, setParams] = useSearchParams()

  const search = params.get('q') || undefined

  const brand = params.get('brand') || undefined

  const age = params.get('age') || undefined

  const interest = params.get('interest') || undefined

  const main = params.get('main') || undefined

  const dept = params.get('dept') || undefined

  const category = params.get('category') || undefined

  const minPrice = params.get('min_price') || undefined

  const maxPrice = params.get('max_price') || undefined

  const sortValue = params.get('sort') || 'relevance'

  const pageSize = Number(params.get('page_size') || '24')

  const page = Number(params.get('page') || '1')



  const sortOptions = getSortOptions(t)
  const sortOption = sortOptions.find((o) => o.value === sortValue) ?? sortOptions[0]



  const { data: categoryTree = [] } = useQuery(catalogQueries.categoryTree)

  const { data: ageGroups = [] } = useQuery(catalogQueries.ageGroups)

  const { data: interests = [] } = useQuery(catalogQueries.interests)

  const { data: brands = [] } = useQuery(catalogQueries.brands)



  const { data, isLoading } = useQuery({

    queryKey: ['products', search, brand, age, interest, main, dept, category, minPrice, maxPrice, sortValue, pageSize, page],

    queryFn: ({ signal }) =>

      getDataWithMeta<Product[]>(

        '/products',

        {

          ...(search ? { search } : {}),

          ...(brand ? { brand_code: Number(brand) || brand } : {}),

          ...(age ? { age } : {}),

          ...(interest ? { interest } : {}),

          ...(main ? { main_category_code: main } : {}),

          ...(dept ? { department_code: dept } : {}),

          ...(category ? { category_code: category } : {}),

          ...(minPrice ? { min_price: minPrice } : {}),

          ...(maxPrice ? { max_price: maxPrice } : {}),

          sort: sortOption.sort,

          order: sortOption.order,

          page,

          page_size: pageSize,

        },

        { signal },

      ),

    placeholderData: keepPreviousData,

  })



  const products = data?.data ?? []

  const meta = data?.meta

  const totalPages = meta?.total_pages ?? 1

  const activeMainNode = categoryTree.find((c) => String(c.code) === main)
  const activeMainName = activeMainNode ? categoryDisplayName(activeMainNode, locale) : undefined

  const showSkeleton = isLoading && products.length === 0



  function updateParam(key: string, value: string | null) {

    const next = new URLSearchParams(params)

    if (value) next.set(key, value)

    else next.delete(key)

    if (key === 'main') {

      next.delete('dept')

      next.delete('category')

    }

    if (key === 'dept') next.delete('category')

    next.delete('page')

    setParams(next)

  }



  function handlePriceApply(min: string, max: string) {

    const next = new URLSearchParams(params)

    if (min) next.set('min_price', min)

    else next.delete('min_price')

    if (max) next.set('max_price', max)

    else next.delete('max_price')

    next.delete('page')

    setParams(next)

  }



  function handleCategoryPill(pill: CategoryPill) {

    const next = new URLSearchParams(params)



    if (pill.paramKey === 'all') {

      const activeMain = categoryTree.find((m) => String(m.code) === main)

      const activeDeptNode = activeMain?.children?.find((d) => String(d.code) === dept)

      const hasSubCategories = (activeDeptNode?.children?.length ?? 0) > 0



      if (dept && hasSubCategories) {

        next.delete('category')

      } else if (main) {

        next.delete('dept')

        next.delete('category')

      } else {

        next.delete('main')

        next.delete('dept')

        next.delete('category')

      }

    } else if (pill.value) {

      next.set(pill.paramKey, pill.value)

      if (pill.paramKey === 'main') {

        next.delete('dept')

        next.delete('category')

      }

      if (pill.paramKey === 'dept') {

        next.delete('category')

      }

    }



    next.delete('page')

    setParams(next)

  }



  function handleSortChange(value: string) {

    const next = new URLSearchParams(params)

    if (value === 'relevance') next.delete('sort')

    else next.set('sort', value)

    next.delete('page')

    setParams(next)

  }



  const activeAgeName = age
    ? ageGroups.find((group) => group.slug === age)
    : undefined
  const activeBrand = brand
    ? brands.find((item) => String(item.code) === String(brand))
    : undefined
  const title =
    activeMainName ||
    (activeAgeName ? ageGroupDisplayName(activeAgeName, locale, t) : undefined) ||
    (activeBrand ? brandDisplayName(activeBrand, locale) : undefined) ||
    (search ? `${t.shared.resultsFor} “${search}”` : t.shared.allToys)
  const subtitle =
    meta?.total_records != null
      ? `${meta.total_records.toLocaleString()} ${t.shared.productsCount}`
      : undefined



  const pageHeader = <CatalogPageHero title={title} subtitle={subtitle} />



  const toolbar = (

    <CatalogCategoryToolbar

      categoryTree={categoryTree}

      selectedMain={main}

      selectedDept={dept}

      selectedCategory={category}

      totalCount={meta?.total_records}

      sortValue={sortValue}

      onCategorySelect={handleCategoryPill}

      onSortChange={handleSortChange}

    />

  )



  return (

    <CatalogLayout

      pageHeader={pageHeader}

      toolbar={toolbar}

      sortValue={sortValue}

      onSortChange={handleSortChange}

      filterProps={{

        categoryTree,

        ageGroups,

        brands,

        interests,

        selectedMain: main,

        selectedDept: dept,

        selectedCategory: category,

        selectedAge: age,

        selectedBrand: brand,

        selectedInterest: interest,

        minPrice: minPrice ?? '',

        maxPrice: maxPrice ?? '',

        onSelect: updateParam,

        onPriceApply: handlePriceApply,

        onClear: () => setParams(new URLSearchParams()),

      }}

    >

      <SeoHead
        title={title}
        description={
          search
            ? `Search results for “${search}” — toys and gifts at MamaHub Qatar.`
            : `${title} — browse our toy catalog with filters for age, brand, and category.`
        }
        noIndex={false}
      />

      {showSkeleton ? (
        <div className={PRODUCT_GRID_SKELETON}>

          {Array.from({ length: 10 }).map((_, i) => (

            <div key={i} className="min-h-[320px] animate-pulse rounded-2xl bg-brand-tint/70" />

          ))}

        </div>

      ) : products.length === 0 ? (

        <p className="py-16 text-center text-slate-500">{t.shared.noProductsMatch}</p>

      ) : (

        <>

          <div className={PRODUCT_GRID}>

            {products.map((p) => (

              <ProductCard

                key={p.item_code}

                product={p}

                badge={

                  p.discount_percent && p.discount_percent > 0

                    ? `${p.discount_percent}%`

                    : undefined

                }

              />

            ))}

          </div>

          <Pagination

            page={page}

            totalPages={totalPages}

            pageSize={pageSize}

            onPageChange={(p) => {

              const next = new URLSearchParams(params)

              next.set('page', String(p))

              setParams(next)

              window.scrollTo({ top: 0, behavior: 'smooth' })

            }}

            onPageSizeChange={(size) => {

              const next = new URLSearchParams(params)

              next.set('page_size', String(size))

              next.delete('page')

              setParams(next)

            }}

          />

        </>

      )}

    </CatalogLayout>

  )

}


