# epg-editor — Roadmap

Each milestone ends in a working, tested, committed state. Requirement IDs refer to [REQUIREMENTS.md](REQUIREMENTS.md). Do milestones in order; within a milestone, write tests alongside code.

## M0 — Scaffold

- SvelteKit + `adapter-node`, Svelte 5, TypeScript, Tailwind v4 (`@tailwindcss/vite`), Vitest, ESLint, Prettier per [STYLE.md](STYLE.md).
- `package.json` scripts: `dev`, `build`, `preview`, `check`, `lint`, `format`, `test`, `run:all`, `run:sync`.
- `.gitattributes` (LF), `.gitignore` (`node_modules`, `.svelte-kit`, `build`, `/data`, `.env`).
- Port `app.css` palette, dark-mode manager, `+layout.svelte` head script, toast setup, `Common/*` components, the icons needed, `NavBar` with own wordmark.
- Empty home page rendering in light and dark.
- **Done when:** `npm run check && npm run lint && npm test && npm run build` pass.

## M1 — Core libraries (no UI)

- `core/escapeString.ts` (port + tests vs. epg behaviour).
- `core/playlistParser.ts` — FR-M-3/4/5/7. Fixtures: HDHomeRun lineup (OQ-1), generic IPTV M3U, edge cases (BOM, CRLF, missing header, duplicates).
- `core/channelsXml.ts` — FR-X-2..5, golden-file tests.
- `server/config.ts`, `server/storage.ts` (atomic writes), `server/lineupStore.ts`.
- **Spike:** run epg `grab` against a hand-written `channels.xml` with `lcn` to confirm `<lcn>` reaches the guide (FR-X-3) and document the result.

## M2 — epg checkout, overlay, index

- `server/epgRepo.ts` (clone/fetch/reset/npm ci/api:load) — FR-G-1..6.
- `server/overlay.ts` — FR-O-1..3 with temp-dir tests (link, conflict shadow, restore).
- `server/lock.ts`, `src/commands/run/sync.ts`.
- `server/guideIndex.ts` (parse all `channels.xml`, reload on `status/sync.json` change) and `server/database.ts` (`@iptv-org/sdk`).
- **Done when:** `npm run run:sync` in a dev env produces `/data/epg`, links a fixture overlay site, and the index reports entry counts.

## M3 — Matching

- `core/matcher.ts` — FR-S-1..4 (features, scoring, deterministic ranking), FR-S-5 optional.
- Fixture lineup + fixture `channels.xml` set; acceptance metric test (≥ 70 % correct in top 3).
- `/api/entries`, `/api/database`, `/api/lineups/[slug]/suggestions`.

## M4 — Lineups & editor UI

- `/` lineup list (FR-L-2), `/lineups/new` (upload + URL, FR-M-1/2), `/lineups/[slug]/settings` (FR-L-3..5, re-import diff FR-M-6).
- `/lineups/[slug]` editor: table, filters, `MappingModal` with Suggestions / Search / Manual tabs (FR-P-1..6, FR-E-1..3), provenance badges (FR-P-9).
- `channels.xml` regenerated on each change; download + preview (FR-X-6).
- **Done when:** a fixture lineup can be fully mapped in the browser and the resulting `channels.xml` matches expectations.

## M5 — Grab, scheduling, serving

- `server/grabRunner.ts`, `src/commands/run/all.ts` (lock → sync → grab each lineup), sanitised env (FR-R-4), atomic publish (FR-R-2).
- `pm2.config.cjs` (web, scheduler via `chronos`, optional startup run) — FR-R-1.
- `/guides/[file]` route with ETag/Last-Modified/HEAD (FR-R-5).
- Run history + log viewer (`/lineups/[slug]/runs`, FR-R-6); "Grab now" / "Sync now" via `server/jobs.ts` (FR-R-3); `/status` page (FR-O-5).
- Integration test (opt-in) per ARCHITECTURE §8.

## M6 — Docker & docs

- `Dockerfile`, `docker-entrypoint.sh`, `.dockerignore`; non-root; amd64 + arm64 build (NFR-DEP-*).
- README: quick start (`docker run` / compose example), env table, how to use the guide URL (client-neutral, no per-client setup steps), overlay workflow (develop → mount → sync → map → contribute upstream), security note (NFR-SEC-1).
- Walk through acceptance criteria §8 manually and record results.

## M7 — Polish (SHOULD/COULD items)

- Bulk accept (FR-P-7), duplicate/stale warnings (FR-P-8), live grab progress (FR-R-7), import existing `channels.xml` (FR-X-7), keyboard navigation (FR-P-10), accessibility pass (FR-U-5).

## Later (out of v1 scope)

- FUT-1 rewritten M3U (`/playlists/<slug>.m3u` with `tvg-id`/`tvg-chno`), FUT-2 merged guide, FUT-3 HDHomeRun discovery, FUT-4 auth, FUT-5 per-lineup schedules.
