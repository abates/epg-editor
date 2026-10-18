// Comma or whitespace separated list, lower-cased, de-duplicated, order kept ("us, CA" → ["us", "ca"])
export function parseList(value: FormDataEntryValue | null): string[] {
  if (typeof value !== 'string') return []

  const items = value
    .split(/[\s,]+/)
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)

  return [...new Set(items)]
}

// Blank means "use the default" (undefined); anything else must be a whole number in range
export function parseOptionalInteger(
  value: FormDataEntryValue | null,
  options: { min?: number; max?: number } = {}
): number | undefined {
  if (typeof value !== 'string' || !value.trim()) return undefined

  const text = value.trim()
  const min = options.min ?? 0
  const max = options.max ?? Number.MAX_SAFE_INTEGER
  if (!/^\d+$/.test(text) || Number(text) < min || Number(text) > max)
    throw new Error(`must be a whole number between ${min} and ${max}`)

  return Number(text)
}

// Server errors are lower-case (epg logging style); form messages start with a capital
export function toSentence(message: string): string {
  return message.charAt(0).toUpperCase() + message.slice(1)
}
