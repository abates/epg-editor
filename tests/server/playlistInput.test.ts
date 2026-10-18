import { readPlaylistInput } from '$lib/server/playlistInput'
import { PlaylistFetchError } from '$lib/server/fetchPlaylist'
import { MAX_PLAYLIST_BYTES } from '$lib/constants'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs/promises'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')

function form(fields: Record<string, string | File>): FormData {
  const data = new FormData()
  for (const [name, value] of Object.entries(fields)) data.set(name, value)

  return data
}

describe('readPlaylistInput', () => {
  it('reads an uploaded file', async () => {
    const file = new File([m3u], 'lineup.m3u')

    expect(await readPlaylistInput(form({ sourceType: 'upload', file }))).toEqual({
      ok: true,
      m3u,
      source: { type: 'upload' },
      channels: 14,
      warnings: []
    })
  })

  it('fetches a URL and stores it as the source', async () => {
    const fetch = async (url: string) => (url === 'http://hdhr/lineup.m3u' ? m3u : '')

    expect(
      await readPlaylistInput(form({ sourceType: 'url', url: ' http://hdhr/lineup.m3u ' }), {
        fetch
      })
    ).toMatchObject({ ok: true, source: { type: 'url', url: 'http://hdhr/lineup.m3u' } })
  })

  it('turns fetch failures into form errors', async () => {
    const fetch = async () => {
      throw new PlaylistFetchError('No answer within 10 s')
    }

    expect(
      await readPlaylistInput(form({ sourceType: 'url', url: 'http://x' }), { fetch })
    ).toEqual({ ok: false, error: 'Could not fetch the playlist: No answer within 10 s' })
  })

  it('rejects missing input, large files and playlists without channels', async () => {
    const error = async (fields: Record<string, string | File>) => {
      const result = await readPlaylistInput(form(fields))
      return result.ok ? null : result.error
    }

    expect(await error({})).toBe('Choose a file upload or a URL')
    expect(await error({ sourceType: 'url' })).toBe('Enter the playlist URL')
    expect(await error({ sourceType: 'upload' })).toBe('Choose an M3U file')
    expect(
      await error({
        sourceType: 'upload',
        file: new File(['x'.repeat(MAX_PLAYLIST_BYTES + 1)], 'big.m3u')
      })
    ).toBe('The file is larger than 5 MB')
    expect(await error({ sourceType: 'upload', file: new File(['#EXTM3U\n'], 'empty.m3u') })).toBe(
      'The playlist has no channels'
    )
  })
})
