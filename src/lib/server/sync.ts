import type { OverlayReportData, SyncStatusData } from '$lib/types/sync'
import { markStaleMappings } from '$lib/core/staleMappings'
import { RunLog, rotateLogs, type RunLogger } from './runLog'
import { LineupStore } from './lineupStore'
import { GuideIndex } from './guideIndex'
import type { Config } from './config'
import { Database } from './database'
import { EpgRepo } from './epgRepo'
import { resolveEpgConfig } from './epgSource'
import { Overlay } from './overlay'
import { Storage } from './storage'

export const SYNC_STATUS_FILE = 'status/sync.json'
export const SHADOW_DIR = '.epg-sites-shadow'
const LOGS_DIR = 'logs'
const KEEP_LOGS = 20

export interface SyncOptions {
  config: Config
  logger?: RunLogger
  // Overridable so tests can use a stub instead of a real npm install
  npm?: string
}

export async function readSyncStatus(storage: Storage): Promise<SyncStatusData | null> {
  if (!(await storage.exists(SYNC_STATUS_FILE))) return null

  return storage.json<SyncStatusData>(SYNC_STATUS_FILE)
}

// Sync = update the epg checkout, re-link overlay sites, rebuild the index, refresh lineups
// [5.8]. The caller holds the run lock. A failed git/npm step keeps the previous checkout
// usable: overlay, index and lineups are still refreshed against it [FR-G-5]
export async function runSync({ config, logger, npm }: SyncOptions): Promise<SyncStatusData> {
  const storage = new Storage(config.storageDir)
  const startedAt = new Date()
  const log = await RunLog.open(storage.path(LOGS_DIR), 'sync', startedAt, logger)
  const previous = await readSyncStatus(storage).catch(() => null)
  const warnings: string[] = []
  let error: string | null = null
  let lockfileHash = previous?.lockfileHash ?? null
  let overlayReport: OverlayReportData = { sites: [], errors: [] }
  let index: GuideIndex | null = null
  let database: Database | null = null

  // A saved /status override takes over from EPG_REPO/EPG_BRANCH/EPG_REF (issue #5)
  const epg = await resolveEpgConfig(storage, config.epg)
  const repo = new EpgRepo({
    dir: config.epgDir,
    ...epg,
    npm,
    onLine: line => log.line(line)
  })
  const overlay = new Overlay({
    overlayDir: config.overlayDir,
    sitesDir: repo.sitesDir,
    shadowDir: storage.path(SHADOW_DIR)
  })
  const warn = (message: string) => {
    warnings.push(message)
    log.warn(message)
  }

  try {
    log.info('removing overlay links...')
    await overlay.remove()

    log.info(`updating ${repo.dir} to ${repo.target}...`)
    const commits = await repo.checkout()
    log.info(`checked out ${commits.current}`)

    try {
      log.info('installing dependencies...')
      const install = await repo.install(lockfileHash)
      lockfileHash = install.hash
      if (!install.installed) log.info('package-lock.json unchanged, skipped npm ci')
    } catch (installError) {
      // npm ci removes node_modules first, so go back to the commit that last installed
      lockfileHash = null
      if (commits.previous && commits.previous !== commits.current) {
        log.warn(`npm ci failed, rolling back to ${commits.previous}...`)
        await repo.reset(commits.previous)
        lockfileHash = (await repo.install(null)).hash
      }
      throw installError
    }

    log.info('loading api data...')
    try {
      await repo.loadApi()
    } catch (apiError) {
      if (!(await repo.hasApiData())) throw apiError
      warn(`api:load failed, keeping the previous database: ${message(apiError)}`)
    }
  } catch (syncError) {
    error = message(syncError)
    log.error(error)
  }

  if (await repo.exists()) {
    try {
      log.info('linking overlay sites...')
      overlayReport = await overlay.apply()
      for (const site of overlayReport.sites) {
        if (site.conflict) warn(`overlay site ${site.name} replaces the upstream site`)
      }
      for (const siteError of overlayReport.errors) {
        warn(`overlay site ${siteError.name}: ${siteError.message}`)
      }

      log.info('loading guide index...')
      index = await GuideIndex.load(repo.sitesDir)
      log.info(`found ${index.count} entries in ${index.sites.length} sites`)
      for (const indexError of index.errors) warn(`${indexError.file}: ${indexError.message}`)

      if (await repo.hasApiData()) {
        log.info('loading database...')
        database = await Database.load(repo.dataDir).catch(dbError => {
          warn(`could not load the iptv-org database: ${message(dbError)}`)
          return null
        })
        if (database) {
          const stats = database.stats()
          log.info(`found ${stats.channels} channels and ${stats.feeds} feeds`)
        }
      }

      log.info('refreshing lineups...')
      const loaded = database
      const store = new LineupStore(storage, {
        logos: async () => loaded && (xmltvId => loaded.logo(xmltvId))
      })
      await refreshLineups(store, index, log, warn)
    } catch (refreshError) {
      error ??= message(refreshError)
      log.error(message(refreshError))
    }
  }

  const finishedAt = new Date()
  const status: SyncStatusData = {
    result: error ? 'failed' : 'success',
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    duration: finishedAt.getTime() - startedAt.getTime(),
    repo: repo.repo,
    ref: repo.target,
    commit: await repo.head().catch(() => null),
    lockfileHash,
    error,
    warnings,
    overlay: overlayReport,
    index: index?.stats() ?? null,
    database: database?.stats() ?? null,
    log: log.name,
    logTail: []
  }
  log.info(error ? 'sync failed' : 'sync finished')
  status.logTail = log.tail
  await log.close()

  // Written last: the web process reloads its index when this file changes
  await storage.saveJson(SYNC_STATUS_FILE, status)
  await rotateLogs(storage.path(LOGS_DIR), 'sync', KEEP_LOGS)

  return status
}

// FR-G-4: mark mappings whose entry vanished as stale and regenerate every channels.xml
async function refreshLineups(
  store: LineupStore,
  index: GuideIndex,
  log: RunLog,
  warn: (message: string) => void
) {
  const { lineups, errors } = await store.list()
  for (const lineupError of errors) warn(`lineup ${lineupError.slug}: ${lineupError.message}`)

  for (const { slug } of lineups) {
    try {
      const { mappings, changed } = markStaleMappings(await store.loadMappings(slug), index)
      if (changed) {
        await store.saveMappings(slug, mappings)
        log.info(`${slug}: ${changed} mapping(s) changed stale state`)
      } else {
        await store.writeChannelsXml(slug)
      }
    } catch (lineupError) {
      warn(`lineup ${slug}: ${message(lineupError)}`)
    }
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
