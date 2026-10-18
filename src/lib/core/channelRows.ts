import type { ChannelCountsData, ChannelRowData } from '$lib/types/channel'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingsData } from '$lib/types/mapping'
import { compareChannelNumbers } from './channelsXml'

// One editor row per M3U channel, in channel number order [FR-P-1]. "Suggested" is not
// stored: the editor shows it for unmapped rows once their top suggestion has loaded
export function buildChannelRows(
  items: PlaylistItemData[],
  mappings: MappingsData
): ChannelRowData[] {
  return items
    .map(item => {
      const mapping = mappings.items[item.key] ?? null

      return {
        key: item.key,
        number: item.number,
        name: item.name,
        logo: item.logo,
        status: mapping?.status ?? 'unmapped',
        mapping
      }
    })
    .sort((a, b) => compareChannelNumbers(a.number, b.number) || a.name.localeCompare(b.name))
}

// Per-status counts for the lineup list [FR-L-2] and the editor filters [FR-P-2]
export function countChannels(rows: ChannelRowData[]): ChannelCountsData {
  const counts: ChannelCountsData = {
    total: rows.length,
    mapped: 0,
    skipped: 0,
    unmapped: 0,
    stale: 0
  }
  for (const row of rows) {
    counts[row.status]++
    if (row.mapping?.stale) counts.stale++
  }

  return counts
}
