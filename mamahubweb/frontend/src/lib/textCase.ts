/** Title case for catalog labels — e.g. "bath soap" → "Bath Soap". */
export function toTitleCase(text: string): string {
  return text.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

/** Sentence case — e.g. "HELLO WORLD" → "Hello world". */
export function toSentenceCase(text: string): string {
  const lower = text.toLowerCase().trim()
  if (!lower) return lower
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}
