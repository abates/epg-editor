import type { JobKind, JobStatusData } from '$lib/types/run'
import { readCurrentRun } from './runHistory'
import { isRunLocked } from './lock'
import { Storage } from './storage'
import { spawn } from 'node:child_process'

const START_TIMEOUT = 15_000
const POLL_INTERVAL = 250

export type StartJobResult = { ok: true } | { ok: false; status: 409 | 500; message: string }

export interface JobsOptions {
  storageDir: string
  // The app dir with package.json; the commands are npm scripts
  cwd?: string
  npm?: string
}

// "Sync now" / "Grab now" [FR-R-3]. Commands run as detached processes, never inside the web
// process, and take the run lock themselves, so they exclude the scheduler and each other
export class Jobs {
  private readonly storage: Storage
  private readonly cwd: string
  private readonly npm: string

  constructor(options: JobsOptions) {
    this.storage = new Storage(options.storageDir)
    this.cwd = options.cwd ?? process.cwd()
    this.npm = options.npm ?? 'npm'
  }

  async status(): Promise<JobStatusData> {
    const running = await isRunLocked(this.storage.rootDir)

    return { running, current: running ? await readCurrentRun(this.storage) : null }
  }

  // Resolves once the command holds the run lock (or has already finished), so the UI can
  // poll status() right away. A command that exits without the lock lost a race for it
  async start(kind: JobKind, lineup?: string): Promise<StartJobResult> {
    if (await isRunLocked(this.storage.rootDir))
      return { ok: false, status: 409, message: 'A sync or grab is already running' }

    const args =
      kind === 'sync'
        ? ['run', 'run:sync']
        : ['run', 'run:all', ...(lineup ? ['--', `--lineup=${lineup}`] : [])]
    // Our own command, so it gets this process's env (STORAGE_DIR etc.); it sanitises the env
    // of the epg processes it starts. stdio is ignored: each run writes its own log file
    const child = spawn(this.npm, args, {
      cwd: this.cwd,
      env: process.env,
      detached: true,
      stdio: 'ignore'
    })

    const exit = new Promise<number | null>(resolve => {
      child.once('exit', code => resolve(code))
      child.once('error', () => resolve(null))
    })
    child.unref()

    const deadline = Date.now() + START_TIMEOUT
    while (Date.now() < deadline) {
      const code = await Promise.race([exit, delay(POLL_INTERVAL).then(() => undefined)])
      if (code === 0) return { ok: true }
      if (code !== undefined) {
        if (await isRunLocked(this.storage.rootDir))
          return { ok: false, status: 409, message: 'A sync or grab is already running' }
        const reason = code === null ? 'could not be started' : `exited with code ${code}`
        return { ok: false, status: 500, message: `The ${kind} command ${reason}` }
      }
      if (await isRunLocked(this.storage.rootDir)) return { ok: true }
    }

    // Still starting (slow machine); the UI polls status() anyway
    return { ok: true }
  }
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}
