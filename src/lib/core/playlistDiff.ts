import type { PlaylistItemData } from '$lib/types/playlist'
import type { PlaylistDiffData } from '$lib/types/playlistDiff'
import { compareChannelNumbers } from './channelsXml'

// FR-M-6: channels are matched by key, so a renamed channel keeps its mapping
export function diffPlaylists(
  current: PlaylistItemData[],
  next: PlaylistItemData[]
): PlaylistDiffData {
  const currentByKey = new Map(current.map(item => [item.key, item]))
  const nextKeys = new Set(next.map(item => item.key))

  const added = next.filter(item => !currentByKey.has(item.key))
  const removed = current.filter(item => !nextKeys.has(item.key))
  const renamed = next.flatMap(item => {
    const before = currentByKey.get(item.key)
    if (!before || before.name === item.name) return []

    return [{ key: item.key, number: item.number, from: before.name, to: item.name }]
  })

  return {
    added: added.map(toChannel).sort(compareChannels),
    removed: removed.map(toChannel).sort(compareChannels),
    renamed: renamed.sort(compareChannels),
    unchanged: next.length - added.length - renamed.length
  }
}

function toChannel(item: PlaylistItemData) {
  return { key: item.key, number: item.number, name: item.name }
}

function compareChannels(a: { number: string | null; key: string }, b: typeof a): number {
  return compareChannelNumbers(a.number, b.number) || a.key.localeCompare(b.key)
}
