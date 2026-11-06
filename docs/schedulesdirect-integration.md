# SchedulesDirect.org integration notes

Reference: https://json.schedulesdirect.org/ (SD JSON Service API docs).
Verify current endpoint paths/behavior against SD's live docs when
implementing — this file records the integration *shape*, not a frozen
contract.

## Auth

- `POST /token` with username + SHA1-hashed password returns a short-lived
  token (~24h).
- Token goes in the `token` request header for subsequent calls.
- Username/password are read from environment variables
  (`SD_USERNAME` / `SD_PASSWORD`) — never persisted to `config/lineups.json`.
  The token itself may be cached in memory or under `cache/sd/` and refreshed
  transparently when expired/about to expire; it is not a secret worth
  protecting as carefully as the password, but still shouldn't be logged.

## Rate limits / caching expectations

SD throttles and expects well-behaved clients to cache. Concretely:

- Station/lineup/schedule metadata changes infrequently — cache with a TTL
  (hours, not seconds) rather than fetching live on every UI interaction.
  This is what `/data/cache/sd/` is for.
- Program/schedule data changes daily; SD exposes `md5` hashes per
  station/day so a client can check "has this changed" before re-pulling the
  full schedule — use that to avoid redundant fetches on the scheduled
  refresh. Implemented via `POST /schedules/md5` (`SdClient
  .get_schedule_md5s`, same request shape as `/schedules` — an array of
  `{stationID, date[]}` — but a response keyed `stationID -> date ->
  {code, message, lastModified, md5}`, verified against
  SchedulesDirect/JSON-Service's wiki during Phase 5 implementation): the
  refresh job (`backend/app/services/refresh.py`) calls this first and
  only falls through to the full `POST /schedules` for a station/day whose
  md5 differs from what's cached (or was never cached).
- SD's own docs ask clients not to sync more than once an hour — the
  scheduled refresh job's interval (`EPG_EDITOR_REFRESH_INTERVAL`, default
  12 hours) is clamped up to a 1-hour floor if configured lower.
- Only fetch schedules/programs for stations that are actually mapped to a
  channel in a lineup — no speculative bulk-fetching of every station in
  every associated SD lineup.
- SD documents a hard cap of 5000 IDs per `POST /programs` request.
  `SdClient.get_programs` chunks internally (`PROGRAMS_REQUEST_CHUNK_SIZE`)
  so callers can pass however many program IDs a guide window's worth of
  mapped stations actually needs without tripping over that cap — a real
  account's mapped-station count can exceed it, and a cap-exceeding
  request would otherwise fail outright (found during peer review of the
  Phase 5 refresh pipeline, docs/backlog.md item 32).

## Endpoints needed

- **Account lineups**: list the user's SD account lineups; add a lineup by
  postal code/lineup ID; remove a lineup. Backs the "manage lineups in my SD
  account" UI feature directly — this is distinct from epg-editor's own
  lineups.
- **Lineup/headend detail**: given an SD lineup ID, list its stations
  (the candidate pool for channel-mapping suggestions).
- **Schedules**: per station, per day — md5 + schedule data.
- **Programs**: program metadata by program ID, batched.
- **Logos**: station logo URLs (used for channel display, not required for
  mapping logic).

## Mapping suggestion inputs

When computing suggestions for a channel, the candidate station pool is the
union of stations across the epg-editor lineup's associated `sdLineupIds`
(cached locally, not re-fetched per suggestion run). Match on station name,
call sign, and affiliate — see `docs/data-model.md` for where results are
stored (`mapping.suggestions`).

## XMLTV generation inputs

For each channel with a mapped SD station (`sdStationId`/`sdLineupId` set),
pull the station's cached schedule entries
for the desired guide window (e.g. next N days) and resolve each schedule
entry's program ID to cached program metadata. Emit standard XMLTV
`<channel>` and `<programme>` elements. Validate output against the XMLTV DTD
during development to catch generation bugs early.

### Program metadata used for series/episode info (docs/backlog.md item 40)

SD's `POST /programs` response (modeled as `SdProgram` in `models/sd.py`)
carries several fields `services/xmltv.py` needs to tell a movie apart from
a series episode and to emit episode/series details, verified against
SchedulesDirect/JSON-Service's wiki
(`API-20141201.md`/`API-20141201-Program-Response.md`) during item 40's
implementation:

