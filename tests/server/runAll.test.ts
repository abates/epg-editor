import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { loadConfig, type Config } from '$lib/server/config'
import { readCurrentRun, RunHistory } from '$lib/server/runHistory'
import { LineupStore } from '$lib/server/lineupStore'
import { Storage } from '$lib/server/storage'
import { runAll } from '$lib/server/runAll'
import type { MappingsData } from '$lib/types/mapping'
import { createRemote, createStubNpm } from './helpers/fakeEpg'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')
// Mapped to an entry of the fixture tvtv.us site, so it survives the sync's stale check
const mappings: MappingsData = {
  version: 1,
  items: {
    '2.1': {
      status: 'mapped',
      guide: {
        site: 'tvtv.us',
        site_id: '10098',
        lang: 'en',
        xmltv_id: 'WCBSTV.us@SD',
        name: 'WCBS',
        origin: 'upstream'
      },
      updatedAt: '2026-01-01T00:00:00.000Z'
    }
  }
}

let rootDir: string
let config: Config
let storage: Storage
let store: LineupStore
let history: RunHistory
let npm: string

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-runall-'))
  const remoteUrl = await createRemote(path.join(rootDir, 'remote'))
  config = loadConfig({
    STORAGE_DIR: path.join(rootDir, 'data'),
    OVERLAY_DIR: path.join(rootDir, 'overlay'),
    EPG_REPO: remoteUrl
  })
  storage = new Storage(config.storageDir)
  store = new LineupStore(storage)
  history = new RunHistory(storage)
  npm = await createStubNpm(path.join(rootDir, 'bin'))

  for (const slug of ['ota', 'off']) {
    await store.create({ name: slug, slug, source: { type: 'upload' }, m3u })
    await store.saveMappings(slug, mappings)
  }
  await store.update('off', { grab: { enabled: false } })
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('runAll', () => {
  it('syncs, then grabs every enabled lineup', async () => {
    const { sync, runs } = await runAll({ config, npm })

    expect(sync.result).toBe('success')
    expect(Object.keys(runs)).toEqual(['ota'])
    expect(runs.ota.result).toBe('success')
    expect(await storage.exists('guides/ota.xml')).toBe(true)
    expect(await storage.exists('guides/off.xml')).toBe(false)
    expect(await history.list('off')).toEqual([])
    expect(await readCurrentRun(storage)).toBeNull()
  })

  it('grabs only the given lineup, even when scheduled grabs are off for it', async () => {
    const { runs } = await runAll({ config, npm, lineup: 'off' })

    expect(Object.keys(runs)).toEqual(['off'])
    expect(await storage.exists('guides/off.xml')).toBe(true)
    expect(await storage.exists('guides/ota.xml')).toBe(false)
  })

  it('still grabs with the previous checkout when the sync fails', async () => {
    await runAll({ config, npm })
    // Break the next sync: the remote is gone
    await fs.rm(path.join(rootDir, 'remote'), { recursive: true })

    const { sync, runs } = await runAll({ config, npm })

    expect(sync.result).toBe('failed')
    expect(runs.ota.result).toBe('success')
    expect((await history.list('ota')).length).toBe(2)
  })

  it('throws for an unknown lineup before doing anything', async () => {
    await expect(runAll({ config, npm, lineup: 'nope' })).rejects.toThrow('not found')
    expect(await storage.exists('status/sync.json')).toBe(false)
  })
})
