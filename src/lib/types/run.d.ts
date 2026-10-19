export type RunResult = 'success' | 'failed' | 'skipped'

// One grab of one lineup, kept in status/runs/<slug>.json [FR-R-6]
export interface RunData {
  startedAt: string
  finishedAt: string
  duration: number
  result: RunResult
  channels: number | null
  programs: number | null
  error: string | null
  // File name under /data/logs, null when nothing was logged
  log: string | null
}

// status/runs/<slug>.json, newest run first
export interface RunHistoryData {
  version: 1
  runs: RunData[]
}

// status/current.json, written by the command that holds the run lock
export interface CurrentRunData {
  step: 'sync' | 'grab'
  lineup: string | null
  startedAt: string
  pid: number
}

export type JobKind = 'sync' | 'grab'

// GET /api/jobs
export interface JobStatusData {
  running: boolean
  current: CurrentRunData | null
}
