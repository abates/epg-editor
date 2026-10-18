import {
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
      warnings: ['Without an xmltv_id the guide uses the site ID as the channel id']
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
