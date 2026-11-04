# Data model

epg-editor has no database. All durable app state is a JSON file on a mounted
volume. This document defines its shape. Treat this as the schema to implement
against — update this file in the same change if the schema changes.

## `/data/config/lineups.json`

The single source of truth for everything the user has built in epg-editor.
Not regenerable from SchedulesDirect — back this up, don't treat it as cache.

```json
{
  "schemaVersion": 1,
  "lineups": [
    {
      "id": "uuid-or-slug",
      "name": "Living Room Antenna",
      "source": "manual | m3u",
      "createdAt": "2026-10-29T00:00:00Z",
      "updatedAt": "2026-10-29T00:00:00Z",
      "sdLineupIds": ["USA-OTA-12345", "USA-CABLE-67890"],
      "channels": [
        {
          "id": "uuid-or-slug",
          "number": "7.1",
          "name": "KGO-TV",
          "logoUrl": "https://...",
          "tvgId": "KGO.us",
          "group": "Local",
          "sourceStreamUrl": "http://hdhomerun.local/auto/v7.1",
          "missingSince": null,
          "mapping": {
            "sdStationId": "10123",
            "sdLineupId": "USA-OTA-12345",
            "mappedAt": "2026-10-29T00:10:00Z",
            "suggestions": [
              { "sdStationId": "10123", "sdLineupId": "USA-OTA-12345", "score": 0.97 },
              { "sdStationId": "10456", "sdLineupId": "USA-OTA-12345", "score": 0.41 }
            ]
          }
        }
      ]
    }
  ]
}
```

Notes:

- `sourceStreamUrl` is retained purely as metadata (useful context when
  re-importing/refreshing from M3U); epg-editor never proxies or plays streams.
- `group`: from an M3U entry's `group-title` attribute (e.g. "Local",
  "Sports"); `null` for manually-added channels and for M3U entries that
  didn't specify one. Persisted (not just surfaced in an import-result
  response) for future UI grouping/filtering. Updated in place on
  re-import like the other M3U-derived fields (`name`, `logoUrl`, `number`,
  `tvgId`, `sourceStreamUrl`).
- `tvgId`/`number`: from an M3U entry's `tvg-id`/`tvg-chno` attributes.
  **Real-world addition:** some HDHomeRun firmware exports omit
  `tvg-id`/`tvg-chno` and instead emit `channel-id`/`channel-number` for
  the same data — both are recognized as alternates, consulted only when
  the standard `tvg-id`/`tvg-chno` attribute is absent on that entry (the
  standard attribute wins when both are present). Found against a real
  HDHomeRun firmware export during checkpoint 19, not a pre-specified
  attribute name; see `backend/app/services/m3u.py`'s `parse_m3u`
  docstring for the exact rule.
- `missingSince`: `null` normally. When an `m3u`-sourced lineup is
  re-imported and this channel's `tvgId` (fallback: `number`) no longer
  appears in the new M3U, set this to the re-import timestamp instead of
  deleting the channel — its mapping is preserved until the user
  explicitly removes it in the UI. Re-importing again with the channel
  present clears it back to `null`.
- `mapping` is `null`/absent until the user has at least suggestions
  computed. "Mapped" is derived purely from `sdStationId`/`sdLineupId` being
  non-`null` — there is no separate gating boolean. `suggestions` populated
  with `sdStationId` still `null` is the "needs review" state the UI's
  bulk-accept flow operates on.
