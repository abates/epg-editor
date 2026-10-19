import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { acquireRunLock } from '$lib/server/lock'
import { Jobs } from '$lib/server/jobs'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-jobs-'))
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

// Stand-in for `npm run run:*`, run with cwd = rootDir: logs its arguments, then runs `body`
async function stubNpm(body: string): Promise<string> {
  const filepath = path.join(rootDir, 'npm')
  await fs.writeFile(filepath, ['#!/bin/sh', 'echo "$*" >> calls.log', body, ''].join('\n'), {
    mode: 0o755
  })

  return filepath
}

const jobs = (npm: string) => new Jobs({ storageDir: rootDir, cwd: rootDir, npm })
const calls = async () => (await fs.readFile(path.join(rootDir, 'calls.log'), 'utf8')).trim()

describe('Jobs', () => {
  it('waits until the command holds the run lock', async () => {
    // Takes the lock the way proper-lockfile does, holds it for a moment, then releases it
    const npm = await stubNpm('sleep 0.5; mkdir run.lock; sleep 1; rmdir run.lock')
    const manager = jobs(npm)

    expect(await manager.start('grab', 'ota')).toEqual({ ok: true })
    expect((await manager.status()).running).toBe(true)
    expect(await calls()).toBe('run run:all -- --lineup=ota')
  })

  it('starts run:sync and run:all for every lineup', async () => {
    const npm = await stubNpm('exit 0')

    expect(await jobs(npm).start('sync')).toEqual({ ok: true })
    expect(await jobs(npm).start('grab')).toEqual({ ok: true })
    expect(await calls()).toBe('run run:sync\nrun run:all')
  })

  it('rejects a job while another run holds the lock [FR-R-3]', async () => {
    const npm = await stubNpm('exit 0')
    const release = await acquireRunLock(rootDir)
    try {
      expect(await jobs(npm).start('grab')).toEqual({
        ok: false,
        status: 409,
        message: 'A sync or grab is already running'
      })
      await expect(fs.access(path.join(rootDir, 'calls.log'))).rejects.toThrow()
    } finally {
      await release()
    }
  })

  it('reports a command that fails before taking the lock', async () => {
    const npm = await stubNpm('exit 3')

    expect(await jobs(npm).start('sync')).toEqual({
      ok: false,
      status: 500,
      message: 'The sync command exited with code 3'
    })
  })

  it('reports no current run while unlocked', async () => {
    expect(await jobs(await stubNpm('exit 0')).status()).toEqual({ running: false, current: null })
  })
})
