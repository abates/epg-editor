import type { DatabaseChannelData } from '$lib/types/database'
import type { DatabaseStatsData } from '$lib/types/sync'
import { parseXmltvId } from '$lib/core/xmltvId'
import MiniSearch from 'minisearch'
import * as sdk from '@iptv-org/sdk'

const SEARCH_LIMIT = 20

// The iptv-org database (channels, feeds) that epg's `api:load` downloads into
// <epg>/temp/data. Loaded the same way epg's scripts/api.ts does [FR-S-5]
export class Database {
  readonly channels: sdk.Models.Channel[]
  readonly feeds: sdk.Models.Feed[]
  private readonly channelsById: Map<string, sdk.Models.Channel>
  private readonly feedsByStreamId: Map<string, sdk.Models.Feed>
  private readonly feedsByChannel: Map<string, sdk.Models.Feed[]>
  private search: MiniSearch<{
    id: number
    xmltv_id: string
    name: string
    alt_names: string
  }> | null = null

  constructor(channels: sdk.Models.Channel[], feeds: sdk.Models.Feed[]) {
    this.channels = channels
    this.feeds = feeds
    this.channelsById = new Map(channels.map(channel => [channel.id, channel]))
    this.feedsByStreamId = new Map(feeds.map(feed => [feed.getStreamId(), feed]))
    this.feedsByChannel = new Map()
    for (const feed of feeds) {
      const list = this.feedsByChannel.get(feed.channel)
      if (list) list.push(feed)
      else this.feedsByChannel.set(feed.channel, [feed])
    }
  }

  static async load(dataDir: string): Promise<Database> {
    const dataManager = new sdk.DataManager({ dataDir })
    await dataManager.loadFromDisk()
    dataManager.processData()
    const { channels, feeds } = dataManager.getProcessedData()

    return new Database(channels.all(), feeds.all())
  }

  // FR-E-2: warn (don't block) when an xmltv_id is not in the database
  hasXmltvId(xmltvId: string): boolean {
    const parts = parseXmltvId(xmltvId)
    if (!parts) return false
    if (!parts.feed) return this.channelsById.has(parts.channel)

    return this.feedsByStreamId.has(xmltvId)
  }

  // Display name for a manual mapping; null when the channel is not in the database
  channelName(xmltvId: string): string | null {
    const parts = parseXmltvId(xmltvId)

    return (parts && this.channelsById.get(parts.channel)?.name) ?? null
  }

  // Same lookup as epg's grab (getLogoForChannel): the feed's first logo, then the channel's.
  // Null when the database has none
  logo(xmltvId: string): string | null {
    const feedLogo = this.feedsByStreamId.get(xmltvId)?.getLogos().first()
    if (feedLogo) return feedLogo.url

    const [channelId] = xmltvId.split('@')

    return this.channelsById.get(channelId)?.getLogos().first()?.url ?? null
  }

  // Channels by id, name or alternative name, each with its feeds [FR-E-1, FR-S-5]
  find(query: string, limit = SEARCH_LIMIT): DatabaseChannelData[] {
    if (!query.trim()) return []

    return this.index()
      .search(query, {
        combineWith: 'AND',
        prefix: true,
        fuzzy: term => (term.length > 4 ? 0.2 : false)
      })
      .slice(0, limit)
      .map(result => this.toChannelData(this.channels[result.id]))
  }

  stats(): DatabaseStatsData {
    return { channels: this.channels.length, feeds: this.feeds.length }
  }

  // Built on first use: most page loads never search the database
  private index() {
    if (!this.search) {
      this.search = new MiniSearch({
        fields: ['xmltv_id', 'name', 'alt_names'],
        searchOptions: { boost: { xmltv_id: 2, name: 2 } }
      })
      this.search.addAll(
        this.channels.map((channel, id) => ({
          id,
          xmltv_id: channel.id,
          name: channel.name,
          alt_names: channel.alt_names.join(' ')
        }))
      )
    }

    return this.search
  }

  private toChannelData(channel: sdk.Models.Channel): DatabaseChannelData {
    const feeds = (this.feedsByChannel.get(channel.id) ?? []).map(feed => ({
      xmltv_id: feed.getStreamId(),
      name: feed.name,
      is_main: feed.is_main
    }))

    return {
      xmltv_id: channel.id,
      name: channel.name,
      alt_names: channel.alt_names,
      country: channel.country,
      closed: channel.closed ?? null,
      feeds: feeds.sort((a, b) => Number(b.is_main) - Number(a.is_main))
    }
  }
}
