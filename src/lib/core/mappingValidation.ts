import type { BulkMappingRequestData, MappingRequestData } from '$lib/types/mapping'
import { XMLTV_ID_PATTERN } from './xmltvId'
import { isValidSlug } from './slug'

const LANG_PATTERN = /^[a-z]{2}$/

export interface GuideEntryInput {
  site: string
  site_id: string
  lang: string | null
  xmltv_id: string
}

export type GuideEntryField = keyof GuideEntryInput

export interface GuideEntryLookup {
  hasSite(site: string): boolean
  // Left out when the iptv-org database is not loaded; the "not in database" warning is skipped
  hasXmltvId?(xmltvId: string): boolean
}

export interface GuideEntryValidation {
  value: GuideEntryInput
  errors: Partial<Record<GuideEntryField, string>>
  warnings: string[]
}

// FR-E-2: errors block saving a manual entry, warnings are shown but don't
export function validateGuideEntry(
  input: GuideEntryInput,
  lookup: GuideEntryLookup
): GuideEntryValidation {
  const value: GuideEntryInput = {
    site: input.site.trim(),
    site_id: input.site_id.trim(),
    lang: input.lang?.trim() || null,
    xmltv_id: input.xmltv_id.trim()
  }
  const errors: GuideEntryValidation['errors'] = {}
  const warnings: string[] = []

  if (!value.site) errors.site = 'Site is required'
  else if (!isValidSlug(value.site) || !lookup.hasSite(value.site))
    errors.site = `Unknown site "${value.site}"`

  if (!value.site_id) errors.site_id = 'Site ID is required'

  if (value.lang && !LANG_PATTERN.test(value.lang))
    errors.lang = 'Language must be a two-letter ISO 639-1 code'

  if (!value.xmltv_id) {
    warnings.push('Without an xmltv_id the guide has no logo from the iptv-org database')
  } else if (!XMLTV_ID_PATTERN.test(value.xmltv_id)) {
    errors.xmltv_id = 'xmltv_id must look like ChannelID.cc or ChannelID.cc@Feed'
  } else if (lookup.hasXmltvId && !lookup.hasXmltvId(value.xmltv_id)) {
    warnings.push(`"${value.xmltv_id}" is not in the iptv-org database`)
  }

  return { value, errors, warnings }
}

// Shape check of a PUT /api/lineups/<slug>/mappings body; throws with a message for a 400
export function parseMappingRequest(body: unknown): MappingRequestData {
  if (!isObject(body)) throw new Error('Expected a JSON object')

  const key = body.key
  if (typeof key !== 'string' || !key) throw new Error('"key" is required')

  if (body.status === 'skipped') return { key, status: 'skipped' }
  if (body.status !== 'mapped') throw new Error('"status" must be "mapped" or "skipped"')

  if (isObject(body.entry)) return { key, status: 'mapped', entry: parseEntry(body.entry) }

  if (isObject(body.manual)) {
    const { site, site_id, lang, xmltv_id } = body.manual
    if (
      typeof site !== 'string' ||
      typeof site_id !== 'string' ||
      typeof xmltv_id !== 'string' ||
      (lang !== null && lang !== undefined && typeof lang !== 'string')
    )
      throw new Error('"manual" needs "site", "site_id", "lang" and "xmltv_id"')

    return { key, status: 'mapped', manual: { site, site_id, lang: lang ?? null, xmltv_id } }
  }

  throw new Error('A mapped channel needs "entry" or "manual"')
}

// Shape check of a POST /api/lineups/<slug>/mappings/bulk body [FR-P-7]
export function parseBulkMappingRequest(body: unknown): BulkMappingRequestData {
  if (!isObject(body) || !Array.isArray(body.items)) throw new Error('"items" must be an array')
  if (!body.items.length) throw new Error('"items" is empty')

  const keys = new Set<string>()
  const items = body.items.map(item => {
    if (!isObject(item)) throw new Error('Each item must be a JSON object')
    const key = item.key
    if (typeof key !== 'string' || !key) throw new Error('"key" is required')
    if (keys.has(key)) throw new Error(`Channel "${key}" is listed twice`)
    keys.add(key)
    if (!isObject(item.entry)) throw new Error('Each item needs an "entry"')

    return { key, entry: parseEntry(item.entry) }
  })

  return { items }
}

function parseEntry(entry: Record<string, unknown>): { site: string; site_id: string } {
  const { site, site_id } = entry
  if (typeof site !== 'string' || typeof site_id !== 'string')
    throw new Error('"entry" needs "site" and "site_id"')

  return { site, site_id }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
