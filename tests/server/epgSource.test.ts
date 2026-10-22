import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  clearEpgSourceOverride,
  readEpgSourceOverride,
  resolveEpgConfig,
  saveEpgSourceOverride,
  validateEpgSource
} from '$lib/server/epgSource'
import { Storage } from '$lib/server/storage'
import { createRemote, git } from './helpers/fakeEpg'
import type { AddressInfo } from 'node:net'
import fs from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let storage: Storage

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-epgsource-'))
  storage = new Storage(path.join(rootDir, 'data'))
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

// Binds then immediately closes a port, so connecting to it fails fast with ECONNREFUSED
// instead of a real (slow, flaky) DNS lookup or timeout
async function unreachableUrl(): Promise<string> {
  const server = http.createServer()
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = (server.address() as AddressInfo).port
  await new Promise(resolve => server.close(resolve))

  return `https://127.0.0.1:${port}/missing.git`
}

describe('readEpgSourceOverride / saveEpgSourceOverride / clearEpgSourceOverride', () => {
  it('reads as null before the first save, round-trips, then clears', async () => {
    expect(await readEpgSourceOverride(storage)).toBeNull()

    await saveEpgSourceOverride(storage, { repo: 'https://example.com/fork.git', ref: 'feature' })
    expect(await readEpgSourceOverride(storage)).toEqual({
      repo: 'https://example.com/fork.git',
      ref: 'feature'
    })

    await clearEpgSourceOverride(storage)
    expect(await readEpgSourceOverride(storage)).toBeNull()
  })

  it('clearing when nothing was saved is a no-op', async () => {
    await expect(clearEpgSourceOverride(storage)).resolves.toBeUndefined()
  })
})

describe('resolveEpgConfig', () => {
  const defaultEpg = { repo: 'https://github.com/iptv-org/epg.git', branch: 'master', ref: null }

  it('returns the default config when there is no override', async () => {
    expect(await resolveEpgConfig(storage, defaultEpg)).toEqual(defaultEpg)
  })

  // The override replaces a pinned EPG_REF default too: only one source is ever checked out
  it('substitutes the saved repo/ref for the default', async () => {
    await saveEpgSourceOverride(storage, { repo: 'https://example.com/fork.git', ref: 'pr-123' })

    expect(await resolveEpgConfig(storage, { ...defaultEpg, ref: 'v1.0.0' })).toEqual({
      repo: 'https://example.com/fork.git',
      branch: 'pr-123',
      ref: null
    })
  })
})

describe('validateEpgSource', () => {
  let remoteDir: string
  let remoteUrl: string

  beforeEach(async () => {
    remoteDir = path.join(rootDir, 'remote')
    remoteUrl = await createRemote(remoteDir)
    git(remoteDir, ['branch', 'feature'])
  })

  it('rejects a repo url that is not http(s)', async () => {
    expect(await validateEpgSource(remoteUrl, 'master')).toEqual({
      repo: 'Only http/https URLs are supported'
    })
  })

  it('rejects an unparsable url', async () => {
    expect(await validateEpgSource('not a url', 'master')).toEqual({
      repo: '"not a url" is not a valid URL'
    })
  })

  it('accepts a reachable repo and an existing branch', async () => {
    expect(await validateEpgSource(remoteUrl, 'master', { allowedProtocols: ['file:'] })).toEqual(
      {}
    )
    expect(await validateEpgSource(remoteUrl, 'feature', { allowedProtocols: ['file:'] })).toEqual(
      {}
    )
  })

  it('reports an unknown branch on the ref field, leaving the repo field clean', async () => {
    expect(
      await validateEpgSource(remoteUrl, 'no-such-branch', { allowedProtocols: ['file:'] })
    ).toEqual({ ref: `"no-such-branch" was not found in ${remoteUrl}` })
  })

  it('lets a commit SHA through unchecked, since ls-remote cannot confirm it', async () => {
    const sha = git(remoteDir, ['rev-parse', 'HEAD'])

    expect(await validateEpgSource(remoteUrl, sha, { allowedProtocols: ['file:'] })).toEqual({})
  })

  it('reports an unreachable repo on the repo field', async () => {
    const result = await validateEpgSource(await unreachableUrl(), 'master')

    expect(Object.keys(result)).toEqual(['repo'])
    expect(result.repo).toContain('Could not reach')
  })
})
