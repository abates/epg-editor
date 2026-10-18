import type { MappingData } from './mapping'

export type ChannelStatus = 'mapped' | 'skipped' | 'unmapped'

// One row of the lineup editor [FR-P-1]
export interface ChannelRowData {
  key: string
  number: string | null
  name: string
  logo: string | null
  status: ChannelStatus
  mapping: MappingData | null
}

export interface ChannelCountsData {
  total: number
  mapped: number
  skipped: number
  unmapped: number
  stale: number
}

// What the editor shows: "suggested" is an unmapped row with a loaded top suggestion
export type BadgeStatus = ChannelStatus | 'suggested' | 'stale'
