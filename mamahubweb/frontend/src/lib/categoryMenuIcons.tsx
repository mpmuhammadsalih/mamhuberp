import type { ComponentType } from 'react'
import {
  IconBaby,
  IconBlocks,
  IconCake,
  IconGift,
  IconPlane,
  IconRobot,
  IconSparkle,
  IconTeddy,
} from '../components/icons/Icons'

type IconProps = { className?: string; size?: number }

interface CategoryIconConfig {
  bg: string
  Icon: ComponentType<IconProps>
}

function IconFashion({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path
        d="M8 4l-2 4H4l3 6v8h10v-8l3-6h-2l-2-4-2 2h-4L8 4z"
        fill="#EC4899"
        stroke="#BE185D"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconPencil({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M4 18l10-10 4 4L8 22H4v-4z" fill="#FBBF24" stroke="#D97706" strokeWidth="1.2" />
      <path d="M13 7l4 4" stroke="#92400E" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function IconHome({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 01-1 1h-5v-6H10v6H5a1 1 0 01-1-1v-9.5z" fill="#34D399" stroke="#059669" strokeWidth="1.2" />
    </svg>
  )
}

function IconBall({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <circle cx="12" cy="12" r="8" fill="#FB923C" stroke="#EA580C" strokeWidth="1.2" />
      <path d="M12 4v16M4 12h16" stroke="#FFF7ED" strokeWidth="1.2" opacity="0.8" />
    </svg>
  )
}

function IconCar({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M4 14h16l-1.5-5a2 2 0 00-1.9-1.4H7.4A2 2 0 005.5 9L4 14z" fill="#60A5FA" stroke="#2563EB" strokeWidth="1.2" />
      <circle cx="8" cy="16" r="1.5" fill="#1E3A8A" />
      <circle cx="16" cy="16" r="1.5" fill="#1E3A8A" />
    </svg>
  )
}

function IconDoll({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <circle cx="12" cy="7" r="3.5" fill="#F9A8D4" stroke="#DB2777" strokeWidth="1.2" />
      <path d="M7 20c1-4 10-4 10 0" fill="#F472B6" stroke="#DB2777" strokeWidth="1.2" />
    </svg>
  )
}

function IconBook({ size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} fill="none">
      <path d="M5 4h7a3 3 0 013 3v14a2.5 2.5 0 00-2.5-2H5V4z" fill="#A78BFA" stroke="#7C3AED" strokeWidth="1.2" />
      <path d="M19 4h-7a3 3 0 00-3 3v14a2.5 2.5 0 012.5-2H19V4z" fill="#C4B5FD" stroke="#7C3AED" strokeWidth="1.2" />
    </svg>
  )
}

const RULES: Array<{ keys: string[]; config: CategoryIconConfig }> = [
  { keys: ['baby'], config: { bg: 'bg-[#FFF3D6]', Icon: IconBaby } },
  { keys: ['soft', 'plush'], config: { bg: 'bg-[#FCE7F3]', Icon: IconTeddy } },
  { keys: ['fashion', 'costume'], config: { bg: 'bg-[#FDF2F8]', Icon: IconFashion } },
  { keys: ['stationery', 'school', 'bag'], config: { bg: 'bg-[#FEF9C3]', Icon: IconPencil } },
  { keys: ['electronic', 'mobile', 'electric'], config: { bg: 'bg-[#DBEAFE]', Icon: IconRobot } },
  { keys: ['home', 'household'], config: { bg: 'bg-[#D1FAE5]', Icon: IconHome } },
  { keys: ['party', 'seasonal', 'water'], config: { bg: 'bg-[#FFEDD5]', Icon: IconGift } },
  { keys: ['educational', 'puzzle', 'cube', 'game'], config: { bg: 'bg-[#E0E7FF]', Icon: IconBlocks } },
  { keys: ['sport', 'outdoor', 'racket', 'football'], config: { bg: 'bg-[#DCFCE7]', Icon: IconBall } },
  { keys: ['arts', 'craft', 'slime', 'clay', 'draw', 'musical'], config: { bg: 'bg-[#F3E8FF]', Icon: IconSparkle } },
  { keys: ['ride', 'vehicle', 'car', 'tricycle'], config: { bg: 'bg-[#E0F2FE]', Icon: IconCar } },
  { keys: ['doll', 'pretend', 'character'], config: { bg: 'bg-[#FCE7F3]', Icon: IconDoll } },
  { keys: ['action', 'gun', 'bubble'], config: { bg: 'bg-[#FEE2E2]', Icon: IconPlane } },
  { keys: ['entertain'], config: { bg: 'bg-[#FFE4E6]', Icon: IconCake } },
  { keys: ['book', 'beauty', 'gum'], config: { bg: 'bg-[#EDE9FE]', Icon: IconBook } },
  { keys: ['toy'], config: { bg: 'bg-[#FFF3C4]', Icon: IconTeddy } },
]

const FALLBACKS: CategoryIconConfig[] = [
  { bg: 'bg-[#FFF3C4]', Icon: IconTeddy },
  { bg: 'bg-[#DBEAFE]', Icon: IconRobot },
  { bg: 'bg-[#FEF9C3]', Icon: IconBlocks },
  { bg: 'bg-[#D1FAE5]', Icon: IconBall },
  { bg: 'bg-[#F3E8FF]', Icon: IconGift },
  { bg: 'bg-[#FFEDD5]', Icon: IconPlane },
  { bg: 'bg-[#FFF3D6]', Icon: IconBaby },
  { bg: 'bg-[#E0E7FF]', Icon: IconSparkle },
]

function normalize(name: string) {
  return name.toLowerCase().replace(/&/g, 'and').replace(/\s+/g, ' ')
}

export function getCategoryMenuIcon(name: string, seed = 0): CategoryIconConfig {
  const haystack = normalize(name)
  for (const rule of RULES) {
    if (rule.keys.some((key) => haystack.includes(key))) {
      return rule.config
    }
  }
  return FALLBACKS[Math.abs(seed) % FALLBACKS.length]
}
