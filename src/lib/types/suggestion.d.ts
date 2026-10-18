import type { GuideEntryData } from './guide'

export type MatchReasonKind =
  | 'callSign'
  | 'inheritedCallSign'
  | 'subChannel'
  | 'subChannelMismatch'
  | 'name'
  | 'country'
  | 'countryMismatch'
  | 'preferredSite'
  | 'noXmltvId'

// One line of "why it matched" in the suggestions list [FR-P-4]
export interface MatchReasonData {
  kind: MatchReasonKind
  points: number
  detail: string
}

export interface SuggestionData {
  entry: GuideEntryData
  score: number
  reasons: MatchReasonData[]
}
