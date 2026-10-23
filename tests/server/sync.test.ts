import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { readSyncStatus, runSync } from '$lib/server/sync'
import { clearEpgSourceOverride, saveEpgSourceOverride } from '$lib/server/epgSource'
import { LineupStore } from '$lib/server/lineupStore'
import { loadConfig, type Config } from '$lib/server/config'
import { parsePlaylist } from '$lib/core/playlistParser'
import { Storage } from '$lib/server/storage'
import type { MappingsData } from '$lib/types/mapping'
import {
  FIXTURE_OVERLAY_DIR,
  commit,
  createRemote,
  createStubNpm,
  git,
  npmCalls
} from './helpers/fakeEpg'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')
const tvtvChannelsXml = 'sites/tvtv.us/tvtv.us.channels.xml'

let rootDir: string
let remoteDir: string
let remoteUrl: string
let npm: string
let config: Config
let storage: Storage

function configWith(env: Record<string, string> = {}): Config {
  return loadConfig({
    STORAGE_DIR: path.join(rootDir, 'data'),
    OVERLAY_DIR: path.join(rootDir, 'overlay'),
    EPG_REPO: remoteUrl,
    ...env
  })
}

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-sync-'))
  remoteDir = path.join(rootDir, 'remote')
  remoteUrl = await createRemote(remoteDir)
  npm = await createStubNpm(path.join(rootDir, 'bin'))
  await fs.cp(FIXTURE_OVERLAY_DIR, path.join(rootDir, 'overlay'), { recursive: true })
  config = configWith()
  storage = new Storage(config.storageDir)
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('runSync', () => {
  it('clones, installs, links the overlay and indexes on first run', async () => {
    const status = await runSync({ config, npm })

    expect(status.result).toBe('success')
    expect(status.error).toBeNull()
    expect(status.commit).toBe(git(remoteDir, ['rev-parse', 'HEAD']))
    expect(status.ref).toBe('master')
    expect(status.overlay.sites).toEqual([
      { name: 'example.com', conflict: true },
      { name: 'local.example', conflict: false }
    ])
    expect(status.warnings).toContain('overlay site example.com replaces the upstream site')
    // tvtv.us (3) + overlay example.com (1) + local.example (1)
    expect(status.index).toEqual({ sites: 3, entries: 5, errors: [] })
    expect(await npmCalls(config.epgDir)).toEqual(['ci --ignore-scripts', 'run api:load'])
    expect(await readSyncStatus(storage)).toEqual(status)
    expect(await storage.load(`logs/${status.log}`)).toContain('sync finished')
    expect(status.logTail.at(-1)).toBe('sync finished')
  })

  it('skips npm ci when package-lock.json is unchanged', async () => {
    await runSync({ config, npm })
    const status = await runSync({ config, npm })

    expect(status.result).toBe('success')
    expect(await npmCalls(config.epgDir)).toEqual([
      'ci --ignore-scripts',
      'run api:load',
      'run api:load'
    ])
  })

  it('marks mappings stale when their entry disappears and rewrites channels.xml', async () => {
    const store = new LineupStore(storage)
    await store.create({ name: 'OTA', slug: 'ota', source: { type: 'upload' }, m3u })
    const [first, second] = parsePlaylist(m3u).items
    const guide = (site_id: string) => ({
      site: 'tvtv.us',
      site_id,
      lang: 'en',
      xmltv_id: '',
      name: site_id,
      origin: 'upstream' as const
    })
    const mappings: MappingsData = {
      version: 1,
      items: {
        [first.key]: { status: 'mapped', guide: guide('10098'), updatedAt: '' },
        [second.key]: { status: 'mapped', guide: guide('10991'), updatedAt: '' }
      }
    }
    await runSync({ config, npm })
    await store.saveMappings('ota', mappings)

    const xml = await fs.readFile(path.join(remoteDir, tvtvChannelsXml), 'utf8')
    await commit(remoteDir, { [tvtvChannelsXml]: xml.replace(/.*site_id="10991".*\n/, '') })
    await runSync({ config, npm })

    const updated = await store.loadMappings('ota')
    expect(updated.items[first.key].stale).toBeUndefined()
    expect(updated.items[second.key].stale).toBe(true)
    expect(await store.loadChannelsXml('ota')).toContain('site_id="10991"')
  })

  it('keeps the previous checkout and overlay when the fetch fails', async () => {
    const first = await runSync({ config, npm })
    const status = await runSync({
      config: configWith({ EPG_REPO: `file://${rootDir}/missing` }),
      npm
    })

    expect(status.result).toBe('failed')
    expect(status.error).toMatch(/git fetch/)
    expect(status.commit).toBe(first.commit)
    expect(status.lockfileHash).toBe(first.lockfileHash)
    expect(status.overlay.sites).toHaveLength(2)
    expect(status.index?.entries).toBe(5)
  })

  it('rolls back to the previous commit when npm ci fails', async () => {
    const first = await runSync({ config, npm })
    await commit(remoteDir, {
      'package-lock.json': '{"lockfileVersion":3,"broken":true}\n',
      'npm-fail': ''
    })

    const status = await runSync({ config, npm })

    expect(status.result).toBe('failed')
    expect(status.commit).toBe(first.commit)
    expect(status.lockfileHash).toBe(first.lockfileHash)
    expect(status.index?.entries).toBe(5)
    expect(await fs.readdir(config.epgDir)).not.toContain('npm-fail')
    expect(await npmCalls(config.epgDir)).toEqual([
      'ci --ignore-scripts',
      'run api:load',
      'ci --ignore-scripts',
      'ci --ignore-scripts'
    ])
  })

  it('records a failed first clone without creating a checkout', async () => {
    const status = await runSync({
      config: configWith({ EPG_REPO: `file://${rootDir}/missing` }),
      npm
    })

    expect(status.result).toBe('failed')
    expect(status.commit).toBeNull()
    expect(status.index).toBeNull()
    expect(await fs.readdir(config.storageDir)).not.toContain('epg')
  })

  it('checks out a saved /status override instead of the env-configured repo/branch', async () => {
    const forkDir = path.join(rootDir, 'fork')
    const forkUrl = await createRemote(forkDir)
    const forkCommit = await commit(forkDir, { FORK_MARKER: 'x' })
    await saveEpgSourceOverride(storage, { repo: forkUrl, ref: 'master' })

    const status = await runSync({ config, npm })

    expect(status.result).toBe('success')
    expect(status.repo).toBe(forkUrl)
    expect(status.ref).toBe('master')
    expect(status.commit).toBe(forkCommit)
  })

  it('goes back to the env-configured repo/branch once the override is reset', async () => {
    const forkDir = path.join(rootDir, 'fork')
    const forkUrl = await createRemote(forkDir)
    await saveEpgSourceOverride(storage, { repo: forkUrl, ref: 'master' })
    await runSync({ config, npm })

    await clearEpgSourceOverride(storage)
    const status = await runSync({ config, npm })

    expect(status.result).toBe('success')
    expect(status.repo).toBe(remoteUrl)
    expect(status.commit).toBe(git(remoteDir, ['rev-parse', 'HEAD']))
  })

  it('keeps the last 20 sync logs', async () => {
    await fs.mkdir(storage.path('logs'), { recursive: true })
    for (let i = 0; i < 25; i++) {
      await fs.writeFile(
        storage.path(`logs/sync-2000-01-01T00-00-${String(i).padStart(2, '0')}.log`),
        ''
      )
    }
    await runSync({ config, npm })

    const logs = await fs.readdir(storage.path('logs'))
    expect(logs).toHaveLength(20)
    expect(logs.sort().at(0)).toBe('sync-2000-01-01T00-00-06.log')
  })
})
