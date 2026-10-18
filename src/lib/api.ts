import type { ChannelRowData } from '$lib/types/channel'
import type { DatabaseChannelData } from '$lib/types/database'
import type { GuideEntryData } from '$lib/types/guide'
import type { GuideEntryField } from '$lib/core/mappingValidation'
import type { MappingRequestData } from '$lib/types/mapping'
import type { SuggestionData } from '$lib/types/suggestion'

// Browser-side calls to the /api endpoints. Failures throw with the server's message
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export interface MappingResponse {
  row: ChannelRowData
  warnings: string[]
}

export type SaveMappingResponse =
  | ({ ok: true } & MappingResponse)
  | { ok: false; errors: Partial<Record<GuideEntryField, string>>; warnings: string[] }

export async function getSuggestions(slug: string, key: string): Promise<SuggestionData[]> {
  const params = new URLSearchParams({ key })
  const { suggestions } = await request(`/api/lineups/${slug}/suggestions?${params}`)

  return suggestions
}

export async function searchEntries(
  query: string,
  filters: { site?: string; country?: string; lang?: string }
): Promise<GuideEntryData[]> {
  const params = new URLSearchParams({ q: query })
  for (const [name, value] of Object.entries(filters)) if (value) params.set(name, value)
  const { entries } = await request(`/api/entries?${params}`)

  return entries
}

export async function searchDatabase(query: string): Promise<DatabaseChannelData[]> {
  const { channels } = await request(`/api/database?${new URLSearchParams({ q: query })}`)

  return channels
}

export async function saveMapping(
  slug: string,
  mapping: MappingRequestData
): Promise<SaveMappingResponse> {
  const response = await fetch(`/api/lineups/${slug}/mappings`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(mapping)
  })
  if (response.status === 422) return { ok: false, ...(await response.json()) }

  return { ok: true, ...(await parse(response)) }
}

export async function clearMapping(slug: string, key: string): Promise<MappingResponse> {
  const params = new URLSearchParams({ key })

  return request(`/api/lineups/${slug}/mappings?${params}`, { method: 'DELETE' })
}

async function request(url: string, init?: RequestInit) {
  return parse(await fetch(url, init))
}

async function parse(response: Response) {
  if (response.ok) return response.json()

  const body = await response.json().catch(() => null)
  throw new ApiError(response.status, body?.message ?? `Request failed: HTTP ${response.status}`)
}
