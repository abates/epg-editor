# epg-editor — Requirements

Status: Draft v1 (2026-10-18)

## 1. Purpose

`epg-editor` is a small self-hosted web application that turns an IPTV channel list (`.m3u`) — primarily the lineup from an OTA tuner such as an HDHomeRun — into a working XMLTV guide by:

1. Letting the user map each M3U channel to a guide source entry from the [iptv-org/epg](https://github.com/iptv-org/epg) project (a `site` + `site_id` + `xmltv_id`).
2. Writing a `channels.xml` file in the exact format consumed by `iptv-org/epg` (`npm run grab -- --channels=...`).
3. Running the `iptv-org/epg` grabber on a cron schedule against that file.
4. Serving the resulting `guide.xml` over HTTP so it can be consumed by Plex, Jellyfin, Channels DVR, etc.

The application ships as a single Docker image. `iptv-org/epg` is **not** vendored; it is cloned with `git` at runtime.

## 2. Glossary

| Term | Meaning |
| --- | --- |
| **Lineup** | A named M3U source (e.g. "Living room HDHomeRun") plus its mappings, `channels.xml`, grab settings and generated guide. |
| **M3U channel** | One `#EXTINF` entry from the uploaded/fetched playlist. |
| **Guide entry** | One `<channel>` element from a `sites/<site>/*.channels.xml` file in iptv-org/epg (or the local overlay). Identified by `site` + `site_id`. |
| **xmltv_id** | iptv-org stream ID, `<ChannelID>@<FeedID>` (e.g. `WCBSTV.us@SD`). Becomes the `<channel id>` in the guide. |
| **Mapping** | The association M3U channel → guide entry (or "skipped"). |
| **Overlay** | A user-mounted directory of site folders (same layout as `iptv-org/epg/sites`) that is merged into the epg checkout. Used to run and test sites that are not yet upstream. |
| **Sync** | `git clone`/`git pull` of iptv-org/epg, dependency install, API data refresh, overlay linking, and index rebuild. |
| **Grab** | Running `npm run grab` in the epg checkout for a lineup's `channels.xml`. |

## 3. Users and context

- Single household / homelab user on a **trusted LAN**. No authentication (see NFR-SEC-1).
- Primary device: HDHomeRun (US ATSC). Must not hard-code US assumptions — country/site filters are configurable.
- The user may develop new site configs outside the app and contribute them upstream; the app only needs to *consume* them (see §5.6).

## 4. Scope

### In scope (v1)

- Multiple named lineups.
- M3U input by file upload or by URL (re-fetchable).
- Auto-suggested matches with manual confirmation; manual search; manual entry.
- `channels.xml` generation per lineup, written to disk.
- Scheduled + on-demand grabbing via iptv-org/epg; per-lineup guide served over HTTP.
- Local site overlay.
- Look and feel aligned with [iptv-org.github.io](https://iptv-org.github.io) (light/dark).
- Dockerfile; all state on a single volume.

### Out of scope (v1) — recorded for later

- **FUT-1 — Rewritten M3U output.** Serve a copy of each lineup's M3U with `tvg-id` = mapped `xmltv_id` (plus `tvg-chno`, `tvg-logo`) so players that match by `tvg-id` line up with the guide. Design data model so this is a pure addition (mappings already keyed by M3U channel and contain `xmltv_id`).
- FUT-2 — Merged guide across lineups.
- FUT-3 — HDHomeRun discovery (`/discover.json`, `/lineup.json`) instead of M3U.
- FUT-4 — Authentication.
- FUT-5 — Per-lineup cron schedules.
- Developing/editing site configs inside the app (explicit non-goal; see §5.6).

## 5. Functional requirements

Priority: **MUST** / **SHOULD** / **COULD**.

### 5.1 Lineup management

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-L-1 | MUST | User can create a lineup with a display name. A URL-safe `slug` is derived from the name (unique; editable on create only). |
| FR-L-2 | MUST | Lineup list page shows, per lineup: name, channel count, mapped / skipped / unmapped counts, last grab time + result, guide URL with copy button. |
| FR-L-3 | MUST | User can rename and delete a lineup. Delete requires confirmation and removes its mappings, `channels.xml` and guide files. |
| FR-L-4 | MUST | Each lineup has filter settings used for suggestions: countries (default `us`), languages (optional), and an ordered list of preferred sites (e.g. `tvtv.us`, `zap2it.com`). |
| FR-L-5 | MUST | Each lineup can override grab options: `days`, `maxConnections`, `delay`, `timeout`, `gzip` (on/off), `enabled` (included in scheduled grabs). Unset values fall back to env defaults (§7). |

### 5.2 M3U input

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-M-1 | MUST | Upload an `.m3u`/`.m3u8` file when creating a lineup or to replace a lineup's source. |
| FR-M-2 | MUST | Alternatively provide a URL (e.g. `http://<hdhomerun-ip>/lineup.m3u`); the app fetches it server-side and stores the URL with the lineup. |
| FR-M-3 | MUST | Parse extended M3U: `#EXTINF:<duration> <attrs>,<title>` followed by the stream URL. Recognised attributes: `tvg-id`, `tvg-name`, `tvg-chno`, `tvg-logo`, `group-title`, `channel-id`, `channel-number`. Unknown attributes are preserved. Tolerate CRLF, BOM, blank lines, missing `#EXTM3U`. |
| FR-M-4 | MUST | Each M3U channel gets a stable **key** used to attach mappings: first non-empty of `channel-number` / `tvg-chno` / `channel-id` / `tvg-id`; else the stream URL; else the normalised title. Duplicate keys get a `#n` suffix and a warning. |
| FR-M-5 | MUST | Derive a **channel number** (`lcn`) for each channel: `channel-number` / `tvg-chno`, else a leading `\d+(\.\d+)?` in the title (HDHomeRun titles look like `2.1 WCBS-HD`). |
| FR-M-6 | MUST | Re-importing (re-upload or "Refresh from URL") preserves mappings for unchanged keys and shows a diff: added, removed, renamed channels. Removed channels' mappings are dropped only after user confirms. |
| FR-M-7 | SHOULD | Show parse warnings (skipped lines, duplicate keys) without failing the import. Reject files with zero channels. |
| FR-M-8 | COULD | Store the original M3U verbatim (needed for FUT-1). — *Treat as MUST in the data model; cheap and unblocks FUT-1.* |

### 5.3 Mapping

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-P-1 | MUST | Lineup editor lists all M3U channels sorted by channel number (natural sort, so `2.1 < 2.10 < 11.1`), showing number, logo (if any), name, status badge (Mapped / Suggested / Skipped / Unmapped) and the mapped guide entry (`site`, `site_id`, `xmltv_id`, entry name). |
| FR-P-2 | MUST | Filters: status, free-text search. Counts per status shown. |
| FR-P-3 | MUST | For each unmapped channel the app computes ranked **suggestions** (top 10) from the guide entry index, honouring lineup country/language/preferred-site settings. See §5.4. |
| FR-P-4 | MUST | Opening a channel shows a mapping panel/modal with: suggestions (score + why it matched), a search box over all guide entries (filterable by site, country, language), and a **Manual** tab (§5.5). User confirms one entry → status Mapped. |
| FR-P-5 | MUST | User can mark a channel **Skipped** (excluded from `channels.xml`) and can clear a mapping. |
| FR-P-6 | MUST | Every mapping change is persisted immediately (no separate "Save" step) and `channels.xml` is regenerated (§5.7). |
| FR-P-7 | SHOULD | Bulk action: "Accept top suggestion" for selected channels / all channels whose top score ≥ threshold; result shown for review, nothing is applied without a click. |
| FR-P-8 | SHOULD | Warn when two M3U channels map to the same `xmltv_id` (guide will contain one `<channel>` id; second number would be lost), and when a mapped entry no longer exists after a sync (stale mapping). |
| FR-P-9 | SHOULD | Show entry provenance badge: `upstream`, `overlay` (local site), `manual`. |
| FR-P-10 | COULD | Keyboard navigation in the editor (↑/↓ select channel, Enter open, 1–9 pick suggestion, S skip). |

### 5.4 Suggestion engine

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-S-1 | MUST | Build an in-memory index of all guide entries from `<epg>/sites/**/*.channels.xml` (including overlay sites) on startup and after each sync. Parse with `EPGGrabber.parseChannelsXML` from `epg-grabber` so semantics match the grabber. |
| FR-S-2 | MUST | Feature extraction from an M3U channel: normalised name (strip `-HD`, `-DT`, `-LD`, `-CD`, sub-channel suffixes, punctuation, case); US/CA/MX broadcast **call sign** (`^[KWCX][A-Z]{2,3}`) when present; channel number. |
| FR-S-3 | MUST | Scoring combines (weights configurable in code, documented in tests): exact call-sign match against the `xmltv_id` channel part or entry name; fuzzy name similarity; country match (from `xmltv_id` suffix, e.g. `.us`); preferred-site rank; entries with empty `xmltv_id` ranked lower. |
| FR-S-4 | MUST | Deterministic: same inputs → same ranked output. Covered by unit tests with fixture M3U + fixture `channels.xml` files. |
| FR-S-5 | SHOULD | Also use the iptv-org database (`@iptv-org/sdk` data loaded from the epg checkout's API data) to resolve channel display names / alt names for search and to validate `xmltv_id`s. |
| FR-S-6 | SHOULD | Suggestions for a 100-channel lineup computed in < 2 s on a Raspberry Pi 4 class machine. |

### 5.5 Manual entries

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-E-1 | MUST | Manual tab lets the user enter `site` (picker of known sites, upstream + overlay), `site_id` (free text), `lang` (ISO 639-1, default from lineup), and `xmltv_id` (free text with search-as-you-type against the iptv-org database channels + feeds). |
| FR-E-2 | MUST | Validate: `site` exists; `site_id` non-empty; `xmltv_id` matches `^[A-Za-z0-9]+\.[a-z]{2}(@[A-Za-z0-9]+)?$` or is empty. Warn (don't block) if `xmltv_id` is not in the database, or empty (epg falls back to `site_id` as the guide channel id). |
| FR-E-3 | SHOULD | Show a link to the iptv-org/epg channel-request form and iptv-org/database for missing channels, to encourage contributing upstream. |

### 5.6 Local site overlay

Concept: sites that are not (yet) in iptv-org/epg are developed **outside** this app (in a normal epg checkout using `npm run sites:init`, its tests, etc.) and dropped into a mounted volume. The app merely makes them available to the grabber and the suggestion index. Once they work, the user copies the folder into a fork of iptv-org/epg and opens a PR.

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-O-1 | MUST | Overlay directory (default `/data/sites`) uses upstream layout: `<site>/<site>.config.js` and `<site>/<site>.channels.xml` (more files allowed). |
| FR-O-2 | MUST | During sync, each overlay site folder is symlinked into `<epg>/sites/<site>` so it resolves epg's `node_modules` (site configs `require('dayjs')`, etc.) and is found by `grab` via `SITES_DIR`. |
| FR-O-3 | MUST | If an overlay site has the same name as an upstream site, the overlay wins; the upstream folder is moved aside for the duration (restored on next sync if overlay removed) and the conflict is shown in the UI. Sync must leave the git working tree restorable (`git status` clean after removing links / `git checkout -- sites`). |
| FR-O-4 | MUST | Overlay entries appear in the suggestion index with an `overlay` badge. |
| FR-O-5 | SHOULD | Status page lists overlay sites, conflicts and any load errors (e.g. config fails to `require`). |
| FR-O-6 | SHOULD | Document the overlay workflow in README (develop → mount → map → grab → contribute). |

### 5.7 channels.xml generation

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-X-1 | MUST | One file per lineup at `/data/lineups/<slug>/channels.xml`, regenerated on every mapping change and after sync. Written atomically (temp file + rename). |
| FR-X-2 | MUST | Format compatible with iptv-org/epg, attributes in this order: `<channel site="" site_id="" lang="" xmltv_id="" lcn="" [logo=""]>Display Name</channel>`, XML declaration `<?xml version="1.0" encoding="UTF-8"?>`, values escaped like epg's `escapeString`. |
| FR-X-3 | MUST | `lcn` = M3U channel number (FR-M-5) so the generated guide carries `<lcn>` for Plex channel-number matching. *(Verified: `epg-grabber` parses `lcn` and emits `<lcn>`; epg's own `generateChannelsXML` drops it, so do not reuse that helper. End-to-end `grab` run: [spikes/M1-lcn.md](spikes/M1-lcn.md).)* |
| FR-X-4 | MUST | Display name = M3U channel name (e.g. `WCBS-HD`), not the guide entry's name; this becomes `<display-name>` in the guide. |
| FR-X-5 | MUST | Only Mapped channels are written; order by channel number. |
| FR-X-6 | SHOULD | Download button for `channels.xml` in the UI; read-only preview. |
| FR-X-7 | SHOULD | Import an existing `channels.xml` into a lineup (match by `lcn` or display name) to migrate prior hand-made files. |

### 5.8 epg checkout sync

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-G-1 | MUST | On container start, if `<epg>` (default `/data/epg`) is absent: `git clone --depth 1 -b $EPG_BRANCH $EPG_REPO`. |
| FR-G-2 | MUST | Before each scheduled grab run, and on "Sync now": `git fetch --depth 1` + hard reset to `origin/$EPG_BRANCH` (overlay links removed first, re-applied after). |
| FR-G-3 | MUST | Run `npm ci --ignore-scripts` in `<epg>` when `package-lock.json` changed (hash stored), then `npm run api:load` to refresh iptv-org database files. |
| FR-G-4 | MUST | Rebuild guide-entry index; mark mappings whose entry disappeared as stale (FR-P-8); regenerate all `channels.xml`. |
| FR-G-5 | MUST | Record sync status: commit SHA, time, duration, result, log tail. A failed sync leaves the previous checkout usable (grab proceeds with last good checkout and logs a warning). |
| FR-G-6 | SHOULD | `EPG_REF` env pins a tag/commit instead of tracking the branch. |

### 5.9 Grab & guide serving

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-R-1 | MUST | Scheduled run on `CRON_SCHEDULE` (default `0 0 * * *`): sync, then grab every enabled lineup sequentially. Optional run at startup (`RUN_AT_STARTUP`, default `true`), modelled on iptv-org/epg's `pm2.config.js` (pm2 + `chronos`). |
| FR-R-2 | MUST | Grab = in `<epg>`: `npm run grab --- --channels=<lineup channels.xml> --output=<tmp> [--days --maxConnections --delay --timeout --gzip]`; on success, atomically move into `/data/guides/<slug>.xml` (+ `.xml.gz`). A failed grab never replaces the last good guide. |
| FR-R-3 | MUST | Only one run at a time (file lock in `/data`); "Grab now" (all or one lineup) from the UI is rejected with a message if a run is in progress. |
| FR-R-4 | MUST | Child processes get a sanitised environment (no leakage of this app's vars into epg; epg itself reads `DATA_DIR`, `SITES_DIR`, `ROOT_DIR`, etc.). |
| FR-R-5 | MUST | Serve guides at `GET /guides/<slug>.xml` and `GET /guides/<slug>.xml.gz` with correct `Content-Type`, `Last-Modified`, `ETag`, and `HEAD` support; 404 until the first successful grab. |
| FR-R-6 | MUST | Per-lineup run history (last 20): start, end, result, channel count, program count, log file. Log viewer in UI (tail). |
| FR-R-7 | SHOULD | Live progress in UI while a grab runs (polling or SSE of `[i/total]` lines from epg output). |

### 5.10 UI / look and feel

| ID | Pri | Requirement |
| --- | --- | --- |
| FR-U-1 | MUST | Visual language of iptv-org.github.io: Tailwind v4, the `primary-*` HSL(219°, 23%) palette, `#f8fafc` / `primary-850` nav bar, `bg-white` / `dark:bg-primary-810` rounded-md cards, gray-500/400 text, pill badges, icon buttons, toasts bottom-left. See [STYLE.md](STYLE.md). |
| FR-U-2 | MUST | Class-based dark mode with toggle, persisted in `localStorage.theme`, defaulting to `prefers-color-scheme`, applied before paint (inline head script as in the site's `+layout.svelte`). |
| FR-U-3 | MUST | Responsive down to 375 px width; editor table collapses to cards on small screens. |
| FR-U-4 | MUST | Own wordmark "epg-editor" (do **not** reuse the iptv-org logo as this app's brand); footer credit "Guide data and tools by iptv-org" with links. |
| FR-U-5 | SHOULD | Accessible: keyboard operable, focus visible, labels on icon buttons (`title`/`aria-label`), contrast AA in both themes. |

Pages:

| Route | Purpose |
| --- | --- |
| `/` | Lineup list (FR-L-2), "New lineup", global "Grab now", sync status summary. |
| `/lineups/new` | Name + M3U upload/URL + filter settings. |
| `/lineups/[slug]` | Mapping editor (5.3). |
| `/lineups/[slug]/settings` | Filters, grab overrides, M3U source / refresh, delete. |
| `/lineups/[slug]/runs` | Run history + logs. |
| `/status` | epg checkout (SHA, branch, last sync), overlay sites & conflicts, index stats, "Sync now". |
| `/guides/[slug].xml(.gz)` | Guide files (FR-R-5). |

## 6. Non-functional requirements

| ID | Requirement |
| --- | --- |
| NFR-DEP-1 | Single Docker image based on `node:22-alpine` (same as iptv-org/epg), includes `git`. One exposed port (default `3000`). |
| NFR-DEP-2 | All mutable state lives under one volume `/data` (lineups, guides, epg checkout, overlay, logs). Container is otherwise disposable. |
| NFR-DEP-3 | First start (clone + install + API load) may take several minutes; UI must be reachable during it and show an "initialising" state. |
| NFR-DEP-4 | Runs as non-root user; `/data` ownership documented (`PUID`/`PGID` not required in v1). |
| NFR-DEP-5 | Works on `linux/amd64` and `linux/arm64`. |
| NFR-SEC-1 | No authentication. README states it is for trusted networks only and must not be exposed to the internet. |
| NFR-SEC-2 | URL fetch (FR-M-2) limited to `http`/`https`, 10 s timeout, 5 MB max body. Upload limit 5 MB. |
| NFR-SEC-3 | Slugs and site names validated (`^[a-z0-9][a-z0-9.-]*$`) before use in paths; no path traversal in `/guides/*`. |
| NFR-SEC-4 | Child processes spawned with argument arrays (no shell interpolation of user input). |
| NFR-REL-1 | All writes of user data are atomic (temp + rename). Corrupt/missing JSON for one lineup must not break others. |
| NFR-REL-2 | A crashed web process or grab is restarted by pm2; the lock is released on process exit / considered stale after a timeout. |
| NFR-PERF-1 | Index of all upstream guide entries (~100k+) built in < 30 s and held in memory; memory footprint of the web process < 512 MB. |
| NFR-MAINT-1 | Code style matches iptv-org conventions (see [STYLE.md](STYLE.md)); `npm run lint`, `npm run check`, `npm test` pass in CI. |
| NFR-MAINT-2 | Unit tests for M3U parsing, key/number derivation, suggestion scoring, `channels.xml` generation, overlay linking, lineup store. Fixtures under `tests/__data__/{input,expected}` (iptv-org convention). |
| NFR-COMPAT-1 | Generated `channels.xml` must be accepted by the pinned/current iptv-org/epg `grab` command — verified by an integration test that runs `grab` against a fixture site (or `--days=1` against a local mock). |

## 7. Configuration (environment variables)

Names deliberately avoid iptv-org/epg's own env vars (`DATA_DIR`, `SITES_DIR`, `ROOT_DIR`, `GUIDES_DIR`, `API_DIR`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `3000` | HTTP port (adapter-node). |
| `ORIGIN` | — | Public origin, required by SvelteKit adapter-node for form actions (e.g. `http://nas.local:3000`). |
| `BODY_SIZE_LIMIT` | `5M` | adapter-node request size limit (uploads). |
| `STORAGE_DIR` | `/data` | Root of all state. |
| `OVERLAY_DIR` | `$STORAGE_DIR/sites` | Local site overlay. |
| `EPG_REPO` | `https://github.com/iptv-org/epg.git` | Git URL. |
| `EPG_BRANCH` | `master` | Branch to track. |
| `EPG_REF` | — | Optional tag/commit pin. |
| `CRON_SCHEDULE` | `0 0 * * *` | Scheduled run. |
| `RUN_AT_STARTUP` | `true` | Run sync + grab on start. |
| `GRAB_DAYS` | (site default) | Default `--days`. |
| `GRAB_MAX_CONNECTIONS` | `1` | Default `--maxConnections`. |
| `GRAB_DELAY` | `0` | Default `--delay` (ms). |
| `GRAB_TIMEOUT` | `30000` | Default `--timeout` (ms). |
| `GRAB_GZIP` | `true` | Also write `.xml.gz`. |
| `TZ` | `UTC` | Cron and display timezone. |

## 8. Acceptance criteria (v1 "done")

1. `docker run -p 3000:3000 -v epg-data:/data -e ORIGIN=http://localhost:3000 epg-editor` starts, clones iptv-org/epg, and shows the lineup list.
2. Uploading an HDHomeRun `lineup.m3u` creates a lineup listing every channel with its number.
3. For a typical US OTA lineup, ≥ 70 % of channels have the correct entry among the top 3 suggestions (measured on the fixture lineup in tests).
4. Mapping channels writes `/data/lineups/<slug>/channels.xml` that `npm run grab -- --channels=...` in a plain iptv-org/epg checkout accepts without error.
5. "Grab now" produces `/guides/<slug>.xml`; adding it as an XMLTV source in Plex shows guide data for mapped channels.
6. Dropping a site folder into `/data/sites` and clicking "Sync now" makes its entries searchable and grabbable.
7. Light and dark themes visually consistent with iptv-org.github.io.

## 9. Open questions

- **OQ-1** — Need a real HDHomeRun `lineup.m3u` sample (sanitised) for fixtures; attribute names in FR-M-3 are based on common HDHomeRun / IPTV conventions and must be confirmed against it. *Resolved 2026-10-18: checked against a real `lineup.m3u` from an HDHR5-4K (firmware `hdhomerun5_atsc3` 20260326, 73 channels incl. ATSC 3.0). Every entry is `#EXTINF:-1 channel-id="N" channel-number="N" tvg-name="Name",N Name`, followed by `http://<ip>:5004/auto/vN`. No `tvg-id`, `tvg-chno`, `tvg-logo` or `group-title`; LF line endings, no BOM. The fixture `tests/__data__/input/m3u/hdhomerun.m3u` uses this format.*
- **OQ-2** — Confirm Plex matches XMLTV channels to tuner channels via `<lcn>` / numeric display name for HDHomeRun DVR; if not, consider emitting the number as an extra `<display-name>` (would require a post-process step since epg-grabber writes a single display-name).
- **OQ-3** — Some upstream US sites (e.g. `tvtv.us`) hard-code a lineup ID in their config URL. Check whether OTA station `site_id`s work regardless of lineup; if not, overlay copies of those sites may be needed (document in README).
