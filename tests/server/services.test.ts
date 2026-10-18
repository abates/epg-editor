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
})
