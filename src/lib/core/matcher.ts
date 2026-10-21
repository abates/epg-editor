import type { MatchReasonData, SuggestionData } from '$lib/types/suggestion'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { LineupFiltersData } from '$lib/types/lineup'
import type { GuideEntryData } from '$lib/types/guide'
import MiniSearch, { type SearchOptions } from 'minisearch'

// US/CA/MX broadcast call sign [FR-S-2]
const CALL_SIGN = /^[KWCX][A-Z]{2,3}$/
// A call sign inside an entry name, with an optional sub-channel: WCBS-DT2, KOVR2, WPXO-LD1
const NAME_CALL_SIGN =
  /(?<![A-Za-z0-9])([KWCX][A-Z]{2,3})(?:-?(?:DT|TV|LD|CD|LP|D))?(\d{1,2})?(?![A-Za-z0-9])/g
// What may follow the call sign in an xmltv_id channel part: WCBSTV21, WRCDT3, WGNHD, WPIX71
const XMLTV_CALL_SIGN_REST = /^(?:TV|DT|LD|CD|LP|HD|D)?\d*$/
// Feed and quality markers: WCBS-HD, WPIX.2, WCBS*NX, KXYZ-LD
const NAME_SUFFIX = /[-.*](?:HD|SD|DT\d*|LD\d*|CD\d*|NX|\d+)(?![A-Za-z0-9])/gi
const IGNORED_TOKENS = new Set(['hd', 'sd', 'fhd', 'uhd'])

// Points per signal [FR-S-3]. tests/core/matcher.test.ts documents how each one behaves
export const MATCH_WEIGHTS = {
  callSign: 40,
  // Call sign taken from the lineup's x.1 channel; only counts when the entry names a sub-channel
  inheritedCallSign: 20,
  subChannel: 15,
  subChannelMismatch: -25,
  // Multiplied by the 0..1 name similarity
  name: 40,
  country: 10,
  countryMismatch: -15,
  // First preferred site gets the full amount, later ones less
  preferredSite: 10,
  // Small, because most upstream entries have no xmltv_id
  noXmltvId: -3
}

export type MatchWeights = typeof MATCH_WEIGHTS

export const SUGGESTION_LIMIT = 10
const CANDIDATE_LIMIT = 100
const SEARCH_LIMIT = 50

export interface ChannelFeatures {
  tokens: string[]
  callSign: string | null
  inheritedCallSign: boolean
  subChannel: number | null
}

interface EntryCallSign {
  callSign: string
  subChannel: number | null
}

export interface EntrySearchOptions {
  site?: string
  country?: string
  lang?: string
  limit?: number
}

// Lower-case name tokens without feed/quality suffixes or channel numbers [FR-S-2]
export function tokenizeName(name: string): string[] {
  return name
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/(?<![\p{L}\p{N}])\d+\.\d+(?![\p{L}\p{N}])/gu, ' ')
    .replace(NAME_SUFFIX, ' ')
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter(token => token && !IGNORED_TOKENS.has(token))
}

// Call sign from the start of an M3U name ("WCBS-HD", "WPIX.2", "WCBS*NX")
export function callSignFromName(name: string): string | null {
  const first = name.trim().split(/[^A-Za-z0-9]+/)[0]

  return CALL_SIGN.test(first) ? first : null
}

// major channel number → call sign, so "2.2 StartTV" can use the call sign of "2.1 WCBS-HD"
export function lineupCallSigns(items: PlaylistItemData[]): Map<string, string> {
  const found = new Map<string, { callSign: string; minor: number }>()

  for (const item of items) {
    const callSign = callSignFromName(item.name)
    const number = parseChannelNumber(item.number)
    if (!callSign || !number) continue
    const current = found.get(number.major)
    if (!current || number.minor < current.minor)
      found.set(number.major, { callSign, minor: number.minor })
  }

  return new Map([...found].map(([major, { callSign }]) => [major, callSign]))
}

export function extractFeatures(
  item: PlaylistItemData,
  callSigns: Map<string, string> = new Map()
): ChannelFeatures {
  const number = parseChannelNumber(item.number)
  const own = callSignFromName(item.name)
  const inherited = !own && number ? (callSigns.get(number.major) ?? null) : null

  return {
    tokens: tokenizeName(item.name),
    callSign: own ?? inherited,
    inheritedCallSign: !!inherited,
    subChannel: number?.minor ?? null
  }
}

