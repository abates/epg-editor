import { error } from '@sveltejs/kit'

const MAX_LIMIT = 200

// ?limit=, defaulting when absent; 400 when it is not a whole number between 1 and 200
export function limitParam(url: URL, fallback: number): number {
  const value = url.searchParams.get('limit')
  if (value === null || value === '') return fallback
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > MAX_LIMIT)
    error(400, `"limit" must be between 1 and ${MAX_LIMIT}`)

  return Number(value)
}
