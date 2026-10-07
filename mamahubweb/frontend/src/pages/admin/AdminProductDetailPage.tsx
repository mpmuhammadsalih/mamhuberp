import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { AdminState } from '../../components/admin/AdminState'
import {
  AdminButton,
  AdminCard,
  AdminField,
  AdminInput,
  AdminPageTitle,
  AdminTextarea,
  AdminToggle,
} from '../../components/admin/ui'
import { ProductImage } from '../../components/ProductImage'
import { getData } from '../../lib/api'
import { formatMoney } from '../../lib/currency'
import type { Product } from '../../types/api'

export function AdminProductDetailPage() {
  const { itemCode } = useParams()

  const { data: product, isLoading, isError } = useQuery({
    queryKey: ['admin-product', itemCode],
    queryFn: () => getData<Product>(`/admin/products/${itemCode}`),
    enabled: Boolean(itemCode),
  })

  const [active, setActive] = useState(true)

  return (
    <div>
      <Link to="/admin/products" className="text-sm font-medium text-[#E91E63] hover:underline">
        ← Back to products
      </Link>

      <AdminState isLoading={isLoading} isError={isError} isEmpty={!product}>
        {product && (
          <>
            <AdminPageTitle
              title="Edit Product"
              description={`SKU ${product.item_code} · ${product.brand_name || 'Generic brand'}`}
              action={
                <div className="flex gap-2">
                  <Link to="/admin/products">
                    <AdminButton variant="secondary">Cancel</AdminButton>
                  </Link>
                  <AdminButton>Save Changes</AdminButton>
                </div>
              }
            />

            <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
              <AdminCard>
                <div className="grid gap-5 md:grid-cols-2">
                  <AdminField label="Product Name" className="md:col-span-2">
                    <AdminInput defaultValue={product.item_name ?? ''} readOnly />
                  </AdminField>
                  <AdminField label="Category">
                    <AdminInput defaultValue={product.category_name ?? ''} readOnly />
                  </AdminField>
                  <AdminField label="Brand">
                    <AdminInput defaultValue={product.brand_name ?? 'Generic'} readOnly />
                  </AdminField>
                  <AdminField label="SKU">
                    <AdminInput defaultValue={String(product.item_code)} readOnly />
                  </AdminField>
                  <AdminField label="Stock Quantity">
                    <AdminInput defaultValue={String(product.current_stock ?? 0)} readOnly />
                  </AdminField>
                  <AdminField label="Price (QAR)">
                    <AdminInput defaultValue={String(product.retail_price ?? 0)} readOnly />
                  </AdminField>
                  <AdminField label="Sale Price / MRP">
                    <AdminInput
                      defaultValue={String(product.offer_price ?? product.retail_price ?? 0)}
                      readOnly
                    />
                  </AdminField>
                  <AdminField label="Description" className="md:col-span-2">
                    <AdminTextarea rows={4} defaultValue={product.description ?? product.item_name ?? ''} readOnly />
                  </AdminField>
                  <AdminToggle
                    checked={active && (product.current_stock ?? 0) > 0}
                    onChange={setActive}
                    label="Active on storefront"
                  />
                </div>
              </AdminCard>

              <AdminCard>
                <h2 className="mb-4 text-lg font-semibold text-[#0f172a]">Product Images</h2>
                <div className="grid grid-cols-2 gap-3">
                  <div className="overflow-hidden rounded-xl ring-1 ring-[#eef1f6]">
                    <ProductImage src={product.primary_image_url} alt={product.item_name || ''} className="aspect-square w-full object-cover" />
                  </div>
                  {(product.images ?? []).slice(0, 3).map((img, i) => (
                    <div key={i} className="overflow-hidden rounded-xl ring-1 ring-[#eef1f6]">
                      <ProductImage src={img.image_url ?? img.image_path} alt="" className="aspect-square w-full object-cover" />
                    </div>
                  ))}
                  <button
                    type="button"
                    className="flex aspect-square flex-col items-center justify-center rounded-xl border-2 border-dashed border-[#e2e8f0] text-sm text-[#94a3b8] hover:border-[#E91E63] hover:text-[#E91E63]"
                  >
                    + Add Images
                  </button>
                </div>
                <p className="mt-4 text-center text-2xl font-bold text-[#E91E63]">
                  {formatMoney(product.retail_price ?? 0)}
                </p>
              </AdminCard>
            </div>

            {product.warehouse_stock && product.warehouse_stock.length > 0 && (
              <AdminCard className="mt-6">
                <h2 className="mb-3 font-semibold text-[#0f172a]">Warehouse stock</h2>
                <ul className="grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                  {product.warehouse_stock.map((w) => (
                    <li key={w.warehouse_id} className="rounded-xl bg-[#f8fafc] px-4 py-3 text-sm">
                      Warehouse {w.warehouse_id}: <strong>{w.qty}</strong> units
                    </li>
                  ))}
                </ul>
              </AdminCard>
            )}
          </>
        )}
      </AdminState>
    </div>
  )
}
