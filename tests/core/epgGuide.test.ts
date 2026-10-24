import { describe, expect, it } from 'vitest'
import { parseXmltv } from '@iptv/xmltv'
import { buildGuideView } from '$lib/core/epgGuide'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingsData } from '$lib/types/mapping'

const SLUG = 'ota'
const GENERATED_AT = new Date('2026-10-20T06:00:00.000Z')

const XML = `<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="ota.2.1"><display-name>WCBS-HD</display-name><lcn>2.1</lcn></channel>
  <channel id="ota.4.1"><display-name>WNBC-HD</display-name><lcn>4.1</lcn></channel>
  <channel id="ota.13.1"><display-name>WNET-HD</display-name><lcn>13.1</lcn></channel>
  <programme start="20261020000000 +0000" stop="20261020003000 +0000" channel="ota.2.1">
    <title>Early Show</title>
    <desc>A description</desc>
    <category>News</category>
    <category>Local</category>
  </programme>
  <programme start="20261020003000 +0000" stop="20261020010000 +0000" channel="ota.2.1">
    <title>Late Show</title>
  </programme>
  <programme start="20261020000000 +0000" channel="ota.4.1">
    <title>No stop time</title>
  </programme>
  <programme start="20261020000000 +0000" stop="20261020010000 +0000" channel="other.5.1">
    <title>Foreign guide, ignored</title>
  </programme>
</tv>
`

const items: PlaylistItemData[] = [
  {
    key: '2.1',
    number: '2.1',
    name: 'WCBS-HD',
    url: 'http://x/1',
    logo: null,
    group: null,
    attributes: {}
  },
  {
    key: '4.1',
    number: '4.1',
    name: 'WNBC-HD',
    url: 'http://x/2',
    logo: null,
    group: null,
    attributes: {}
  },
  {
    key: '13.1',
    number: '13.1',
    name: 'WNET-HD',
    url: 'http://x/3',
    logo: null,
    group: null,
    attributes: {}
  }
]

const mappings: MappingsData = {
  version: 1,
  items: {
    '2.1': {
      status: 'mapped',
      guide: {
        site: 'tvtv.us',
        site_id: '1',
        lang: 'en',
        xmltv_id: 'WCBSTV.us@SD',
        name: 'WCBS',
        origin: 'upstream'
      },
      updatedAt: '2026-10-18T00:00:00.000Z'
    },
    // Re-mapped since the grab: the guide still has the old entry's data, but the logo should
    // reflect this new xmltv_id, never a value baked into the guide file
    '4.1': {
      status: 'mapped',
      guide: {
        site: 'tvtv.us',
        site_id: '2',
        lang: 'en',
        xmltv_id: 'WNBC.us@SD',
        name: 'WNBC',
        origin: 'upstream'
      },
      updatedAt: '2026-10-19T00:00:00.000Z'
    }
    // 13.1 has no current mapping (cleared since the grab) — still shown, just no logo
  }
}

const logo = (xmltvId: string) => (xmltvId === 'WNBC.us@SD' ? 'https://example.com/wnbc.png' : null)

describe('buildGuideView', () => {
  it('builds channels in channel-number order with their programmes', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)

    expect(view.channels.map(channel => channel.key)).toEqual(['2.1', '4.1', '13.1'])
    expect(view.generatedAt).toBe(GENERATED_AT.toISOString())
  })

  it("resolves each channel from the guide id, not the guide's own display-name/lcn", () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)
    const wcbs = view.channels.find(channel => channel.key === '2.1')

    expect(wcbs).toMatchObject({ name: 'WCBS-HD', number: '2.1' })
  })

  it('looks up the logo from the current mapping, not the guide file [issue #9]', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)

    expect(view.channels.find(c => c.key === '2.1')?.logo).toBeNull()
    expect(view.channels.find(c => c.key === '4.1')?.logo).toBe('https://example.com/wnbc.png')
    expect(view.channels.find(c => c.key === '13.1')?.logo).toBeNull()
  })

  it('parses programme title/desc/category and joins multiple categories', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)
    const [early, late] = view.channels.find(c => c.key === '2.1')?.programs ?? []

    expect(early).toMatchObject({
      start: '2026-10-20T00:00:00.000Z',
      stop: '2026-10-20T00:30:00.000Z',
      title: 'Early Show',
      desc: 'A description',
      category: 'News, Local'
    })
    expect(late).toMatchObject({ title: 'Late Show', desc: null, category: null })
  })

  it('treats a missing stop time as zero-length rather than throwing', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)
    const [programme] = view.channels.find(c => c.key === '4.1')?.programs ?? []

    expect(programme.start).toBe(programme.stop)
  })

  it('ignores programmes for channels from another guide/lineup', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)

    expect(view.channels).toHaveLength(3)
  })

  it('computes the overall time range from the earliest start to the latest stop', () => {
    const view = buildGuideView(parseXmltv(XML), SLUG, items, mappings, GENERATED_AT, logo)

    expect(view.range).toEqual({
      start: '2026-10-20T00:00:00.000Z',
      stop: '2026-10-20T01:00:00.000Z'
    })
  })

  it('returns a null range when the guide has channels but no programmes', () => {
    const empty = parseXmltv(
      `<?xml version="1.0"?><tv><channel id="ota.2.1"><display-name>WCBS</display-name></channel></tv>`
    )
    const view = buildGuideView(empty, SLUG, items, mappings, GENERATED_AT, logo)

    expect(view.range).toBeNull()
    expect(view.channels[0].programs).toEqual([])
  })
})
