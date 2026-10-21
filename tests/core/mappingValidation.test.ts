import {
  parseBulkMappingRequest,
  parseMappingRequest,
  validateGuideEntry,
  type GuideEntryLookup
} from '$lib/core/mappingValidation'
import { describe, expect, it } from 'vitest'

const lookup: GuideEntryLookup = {
  hasSite: site => site === 'tvtv.us',
  hasXmltvId: id => id === 'WCBSTV.us@SD'
}

const entry = { site: 'tvtv.us', site_id: '10098', lang: 'en', xmltv_id: 'WCBSTV.us@SD' }

describe('validateGuideEntry', () => {
  it('accepts a known entry and trims values', () => {
    expect(
      validateGuideEntry({ ...entry, site: ' tvtv.us ', site_id: ' 10098 ', lang: ' ' }, lookup)
    ).toEqual({ value: { ...entry, lang: null }, errors: {}, warnings: [] })
  })

  it('blocks a missing or unknown site, an empty site_id and a malformed lang or xmltv_id', () => {
    expect(validateGuideEntry({ ...entry, site: '', site_id: '' }, lookup).errors).toEqual({
      site: 'Site is required',
      site_id: 'Site ID is required'
    })
    expect(
      validateGuideEntry({ ...entry, site: '../x', lang: 'eng', xmltv_id: 'WCBS' }, lookup).errors
    ).toEqual({
      site: 'Unknown site "../x"',
      lang: 'Language must be a two-letter ISO 639-1 code',
      xmltv_id: 'xmltv_id must look like ChannelID.cc or ChannelID.cc@Feed'
    })
  })

  it('warns about an empty xmltv_id or one missing from the database', () => {
    expect(validateGuideEntry({ ...entry, xmltv_id: '' }, lookup)).toMatchObject({
      errors: {},
      warnings: ['Without an xmltv_id the guide has no logo from the iptv-org database']
    })
    expect(validateGuideEntry({ ...entry, xmltv_id: 'WXYZ.us' }, lookup)).toMatchObject({
      errors: {},
      warnings: ['"WXYZ.us" is not in the iptv-org database']
    })
  })

  it('skips the database check when no database is loaded', () => {
    const noDatabase = { hasSite: lookup.hasSite }
    expect(validateGuideEntry({ ...entry, xmltv_id: 'WXYZ.us' }, noDatabase).warnings).toEqual([])
  })
})

describe('parseMappingRequest', () => {
  it('accepts skips, index entries and manual entries', () => {
    expect(parseMappingRequest({ key: '2.1', status: 'skipped' })).toEqual({
      key: '2.1',
      status: 'skipped'
    })
    expect(
      parseMappingRequest({
        key: '2.1',
        status: 'mapped',
        entry: { site: 'tvtv.us', site_id: '1' }
      })
    ).toEqual({ key: '2.1', status: 'mapped', entry: { site: 'tvtv.us', site_id: '1' } })
    expect(
      parseMappingRequest({
        key: '2.1',
        status: 'mapped',
        manual: { site: 'tvtv.us', site_id: '1', xmltv_id: '' }
      })
    ).toEqual({
      key: '2.1',
      status: 'mapped',
      manual: { site: 'tvtv.us', site_id: '1', lang: null, xmltv_id: '' }
    })
  })

  it('rejects malformed bodies', () => {
    expect(() => parseMappingRequest([])).toThrow('JSON object')
    expect(() => parseMappingRequest({ status: 'skipped' })).toThrow('"key" is required')
    expect(() => parseMappingRequest({ key: '2.1', status: 'gone' })).toThrow('"status"')
    expect(() => parseMappingRequest({ key: '2.1', status: 'mapped' })).toThrow('"entry" or')
    expect(() =>
      parseMappingRequest({ key: '2.1', status: 'mapped', entry: { site: 'tvtv.us' } })
    ).toThrow('"site_id"')
    expect(() =>
      parseMappingRequest({ key: '2.1', status: 'mapped', manual: { site: 'tvtv.us', lang: 1 } })
    ).toThrow('"manual" needs')
  })
})

describe('parseBulkMappingRequest', () => {
  it('accepts a list of channels and index entries', () => {
    const item = { key: '2.1', entry: { site: 'tvtv.us', site_id: '16689', extra: true } }

    expect(parseBulkMappingRequest({ items: [item] })).toEqual({
      items: [{ key: '2.1', entry: { site: 'tvtv.us', site_id: '16689' } }]
    })
  })

  it('rejects a missing or empty list, a bad item and a channel listed twice', () => {
    const item = { key: '2.1', entry: { site: 'tvtv.us', site_id: '16689' } }

    expect(() => parseBulkMappingRequest({})).toThrow('"items" must be an array')
    expect(() => parseBulkMappingRequest({ items: [] })).toThrow('"items" is empty')
    expect(() => parseBulkMappingRequest({ items: [{ ...item, key: '' }] })).toThrow('"key"')
    expect(() => parseBulkMappingRequest({ items: [{ key: '2.1' }] })).toThrow('"entry"')
    expect(() =>
      parseBulkMappingRequest({ items: [{ key: '2.1', entry: { site: 'tvtv.us' } }] })
    ).toThrow('"entry" needs "site" and "site_id"')
    expect(() => parseBulkMappingRequest({ items: [item, item] })).toThrow('listed twice')
  })
})
