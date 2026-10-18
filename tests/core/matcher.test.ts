import {
  MATCH_WEIGHTS,
  Matcher,
  callSignFromName,
  entryCallSigns,
  extractFeatures,
  lineupCallSigns,
  nameSimilarity,
  tokenizeName
} from '$lib/core/matcher'
import type { LineupFiltersData } from '$lib/types/lineup'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { GuideEntryData } from '$lib/types/guide'
import { parsePlaylist } from '$lib/core/playlistParser'
import { countryFromXmltvId } from '$lib/core/xmltvId'
import { GuideIndex } from '$lib/server/guideIndex'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'

const US: LineupFiltersData = { countries: ['us'], languages: [], preferredSites: [] }

function item(number: string | null, name: string): PlaylistItemData {
  return {
    key: number ?? name,
    number,
    name,
    url: 'http://x',
    logo: null,
    group: null,
    attributes: {}
  }
}

function entry(site: string, site_id: string, name: string, xmltv_id = ''): GuideEntryData {
  return {
    site,
    site_id,
    lang: 'en',
    xmltv_id,
    name,
    logo: null,
    country: countryFromXmltvId(xmltv_id),
    origin: 'upstream'
  }
}

function reasons(matcher: Matcher, channel: PlaylistItemData, filters = US, items = [channel]) {
  const [top] = matcher.suggest(channel, filters, { callSigns: lineupCallSigns(items) })

  return Object.fromEntries(top.reasons.map(reason => [reason.kind, reason.points]))
}

describe('tokenizeName', () => {
  it('strips feed suffixes, sub-channel numbers, punctuation and case [FR-S-2]', () => {
    expect(tokenizeName('WCBS-HD')).toEqual(['wcbs'])
    expect(tokenizeName('WPIX.2')).toEqual(['wpix'])
    expect(tokenizeName('WNET 13.2')).toEqual(['wnet'])
    expect(tokenizeName('WCBS*NX')).toEqual(['wcbs'])
    expect(tokenizeName('KXYZ-LD')).toEqual(['kxyz'])
    expect(tokenizeName('Charge!')).toEqual(['charge'])
    expect(tokenizeName('CBS (WCBS-DT1) New York, NY')).toEqual([
      'cbs',
      'wcbs',
      'new',
      'york',
      'ny'
    ])
  })

  it('splits camel case and folds accents', () => {
    expect(tokenizeName('StartTV')).toEqual(['start', 'tv'])
    expect(tokenizeName('Télé-Québec')).toEqual(['tele', 'quebec'])
  })
})

describe('callSignFromName', () => {
  it('finds a US/CA/MX call sign at the start of the name', () => {
    expect(callSignFromName('WCBS-HD')).toBe('WCBS')
    expect(callSignFromName('WPIX.2')).toBe('WPIX')
    expect(callSignFromName('WCBS*NX')).toBe('WCBS')
    expect(callSignFromName('KYW')).toBe('KYW')
    expect(callSignFromName('CBLT-DT')).toBe('CBLT')
  })

  it('ignores names that are not call signs', () => {
    expect(callSignFromName('ION')).toBeNull()
    expect(callSignFromName('StartTV')).toBeNull()
    expect(callSignFromName('Charge!')).toBeNull()
    expect(callSignFromName('wcbs')).toBeNull()
  })
})

describe('lineupCallSigns', () => {
  it('maps each major channel number to the call sign of its lowest sub-channel', () => {
    const items = [item('2.2', 'StartTV'), item('2.1', 'WCBS-HD'), item('31.1', 'ION')]

    expect(lineupCallSigns(items)).toEqual(new Map([['2', 'WCBS']]))
  })
})

describe('extractFeatures', () => {
  it('inherits the call sign from the lineup when the name has none', () => {
    const callSigns = new Map([['2', 'WCBS']])

    expect(extractFeatures(item('2.2', 'StartTV'), callSigns)).toEqual({
      tokens: ['start', 'tv'],
      callSign: 'WCBS',
      inheritedCallSign: true,
      subChannel: 2
    })
    expect(extractFeatures(item('11.2', 'WPIX.2'), callSigns)).toEqual({
      tokens: ['wpix'],
      callSign: 'WPIX',
      inheritedCallSign: false,
      subChannel: 2
    })
    expect(extractFeatures(item(null, 'ION')).subChannel).toBeNull()
  })
})

