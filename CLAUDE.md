# CLAUDE.md

## What this is

`epg-editor` is a self-hosted SvelteKit web app (Docker). It does four things:

1. Imports an IPTV `.m3u` file (mainly an HDHomeRun OTA lineup).
2. Lets the user map each channel to a guide entry from [iptv-org/epg](https://github.com/iptv-org/epg).
3. Writes a `channels.xml` file per lineup.
4. Runs iptv-org/epg's `grab` on a cron schedule and serves the resulting `guide.xml` to Plex and similar clients.

iptv-org/epg is **cloned with git at runtime** into the data volume. It is never vendored or added as an npm dependency.

Read these before working on a feature:
- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md): what to build. Requirement IDs (FR-x, NFR-x) are referenced in code comments and commits only where useful.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): processes, the `/data` layout, the data model, the source tree and the reuse table.
- [docs/STYLE.md](docs/STYLE.md): code and UI conventions copied from the iptv-org projects.
- [docs/ROADMAP.md](docs/ROADMAP.md): milestone order. Finish and test one milestone before starting the next.

## Stack

SvelteKit 2 + `@sveltejs/adapter-node`, Svelte 5 (runes only), TypeScript (strict), Tailwind CSS v4, Vitest, ESLint flat config, Prettier.

Server side: `@freearhey/core`, `epg-grabber`, `@iptv-org/sdk`, `commander`, `tsx`, `pm2`, `@freearhey/chronos`. These are the same libraries iptv-org/epg uses. Prefer them over new dependencies.

## Commands

```sh
npm run dev          # vite dev server
npm run build        # production build (adapter-node → build/)
npm run check        # svelte-check / type check
npm run lint         # eslint
npm run format       # prettier --write
npm test             # vitest run
npm run test:integration  # opt-in: real epg clone + grab against a mock overlay site (network)
npm run run:sync     # tsx src/commands/run/sync.ts: clone/pull epg, install, link overlay
npm run run:all      # tsx src/commands/run/all.ts: sync + grab all enabled lineups
```

For local dev, set `STORAGE_DIR=./dev-data` so nothing writes to `/data`.

## Rules

- **Style:** follow docs/STYLE.md. In short: no semicolons, single quotes, 100 columns, no trailing commas, `arrowParens: avoid`, LF line endings. Use Svelte 5 runes with `interface Props`, snippets and `onX` callback props. When the two upstream repos disagree, iptv-org.github.io wins.
- **Look and feel:** reuse the iptv-org.github.io palette (`primary-*`, hsl 219° 23%), card, badge and nav patterns, and class-based dark mode. Don't use the iptv-org logo as our brand.
- **channels.xml format:** `<channel site="" site_id="" lang="" xmltv_id="" lcn="">M3U name</channel>`. Always include `lcn` (the channel number), because Plex needs it. Don't call epg's `generateChannelsXML`, since it drops `lcn`. Parse `channels.xml` files with `EPGGrabber.parseChannelsXML` from `epg-grabber`.
- **Env var names:** never reuse iptv-org/epg's env var names (`DATA_DIR`, `SITES_DIR`, `ROOT_DIR`, `GUIDES_DIR`, `API_DIR`). Our root dir is `STORAGE_DIR`. Spawn epg child processes with a sanitised env and argument arrays, never shell strings.
- **Grabs:** they always run in a separate process (`src/commands`) under `/data/run.lock`, never inside the web server process.
- **Writes:** every write of user data is atomic (write a temp file, then rename). A failed grab or sync must never replace the last good guide or checkout.
- **Overlay sites:** local sites in `/data/sites/<site>` get symlinked into `/data/epg/sites/` so they can resolve epg's `node_modules`. The app does not author site configs, which is an explicit non-goal.
- **Code layout:** pure logic goes in `src/lib/core/` with unit tests and fixtures under `tests/__data__/{input,expected}`. Node-only code goes in `src/lib/server/`.
- **Upstream reference:** before inventing behaviour, check how iptv-org/epg does it (`scripts/commands/channels/edit.ts` is the CLI equivalent of our mapping flow, and `scripts/commands/epg/grab.ts` and `pm2.config.js` cover grab and scheduling). Clone it to a scratch dir to read it.
- **Out of scope for v1:** rewriting or serving a modified M3U (FUT-1). Keep the data model ready for it, but don't build it yet.

## Gotchas

- adapter-node needs `ORIGIN` (or `PROTOCOL_HEADER`/`HOST_HEADER`) set, or form actions fail the CSRF check. `BODY_SIZE_LIMIT` controls the upload size.
- Overlay sites are symlinks, so `grab` must run with `NODE_PRESERVE_SYMLINKS=1` or their `require('dayjs')` fails ([docs/spikes/M2-overlay-symlinks.md](docs/spikes/M2-overlay-symlinks.md)).
- A fresh epg checkout shows hundreds of "modified" files (upstream CRLF blobs vs. `eol=crlf`). That's expected; don't treat `git status` output there as our bug.
- `nano-spawn` merges `env` over `process.env`. Use `runCommand` from `src/lib/server/spawn.ts`, which blanks inherited vars, never `nano-spawn` directly.
- `npm install` in the epg checkout triggers `postinstall: api:load` and `prepare: husky`. Use `npm ci --ignore-scripts` and then `npm run api:load` explicitly.
- epg's `grab` falls back to `site_id` as the guide channel id when `xmltv_id` is empty. Warn the user about this rather than blocking it.
- `xmltv_id` format is `ChannelID.cc@FeedID` (for example `WCBSTV.us@SD`). The country comes from the `.cc` suffix.
- Some US sites (for example `tvtv.us`) hard-code a lineup ID in their config URL. See REQUIREMENTS OQ-3.
