// Shared TypeScript types for epg-editor's domain objects, mirroring the
// backend's Pydantic models (`backend/app/models/lineup.py`) and
// `docs/data-model.md` exactly (see CLAUDE.md's "Frontend module layout").
// Other TypeScript modules should import these rather than redefining the
// shapes ad hoc.

/** How an epg-editor lineup's channel list was populated. */
export type LineupSource = 'manual' | 'm3u';

/**
 * A single candidate SD station suggested for a channel.
 *
 * Populated by the (not-yet-built, Phase 3) suggestion-scoring service;
 * `suggestions` arrays are empty until that lands.
 */
export interface MappingSuggestion {
  sdStationId: string;
  sdLineupId: string;
  score: number;
}

/**
 * A channel's association with a SchedulesDirect station.
 *
 * `sdStationId`/`sdLineupId` are `null` until a suggestion is accepted or
 * the user sets a mapping directly via the manual-confirm endpoint.
 * `confirmed: false` with `suggestions` populated is the "needs review"
 * state the (future) bulk-accept flow operates on.
 */
export interface ChannelMapping {
  sdStationId: string | null;
  sdLineupId: string | null;
  confirmed: boolean;
  confirmedAt: string | null;
  suggestions: MappingSuggestion[];
}

/** A single channel within an epg-editor lineup. */
export interface Channel {
  id: string;
  number: string | null;
  name: string;
  logoUrl: string | null;
  tvgId: string | null;
  sourceStreamUrl: string | null;
  /**
   * Set when an `m3u`-sourced lineup is re-imported and this channel no
   * longer appears in the new file. `null` normally, and cleared back to
   * `null` if a later re-import sees the channel again.
   */
  missingSince: string | null;
  mapping: ChannelMapping | null;
}

/** An epg-editor lineup: a named list of channels plus SD associations. */
export interface Lineup {
  id: string;
  name: string;
  source: LineupSource;
  createdAt: string;
  updatedAt: string;
  sdLineupIds: string[];
  channels: Channel[];
}

/** A single station-scoped failure within an otherwise-successful sync. */
export interface StationSyncError {
  sdStationId: string;
  message: string;
}

/**
 * Result of `POST /api/lineups/{lineupId}/sync-and-generate`: fetching
 * fresh SD schedule/program data for every confirmed-mapped channel in a
 * lineup, caching it, and regenerating the lineup's XMLTV output file.
 *
 * A 200 response doesn't guarantee every station succeeded -
 * `stationErrors`/`errors` can be non-empty alongside non-zero success
 * counts (partial failure), so callers should surface both rather than
 * treating a 200 as unconditional success.
 */
export interface SyncResult {
  lineupId: string;
  stationsSynced: number;
  scheduleDaysFetched: number;
  programsFetched: number;
  channelsGenerated: number;
  stationErrors: StationSyncError[];
  errors: string[];
}
