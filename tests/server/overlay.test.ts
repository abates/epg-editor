import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Overlay } from '$lib/server/overlay'
import { FIXTURE_OVERLAY_DIR, FIXTURE_SITES_DIR, git } from './helpers/fakeEpg'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let epgDir: string
let overlayDir: string
let overlay: Overlay

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-overlay-'))
  epgDir = path.join(rootDir, 'epg')
  overlayDir = path.join(rootDir, 'sites')
  await fs.cp(FIXTURE_SITES_DIR, path.join(epgDir, 'sites'), { recursive: true })
  await fs.cp(FIXTURE_OVERLAY_DIR, overlayDir, { recursive: true })
  git(epgDir, ['init', '--quiet'])
  git(epgDir, ['add', '.'])
  git(epgDir, ['commit', '--quiet', '-m', 'initial'])

  overlay = new Overlay({
    overlayDir,
    sitesDir: path.join(epgDir, 'sites'),
    shadowDir: path.join(rootDir, '.epg-sites-shadow')
  })
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('Overlay', () => {
  it('links overlay sites and shadows upstream sites of the same name', async () => {
    const report = await overlay.apply()

    expect(report).toEqual({
      sites: [
        { name: 'example.com', conflict: true },
        { name: 'local.example', conflict: false }
      ],
      errors: []
    })
    expect(await fs.readlink(path.join(epgDir, 'sites/local.example'))).toBe(
      path.join(overlayDir, 'local.example')
    )
    expect(await fs.readlink(path.join(epgDir, 'sites/example.com'))).toBe(
      path.join(overlayDir, 'example.com')
    )
    expect(
      await fs.readFile(
        path.join(rootDir, '.epg-sites-shadow/example.com/example.com.channels.xml'),
        'utf8'
      )
    ).toContain('site_id="tf1"')
  })

  it('restores the checkout so git status is clean', async () => {
    await overlay.apply()
    await overlay.remove()

    expect(git(epgDir, ['status', '--porcelain'])).toBe('')
    expect(await fs.readdir(path.join(rootDir, '.epg-sites-shadow'))).toEqual([])
  })

  it('restores a shadowed site once its overlay is removed', async () => {
    await overlay.apply()
    await fs.rm(path.join(overlayDir, 'example.com'), { recursive: true })
    await overlay.remove()
    const report = await overlay.apply()

    expect(report.sites).toEqual([{ name: 'local.example', conflict: false }])
    expect((await fs.lstat(path.join(epgDir, 'sites/example.com'))).isDirectory()).toBe(true)
    expect(git(epgDir, ['status', '--porcelain'])).toBe('?? sites/local.example')
  })

  it('can be applied twice without remove in between', async () => {
    await overlay.apply()
    const report = await overlay.apply()

    expect(report.sites.map(site => site.name)).toEqual(['example.com', 'local.example'])
    await overlay.remove()
    expect(git(epgDir, ['status', '--porcelain'])).toBe('')
  })

  it('reports invalid overlay folders and skips files and dot folders', async () => {
    await fs.mkdir(path.join(overlayDir, 'Bad_Name'))
    await fs.mkdir(path.join(overlayDir, 'no-config.example'))
    await fs.mkdir(path.join(overlayDir, '.git'))
    await fs.writeFile(path.join(overlayDir, 'README.md'), '# notes')

    const report = await overlay.apply()

    expect(report.errors).toEqual([
      {
        name: 'Bad_Name',
        message: 'invalid site name: use lower-case letters, digits, "." and "-"'
      },
      { name: 'no-config.example', message: 'missing no-config.example.config.js' }
    ])
    expect(report.sites).toHaveLength(2)
  })

  it('does nothing when the overlay dir is missing', async () => {
    await fs.rm(overlayDir, { recursive: true })

    expect(await overlay.apply()).toEqual({ sites: [], errors: [] })
    await overlay.remove()
    expect(git(epgDir, ['status', '--porcelain'])).toBe('')
  })
})
