# epg-editor

A self-hosted web app for building channel lineups and generating XMLTV guide
data from [SchedulesDirect.org](https://schedulesdirect.org). Create a lineup
manually or import one from an M3U playlist, map its channels to the matching
SchedulesDirect stations, and epg-editor generates an XMLTV file you can point
any XMLTV-compatible media server at.

## Status

Early planning stage — see [CLAUDE.md](CLAUDE.md) and [docs/](docs) for the
architecture and data model this project is being built against.

## Running

Ships as a single Docker image intended to be added to an existing
`docker-compose.yml` alongside whatever else you run. See
[`docker-compose.example.yml`](docker-compose.example.yml) for the required
volume mount and environment variables.

## Development

Backend (FastAPI via `uv`):

```bash
source .env
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8080
```

The dev server must run on port 8080 — the frontend's Vite dev-proxy
(`frontend/vite.config.ts`) and the devcontainer's forwarded ports both
assume the backend is reachable at `:8080`. `uvicorn` defaults to port 8000
if `--port` is omitted, so don't drop that flag in dev.

Frontend (Vite + npm) — see [`frontend/README.md`](frontend/README.md).

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `SD_USERNAME` | yes | SchedulesDirect.org account username |
| `SD_PASSWORD` | yes | SchedulesDirect.org account password |
| `EPG_EDITOR_REFRESH_INTERVAL` | no | How often the background refresh job re-syncs SD data and regenerates XMLTV, in **hours** (the name has no `_HOURS` suffix, but the value is always a number of hours). Defaults to `12`. Values below `1` are clamped up to `1` hour, per SchedulesDirect's own request not to sync more than once an hour. A manual "refresh now" action (UI button / `POST /api/refresh-now`) runs the same pipeline on demand without affecting this schedule. |

All other app state (lineups, channels, mappings, generated XMLTV) lives on
the `/data` volume — see [docs/data-model.md](docs/data-model.md).