- **`programID`**: 14 characters — a 2-letter type prefix (`EP` episode,
  `SH` generic/no-specific-episode series reference, `MV` movie, `SP`
  sports, and others) followed by 12 digits: the first 8 identify the
  show/series, the last 4 identify the specific episode (`"0000"`
  conventionally meaning "no specific episode," as on an `SH` entry).
  zap2xml (the most widely used SD-to-XMLTV grabber, and the reason Plex's
  XMLTV importer recognizes this convention at all) formats this as a
  `dd_progid`-system `<episode-num>` by inserting a dot before the last 4
  digits, e.g. `EP01280105.0074`.
- **`entityType`**: SD's own classification. `API-20141201-Program-Response.md`
  documents roughly 20 values; the ones confirmed against real `/programs`
  responses or named in SD's own docs as of item 40's implementation are
  `Episode`, `Series`, `Show`, `Miniseries`, `Special`, `Movie`, `TV Movie`,
  `Paid Program`, `Sports`, `Sport-Related Episode`, and `Team Event` — the
  full enumeration isn't reproduced here; see SchedulesDirect/JSON-Service's
  wiki for the authoritative list. **This, not the programID prefix, is
  SD's documented authoritative movie-vs-episode signal** — their own docs
  note "not all sports events will have a leading `SP` programID; your
  application should use the entity type." `services/xmltv.py` treats the
  programID prefix as a fallback only, for programs cached before this
  field existed on `SdProgram` (see the cache-migration note below).

  **Movie-vs-series classification is "movie unless proven otherwise"**
  (peer-review fix to item 40, 2026-11-06): `services/xmltv.py`'s
  `_is_movie` checks `entityType` against a short, explicit allowlist
  (`_MOVIE_ENTITY_TYPES`: `Movie`, `TV Movie`, `Paid Program`) rather than
  enumerating every series-ish value. The original fix enumerated a
  "series" set (`Episode`, `Series`, `Miniseries`, `Sport-Related Episode`)
  and fell through to *no* classification (and therefore no episode-num at
  all) for any `entityType` value outside that set — `Show` being the
  concrete case that surfaced this, but it affected every unlisted value,
  including ones SD might add in the future. Enumerating movie types
  instead fails safe toward the series branch: `Series`, `Show`, `Special`,
  `Sports`, `Sport-Related Episode`, `Team Event`, `Miniseries`, and any
  other/future `entityType` value all get series treatment (a `dd_progid`
  episode-num at minimum) rather than silently getting none.
- **`showType`**: a finer-grained description (e.g. `"Feature Film"` for a
  `Movie`-entityType program). Modeled for completeness; not currently used
  for the movie/series decision.
- **`metadata`**: a list of single-key `{providerName: {season, episode,
  totalEpisodes, totalSeasons}}` objects (observed provider: `"Gracenote"`;
  SD's docs also mention TVMaze). Not every program has this — many
  stations' listings carry only the programID/entityType, no Gracenote
  season/episode numbers — so `services/xmltv.py` emits a `dd_progid`
  `<episode-num>` whenever a program is a series episode regardless, and
  layers `xmltv_ns`/`onscreen`-system `<episode-num>` entries on top only
  when season/episode numbers are actually present.
- **`episodeTitle150`**: the episode's own title (XMLTV `<sub-title>`).
- **`originalAirDate`**: `"YYYY-MM-DD"`; mapped to XMLTV's `<date>` as
  digits-only (e.g. `"20131108"`), the long-established convention
  SD-sourced XMLTV grabbers use for this field.
- **`genres`**: free-text genre strings; mapped straight to XMLTV
  `<category>` elements alongside a `"Movie"`/`"Series"` classification
  category.

**Cache-migration note**: `entityType`/`showType`/`metadata` were added to
`SdProgram` in item 40, after this app had already been caching program
responses in `cache/sd/programs/` without them. A `CachedProgram` written
before this change still deserializes fine (the new fields default to
`None`/empty, same as SD itself reporting nothing), but `services/refresh
.py`'s md5-based skip logic (see "Rate limits / caching expectations"
above) means an already-cached, unchanged program will **not**
automatically re-fetch just because the app upgraded — nothing in SD's own
per-program/per-airing md5 changed. Since `cache/sd/` is fully regenerable
and safe to delete at any time (per `docs/data-model.md`), the fix for an
existing deployment picking up this change is a one-time manual clear of
`cache/sd/programs/` followed by a refresh (wait for the next scheduled
run, or trigger `POST /api/refresh-now`) — see docs/backlog.md item 40.
