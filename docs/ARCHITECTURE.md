# epg-editor — Architecture

Companion to [REQUIREMENTS.md](REQUIREMENTS.md). Requirement IDs in brackets.

## 1. Overview

```
                     ┌──────────────────────────── container (node:22-alpine) ───────────────────────────┐
 Browser ──HTTP──►   │  pm2-runtime                                                                      │
 Plex   ──GET /guides│   ├─ web        node build  (SvelteKit adapter-node, port 3000)                   │
                     │   │   ├─ UI routes + form actions + /api/* endpoints                              │
                     │   │   ├─ in-memory GuideIndex (all sites/*.channels.xml + iptv-org database)      │
                     │   │   └─ serves /data/guides/*.xml(.gz)                                           │
                     │   ├─ scheduler  chronos -e "npm run run:all" -p $CRON_SCHEDULE                    │
                     │   ├─ init       npm run run:sync  (only if /data/epg missing)                     │
                     │   └─ startup    npm run run:all            (only if RUN_AT_STARTUP=true)          │
                     │                                                                                   │
                     │  npm run run:all  (tsx src/commands/run/all.ts)                                   │
                     │     1. acquire /data/run.lock                                                     │
                     │     2. sync  : git fetch/reset /data/epg → npm ci (if lock changed) → api:load    │
                     │                → link overlay /data/sites/* into /data/epg/sites/                 │
                     │     3. for each enabled lineup:                                                   │
                     │          spawn (cwd /data/epg) npm run grab --- --channels=… --output=…           │
                     │          → atomic move to /data/guides/<slug>.xml(.gz)                            │
                     │     4. write status files, release lock                                           │
                     └───────────────────────────────────────────────────────────────────────────────────┘
```

The structure deliberately mirrors iptv-org/epg's own container (`pm2.config.js` with `chronos` + an optional startup run) [FR-R-1], with SvelteKit replacing `serve`.

**Why commands run as separate processes:** grab runs are long (minutes to hours), memory-hungry, and must survive web restarts. The web process never runs a grab in-process; "Grab now" / "Sync now" spawn the same command detached (`npm run run:all -- --lineup=<slug>` / `npm run run:sync`) and the lock makes them mutually exclusive with the scheduler [FR-R-3].

**How the web process learns about a sync:** the command writes `/data/status/sync.json` (incl. commit SHA). The web process checks its mtime on request (cheap `stat`, throttled) and rebuilds `GuideIndex` when it changes [FR-G-4]. No IPC needed.

## 2. Volume layout [NFR-DEP-2]

```
/data
├── epg/                          # git clone of iptv-org/epg (+ its node_modules, temp/data API json)
│   └── sites/<site> -> /data/sites/<site>   # overlay symlinks (created by sync)
├── sites/                        # OVERLAY: user-mounted local site folders [5.6]
│   └── example.com/{example.com.config.js, example.com.channels.xml, …}
├── lineups/
│   └── <slug>/
│       ├── lineup.json           # metadata + settings
│       ├── source.m3u            # original playlist, verbatim [FR-M-8]
│       ├── mappings.json         # key → mapping
│       └── channels.xml          # generated [5.7]
├── guides/
│   ├── <slug>.xml
│   └── <slug>.xml.gz
├── status/
│   ├── sync.json                 # last sync result, SHA, lockfile hash, overlay report
│   ├── epg-source-override.json  # optional { repo, ref } from /status, overrides EPG_* env [FR-G-7]
│   ├── current.json              # step/lineup of the run holding run.lock (removed when it ends)
│   └── runs/<slug>.json          # last 20 runs
├── logs/
│   ├── sync-<ts>.log
│   └── grab-<slug>-<ts>.log      # kept while its run is in runs/<slug>.json (last 20)
├── .epg-sites-shadow/            # upstream site folders moved aside by overlay conflicts [FR-O-3]
└── run.lock
```

## 3. Data model (TypeScript)

