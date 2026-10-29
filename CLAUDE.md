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
- **Backend: Python, FastAPI.** Locked in — not a default to swap out.
- **Python dependency management and builds: `uv`.** Not pip/poetry/pipenv
  directly. `backend/pyproject.toml` + `uv.lock` define dependencies; install
  with `uv sync`; the Docker build's Python stage uses `uv` as well.
- **Backend data models: Pydantic.** Every structured object that crosses a
  boundary — SD API requests/responses, the `config/lineups.json` contents,
  FastAPI request/response bodies — is a Pydantic model, not a raw dict.
  This is true even though there's no database: Pydantic is the validation/
  (de)serialization layer in its place.
- **Scheduled tasks: APScheduler.** Locked in as the in-process scheduler —
  no external task queue/broker.
- **Frontend: React + TypeScript, styled-components for all styling.** Do not
  introduce Tailwind, CSS Modules, or other styling systems. See
  [github.com/styled-components/styled-components](https://github.com/styled-components/styled-components).
- **Frontend dependency management: plain `npm`.** No yarn, pnpm, or
  monorepo/workspace tooling — `frontend/package.json` + `package-lock.json`,
  installed with `npm install`.
- **Frontend API client: vanilla JavaScript, isolated from presentation
  code.** The module responsible for calling the epg-editor backend API
  (`frontend/src/api/`) is plain `.js`, not `.ts`/`.tsx`, and contains no
  React/JSX or styled-components — it's a clean HTTP client the rest of the
  (TypeScript) app imports. See "Frontend module layout" below.
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
- **Guide refresh:** the APScheduler-based scheduler periodically refreshes
  cached SD data and regenerates XMLTV files. The UI also exposes a manual
  "refresh now" action that runs the same pipeline on demand. Refresh
  interval should be configurable via environment variable.

## Backend module layout (separation of concerns)

The backend must keep these concerns in separate modules/packages — no module
should straddle two of these responsibilities:

- **`sd_client/`** — the *only* place that talks HTTP to SchedulesDirect.
  A typed client exposing methods like "get token", "list account lineups",
  "add/remove account lineup", "get lineup stations", "get schedules",
  "get programs", "get logos". Requests and responses are Pydantic models.
  This module knows nothing about epg-editor's own domain concepts
  (epg-editor "lineups", channel mappings) — it's a thin wrapper around SD's
  JSON API and would be reusable outside this app.
- **`models/`** — shared Pydantic models: both the app's own domain objects
  (`Lineup`, `Channel`, `ChannelMapping`, matching `docs/data-model.md`) and
  the SD request/response schemas used by `sd_client/`. Other modules import
  from here rather than redefining shapes.
- **`storage/`** — all reads/writes of `config/lineups.json`,
  `cache/sd/*`, and `output/*.xml`. Nothing outside this module touches the
  filesystem under `/data` directly. Responsible for the atomic-write
  guarantee on `config/lineups.json` (see `docs/data-model.md`).
- **`services/` (or `domain/`)** — the actual business logic: M3U parsing,
  mapping-suggestion computation, XMLTV generation. Calls into `sd_client/`
  and `storage/`; never does its own HTTP or raw file I/O.
- **`scheduler/`** — APScheduler setup and job definitions. Jobs are thin —
  they call into `services/` functions rather than embedding logic themselves.
- **`api/`** — FastAPI routers. Thin HTTP layer that validates
  input/output via Pydantic and delegates to `services/`. No business logic
  or direct storage/SD-client calls here either.

Dependency direction: `api/` and `scheduler/` → `services/` → `sd_client/` +
`storage/` → `models/`. Lower layers never import from higher ones.

## Frontend module layout (separation of concerns)

- **`frontend/src/api/`** — vanilla JavaScript. The only place that issues
  HTTP requests to the epg-editor backend. No React, no JSX, no
  styled-components, no TypeScript-specific syntax — plain functions/modules
  that presentational code imports and calls. Keeping this in plain JS (not
  TS) is intentional, not an oversight.
- **`frontend/src/components/`, `frontend/src/pages/`** — TypeScript (`.tsx`),
  all styling via styled-components. These call into `api/` for data; they
  never construct `fetch`/HTTP calls themselves.
- **`frontend/src/types/`** — shared TypeScript types for domain objects
  (mirroring the backend's Pydantic models / `docs/data-model.md`).
- `tsconfig.json` must set `"allowJs": true` (and ideally `"checkJs": false`)
  so the plain-JS `api/` directory coexists with the rest of the
  TypeScript app without being type-checked as if it were TS.

## Core workflows

1. **Create a lineup.**
   - Manually: user adds channels one at a time (number, name, logo, etc.).
   - From M3U: user uploads an M3U file (as produced by e.g. an HDHomeRun
     device); parse `#EXTINF` entries (`tvg-id`, `tvg-name`, `tvg-logo`,
     `group-title`, channel number if present) to pre-populate the channel
     list. The stream URL is retained only as metadata on the channel record —
     epg-editor does not proxy or manage streams.
   - **Re-importing M3U into an existing lineup:** match incoming entries to
     existing channels by `tvgId` (fallback: channel number). Update matched
     channels' metadata in place (preserving their confirmed mapping).
     Unmatched incoming entries are added as new channels. Existing channels
     that no longer appear in the new M3U are **flagged as missing, not
     auto-deleted** — the user confirms removal in the UI. This avoids
     silently discarding a channel's confirmed mapping because of a flaky or
     partial M3U fetch.
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
   - **Bulk-accept** all suggestions at or above a confidence threshold. The
     threshold is a **fixed backend default (not a UI control)** — pick a
     starting value (e.g. `0.85`) and tune it during implementation based on
     real matching results; exposing it as a user-adjustable setting is not
     in scope.
5. **Generate XMLTV.** For every channel with a confirmed mapping, pull cached
   SD schedule/program data and emit a valid XMLTV document. Default to one
   XMLTV file per epg-editor lineup (Plex/Jellyfin each typically point at one
   EPG URL per tuner/source) — write it to the output directory, overwriting
   the previous version.
6. **Serve XMLTV.** Expose each generated file at a stable HTTP path
   (e.g. `/xmltv/{lineup-id}.xml`) as a static file response.

### Reserved URL path prefixes

The single backend process serves the JSON API, generated XMLTV files, and
the static React app on one port, so these prefixes are reserved to avoid
collisions (e.g. a lineup whose id/slug happens to be `api`):

- `/api/*` — all JSON API routes (FastAPI routers).
- `/xmltv/*` — all generated-guide output (e.g. `/xmltv/{lineup-id}.xml`).
- Everything else falls through to the static React app / its client-side
  router.

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

- React + TypeScript, styled-components only for styling.
- Plain `npm` for dependency management (no yarn/pnpm). See "Frontend module
  layout" above for the vanilla-JS `api/` vs. TypeScript presentation split.
- Suggested but **not yet locked** libraries to evaluate at implementation
  time (recommend options, let the user decide — do not just pick silently):
  server state/data fetching (e.g. TanStack Query), routing (e.g. React
  Router), M3U upload UX.
- No Tailwind. No inline style objects as a styling strategy — use
  styled-components.

## Docker

- Single multi-stage `Dockerfile` **at the repo root** (matches
  `docker-compose.example.yml`'s `build: .`):
  1. Node stage runs `npm install` + build to produce the frontend's
     production static assets.
  2. Python stage installs backend dependencies with `uv` (from
     `backend/pyproject.toml` + `uv.lock`), copies the backend source and the
     built frontend assets, and runs the single server process.
- An entrypoint script (if needed, e.g. to ensure `/data/{config,cache,output}`
  exist before the app starts) lives at `docker/entrypoint.sh` and is `COPY`'d
  into the image by the root `Dockerfile` — only the `Dockerfile` itself must
  be at the root.
- Provide a `docker-compose.example.yml` showing the volume mount for `/data`
  and the required SD credential environment variables. Keep it client-neutral
  — do not add Plex- or Jellyfin-specific setup steps anywhere in the repo
  (README included); this project is a general XMLTV source, not a
  Plex/Jellyfin plugin.

## Project agents

`.claude/agents/` defines project-local Claude Code agents for working on
epg-editor: `project-manager` (coordinates the others — use it for anything
spanning more than one role), `backend-developer`, `frontend-developer`,
`peer-reviewer` (covers both frontend and backend), and `uat-tester`. Keep
each one's hard-constraints list in sync with this file if an architecture
decision changes.

## Development environment

A `.devcontainer/` configuration is checked in so development happens inside
a VS Code dev container with both the Python and Node toolchains available.
Keep it working as the backend/frontend scaffolding is added — update its
`postCreateCommand`/features if dependency install steps change.

## Repository layout (intended — create as implementation proceeds)

```
epg-editor/
├── backend/
│   └── app/
│       ├── api/          # FastAPI routers
│       ├── services/     # business logic: mapping, XMLTV generation, M3U parsing
│       ├── sd_client/    # SchedulesDirect JSON API client
│       ├── storage/      # JSON config/cache/output file I/O
│       ├── models/       # Pydantic models (domain + SD schemas)
│       └── scheduler/    # APScheduler setup and jobs
├── frontend/
│   └── src/
│       ├── api/          # vanilla JS backend API client (no React/TS)
│       ├── components/   # React + TypeScript, styled-components
│       ├── pages/        # route-level views (TypeScript)
│       └── types/        # shared TypeScript types
├── docker/
│   └── entrypoint.sh  # copied into the image by the root Dockerfile
├── docs/              # architecture docs (this file links to them)
├── .devcontainer/     # VS Code dev container config
├── Dockerfile
├── docker-compose.example.yml
├── README.md
└── CLAUDE.md
```

## Open decisions deferred to implementation time

- Exact fuzzy-matching library/threshold for mapping suggestions.
- Whether `config/lineups.json` becomes multiple files (one per lineup) once
  real usage shows a single file is unwieldy — not a reason to add a database.
- Exact refresh interval default and its env var name.