describe('entryCallSigns', () => {
  it('reads call signs and sub-channels from entry names', () => {
    const found = (name: string) => entryCallSigns(entry('x', '1', name))

    expect(found('Start TV (WCBS-DT2) New York, NY')).toEqual([{ callSign: 'WCBS', subChannel: 2 }])
    expect(found('Start TV (KOVR2) Sacramento, CA')).toEqual([{ callSign: 'KOVR', subChannel: 2 }])
    expect(found('América TeVé (WPXO-LD) East Orange, NJ')).toEqual([
      { callSign: 'WPXO', subChannel: null }
    ])
    expect(found('WCBS (New York) CBS East')).toContainEqual({ callSign: 'WCBS', subChannel: null })
  })

  it('reads the call sign from the xmltv_id channel part', () => {
    const found = (xmltv_id: string) =>
      entryCallSigns(entry('x', '1', 'Name', xmltv_id)).map(found => found.callSign)

    expect(found('WCBSTV21.us@HD')).toEqual(['WCBS'])
    expect(found('WPIX71.us@HD')).toEqual(['WPIX'])
    expect(found('WRCDT3.us@SD')).toEqual(['WRC'])
    expect(found('WGNHD.us@SD')).toContain('WGN')
    expect(found('NBCLX.us@SD')).toEqual([])
  })

  it('treats an explicit DTn in the xmltv_id as the sub-channel', () => {
    expect(entryCallSigns(entry('x', '1', 'WPIX QVC', 'WPIXDT5.us@SD'))).toContainEqual({
      callSign: 'WPIX',
      subChannel: 5
    })
  })
})

describe('nameSimilarity', () => {
  it('is 1 for the same name and 0 for nothing in common', () => {
    expect(nameSimilarity(['start', 'tv'], ['start', 'tv'])).toBe(1)
    expect(nameSimilarity(['start', 'tv'], ['starttv'])).toBe(1)
    expect(nameSimilarity(['ion'], ['bounce'])).toBe(0)
  })

  it('prefers a tight match over a longer name that contains it', () => {
    const tight = nameSimilarity(['start', 'tv'], ['start', 'tv'])
    const longer = nameSimilarity(['start', 'tv'], ['start', 'tv', 'new', 'york', 'ny'])

    expect(longer).toBeGreaterThan(0.75)
    expect(longer).toBeLessThan(tight)
  })
})

// One test per FR-S-3 signal, so a change to MATCH_WEIGHTS shows up here
describe('Matcher scoring', () => {
  it('scores an exact call sign and a confirmed sub-channel', () => {
    const matcher = new Matcher([
      entry('tvtv.us', '1', 'CBS (WCBS-DT1) New York, NY', 'WCBSTV21.us@HD')
    ])

    expect(reasons(matcher, item('2.1', 'WCBS-HD'))).toEqual({
      callSign: MATCH_WEIGHTS.callSign,
      subChannel: MATCH_WEIGHTS.subChannel,
      country: MATCH_WEIGHTS.country
    })
  })

  it('does not score the name again when it is only the call sign', () => {
    const matcher = new Matcher([entry('a', '1', 'WCBS', 'WCBSTV21.us@HD')])

    expect(reasons(matcher, item('2.1', 'WCBS-HD'))).not.toHaveProperty('name')
  })

  it('penalises a different sub-channel, treating entries without one as x.1', () => {
    const matcher = new Matcher([entry('a', '1', 'WPIX', 'WPIX71.us@HD')])

    expect(reasons(matcher, item('11.2', 'WPIX.2'))).toMatchObject({
      callSign: MATCH_WEIGHTS.callSign,
      subChannelMismatch: MATCH_WEIGHTS.subChannelMismatch
    })
  })

  it('counts an inherited call sign only when the entry names a sub-channel', () => {
    const items = [item('2.1', 'WCBS-HD'), item('2.2', 'StartTV')]
    const confirmed = new Matcher([entry('a', '1', 'Start TV (WCBS-DT2) New York, NY')])
    const unconfirmed = new Matcher([entry('a', '1', 'WCBS (New York) CBS East')])

    expect(reasons(confirmed, items[1], US, items)).toMatchObject({
      inheritedCallSign: MATCH_WEIGHTS.inheritedCallSign,
      subChannel: MATCH_WEIGHTS.subChannel
    })
    expect(reasons(unconfirmed, items[1], US, items)).not.toHaveProperty('inheritedCallSign')
  })

  it('scales name similarity by the name weight', () => {
    const matcher = new Matcher([entry('a', '1', 'Start TV', 'StartTV.us@SD')])

    expect(reasons(matcher, item('2.2', 'StartTV')).name).toBe(MATCH_WEIGHTS.name)
  })

  it('rewards the lineup country and penalises other countries', () => {
    const matcher = new Matcher([
      entry('a', 'us', 'Charge!', 'Charge.us@SD'),
      entry('a', 'ca', 'Charge!', 'Charge.ca@SD')
    ])
    const [us, ca] = matcher.suggest(item('63.1', 'Charge!'), US)

    expect(us.entry.site_id).toBe('us')
    expect(us.score - ca.score).toBe(MATCH_WEIGHTS.country - MATCH_WEIGHTS.countryMismatch)
  })

  it('ranks preferred sites in order', () => {
    const matcher = new Matcher([
      entry('a.com', '1', 'Charge!', 'Charge.us@SD'),
      entry('b.com', '1', 'Charge!', 'Charge.us@SD'),
      entry('c.com', '1', 'Charge!', 'Charge.us@SD')
    ])
    const filters = { ...US, preferredSites: ['c.com', 'b.com'] }
    const suggestions = matcher.suggest(item('63.1', 'Charge!'), filters)

    expect(suggestions.map(suggestion => suggestion.entry.site)).toEqual([
      'c.com',
      'b.com',
      'a.com'
    ])
    expect(suggestions[0].reasons).toContainEqual({
      kind: 'preferredSite',
      points: MATCH_WEIGHTS.preferredSite,
      detail: 'preferred site #1'
    })
    expect(suggestions[1].reasons).toContainEqual({
      kind: 'preferredSite',
      points: MATCH_WEIGHTS.preferredSite / 2,
      detail: 'preferred site #2'
    })
  })

  it('ranks entries without an xmltv_id slightly lower', () => {
    const matcher = new Matcher([entry('a', '1', 'Bounce'), entry('b', '1', 'Bounce', 'Bounce.us')])
    const [first, second] = matcher.suggest(item('31.2', 'Bounce'), { ...US, countries: [] })

    expect(first.entry.site).toBe('b')
    expect(first.score - second.score).toBe(-MATCH_WEIGHTS.noXmltvId)
  })

  it('only suggests entries in the lineup languages', () => {
    const matcher = new Matcher([
      { ...entry('digea.gr', '1', 'ION'), lang: 'el' },
      entry('plex.tv', '1', 'ION', 'IONTV.us@East')
    ])
    const sites = (languages: string[]) =>
      matcher.suggest(item('31.1', 'ION'), { ...US, languages }).map(s => s.entry.site)

    expect(sites([])).toEqual(['plex.tv', 'digea.gr'])
    expect(sites(['en'])).toEqual(['plex.tv'])
  })

  it('accepts custom weights', () => {
    const weights = { ...MATCH_WEIGHTS, country: 0, countryMismatch: 0 }
    const matcher = new Matcher([entry('a', '1', 'Charge!', 'Charge.ca@SD')], weights)

    expect(matcher.suggest(item('63.1', 'Charge!'), US)[0].score).toBe(MATCH_WEIGHTS.name)
  })
})

