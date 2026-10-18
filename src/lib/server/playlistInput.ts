import type { LineupSourceData } from '$lib/types/lineup'
import { fetchPlaylist, PlaylistFetchError } from './fetchPlaylist'
import { parsePlaylist } from '$lib/core/playlistParser'
import { MAX_PLAYLIST_BYTES } from '$lib/constants'

export type PlaylistInputResult =
  | {
      ok: true
      m3u: string
      source: Omit<LineupSourceData, 'importedAt'>
      channels: number
      warnings: string[]
    }
  | { ok: false; error: string }

// The M3U of a lineup form: an uploaded file (`file`) or a URL to fetch (`url`), chosen by
// `sourceType` [FR-M-1, FR-M-2]. Playlists without channels are rejected [FR-M-7]
export async function readPlaylistInput(
  form: FormData,
  options: { fetch?: typeof fetchPlaylist } = {}
): Promise<PlaylistInputResult> {
  const sourceType = form.get('sourceType')
  let m3u: string
  let source: Omit<LineupSourceData, 'importedAt'>

  if (sourceType === 'url') {
    const url = String(form.get('url') ?? '').trim()
    if (!url) return { ok: false, error: 'Enter the playlist URL' }
    try {
      m3u = await (options.fetch ?? fetchPlaylist)(url)
    } catch (error) {
      if (error instanceof PlaylistFetchError)
        return { ok: false, error: `Could not fetch the playlist: ${error.message}` }
      throw error
    }
    source = { type: 'url', url }
  } else if (sourceType === 'upload') {
    const file = form.get('file')
    if (!(file instanceof File) || !file.size) return { ok: false, error: 'Choose an M3U file' }
    if (file.size > MAX_PLAYLIST_BYTES)
      return { ok: false, error: `The file is larger than ${MAX_PLAYLIST_BYTES / 1024 / 1024} MB` }
    m3u = await file.text()
    source = { type: 'upload' }
  } else {
    return { ok: false, error: 'Choose a file upload or a URL' }
  }

  const { items, warnings } = parsePlaylist(m3u)
  if (!items.length) return { ok: false, error: 'The playlist has no channels' }

  return { ok: true, m3u, source, channels: items.length, warnings }
}
