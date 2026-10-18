import lockfile from 'proper-lockfile'
import fs from 'node:fs/promises'
import path from 'node:path'

const LOCK_FILE = 'run.lock'
// The holder refreshes the lock's mtime every STALE_MS / 2. A lock that has not been refreshed
// for STALE_MS belongs to a process that died, and the next run takes it over
const STALE_MS = 60_000

export class RunLockedError extends Error {
  constructor() {
    super('another sync or grab is already running')
    this.name = 'RunLockedError'
  }
}

// FR-R-3: only one sync/grab at a time across the scheduler, startup run and "Grab now"
export async function acquireRunLock(storageDir: string): Promise<() => Promise<void>> {
  await fs.mkdir(storageDir, { recursive: true })

  try {
    return await lockfile.lock(storageDir, { ...lockOptions(storageDir), retries: 0 })
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ELOCKED') throw new RunLockedError()
    throw error
  }
}

export async function withRunLock<T>(storageDir: string, fn: () => Promise<T>): Promise<T> {
  const release = await acquireRunLock(storageDir)
  try {
    return await fn()
  } finally {
    await release()
  }
}

// Read-only check for the web process; a stale lock counts as unlocked
export async function isRunLocked(storageDir: string): Promise<boolean> {
  return lockfile.check(storageDir, lockOptions(storageDir))
}

function lockOptions(storageDir: string) {
  return {
    lockfilePath: path.join(storageDir, LOCK_FILE),
    stale: STALE_MS,
    realpath: false
  }
}
