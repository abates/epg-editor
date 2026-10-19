import type { RunData } from '$lib/types/run'
import type { SyncStatusData } from '$lib/types/sync'
import { clearCurrentRun, writeCurrentRun } from './runHistory'
import { LineupStore } from './lineupStore'
import type { RunLogger } from './runLog'
import type { Config } from './config'
import { runGrab } from './grabRunner'
import { Storage } from './storage'
import { runSync } from './sync'

export interface RunAllOptions {
  config: Config
  logger?: RunLogger
  // Grab only this lineup, even if it is not enabled for scheduled grabs ("Grab now")
  lineup?: string
  npm?: string
}

export interface RunAllResult {
  sync: SyncStatusData
  runs: Record<string, RunData>
}

// Sync, then grab every enabled lineup one after the other [FR-R-1]. A failed sync keeps the
// previous checkout, so the grabs still run against it [FR-G-5]. The caller holds the run lock
export async function runAll({
  config,
  logger,
  lineup,
  npm
}: RunAllOptions): Promise<RunAllResult> {
  const storage = new Storage(config.storageDir)
  const store = new LineupStore(storage)
  if (lineup && !(await store.exists(lineup))) throw new Error(`lineup "${lineup}" not found`)

  try {
    await writeCurrentRun(storage, { step: 'sync', lineup: lineup ?? null })
    const sync = await runSync({ config, logger, npm })
    if (sync.result === 'failed')
      logger?.warn(`sync failed, grabbing with the previous checkout: ${sync.error}`)

    const slugs = lineup ? [lineup] : await enabledLineups(store, logger)
    const runs: Record<string, RunData> = {}
    for (const slug of slugs) {
      await writeCurrentRun(storage, { step: 'grab', lineup: slug })
      try {
        runs[slug] = await runGrab(slug, { config, logger, npm })
      } catch (error) {
        // A lineup that can't be read must not stop the others [NFR-REL-1]
        logger?.error(`${slug}: ${(error as Error).message}`)
      }
    }

    return { sync, runs }
  } finally {
    await clearCurrentRun(storage)
  }
}

async function enabledLineups(store: LineupStore, logger?: RunLogger): Promise<string[]> {
  const { lineups, errors } = await store.list()
  for (const { slug, message } of errors) logger?.warn(`lineup ${slug}: ${message}`)

  return lineups.filter(lineup => lineup.grab.enabled).map(lineup => lineup.slug)
}
