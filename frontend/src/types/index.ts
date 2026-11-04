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
 * Populated by the suggestion-scoring service; `suggestions` arrays are
 * empty until "Generate Suggestions" has been run for the lineup.
 *
 * `stationName`/`callsign`/`logoUrl` are enrichment fields populated from
 * cached SchedulesDirect station data when available - they are `null`
 * (not omitted) when that cache data isn't available (e.g. stale cache, a
 * disassociated SD lineup). Callers must fall back to `sdStationId`/
 * `sdLineupId` rather than assuming these are always present.
 */
export interface MappingSuggestion {
  sdStationId: string;
  sdLineupId: string;
  score: number;
  stationName: string | null;
  callsign: string | null;
  logoUrl: string | null;
}

/**
 * A channel's association with a SchedulesDirect station.
 *
 * `sdStationId`/`sdLineupId` are `null` until a suggestion is accepted or
 * the user sets a mapping directly via the mapping endpoint. A `null`
 * `sdStationId` with `suggestions` populated is the "needs review" state
 * the bulk-accept flow operates on - there's no separate confirmed/
 * unconfirmed boolean; a non-null `sdStationId` always means mapped.
 */
export interface ChannelMapping {
  sdStationId: string | null;
  sdLineupId: string | null;
  mappedAt: string | null;
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

// --- Cache-only station search (`/api/lineups/{lineupId}/station-search`) -
//
// Backs the searchable station picker in `ChannelMappingForm` (backlog item
// 37) - mirrors `backend/app/models/station_search.py`'s
// `StationSearchCandidate`/`StationSearchResult`.

/**
 * One SD station candidate matched against a search query (or, in browse
 * mode, one entry from the full candidate pool).
 *
 * `callsign`/`affiliate`/`logoUrl` are enrichment fields from cached SD
 * station data and may be `null`. `score` is on the same 0-1 scale as
 * `MappingSuggestion.score`; it's `0.0` for every result in browse mode
 * (empty/whitespace `query`) and always `> 0.0` for a non-empty query -
 * zero-relevance candidates are excluded from `results` entirely in that
 * case rather than appearing with `score: 0.0` (see
 * `StationSearchResult.results`'s docstring).
 */
export interface StationSearchCandidate {
  stationID: string;
  name: string;
  callsign: string | null;
  affiliate: string | null;
  logoUrl: string | null;
  sdLineupId: string;
  score: number;
}

/**
 * Response body for `GET /api/lineups/{lineupId}/station-search`.
 *
 * An empty `results` genuinely means "no matches" only when
 * `uncachedSdLineupIds` is also empty - a non-empty `uncachedSdLineupIds`
 * means some of the lineup's associated SD lineups have no cached station
 * roster yet, so an empty/sparse `results` could just mean incomplete data,
 * not "nothing matched." Treat `uncachedSdLineupIds` as a set (may
 * theoretically contain duplicates) - dedupe client-side before rendering
 * each one.
 */
export interface StationSearchResult {
  lineupId: string;
  query: string;
  resultCount: number;
  /**
   * Size of the full deduped candidate pool before truncation by `limit` -
   * use this for a "showing N of M, type to narrow" hint in browse mode
   * when the pool is bigger than what's shown.
   */
  candidatePoolSize: number;
  uncachedSdLineupIds: string[];
  results: StationSearchCandidate[];
}

// --- SchedulesDirect account lineups (`/api/sd-account/*`) --------------
//
// These mirror `backend/app/models/sd.py`'s `SdLineupSummary`/
// `SdAddRemoveLineupResponse` and `backend/app/models/sd_account.py`'s
// `SdAccountLineupLimit` - the user's real SD *account* lineups (SD's own
// headend subscriptions), entirely distinct from epg-editor's own `Lineup`
// above. See `frontend/src/api/sdAccount.js`.

/** One of the user's subscribed SD account lineups. */
export interface SdAccountLineup {
  lineup: string;
  name: string;
  transport: string | null;
  location: string | null;
  uri: string | null;
}

/**
 * Response from `POST /api/sd-account/lineups` or
 * `DELETE /api/sd-account/lineups/{lineupId}` - SD's raw add/remove
 * confirmation shape. Only `message` (when present) is generally worth
 * surfacing to the user; a generic success message is a fine fallback.
 */
export interface SdAddRemoveLineupResponse {
  response: string | null;
  code: number;
  serverID: string | null;
  message: string | null;
  changesRemaining: number | null;
  datetime: string | null;
}

/**
 * The account's lineup-slot usage, from `GET /api/sd-account/limit`.
 *
 * `maxLineups` is `null` if SD's `/status` response didn't include it -
 * treat that as "limit unknown," not as zero/unlimited. `lineupsUsed`
 * conservatively includes lineups SD has marked `isDeleted` on their side;
 * `deletedLineupCount` says how many of that total are in that state.
 */
export interface SdAccountLineupLimit {
  maxLineups: number | null;
  lineupsUsed: number;
  deletedLineupCount: number;
}

// --- Global refresh pipeline (`/api/refresh-now`) -----------------------
//
// Mirrors `backend/app/models/refresh.py`'s `RefreshResult`/`RefreshError`.
// Deliberately a separate, all-lineups result shape from the removed
// per-lineup `sync-and-generate` mechanism - this one runs across every
// epg-editor lineup in a single call, not just one. See
// `frontend/src/api/refresh.js` and `components/RefreshNowPanel.tsx`.

/** What a `RefreshError` is scoped to. */
export type RefreshErrorScope = 'account' | 'sd_lineup' | 'lineup' | 'station' | 'programs';

/**
 * One failure recorded during a `POST /api/refresh-now` run. `id` is the
 * relevant SD lineup id / epg-editor lineup id / SD station id for scopes
 * that have one; `null` for `scope: "account"` and `scope: "programs"`
 * (not tied to one specific id).
 */
export interface RefreshError {
  scope: RefreshErrorScope;
  id: string | null;
  message: string;
}

/**
 * Response body for `POST /api/refresh-now`: the outcome of one run of the
 * global refresh pipeline across every epg-editor lineup (station roster
 * refresh, schedule/program fetch with the md5-based "skip unchanged"
 * optimization, and XMLTV regeneration).
 *
 * Produced identically by this manual trigger and the APScheduler job that
 * runs the same pipeline on a timer (`EPG_EDITOR_REFRESH_INTERVAL` hours) -
 * triggering this does not reset or otherwise affect that schedule.
 *
 * A 200 response doesn't guarantee every step succeeded - `errors` can be
 * non-empty alongside non-zero success counts (partial failure at the
 * account/SD-lineup/lineup/station/programs level), so callers should
 * surface both rather than treating a 200 as unconditional success.
 */
export interface RefreshResult {
  lineupsProcessed: number;
  lineupsRegenerated: number;
  stationRostersRefreshed: number;
  stationRostersSkipped: number;
  scheduleDaysChecked: number;
  scheduleDaysRefetched: number;
  scheduleDaysSkippedUnchanged: number;
  programsFetched: number;
  errors: RefreshError[];
}
