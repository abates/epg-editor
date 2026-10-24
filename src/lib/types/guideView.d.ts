// A programme block as rendered by the grid; times are ISO 8601 (parsed from the XMLTV
// start/stop, which carry an explicit UTC offset) so the browser renders them in local time
export interface GuideViewProgramData {
  start: string
  stop: string
  title: string
  desc: string | null
  category: string | null
}

export interface GuideViewChannelData {
  key: string
  name: string
  number: string | null
  logo: string | null
  programs: GuideViewProgramData[] // sorted by start
}

export interface GuideViewRangeData {
  start: string
  stop: string
}

export interface GuideViewData {
  channels: GuideViewChannelData[]
  range: GuideViewRangeData | null // null when no programme has any data yet
  generatedAt: string // the guide file's mtime, ISO 8601
}
