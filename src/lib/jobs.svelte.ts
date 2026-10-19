import type { CurrentRunData, JobKind, JobStatusData } from '$lib/types/run'
import { ApiError, getJobStatus, startJob } from '$lib/api'
import { toast } from '@zerodevx/svelte-toast'
import { invalidateAll } from '$app/navigation'

const POLL_INTERVAL = 3000

// Shared state of the running sync/grab. Polls /api/jobs while a run is in progress and
// reloads the page data when it ends [FR-R-3]
class JobManager {
  running = $state(false)
  current: CurrentRunData | null = $state(null)
  starting = $state(false)
  private timer: ReturnType<typeof setTimeout> | null = null

  // Called with the status from the layout load on every navigation
  set(status: JobStatusData) {
    this.apply(status)
    if (this.running) this.poll()
  }

  async start(kind: JobKind, lineup?: string) {
    this.starting = true
    try {
      this.apply(await startJob(kind, lineup))
      toast.push(kind === 'sync' ? 'Sync started' : 'Grab started')
      this.poll()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) this.running = true
      toast.push((error as Error).message)
    } finally {
      this.starting = false
    }
  }

  private apply(status: JobStatusData) {
    this.running = status.running
    this.current = status.current
  }

  private poll() {
    if (this.timer) return
    this.timer = setTimeout(async () => {
      this.timer = null
      const status = await getJobStatus().catch(() => null)
      if (!status) return this.poll()

      const wasRunning = this.running
      this.apply(status)
      if (status.running) return this.poll()
      if (wasRunning) {
        toast.push('Run finished')
        await invalidateAll()
      }
    }, POLL_INTERVAL)
  }
}

export const jobs = new JobManager()
