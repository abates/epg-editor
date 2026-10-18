export type GuideOrigin = 'upstream' | 'overlay' | 'manual'

export interface MappingGuideData {
  site: string
  site_id: string
  lang: string | null
  xmltv_id: string
  name: string
  origin: GuideOrigin
}

export interface MappingData {
  status: 'mapped' | 'skipped'
  guide?: MappingGuideData
  stale?: boolean
  updatedAt: string
}

export interface MappingsData {
  version: 1
  items: Record<string, MappingData>
}
