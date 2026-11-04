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
