import type { CurrentRunData, RunData, RunHistoryData } from '$lib/types/run'
import { isValidSlug } from '$lib/core/slug'
import { Storage } from './storage'

export const RUNS_DIR = 'status/runs'
export const CURRENT_RUN_FILE = 'status/current.json'
export const LOGS_DIR = 'logs'
const KEEP_RUNS = 20

// Per-lineup run history [FR-R-6]. Only the last 20 runs are kept, and the log files of
// dropped runs are deleted with them, so the logs dir rotates per lineup
export class RunHistory {
  readonly storage: Storage

  constructor(storage: Storage) {
    this.storage = storage
  }

  async list(slug: string): Promise<RunData[]> {
    const file = this.file(slug)
    if (!(await this.storage.exists(file))) return []

    return (await this.storage.json<RunHistoryData>(file)).runs
  }

  async last(slug: string): Promise<RunData | null> {
    return (await this.list(slug).catch(() => []))[0] ?? null
  }

  async add(slug: string, run: RunData): Promise<RunData[]> {
    const previous = await this.list(slug).catch(() => [])
    const runs = [run, ...previous]
    const kept = runs.slice(0, KEEP_RUNS)
    await this.storage.saveJson(this.file(slug), { version: 1, runs: kept })

    const keptLogs = new Set(kept.map(run => run.log))
    for (const dropped of runs.slice(KEEP_RUNS)) {
      if (dropped.log && !keptLogs.has(dropped.log) && isLogName(dropped.log))
        await this.storage.remove(`${LOGS_DIR}/${dropped.log}`)
    }

    return kept
  }

  // The last `lines` lines of a run's log. Only logs listed in the history can be read, so
  // the name can't point anywhere else
  async tail(slug: string, log: string, lines = 500): Promise<string[] | null> {
    const runs = await this.list(slug)
    if (!isLogName(log) || !runs.some(run => run.log === log)) return null
    if (!(await this.storage.exists(`${LOGS_DIR}/${log}`))) return null

    const content = await this.storage.load(`${LOGS_DIR}/${log}`)

    return content.replace(/\n$/, '').split('\n').slice(-lines)
  }

  private file(slug: string): string {
    if (!isValidSlug(slug)) throw new Error(`invalid slug "${slug}"`)

    return `${RUNS_DIR}/${slug}.json`
  }
}

export async function readCurrentRun(storage: Storage): Promise<CurrentRunData | null> {
  if (!(await storage.exists(CURRENT_RUN_FILE))) return null

  return storage.json<CurrentRunData>(CURRENT_RUN_FILE).catch(() => null)
}

export async function writeCurrentRun(
  storage: Storage,
  current: Omit<CurrentRunData, 'pid' | 'startedAt'>
): Promise<void> {
  const data: CurrentRunData = { ...current, startedAt: new Date().toISOString(), pid: process.pid }
  await storage.saveJson(CURRENT_RUN_FILE, data)
}

export async function clearCurrentRun(storage: Storage): Promise<void> {
  await storage.remove(CURRENT_RUN_FILE)
}

function isLogName(name: string): boolean {
  return /^[a-z0-9][a-zA-Z0-9.-]*\.log$/.test(name)
}
