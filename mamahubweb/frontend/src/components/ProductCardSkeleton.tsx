interface Props {
  variant?: 'grid' | 'carousel'
}

export function ProductCardSkeleton({ variant = 'grid' }: Props) {
  const widthClass = variant === 'carousel' ? 'min-w-[176px] max-w-[214px] shrink-0' : ''
  return (
    <div
      className={`flex min-h-[320px] animate-pulse flex-col overflow-hidden rounded-[32px] bg-white p-1.5 shadow-[0_10px_28px_rgba(15,23,42,0.06)] ring-1 ring-slate-200/80 ${widthClass}`}
    >
      <div className="aspect-square rounded-[22px] bg-slate-100" />
      <div className="flex flex-1 flex-col px-1.5 pt-2">
        <div className="h-5 w-2/5 rounded bg-slate-100" />
        <div className="mt-3 h-3.5 w-full rounded bg-slate-100" />
        <div className="mt-2 h-3.5 w-3/4 rounded bg-slate-100" />
        <div className="mt-auto h-11 w-full rounded-full bg-slate-100" />
      </div>
    </div>
  )
}

export function ProductCarouselSkeleton({ title }: { title: string }) {
  return (
    <section className="mx-auto w-full max-w-[1560px] px-4 pb-12 pt-2 sm:px-6 md:px-8 lg:pb-14 lg:px-12 xl:px-16">
      <div className="mb-6 h-8 w-48 animate-pulse rounded-lg bg-brand-tint lg:mb-7" aria-hidden />
      <span className="sr-only">{title}</span>
      <div className="flex gap-4 overflow-hidden lg:gap-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <ProductCardSkeleton key={i} variant="carousel" />
        ))}
      </div>
    </section>
  )
}
