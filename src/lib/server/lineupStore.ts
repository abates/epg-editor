import type {
  LineupData,
  LineupFiltersData,
  LineupGrabData,
  LineupSourceData
} from '$lib/types/lineup'
import type { MappingData, MappingsData } from '$lib/types/mapping'
import { generateChannelsXml } from '$lib/core/channelsXml'
import { parsePlaylist } from '$lib/core/playlistParser'
import { isValidSlug, toSlug } from '$lib/core/slug'
import { Storage } from './storage'
import crypto from 'node:crypto'

const LINEUPS_DIR = 'lineups'
const GUIDES_DIR = 'guides'
const RUNS_DIR = 'status/runs'
const PENDING_SOURCE = 'pending-source.json'

export interface CreateLineupInput {
  name: string
  slug?: string
  source: Omit<LineupSourceData, 'importedAt'>
  m3u: string
  filters?: Partial<LineupFiltersData>
}

export interface UpdateLineupInput {
  name?: string
  filters?: Partial<LineupFiltersData>
  grab?: Partial<LineupGrabData>
}

export interface PendingSourceData {
  source: Omit<LineupSourceData, 'importedAt'>
  m3u: string
  createdAt: string
}

export interface LineupLoadError {
  slug: string
  message: string
}

export interface LineupListResult {
  lineups: LineupData[]
  errors: LineupLoadError[]
}

// CRUD over /data/lineups/<slug>/{lineup.json,source.m3u,mappings.json,channels.xml}.
// Writes to one lineup are queued so concurrent edits can't overwrite each other's changes
export class LineupStore {
  readonly storage: Storage
  private readonly queues = new Map<string, Promise<unknown>>()

  constructor(storage: Storage) {
    this.storage = storage
  }

  // A broken lineup.json is reported in `errors` and does not hide the other lineups [NFR-REL-1]
  async list(): Promise<LineupListResult> {
    const result: LineupListResult = { lineups: [], errors: [] }
    const slugs = (await this.storage.listDirs(LINEUPS_DIR)).filter(isValidSlug).sort()

    for (const slug of slugs) {
      try {
        result.lineups.push(await this.storage.json<LineupData>(this.file(slug, 'lineup.json')))
      } catch (error) {
        result.errors.push({ slug, message: (error as Error).message })
      }
    }

    return result
  }

  async exists(slug: string): Promise<boolean> {
    this.assertSlug(slug)

    return this.storage.exists(this.file(slug, 'lineup.json'))
  }

  async get(slug: string): Promise<LineupData | null> {
    if (!(await this.exists(slug))) return null

    return this.storage.json<LineupData>(this.file(slug, 'lineup.json'))
  }

  // Files are written to a temp dir that is renamed into place, so a failed create leaves nothing
  async create(input: CreateLineupInput): Promise<LineupData> {
    const name = input.name.trim()
    if (!name) throw new Error('lineup name is required')

    const slug = input.slug !== undefined ? input.slug.trim() : await this.uniqueSlug(name)
    this.assertSlug(slug)
    if (await this.storage.exists(this.dir(slug)))
      throw new Error(`lineup "${slug}" already exists`)

    const now = new Date().toISOString()
    const lineup: LineupData = {
      slug,
      name,
      source: { ...input.source, importedAt: now },
      filters: { countries: ['us'], languages: [], preferredSites: [], ...input.filters },
      grab: { enabled: true },
      createdAt: now,
      updatedAt: now
    }
    const mappings: MappingsData = { version: 1, items: {} }
    const { items } = parsePlaylist(input.m3u)

    const tmpDir = `${LINEUPS_DIR}/.tmp-${slug}-${crypto.randomUUID()}`
    try {
      await this.storage.saveJson(`${tmpDir}/lineup.json`, lineup)
      await this.storage.save(`${tmpDir}/source.m3u`, input.m3u)
      await this.storage.saveJson(`${tmpDir}/mappings.json`, mappings)
      await this.storage.save(`${tmpDir}/channels.xml`, generateChannelsXml(items, mappings))
      await this.storage.move(tmpDir, this.dir(slug))
    } finally {
      await this.storage.remove(tmpDir)
    }

    return lineup
  }

  async update(slug: string, changes: UpdateLineupInput): Promise<LineupData> {
    return this.exclusive(slug, () => this.applyUpdate(slug, changes))
  }

  private async applyUpdate(slug: string, changes: UpdateLineupInput): Promise<LineupData> {
    const lineup = await this.require(slug)
    const name = changes.name?.trim()
    if (changes.name !== undefined && !name) throw new Error('lineup name is required')

    const updated: LineupData = {
      ...lineup,
      name: name ?? lineup.name,
      filters: { ...lineup.filters, ...changes.filters },
      grab: { ...lineup.grab, ...changes.grab },
      updatedAt: new Date().toISOString()
    }
    await this.storage.saveJson(this.file(slug, 'lineup.json'), updated)

    return updated
  }

  // FR-L-3: removes the lineup, its guide files and its run history
  async delete(slug: string): Promise<void> {
    this.assertSlug(slug)
    await this.exclusive(slug, async () => {
      await this.storage.remove(this.dir(slug))
      await this.storage.remove(`${GUIDES_DIR}/${slug}.xml`)
      await this.storage.remove(`${GUIDES_DIR}/${slug}.xml.gz`)
      await this.storage.remove(`${RUNS_DIR}/${slug}.json`)
    })
  }

