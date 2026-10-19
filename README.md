# epg-editor

A small self-hosted web app that turns an IPTV channel list (mainly an HDHomeRun OTA lineup) into an XMLTV guide for Plex, Jellyfin, Channels DVR and similar clients.

1. Import a `.m3u` playlist by upload or URL (for example `http://<hdhomerun-ip>/lineup.m3u`).
2. Map each channel to a guide entry from [iptv-org/epg](https://github.com/iptv-org/epg). The app suggests matches; you confirm them.
3. The app writes a `channels.xml` per lineup, runs iptv-org/epg's `grab` on a schedule, and serves the result at `/guides/<lineup>.xml`.

iptv-org/epg is cloned with git into the data volume at runtime. Guide data and grabbers come from [iptv-org](https://github.com/iptv-org).

> [!WARNING]
> epg-editor has no authentication. Run it on a trusted network only and **never expose it to the internet**. Anyone who can reach it can change your lineups and start grabs.

## Quick start

Images for amd64 and arm64 are published to `ghcr.io/abates/epg-editor` for each release, tagged with the version and `latest`.

```sh
docker run -d --name epg-editor \
  -p 3000:3000 \
  -v epg-data:/data \
  -e ORIGIN=http://localhost:3000 \
  -e TZ=America/New_York \
  ghcr.io/abates/epg-editor:latest
```

Open <http://localhost:3000>. On first start the app clones iptv-org/epg, installs its dependencies and indexes about 180,000 guide entries. The UI shows an "initialising" notice until that finishes, which usually takes a few minutes.

Set `ORIGIN` to the URL you type into the browser (for example `http://nas.local:3000`). If it doesn't match, forms such as "New lineup" fail with a CSRF error.

### Docker Compose

```yaml
services:
  epg-editor:
    image: ghcr.io/abates/epg-editor:latest
    container_name: epg-editor
    restart: unless-stopped
    ports:
      - 3000:3000
    volumes:
      - ./data:/data
      # Optional: local site configs, see "Local sites" below
      # - ./sites:/data/sites
    environment:
      ORIGIN: http://nas.local:3000
      TZ: America/New_York
      CRON_SCHEDULE: 0 3 * * *
      # Optional: run as the owner of ./data (default 1000)
      # PUID: 1000
      # PGID: 1000
```

### The data volume

All state lives in `/data`: lineups, generated guides, the iptv-org/epg checkout, run logs and local sites. The container itself is disposable.

The app runs as a non-root user with uid `PUID` and gid `PGID`, both `1000` by default (the image's `node` user). The container starts as root only to apply those ids, then drops to that user. A new named volume works as is. For a bind mount, set `PUID`/`PGID` to the owner of the host directory, or make it writable by the default user:

```sh
mkdir -p data && sudo chown -R 1000:1000 data
```

The container never changes the ownership of `/data`. If it isn't writable by `PUID`:`PGID`, the container exits at start with a message saying so. This includes a named volume first created with other ids, so `chown` it when you change `PUID`/`PGID`.

`docker run --user <uid>:<gid>` (`user:` in Compose) also works. The container then never runs as root, and `PUID`/`PGID` are ignored.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ORIGIN` | — | Public URL of the app, for example `http://nas.local:3000`. Required for forms. |
| `PUID` | `1000` | User id the app runs as. |
| `PGID` | `1000` | Group id the app runs as. |
| `PORT` | `3000` | HTTP port inside the container. |
| `BODY_SIZE_LIMIT` | `5M` | Maximum request size (playlist uploads). |
| `TZ` | `UTC` | Timezone for `CRON_SCHEDULE`. |
| `STORAGE_DIR` | `/data` | Root of all state. |
| `OVERLAY_DIR` | `$STORAGE_DIR/sites` | Local site configs. |
| `EPG_REPO` | `https://github.com/iptv-org/epg.git` | iptv-org/epg git URL (a fork works too). |
| `EPG_BRANCH` | `master` | Branch to track. |
| `EPG_REF` | — | Pin a tag or commit instead of tracking the branch. |
| `CRON_SCHEDULE` | `0 0 * * *` | When to sync and grab every enabled lineup. A run still going at the next tick is stopped, so leave room for a full run. |
| `RUN_AT_STARTUP` | `true` | Sync and grab when the container starts. |
| `GRAB_DAYS` | site default | Default `--days`. |
| `GRAB_MAX_CONNECTIONS` | `1` | Default `--maxConnections`. |
| `GRAB_DELAY` | `0` | Default `--delay` between requests (ms). |
| `GRAB_TIMEOUT` | `30000` | Default `--timeout` per request (ms). |
| `GRAB_GZIP` | `true` | Also write `<lineup>.xml.gz`. |

Each lineup can override the `GRAB_*` values and opt out of scheduled grabs on its settings page.

## Using it

1. **New lineup:** give it a name and upload your `lineup.m3u`, or enter the tuner's playlist URL so you can refresh it later. Set the countries (default `us`) and, optionally, the guide sites you prefer, such as `ontvtonight.com`.
2. **Map channels:** open a channel to see suggestions with the reason for each score. Pick one, search all entries, or enter `site` / `site_id` / `xmltv_id` by hand. Mark channels you don't want in the guide as skipped. Every change is saved and `channels.xml` is rewritten straight away.
3. **Grab:** click "Grab now" on the lineup, or wait for the schedule. The run history page shows each run's result and log.
4. **Use the guide:** the lineup card shows its guide URL, for example `http://nas.local:3000/guides/living-room.xml`.

Not every upstream site works for every channel, and sites break when the provider changes its pages. If a run finds no programmes, the log shows which requests failed. Try another site's entry for that channel. The last good guide is kept until a grab succeeds.

> [!NOTE]
> Some US sites hard-code a lineup in their config. In October 2026, for example, `tvtv.us` requests a fixed New York lineup and returns 404 for the station IDs it lists. If a site fails for all your channels, pick a different site, or copy and fix its config as a local site (below).

## The guide

Each lineup's guide is a standard XMLTV file. Add its URL as an XMLTV source in your client; see the client's own documentation for where.

- `/guides/<lineup>.xml` is the plain guide, and `/guides/<lineup>.xml.gz` is the gzipped copy when `GRAB_GZIP` is on.
- The client fetches the guide over HTTP, so it must be able to reach epg-editor.
- Each channel carries its number from the playlist (for example `2.1`) as `<lcn>`, and the playlist's channel name as `<display-name>`. Clients use these to match guide channels to tuner channels.
- The URL returns 404 until the lineup's first successful grab. After that, a failed grab keeps the last good guide.
- Clients refresh guides on their own schedule. After changing mappings, run a grab, then refresh the guide in your client.

## Local sites

epg-editor doesn't create or edit site configs. Sites that aren't in iptv-org/epg yet are developed in a normal iptv-org/epg checkout and then dropped into `/data/sites`, which the app treats as an overlay on top of upstream.

1. **Develop** the site in your own clone of iptv-org/epg (start it with `npm run sites:init`, then use the site's tests and `npm run grab`). See iptv-org/epg's [contributing guide](https://github.com/iptv-org/epg/blob/master/CONTRIBUTING.md).
2. **Mount** it: copy the site folder to `/data/sites/example.com/`, so it contains `example.com.config.js` and `example.com.channels.xml`. With Compose, mount a host directory at `/data/sites`.
3. **Sync:** click "Sync now" on the Status page. The site is linked into the epg checkout and its entries appear in suggestions and search with an `overlay` badge. If it has the same name as an upstream site, your copy wins while it's there, and the Status page shows the conflict.
4. **Map and grab** as with any other site.
5. **Contribute upstream:** once it works, copy the folder into your fork of iptv-org/epg and open a pull request. When it is merged, remove your copy from `/data/sites` and sync again.

Site configs can only `require` packages that iptv-org/epg itself installs (for example `dayjs`, `axios`, `cheerio`).

Missing a channel or feed in iptv-org's database? Request it in [iptv-org/database](https://github.com/iptv-org/database).

## Development

Requires Node.js 22.

```sh
npm ci
STORAGE_DIR=./dev-data npm run run:sync   # clone iptv-org/epg into ./dev-data
STORAGE_DIR=./dev-data npm run dev
```

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | Production build (`build/`) |
| `npm run check` / `npm run lint` / `npm test` | Type check, lint, unit tests |
| `npm run test:integration` | Real iptv-org/epg clone and grab against a mock site (needs network) |
| `npm run run:sync` / `npm run run:all` | Sync only / sync and grab all enabled lineups |

To build the image yourself: `docker build -t epg-editor .`

### Releases

Pushing a tag `v<version>` publishes the image to ghcr.io as `<version>` and `latest` ([release workflow](.github/workflows/release.yml)). The tag must match `version` in `package.json`, or the workflow fails before building. For example:

```sh
npm version 1.0.0          # sets package.json, commits and tags v1.0.0
git push --follow-tags
```

Design docs are in [docs/](docs/): [requirements](docs/REQUIREMENTS.md), [architecture](docs/ARCHITECTURE.md), [style](docs/STYLE.md) and [roadmap](docs/ROADMAP.md).

## License

[Apache-2.0](LICENSE)
