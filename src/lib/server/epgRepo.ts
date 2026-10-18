import { runCommand, sanitizedEnv } from './spawn'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'

export interface EpgRepoOptions {
  dir: string
  repo: string
  branch: string
  ref: string | null
  onLine?: (line: string) => void
  // Overridable so tests can use a stub instead of a real npm install
  npm?: string
}

export interface CheckoutResult {
  previous: string | null
  current: string
}

// The iptv-org/epg checkout under STORAGE_DIR [FR-G-1..3, FR-G-6]
export class EpgRepo {
  readonly dir: string
  readonly repo: string
  readonly target: string
  readonly npm: string
  readonly onLine?: (line: string) => void

  constructor(options: EpgRepoOptions) {
    this.dir = path.resolve(options.dir)
    this.repo = options.repo
    this.target = options.ref ?? options.branch
    this.npm = options.npm ?? 'npm'
    this.onLine = options.onLine
  }

  get sitesDir(): string {
    return path.join(this.dir, 'sites')
  }

  get dataDir(): string {
    return path.join(this.dir, 'temp', 'data')
  }

  async exists(): Promise<boolean> {
    return isDir(path.join(this.dir, '.git'))
  }

  async head(): Promise<string | null> {
    if (!(await this.exists())) return null

    return (await this.git(this.dir, ['rev-parse', 'HEAD'])).trim()
  }

  // Clones on first use, otherwise moves the checkout to the latest commit of the branch
  // (or EPG_REF). A failed fetch leaves the previous checkout untouched [FR-G-5]
  async checkout(): Promise<CheckoutResult> {
    if (!(await this.exists())) {
      await this.clone()
      return { previous: null, current: (await this.head()) as string }
    }

    const previous = await this.head()
    await this.git(this.dir, ['remote', 'set-url', 'origin', this.repo])
    await this.fetch(this.dir)

    return { previous, current: (await this.head()) as string }
  }

  async reset(commit: string): Promise<void> {
    await this.git(this.dir, ['reset', '--hard', commit])
    await this.git(this.dir, ['clean', '-fd', '--', 'sites'])
  }

  async lockfileHash(): Promise<string> {
    const content = await fs.readFile(path.join(this.dir, 'package-lock.json'))

    return crypto.createHash('sha256').update(content).digest('hex')
  }

  // npm ci only when package-lock.json changed. --ignore-scripts skips epg's postinstall
  // (api:load) and prepare (husky); api:load runs on its own in loadApi() [FR-G-3]
  async install(previousHash: string | null): Promise<{ hash: string; installed: boolean }> {
    const hash = await this.lockfileHash()
    if (hash === previousHash && (await isDir(path.join(this.dir, 'node_modules')))) {
      return { hash, installed: false }
    }

    await this.runNpm(['ci', '--ignore-scripts'])

    return { hash, installed: true }
  }

  // Downloads the iptv-org database into temp/data, which grab and database.ts read
  async loadApi(): Promise<void> {
    await this.runNpm(['run', 'api:load'])
  }

  async hasApiData(): Promise<boolean> {
    return isDir(this.dataDir)
  }

  // Shallow clone into a temp dir next to the target, then rename, so a failed clone leaves
  // nothing behind. init + fetch instead of `git clone -b` so EPG_REF can also be a commit
  private async clone() {
    const tmpDir = `${this.dir}.tmp-${crypto.randomUUID()}`
    await fs.mkdir(path.dirname(this.dir), { recursive: true })
    try {
      await this.git(path.dirname(this.dir), ['init', '--quiet', tmpDir])
      await this.git(tmpDir, ['remote', 'add', 'origin', this.repo])
      await this.fetch(tmpDir)
      await fs.rename(tmpDir, this.dir)
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true })
    }
  }

  private async fetch(cwd: string) {
    await this.git(cwd, ['fetch', '--depth', '1', 'origin', this.target])
    await this.git(cwd, ['reset', '--hard', 'FETCH_HEAD'])
    // Only sites/: node_modules and temp/ are ignored files and must survive
    await this.git(cwd, ['clean', '-fd', '--', 'sites'])
  }

  private async git(cwd: string, args: string[]): Promise<string> {
    return runCommand('git', args, {
      cwd,
      env: sanitizedEnv({ GIT_TERMINAL_PROMPT: '0' }),
      onLine: this.onLine
    })
  }

  private async runNpm(args: string[]): Promise<string> {
    return runCommand(this.npm, args, {
      cwd: this.dir,
      env: sanitizedEnv({
        npm_config_audit: 'false',
        npm_config_fund: 'false',
        npm_config_update_notifier: 'false'
      }),
      onLine: this.onLine
    })
  }
}

async function isDir(filepath: string): Promise<boolean> {
  try {
    return (await fs.stat(filepath)).isDirectory()
  } catch {
    return false
  }
}