- `suggestions` are recomputed (not accumulated) each time mapping suggestions
  are (re)run for a channel. Recomputed for *every* channel in the lineup,
  including ones that already have a mapped SD station — recomputation only
  ever replaces this `suggestions` list (a read-only "what else was
  considered" record for the UI); it never touches `sdStationId`/
  `sdLineupId`/`mappedAt`, so an existing mapping can't be silently
  changed by a later suggestion run. Capped at the top 5 highest-scoring
  candidates per channel (`MAX_SUGGESTIONS_PER_CHANNEL` in
  `backend/app/services/suggestions.py`) rather than every candidate in the
  pool, since a cable SD lineup's station roster can run into the hundreds.
  Scored via `rapidfuzz.fuzz.WRatio` (with `rapidfuzz.utils.default_process`)
  against each candidate station's `name`, `callsign`, *and* `affiliate`,
  taking the max across the three and normalizing `WRatio`'s 0-100 output to
  this field's 0-1 scale — see that module for the full scoring/threshold
  rationale (including why a channel's `tvgId` is deliberately *not* used
  as an additional matching signal). The candidate pool for a given
  epg-editor lineup is the deduped (by `stationID`) union of cached
  stations across every SD lineup in that lineup's `sdLineupIds`; station
  rosters are fetched from SD and cached under `cache/sd/stations/` only on
  a cache miss, and only for SD lineups actually associated with the
  epg-editor lineup being scored (no speculative bulk-fetching).
  **The three display-only fields below (`stationName`/`callsign`/
  `logoUrl`) are present as keys in the persisted JSON (`MappingSuggestion`
  always declares them) but always `null` on disk** — the meaningful
  persisted shape is `{sdStationId, sdLineupId, score}` as shown above.
  Every `api/lineups.py`/`api/m3u.py` route that returns a `Channel` or
  `Lineup` additionally returns `stationName`/`callsign`/`logoUrl` populated
  on each suggestion in the *response body only* — computed fresh at
  request time from the cached SD station roster
  (`services.suggestions.enrich_channel_suggestions`/
  `enrich_lineup_suggestions`/`enrich_lineups_suggestions`) so the
  suggestion-review UI can show a human-readable name/call sign instead of
  a bare SD station ID, no matter which endpoint's response the frontend
  used to update its local state. `config/lineups.json` is never written
  with these three fields populated with real data.
- Writes to this file must be atomic (write to a temp file + rename) since it's
  the one piece of state that must never be left partially written.
- Atomicity of the file write alone isn't enough to prevent lost updates:
  FastAPI runs sync route handlers in a threadpool, so two concurrent
  mutations (e.g. two "add channel" requests) that each do their own
  load -> mutate -> save can race and silently drop one of them even
  though each individual write is atomic. `storage/lineups.py` closes this
  with `update_lineups()`, which holds a process-wide lock across the full
  load-mutate-save cycle; every mutation in `services/lineups.py` goes
  through it rather than calling `load_lineups`/`save_lineups` directly.

## `/data/cache/sd/`

Cached SchedulesDirect API responses: lineups, stations/maps, schedules (by
station/day), program metadata, station logos. Fully regenerable from SD.
Exact file/key layout is an implementation detail of the SD client, but should
be organized so a single station's or lineup's cache can be invalidated/
refreshed independently (avoid one giant blob). Include a fetched-at timestamp
per cached entity so the refresh job can apply a TTL.

A cached SD lineup's station roster (`stations/<sdLineupId>.json`,
`CachedLineupStations`) additionally records SD's own `GET /status`
`lineups[].modified` timestamp *as of the fetch that produced the cache
entry*, alongside `fetchedAt`. Phase 5's refresh job
(`backend/app/services/refresh.py`) compares a fresh `modified` value
against this to decide whether a roster actually needs re-fetching, with a
30-day fallback TTL (keyed off `fetchedAt`) forcing a re-fetch regardless —
see CLAUDE.md's "Guide refresh" section.

A cached program's metadata (`programs/<programId>.json`, `CachedProgram`)
additionally records `scheduleMd5`: the per-airing md5 (`SdScheduleProgram
.md5`) reported by whichever schedule day this program was fetched on
behalf of, at fetch time. The refresh job compares this against the md5 a
*current* cached schedule reports for the same program ID — scanning every
cached schedule day in the guide window, not just ones refetched in a given
run — to decide whether a program needs (re-)fetching. This is what makes a
previously-failed `/programs` fetch self-heal on a later run even when the
schedule day it belongs to has since gone md5-unchanged (a schedule day's
own md5 not changing used to mean its programs' fetch was never retried
again once it had failed once — a HIGH-severity peer-review finding fixed
under docs/backlog.md item 32).

## `/data/output/`

Generated XMLTV files, one per epg-editor lineup by default:
`/data/output/<lineup-id>.xml`. Regenerated in place (overwrite, atomic write)
by the generation job. Served read-only over HTTP — the serving code should
never write to this directory.
