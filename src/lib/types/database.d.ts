export interface DatabaseFeedData {
  xmltv_id: string
  name: string
  is_main: boolean
}

// A channel from the iptv-org database, for xmltv_id search-as-you-type [FR-E-1]
export interface DatabaseChannelData {
  xmltv_id: string
  name: string
  alt_names: string[]
  country: string
  closed: string | null
  feeds: DatabaseFeedData[]
}
