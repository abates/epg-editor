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
  /**
   * From an M3U entry's `group-title` attribute (e.g. "Local", "Sports").
   * `null` for manually-added channels and for M3U entries that didn't
   * specify one.
   */
  group: string | null;
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

/**
 * Outcome of merging parsed M3U entries into an epg-editor lineup, returned
 * by both `POST /api/lineups/import-m3u` (brand-new lineup) and
 * `POST /api/lineups/{lineupId}/import-m3u` (re-import into an existing
 * `m3u`-sourced lineup). Entries are full `Channel` objects, not diffs.
 *
 * - `added`: brand-new channels created from unmatched incoming entries.
 * - `updated`: existing channels whose metadata was refreshed in place
 *   (their `mapping` is always preserved untouched).
 * - `flaggedMissing`: channels no longer present in the uploaded file -
 *   never deleted automatically, just flagged via `Channel.missingSince`.
 *   Includes channels flagged by a *previous* re-import that are still
 *   missing now, not just newly-flagged ones.
 * - `unidentifiedEntryCount`: how many parsed entries in this file had
 *   neither a `tvg-id` nor a channel number - entries with no stable
 *   identity signal to match against existing channels on a future
 *   re-import. This is a known, accepted limitation (not a bug): such an
 *   entry is always treated as brand-new on every import/re-import, which
 *   can grow the lineup by a duplicate channel per re-import and flag a
 *   previously-matched channel as missing as a side effect. Present on
 *   every import result (descriptive of "what's in this file"), with `0`
 *   being the normal value when every entry carries an identifier.
 */
export interface M3UImportResult {
  added: Channel[];
  updated: Channel[];
  flaggedMissing: Channel[];
  unidentifiedEntryCount: number;
}

/** Response body for both M3U import endpoints. */
export interface M3UImportResponse {
  lineup: Lineup;
  result: M3UImportResult;
}

/**
 * How many candidate suggestions were (re)computed for one channel by a
 * `POST /api/lineups/{lineupId}/suggestions` run. Capped at the backend's
 * `MAX_SUGGESTIONS_PER_CHANNEL` (5) even when the candidate station pool is
 * larger - see `docs/data-model.md`'s `suggestions` notes.
 */
export interface ChannelSuggestionCount {
  channelId: string;
  suggestionCount: number;
}

/**
 * Response body for `POST /api/lineups/{lineupId}/suggestions`.
 *
 * Deliberately does NOT include the actual suggestions - those are written
 * onto each channel's own `mapping.suggestions` field (recomputed, not
 * accumulated), so callers must re-fetch the lineup (`getLineup`) after a
 * successful call to see them reflected.
 */
export interface SuggestionResult {
  lineupId: string;
  /** Size of the deduped candidate station pool across the lineup's `sdLineupIds`. */
  stationPoolSize: number;
  /** Number of channels in the lineup that suggestions were (re)computed for. */
  channelsScored: number;
  channelSuggestionCounts: ChannelSuggestionCount[];
}

/** One channel that `POST /api/lineups/{lineupId}/bulk-accept-suggestions` auto-confirmed. */
export interface ConfirmedSuggestion {
  channelId: string;
  sdStationId: string;
  sdLineupId: string;
  score: number;
}

/**
 * Response body for `POST /api/lineups/{lineupId}/bulk-accept-suggestions`.
 *
 * `threshold` is the fixed backend constant actually applied (currently
 * `0.92`) - surfaced here so the frontend can display it without hardcoding
 * its own copy of the value; it is NOT a user-adjustable setting (see
 * CLAUDE.md's Core workflow #4 - no UI control for this).
 *
 * Like `SuggestionResult`, this does NOT include full updated `Channel`
 * objects - re-fetch the lineup after a successful call to see the
 * newly-confirmed mappings.
 */
export interface BulkAcceptResult {
  lineupId: string;
  threshold: number;
  confirmedCount: number;
  confirmed: ConfirmedSuggestion[];
}
