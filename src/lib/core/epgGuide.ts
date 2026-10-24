import type { GuideViewChannelData, GuideViewData } from '$lib/types/guideView'
import type { PlaylistItemData } from '$lib/types/playlist'
import type { MappingsData } from '$lib/types/mapping'
import { compareChannelNumbers } from './channelsXml'
import type { Xmltv, XmltvProgramme } from '@iptv/xmltv'

export type GuideLogoLookup = (xmltvId: string) => string | null

// Logo for a guide channel: the lineup's *current* mapping's xmltv_id, looked up the same way
// the editor resolves mapped-channel icons (Database.logo) [issue #9] — never a value read from
// the guide file itself, so a re-mapping shows its new icon without waiting for the next grab
export function buildGuideView(
  xmltv: Xmltv,
  slug: string,
  items: PlaylistItemData[],
  mappings: MappingsData,
  generatedAt: Date,
  logo?: GuideLogoLookup
): GuideViewData {
  const itemsByKey = new Map(items.map(item => [item.key, item]))
  const channels: GuideViewChannelData[] = []
  const indexByKey = new Map<string, number>()

  for (const channel of xmltv.channels ?? []) {
    const key = channelKey(slug, channel.id)
    if (key === null || indexByKey.has(key)) continue

    const item = itemsByKey.get(key)
    const xmltvId = mappings.items[key]?.guide?.xmltv_id
    indexByKey.set(key, channels.length)
    channels.push({
      key,
      name: item?.name ?? firstValue(channel.displayName) ?? key,
      number: item?.number ?? null,
      logo: (xmltvId && logo?.(xmltvId)) || null,
      programs: []
    })
  }
  channels.sort((a, b) => compareChannelNumbers(a.number, b.number) || a.name.localeCompare(b.name))
  channels.forEach((channel, i) => indexByKey.set(channel.key, i))

  let rangeStart: Date | null = null
  let rangeStop: Date | null = null
  for (const programme of xmltv.programmes ?? []) {
    const key = channelKey(slug, programme.channel)
    const index = key === null ? undefined : indexByKey.get(key)
    if (index === undefined) continue

    const { start, stop } = programmeTimes(programme)
    channels[index].programs.push({
      start: start.toISOString(),
      stop: stop.toISOString(),
      title: firstValue(programme.title) ?? '',
      desc: firstValue(programme.desc),
      category: joinValues(programme.category)
    })
    if (!rangeStart || start < rangeStart) rangeStart = start
    if (!rangeStop || stop > rangeStop) rangeStop = stop
  }
  for (const channel of channels) channel.programs.sort((a, b) => a.start.localeCompare(b.start))

  return {
    channels,
    range:
      rangeStart && rangeStop
        ? { start: rangeStart.toISOString(), stop: rangeStop.toISOString() }
        : null,
    generatedAt: generatedAt.toISOString()
  }
}

// Strips the lineup's slug prefix from a guide `<channel id>` to recover the M3U key it was
// generated from [FR-X-8]. Null for an id that doesn't belong to this lineup (a hand-edited or
// foreign guide file — shouldn't happen for one our own grab wrote)
function channelKey(slug: string, id: string): string | null {
  const prefix = `${slug}.`

  return id.startsWith(prefix) ? id.slice(prefix.length) : null
}

// `stop` is optional in the XMLTV DTD; without it the programme's end is unknown, so it is
// drawn as zero-length (the grid enforces a minimum visible width)
function programmeTimes(programme: XmltvProgramme): { start: Date; stop: Date } {
  return { start: programme.start, stop: programme.stop ?? programme.start }
}

function firstValue(values?: { _value: string }[]): string | null {
  return values?.[0]?._value ?? null
}

function joinValues(values?: { _value: string }[]): string | null {
  return values?.length ? values.map(value => value._value).join(', ') : null
}
