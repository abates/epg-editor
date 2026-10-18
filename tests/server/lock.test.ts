import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { acquireRunLock, isRunLocked, RunLockedError, withRunLock } from '$lib/server/lock'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-lock-'))
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

describe('run lock', () => {
  it('allows one holder at a time', async () => {
    const release = await acquireRunLock(rootDir)

    expect(await isRunLocked(rootDir)).toBe(true)
    await expect(acquireRunLock(rootDir)).rejects.toBeInstanceOf(RunLockedError)

    await release()
    expect(await isRunLocked(rootDir)).toBe(false)
  })

  it('creates run.lock in the storage dir', async () => {
    const release = await acquireRunLock(rootDir)

    expect((await fs.stat(path.join(rootDir, 'run.lock'))).isDirectory()).toBe(true)
    await release()
  })

  it('takes over a lock left behind by a process that died', async () => {
    // A crashed holder stops refreshing the lock's mtime
    await fs.mkdir(path.join(rootDir, 'run.lock'))
    const past = new Date(Date.now() - 5 * 60_000)
    await fs.utimes(path.join(rootDir, 'run.lock'), past, past)

    expect(await isRunLocked(rootDir)).toBe(false)
    const release = await acquireRunLock(rootDir)
    expect(await isRunLocked(rootDir)).toBe(true)
    await release()
  })

  it('releases the lock when the callback throws', async () => {
    await expect(
      withRunLock(rootDir, async () => {
        throw new Error('boom')
      })
    ).rejects.toThrow('boom')

    expect(await isRunLocked(rootDir)).toBe(false)
  })
})
