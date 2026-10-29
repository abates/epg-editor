# epg-editor

## Purpose

epg-editor is a self-hosted web application for building and maintaining XMLTV
guide data consumed by streaming media platforms (e.g. Plex, Jellyfin). It lets
a user define "lineups" of channels — either by hand or imported from an M3U
playlist (e.g. from an HDHomeRun) — and map each channel to the matching
station in one or more SchedulesDirect.org lineups. From the confirmed
mappings it generates XMLTV files and serves them over HTTP.

SchedulesDirect.org (SD) is the sole upstream guide-data provider.

## Architecture decisions (locked in — do not revisit without the user)

These were explicitly decided in planning and should be treated as constraints,
not defaults to reconsider:

- **No database.** All persistent app state (lineups, channels, mappings) lives
  in a JSON file (or small set of JSON files) on a mounted volume. See
  [docs/data-model.md](docs/data-model.md).
- **No login / no multi-user auth.** The app is single-user and assumes
  network-level trust (LAN, reverse proxy, etc.) — same posture as most
  self-hosted homelab tools. Do not add session/auth scaffolding.
- **SchedulesDirect credentials come from environment variables only**
  (e.g. `SD_USERNAME`, `SD_PASSWORD`). They are never written to the JSON
  config, never logged, never cached to disk in plaintext. The short-lived SD
  API token obtained at runtime may be cached in memory or in the cache
  directory (not the config file).
- **Backend: Python.** Framework choice is FastAPI (async, OpenAPI schema for
  free, pairs well with an in-process scheduler) unless a future agent has a
  strong reason to deviate — confirm with the user before switching frameworks.
- **Frontend: React, styled-components for all styling.** Do not introduce
  Tailwind, CSS Modules, or other styling systems. See
  [github.com/styled-components/styled-components](https://github.com/styled-components/styled-components).
- **Single Docker image.** Multi-stage build: build the React app, then copy
  the static build output into the Python backend image. One process
  (e.g. `uvicorn`) serves the API, the static frontend, and the generated
  XMLTV files. No docker-compose with multiple app services — just one image
  meant to be dropped into *someone else's* compose file alongside Plex/Jellyfin.
- **XMLTV delivery:** generation is a distinct step from serving.
  - Generation (scheduled or triggered from the UI) writes an XMLTV file to
    disk under the data volume.
  - Serving is a plain HTTP endpoint/static file response that returns the
    already-generated file — XMLTV is never generated on-the-fly per request.
- **Guide refresh:** a background scheduler (in-process, e.g. APScheduler —
  no external task queue/broker) periodically refreshes cached SD data and
  regenerates XMLTV files. The UI also exposes a manual "refresh now" action
  that runs the same pipeline on demand. Refresh interval should be
  configurable via environment variable.

## Core workflows

1. **Create a lineup.**
   - Manually: user adds channels one at a time (number, name, logo, etc.).
   - From M3U: user uploads an M3U file (as produced by e.g. an HDHomeRun
     device); parse `#EXTINF` entries (`tvg-id`, `tvg-name`, `tvg-logo`,
     `group-title`, channel number if present) to pre-populate the channel
     list. The stream URL is retained only as metadata on the channel record —
     epg-editor does not proxy or manage streams.
2. **Manage SchedulesDirect account lineups.** Full CRUD against the user's SD
   account lineups (SD calls these "lineups"/headend subscriptions) via the SD
   API: list, add, remove. SD accounts have a limited number of lineup slots —
   surface that limit in the UI rather than discovering it via a failed API
   call.
3. **Associate SD lineup(s) with an epg-editor lineup.** One epg-editor lineup
   can draw channel/station candidates from multiple SD lineups (e.g. an
   over-the-air lineup plus a cable lineup).
4. **Map channels.** For each epg-editor channel, suggest candidate SD
   stations from the associated SD lineup(s) using fuzzy matching on
   name/call sign (candidate library: `rapidfuzz` — confirm/evaluate before
   locking in, per the user's library-selection preference). Each suggestion
   carries a confidence score. The user can:
   - Accept/reject suggestions individually.
   - **Bulk-accept** all suggestions at or above a confidence threshold.
5. **Generate XMLTV.** For every channel with a confirmed mapping, pull cached
   SD schedule/program data and emit a valid XMLTV document. Default to one
   XMLTV file per epg-editor lineup (Plex/Jellyfin each typically point at one
   EPG URL per tuner/source) — write it to the output directory, overwriting
   the previous version.
6. **Serve XMLTV.** Expose each generated file at a stable HTTP path
   (e.g. `/xmltv/{lineup-id}.xml`) as a static file response.

## Persistent data layout (no database)

See [docs/data-model.md](docs/data-model.md) for the full JSON schema. Summary:

```
/data
├── config/
│   └── lineups.json      # source of truth: lineups, channels, mappings, SD lineup associations
├── cache/
│   └── sd/                # cached SchedulesDirect API responses (stations, schedules, programs) — regenerable, safe to delete, has TTL
└── output/
    └── <lineup-id>.xml    # generated XMLTV, written by the generation job, served over HTTP
```

`config/lineups.json` is the only data that is *not* regenerable from SD — treat
it as the thing that must never be silently dropped or corrupted. `cache/` and
`output/` can always be rebuilt from `config/` + SD.

## SchedulesDirect API integration notes

See [docs/schedulesdirect-integration.md](docs/schedulesdirect-integration.md)
for endpoint-level notes (auth/token flow, lineups, stations, schedules,
programs, logos) and rate-limit/caching expectations. Key principle: SD
imposes call/day limits and expects clients to cache aggressively — the
`cache/` directory exists specifically to respect that, not just for
performance.

## Frontend conventions

- React, styled-components only for styling.
- Suggested but **not yet locked** libraries to evaluate at implementation
  time (recommend options, let the user decide — do not just pick silently):
  server state/data fetching (e.g. TanStack Query), routing (e.g. React
  Router), M3U upload UX.
- No Tailwind. No inline style objects as a styling strategy — use
  styled-components.

## Docker

- Single multi-stage `Dockerfile`:
  1. Node stage builds the frontend (production static assets).
  2. Python stage copies the backend source + the built frontend assets, and
     runs the single server process.
- Provide a `docker-compose.example.yml` showing the volume mount for `/data`
  and the required SD credential environment variables. Keep it client-neutral
  — do not add Plex- or Jellyfin-specific setup steps anywhere in the repo
  (README included); this project is a general XMLTV source, not a
  Plex/Jellyfin plugin.

## Repository layout (intended — create as implementation proceeds)

```
epg-editor/
├── backend/          # Python (FastAPI) app: SD client, mapping logic, XMLTV generation, scheduler, static file serving
├── frontend/          # React + styled-components app
├── docker/            # Dockerfile, entrypoint script
├── docs/              # architecture docs (this file links to them)
├── docker-compose.example.yml
├── README.md
└── CLAUDE.md
```

## Open decisions deferred to implementation time

- Exact fuzzy-matching library/threshold for mapping suggestions.
- Whether `config/lineups.json` becomes multiple files (one per lineup) once
  real usage shows a single file is unwieldy — not a reason to add a database.
- Exact refresh interval default and its env var name.
