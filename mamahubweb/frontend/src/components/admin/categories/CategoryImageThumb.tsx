import { useState } from 'react'
import { resolveMediaUrl } from '../../../lib/media'

export function CategoryImageThumb({
  name,
  imageUrl,
  size = 'md',
}: {
  name: string
  imageUrl?: string | null
  size?: 'sm' | 'md'
}) {
  const [broken, setBroken] = useState(false)
  const src = resolveMediaUrl(imageUrl ?? undefined)
  const dims = size === 'sm' ? 'h-8 w-8' : 'h-10 w-10'
  const text = size === 'sm' ? 'text-[10px]' : 'text-xs'

  if (src && !broken) {
    return (
      <img
        src={src}
        alt=""
        className={`${dims} shrink-0 rounded object-cover ring-1 ring-[#e2e8f0]`}
        onError={() => setBroken(true)}
      />
    )
  }

  return (
    <span
      className={`${dims} flex shrink-0 items-center justify-center rounded bg-[#eef2f7] font-bold text-[#64748b] ring-1 ring-[#e2e8f0] ${text}`}
      title="No image — add in Admin → Media (placement: category)"
    >
      {name.slice(0, 2).toUpperCase()}
    </span>
  )
}
