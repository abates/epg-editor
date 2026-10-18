import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { LineupStore } from '$lib/server/lineupStore'
import type { MappingsData } from '$lib/types/mapping'
import { Storage } from '$lib/server/storage'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')
const mappings: MappingsData = JSON.parse(
  await fs.readFile('tests/__data__/input/channelsXml/hdhomerun.mappings.json', 'utf8')
)
const expectedXml = await fs.readFile(
  'tests/__data__/expected/channelsXml/hdhomerun.channels.xml',
  'utf8'
)
const emptyXml = await fs.readFile('tests/__data__/expected/channelsXml/empty.channels.xml', 'utf8')

let rootDir: string
let storage: Storage
let store: LineupStore

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-lineups-'))
  storage = new Storage(rootDir)
  store = new LineupStore(storage)
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

const create = (name = 'Living Room') =>
  store.create({ name, source: { type: 'url', url: 'http://hdhr/lineup.m3u' }, m3u })

describe('LineupStore', () => {
  it('creates a lineup with all its files', async () => {
    const lineup = await create()

    expect(lineup).toMatchObject({
      slug: 'living-room',
      name: 'Living Room',
      source: { type: 'url', url: 'http://hdhr/lineup.m3u' },
      filters: { countries: ['us'], languages: [], preferredSites: [] },
      grab: { enabled: true }
    })
    expect(await store.get('living-room')).toEqual(lineup)
    expect(await store.loadSource('living-room')).toBe(m3u)
    expect(await store.loadMappings('living-room')).toEqual({ version: 1, items: {} })
    expect(await store.loadChannelsXml('living-room')).toBe(emptyXml)
    expect(await fs.readdir(path.join(rootDir, 'lineups'))).toEqual(['living-room'])
  })

  it('makes derived slugs unique and rejects taken or invalid explicit slugs', async () => {
    await create()
    expect((await create()).slug).toBe('living-room-2')

    const source = { type: 'upload' as const }
    await expect(store.create({ name: 'X', slug: 'living-room', source, m3u })).rejects.toThrow(
      'already exists'
    )
    await expect(store.create({ name: 'X', slug: '../etc', source, m3u })).rejects.toThrow(
      'invalid slug'
    )
    await expect(store.create({ name: '___', source, m3u })).rejects.toThrow('invalid slug')
    await expect(store.create({ name: ' ', source, m3u })).rejects.toThrow('name is required')
  })

  it('lists lineups and reports broken ones without hiding the others', async () => {
    await create('Alpha')
    await create('Beta')
    await storage.save('lineups/beta/lineup.json', '{ not json')
    await storage.save('lineups/.tmp-left-over/lineup.json', '{}')

    const { lineups, errors } = await store.list()
    expect(lineups.map(lineup => lineup.slug)).toEqual(['alpha'])
    expect(errors).toEqual([{ slug: 'beta', message: expect.stringContaining('not valid JSON') }])
  })

  it('updates name, filters and grab settings but not the slug', async () => {
    await create()
    const updated = await store.update('living-room', {
      name: 'Den',
      filters: { preferredSites: ['tvtv.us'] },
      grab: { days: 2 }
    })

    expect(updated).toMatchObject({
      slug: 'living-room',
      name: 'Den',
      filters: { countries: ['us'], preferredSites: ['tvtv.us'] },
      grab: { enabled: true, days: 2 }
    })
    expect(await store.get('living-room')).toEqual(updated)
  })

  it('regenerates channels.xml when mappings change', async () => {
    await create()
    await store.saveMappings('living-room', mappings)

    expect(await store.loadChannelsXml('living-room')).toBe(expectedXml)
    expect(store.channelsXmlPath('living-room')).toBe(
      path.join(rootDir, 'lineups/living-room/channels.xml')
    )
  })

  it('regenerates channels.xml when the source is replaced', async () => {
    await create()
    await store.saveMappings('living-room', mappings)
    await store.saveSource('living-room', m3u.replace('WCBS-HD', 'WCBS'), { type: 'upload' })

    expect(await store.loadChannelsXml('living-room')).toContain('lcn="2.1">WCBS</channel>')
    expect((await store.get('living-room'))?.source.type).toBe('upload')
  })

  it('deletes the lineup with its guides and run history', async () => {
    await create()
    await storage.save('guides/living-room.xml', '<tv/>')
    await storage.save('guides/living-room.xml.gz', '')
    await storage.save('status/runs/living-room.json', '[]')
    await storage.save('guides/other.xml', '<tv/>')

    await store.delete('living-room')

    expect(await store.get('living-room')).toBeNull()
    expect(await storage.exists('guides/living-room.xml')).toBe(false)
    expect(await storage.exists('guides/living-room.xml.gz')).toBe(false)
    expect(await storage.exists('status/runs/living-room.json')).toBe(false)
    expect(await storage.exists('guides/other.xml')).toBe(true)
  })

  it('throws for unknown or invalid slugs', async () => {
    await expect(store.loadMappings('missing')).rejects.toThrow('not found')
    await expect(store.get('../../etc')).rejects.toThrow('invalid slug')
  })
})
