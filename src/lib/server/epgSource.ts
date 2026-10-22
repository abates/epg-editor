import type { Config } from './config'
import { runCommand, sanitizedEnv } from './spawn'
import { Storage } from './storage'

export const EPG_SOURCE_OVERRIDE_FILE = 'status/epg-source-override.json'

// A user-saved repo/branch override that replaces EPG_REPO/EPG_BRANCH/EPG_REF until reset, so a
// fork or PR branch can be tested from /status without restarting the container [FR-G-7]
export interface EpgSourceOverrideData {
  repo: string
  ref: string
}

export type EpgSourceFieldErrors = Partial<Record<'repo' | 'ref', string>>

export async function readEpgSourceOverride(
  storage: Storage
): Promise<EpgSourceOverrideData | null> {
  if (!(await storage.exists(EPG_SOURCE_OVERRIDE_FILE))) return null

  return storage.json<EpgSourceOverrideData>(EPG_SOURCE_OVERRIDE_FILE).catch(() => null)
}

export async function saveEpgSourceOverride(
  storage: Storage,
  override: EpgSourceOverrideData
): Promise<void> {
  await storage.saveJson(EPG_SOURCE_OVERRIDE_FILE, override)
}

export async function clearEpgSourceOverride(storage: Storage): Promise<void> {
  await storage.remove(EPG_SOURCE_OVERRIDE_FILE)
}

// The epg.* config to check out: the saved override if any, else the env-configured default.
// Used by runSync so every entry point (startup, scheduler, "Sync now", "Save & sync") resolves
// the same way
export async function resolveEpgConfig(
  storage: Storage,
  epg: Config['epg']
): Promise<Config['epg']> {
  const override = await readEpgSourceOverride(storage)

  return override ? { repo: override.repo, branch: override.ref, ref: null } : epg
}

const DEFAULT_ALLOWED_PROTOCOLS = ['http:', 'https:']
// A full or short commit SHA can't be confirmed by ls-remote (it isn't in the refs
// advertisement unless it's also a branch/tag tip), so it's let through unchecked, same as
// EPG_REF today
const COMMIT_SHA = /^[0-9a-f]{7,40}$/i

export interface ValidateEpgSourceOptions {
  // Overridable so tests can validate against a local file:// remote instead of a real one
  allowedProtocols?: string[]
}

// Confirms the repo is reachable and the branch/tag exists via `git ls-remote` before anything
// is saved or synced. Errors are attributed to the field they belong to
export async function validateEpgSource(
  repo: string,
  ref: string,
  options: ValidateEpgSourceOptions = {}
): Promise<EpgSourceFieldErrors> {
  const allowed = options.allowedProtocols ?? DEFAULT_ALLOWED_PROTOCOLS

  let parsed: URL
  try {
    parsed = new URL(repo)
  } catch {
    return { repo: `"${repo}" is not a valid URL` }
  }
  if (!allowed.includes(parsed.protocol)) {
    const schemes = allowed.map(protocol => protocol.replace(':', '')).join('/')
    return { repo: `Only ${schemes} URLs are supported` }
  }

  let output: string
  try {
    output = await runCommand('git', ['ls-remote', repo], {
      cwd: process.cwd(),
      env: sanitizedEnv({ GIT_TERMINAL_PROMPT: '0' })
    })
  } catch (cause) {
    return { repo: `Could not reach "${repo}": ${(cause as Error).message}` }
  }

  const refs = output
    .split('\n')
    .map(line => line.split('\t')[1])
    .filter((name): name is string => Boolean(name))
  const found = refs.some(name => name === `refs/heads/${ref}` || name === `refs/tags/${ref}`)
  if (!found && !COMMIT_SHA.test(ref)) return { ref: `"${ref}" was not found in ${repo}` }

  return {}
}
