import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Services } from '$lib/server/services'
import { SYNC_STATUS_FILE } from '$lib/server/sync'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')

let rootDir: string
let services: Services

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-services-'))
  const epgDir = path.join(rootDir, 'epg')
  await fs.cp('tests/__data__/input/matcher/sites', path.join(epgDir, 'sites'), { recursive: true })
  services = new Services({ storageDir: rootDir, epgDir })
  await services.lineups.create({ name: 'Living Room', source: { type: 'upload' }, m3u })
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

// The guide index (and everything built on it) is ready once a sync has written its status
async function finishSync(dataDir: string | null = 'tests/__data__/input/database') {
  if (dataDir) await fs.cp(dataDir, path.join(rootDir, 'epg/temp/data'), { recursive: true })
  await fs.mkdir(path.join(rootDir, 'status'), { recursive: true })
  await fs.writeFile(path.join(rootDir, SYNC_STATUS_FILE), '{}')
}

describe('Services', () => {
  it('answers 503 until the first sync has finished [NFR-DEP-3]', async () => {
    await expect(services.matcher()).rejects.toMatchObject({ status: 503 })
    await expect(services.database()).rejects.toMatchObject({ status: 503 })
    await expect(services.suggest('living-room', '2.1')).rejects.toMatchObject({ status: 503 })
  })

  it('suggests guide entries for a lineup channel, using the lineup context', async () => {
    await finishSync()

    const [top] = await services.suggest('living-room', '2.2')

    expect(top.entry).toMatchObject({ site: 'tvtv.us', site_id: '74916' })
    expect(top.reasons.map(reason => reason.kind)).toContain('inheritedCallSign')
  })

  it('answers 404 for an unknown lineup or channel', async () => {
    await finishSync()

    await expect(services.suggest('kitchen', '2.1')).rejects.toMatchObject({ status: 404 })
    await expect(services.suggest('living-room', '99.9')).rejects.toMatchObject({ status: 404 })
  })

  it('reuses the matcher and database for the same guide index', async () => {
    await finishSync()

    expect(await services.matcher()).toBe(await services.matcher())
    expect(await services.database()).toBe(await services.database())
  })

  it('answers 503 when the database cannot be loaded', async () => {
    await finishSync(null)

    await expect(services.database()).rejects.toMatchObject({ status: 503 })
    expect(await services.matcher()).toBeTruthy()
  })

  it('lists lineups with channel counts and views a lineup in channel order', async () => {
    await services.lineups.setMapping('living-room', '2.2', {
      status: 'skipped',
      updatedAt: '2026-10-18T00:00:00.000Z'
    })

    const { lineups, errors } = await services.listLineups()
    expect(errors).toEqual([])
    expect(lineups).toMatchObject([
      { lineup: { slug: 'living-room' }, counts: { total: 14, skipped: 1, unmapped: 13 } }
    ])

    const view = await services.viewLineup('living-room')
    expect(view.rows.map(row => row.key).slice(0, 4)).toEqual(['2.1', '2.2', '4.1', '4.10'])
    await expect(services.viewLineup('kitchen')).rejects.toMatchObject({ status: 404 })
  })

  it('has no top suggestions before the first sync', async () => {
    expect(await services.topSuggestions('living-room')).toBeNull()
  })

  it('computes top suggestions for unmapped channels', async () => {
    await finishSync()
    await services.lineups.setMapping('living-room', '2.1', {
      status: 'skipped',
      updatedAt: '2026-10-18T00:00:00.000Z'
    })

    const top = await services.topSuggestions('living-room')
    expect(top?.['2.1']).toBeUndefined()
    expect(top?.['2.2'].entry).toMatchObject({ site: 'tvtv.us', site_id: '74916' })
  })

  it('writes the logo of the mapped entry from the database into channels.xml', async () => {
    await finishSync()

    await services.saveMapping('living-room', {
      key: '2.1',
      status: 'mapped',
      entry: { site: 'tvtv.us', site_id: '18633' }
    })

    expect(await services.lineups.loadChannelsXml('living-room')).toContain(
      'xmltv_id="living-room.2.1" lcn="2.1" logo="https://example.com/logos/iontv-east.png">'
    )
  })

  it('writes channels.xml without logos while the database is not available', async () => {
    await finishSync(null)

    await services.saveMapping('living-room', {
      key: '2.1',
      status: 'mapped',
      entry: { site: 'tvtv.us', site_id: '18633' }
    })

    expect(await services.lineups.loadChannelsXml('living-room')).toContain(
      'xmltv_id="living-room.2.1" lcn="2.1">WCBS-HD</channel>'
    )
  })

  it('maps a channel to an index entry, copying the entry from the index', async () => {
    await finishSync()

    const result = await services.saveMapping('living-room', {
      key: '2.1',
      status: 'mapped',
      entry: { site: 'tvtv.us', site_id: '16689' }
    })

    expect(result).toEqual({
      ok: true,
      warnings: [],
      row: expect.objectContaining({
        key: '2.1',
        status: 'mapped',
        mapping: expect.objectContaining({
          guide: {
            site: 'tvtv.us',
            site_id: '16689',
            lang: 'en',
            xmltv_id: 'WCBSTV21.us@HD',
            name: 'CBS (WCBS-DT1) New York, NY',
            origin: 'upstream'
          }
        })
      })
    })
    expect(await services.lineups.loadChannelsXml('living-room')).toContain(
      'site_id="16689" lang="en" xmltv_id="living-room.2.1" lcn="2.1">WCBS-HD</channel>'
    )
    await expect(
      services.saveMapping('living-room', {
        key: '2.1',
        status: 'mapped',
        entry: { site: 'tvtv.us', site_id: 'nope' }
      })
    ).rejects.toMatchObject({ status: 400 })
  })

  it('validates manual entries and names them from the database', async () => {
    await finishSync()
    const manual = { site: 'tvtv.us', site_id: '123', lang: 'en', xmltv_id: 'IONTV.us@East' }

    const invalid = await services.saveMapping('living-room', {
      key: '31.1',
      status: 'mapped',
      manual: { ...manual, site: 'nowhere.com', xmltv_id: 'IONTV' }
    })
    expect(invalid).toMatchObject({
      ok: false,
      errors: { site: expect.any(String), xmltv_id: expect.any(String) }
    })
    expect((await services.lineups.loadMappings('living-room')).items['31.1']).toBeUndefined()

    const result = await services.saveMapping('living-room', {
      key: '31.1',
      status: 'mapped',
      manual
    })
    expect(result).toMatchObject({
      ok: true,
      warnings: [],
      row: { mapping: { guide: { ...manual, name: 'ION TV', origin: 'manual' } } }
    })

    const unknown = await services.saveMapping('living-room', {
      key: '31.1',
      status: 'mapped',
      manual: { ...manual, xmltv_id: 'WXYZ.us' }
    })
    expect(unknown).toMatchObject({
      ok: true,
      warnings: ['"WXYZ.us" is not in the iptv-org database'],
      row: { mapping: { guide: { name: '123' } } }
    })
  })

  it('accepts several suggestions in one write, or none when one is unknown [FR-P-7]', async () => {
    await finishSync()
    const wcbs = { key: '2.1', entry: { site: 'tvtv.us', site_id: '16689' } }
    const second = { key: '2.2', entry: { site: 'tvtv.us', site_id: '74916' } }

    await expect(
      services.acceptEntries('living-room', {
        items: [wcbs, { ...second, entry: { site: 'tvtv.us', site_id: 'nope' } }]
      })
    ).rejects.toMatchObject({ status: 400 })
    await expect(
      services.acceptEntries('living-room', { items: [wcbs, { ...second, key: '99.9' }] })
    ).rejects.toMatchObject({ status: 404 })
    expect((await services.lineups.loadMappings('living-room')).items).toEqual({})

    const result = await services.acceptEntries('living-room', { items: [wcbs, second] })
    expect(result.rows).toMatchObject([
      { key: '2.1', status: 'mapped', mapping: { guide: { xmltv_id: 'WCBSTV21.us@HD' } } },
      { key: '2.2', status: 'mapped', mapping: { guide: { site_id: '74916' } } }
    ])
    const xml = await services.lineups.loadChannelsXml('living-room')
    expect(xml).toContain('site_id="16689"')
    expect(xml).toContain('site_id="74916"')
  })

  it('skips and clears channels', async () => {
    const skipped = await services.saveMapping('living-room', { key: '2.1', status: 'skipped' })
    expect(skipped).toMatchObject({ ok: true, row: { status: 'skipped' } })

    expect(await services.clearMapping('living-room', '2.1')).toMatchObject({
      status: 'unmapped',
      mapping: null
    })
    await expect(services.clearMapping('living-room', '99.9')).rejects.toMatchObject({
      status: 404
    })
  })

  it('has no guide for a lineup that has never been grabbed', async () => {
    const { lineup, guide } = await services.guideView('living-room')
    expect(lineup.slug).toBe('living-room')
    expect(guide).toBeNull()
    await expect(services.guideView('kitchen')).rejects.toMatchObject({ status: 404 })
  })

  it('parses the published guide, resolving logos from the current mapping [issue #9]', async () => {
    await finishSync()
    await services.saveMapping('living-room', {
      key: '2.1',
      status: 'mapped',
      entry: { site: 'tvtv.us', site_id: '18633' }
    })

    const guideXml = `<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="living-room.2.1"><display-name>WCBS-HD</display-name><lcn>2.1</lcn></channel>
  <programme start="20261020000000 +0000" stop="20261020003000 +0000" channel="living-room.2.1">
    <title>Early Show</title>
  </programme>
</tv>
`
    await fs.mkdir(path.join(rootDir, 'guides'), { recursive: true })
    await fs.writeFile(path.join(rootDir, 'guides', 'living-room.xml'), guideXml)

    const { guide } = await services.guideView('living-room')
    expect(guide?.channels).toMatchObject([
      {
        key: '2.1',
        name: 'WCBS-HD',
        number: '2.1',
        logo: 'https://example.com/logos/iontv-east.png'
      }
    ])
    expect(guide?.channels[0].programs).toMatchObject([{ title: 'Early Show' }])
  })
})
