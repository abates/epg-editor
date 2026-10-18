export interface LineupSourceData {
  type: 'upload' | 'url'
  url?: string
  importedAt: string
}

export interface LineupFiltersData {
  countries: string[]
  languages: string[]
  preferredSites: string[]
}

export interface LineupGrabData {
  enabled: boolean
  days?: number
  maxConnections?: number
  delay?: number
  timeout?: number
  gzip?: boolean
}

export interface LineupData {
  slug: string
  name: string
  source: LineupSourceData
  filters: LineupFiltersData
  grab: LineupGrabData
  createdAt: string
  updatedAt: string
}
