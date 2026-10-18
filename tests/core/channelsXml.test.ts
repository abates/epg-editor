import { compareChannelNumbers, generateChannelsXml } from '$lib/core/channelsXml'
import { parsePlaylist } from '$lib/core/playlistParser'
import type { MappingsData } from '$lib/types/mapping'
import { describe, expect, it } from 'vitest'
import { EPGGrabber } from 'epg-grabber'
import fs from 'node:fs'

const read = (filepath: string) => fs.readFileSync(`tests/__data__/${filepath}`, 'utf8')

describe('generateChannelsXml', () => {
  const { items } = parsePlaylist(read('input/m3u/hdhomerun.m3u'))
  const mappings: MappingsData = JSON.parse(read('input/channelsXml/hdhomerun.mappings.json'))

  it('writes mapped channels in channel number order', () => {
    const xml = generateChannelsXml(items, mappings)
    expect(xml).toBe(read('expected/channelsXml/hdhomerun.channels.xml'))
  })

  it('does not depend on playlist order', () => {
    const xml = generateChannelsXml([...items].reverse(), mappings)
    expect(xml).toBe(read('expected/channelsXml/hdhomerun.channels.xml'))
  })

  it('writes an empty file when nothing is mapped', () => {
    const xml = generateChannelsXml(items, { version: 1, items: {} })
    expect(xml).toBe(read('expected/channelsXml/empty.channels.xml'))
  })

  it('is readable by epg-grabber, including lcn', () => {
    const channels = EPGGrabber.parseChannelsXML(generateChannelsXml(items, mappings))
    expect(
      channels.map(({ site, site_id, lang, xmltv_id, lcn, name }) => ({
        site,
        site_id,
        lang,
        xmltv_id,
        lcn,
        name
      }))
    ).toEqual([
      {
        site: 'tvtv.us',
        site_id: '10098',
        lang: 'en',
        xmltv_id: 'WCBSTV.us@SD',
        lcn: '2.1',
        name: 'WCBS-HD'
      },
      {
        site: 'tvtv.us',
        site_id: '10099',
        lang: 'en',
        xmltv_id: 'WNBC.us@SD',
        lcn: '4.1',
        name: 'WNBC-HD'
      },
      {
        site: 'example.local',
        site_id: 'nbc lx & "more"',
        lang: 'en',
        xmltv_id: '',
        lcn: '4.10',
        name: 'NBC LX'
      },
      {
        site: 'tvtv.us',
        site_id: '10003',
        lang: 'en',
        xmltv_id: 'WABCTV.us@SD',
        lcn: '7.1',
        name: 'WABC-HD'
      },
      {
        site: 'tvtv.us',
        site_id: '10045',
        lang: null,
        xmltv_id: 'WNETTV.us@SD',
        lcn: '13.1',
        name: 'WNET-HD'
      }
    ])
    expect(
      EPGGrabber.parseChannelsXML(generateChannelsXml(items, { version: 1, items: {} }))
    ).toEqual([])
  })
})

describe('compareChannelNumbers', () => {
  it('sorts by numeric parts with unnumbered channels last', () => {
    const numbers = ['10.1', null, '2.10', '4.1', '2.2', '2', '2.1']
    expect(numbers.sort(compareChannelNumbers)).toEqual([
      '2',
      '2.1',
      '2.2',
      '2.10',
      '4.1',
      '10.1',
      null
    ])
  })
})
