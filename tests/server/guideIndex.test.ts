import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { GuideIndex, GuideIndexCache } from '$lib/server/guideIndex'
import { FIXTURE_OVERLAY_DIR, FIXTURE_SITES_DIR } from './helpers/fakeEpg'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let sitesDir: string

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-index-'))
  sitesDir = path.join(rootDir, 'sites')
  await fs.cp(FIXTURE_SITES_DIR, sitesDir, { recursive: true })
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('GuideIndex', () => {
  it('loads every channels.xml entry', async () => {
    const index = await GuideIndex.load(sitesDir)

    expect(index.sites).toEqual(['example.com', 'tvtv.us'])
    expect(index.count).toBe(4)
    expect(index.errors).toEqual([])
    expect(index.find('example.com', 'tf1')).toEqual({
      site: 'example.com',
      site_id: 'tf1',
      lang: 'fr',
      xmltv_id: 'TF1.fr@SD',
      name: 'TF1',
      logo: 'https://example.com/tf1.png',
      country: 'fr',
      origin: 'upstream'
    })
    expect(index.find('tvtv.us', '20453')).toMatchObject({ xmltv_id: '', country: null })
  })

  it('marks symlinked sites as overlay', async () => {
    await fs.symlink(
      path.join(FIXTURE_OVERLAY_DIR, 'local.example'),
      path.join(sitesDir, 'local.example')
    )
    const index = await GuideIndex.load(sitesDir)

    expect(index.find('local.example', 'wpix')?.origin).toBe('overlay')
    expect(index.find('tvtv.us', '10098')?.origin).toBe('upstream')
  })

  it('answers lookups for stale-mapping checks', async () => {
    const index = await GuideIndex.load(sitesDir)

    expect(index.hasEntry('tvtv.us', '10098')).toBe(true)
    expect(index.hasEntry('tvtv.us', 'gone')).toBe(false)
    expect(index.hasSite('tvtv.us')).toBe(true)
    expect(index.hasSite('gone.example')).toBe(false)
  })

  it('reports unreadable files and keeps the rest', async () => {
    await fs.writeFile(path.join(sitesDir, 'tvtv.us/broken.channels.xml'), 'not xml')
    await fs.symlink(path.join(rootDir, 'missing'), path.join(sitesDir, 'dangling.example'))
    const index = await GuideIndex.load(sitesDir)

    expect(index.errors.map(error => error.file)).toEqual(['tvtv.us/broken.channels.xml'])
    expect(index.count).toBe(4)
    expect(index.sites).toEqual(['example.com', 'tvtv.us'])
  })

  it('is empty when the sites dir is missing', async () => {
    const index = await GuideIndex.load(path.join(rootDir, 'missing'))

    expect(index.count).toBe(0)
    expect(index.sites).toEqual([])
  })
})

describe('GuideIndexCache', () => {
  let statusFile: string
  let cache: GuideIndexCache

  beforeEach(() => {
    statusFile = path.join(rootDir, 'sync.json')
    cache = new GuideIndexCache({ sitesDir, statusFile, throttleMs: 1000 })
  })

  async function touch(seconds: number) {
    await fs.writeFile(statusFile, '{}')
    await fs.utimes(statusFile, seconds, seconds)
  }

  it('is not ready before the first sync', async () => {
    expect(await cache.get(0)).toBeNull()
  })

  it('reloads only when sync.json changes', async () => {
    await touch(1000)
    const first = await cache.get(0)
    expect(first?.count).toBe(4)

    await fs.rm(path.join(sitesDir, 'example.com'), { recursive: true })
    expect(await cache.get(5000)).toBe(first)

    await touch(2000)
    expect(await cache.get(500)).toBe(first) // throttled
    const second = await cache.get(10000)
    expect(second).not.toBe(first)
    expect(second?.count).toBe(3)
  })

  it('shares one load between concurrent callers', async () => {
    await touch(1000)
    const [a, b] = await Promise.all([cache.get(0), cache.get(0)])

    expect(a).toBe(b)
  })
})
