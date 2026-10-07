import { ProductCard } from '../ProductCard'
import { useLocale } from '../../i18n/LocaleContext'
import type { Product } from '../../types/api'

interface Props {
  product: Product
}

export function NewArrivalCard({ product }: Props) {
  const { t } = useLocale()
  return <ProductCard product={product} badge={t.shared.new} />
}
