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
          "sourceStreamUrl": "http://hdhomerun.local/auto/v7.1",
          "mapping": {
            "sdStationId": "10123",
            "sdLineupId": "USA-OTA-12345",
            "confirmed": true,
            "confirmedAt": "2026-10-29T00:10:00Z",
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
- `mapping` is `null`/absent until the user has at least suggestions computed;
  `confirmed: false` with `suggestions` populated is the "needs review" state
  the UI's bulk-accept flow operates on.
- `suggestions` are recomputed (not accumulated) each time mapping suggestions
  are (re)run for a channel.
- Writes to this file must be atomic (write to a temp file + rename) since it's
  the one piece of state that must never be left partially written.

## `/data/cache/sd/`

Cached SchedulesDirect API responses: lineups, stations/maps, schedules (by
station/day), program metadata, station logos. Fully regenerable from SD.
Exact file/key layout is an implementation detail of the SD client, but should
be organized so a single station's or lineup's cache can be invalidated/
refreshed independently (avoid one giant blob). Include a fetched-at timestamp
per cached entity so the refresh job can apply a TTL.

## `/data/output/`

Generated XMLTV files, one per epg-editor lineup by default:
`/data/output/<lineup-id>.xml`. Regenerated in place (overwrite, atomic write)
by the generation job. Served read-only over HTTP — the serving code should
never write to this directory.
