import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { LineupStore } from '$lib/server/lineupStore'
import { RunHistory } from '$lib/server/runHistory'
import { Storage } from '$lib/server/storage'
import type { MappingsData } from '$lib/types/mapping'
import { execFile } from 'node:child_process'
import { gunzipSync } from 'node:zlib'
import { promisify } from 'node:util'
import http from 'node:http'
import fs from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'

// ARCHITECTURE §8 / NFR-COMPAT-1: the real `npm run run:all` against a real iptv-org/epg
// checkout (clone, npm ci, api:load) and an overlay site served from a local HTTP server.
// Needs network access and takes several minutes: `npm run test:integration`.
// INTEGRATION_EPG_REPO / INTEGRATION_EPG_REF pick the checkout (a local path makes cloning fast)
const EPG_REPO = process.env.INTEGRATION_EPG_REPO ?? 'https://github.com/iptv-org/epg.git'
// The commit the M1 lcn spike ran against
const EPG_REF = process.env.INTEGRATION_EPG_REF ?? '6f6cfe2f82fac6bf4e09def36baae4fc5656bacc'
const SITE = 'mock.local'

const m3u = await fs.readFile('tests/__data__/input/m3u/hdhomerun.m3u', 'utf8')

let rootDir: string
let server: http.Server
let output: { code: number; stdout: string; stderr: string }

function siteConfig(port: number): string {
  // require('dayjs') only resolves from epg's node_modules with NODE_PRESERVE_SYMLINKS=1
  return `const dayjs = require('dayjs')

module.exports = {
  site: '${SITE}',
  days: 1,
  url({ channel, date }) {
    return 'http://127.0.0.1:${port}/' + channel.site_id + '?date=' + date.format('YYYY-MM-DD')
  },
  parser({ content }) {
    return JSON.parse(content).map(item => ({
      title: item.title,
      start: dayjs(item.start),
      stop: dayjs(item.stop)
    }))
  }
}
`
}

const channelsXml = `<?xml version="1.0" encoding="UTF-8"?>
<channels>
  <channel site="${SITE}" lang="en" xmltv_id="WCBSTV.us@SD" site_id="wcbs">WCBS</channel>
  <channel site="${SITE}" lang="en" xmltv_id="" site_id="nbclx">NBC LX</channel>
</channels>
`

function mapped(site_id: string, xmltv_id: string, name: string): MappingsData['items'][string] {
  return {
    status: 'mapped',
    guide: { site: SITE, site_id, lang: 'en', xmltv_id, name, origin: 'overlay' },
    updatedAt: '2026-01-01T00:00:00.000Z'
  }
}

beforeAll(async () => {
  rootDir = await fs.mkdtemp(path.join(os.tmpdir(), 'epg-editor-integration-'))
  const storageDir = path.join(rootDir, 'data')
  const overlayDir = path.join(rootDir, 'sites')

  server = http.createServer((request, response) => {
    const day = new URL(request.url ?? '/', 'http://localhost').searchParams.get('date')
    const programs = [0, 1].map(hour => ({
      title: `${request.url?.split('?')[0].slice(1)} show ${hour}`,
      start: `${day}T0${hour}:00:00Z`,
      stop: `${day}T0${hour + 1}:00:00Z`
    }))
    response.setHeader('content-type', 'application/json')
    response.end(JSON.stringify(programs))
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const { port } = server.address() as { port: number }

  await fs.mkdir(path.join(overlayDir, SITE), { recursive: true })
  await fs.writeFile(path.join(overlayDir, SITE, `${SITE}.config.js`), siteConfig(port))
  await fs.writeFile(path.join(overlayDir, SITE, `${SITE}.channels.xml`), channelsXml)

  const store = new LineupStore(new Storage(storageDir))
  await store.create({ name: 'OTA', slug: 'ota', source: { type: 'upload' }, m3u })
  await store.saveMappings('ota', {
    version: 1,
    items: {
      '2.1': mapped('wcbs', 'WCBSTV.us@SD', 'WCBS'),
      '4.10': mapped('nbclx', '', 'NBC LX')
    }
  })

  const run = promisify(execFile)
  try {
    const result = await run('npx', ['tsx', 'src/commands/run/all.ts'], {
      env: {
        PATH: process.env.PATH,
        HOME: process.env.HOME,
        STORAGE_DIR: storageDir,
        OVERLAY_DIR: overlayDir,
        EPG_REPO,
        EPG_REF,
        GRAB_DAYS: '1'
      },
      maxBuffer: 64 * 1024 * 1024
    })
    output = { code: 0, ...result }
  } catch (error) {
    const failed = error as { code: number; stdout: string; stderr: string }
    output = { code: failed.code, stdout: failed.stdout, stderr: failed.stderr }
  }
}, 30 * 60_000)

afterAll(async () => {
  server?.close()
  if (rootDir) await fs.rm(rootDir, { recursive: true, force: true })
})

describe('run:all against iptv-org/epg', () => {
  it('exits successfully', () => {
    expect(output.code, `${output.stdout}\n${output.stderr}`).toBe(0)
  })

  it('publishes a guide with lcn, display names and programmes [FR-X-3, FR-R-2]', async () => {
    const xml = await fs.readFile(path.join(rootDir, 'data/guides/ota.xml'), 'utf8')

    expect(xml).toMatch(
      /<channel id="WCBSTV\.us@SD"><display-name>WCBS-HD<\/display-name>.*?<lcn>2\.1<\/lcn>/s
    )
    // An empty xmltv_id falls back to site_id
    expect(xml).toMatch(/<channel id="nbclx">.*?<lcn>4\.10<\/lcn>/s)
    expect(xml).toContain('wcbs show 0')
    expect(xml.match(/<programme /g)).toHaveLength(4)
    expect(
      gunzipSync(await fs.readFile(path.join(rootDir, 'data/guides/ota.xml.gz'))).toString()
    ).toBe(xml)
  })

  it('records the run [FR-R-6]', async () => {
    const [run] = await new RunHistory(new Storage(path.join(rootDir, 'data'))).list('ota')

    expect(run).toMatchObject({ result: 'success', channels: 2, programs: 4 })
  })
})
