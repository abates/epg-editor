import { parsePlaylist } from '$lib/core/playlistParser'
import { diffPlaylists } from '$lib/core/playlistDiff'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs/promises'

const current = parsePlaylist(await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8'))
const next = parsePlaylist(
  await fs.readFile('tests/__data__/input/playlistDiff/hdhomerun-next.m3u', 'utf8')
)
const expected = JSON.parse(
  await fs.readFile('tests/__data__/expected/playlistDiff/hdhomerun.json', 'utf8')
)

describe('diffPlaylists', () => {
  it('lists added, removed and renamed channels by key in channel order', () => {
    expect(diffPlaylists(current.items, next.items)).toEqual(expected)
  })

  it('reports no changes for the same playlist', () => {
    expect(diffPlaylists(current.items, current.items)).toEqual({
      added: [],
      removed: [],
      renamed: [],
      unchanged: current.items.length
    })
  })
})
