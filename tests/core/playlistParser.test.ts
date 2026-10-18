import { parsePlaylist } from '$lib/core/playlistParser'
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'

const input = (name: string) => fs.readFileSync(`tests/__data__/input/m3u/${name}`, 'utf8')
const expected = (name: string) =>
  JSON.parse(fs.readFileSync(`tests/__data__/expected/m3u/${name}`, 'utf8'))

describe('parsePlaylist', () => {
  it.each(['hdhomerun', 'generic', 'edge-cases'])('parses %s.m3u', name => {
    expect(parsePlaylist(input(`${name}.m3u`))).toEqual(expected(`${name}.json`))
  })

  it('keeps the edge-case fixture byte-exact (BOM + CRLF)', () => {
    const content = input('edge-cases.m3u')
    expect(content.startsWith('\uFEFF')).toBe(true)
    expect(content).toContain('\r\n')
  })

  it('derives the key in FR-M-4 order', () => {
    const m3u = [
      '#EXTM3U',
      '#EXTINF:-1 tvg-id="a" channel-id="b" tvg-chno="c" channel-number="d",One',
      'http://x/1',
      '#EXTINF:-1 tvg-id="a" channel-id="b" tvg-chno="c",Two',
      'http://x/2',
      '#EXTINF:-1 tvg-id="a" channel-id="b",Three',
      'http://x/3',
      '#EXTINF:-1 tvg-id="a",Four',
      'http://x/4',
      '#EXTINF:-1 tvg-id="",Five',
      'http://x/5'
    ].join('\n')

    expect(parsePlaylist(m3u).items.map(item => item.key)).toEqual([
      'd',
      'c',
      'b',
      'a',
      'http://x/5'
    ])
  })

  it('derives the number from attributes, then from the title', () => {
    const m3u = [
      '#EXTINF:-1 tvg-chno="7",7.1 Title Number Ignored',
      'http://x/1',
      '#EXTINF:-1,11.2 WPIX-HD',
      'http://x/2',
      '#EXTINF:-1,3ABN',
      'http://x/3'
    ].join('\n')

    expect(parsePlaylist(m3u).items.map(({ number, name }) => ({ number, name }))).toEqual([
      { number: '7', name: '7.1 Title Number Ignored' },
      { number: '11.2', name: 'WPIX-HD' },
      { number: null, name: '3ABN' }
    ])
  })

  it('warns about entries without a usable stream URL', () => {
    const m3u = [
      '#EXTM3U',
      '#EXTINF:-1 tvg-id="a",No URL',
      '#EXTINF:-1 tvg-id="b",UDP',
      'udp://@239.0.0.1:1234',
      'http://x/orphan',
      '#EXTINF:-1 tvg-id="c",Last'
    ].join('\n')

    const result = parsePlaylist(m3u)
    expect(result.items).toEqual([])
    expect(result.warnings).toEqual([
      'line 2: "No URL" has no stream URL',
      'line 4: "UDP" skipped, only http(s) URLs are supported',
      'line 5: stream URL without #EXTINF skipped',
      'line 6: "Last" has no stream URL'
    ])
  })

  it('ignores malformed header attributes', () => {
    const result = parsePlaylist('#EXTM3U x-tvg-url=bad\n#EXTINF:-1,A\nhttp://x/a\n')
    expect(result.items.map(item => item.name)).toEqual(['A'])
    expect(result.warnings).toEqual(['line 1: malformed #EXTM3U attributes ignored'])
  })

  // Each of these makes @iptv/playlist loop forever when passed to it unfiltered
  it.each([
    ['unquoted attribute', '#EXTM3U\n#EXTINF:-1 tvg-id=x,A\nhttp://a\n'],
    ['rtsp URL with a query', '#EXTM3U\n#EXTINF:-1 tvg-id="x",A\nrtsp://cam/stream?a=b\n'],
    ['stray line with =', '#EXTM3U\n#EXTINF:-1 tvg-id="x",A\nhttp://a\nfoo=bar\n'],
    ['bare word before the title', '#EXTINF:-1 foo,T a=b\nhttp://a\n'],
    ['header with a bare word', '#EXTM3Ua,1.2=\nhttp://a\n']
  ])('does not hang on %s', (_, m3u) => {
    expect(() => parsePlaylist(m3u)).not.toThrow()
  })
})
