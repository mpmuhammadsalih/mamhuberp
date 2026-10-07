import { useQuery } from '@tanstack/react-query'
import { useLocale } from '../../i18n/LocaleContext'
import { getData } from '../../lib/api'
import type { Product } from '../../types/api'
import { ProductCarousel } from './ProductCarousel'

interface Props {
  itemCode: number
  viewAllHref?: string
}

export function SuggestedProductsCarousel({
  itemCode,
  viewAllHref = '/featured',
}: Props) {
  const { t } = useLocale()

  const { data } = useQuery({
    queryKey: ['suggested-products', itemCode],
    queryFn: ({ signal }) =>
      getData<Product[]>(
        '/products/suggested',
        { item_code: itemCode, page_size: 12 },
        { signal },
      ),
    enabled: Boolean(itemCode),
  })

  return (
    <ProductCarousel
      title={t.shared.suggestedProducts}
      products={data ?? []}
      viewAllHref={viewAllHref}
    />
  )
}
