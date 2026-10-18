export interface GuideEntryData {
  site: string
  site_id: string
  lang: string | null
  xmltv_id: string
  name: string
  logo: string | null
  country: string | null
  origin: 'upstream' | 'overlay'
}
