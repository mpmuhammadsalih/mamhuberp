import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IconArrowRight, IconBaby, IconPlane, IconRobot, IconTeddy } from './icons/Icons'
import { resolveMediaUrl } from '../lib/media'

const STYLES = [
  {
    bg: 'bg-gradient-to-br from-[#FFF8E7] to-[#FFF3D6]',
    ring: 'ring-[#FF7043]/25',
    accent: 'bg-[#FF7043]',
    text: 'text-[#FF7043]',
    icon: IconBaby,
  },
  {
    bg: 'bg-gradient-to-br from-[#E8F8ED] to-[#DFF5E6]',
    ring: 'ring-[#43A047]/25',
    accent: 'bg-[#43A047]',
    text: 'text-[#43A047]',
    icon: IconTeddy,
  },
  {
    bg: 'bg-gradient-to-br from-[#F6EEFC] to-[#EDE0F8]',
    ring: 'ring-[#AB47BC]/25',
    accent: 'bg-[#AB47BC]',
    text: 'text-[#AB47BC]',
    icon: IconPlane,
  },
  {
    bg: 'bg-gradient-to-br from-[#E8F2FC] to-[#DCEBFA]',
    ring: 'ring-[#1E88E5]/25',
    accent: 'bg-[#1E88E5]',
    text: 'text-[#1E88E5]',
    icon: IconRobot,
  },
] as const

interface Props {
  slug: string
  name: string
  index: number
  imageUrl?: string
}

export function AgeGroupCard({ slug, name, index, imageUrl }: Props) {
  const style = STYLES[index % STYLES.length]
  const Icon = style.icon
  const photo = resolveMediaUrl(imageUrl)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [photo])

  const showPhoto = Boolean(photo) && !failed

  return (
    <Link
      to={`/products?age=${slug}`}
      className="group flex w-full max-w-[220px] flex-col items-center gap-3 text-center sm:max-w-[256px] sm:gap-3.5 lg:max-w-[300px] xl:max-w-[328px]"
    >
      <span
        className={`relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-full shadow-md ring-4 ${style.ring} transition duration-200 group-hover:scale-[1.04] group-hover:shadow-lg motion-reduce:transform-none ${style.bg}`}
      >
        {showPhoto ? (
          <img
            key={photo}
            src={photo}
            alt=""
            className="h-full w-full object-cover object-center transition duration-500 group-hover:scale-[1.06]"
            loading="lazy"
            onError={() => setFailed(true)}
          />
        ) : (
          <Icon size={64} className="h-16 w-16 drop-shadow-md sm:h-[4.5rem] sm:w-[4.5rem]" />
        )}

        <span
          className={`absolute bottom-1 right-1 flex h-7 w-7 items-center justify-center rounded-full ${style.accent} text-white shadow-sm transition group-hover:scale-110 sm:h-8 sm:w-8`}
        >
          <IconArrowRight size={14} />
        </span>
      </span>

      <p className={`line-clamp-2 w-full font-display text-sm font-bold leading-tight sm:text-base ${style.text}`}>
        {name}
      </p>
    </Link>
  )
}