```ts
// lineup.json
interface LineupData {
  slug: string
  name: string
  source: { type: 'upload' | 'url'; url?: string; importedAt: string }
  filters: { countries: string[]; languages: string[]; preferredSites: string[] }
  grab: { enabled: boolean; days?: number; maxConnections?: number; delay?: number; timeout?: number; gzip?: boolean }
  createdAt: string
  updatedAt: string
}

// parsed from source.m3u (not persisted separately)
interface PlaylistItemData {
  key: string               // FR-M-4
  number: string | null     // FR-M-5 → lcn
  name: string
  url: string
  logo: string | null
  group: string | null
  attributes: Record<string, string>
}

// mappings.json  →  { version: 1, items: Record<key, MappingData> }
interface MappingData {
  status: 'mapped' | 'skipped'
  guide?: {
    site: string
    site_id: string
    lang: string | null
    xmltv_id: string        // iptv-org id; channels.xml gets the guide id <slug>.<key> [FR-X-8]
    name: string            // entry name from channels.xml, for display only
    origin: 'upstream' | 'overlay' | 'manual'
  }
  stale?: boolean           // entry vanished after sync [FR-P-8]
  updatedAt: string
}

// in-memory index entry
interface GuideEntry {
  site: string
  site_id: string
  lang: string | null
  xmltv_id: string
  name: string
  logo: string | null
  country: string | null    // derived from xmltv_id suffix
  origin: 'upstream' | 'overlay'
}
```

"Unmapped" and "Suggested" are not persisted: a channel without a mapping is unmapped; suggestions are computed on demand.

Classes follow the iptv-org pattern of thin model classes with `toObject()` / `toJSON()` and use `Collection` / `Dictionary` from `@freearhey/core`.

## 4. Source tree

Mirrors iptv-org.github.io (`src/lib/{components,icons,actions,types,…}`, `src/commands`) with SvelteKit's `$lib/server` for server-only code.

