import { execFileSync } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'

export const FIXTURE_SITES_DIR = path.resolve('tests/__data__/input/sites')
export const FIXTURE_OVERLAY_DIR = path.resolve('tests/__data__/input/overlay')

export function git(cwd: string, args: string[]): string {
  return execFileSync(
    'git',
    ['-c', 'user.name=test', '-c', 'user.email=test@example.com', ...args],
    { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }
  ).trim()
}

// A local stand-in for iptv-org/epg with the fixture sites. Returns a file:// URL, since
// shallow fetches are ignored for plain local paths
export async function createRemote(dir: string): Promise<string> {
  await fs.mkdir(dir, { recursive: true })
  git(dir, ['init', '--quiet', '--initial-branch', 'master'])
  await fs.cp(FIXTURE_SITES_DIR, path.join(dir, 'sites'), { recursive: true })
  await fs.writeFile(path.join(dir, 'package-lock.json'), '{"lockfileVersion":3}\n')
  await fs.writeFile(path.join(dir, '.gitignore'), '/node_modules/\n/temp/\n')
  git(dir, ['add', '.'])
  git(dir, ['commit', '--quiet', '-m', 'initial'])

  return `file://${dir}`
}

export async function commit(
  dir: string,
  files: Record<string, string | null>,
  message = 'update'
): Promise<string> {
  for (const [file, content] of Object.entries(files)) {
    const filepath = path.join(dir, file)
    if (content === null) {
      await fs.rm(filepath, { recursive: true, force: true })
    } else {
      await fs.mkdir(path.dirname(filepath), { recursive: true })
      await fs.writeFile(filepath, content)
    }
  }
  git(dir, ['add', '--all'])
  git(dir, ['commit', '--quiet', '-m', message])

  return git(dir, ['rev-parse', 'HEAD'])
}

// Stand-in for npm: logs its arguments to npm-calls.log in the checkout, creates node_modules
// for `ci` and temp/data for `run api:load`, and fails when the checkout has an npm-fail file
export async function createStubNpm(dir: string): Promise<string> {
  const filepath = path.join(dir, 'npm')
  await fs.mkdir(dir, { recursive: true })
  await fs.writeFile(
    filepath,
    [
      '#!/bin/sh',
      'echo "$*" >> npm-calls.log',
      'if [ -e npm-fail ]; then echo "stub npm failed" >&2; exit 1; fi',
      'if [ "$1" = "ci" ]; then mkdir -p node_modules; fi',
      'if [ "$1 $2" = "run api:load" ]; then mkdir -p temp/data; fi',
      ''
    ].join('\n'),
    { mode: 0o755 }
  )

  return filepath
}

export async function npmCalls(checkoutDir: string): Promise<string[]> {
  try {
    const log = await fs.readFile(path.join(checkoutDir, 'npm-calls.log'), 'utf8')
    return log.trim().split('\n')
  } catch {
    return []
  }
}
