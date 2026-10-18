import { Database } from '$lib/server/database'
import { describe, expect, it } from 'vitest'

const database = await Database.load('tests/__data__/input/database')

describe('Database', () => {
  it('loads channels and feeds', () => {
    expect(database.stats()).toEqual({ channels: 5, feeds: 11 })
  })

  it('knows channel and feed xmltv_ids [FR-E-2]', () => {
    expect(database.hasXmltvId('IONTV.us')).toBe(true)
    expect(database.hasXmltvId('IONTV.us@East')).toBe(true)
    expect(database.hasXmltvId('IONTV.us@West')).toBe(false)
    expect(database.hasXmltvId('WCBSTV.us')).toBe(false)
  })

  it('names channels by xmltv_id, with or without a feed', () => {
    expect(database.channelName('IONTV.us@East')).toBe(database.find('ion tv')[0].name)
    expect(database.channelName('IONTV.us')).toBe(database.find('ion tv')[0].name)
    expect(database.channelName('WCBSTV.us')).toBeNull()
    expect(database.channelName('not an id')).toBeNull()
  })

  describe('find', () => {
    const ids = (query: string, limit?: number) =>
      database.find(query, limit).map(channel => channel.xmltv_id)

    it('matches every word of the query, with prefixes [FR-E-1]', () => {
      expect(ids('ion tv')).toEqual(['IONTV.us'])
      expect(ids('sta')).toEqual(['StartTV.us'])
      expect(ids('')).toEqual([])
    })

    it('searches xmltv_ids and alternative names [FR-S-5]', () => {
      expect(ids('NBCLX')).toEqual(['NBCLX.us'])
      expect(ids('Nickelodeon')).toEqual(['BobEsponjaCalcaQuadrada.us'])
    })

    it('returns the channel with its feeds, main feed first', () => {
      expect(database.find('charge')).toEqual([
        {
          xmltv_id: 'Charge.us',
          name: 'Charge!',
          alt_names: [],
          country: 'US',
          closed: null,
          feeds: [
            { xmltv_id: 'Charge.us@SD', name: 'SD', is_main: true },
            { xmltv_id: 'Charge.us@K27HPD', name: 'K27HP-D', is_main: false },
            { xmltv_id: 'Charge.us@KABCTV', name: 'KABC-TV', is_main: false }
          ]
        }
      ])
    })

    it('honours the limit', () => {
      expect(ids('us', 2)).toHaveLength(2)
    })
  })
})
