import type {
  BulkMappingRequestData,
  MappingData,
  MappingGuideData,
  MappingRequestData
} from '$lib/types/mapping'
import type { ChannelCountsData, ChannelRowData } from '$lib/types/channel'
import type { SuggestionData } from '$lib/types/suggestion'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { SyncStatusData } from '$lib/types/sync'
import type { LineupData } from '$lib/types/lineup'
import type { GuideViewData } from '$lib/types/guideView'
import type { RunData } from '$lib/types/run'
import { validateGuideEntry, type GuideEntryField } from '$lib/core/mappingValidation'
import { buildChannelRows, countChannels } from '$lib/core/channelRows'
import type { ChannelLogo } from '$lib/core/channelsXml'
import { Matcher, lineupCallSigns } from '$lib/core/matcher'
import { parsePlaylist } from '$lib/core/playlistParser'
import { buildGuideView } from '$lib/core/epgGuide'
import { GuideIndex, GuideIndexCache } from './guideIndex'
import { config as defaultConfig, type Config } from './config'
import { LineupStore, type LineupLoadError } from './lineupStore'
import { SYNC_STATUS_FILE, readSyncStatus } from './sync'
import {
  clearEpgSourceOverride,
  readEpgSourceOverride,
  saveEpgSourceOverride,
  validateEpgSource,
  type EpgSourceFieldErrors,
  type EpgSourceOverrideData
} from './epgSource'
import { RunHistory } from './runHistory'
import { GUIDES_DIR } from './grabRunner'
import { Database } from './database'
import { Storage } from './storage'
import { Jobs } from './jobs'
import { parseXmltv } from '@iptv/xmltv'
import { error } from '@sveltejs/kit'
import fs from 'node:fs/promises'
import path from 'node:path'

// Long-lived state of the web process. The matcher and database belong to one guide index,
// so both are rebuilt when a sync rewrites status/sync.json and the index reloads
export interface LineupSummaryData {
  lineup: LineupData
  counts: ChannelCountsData
  lastRun: RunData | null
}

export interface LineupViewData {
  lineup: LineupData
  rows: ChannelRowData[]
  counts: ChannelCountsData
  warnings: string[]
}

export interface GuideViewResult {
  lineup: LineupData
  guide: GuideViewData | null
}

export type SaveMappingResult =
  | { ok: true; row: ChannelRowData; warnings: string[] }
  | { ok: false; errors: Partial<Record<GuideEntryField, string>>; warnings: string[] }

export class Services {
  readonly lineups: LineupStore
  readonly guideIndex: GuideIndexCache
  readonly runs: RunHistory
  readonly jobs: Jobs
  private readonly storage: Storage
  private readonly dataDir: string
  private readonly matchers = new WeakMap<GuideIndex, Matcher>()
  private readonly databases = new WeakMap<GuideIndex, Promise<Database | null>>()