// Suggestions and entry search over the guide index. Build once per index (the MiniSearch
// index takes a moment for ~180k entries) and reuse it for every lineup [FR-S-6]
export class Matcher {
  readonly entries: GuideEntryData[]
  readonly weights: MatchWeights
  private readonly search: MiniSearch<{ id: number; name: string }>
  private readonly byCallSign: Map<string, number[]>

  constructor(entries: GuideEntryData[], weights: MatchWeights = MATCH_WEIGHTS) {
    this.entries = entries
    this.weights = weights
    this.search = new MiniSearch({ fields: ['name'], tokenize: tokenizeName })
    this.search.addAll(entries.map((entry, id) => ({ id, name: entry.name })))

    this.byCallSign = new Map()
    entries.forEach((entry, id) => {
      for (const callSign of new Set(entryCallSigns(entry).map(found => found.callSign))) {
        const ids = this.byCallSign.get(callSign)
        if (ids) ids.push(id)
        else this.byCallSign.set(callSign, [id])
      }
    })
  }

  // Ranked guide entries for one M3U channel, best first [FR-P-3, FR-S-3, FR-S-4]
  suggest(
    item: PlaylistItemData,
    filters: LineupFiltersData,
    options: { callSigns?: Map<string, string>; limit?: number } = {}
  ): SuggestionData[] {
    const features = extractFeatures(item, options.callSigns)
    const allowed = (id: number) => matchesLanguage(this.entries[id], filters.languages)

    const candidates = new Set<number>()
    if (features.tokens.length) {
      // The joined form finds "NBCLX" for "NBC LX" among hundreds of "NBC ..." entries
      const joined = features.tokens.length > 1 ? [features.tokens.join('')] : []
      const results = this.search.search([...features.tokens, ...joined].join(' '), {
        ...FUZZY_SEARCH,
        filter: result => allowed(result.id)
      })
      for (const result of results.slice(0, CANDIDATE_LIMIT)) candidates.add(result.id)
    }
    if (features.callSign) {
      for (const id of this.byCallSign.get(features.callSign) ?? []) {
        if (allowed(id)) candidates.add(id)
      }
    }

    return [...candidates]
      .map(id => this.score(this.entries[id], features, filters))
      .sort(compareSuggestions)
      .slice(0, options.limit ?? SUGGESTION_LIMIT)
      .map(suggestion => ({ ...suggestion, score: round(suggestion.score) }))
  }

  // Free-text search for the manual Search tab; an empty query lists entries in index order
  find(query: string, options: EntrySearchOptions = {}): GuideEntryData[] {
    const limit = options.limit ?? SEARCH_LIMIT
    const allowed = (entry: GuideEntryData) =>
      (!options.site || entry.site === options.site) &&
      (!options.country || entry.country === options.country) &&
      (!options.lang || entry.lang === options.lang)

    if (!tokenizeName(query).length) return this.entries.filter(allowed).slice(0, limit)

    return this.search
      .search(query, {
        ...FUZZY_SEARCH,
        combineWith: 'AND',
        filter: r => allowed(this.entries[r.id])
      })
      .slice(0, limit)
      .map(result => this.entries[result.id])
  }

  private score(
    entry: GuideEntryData,
    features: ChannelFeatures,
    filters: LineupFiltersData
  ): SuggestionData {
    const weights = this.weights
    const reasons: MatchReasonData[] = []
    const add = (kind: MatchReasonData['kind'], points: number, detail: string) => {
      if (points) reasons.push({ kind, points: round(points), detail })
    }

    const found = features.callSign
      ? entryCallSigns(entry).filter(found => found.callSign === features.callSign)
      : []
    const explicit = found.map(found => found.subChannel).filter(sub => sub !== null)
    // A call sign inherited from the lineup only counts when the entry names a sub-channel
    if (found.length && (!features.inheritedCallSign || explicit.length)) {
      if (features.inheritedCallSign)
        add(
          'inheritedCallSign',
          weights.inheritedCallSign,
          `call sign ${features.callSign} (lineup)`
        )
      else add('callSign', weights.callSign, `call sign ${features.callSign}`)

      // An entry that names no sub-channel is taken to be the main (x.1) feed
      const subChannels = explicit.length ? explicit : [1]
      if (features.subChannel !== null && !subChannels.includes(features.subChannel))
        add('subChannelMismatch', weights.subChannelMismatch, `sub-channel ${subChannels[0]}`)
      else if (features.subChannel !== null && explicit.length)
        add('subChannel', weights.subChannel, `sub-channel ${features.subChannel}`)
    }

    // A name that is only the call sign ("WCBS-HD") was already scored above
    const nameIsCallSign =
      !!found.length &&
      !features.inheritedCallSign &&
      features.tokens.join('') === features.callSign?.toLowerCase()
    const similarity = nameIsCallSign
      ? 0
      : nameSimilarity(features.tokens, tokenizeName(stripParentheses(entry.name)))
    if (similarity > 0)
      add('name', weights.name * similarity, `name ${Math.round(similarity * 100)}% similar`)

    if (entry.country && filters.countries.length) {
      if (filters.countries.includes(entry.country))
        add('country', weights.country, `country ${entry.country}`)
      else add('countryMismatch', weights.countryMismatch, `country ${entry.country}`)
    }

    const rank = filters.preferredSites.indexOf(entry.site)
    if (rank >= 0) {
      const points = weights.preferredSite * (1 - rank / filters.preferredSites.length)
      add('preferredSite', points, `preferred site #${rank + 1}`)
    }

    if (!entry.xmltv_id)
      add('noXmltvId', weights.noXmltvId, 'no xmltv_id (not in the iptv-org database)')

    return { entry, score: reasons.reduce((sum, reason) => sum + reason.points, 0), reasons }
  }
}