  async loadSource(slug: string): Promise<string> {
    await this.require(slug)

    return this.storage.load(this.file(slug, 'source.m3u'))
  }

  // Re-import. Callers drop mappings of removed keys themselves after the user confirms [FR-M-6]
  async saveSource(slug: string, m3u: string, source: Omit<LineupSourceData, 'importedAt'>) {
    const lineup = await this.require(slug)
    const now = new Date().toISOString()

    await this.storage.save(this.file(slug, 'source.m3u'), m3u)
    await this.storage.saveJson(this.file(slug, 'lineup.json'), {
      ...lineup,
      source: { ...source, importedAt: now },
      updatedAt: now
    })
    await this.writeChannelsXml(slug)
  }

  // FR-M-6: re-import replaces the source, keeps mappings of unchanged keys, and drops the
  // mappings of removed channels only when the user confirmed that
  async reimport(
    slug: string,
    m3u: string,
    source: Omit<LineupSourceData, 'importedAt'>,
    options: { dropRemoved: boolean }
  ): Promise<void> {
    await this.exclusive(slug, async () => {
      const { items } = parsePlaylist(m3u)
      if (!items.length) throw new Error('the playlist has no channels')

      if (options.dropRemoved) {
        const keys = new Set(items.map(item => item.key))
        const mappings = await this.loadMappings(slug)
        const kept = Object.entries(mappings.items).filter(([key]) => keys.has(key))
        if (kept.length < Object.keys(mappings.items).length) {
          await this.storage.saveJson(this.file(slug, 'mappings.json'), {
            ...mappings,
            items: Object.fromEntries(kept)
          })
        }
      }
      await this.saveSource(slug, m3u, source)
      await this.storage.remove(this.file(slug, PENDING_SOURCE))
    })
  }

  // A re-imported playlist waits here while the user reviews the diff
  async savePendingSource(slug: string, m3u: string, source: PendingSourceData['source']) {
    await this.require(slug)
    const pending: PendingSourceData = { source, m3u, createdAt: new Date().toISOString() }
    await this.storage.saveJson(this.file(slug, PENDING_SOURCE), pending)
  }

  async loadPendingSource(slug: string): Promise<PendingSourceData | null> {
    await this.require(slug)
    const file = this.file(slug, PENDING_SOURCE)
    if (!(await this.storage.exists(file))) return null

    return this.storage.json<PendingSourceData>(file)
  }

  async discardPendingSource(slug: string): Promise<void> {
    this.assertSlug(slug)
    await this.storage.remove(this.file(slug, PENDING_SOURCE))
  }

  async loadMappings(slug: string): Promise<MappingsData> {
    await this.require(slug)

    return this.storage.json<MappingsData>(this.file(slug, 'mappings.json'))
  }

  // FR-X-1: channels.xml is regenerated on every mapping change
  async saveMappings(slug: string, mappings: MappingsData): Promise<void> {
    await this.require(slug)
    await this.storage.saveJson(this.file(slug, 'mappings.json'), mappings)
    await this.writeChannelsXml(slug)
  }

  // FR-P-6: one channel's mapping, or null to clear it; channels.xml is rewritten each time
  async setMapping(slug: string, key: string, mapping: MappingData | null): Promise<MappingsData> {
    return this.exclusive(slug, async () => {
      const mappings = await this.loadMappings(slug)
      const items = { ...mappings.items }
      if (mapping) items[key] = mapping
      else delete items[key]

      const updated: MappingsData = { ...mappings, items }
      await this.saveMappings(slug, updated)

      return updated
    })
  }

  async loadChannelsXml(slug: string): Promise<string> {
    await this.require(slug)

    return this.storage.load(this.file(slug, 'channels.xml'))
  }

  async writeChannelsXml(slug: string): Promise<string> {
    const { items } = parsePlaylist(await this.loadSource(slug))
    const xml = generateChannelsXml(items, await this.loadMappings(slug))
    await this.storage.save(this.file(slug, 'channels.xml'), xml)

    return xml
  }

  channelsXmlPath(slug: string): string {
    this.assertSlug(slug)

    return this.storage.path(this.file(slug, 'channels.xml'))
  }

  // Runs `task` after every earlier queued write to the same lineup has settled
  private exclusive<T>(slug: string, task: () => Promise<T>): Promise<T> {
    const previous = this.queues.get(slug) ?? Promise.resolve()
    const result = previous.catch(() => {}).then(task)
    const settled = result.catch(() => {})
    this.queues.set(slug, settled)
    settled.then(() => {
      if (this.queues.get(slug) === settled) this.queues.delete(slug)
    })

    return result
  }

  private async require(slug: string): Promise<LineupData> {
    this.assertSlug(slug)
    const lineup = await this.get(slug)
    if (!lineup) throw new Error(`lineup "${slug}" not found`)

    return lineup
  }

  private async uniqueSlug(name: string): Promise<string> {
    const base = toSlug(name)
    if (!isValidSlug(base)) return base

    let slug = base
    for (let n = 2; await this.storage.exists(this.dir(slug)); n++) slug = `${base}-${n}`

    return slug
  }

  private assertSlug(slug: string) {
    if (!isValidSlug(slug)) {
      throw new Error(`invalid slug "${slug}": use lower-case letters, digits, "." and "-"`)
    }
  }

  private dir(slug: string): string {
    return `${LINEUPS_DIR}/${slug}`
  }

  private file(slug: string, name: string): string {
    return `${LINEUPS_DIR}/${slug}/${name}`
  }
}
