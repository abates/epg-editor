import type { DatabaseStatsData } from '$lib/types/sync'
import { parseXmltvId } from '$lib/core/xmltvId'
import * as sdk from '@iptv-org/sdk'

// The iptv-org database (channels, feeds) that epg's `api:load` downloads into
// <epg>/temp/data. Loaded the same way epg's scripts/api.ts does [FR-S-5]
export class Database {
  readonly channels: sdk.Models.Channel[]
  readonly feeds: sdk.Models.Feed[]
  private readonly channelIds: Set<string>
  private readonly streamIds: Set<string>

  constructor(channels: sdk.Models.Channel[], feeds: sdk.Models.Feed[]) {
    this.channels = channels
    this.feeds = feeds
    this.channelIds = new Set(channels.map(channel => channel.id))
    this.streamIds = new Set(feeds.map(feed => feed.getStreamId()))
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
    if (!parts.feed) return this.channelIds.has(parts.channel)

    return this.streamIds.has(xmltvId)
  }

  stats(): DatabaseStatsData {
    return { channels: this.channels.length, feeds: this.feeds.length }
  }
}
