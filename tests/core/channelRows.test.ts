import { buildChannelRows, countChannels } from '$lib/core/channelRows'
import { parsePlaylist } from '$lib/core/playlistParser'
import type { MappingsData } from '$lib/types/mapping'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs/promises'

const { items } = parsePlaylist(await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8'))
const mappings: MappingsData = JSON.parse(
  await fs.readFile('tests/__data__/input/channelsXml/hdhomerun.mappings.json', 'utf8')
)

describe('buildChannelRows', () => {
  it('returns one row per channel in channel number order with its mapping', () => {
    const rows = buildChannelRows(items, mappings)

    expect(rows.map(row => row.number)).toEqual([
      '2.1',
      '2.2',
      '4.1',
      '4.10',
      '5.1',
      '7.1',
      '11.1',
      '11.2',
      '13.1',
      '13.2',
      '31.1',
      '63.1',
      '68.1',
      '102.1'
    ])
    expect(rows[0]).toEqual({
      key: '2.1',
      number: '2.1',
      name: 'WCBS-HD',
      logo: null,
      status: 'mapped',
      mapping: mappings.items['2.1']
    })
    expect(rows[1].status).toBe('skipped')
    expect(rows.find(row => row.key === '31.1')).toMatchObject({
      status: 'unmapped',
      mapping: null
    })
  })

  it('ignores mappings of channels that are not in the playlist', () => {
    const extra: MappingsData = {
      version: 1,
      items: { gone: { status: 'skipped', updatedAt: '2026-10-18T00:00:00.000Z' } }
    }

    expect(buildChannelRows(items, extra).some(row => row.key === 'gone')).toBe(false)
  })
})

describe('countChannels', () => {
  it('counts rows per status and stale mappings', () => {
    expect(countChannels(buildChannelRows(items, mappings))).toEqual({
      total: 14,
      mapped: 5,
      skipped: 1,
      unmapped: 8,
      stale: 1
    })
  })
})
