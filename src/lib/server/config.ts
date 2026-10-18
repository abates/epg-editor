import path from 'node:path'

// Read from process.env rather than $env so the tsx commands (outside SvelteKit) can use it too
export interface Config {
  storageDir: string
  overlayDir: string
  epg: {
    repo: string
    branch: string
    ref: string | null
  }
  cronSchedule: string
  runAtStartup: boolean
  grab: {
    days: number | null
    maxConnections: number
    delay: number
    timeout: number
    gzip: boolean
  }
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const storageDir = path.resolve(string(env, 'STORAGE_DIR') ?? '/data')

  return {
    storageDir,
    overlayDir: path.resolve(string(env, 'OVERLAY_DIR') ?? path.join(storageDir, 'sites')),
    epg: {
      repo: string(env, 'EPG_REPO') ?? 'https://github.com/iptv-org/epg.git',
      branch: string(env, 'EPG_BRANCH') ?? 'master',
      ref: string(env, 'EPG_REF')
    },
    cronSchedule: string(env, 'CRON_SCHEDULE') ?? '0 0 * * *',
    runAtStartup: boolean(env, 'RUN_AT_STARTUP') ?? true,
    grab: {
      days: integer(env, 'GRAB_DAYS'),
      maxConnections: integer(env, 'GRAB_MAX_CONNECTIONS') ?? 1,
      delay: integer(env, 'GRAB_DELAY') ?? 0,
      timeout: integer(env, 'GRAB_TIMEOUT') ?? 30000,
      gzip: boolean(env, 'GRAB_GZIP') ?? true
    }
  }
}

export const config = loadConfig()

function string(env: NodeJS.ProcessEnv, name: string): string | null {
  const value = env[name]?.trim()

  return value ? value : null
}

function integer(env: NodeJS.ProcessEnv, name: string): number | null {
  const value = string(env, name)
  if (value === null) return null
  if (!/^\d+$/.test(value))
    throw new Error(`${name} must be a non-negative integer, got "${value}"`)

  return Number(value)
}

function boolean(env: NodeJS.ProcessEnv, name: string): boolean | null {
  const value = string(env, name)?.toLowerCase()
  if (value === undefined) return null
  if (['true', '1', 'yes'].includes(value)) return true
  if (['false', '0', 'no'].includes(value)) return false

  throw new Error(`${name} must be true or false, got "${value}"`)
}