describe('Matcher with the fixture lineup', async () => {
  const index = await GuideIndex.load('tests/__data__/input/matcher/sites')
  const { items } = parsePlaylist(fs.readFileSync('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8'))
  const expected: Record<string, string[]> = JSON.parse(
    fs.readFileSync('tests/__data__/expected/matcher/hdhomerun.json', 'utf8')
  )
  const callSigns = lineupCallSigns(items)
  const matcher = new Matcher(index.entries)
  const suggest = (m: Matcher) =>
    items.map(item =>
      m.suggest(item, US, { callSigns }).map(s => `${s.entry.site}/${s.entry.site_id}`)
    )

  it('loads the fixture without errors', () => {
    expect(index.errors).toEqual([])
    expect(Object.keys(expected).sort()).toEqual(items.map(item => item.key).sort())
  })

  // FR-S acceptance metric: >= 70 % of channels have a correct entry in the top 3
  it('puts a correct entry in the top 3 for at least 70 % of channels', () => {
    const ranked = suggest(matcher)
    const misses = items.filter(
      (item, i) => !ranked[i].slice(0, 3).some(id => expected[item.key].includes(id))
    )

    expect(misses.map(item => `${item.number} ${item.name}`)).toEqual([])
    expect(1 - misses.length / items.length).toBeGreaterThanOrEqual(0.7)
  })

  it('returns at most 10 suggestions per channel [FR-P-3]', () => {
    for (const ranked of suggest(matcher)) expect(ranked.length).toBeLessThanOrEqual(10)
  })

  it('is deterministic regardless of index order [FR-S-4]', () => {
    const reversed = new Matcher([...index.entries].reverse())

    expect(suggest(reversed)).toEqual(suggest(matcher))
    expect(suggest(matcher)).toEqual(suggest(new Matcher(index.entries)))
  })
})

describe('Matcher.find', () => {
  const matcher = new Matcher([
    entry('tvtv.us', '1', 'Start TV (WCBS-DT2) New York, NY', 'WCBSTV212.us@SD'),
    entry('directv.com', '2', 'Start TV'),
    { ...entry('digea.gr', '3', 'Star Channel'), lang: 'el' }
  ])
  const ids = (query: string, options = {}) => matcher.find(query, options).map(e => e.site_id)

  it('finds entries containing every query word, with prefixes', () => {
    expect(ids('start tv').sort()).toEqual(['1', '2'])
    expect(ids('star')).toContain('3')
    expect(ids('start new york')).toEqual(['1'])
  })

  it('filters by site, country and language', () => {
    expect(ids('start', { site: 'directv.com' })).toEqual(['2'])
    expect(ids('start', { country: 'us' })).toEqual(['1'])
    expect(ids('sta', { lang: 'el' })).toEqual(['3'])
  })

  it('lists entries in index order for an empty query', () => {
    expect(ids('')).toEqual(['1', '2', '3'])
    expect(ids('', { limit: 1 })).toEqual(['1'])
  })
})
