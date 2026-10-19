import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  RunHistory,
  clearCurrentRun,
  readCurrentRun,
  writeCurrentRun
} from '$lib/server/runHistory'
import { Storage } from '$lib/server/storage'
import type { RunData } from '$lib/types/run'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

let rootDir: string
let storage: Storage
let history: RunHistory

beforeEach(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-runs-'))
  storage = new Storage(rootDir)
  history = new RunHistory(storage)
})

afterEach(async () => {
  await fs.rm(rootDir, { recursive: true, force: true })
})

function run(n: number, log: string | null = `grab-ota-${n}.log`): RunData {
  return {
    startedAt: new Date(Date.UTC(2026, 0, 1, 0, n)).toISOString(),
    finishedAt: new Date(Date.UTC(2026, 0, 1, 0, n, 30)).toISOString(),
    duration: 30_000,
    result: 'success',
    channels: 1,
    programs: 2,
    error: null,
    log
  }
}

describe('RunHistory', () => {
  it('lists runs newest first', async () => {
    await history.add('ota', run(1))
    await history.add('ota', run(2))

    expect((await history.list('ota')).map(run => run.log)).toEqual([
      'grab-ota-2.log',
      'grab-ota-1.log'
    ])
    expect(await history.last('ota')).toEqual(run(2))
    expect(await history.last('other')).toBeNull()
  })

  it('keeps the last 20 runs and deletes the logs of older ones', async () => {
    for (let n = 1; n <= 22; n++) {
      await storage.save(`logs/grab-ota-${n}.log`, `run ${n}\n`)
      await history.add('ota', run(n))
    }

    const runs = await history.list('ota')
    expect(runs).toHaveLength(20)
    expect(runs.at(-1)?.log).toBe('grab-ota-3.log')
    expect(await storage.exists('logs/grab-ota-1.log')).toBe(false)
    expect(await storage.exists('logs/grab-ota-2.log')).toBe(false)
    expect(await storage.exists('logs/grab-ota-3.log')).toBe(true)
  })

  it('does not touch the logs of a lineup whose slug starts with the same name', async () => {
    await storage.save('logs/grab-ota-west-1.log', 'other lineup\n')
    for (let n = 1; n <= 21; n++) await history.add('ota', run(n))

    expect(await storage.exists('logs/grab-ota-west-1.log')).toBe(true)
  })

  it('tails only logs listed in the history', async () => {
    await storage.save('logs/grab-ota-1.log', 'a\nb\nc\n')
    await storage.save('logs/sync-1.log', 'secret\n')
    await history.add('ota', run(1))

    expect(await history.tail('ota', 'grab-ota-1.log', 2)).toEqual(['b', 'c'])
    expect(await history.tail('ota', 'sync-1.log')).toBeNull()
    expect(await history.tail('ota', '../lineups/ota/lineup.json')).toBeNull()
  })

  it('rejects invalid slugs', async () => {
    await expect(history.list('../x')).rejects.toThrow('invalid slug')
  })
})

describe('current run', () => {
  it('is written by the lock holder and cleared afterwards', async () => {
    expect(await readCurrentRun(storage)).toBeNull()

    await writeCurrentRun(storage, { step: 'grab', lineup: 'ota' })
    expect(await readCurrentRun(storage)).toMatchObject({
      step: 'grab',
      lineup: 'ota',
      pid: process.pid
    })

    await clearCurrentRun(storage)
    expect(await readCurrentRun(storage)).toBeNull()
  })
})
