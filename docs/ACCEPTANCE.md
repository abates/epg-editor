# Acceptance walkthrough (M6)

The v1 acceptance criteria from [REQUIREMENTS.md §8](REQUIREMENTS.md#8-acceptance-criteria-v1-done), checked by hand against the Docker image.

- **Date:** 2026-10-19
- **Image:** `docker build -t epg-editor:dev .` on linux/amd64 (234 MB)
- **epg:** `master` at `6f6cfe2`
- **Run:** `docker run -d -p 3300:3000 -v epg-test-data:/data -e ORIGIN=http://localhost:3300 epg-editor:dev`

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Container starts, clones iptv-org/epg, shows the lineup list | **Pass.** pm2 started `web`, `scheduler` and `startup`. The UI answered with 200 while the startup run cloned epg, ran `npm ci` and `api:load`, and indexed 180,681 entries in 251 sites plus 31,680 channels and 45,309 feeds. The health check reported `healthy`. With `RUN_AT_STARTUP=false` the `init` app ran instead and the home page showed the "initialising" notice. |
| 2 | Uploading an HDHomeRun `lineup.m3u` lists every channel with its number | **Pass.** Uploading `tests/__data__/input/m3u/hdhomerun.m3u` through the new-lineup form created `living-room` with all 14 channels, numbered 2.1, 2.2, 4.1, 4.10 and so on. |
| 3 | ≥ 70 % of channels have the correct entry in the top 3 | **Pass.** `tests/core/matcher.test.ts` gets 14 of 14 (100 %) on the fixture lineup. Against the live index, the top suggestion for 2.1, 4.1 and 7.1 was the right station. |
| 4 | Mapping writes a `channels.xml` that epg's `grab` accepts | **Pass.** `/data/lineups/living-room/channels.xml` had `site`, `site_id`, `lang`, `xmltv_id` and `lcn` for each mapped channel, and `grab` in the container's plain epg checkout ran it without errors. |
| 5 | "Grab now" produces `/guides/<slug>.xml`; Plex shows guide data | **Pass for the guide, Plex not tested.** Mapped to `ontvtonight.com`, "Grab now" saved 3 channels and 178 programmes. `/guides/living-room.xml` had `<lcn>2.1</lcn>` and so on, `Content-Type: application/xml`, an `ETag` (a matching `If-None-Match` got 304) and `Last-Modified`. The `.xml.gz` was served as well, and `/guides/..%2F…` returned 404. **Still to do:** add the URL to Plex as an XMLTV source (also settles OQ-2). |
| 6 | A site folder in `/data/sites` plus "Sync now" makes it searchable and grabbable | **Pass.** A `mock.local` site that `require`s `dayjs` was copied into `/data/sites`. After "Sync now", `/data/epg/sites/mock.local` was a symlink and `/api/entries` returned its entry with `origin: overlay`. A grab with one channel mapped to it wrote its programmes into the guide. |
| 7 | Light and dark themes match iptv-org.github.io | **Pass.** Checked the lineup list in Chrome in both themes. |

## Other checks

- **Restart:** `docker restart` kept the lineup, mappings and guide. The startup run synced and grabbed again.
- **Non-root:** the processes run as `uid=1000(node)`. A root-owned bind mount at `/data` makes the container exit with `error: /data is not writable by uid 1000` and a `chown` hint.
- **Missing `ORIGIN`:** the entrypoint prints a warning.
- **arm64 (NFR-DEP-5):** not built here, because this host has no QEMU binfmt handler for arm64. `.github/workflows/ci.yml` builds `linux/amd64,linux/arm64` with buildx. Nothing in the Dockerfile is architecture-specific, and `node:22-alpine` publishes arm64.

## Findings

- **tvtv.us returns 404** for every station: its config hard-codes the lineup `USA-NY71652-X` (OQ-3). A direct `curl` of the same URL also got 404, so this is upstream, not the app. The failed run was recorded as `failed` ("grab found no programmes") and no guide was published, as FR-R-2 requires. The README tells users to pick another site or to override the site with a local copy.
