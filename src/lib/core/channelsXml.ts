import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingsData } from '$lib/types/mapping'
import { escapeString } from './escapeString'

const EOL = '\n'

// Same layout as epg's generateChannelsXML, plus `lcn`, which epg drops and Plex needs
export function generateChannelsXml(items: PlaylistItemData[], mappings: MappingsData): string {
  let output = `<?xml version="1.0" encoding="UTF-8"?>${EOL}<channels>${EOL}`

  const mapped = items
    .map(item => ({ item, guide: mappings.items[item.key]?.guide }))
    .filter(({ item, guide }) => mappings.items[item.key]?.status === 'mapped' && guide)
    .sort((a, b) => compareItems(a.item, b.item))

  for (const { item, guide } of mapped) {
    if (!guide) continue
    const site = escapeString(guide.site)
    const site_id = escapeString(guide.site_id)
    const lang = escapeString(guide.lang)
    const xmltv_id = escapeString(guide.xmltv_id)
    const lcn = escapeString(item.number)
    const displayName = escapeString(item.name)

    output += `  <channel site="${site}" site_id="${site_id}" lang="${lang}" xmltv_id="${xmltv_id}" lcn="${lcn}">${displayName}</channel>${EOL}`
  }

  output += `</channels>${EOL}`

  return output
}

// Channel numbers sort by numeric parts ("2.2" < "2.10" < "10.1"); unnumbered channels go last
export function compareChannelNumbers(a: string | null, b: string | null): number {
  if (a === b) return 0
  if (a === null) return 1
  if (b === null) return -1

  const partsA = a.split('.').map(Number)
  const partsB = b.split('.').map(Number)
  for (let i = 0; i < Math.max(partsA.length, partsB.length); i++) {
    const diff = (partsA[i] ?? -1) - (partsB[i] ?? -1)
    if (diff) return diff
  }

  return 0
}

function compareItems(a: PlaylistItemData, b: PlaylistItemData): number {
  return compareChannelNumbers(a.number, b.number) || a.name.localeCompare(b.name)
}