```
.
├── CLAUDE.md
├── Dockerfile  .dockerignore  .github/workflows/{ci,release}.yml
├── docker-entrypoint.sh          # ensures /data dirs, then exec pm2-runtime
├── pm2.config.cjs
├── package.json  .npmrc (engine-strict=true)  .prettierrc  eslint.config.js
├── svelte.config.js  vite.config.js  tsconfig.json
├── docs/
├── src/
│   ├── app.html  app.css  app.d.ts  hooks.server.ts
│   ├── commands/                 # tsx CLI entry points (commander), run by pm2/chronos/UI
│   │   ├── run/all.ts            # lock → sync → grab lineups
│   │   ├── run/sync.ts           # lock → sync only
│   │   └── lineups/export.ts     # (dev aid) print channels.xml for a lineup
│   ├── lib/
│   │   ├── components/           # Svelte components, one folder each + index.ts barrel
│   │   │   ├── Common/           # Button, Card, Badge, IconButton, Modal, SearchField, Checkbox,
│   │   │   │                     # CopyToClipboard, CodeBlock (ported from iptv-org.github.io)
│   │   │   ├── NavBar/
│   │   │   ├── LineupCard/
│   │   │   ├── ChannelTable/ ChannelRow/
│   │   │   ├── MappingModal/     # Suggestions / Search / Manual tabs
│   │   │   ├── RunLog/  RunResultBadge/  JobButton/
│   │   │   ├── GuideGrid/        # episode guide viewer's channel × time grid [5.10]
│   │   │   └── index.ts
│   │   ├── icons/                # one Svelte SVG per icon, `size` prop (site convention)
│   │   ├── actions/              # clickOutside, tippy
│   │   ├── types/                # *.d.ts
│   │   ├── darkMode.svelte.ts  modal.svelte.ts  constants.ts  api.ts (browser /api client)
│   │   ├── jobs.svelte.ts        # running sync/grab state, polls /api/jobs [FR-R-3]
│   │   ├── core/                 # pure, isomorphic, fully unit-tested
│   │   │   ├── playlistParser.ts     # M3U → PlaylistItem[] [5.2]
│   │   │   ├── channelsXml.ts        # Mapping[] → channels.xml string [5.7]
│   │   │   ├── matcher.ts            # features + scoring [5.4]
│   │   │   ├── slug.ts               # slugify + NFR-SEC-3 slug check
│   │   │   ├── xmltvId.ts            # xmltv_id format + country suffix
│   │   │   ├── staleMappings.ts      # mark mappings whose entry vanished [FR-P-8]
│   │   │   ├── channelRows.ts        # editor rows + per-status counts [FR-P-1, FR-L-2]
│   │   │   ├── playlistDiff.ts       # re-import diff: added / removed / renamed [FR-M-6]
│   │   │   ├── mappingValidation.ts  # manual entry checks + mapping request shape [FR-E-2]
│   │   │   ├── formValues.ts         # list / optional-integer form fields
│   │   │   ├── guideFile.ts          # /guides file names, ETag, conditional requests [FR-R-5]
│   │   │   ├── epgGuide.ts           # parsed guide + current mappings → grid view-model [5.10]
│   │   │   ├── formatDuration.ts     # run durations for the UI
│   │   │   └── escapeString.ts       # port of epg's escapeString
│   │   ├── models/               # Lineup, PlaylistItem, Mapping, GuideEntry
│   │   └── server/               # server-only (Node fs, child_process)
│   │       ├── config.ts             # env parsing with defaults [§7]
│   │       ├── storage.ts            # atomic JSON/text read/write under STORAGE_DIR
│   │       ├── lineupStore.ts        # CRUD over /data/lineups; per-lineup write queue
│   │       ├── fetchPlaylist.ts      # M3U URL fetch with NFR-SEC-2 limits
│   │       ├── playlistInput.ts      # M3U from a form (upload or URL)
│   │       ├── guideIndex.ts         # build/search index; reload on sync.json change
│   │       ├── database.ts           # @iptv-org/sdk DataManager over /data/epg/temp/data
│   │       ├── epgRepo.ts            # clone/fetch/reset/npm ci/api:load
│   │       ├── epgSource.ts          # /status repo/branch override: read/save/clear, git ls-remote validation [FR-G-7]
│   │       ├── overlay.ts            # link/unlink overlay sites, conflict handling
│   │       ├── sync.ts               # sync orchestration, shared by run:sync and run:all
│   │       ├── grabRunner.ts         # build args, spawn, capture log, atomic publish
│   │       ├── runAll.ts             # sync + grab enabled lineups, shared by run:all
│   │       ├── runHistory.ts         # status/runs/<slug>.json, log tail, status/current.json
│   │       ├── spawn.ts              # nano-spawn with argument arrays + sanitised env
│   │       ├── runLog.ts             # per-run log file under /data/logs + tail + rotation
│   │       ├── lock.ts               # run.lock via proper-lockfile (mtime-based stale detection)
│   │       ├── jobs.ts               # spawn detached commands from the web process
│   │       └── services.ts           # web-process singletons: lineups, index, matcher, database
│   └── routes/
│       ├── +layout.svelte  +page.svelte  +page.server.ts
│       ├── lineups/new/
│       ├── lineups/[slug]/{+page,settings,settings/reimport,runs}/
│       ├── lineups/[slug]/channels.xml/+server.ts   # preview / ?download [FR-X-6]
│       ├── status/
│       ├── guides/[file]/+server.ts       # FR-R-5
│       └── api/
│           ├── lineups/[slug]/suggestions/+server.ts   # GET ?key=
│           ├── lineups/[slug]/mappings/+server.ts      # PUT/DELETE single mapping
│           ├── entries/+server.ts                      # GET ?q=&site=&country=&lang=
│           ├── database/+server.ts                     # GET ?q= (xmltv_id autocomplete)
│           └── jobs/+server.ts                         # POST sync|grab, GET status (poll)
├── static/                        # favicon, icon.svg (own mark)
└── tests/
    ├── __data__/input/  __data__/expected/
    ├── core/*.test.ts             # vitest
    └── server/*.test.ts
```

