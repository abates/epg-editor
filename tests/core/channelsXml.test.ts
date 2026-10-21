import { compareChannelNumbers, generateChannelsXml, guideChannelId } from '$lib/core/channelsXml'
import { parsePlaylist } from '$lib/core/playlistParser'
import type { MappingsData } from '$lib/types/mapping'
import { describe, expect, it } from 'vitest'
import { EPGGrabber } from 'epg-grabber'
import fs from 'node:fs'

const read = (filepath: string) => fs.readFileSync(`tests/__data__/${filepath}`, 'utf8')

describe('generateChannelsXml', () => {
  const { items } = parsePlaylist(read('input/m3u/hdhomerun.m3u'))
  const mappings: MappingsData = JSON.parse(read('input/channelsXml/hdhomerun.mappings.json'))
  const logo = (xmltvId: string) =>
    xmltvId === 'WNBC.us@SD' ? null : `https://example.com/${xmltvId}.png?a=1&b=2`
  const guideIds = (xml: string) =>
    EPGGrabber.parseChannelsXML(xml).map(({ lcn, xmltv_id }) => ({ lcn, xmltv_id }))

  it('writes mapped channels in channel number order', () => {
    const xml = generateChannelsXml('ota', items, mappings)
    expect(xml).toBe(read('expected/channelsXml/hdhomerun.channels.xml'))
  })

  it('does not depend on playlist order', () => {
    const xml = generateChannelsXml('ota', [...items].reverse(), mappings)
    expect(xml).toBe(read('expected/channelsXml/hdhomerun.channels.xml'))
  })

  it('writes an empty file when nothing is mapped', () => {
    const xml = generateChannelsXml('ota', items, { version: 1, items: {} })
    expect(xml).toBe(read('expected/channelsXml/empty.channels.xml'))
  })

  it('writes the logo of the entry xmltv_id when there is one', () => {
    const xml = generateChannelsXml('ota', items, mappings, { logo })
    expect(xml).toBe(read('expected/channelsXml/hdhomerun-logos.channels.xml'))
  })

  it('keeps the guide id when a channel is re-mapped to another site or feed', () => {
    const before = guideIds(generateChannelsXml('ota', items, mappings))
    const remapped = structuredClone(mappings)
    remapped.items['2.1'].guide = {
      site: 'example.local',
      site_id: 'wcbs',
      lang: 'en',
      xmltv_id: '',
      name: 'WCBS',
      origin: 'overlay'
    }
    remapped.items['4.1'].guide = { ...remapped.items['4.1'].guide!, xmltv_id: 'WNBC.us@HD' }

    expect(guideIds(generateChannelsXml('ota', items, remapped))).toEqual(before)
  })

  it('gives channels mapped to the same entry their own guide ids', () => {
    const shared = structuredClone(mappings)
    shared.items['13.1'].guide = shared.items['2.1'].guide

    const ids = guideIds(generateChannelsXml('ota', items, shared)).map(c => c.xmltv_id)
    expect(ids).toContain('ota.2.1')
    expect(ids).toContain('ota.13.1')
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('is readable by epg-grabber, including lcn and logo', () => {
    const channels = EPGGrabber.parseChannelsXML(
      generateChannelsXml('ota', items, mappings, { logo })
    )
    expect(
      channels.map(({ site, site_id, lang, xmltv_id, lcn, logo, name }) => ({
        site,
        site_id,
        lang,
        xmltv_id,
        lcn,
        logo,
        name
      }))
    ).toEqual([
      {
        site: 'tvtv.us',
        site_id: '10098',
        lang: 'en',
        xmltv_id: 'ota.2.1',
        lcn: '2.1',
        logo: 'https://example.com/WCBSTV.us@SD.png?a=1&b=2',
        name: 'WCBS-HD'
      },
      {
        site: 'tvtv.us',
        site_id: '10099',
        lang: 'en',
        xmltv_id: 'ota.4.1',
        lcn: '4.1',
        logo: null,
        name: 'WNBC-HD'
      },
      {
        site: 'example.local',
        site_id: 'nbc lx & "more"',
        lang: 'en',
        xmltv_id: 'ota.4.10',
        lcn: '4.10',
        logo: null,
        name: 'NBC LX'
      },
      {
        site: 'tvtv.us',
        site_id: '10003',
        lang: 'en',
        xmltv_id: 'ota.7.1',
        lcn: '7.1',
        logo: 'https://example.com/WABCTV.us@SD.png?a=1&b=2',
        name: 'WABC-HD'
      },
      {
        site: 'tvtv.us',
        site_id: '10045',
        lang: null,
        xmltv_id: 'ota.13.1',
        lcn: '13.1',
        logo: 'https://example.com/WNETTV.us@SD.png?a=1&b=2',
        name: 'WNET-HD'
      }
    ])
    expect(
      EPGGrabber.parseChannelsXML(generateChannelsXml('ota', items, { version: 1, items: {} }))
    ).toEqual([])
  })
})

describe('guideChannelId', () => {
  it('is the lineup slug and the channel key [FR-M-4]', () => {
    expect(guideChannelId('ota', '5.1')).toBe('ota.5.1')
    expect(guideChannelId('ota', '5.1#2')).toBe('ota.5.1#2')
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
