import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingsData } from '$lib/types/mapping'
import { escapeString } from './escapeString'

const EOL = '\n'

// Logo URL for an iptv-org xmltv_id, or null when there is none
export type ChannelLogo = (xmltvId: string) => string | null

export interface ChannelsXmlOptions {
  logo?: ChannelLogo
}

// The guide's <channel id> for a lineup channel. It comes from the lineup and the channel's key
// [FR-M-4], not from the mapped entry, so re-mapping a channel doesn't change it and clients
// such as Plex keep their channel mapping. Keys are unique within a lineup
export function guideChannelId(slug: string, key: string): string {
  return `${slug}.${key}`
}

// Same layout as epg's generateChannelsXML, plus `lcn`, which epg drops and Plex needs.
// `xmltv_id` is the stable guide id, so epg's grab can't find the logo by it: the entry's real
// xmltv_id is looked up here instead and written as `logo`
export function generateChannelsXml(
  slug: string,
  items: PlaylistItemData[],
  mappings: MappingsData,
  { logo }: ChannelsXmlOptions = {}
): string {
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
    const xmltv_id = escapeString(guideChannelId(slug, item.key))
    const lcn = escapeString(item.number)
    const logoUrl = guide.xmltv_id && logo ? logo(guide.xmltv_id) : null
    const logoAttr = logoUrl ? ` logo="${escapeString(logoUrl)}"` : ''
    const displayName = escapeString(item.name)

    output += `  <channel site="${site}" site_id="${site_id}" lang="${lang}" xmltv_id="${xmltv_id}" lcn="${lcn}"${logoAttr}>${displayName}</channel>${EOL}`
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
