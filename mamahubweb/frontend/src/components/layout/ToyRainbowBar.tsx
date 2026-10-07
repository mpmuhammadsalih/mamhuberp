interface Props {
  className?: string
}

const BANDS = [
  'bg-brand-accent',
  'bg-brand-orange',
  'bg-brand-yellow',
  'bg-brand-teal',
  'bg-brand-purple',
] as const

export function ToyRainbowBar({ className = '' }: Props) {
  return (
    <div className={`flex h-1.5 w-full overflow-hidden ${className}`} aria-hidden>
      {BANDS.map((color) => (
        <span key={color} className={`min-w-0 flex-1 ${color}`} />
      ))}
    </div>
  )
}
