import { useLocale } from '../i18n/LocaleContext'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { IconHeart } from './icons/Icons'
import { deleteData, getApiErrorMessage, getData, postData } from '../lib/api'
import { storage } from '../lib/storage'
import type { WishlistItem } from '../types/api'

interface WishlistData {
  items: WishlistItem[]
}

interface Props {
  itemCode: number
  size?: number
  variant?: 'card' | 'detail'
  className?: string
}

export function WishlistButton({ itemCode, size = 16, variant = 'card', className = '' }: Props) {
  const { t } = useLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const loggedIn = storage.hasSession()
  void location

  const { data: wishlist } = useQuery({
    queryKey: ['wishlist'],
    queryFn: () => getData<WishlistData>('/wishlist'),
    enabled: loggedIn,
    staleTime: 30_000,
  })

  const wishlistItem = wishlist?.items?.find((item) => item.item_code === itemCode)
  const saved = Boolean(wishlistItem)

  const addItem = useMutation({
    mutationFn: () => postData<WishlistData>('/wishlist/items', { item_code: itemCode }),
    onSuccess: (data) => {
      queryClient.setQueryData(['wishlist'], data)
    },
  })

  const removeItem = useMutation({
    mutationFn: () => deleteData<WishlistData>(`/wishlist/items/${wishlistItem!.wishlist_item_id}`),
    onSuccess: (data) => {
      queryClient.setQueryData(['wishlist'], data)
    },
  })

  const busy = addItem.isPending || removeItem.isPending
  const error = addItem.error ?? removeItem.error
  const errorMessage = error ? getApiErrorMessage(error) : null

  function handleClick(event: React.MouseEvent) {
    event.preventDefault()
    event.stopPropagation()
    if (!loggedIn) {
      const redirect = encodeURIComponent(location.pathname + location.search)
      navigate(`/login?redirect=${redirect}`)
      return
    }
    if (saved && wishlistItem) {
      removeItem.mutate()
      return
    }
    addItem.mutate()
  }

  const variantClass =
    variant === 'card'
      ? 'absolute end-2.5 top-2.5 z-20 flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-sm transition'
      : 'absolute end-3 top-3 z-20 transition'

  const wishlistLabel = saved ? t.product.removeFromWishlist : t.product.addToWishlist

  return (
    <div className="pointer-events-none absolute inset-0 z-20">
      <button
        type="button"
        disabled={busy}
        className={`pointer-events-auto ${variantClass} ${saved ? 'text-brand-rose' : 'text-gray-300 hover:text-brand-rose'} disabled:opacity-60 ${className}`}
        onClick={handleClick}
        onMouseDown={(event) => event.stopPropagation()}
        aria-label={wishlistLabel}
        aria-pressed={saved}
        title={errorMessage ?? wishlistLabel}
      >
        <IconHeart size={size} filled={saved} />
      </button>
      {errorMessage ? (
        <p
          className="pointer-events-none absolute end-2 top-12 z-20 max-w-[10rem] rounded-md bg-red-600 px-2 py-1 text-[10px] font-medium leading-tight text-white shadow"
          role="status"
        >
          {errorMessage}
        </p>
      ) : null}
    </div>
  )
}
