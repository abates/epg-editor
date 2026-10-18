import { countryFromXmltvId, parseXmltvId } from '$lib/core/xmltvId'
import { describe, expect, it } from 'vitest'

describe('parseXmltvId', () => {
  it('splits channel, country and feed', () => {
    expect(parseXmltvId('WCBSTV.us@SD')).toEqual({
      channel: 'WCBSTV.us',
      country: 'us',
      feed: 'SD'
    })
    expect(parseXmltvId('TF1.fr')).toEqual({ channel: 'TF1.fr', country: 'fr', feed: null })
  })

  it('rejects ids that do not match the iptv-org format', () => {
    for (const id of ['', 'WCBSTV', 'WCBSTV.US', 'WCBS-TV.us', 'WCBSTV.us@', 'WCBSTV.usa']) {
      expect(parseXmltvId(id)).toBeNull()
    }
  })
})

describe('countryFromXmltvId', () => {
  it('returns the country suffix or null', () => {
    expect(countryFromXmltvId('WCBSTV.us@SD')).toBe('us')
    expect(countryFromXmltvId('')).toBeNull()
  })
})