Writes from forms use SvelteKit **form actions** (progressive enhancement); interactive per-channel operations (suggestions, map/skip) use small JSON endpoints under `/api`.

## 5. Key flows

### 5.1 Create lineup / import M3U
1. Form action receives name + file or URL → fetch (NFR-SEC-2 limits) → `playlistParser.parse()`.
2. Reject if 0 items; collect warnings.
3. `lineupStore.create()` writes `lineup.json`, `source.m3u`, empty `mappings.json`, empty `channels.xml`.
4. Redirect to editor.

Re-import: parse new playlist → keep it in `lineups/<slug>/pending-source.json` → diff by `key` against current on `/lineups/<slug>/settings/reimport` → on confirm, write `source.m3u`, drop mappings of removed keys (only when the user ticks that), regenerate `channels.xml` [FR-M-6].

### 5.2 Map a channel
1. Editor loads lineup + items + mappings (+page.server.ts).
2. Opening a row → `GET /api/lineups/<slug>/suggestions?key=…` → `matcher.suggest(item, guideIndex, lineup.filters)`.
3. Confirm → `PUT /api/lineups/<slug>/mappings` with `{ key, status: 'skipped' }`, `{ key, status: 'mapped', entry: { site, site_id } }` (copied from the index, so only existing entries can be saved) or `{ key, status: 'mapped', manual: { site, site_id, lang, xmltv_id } }` (validated, FR-E-2; 422 with field errors) → write `mappings.json` → regenerate `channels.xml` → return updated row. `DELETE ?key=` clears a mapping. Writes to one lineup are queued in-process so concurrent edits don't overwrite each other.

### 5.3 Sync [5.8]
Implemented in `server/sync.ts`; the caller holds `run.lock`.

0. Resolve the repo/branch to check out: `status/epg-source-override.json` if one is saved, else `EPG_REPO`/`EPG_BRANCH`/`EPG_REF` (`server/epgSource.ts`, `resolveEpgConfig`) [FR-G-7]. Every entry point (startup, scheduler, "Sync now", "Save & sync") goes through this, so only one source is ever checked out.
1. Remove overlay links, restore shadowed upstream folders.
2. First run: `git init` a temp dir next to `/data/epg`, then the fetch below, then rename into place (a failed clone leaves nothing; init + fetch lets `EPG_REF` be a commit). Later runs: `git remote set-url origin $EPG_REPO`, then `git fetch --depth 1 origin <branch|ref>` → `git reset --hard FETCH_HEAD` → `git clean -fd -- sites` (only `sites/`; never touch `node_modules`/`temp`).
3. If sha256(`package-lock.json`) ≠ stored, or `node_modules` is missing → `npm ci --ignore-scripts`. If that fails, `git reset --hard` back to the previous commit and `npm ci` again, so the last good checkout keeps working.
4. `npm run api:load` (refresh database JSON into `temp/data`). If it fails but `temp/data` exists, keep the old data with a warning.
5. Apply overlay: for each `/data/sites/<site>` → if `/data/epg/sites/<site>` exists, move it to `/data/.epg-sites-shadow/` → symlink.
6. Load `GuideIndex` and the database; mark stale mappings and regenerate every lineup's `channels.xml` [FR-G-4].
7. Write `status/sync.json` (sha, times, overlay report, index/database counts, log tail) last. Steps 5–6 run even when 2–4 failed, against the previous checkout.

A fresh epg checkout is never `git status`-clean: upstream commits CRLF blobs under `eol=crlf` attributes ([spikes/M2-overlay-symlinks.md](spikes/M2-overlay-symlinks.md)).

