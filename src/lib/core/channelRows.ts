import type { ChannelCountsData, ChannelRowData } from '$lib/types/channel'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingData, MappingsData } from '$lib/types/mapping'
import { compareChannelNumbers, type ChannelLogo } from './channelsXml'

// One editor row per M3U channel, in channel number order [FR-P-1]. "Suggested" is not
// stored: the editor shows it for unmapped rows once their top suggestion has loaded. `logo`
// resolves the mapped entry's current icon for display; it is never written to mappings.json
export function buildChannelRows(
  items: PlaylistItemData[],
  mappings: MappingsData,
  logo?: ChannelLogo
): ChannelRowData[] {
  return items
    .map(item => {
      const mapping = withLogo(mappings.items[item.key] ?? null, logo)
      const row: ChannelRowData = {
        key: item.key,
        number: item.number,
        name: item.name,
        logo: item.logo,
        status: mapping?.status ?? 'unmapped',
        mapping
      }

      return row
    })
    .sort((a, b) => compareChannelNumbers(a.number, b.number) || a.name.localeCompare(b.name))
}

function withLogo(mapping: MappingData | null, logo?: ChannelLogo): MappingData | null {
  if (!mapping?.guide?.xmltv_id || !logo) return mapping

  const logoUrl = logo(mapping.guide.xmltv_id)

  return logoUrl ? { ...mapping, guide: { ...mapping.guide, logo: logoUrl } } : mapping
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