  constructor(config: Pick<Config, 'storageDir' | 'epgDir'>) {
    this.storage = new Storage(config.storageDir)
    this.lineups = new LineupStore(this.storage, { logos: () => this.channelLogo() })
    this.runs = new RunHistory(this.storage)
    this.jobs = new Jobs({ storageDir: config.storageDir })
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

  // Lineup list [FR-L-2]; a lineup whose files can't be read is reported, not thrown
  async listLineups(): Promise<{ lineups: LineupSummaryData[]; errors: LineupLoadError[] }> {
    const { lineups, errors } = await this.lineups.list()
    const summaries: LineupSummaryData[] = []
    for (const lineup of lineups) {
      try {
        const { counts } = await this.viewLineup(lineup.slug)
        summaries.push({ lineup, counts, lastRun: await this.runs.last(lineup.slug) })
      } catch (error) {
        errors.push({ slug: lineup.slug, message: (error as Error).message })
      }
    }

    return { lineups: summaries, errors }
  }

  // Null until the first sync has finished; a broken file reads as missing
  async syncStatus(): Promise<SyncStatusData | null> {
    return readSyncStatus(this.storage).catch(() => null)
  }

  // Null while the default (env-configured) repo/branch is in effect
  async epgSourceOverride(): Promise<EpgSourceOverrideData | null> {
    return readEpgSourceOverride(this.storage)
  }

  // Validates before persisting; nothing is saved when the repo or branch/ref doesn't resolve
  async saveEpgSource(
    repo: string,
    ref: string
  ): Promise<{ ok: true } | { ok: false; errors: EpgSourceFieldErrors }> {
    const errors = await validateEpgSource(repo, ref)
    if (Object.keys(errors).length) return { ok: false, errors }

    await saveEpgSourceOverride(this.storage, { repo, ref })
    return { ok: true }
  }

  async resetEpgSource(): Promise<void> {
    await clearEpgSourceOverride(this.storage)
  }

  // Editor rows [FR-P-1]
  async viewLineup(slug: string): Promise<LineupViewData> {
    const lineup = await this.lineups.get(slug)
    if (!lineup) error(404, `Lineup "${slug}" not found`)

    const { items, warnings } = parsePlaylist(await this.lineups.loadSource(slug))
    const logo = (await this.channelLogo()) ?? undefined
    const rows = buildChannelRows(items, await this.lineups.loadMappings(slug), logo)

    return { lineup, rows, counts: countChannels(rows), warnings }
  }

  // In-app episode guide viewer [issue #9]: parses the file FR-R-5 is currently serving, so it
  // always mirrors the last successful grab. Null guide while the lineup has never been grabbed
  async guideView(slug: string): Promise<GuideViewResult> {
    const lineup = await this.lineups.get(slug)
    if (!lineup) error(404, `Lineup "${slug}" not found`)

    const filepath = this.storage.path(GUIDES_DIR, `${slug}.xml`)
    const stat = await fs.stat(filepath).catch(() => null)
    if (!stat?.isFile()) return { lineup, guide: null }

    const xml = await fs.readFile(filepath, 'utf8')
    const { items } = parsePlaylist(await this.lineups.loadSource(slug))
    const mappings = await this.lineups.loadMappings(slug)
    const logo = (await this.channelLogo()) ?? undefined

    return {
      lineup,
      guide: buildGuideView(parseXmltv(xml), slug, items, mappings, stat.mtime, logo)
    }
  }

  // Best suggestion per unmapped channel, for the editor's "Suggested" badges. Null while
  // the guide index is not ready
  async topSuggestions(slug: string): Promise<Record<string, SuggestionData> | null> {
    const index = await this.guideIndex.get()
    if (!index) return null

    const lineup = await this.lineups.get(slug)
    if (!lineup) return null
    const { items } = parsePlaylist(await this.lineups.loadSource(slug))
    const { items: mappings } = await this.lineups.loadMappings(slug)
    const matcher = await this.matcher()
    const callSigns = lineupCallSigns(items)

    const result: Record<string, SuggestionData> = {}
    for (const item of items) {
      if (mappings[item.key]) continue
      const [top] = matcher.suggest(item, lineup.filters, { callSigns, limit: 1 })
      if (top) result[item.key] = top
    }

    return result
  }

  // Known site names for the Manual tab's picker [FR-E-1]
  async sites(): Promise<string[]> {
    return (await this.guideIndex.get())?.sites ?? []
  }

  // FR-P-4..6: entries picked from the index are copied from it, so a client can't save an
  // entry that doesn't exist; manual entries are validated [FR-E-2]
  async saveMapping(slug: string, request: MappingRequestData): Promise<SaveMappingResult> {
    const item = await this.requireItem(slug, request.key)
    const updatedAt = new Date().toISOString()
    let mapping: MappingData
    let warnings: string[] = []

    if (request.status === 'skipped') {
      mapping = { status: 'skipped', updatedAt }
    } else if ('entry' in request) {
      const guide = indexGuide(await this.readyIndex(), request.entry)
      mapping = { status: 'mapped', guide, updatedAt }
      if (!guide.xmltv_id)
        warnings.push('Without an xmltv_id the guide has no logo from the iptv-org database')
    } else {
      const index = await this.readyIndex()
      const database = await this.optionalDatabase()
      const validation = validateGuideEntry(request.manual, {
        hasSite: site => index.hasSite(site),
        hasXmltvId: database ? id => database.hasXmltvId(id) : undefined
      })
      warnings = validation.warnings
      if (Object.keys(validation.errors).length)
        return { ok: false, errors: validation.errors, warnings }

      const guide: MappingGuideData = {
        ...validation.value,
        name: database?.channelName(validation.value.xmltv_id) ?? validation.value.site_id,
        origin: 'manual'
      }
      mapping = { status: 'mapped', guide, updatedAt }
    }

    await this.lineups.setMapping(slug, item.key, mapping)

    return {
      ok: true,
      row: toRow(item, mapping, (await this.channelLogo()) ?? undefined),
      warnings
    }
  }

  // FR-P-7: accepts reviewed suggestions in one write. Nothing is saved when any channel or
  // entry is unknown, e.g. after a sync since the page loaded
  async acceptEntries(
    slug: string,
    request: BulkMappingRequestData
  ): Promise<{ rows: ChannelRowData[]; warnings: string[] }> {
    if (!(await this.lineups.get(slug))) error(404, `Lineup "${slug}" not found`)

    const { items } = parsePlaylist(await this.lineups.loadSource(slug))
    const byKey = new Map(items.map(item => [item.key, item]))
    const index = await this.readyIndex()
    const logo = (await this.channelLogo()) ?? undefined
    const updatedAt = new Date().toISOString()

    const changes: Record<string, MappingData> = {}
    const rows: ChannelRowData[] = []
    for (const { key, entry } of request.items) {
      const item = byKey.get(key)
      if (!item) error(404, `Channel "${key}" not found in lineup "${slug}"`)
      const mapping: MappingData = { status: 'mapped', guide: indexGuide(index, entry), updatedAt }
      changes[key] = mapping
      rows.push(toRow(item, mapping, logo))
    }
    await this.lineups.setMappings(slug, changes)

    const withoutId = rows.filter(row => !row.mapping?.guide?.xmltv_id).length
    const warnings = withoutId
      ? [`${withoutId} of these entries have no xmltv_id, so they get no iptv-org logo`]
      : []

    return { rows, warnings }
  }

  async clearMapping(slug: string, key: string): Promise<ChannelRowData> {
    const item = await this.requireItem(slug, key)
    await this.lineups.setMapping(slug, key, null)

    return toRow(item, null)
  }

  private async requireItem(slug: string, key: string): Promise<PlaylistItemData> {
    if (!(await this.lineups.get(slug))) error(404, `Lineup "${slug}" not found`)

    const { items } = parsePlaylist(await this.lineups.loadSource(slug))
    const item = items.find(item => item.key === key)
    if (!item) error(404, `Channel "${key}" not found in lineup "${slug}"`)

    return item
  }

  private async optionalDatabase(): Promise<Database | null> {
    try {
      return await this.database()
    } catch {
      return null
    }
  }

  // Same lookup channels.xml's `logo` attribute uses, so the editor shows the icon that will
  // actually be grabbed. Null while the iptv-org database isn't available yet
  private async channelLogo(): Promise<ChannelLogo | null> {
    const database = await this.optionalDatabase()

    return database ? xmltvId => database.logo(xmltvId) : null
  }

  private async readyIndex(): Promise<GuideIndex> {
    return (await this.guideIndex.get()) ?? error(503, 'The guide index is not ready yet')
  }
}

// Entries picked from the index are copied from it, so a client can't save one that doesn't exist
function indexGuide(index: GuideIndex, request: { site: string; site_id: string }) {
  const entry = index.find(request.site, request.site_id)
  if (!entry) error(400, `Guide entry ${request.site} / ${request.site_id} not found`)
  const { site, site_id, lang, xmltv_id, name, origin } = entry

  return { site, site_id, lang, xmltv_id, name, origin } satisfies MappingGuideData
}

function toRow(
  item: PlaylistItemData,
  mapping: MappingData | null,
  logo?: ChannelLogo
): ChannelRowData {
  return buildChannelRows(
    [item],
    { version: 1, items: mapping ? { [item.key]: mapping } : {} },
    logo
  )[0]
}

export const services = new Services(defaultConfig)
