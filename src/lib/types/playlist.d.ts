export interface PlaylistItemData {
  key: string
  number: string | null
  name: string
  url: string
  logo: string | null
  group: string | null
  attributes: Record<string, string>
}

export interface PlaylistParseResult {
  items: PlaylistItemData[]
  warnings: string[]
}
