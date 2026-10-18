import type { GuideIndexStatsData } from '$lib/types/sync'
import type { GuideEntryData } from '$lib/types/guide'
import type { GuideLookup } from '$lib/core/staleMappings'
import { countryFromXmltvId } from '$lib/core/xmltvId'
import { EPGGrabber } from 'epg-grabber'
import fs from 'node:fs/promises'
import path from 'node:path'

export interface GuideIndexError {
  file: string
  message: string
}

// All guide entries from <epg>/sites/*/*.channels.xml, overlay sites included [FR-S-1].
// Parsed with epg-grabber so the semantics match the grabber
export class GuideIndex implements GuideLookup {
  readonly entries: GuideEntryData[]
  readonly sites: string[]
  readonly errors: GuideIndexError[]
  private readonly keyed: Map<string, GuideEntryData>
  private readonly siteSet: Set<string>

  constructor(entries: GuideEntryData[], sites: string[], errors: GuideIndexError[] = []) {
    this.entries = entries
    this.sites = sites
    this.errors = errors
    this.keyed = new Map(entries.map(entry => [entryKey(entry.site, entry.site_id), entry]))
    this.siteSet = new Set(sites)
  }

  // A site folder counts as overlay when it is a symlink (see overlay.ts)
  static async load(sitesDir: string): Promise<GuideIndex> {
    const entries: GuideEntryData[] = []
    const sites: string[] = []
    const errors: GuideIndexError[] = []

    for (const site of (await readdir(sitesDir)).sort()) {
      const siteDir = path.join(sitesDir, site)
      const lstat = await fs.lstat(siteDir)
      const origin = lstat.isSymbolicLink() ? 'overlay' : 'upstream'
      // Skips plain files and broken links
      const files = await fs.readdir(siteDir).catch(() => null)
      if (!files) continue
      sites.push(site)

      for (const file of files.filter(file => file.endsWith('.channels.xml')).sort()) {
        const relative = `${site}/${file}`
        try {
          const xml = await fs.readFile(path.join(siteDir, file), 'utf8')
          for (const channel of EPGGrabber.parseChannelsXML(xml)) {
            entries.push({
              site: channel.site || site,
              site_id: channel.site_id,
              lang: channel.lang || null,
              xmltv_id: channel.xmltv_id || '',
              name: channel.name,
              logo: channel.logo || null,
              country: countryFromXmltvId(channel.xmltv_id || ''),
              origin
            })
          }
        } catch (error) {
          errors.push({ file: relative, message: (error as Error).message })
        }
      }
    }

    return new GuideIndex(entries, sites, errors)
  }

  get count(): number {
    return this.entries.length
  }

  find(site: string, site_id: string): GuideEntryData | undefined {
    return this.keyed.get(entryKey(site, site_id))
  }

  hasEntry(site: string, site_id: string): boolean {
    return this.keyed.has(entryKey(site, site_id))
  }

  hasSite(site: string): boolean {
    return this.siteSet.has(site)
  }

  stats(): GuideIndexStatsData {
    return { sites: this.sites.length, entries: this.count, errors: this.errors }
  }
}

// The web process keeps one index and rebuilds it when the sync command rewrites
// status/sync.json, checking the file's mtime at most once per throttle period [FR-G-4]
export class GuideIndexCache {
  readonly sitesDir: string
  readonly statusFile: string
  readonly throttleMs: number
  private index: GuideIndex | null = null
  private loadedMtime = 0
  private checkedAt = -Infinity
  private pending: Promise<GuideIndex | null> | null = null

  constructor(options: { sitesDir: string; statusFile: string; throttleMs?: number }) {
    this.sitesDir = options.sitesDir
    this.statusFile = options.statusFile
    this.throttleMs = options.throttleMs ?? 5000
  }

  // null until the first sync has finished (the UI shows "initialising") [NFR-DEP-3]
  async get(now = Date.now()): Promise<GuideIndex | null> {
    if (this.pending) return this.pending
    if (now - this.checkedAt < this.throttleMs) return this.index
    this.checkedAt = now

    // Set before the first await so concurrent callers share one stat and one load
    this.pending = this.refresh().finally(() => {
      this.pending = null
    })

    return this.pending
  }

  private async refresh(): Promise<GuideIndex | null> {
    const mtime = await fs
      .stat(this.statusFile)
      .then(stats => stats.mtimeMs)
      .catch(() => 0)
    if (!mtime || (this.index && mtime === this.loadedMtime)) return this.index

    this.index = await GuideIndex.load(this.sitesDir)
    this.loadedMtime = mtime

    return this.index
  }
}

function entryKey(site: string, site_id: string): string {
  return `${site}\u0000${site_id}`
}

async function readdir(dir: string): Promise<string[]> {
  try {
    return await fs.readdir(dir)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}
