import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { fetchPlaylist } from '$lib/server/fetchPlaylist'
import type { AddressInfo } from 'node:net'
import http from 'node:http'

const m3u = '#EXTM3U\n#EXTINF:-1,2.1 WCBS-HD\nhttp://hdhr/auto/v2.1\n'

const server = http.createServer((request, response) => {
  if (request.url === '/lineup.m3u') {
    response.end(m3u)
  } else if (request.url === '/large') {
    // No content-length, so the cap has to be enforced while streaming
    response.write('x'.repeat(600))
    response.end('x'.repeat(600))
  } else if (request.url === '/declared-large') {
    response.setHeader('content-length', '2000')
    response.end('x'.repeat(2000))
  } else if (request.url === '/slow') {
    setTimeout(() => response.end(m3u), 500)
  } else {
    response.statusCode = 404
    response.end()
  }
})

let base: string

beforeAll(async () => {
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

afterAll(async () => {
  server.closeAllConnections()
  await new Promise(resolve => server.close(resolve))
})

describe('fetchPlaylist', () => {
  it('returns the body', async () => {
    expect(await fetchPlaylist(`${base}/lineup.m3u`)).toBe(m3u)
  })

  it('rejects invalid URLs and other protocols', async () => {
    await expect(fetchPlaylist('not a url')).rejects.toThrow('not a valid URL')
    await expect(fetchPlaylist('file:///etc/passwd')).rejects.toThrow('Only http and https')
  })

  it('rejects error responses', async () => {
    await expect(fetchPlaylist(`${base}/missing`)).rejects.toThrow('HTTP 404')
  })

  it('enforces the size cap with and without a content-length', async () => {
    await expect(fetchPlaylist(`${base}/large`, { maxBytes: 1000 })).rejects.toThrow('larger than')
    await expect(fetchPlaylist(`${base}/declared-large`, { maxBytes: 1000 })).rejects.toThrow(
      'larger than'
    )
  })

  it('times out', async () => {
    await expect(fetchPlaylist(`${base}/slow`, { timeout: 100 })).rejects.toThrow('No answer')
  })

  it('reports connection errors', async () => {
    const closed = http.createServer()
    await new Promise<void>(resolve => closed.listen(0, '127.0.0.1', resolve))
    const { port } = closed.address() as AddressInfo
    await new Promise(resolve => closed.close(resolve))

    await expect(fetchPlaylist(`http://127.0.0.1:${port}/lineup.m3u`)).rejects.toThrow(
      'ECONNREFUSED'
    )
  })
})
