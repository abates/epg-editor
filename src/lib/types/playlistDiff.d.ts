export interface PlaylistDiffChannelData {
  key: string
  number: string | null
  name: string
}

export interface PlaylistDiffRenameData {
  key: string
  number: string | null
  from: string
  to: string
}

// Re-import preview [FR-M-6]
export interface PlaylistDiffData {
  added: PlaylistDiffChannelData[]
  removed: PlaylistDiffChannelData[]
  renamed: PlaylistDiffRenameData[]
  unchanged: number
}
