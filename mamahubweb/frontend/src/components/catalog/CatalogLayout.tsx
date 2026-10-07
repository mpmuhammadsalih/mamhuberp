import type { ReactNode } from 'react'

import { useMemo, useState } from 'react'

import { CatalogFloatingFilterSort } from '../catalog/CatalogFloatingFilterSort'

import { ProductFiltersDrawer } from '../catalog/ProductFiltersDrawer'

import { ProductFiltersSidebar } from '../catalog/ProductFiltersSidebar'

import { HOME_CONTAINER } from '../layout/homeLayout'



interface CategoryNode {

  code: number

  name: string

  children?: CategoryNode[]

}



export interface CatalogFilterState {

  categoryTree: CategoryNode[]

  ageGroups: Array<{ slug: string; age_group_name: string }>

  brands: Array<{ code: number; name: string }>

  interests: Array<{ slug: string; interest_name: string }>

  selectedMain?: string

  selectedDept?: string

  selectedCategory?: string

  selectedAge?: string

  selectedBrand?: string

  selectedInterest?: string

  minPrice?: string

  maxPrice?: string

  showAllItems?: boolean

  onShowAllItemsChange?: (enabled: boolean) => void

  onSelect: (key: string, value: string | null) => void

  onPriceApply: (min: string, max: string) => void

  onClear: () => void

}



interface Props {

  title?: string

  subtitle?: string

  pageHeader?: ReactNode

  filterProps: CatalogFilterState

  children: ReactNode

  hero?: ReactNode

  toolbar?: ReactNode

  sortValue?: string

  onSortChange?: (value: string) => void

}



function countActiveFilters(filterProps: CatalogFilterState): number {

  let count = 0

  if (filterProps.selectedMain) count += 1

  if (filterProps.selectedDept) count += 1

  if (filterProps.selectedCategory) count += 1

  if (filterProps.selectedAge) count += 1

  if (filterProps.selectedBrand) count += 1

  if (filterProps.selectedInterest) count += 1

  if (filterProps.minPrice) count += 1

  if (filterProps.maxPrice) count += 1

  return count

}



export function CatalogLayout({

  title,

  subtitle,

  pageHeader,

  filterProps,

  children,

  hero,

  toolbar,

  sortValue,

  onSortChange,

}: Props) {

  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false)

  const activeFilterCount = useMemo(() => countActiveFilters(filterProps), [filterProps])

  const showMobileBar = sortValue != null && onSortChange != null



  return (

    <div className="font-catalog bg-[#fafafa]">

      {hero}



      <div className={`${HOME_CONTAINER} pb-24 pt-6 lg:pb-12 lg:pt-8`}>

        {pageHeader}



        {!pageHeader && !hero && title && (

          <div className="mb-5">

            <h1 className="text-xl font-semibold tracking-tight text-gray-900 sm:text-2xl">{title}</h1>

            {subtitle && <p className="mt-1 text-[13px] font-normal text-gray-500">{subtitle}</p>}

          </div>

        )}



        <ProductFiltersDrawer

          open={mobileFiltersOpen}

          onClose={() => setMobileFiltersOpen(false)}

          {...filterProps}

        />



        {showMobileBar ? (

          <CatalogFloatingFilterSort

            sortValue={sortValue}

            onSortChange={onSortChange}

            onOpenFilters={() => setMobileFiltersOpen(true)}

            activeFilterCount={activeFilterCount}

          />

        ) : null}



        <div className="flex items-start gap-5 lg:gap-7">

          <div className="hidden w-[240px] shrink-0 lg:block xl:w-[280px]">

            <div className="sticky top-[7.75rem] z-10 lg:top-[7rem]">

              <ProductFiltersSidebar {...filterProps} />

            </div>

          </div>



          <div className="min-w-0 flex-1">

            {toolbar}

            {children}

          </div>

        </div>

      </div>

    </div>

  )

}