### 5.4 Grab [5.9]
For each enabled lineup with ≥1 mapped channel:
```
spawn('npm', ['run', 'grab', '---',
  '--channels', <abs channels.xml>,
  '--output',   <tmp>/<slug>.xml,
  ...overrides, ...(gzip ? ['--gzip'] : [])],
  { cwd: '/data/epg', env: sanitizedEnv({ NODE_PRESERVE_SYMLINKS: '1' }) })
```
`NODE_PRESERVE_SYMLINKS=1` is required: without it, symlinked overlay configs resolve `require()` from `/data/sites` and can't find epg's `node_modules` ([spikes/M2-overlay-symlinks.md](spikes/M2-overlay-symlinks.md)).
The temp output dir is `/data/guides/.tmp-<slug>-<uuid>/`, on the same filesystem, so publishing is a `rename`. Pipe stdout/stderr to the run log; on exit 0 with at least one `<channel>` and one `<programme>` → `rename` `.xml.gz` then `.xml` into `/data/guides/` (an old `.xml.gz` is removed when gzip is off). epg exits 0 even when every request failed, so an empty guide counts as a failed run and the last good guide stays. Record the run in `status/runs/<slug>.json`; dropping a run past the 20th deletes its log. Live `[i/total]` progress is FR-R-7 (M7).

A lineup with no mapped channels is recorded as `skipped`. `run:all --lineup=<slug>` ("Grab now") grabs that lineup even when scheduled grabs are off for it.

### 5.5 Jobs and scheduling
- `pm2.config.cjs` runs every app in fork mode. The `scheduler` app runs `@freearhey/chronos` with `npm run run:all`. Like epg's own setup, chronos sends SIGINT to a run that is still going when the next tick fires, so `CRON_SCHEDULE` must leave room for a full run.
- "Grab now" / "Sync now" → `POST /api/jobs` → `jobs.ts` spawns `npm run run:all -- --lineup=<slug>` / `npm run run:sync` detached, then waits until the command holds `run.lock` (or has exited) before answering. A 409 means another run holds the lock. The `web` app has `treekill: false` so these runs survive a web restart.
- While the lock is held, the command keeps `status/current.json` up to date (`sync` or `grab` + lineup). `GET /api/jobs` returns `{ running, current }`; the UI polls it and reloads its data when the run ends.
- "Save & sync" / "Reset to default" on `/status` [FR-G-7]: form actions validate (`git ls-remote`) and persist/clear `status/epg-source-override.json`, then the client calls the same "Sync now" job (`POST /api/jobs`) — no separate run path.

## 6. Reuse from upstream (do not reinvent)

