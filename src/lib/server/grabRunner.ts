import type { LineupGrabData } from '$lib/types/lineup'
import type { RunData } from '$lib/types/run'
import { RunHistory, LOGS_DIR } from './runHistory'
import { RunLog, type RunLogger } from './runLog'
import { runCommand, sanitizedEnv } from './spawn'
import { LineupStore } from './lineupStore'
import type { Config } from './config'
import { Storage } from './storage'
import { EPGGrabber } from 'epg-grabber'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'

export const GUIDES_DIR = 'guides'

export interface GrabPaths {
  channels: string
  output: string
}

export interface GrabOptions {
  config: Config
  logger?: RunLogger
  // Overridable so tests can use a stub instead of epg's real grab
  npm?: string
}

export interface GuideCounts {
  channels: number
  programs: number
}

// FR-R-2: `npm run grab --- --channels=… --output=…` plus the lineup's overrides, falling back
// to the GRAB_* defaults. Unset days leaves each site config's own default
export function buildGrabArgs(
  grab: LineupGrabData,
  defaults: Config['grab'],
  paths: GrabPaths
): string[] {
  const days = grab.days ?? defaults.days
  const args = [
    'run',
    'grab',
    '---',
    `--channels=${paths.channels}`,
    `--output=${paths.output}`,
    `--maxConnections=${grab.maxConnections ?? defaults.maxConnections}`,
    `--delay=${grab.delay ?? defaults.delay}`,
    `--timeout=${grab.timeout ?? defaults.timeout}`
  ]
  if (days !== null) args.push(`--days=${days}`)
  if (grab.gzip ?? defaults.gzip) args.push('--gzip')

  return args
}

// Counts <channel> and <programme> elements of an XMLTV guide
export function countGuide(xml: string): GuideCounts {
  return {
    channels: xml.match(/<channel\s/g)?.length ?? 0,
    programs: xml.match(/<programme\s/g)?.length ?? 0
  }
}

// Grabs one lineup into a temp dir and moves the result into /data/guides. A failed or empty
// grab leaves the last good guide in place [FR-R-2]. Every attempt is recorded [FR-R-6].
// The caller holds the run lock
export async function runGrab(
  slug: string,
  { config, logger, npm }: GrabOptions
): Promise<RunData> {
  const storage = new Storage(config.storageDir)
  const store = new LineupStore(storage)
  const history = new RunHistory(storage)
  const startedAt = new Date()

  const lineup = await store.get(slug)
  if (!lineup) throw new Error(`lineup "${slug}" not found`)

  const channelsXml = await store.writeChannelsXml(slug)
  const mapped = EPGGrabber.parseChannelsXML(channelsXml).length
  if (!mapped) {
    logger?.info(`${slug}: no mapped channels, skipped`)
    const run = finish(startedAt, 'skipped', { error: 'no mapped channels', log: null })
    await history.add(slug, run)
    return run
  }

  const log = await RunLog.open(storage.path(LOGS_DIR), `grab-${slug}`, startedAt, logger)
  const tmpDir = storage.path(GUIDES_DIR, `.tmp-${slug}-${crypto.randomUUID()}`)
  const gzip = lineup.grab.gzip ?? config.grab.gzip
  let run: RunData

  try {
    if (!(await isDir(path.join(config.epgDir, 'node_modules'))))
      throw new Error(`${config.epgDir} has no installed epg checkout, run a sync first`)

    await fs.mkdir(tmpDir, { recursive: true })
    const output = path.join(tmpDir, `${slug}.xml`)
    const args = buildGrabArgs(lineup.grab, config.grab, {
      channels: store.channelsXmlPath(slug),
      output
    })

    log.info(`${slug}: grabbing ${mapped} channel(s)...`)
    try {
      await runCommand(npm ?? 'npm', args, {
        cwd: config.epgDir,
        // FR-O-2: overlay site configs are symlinks and must resolve epg's node_modules
        env: sanitizedEnv({ NODE_PRESERVE_SYMLINKS: '1' }),
        onLine: line => log.line(line)
      })
    } catch (error) {
      throw new Error(`grab failed: ${message(error)}`, { cause: error })
    }

    const counts = countGuide(await fs.readFile(output, 'utf8').catch(() => ''))
    if (!counts.channels) throw new Error('grab wrote no guide, keeping the previous one')
    if (!counts.programs) throw new Error('grab found no programmes, keeping the previous one')

    await publish(storage, slug, tmpDir, gzip)
    log.info(`${slug}: saved ${counts.channels} channel(s) and ${counts.programs} programme(s)`)
    run = finish(startedAt, 'success', { ...counts, log: log.name })
  } catch (error) {
    log.error(message(error))
    run = finish(startedAt, 'failed', { error: message(error), log: log.name })
  } finally {
    await fs.rm(tmpDir, { recursive: true, force: true })
  }

  await log.close()
  await history.add(slug, run)

  return run
}

// Renames within /data/guides, so readers see either the old or the new file. The .gz goes
// first so a client never gets a new .xml next to an older .xml.gz for long
async function publish(storage: Storage, slug: string, tmpDir: string, gzip: boolean) {
  const xml = storage.path(GUIDES_DIR, `${slug}.xml`)
  const gz = `${xml}.gz`
  const tmpGz = path.join(tmpDir, `${slug}.xml.gz`)

  if (gzip && (await isFile(tmpGz))) await fs.rename(tmpGz, gz)
  else await fs.rm(gz, { force: true })
  await fs.rename(path.join(tmpDir, `${slug}.xml`), xml)
}

function finish(
  startedAt: Date,
  result: RunData['result'],
  fields: Partial<Pick<RunData, 'channels' | 'programs' | 'error' | 'log'>>
): RunData {
  const finishedAt = new Date()

  return {
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    duration: finishedAt.getTime() - startedAt.getTime(),
    result,
    channels: fields.channels ?? null,
    programs: fields.programs ?? null,
    error: fields.error ?? null,
    log: fields.log ?? null
  }
}

async function isDir(filepath: string): Promise<boolean> {
  return fs.stat(filepath).then(
    stat => stat.isDirectory(),
    () => false
  )
}

async function isFile(filepath: string): Promise<boolean> {
  return fs.stat(filepath).then(
    stat => stat.isFile(),
    () => false
  )
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