// Call signs an entry refers to, from its name and from the channel part of its xmltv_id
export function entryCallSigns(entry: GuideEntryData): EntryCallSign[] {
  const found: EntryCallSign[] = []

  for (const match of entry.name.matchAll(NAME_CALL_SIGN)) {
    found.push({ callSign: match[1], subChannel: match[2] ? Number(match[2]) : null })
  }

  const channel = entry.xmltv_id.split('@')[0].replace(/\.[a-z]{2}$/, '')
  for (const length of [3, 4]) {
    const callSign = channel.slice(0, length)
    const rest = channel.slice(length)
    if (!CALL_SIGN.test(callSign) || !XMLTV_CALL_SIGN_REST.test(rest)) continue
    // Only an explicit DTn is a sub-channel; digits in ids like WCBSTV212 are ambiguous
    const subChannel = rest.match(/^DT(\d+)$/)?.[1]
    found.push({ callSign, subChannel: subChannel ? Number(subChannel) : null })
  }

  return found
}

// 0..1, mostly "how much of the M3U name is in the entry name", with a little Dice
// coefficient so a tight match ("Start TV") beats a longer one ("Start TV New York NY").
// Character bigrams of the joined tokens, so "StartTV" ~ "Start TV" and "NBC LX" ~ "NBCLX"
export function nameSimilarity(query: string[], entry: string[]): number {
  const a = query.join('')
  const b = entry.join('')
  if (!a || !b) return 0
  if (a === b) return 1
  if (a.length < 2 || b.length < 2) return 0

  const counts = new Map<string, number>()
  for (const bigram of bigrams(b)) counts.set(bigram, (counts.get(bigram) ?? 0) + 1)

  let common = 0
  const queryBigrams = bigrams(a)
  for (const bigram of queryBigrams) {
    const count = counts.get(bigram) ?? 0
    if (count) {
      common++
      counts.set(bigram, count - 1)
    }
  }

  const coverage = common / queryBigrams.length
  const dice = (2 * common) / (queryBigrams.length + b.length - 1)

  return 0.75 * coverage + 0.25 * dice
}

const FUZZY_SEARCH: SearchOptions = {
  // Fuzzy and prefix matching on short terms is slow and noisy (FR-S-6)
  fuzzy: term => (term.length > 4 ? 0.2 : false),
  prefix: term => term.length >= 3
}

function bigrams(value: string): string[] {
  const result: string[] = []
  for (let i = 0; i < value.length - 1; i++) result.push(value.slice(i, i + 2))

  return result
}

// "CBS (WCBS-DT1) New York, NY" → "CBS New York, NY": the call sign is scored separately
function stripParentheses(name: string): string {
  return name.replace(/\([^)]*\)/g, ' ')
}

function matchesLanguage(entry: GuideEntryData, languages: string[]): boolean {
  return !languages.length || !entry.lang || languages.includes(entry.lang)
}

function parseChannelNumber(number: string | null): { major: string; minor: number } | null {
  const match = number?.match(/^(\d+)(?:\.(\d+))?$/)
  if (!match) return null

  return { major: match[1], minor: match[2] ? Number(match[2]) : 1 }
}

// Score first, then a fixed order so equal scores never depend on index order or locale [FR-S-4]
function compareSuggestions(a: SuggestionData, b: SuggestionData): number {
  return (
    b.score - a.score ||
    compareStrings(a.entry.site, b.entry.site) ||
    compareStrings(a.entry.site_id, b.entry.site_id)
  )
}

function compareStrings(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

function round(value: number): number {
  return Math.round(value * 10) / 10
}
