import { getCategoryMenuIcon } from '../../lib/categoryMenuIcons'

interface Props {
  name: string
  seed?: number
  size?: 'sm' | 'md' | 'lg'
}

export function CategoryMenuIcon({ name, seed = 0, size = 'md' }: Props) {
  const { bg, Icon } = getCategoryMenuIcon(name, seed)
  const box = size === 'sm' ? 'h-5 w-5' : size === 'lg' ? 'h-12 w-12' : 'h-6 w-6'
  const iconSize = size === 'sm' ? 14 : size === 'lg' ? 22 : 16

  return (
    <span
      className={`flex ${box} shrink-0 items-center justify-center rounded-full ${bg} shadow-sm ring-1 ring-black/[0.04]`}
      aria-hidden
    >
      <Icon size={iconSize} className="pointer-events-none" />
    </span>
  )
}
