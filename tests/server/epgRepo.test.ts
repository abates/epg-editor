import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { EpgRepo, LockfileMismatchError } from '$lib/server/epgRepo'
import { commit, createRemote, createStubNpm, git, npmCalls } from './helpers/fakeEpg'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let remoteDir: string
let remoteUrl: string
let npm: string
let epgDir: string

function createRepo(options: { ref?: string | null; repo?: string } = {}) {
  return new EpgRepo({
    dir: epgDir,
    repo: options.repo ?? remoteUrl,
    branch: 'master',
    ref: options.ref ?? null,
    npm
  })
}

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-repo-'))
  remoteDir = path.join(rootDir, 'remote')
  remoteUrl = await createRemote(remoteDir)
  npm = await createStubNpm(path.join(rootDir, 'bin'))
  epgDir = path.join(rootDir, 'data/epg')
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('EpgRepo', () => {
  it('clones the branch on first checkout', async () => {
    const repo = createRepo()
    const result = await repo.checkout()

    expect(result).toEqual({ previous: null, current: git(remoteDir, ['rev-parse', 'HEAD']) })
    expect(await repo.exists()).toBe(true)
    expect(await fs.readdir(repo.sitesDir)).toEqual(['example.com', 'tvtv.us'])
    expect(git(epgDir, ['rev-parse', '--is-shallow-repository'])).toBe('true')
  })

  it('leaves nothing behind when the clone fails', async () => {
    const repo = createRepo({ repo: `file://${rootDir}/missing` })

    await expect(repo.checkout()).rejects.toThrow()
    expect(await fs.readdir(path.join(rootDir, 'data'))).toEqual([])
  })

  it('updates to the latest commit and removes untracked files in sites/', async () => {
    const repo = createRepo()
    const first = await repo.checkout()
    await fs.mkdir(path.join(epgDir, 'node_modules'))
    await fs.mkdir(path.join(repo.sitesDir, 'leftover.example'))
    await fs.writeFile(path.join(repo.sitesDir, 'leftover.example/file.txt'), 'x')
    const latest = await commit(remoteDir, { 'sites/example.com': null })

    const result = await repo.checkout()

    expect(result).toEqual({ previous: first.current, current: latest })
    expect(await fs.readdir(repo.sitesDir)).toEqual(['tvtv.us'])
    expect(await fs.readdir(epgDir)).toContain('node_modules')
  })

  it('keeps the checkout when the fetch fails', async () => {
    const repo = createRepo()
    const { current } = await repo.checkout()

    const offline = createRepo({ repo: `file://${rootDir}/missing` })
    await expect(offline.checkout()).rejects.toThrow()

    expect(await repo.head()).toBe(current)
    expect(await fs.readdir(repo.sitesDir)).toEqual(['example.com', 'tvtv.us'])
  })

  it('pins EPG_REF instead of following the branch', async () => {
    const pinned = git(remoteDir, ['rev-parse', 'HEAD'])
    git(remoteDir, ['tag', 'v1'])
    await commit(remoteDir, { 'sites/new.example/new.example.config.js': '' })

    expect((await createRepo({ ref: 'v1' }).checkout()).current).toBe(pinned)
  })

  it('runs npm ci only when package-lock.json changed', async () => {
    const repo = createRepo()
    await repo.checkout()

    const first = await repo.install(null)
    const second = await repo.install(first.hash)
    await commit(remoteDir, { 'package-lock.json': '{"lockfileVersion":3,"changed":true}\n' })
    await repo.checkout()
    const third = await repo.install(second.hash)

    expect([first.installed, second.installed, third.installed]).toEqual([true, false, true])
    expect(third.hash).not.toBe(first.hash)
    expect(await npmCalls(epgDir)).toEqual(['ci --ignore-scripts', 'ci --ignore-scripts'])
  })

  it('runs npm ci again when node_modules is missing', async () => {
    const repo = createRepo()
    await repo.checkout()
    const { hash } = await repo.install(null)
    await fs.rm(path.join(epgDir, 'node_modules'), { recursive: true })

    expect((await repo.install(hash)).installed).toBe(true)
  })

  it('explains that the target repo lockfile is out of sync, not a raw npm error', async () => {
    const repo = createRepo()
    await repo.checkout()
    await fs.writeFile(path.join(epgDir, 'npm-lockfile-mismatch'), '')

    const error = await repo.install(null).catch((e: unknown) => e)

    expect(error).toBeInstanceOf(LockfileMismatchError)
    expect((error as Error).message).toMatch(/package-lock\.json doesn't match its package\.json/)
    expect((error as Error).message).not.toMatch(/npm error/)
  })

  it('loads api data with npm run api:load', async () => {
    const repo = createRepo()
    await repo.checkout()

    expect(await repo.hasApiData()).toBe(false)
    await repo.loadApi()
    expect(await repo.hasApiData()).toBe(true)
    expect(await npmCalls(epgDir)).toEqual(['run api:load'])
  })
})
