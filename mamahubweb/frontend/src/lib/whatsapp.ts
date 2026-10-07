const DEFAULT_WHATSAPP_NUMBER = '97472352255'

export function getWhatsAppNumber(): string | null {
  const raw = import.meta.env.VITE_WHATSAPP_NUMBER
  if (raw === '') return null

  let digits = (raw?.trim() || DEFAULT_WHATSAPP_NUMBER).replace(/\D/g, '')
  if (digits.startsWith('00')) digits = digits.slice(2)
  return digits || null
}

export function buildWhatsAppUrl(number: string, message?: string): string {
  const base = `https://wa.me/${number}`
  const text = message?.trim()
  if (!text) return base
  return `${base}?text=${encodeURIComponent(text)}`
}
