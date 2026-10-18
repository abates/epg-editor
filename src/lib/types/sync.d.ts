export interface OverlaySiteData {
  name: string
  // true when an upstream site of the same name was moved aside [FR-O-3]
  conflict: boolean
}

export interface OverlayErrorData {
  name: string
  message: string
}

export interface OverlayReportData {
  sites: OverlaySiteData[]
  errors: OverlayErrorData[]
}

export interface GuideIndexStatsData {
  sites: number
  entries: number
  errors: { file: string; message: string }[]
}

export interface DatabaseStatsData {
  channels: number
  feeds: number
}

// status/sync.json. The web process reloads its guide index when this file changes
export interface SyncStatusData {
  result: 'success' | 'failed'
  startedAt: string
  finishedAt: string
  duration: number
  repo: string
  ref: string
  commit: string | null
  lockfileHash: string | null
  error: string | null
  warnings: string[]
  overlay: OverlayReportData
  index: GuideIndexStatsData | null
  database: DatabaseStatsData | null
  log: string
  logTail: string[]
}
