import type { SuggestionData } from '$lib/types/suggestion'
import { Matcher, lineupCallSigns } from '$lib/core/matcher'
import { parsePlaylist } from '$lib/core/playlistParser'
import { GuideIndex, GuideIndexCache } from './guideIndex'
import { config as defaultConfig, type Config } from './config'
import { LineupStore } from './lineupStore'
import { SYNC_STATUS_FILE } from './sync'
import { Database } from './database'
import { Storage } from './storage'
import { error } from '@sveltejs/kit'
import path from 'node:path'

// Long-lived state of the web process. The matcher and database belong to one guide index,
// so both are rebuilt when a sync rewrites status/sync.json and the index reloads
export class Services {
  readonly lineups: LineupStore
  readonly guideIndex: GuideIndexCache
  private readonly dataDir: string
  private readonly matchers = new WeakMap<GuideIndex, Matcher>()
  private readonly databases = new WeakMap<GuideIndex, Promise<Database | null>>()

  constructor(config: Pick<Config, 'storageDir' | 'epgDir'>) {
    this.lineups = new LineupStore(new Storage(config.storageDir))
    this.guideIndex = new GuideIndexCache({
      sitesDir: path.join(config.epgDir, 'sites'),
      statusFile: path.join(config.storageDir, SYNC_STATUS_FILE)
    })
    this.dataDir = path.join(config.epgDir, 'temp', 'data')
  }

  // 503 until the first sync has finished [NFR-DEP-3]
  async matcher(): Promise<Matcher> {
    const index = await this.readyIndex()
    let matcher = this.matchers.get(index)
    if (!matcher) {
      matcher = new Matcher(index.entries)
      this.matchers.set(index, matcher)
    }

    return matcher
  }

  async database(): Promise<Database> {
    const index = await this.readyIndex()
    let database = this.databases.get(index)
    if (!database) {
      // The SDK loads a missing data dir as an empty database
      database = Database.load(this.dataDir)
        .then(database => (database.channels.length ? database : null))
        .catch(() => null)
      this.databases.set(index, database)
    }

    return (await database) ?? error(503, 'The iptv-org database is not available')
  }

  // Ranked suggestions for one channel of a lineup [FR-P-3]
  async suggest(slug: string, key: string): Promise<SuggestionData[]> {
    const lineup = await this.lineups.get(slug)
    if (!lineup) error(404, `Lineup "${slug}" not found`)

    const { items } = parsePlaylist(await this.lineups.loadSource(slug))
    const item = items.find(item => item.key === key)
    if (!item) error(404, `Channel "${key}" not found in lineup "${slug}"`)

    const matcher = await this.matcher()

    return matcher.suggest(item, lineup.filters, { callSigns: lineupCallSigns(items) })
  }

  private async readyIndex(): Promise<GuideIndex> {
    return (await this.guideIndex.get()) ?? error(503, 'The guide index is not ready yet')
  }
}

export const services = new Services(defaultConfig)