| Need | Use |
| --- | --- |
| Parse `*.channels.xml` | `EPGGrabber.parseChannelsXML` (`epg-grabber`, same version range as epg) |
| iptv-org database (channels, feeds, alt names) | `@iptv-org/sdk` `DataManager({ dataDir }).loadFromDisk()` pointed at `/data/epg/temp/data` (epg's `api:load` already downloads it) |
| Search index | `minisearch` for matcher candidates, the entry Search tab and `xmltv_id` autocomplete. epg's `searchChannels` uses `@freearhey/search-js`, which filters without ranking and is too slow over ~180k guide entries (FR-S-6). Final ranking is `matcher.ts`'s own scoring |
| Collections, logging | `@freearhey/core` (`Collection`, `Dictionary`, `Logger`) |
| CLI parsing | `commander` |
| Cron | `@freearhey/chronos` (as epg's `pm2.config.js`) |
| Process manager | `pm2` / `pm2-runtime` |
| XML escaping | port of epg's `escapeString` (keep identical behaviour, with test). `epg-grabber` has a copy but doesn't export it; generic XML builders don't strip invalid characters or collapse whitespace the way epg does |
| M3U parsing | `@iptv/playlist`, behind a line filter in `playlistParser.ts` that works around an infinite loop on malformed input ([upstream/iptv-playlist-infinite-loop.md](upstream/iptv-playlist-infinite-loop.md)) |
| Run lock | `proper-lockfile` (atomic mkdir; stale when the holder stops refreshing its mtime, so PID reuse after a container restart can't wedge it) |
| Child processes | `nano-spawn` with argument arrays; `spawn.ts` blanks inherited env vars so only the allow-list reaches epg [FR-R-4]. git runs as the CLI through the same helper (no `simple-git`) |
| Atomic writes | `write-file-atomic` (temp file + fsync + rename). `@freearhey/storage-js` writes in place, so it isn't used for writes |
| Slugs | `slugify` (`strict`, lower-case), then checked against the NFR-SEC-3 pattern |
| UI components | port from iptv-org.github.io `src/lib/components/Common` + icons (public domain / Unlicense) |
| Toasts | `@zerodevx/svelte-toast` with the site's options |
| Natural sort | `natural-orderby` (used by the site) for UI lists. Channel numbers use `compareChannelNumbers` in `channelsXml.ts`, because natural-orderby sorts `2.10` before `2.1` |

The interactive CLI `scripts/commands/channels/edit.ts` in iptv-org/epg is the closest existing equivalent of this app's mapping flow (search → pick channel → pick feed); the UI should follow the same two-step channel → feed concept for manual `xmltv_id` selection.

## 7. Docker

See [`Dockerfile`](../Dockerfile). Two stages on `node:22-alpine`: the build stage runs `npm ci`, `npm run build` and `npm prune --omit=dev`; the runtime stage adds `git`, `tzdata`, `tini` and `su-exec` and copies `node_modules`, `build/`, `src/` and the tsconfig chain (`tsconfig.json` + `.svelte-kit/tsconfig.json`), because the commands run from source with `tsx`. It has `/data` as a volume, a `wget` health check on `/`, and `tini` → `docker-entrypoint.sh` → `pm2-runtime pm2.config.cjs`. The image starts as root: the entrypoint sets the `node` user's uid/gid to `PUID`/`PGID` (default 1000) and re-runs itself as `node` with `su-exec`, so the app never runs as root [NFR-DEP-4]. Started with `--user`, it skips that step and warns if `PUID`/`PGID` are set. It never chowns `/data`; it exits with a `chown` hint when `/data` isn't writable, and warns when `ORIGIN` is unset. CI builds `linux/amd64` and `linux/arm64` [NFR-DEP-5]; a `v<version>` tag matching `package.json` publishes both to `ghcr.io` as `<version>` and `latest` (`release.yml`).

Runtime dependencies needed in the final image (keep in `dependencies`, not `devDependencies`): `pm2`, `@freearhey/chronos`, `tsx`, `commander`, `@freearhey/core`, `epg-grabber`, `@iptv-org/sdk`. The first clone/install happens in a pm2 `init` app (always registered, `autorestart: false`, runs `npm run run:sync` only when `/data/epg` is missing), not in the entrypoint, so the web UI is reachable immediately and shows "initialising" [NFR-DEP-3]. The web process treats a missing `/data/epg` or `status/sync.json` as "not ready". When `RUN_AT_STARTUP=true` the `startup` app runs `run:all` instead (which syncs anyway); the lock serialises them.

## 8. Testing strategy

- **Unit (vitest):** `core/*` pure functions with fixtures in `tests/__data__/input` → `expected` (iptv-org convention). Matcher tests assert top-N for a fixture OTA lineup against fixture `channels.xml` files.
- **Server:** `lineupStore`, `overlay`, `lock`, `grabRunner` arg building — using a temp `STORAGE_DIR`.
- **Integration (opt-in, `npm run test:integration`, own `vitest.integration.config.js`):** clone epg at a pinned ref (`INTEGRATION_EPG_REF`, default the M1 spike commit; `INTEGRATION_EPG_REPO` can point at a local clone) into a temp dir, add an overlay site whose config fetches canned programs from a local HTTP server (and `require`s `dayjs` through the symlink), run `run:all`, assert guide XML contains `<lcn>` and expected channel ids.
- **Lint/type:** `npm run lint`, `npm run check` (svelte-check).
