import { useQuery } from '@tanstack/react-query'
import { useLocale } from '../../i18n/LocaleContext'
import { getDataWithMeta } from '../../lib/api'
import type { Product } from '../../types/api'
import { ProductCarousel } from './ProductCarousel'

interface Props {
  itemCode: number
  categoryCode?: number
  viewAllHref?: string
}

export function SimilarProductsCarousel({
  itemCode,
  categoryCode,
  viewAllHref = '/products',
}: Props) {
  const { t } = useLocale()

  const { data } = useQuery({
    queryKey: ['similar-products', itemCode, categoryCode],
    queryFn: ({ signal }) =>
      getDataWithMeta<Product[]>(
        '/products',
        {
          category_code: categoryCode,
          stock_filter: 'in_stock',
          page: 1,
          page_size: 16,
        },
        { signal },
      ),
    enabled: Boolean(itemCode) && Boolean(categoryCode),
  })

  const products = (data?.data ?? []).filter((product) => product.item_code !== itemCode).slice(0, 12)

  return (
    <ProductCarousel
      title={t.shared.similarProducts}
      products={products}
      viewAllHref={viewAllHref}
    />
  )
}
