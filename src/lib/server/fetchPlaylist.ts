import { MAX_PLAYLIST_BYTES, PLAYLIST_FETCH_TIMEOUT } from '$lib/constants'

export interface FetchPlaylistOptions {
  maxBytes?: number
  timeout?: number
}

// Its message is safe to show to the user as is
export class PlaylistFetchError extends Error {}

// FR-M-2 / NFR-SEC-2: http(s) only, with a timeout and a size cap enforced while streaming
export async function fetchPlaylist(
  url: string,
  options: FetchPlaylistOptions = {}
): Promise<string> {
  const maxBytes = options.maxBytes ?? MAX_PLAYLIST_BYTES
  const timeout = options.timeout ?? PLAYLIST_FETCH_TIMEOUT

  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    throw new PlaylistFetchError(`"${url}" is not a valid URL`)
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')
    throw new PlaylistFetchError('Only http and https URLs are supported')

  const signal = AbortSignal.timeout(timeout)
  try {
    const response = await fetch(parsed, { signal })
    if (!response.ok) throw new PlaylistFetchError(`The server answered HTTP ${response.status}`)

    const length = Number(response.headers.get('content-length'))
    if (length > maxBytes) throw tooLarge(maxBytes)
    if (!response.body) return ''

    const chunks: Uint8Array[] = []
    let size = 0
    for await (const chunk of response.body) {
      size += chunk.byteLength
      if (size > maxBytes) throw tooLarge(maxBytes)
      chunks.push(chunk)
    }

    return Buffer.concat(chunks).toString('utf8')
  } catch (error) {
    if (error instanceof PlaylistFetchError) throw error
    if (signal.aborted) throw new PlaylistFetchError(`No answer within ${timeout / 1000} s`)

    const cause = (error as Error).cause as Error | undefined
    throw new PlaylistFetchError(cause?.message ?? (error as Error).message, { cause: error })
  }
}

function tooLarge(maxBytes: number): PlaylistFetchError {
  return new PlaylistFetchError(`The playlist is larger than ${maxBytes / 1024 / 1024} MB`)
}
