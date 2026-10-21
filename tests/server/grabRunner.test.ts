import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { buildGrabArgs, countGuide, runGrab } from '$lib/server/grabRunner'
import { loadConfig, type Config } from '$lib/server/config'
import { LineupStore } from '$lib/server/lineupStore'
import { RunHistory } from '$lib/server/runHistory'
import { Storage } from '$lib/server/storage'
import type { MappingsData } from '$lib/types/mapping'
import { STUB_GUIDE, createStubNpm } from './helpers/fakeEpg'
import { gunzipSync } from 'node:zlib'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')
const mappings: MappingsData = JSON.parse(
  await fs.readFile('tests/__data__/input/channelsXml/hdhomerun.mappings.json', 'utf8')
)
const defaults = loadConfig({}).grab

let rootDir: string
let config: Config
let storage: Storage
let store: LineupStore
let history: RunHistory
let npm: string

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-grab-'))
  config = loadConfig({ STORAGE_DIR: rootDir })
  storage = new Storage(rootDir)
  store = new LineupStore(storage)
  history = new RunHistory(storage)
  npm = await createStubNpm(path.join(rootDir, 'bin'))
  // An installed checkout, as left by a sync
  await fs.mkdir(path.join(config.epgDir, 'node_modules'), { recursive: true })
  await store.create({ name: 'OTA', slug: 'ota', source: { type: 'upload' }, m3u })
  await store.saveMappings('ota', mappings)
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

const guide = (file: string) => storage.path('guides', file)
const touch = (file: string) => fs.writeFile(path.join(config.epgDir, file), '')

describe('buildGrabArgs', () => {
  const paths = { channels: '/data/lineups/ota/channels.xml', output: '/tmp/x/ota.xml' }

  it('uses the GRAB_* defaults and leaves days to the site config', () => {
    expect(buildGrabArgs({ enabled: true }, defaults, paths)).toEqual([
      'run',
      'grab',
      '---',
      '--channels=/data/lineups/ota/channels.xml',
      '--output=/tmp/x/ota.xml',
      '--maxConnections=1',
      '--delay=0',
      '--timeout=30000',
      '--gzip'
    ])
  })

  it('prefers the lineup overrides', () => {
    const grab = {
      enabled: true,
      days: 3,
      maxConnections: 5,
      delay: 100,
      timeout: 9000,
      gzip: false
    }

    expect(buildGrabArgs(grab, defaults, paths).slice(5)).toEqual([
      '--maxConnections=5',
      '--delay=100',
      '--timeout=9000',
      '--days=3'
    ])
  })

  it('uses GRAB_DAYS when the lineup has no override', () => {
    const args = buildGrabArgs({ enabled: true }, loadConfig({ GRAB_DAYS: '2' }).grab, paths)

    expect(args).toContain('--days=2')
  })
})

describe('countGuide', () => {
  it('counts channels and programmes', () => {
    expect(countGuide(STUB_GUIDE)).toEqual({ channels: 1, programs: 2 })
    expect(countGuide('')).toEqual({ channels: 0, programs: 0 })
  })
})

describe('runGrab', () => {
  it('publishes the guide and its .gz and records the run', async () => {
    const run = await runGrab('ota', { config, npm })

    expect(run).toMatchObject({ result: 'success', channels: 1, programs: 2, error: null })
    expect(await fs.readFile(guide('ota.xml'), 'utf8')).toBe(STUB_GUIDE)
    expect(gunzipSync(await fs.readFile(guide('ota.xml.gz'))).toString()).toBe(STUB_GUIDE)
    expect(await history.list('ota')).toEqual([run])
    expect(await storage.load(`logs/${run.log}`)).toContain('[1/1] example.com')
    // No temp dirs left behind
    expect(await fs.readdir(storage.path('guides'))).toEqual(['ota.xml', 'ota.xml.gz'])
  })

  it('writes channels.xml with logos from the checkout database before grabbing', async () => {
    await fs.cp('tests/__data__/input/database', path.join(config.epgDir, 'temp/data'), {
      recursive: true
    })
    const guide = { ...mappings.items['2.1'].guide!, xmltv_id: 'Charge.us@SD' }
    await store.setMapping('ota', '2.1', { status: 'mapped', guide, updatedAt: '' })

    await runGrab('ota', { config, npm })

    expect(await store.loadChannelsXml('ota')).toContain(
      'xmltv_id="ota.2.1" lcn="2.1" logo="https://example.com/logos/charge.png">'
    )
  })

  it('runs grab in the checkout with the channels.xml path and a sanitised env', async () => {
    const previous = process.env.STORAGE_DIR
    process.env.STORAGE_DIR = rootDir
    try {
      await runGrab('ota', { config, npm })
    } finally {
      if (previous === undefined) delete process.env.STORAGE_DIR
      else process.env.STORAGE_DIR = previous
    }

    const calls = await fs.readFile(path.join(config.epgDir, 'npm-calls.log'), 'utf8')
    expect(calls).toContain(`run grab --- --channels=${store.channelsXmlPath('ota')} --output=`)
    // FR-R-4 and FR-O-2
    expect(await fs.readFile(path.join(config.epgDir, 'grab-env.log'), 'utf8')).toBe(
      'NODE_PRESERVE_SYMLINKS=1 STORAGE_DIR=\n'
    )
  })

  it('removes an old .gz when gzip is turned off', async () => {
    await runGrab('ota', { config, npm })
    await store.update('ota', { grab: { gzip: false } })
    await runGrab('ota', { config, npm })

    expect(await fs.readdir(storage.path('guides'))).toEqual(['ota.xml'])
  })

  it('keeps the last good guide when grab fails', async () => {
    await runGrab('ota', { config, npm })
    const before = await fs.stat(guide('ota.xml'))
    await touch('grab-fail')

    const run = await runGrab('ota', { config, npm })

    expect(run.result).toBe('failed')
    expect(run.error).toMatch(/^grab failed: /)
    expect((await fs.stat(guide('ota.xml'))).mtimeMs).toBe(before.mtimeMs)
    expect(await storage.load(`logs/${run.log}`)).toContain('stub grab failed')
    expect((await history.list('ota')).map(run => run.result)).toEqual(['failed', 'success'])
  })

  it('keeps the last good guide when grab finds no programmes', async () => {
    await runGrab('ota', { config, npm })
    await touch('grab-empty')

    const run = await runGrab('ota', { config, npm })

    expect(run).toMatchObject({ result: 'failed', channels: null, programs: null })
    expect(run.error).toContain('no programmes')
    expect(await fs.readFile(guide('ota.xml'), 'utf8')).toBe(STUB_GUIDE)
  })

  it('skips a lineup without mapped channels', async () => {
    await store.saveMappings('ota', { version: 1, items: {} })

    const run = await runGrab('ota', { config, npm })

    expect(run).toMatchObject({ result: 'skipped', error: 'no mapped channels', log: null })
    expect(await fs.access(path.join(config.epgDir, 'npm-calls.log')).catch(() => 'none')).toBe(
      'none'
    )
  })

  it('fails without an installed epg checkout', async () => {
    await fs.rm(path.join(config.epgDir, 'node_modules'), { recursive: true })

    const run = await runGrab('ota', { config, npm })

    expect(run.result).toBe('failed')
    expect(run.error).toContain('run a sync first')
  })

  it('throws for an unknown lineup', async () => {
    await expect(runGrab('nope', { config, npm })).rejects.toThrow('lineup "nope" not found')
  })
})
