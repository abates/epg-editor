# Backlog — initial build, thin vertical slice first

Ownership: `project-manager` delegates each item below to the named agent(s).
Items marked 🛑 **USER CHECKPOINT** are hard stops — see "User checkpoints"
in `.claude/agents/project-manager.md`. Work does not continue past a 🛑 item
until the product owner (Andrew) has tested and explicitly confirmed it.

Default for all SD-dependent dev work below: agents build and automated-test
against a **mocked** SchedulesDirect client. No agent calls the real SD API
with real credentials. Real-SD interaction happens only at checkpoints,
performed by Andrew against his real account.

## Phase 0 — Scaffolding

1. **Backend skeleton** (`backend-developer`) — `backend/` per CLAUDE.md's
   module layout (`api/`, `services/`, `sd_client/`, `storage/`, `models/`,
   `scheduler/`), `pyproject.toml` + `uv.lock`, FastAPI app with a health
   check, `/data/{config,cache,output}` bootstrapping on startup.
2. **Frontend skeleton** (`frontend-developer`) — `frontend/` with `npm`,
   TypeScript config (`allowJs: true`), the `api/` (vanilla JS) vs.
   `components/`/`pages/` (TSX + styled-components) split, a placeholder
   page that calls the backend health check.
3. **Review scaffolding** (`peer-reviewer`) — confirm module boundaries and
   dependency direction before real logic is added.

## Phase 1 — Thin vertical slice (manual path, no M3U, no fuzzy matching)

4. **Domain + SD Pydantic models** (`backend-developer`) — `models/`:
   `Lineup`, `Channel`, `ChannelMapping` per `docs/data-model.md`, plus SD
   request/response shapes for token, account-lineups, lineup stations.
5. **`config/lineups.json` storage** (`backend-developer`) — `storage/`
   module, load/save with atomic write (temp file + rename).
6. **SD client: auth + account lineups** (`backend-developer`) — `sd_client/`
   module: token fetch/caching/refresh, list/add/remove account lineups.
   Built and tested against a **mock** SD backend — no real credentials used
   here.
7. **Manual lineup CRUD API** (`backend-developer`) — create epg-editor
   lineup, add/edit/remove channels manually, associate `sdLineupIds`.
8. **Manual mapping confirm API** (`backend-developer`) — endpoint to set a
   channel's `mapping.sdStationId`/`confirmed` directly (no suggestions yet).
9. **XMLTV generation service** (`backend-developer`) — for confirmed
   mappings, pull cached station/schedule/program data, emit XMLTV
   (validate against the DTD in dev), write atomically to
   `/data/output/<lineup-id>.xml`.
10. **XMLTV serving endpoint** (`backend-developer`) — `/xmltv/{lineup-id}.xml`
    static file response, read-only.
11. **Frontend: lineup + channel management UI** (`frontend-developer`) —
    create lineup, add channels manually, associate SD lineups, manually
    confirm a mapping.
12. **Peer review of Phase 1** (`peer-reviewer`) — correctness + module
    boundaries across items 4–11.
13. **Automated UAT against mock SD** (`uat-tester`) — exercise the full
    manual slice end-to-end using the mocked SD backend.

14. 🛑 **USER CHECKPOINT — real SD account + real Plex/Jellyfin**
    What to do:
    - Point the running app at your real `SD_USERNAME`/`SD_PASSWORD`.
    - Add/associate one of your real SD account lineups to an epg-editor
      lineup; manually confirm a mapping for at least one real channel.
    - Generate XMLTV and fetch `/xmltv/{lineup-id}.xml`.
    - Point your own Plex/Jellyfin at that URL and confirm it actually shows
      guide data (this step is outside the repo — no setup docs will be
      added for it, per the client-neutral policy in CLAUDE.md).
    Confirmed means: real SD auth works, no SD lineup slot got consumed
    unexpectedly, and your media server displays the generated guide data.
    Report back any failure as a bug — development does not continue past
    this point until you confirm.

## Phase 2 — M3U import

15. **M3U parsing service** (`backend-developer`) — parse `#EXTINF`
    (`tvg-id`, `tvg-name`, `tvg-logo`, `group-title`, channel number).
16. **M3U re-import merge logic** (`backend-developer`) — match by `tvgId`
    (fallback channel number); update matched metadata in place, preserving
    confirmed mappings; add unmatched as new; flag vanished channels via
    `missingSince` (never auto-delete).
17. **Frontend: M3U upload UI** (`frontend-developer`) — upload flow,
    re-import diff view (new / updated / flagged-missing), missing-channel
    removal confirmation.
18. **Review** (`peer-reviewer`) — including the re-import edge case.

19. 🛑 **USER CHECKPOINT — real M3U file**
    What to do: export the actual M3U playlist from your real HDHomeRun (or
    other source) and upload it twice — once as initial import, once after
    making a real change (remove/rename a channel on the device side) to
    exercise the re-import merge path.
    Confirmed means: the parse matches your real channels correctly, and a
    channel you removed on the device shows as flagged-missing, not deleted.
    Development does not continue past this point until you confirm.

## Phase 3 — Mapping suggestions

20. **Evaluate fuzzy-matching library** (`backend-developer`) — evaluate
    `rapidfuzz` (and alternatives if warranted), recommend, bring back to
    Andrew for confirmation before locking in (open decision per CLAUDE.md).
21. **Suggestion generation service** (`backend-developer`) — candidate pool
    = union of stations across a lineup's `sdLineupIds`; score on
    name/call sign/affiliate (via `rapidfuzz`'s `WRatio`); populate
    `mapping.suggestions` (recomputed, not accumulated). Done: confirmed
    `rapidfuzz` + `WRatio` per item 20's evaluation.
22. **Bulk-accept** (`backend-developer`) — accept all suggestions ≥ fixed
    backend threshold (not a UI control). Done: started at **0.92**. This
    isn't a tuned "just above a known false-positive score" cutoff — a
    Phase 3 benchmark confirmed `WRatio` caps a *partial* (non-exact) match
    at roughly 0.90 when the two strings differ substantially in length
    after normalization (e.g. a bare callsign vs. a fuller display name),
    regardless of whether it's a genuine match or a same-affiliate false
    positive, so the two aren't distinguishable at that score level by this
    metric alone. When the strings are closer in length, though, a
    word-reordered or word-subset match can score up to ~0.95 and clear
    0.92. So 0.92 restricts bulk-accept to near-exact full-string matches
    *plus* some genuine similar-length non-exact matches, while deliberately
    excluding the substantially-different-length partial matches as a
    conservative starting point. Still just a starting value; real tuning
    happens at checkpoint 25.
23. **Frontend: suggestion review UI** (`frontend-developer`) — per-channel
    accept/reject, bulk-accept action, confidence display.
24. **Review** (`peer-reviewer`).

25. 🛑 **USER CHECKPOINT — real match quality**
    What to do: run suggestion generation against one of your real SD
    lineups and review the actual suggestions and scores produced for your
    real channels (not synthetic test data).
    Go in expecting this: because 0.92 mostly bulk-accepts near-exact
    full-string matches, plus some similar-length word-reordered/subset
    matches (see item 22), bulk-accept is likely to confirm relatively few
    of your real channels — most real HDHomeRun-style names (e.g.
    "KGO-HD") won't exact-match or closely length-match a station's
    name/callsign/affiliate. That's the intended conservative starting
    point, not a bug; this checkpoint is exactly where real tuning (a lower
    threshold, a better signal, etc.) happens based on what you actually
    see.
    Confirmed means: you're satisfied with the bulk-accept behavior for
    your real lineup — whether that means keeping 0.92, adjusting it, or
    deciding a different signal is needed. Adjust the fixed default if
    warranted, then re-review.
    Development does not continue past this point until you confirm.

## Phase 4 — SD account lineup management UI

26. **Frontend: SD account lineup CRUD** (`frontend-developer`) — list/add/
    remove against the API from item 6; surface SD's lineup-slot limit
    proactively.
27. **Review** (`peer-reviewer`).

28. 🛑 **USER CHECKPOINT — real SD account mutation**
    What to do: use the UI to add and remove a real SD account lineup
    against your real account.
    Confirmed means: it worked, the slot-limit messaging was accurate, and
    nothing unexpected happened to your real SD subscription state.
    Development does not continue past this point until you confirm.

## Phase 5 — Scheduled refresh

29. **Scheduler jobs** (`backend-developer`) — `scheduler/`: APScheduler job
    refreshing cached SD data (via md5 hashes to skip unchanged schedules)
    and regenerating XMLTV; thin jobs calling into `services/`. Scope
    explicitly includes refreshing cached SD lineup station rosters
    (`storage/sd_cache.py`'s `invalidate_lineup_stations`) — Phase 3's
    suggestion-generation service (item 21) caches a lineup's station
    list on first fetch with no TTL/expiry of its own, by design (that
    staleness problem was flagged during Phase 3 review as squarely this
    phase's job, same as schedule/program refresh, not something to
    solve ad hoc in item 21). Done: `scheduler/jobs.py`'s
    `AsyncIOScheduler` job (chosen over `BackgroundScheduler` because the
    job body is a coroutine awaiting `SdClient`'s async HTTP calls, so it
    needs uvicorn's own event loop, not a thread-pool-based one) running
    `services/refresh.py`'s `refresh_all_lineups` on an interval — see item
    31 for the interval itself. The job is thin, calling straight into
    `services/refresh.py`; all the actual logic (md5-based schedule skip,
    station-roster refresh, error isolation) lives there. Wired into
    `app.main`'s `lifespan` (started on app startup, shut down on app
    shutdown), stored on `app.state.scheduler`.

    Scope explicitly includes refreshing cached SD lineup station rosters
    (`storage/sd_cache.py`) — Phase 3's suggestion-generation service
    (item 21) caches a lineup's station list on first fetch with no
    TTL/expiry of its own, by design; that staleness problem is resolved
    here, not ad hoc in item 21. Mechanism: `GET /status` is called once
    per refresh cycle (needed for schedule refresh too); each associated
    SD lineup's `modified` timestamp from that response is compared against
    `CachedLineupStations.modified` (now persisted alongside `fetchedAt`),
    and the roster is only re-fetched if SD's value is newer. A 30-day
    fallback TTL (`services/refresh.py`'s `STATION_ROSTER_TTL`, a fixed
    backend constant, not user-configurable) forces a re-fetch regardless
    of `modified` once a cached roster is that old.

    Schedule refresh uses the "skip unchanged schedules" mechanism quite
    literally: a new `SdClient.get_schedule_md5s` method
    (`POST /schedules/md5`, verified against SchedulesDirect/JSON-Service's
    wiki) returns per-station/day md5+`lastModified` without the full
    schedule payload; only station/days whose md5 differs from what's
    cached (or that were never cached) trigger a full `get_schedules` call.

    This is a distinct, **global** (all-epg-editor-lineups) pipeline from
    the per-lineup `POST /api/lineups/{lineup_id}/sync-and-generate`
    endpoint pulled forward into Phase 1 (no md5-skip optimization, scoped
    to one lineup) — at the time this was written the two mechanisms
    coexisted: the per-lineup button for "refresh just this one lineup, no
    skip-optimization, right now," and the global one for "run the real
    scheduled pipeline across everything, right now" (item 30).

    **Update:** per Andrew's decision, the Phase 1 stopgap has since been
    superseded by this global refresh pipeline and fully removed —
    `services/sync.py`, `api/sync.py`, `models/sync.py`, and
    `POST /api/lineups/{lineup_id}/sync-and-generate` no longer exist.
    `refresh_all_lineups` (this item) is now the only sync/generate
    mechanism in the app. The "both mechanisms coexist" framing above
    describes the state of the app only up through this item's initial
    implementation, not the current state.

    One bad SD lineup/station/epg-editor lineup doesn't abort the whole
    run (collected into the result's `errors`); an auth/account-level SD
    failure does abort the run (propagates), since every subsequent call
    would fail identically.
30. **Manual "refresh now"** (`backend-developer` + `frontend-developer`) —
    API endpoint running the same pipeline on demand, triggered from the UI.
    Done (backend half): `POST /api/refresh-now` — not nested under
    `/lineups/{id}`, since it's explicitly the same global pipeline as item
    29, not a per-lineup action — returning the same `RefreshResult` shape
    the scheduled job logs. Does not reset/reschedule the scheduled job's
    timer in any way; it's an independent, on-demand run of the identical
    function. Frontend trigger/UI still pending.
31. **Decide refresh interval + env var name** (`backend-developer`) —
    propose default + name, confirm with Andrew (open decision per
    CLAUDE.md). Done: confirmed `EPG_EDITOR_REFRESH_INTERVAL` (deliberately
    no `_HOURS` suffix — the unit is documented in prose everywhere this
    var is referenced, not baked into the name), a plain number of hours,
    defaulting to **12**. Values below **1** hour are clamped up to 1
    (rather than rejected outright) per SchedulesDirect's own documented
    courtesy request not to sync more than once an hour — a misconfigured
    env var degrades to "syncs somewhat more often than ideal" instead of
    crashing the app at startup.
32. **Review** (`peer-reviewer`).

    **Update:** peer review found one HIGH-severity bug and three
    lower-severity ones in this pipeline before it ran against a real
    account; all four fixed:
    - HIGH — `services/refresh.py`'s program-fetch step used to scan only
      the schedule days *refetched this run* to decide which program IDs
      to fetch, so a failed `/programs` call for a schedule day whose md5
      later went unchanged would never be retried again — permanently
      "Unknown" titles with no further visible error. Fixed by scanning
      every cached schedule day in the guide window each run (refetched or
      skipped-as-unchanged) and adding a program-level md5 skip
      (`CachedProgram.scheduleMd5`) so this doesn't make every run
      re-fetch every program unconditionally. Also added chunking to
      `SdClient.get_programs` (SD's documented 5000-ID cap per request).
    - MEDIUM — `SdClient.get_lineup_stations` didn't check SD's `code`
      field the way `list_account_lineups`/`get_account_status` already
      did, so an SD error body on HTTP 200 could silently overwrite a good
      cached station roster with an empty one, suppressed from retry for
      up to `STATION_ROSTER_TTL`. Fixed with the same `code` check.
    - MEDIUM-LOW — `SdScheduleMd5Response` validated the whole
      `/schedules/md5` response atomically, so one malformed per-station
      entry failed validation for the entire batch, falling back to a
      full schedule refetch for *every* mapped station, not just the bad
      one. Fixed with per-station lenient parsing.
    - LOW — `scheduler/jobs.py`'s `get_refresh_interval_hours` didn't
      guard against a non-finite `EPG_EDITOR_REFRESH_INTERVAL`
      (`nan`/`inf`/an overflow like `1e400`), which crashed app startup
      instead of falling back to the default as documented. Fixed with a
      `math.isfinite` check.

33. 🛑 **USER CHECKPOINT — real scheduled refresh**
    What to do: let the real app run with the scheduler active against your
    real SD account for at least one full refresh interval; separately,
    trigger "refresh now" manually.
    Confirmed means: refresh completed without errors, cache/output updated
    as expected, and no excessive SD API calls were made (md5 short-circuit
    is working).
    Development does not continue past this point until you confirm.

## Phase 6 — Bugs & feature requests from real-world use (reported 2026-11-03)

Reported by Andrew against his running home deployment while checkpoint 33
(scheduled refresh) is still soaking — tracked independently since none of
these touch the refresh pipeline itself.

34. **Bug: sanitize dots out of XMLTV channel ids** (`backend-developer`) —
    Plex fails to match channel ids containing a literal `.` (e.g. an
    ATSC-subchannel-style `tvgId` like `7.1`). Fix in `services/xmltv.py`'s
    `_channel_xmltv_id` (used for both `<channel id>` and `<programme
    channel>`): replace `.` with `-` in the id *as emitted*, output-only —
    never mutate the stored `tvgId`/channel `id` in `config/lineups.json`.
    The existing duplicate-id dedup in `confirmed_mapped_channels` already
    covers the resulting rare collision case (e.g. two tvgIds that only
    differ by dot placement sanitizing to the same string), so no new
    collision handling is needed. Once live against Andrew's real
    environment, confirm whether any other Plex-unsafe characters need the
    same treatment rather than guessing at a broader character set now.
    **Closed (2026-11-05):** Andrew hasn't hit any other Plex-unsafe
    characters in real use — treating this as fixed with `.` only. Any
    further character turns up as a new bug report, not a reopening.
35. **Feature: XMLTV link + copy-to-clipboard on the lineup page**
    (`frontend-developer`) — on `LineupDetailPage`, surface the lineup's
    full `/xmltv/{lineup-id}.xml` URL (absolute, the app's own origin) with
    a copy-to-clipboard button, so Andrew doesn't have to hand-construct it
    for Plex/Jellyfin. Only show it once a file has actually been
    generated (reuse the existing generation-status signal); show a
    "not generated yet" state otherwise rather than a dead link.
36. ~~**Feature + open decision: name the generated file after the lineup,
    not its id**~~ — **Dismissed by Andrew (2026-11-05), not implemented.**
    Conflicted with the "stable HTTP path" guarantee CLAUDE.md locks in for
    `/xmltv/{lineup-id}.xml` (so a configured Plex/Jellyfin EPG URL never
    breaks). Two options were written up:
    - (a) Cosmetic only, URL unchanged: just set `Content-Disposition` on
      the response so a manual download suggests the lineup name as the
      filename, URL untouched.
    - (b) URL itself becomes name-derived (e.g. `/xmltv/{slug}.xml`):
      friendlier, but a lineup rename would move its EPG URL, breaking any
      already-configured Plex/Jellyfin source, plus needing a new
      slug-collision rule.
    Andrew decided the rename-breaks-the-URL risk in (b) wasn't worth it,
    and (a) wasn't compelling enough on its own to pursue — dismissing the
    item rather than picking either option.
37. **Feature: search Schedules Direct stations when mapping a channel**
    (`backend-developer` + `frontend-developer`) — today, when Phase 3's
    fuzzy suggestions don't surface the right station, the only fallback is
    `ChannelMappingForm`'s raw `sdStationId`/`sdLineupId` text fields (this
    predates Phase 3 — the component's own docstring still says "no
    suggestion scoring yet"). Add a searchable picker over the station
    roster(s) already cached for the lineup's associated SD lineups
    (`storage/sd_cache.py`), filtering by name/callsign/affiliate as the
    user types — no live SD call, rosters are already kept fresh by the
    Phase 5 refresh job. Backend: a new read endpoint over the cached
    roster, reusing the existing name/callsign/affiliate matching rather
    than inventing a new scoring scheme. Frontend: replace/augment the
    manual text-entry mode in `ChannelMappingForm` with a search-and-select
    UI; keep raw id entry available (e.g. behind an "advanced" toggle) as
    an escape hatch for a station that can't be found by search.
38. **Refactor: drop `ChannelMapping.confirmed`, derive "mapped" from
    `sdStationId`/`sdLineupId` presence** (`backend-developer` +
    `frontend-developer`) — found via item 37's UAT: the search picker
    inherits a stale `confirmed` value from the channel's prior mapping
    state, so picking and saving a station can silently leave it
    `confirmed: false` (excluded from XMLTV generation) with no obvious
    indication why. Investigating *why* surfaced that the field is
    redundant, not just mis-defaulted:
    - Suggestion generation (`services/suggestions.py`) never sets
      `sdStationId`/`sdLineupId` — it only populates the separate
      `mapping.suggestions` list. The "needs review" state the model
      docstring describes is `suggestions` populated with `sdStationId`
      still `null`; that distinction already exists independently of
      `confirmed`.
    - Single accept, bulk-accept, and the manual/search form are the
      *only* three places that ever set `sdStationId`/`sdLineupId` — all
      three are explicit user actions, and the first two always pair that
      with `confirmed: true` in the same call. No code path sets a station
      "provisionally." The only way `confirmed` ever diverges from "has a
      station" is the item-37 bug itself — not a feature the divergence
      enables, the only thing it's ever produced.
    - `update_lineup_sd_lineup_ids`'s orphan-protection check
      (`services/lineups.py`, rejects removing an SD lineup id a channel's
      mapping still points at) gates on `channel.mapping.confirmed`, not on
      `sdLineupId` being set — so a channel stuck in the buggy
      "has a station, unconfirmed" state is currently *unprotected* from
      having its `sdLineupId` silently orphaned, the exact outcome that
      guard exists to prevent. Deriving "mapped" from field-presence makes
      this guard strictly more correct.
    Scope:
    - `models/lineup.py`: remove `ChannelMapping.confirmed`; rename
      `confirmedAt` to `mappedAt`, set whenever `sdStationId` is set (kept
      as a plain timestamp for audit/diagnostic purposes — "when did this
      mapping get set" — not as a gate).
    - `services/xmltv.py`'s `confirmed_mapped_channels` (and anywhere else
      filtering on `.confirmed`): derive "mapped" as `sdStationId is not
      None` instead.
    - `services/lineups.py`'s `update_lineup_sd_lineup_ids` orphan guard:
      gate on `sdLineupId` presence instead of `.confirmed`.
    - `services/suggestions.py` (`generate_suggestions`,
      `bulk_accept_suggestions`) and `api/lineups.py`'s mapping-confirm
      endpoint: drop the `confirmed` request/response field; setting
      `sdStationId` always means mapped, full stop.
    - `frontend/src/components/ChannelMappingForm.tsx`: remove the
      "Confirmed" checkbox — "Save mapping" always means mapped, matching
      Accept/bulk-accept. Update `MappingStatusBadge`/`ChannelRow`'s
      `confirmedAt` display to `mappedAt`.
    - `docs/data-model.md`: update the schema and the "needs review"
      explanation to match (suggestions-populated-with-null-sdStationId is
      the needs-review state; no separate boolean).
    Decided by Andrew after discussion (2026-11-04) — not an open question,
    unlike item 36.
39. **Feature: rolling backups of `config/lineups.json`** (`backend-developer`)
    — outcome of the "split `lineups.json` per lineup?" discussion
    (2026-11-05, decided: stay single-file — see CLAUDE.md "Open
    decisions"). Atomic writes already protect against a crash mid-write;
    what they don't protect against is the app itself saving *bad* data
    (a buggy mutation) over every lineup at once. Before each save in
    `storage/lineups.py`, rotate the current file into a small set of
    backups in `config/` (e.g. `lineups.json.1` … `lineups.json.5`,
    newest = `.1`), keeping the last 5. Default count of 5 is a starting
    choice, not confirmed — adjust if Andrew prefers otherwise.
    Constraints:
    - Stays entirely inside `storage/` — no caller changes; still runs
      under `update_lineups`'s `_LOCK` so rotation can't race a save.
    - Skip rotation when there's no existing file (fresh install).
    - Backups use the same 0644 mode as the live file (`_atomic.py`).
    - A failure to rotate a backup must not prevent the real save — log
      it and continue. (Never log file contents.)
    - No restore UI; restoring is a manual copy, documented in
      `docs/data-model.md` alongside the existing "back this up" note.

### Reported 2026-11-05 (Plex, real home deployment)

Items 40–42 are **diagnose-first** bugs: the developer should find out the
root cause and write it up in the item before fixing anything. If the fix
needs a product decision (e.g. which of several image sources to prefer),
stop and bring it to Andrew rather than picking one quietly. Each fix must
stay client-neutral: emit standard, well-formed XMLTV that Plex happens to
read correctly, with no Plex-specific branches or docs (per CLAUDE.md).
Starting observation for all three (from a quick read, not a diagnosis):
`services/xmltv.py`'s `build_xmltv_document` currently emits only
`<title>` and `<desc>` per `<programme>`, and a channel `<icon>` only from
the channel's own `logoUrl` (M3U `tvg-logo` or entered by hand), never
from SchedulesDirect.

40. **Bug: Plex shows no series name or episode info, and treats shows as
    movies when recording** (`backend-developer`) — guide data shows up in
    Plex, but programmes have no series/episode details, and clicking
    "record" on a show offers to record it into the Movies library instead
    of as a TV series. Diagnose which XMLTV elements Plex uses to tell a
    series episode from a movie and to get its series/episode metadata
    (likely candidates to check: `<episode-num>` in the `xmltv_ns` and/or
    `dd_progid`/`onscreen` systems, `<sub-title>`, `<category>` such as
    "Series"/"Movie", `<date>`, `<previously-shown>`/`<new>`), and
    whether the SD program data we already cache (`/programs` responses
    in `cache/sd/`) has the matching fields: SD program ID prefix
    (`EP`/`SH`/`MV`/`SP`), `metadata` season/episode numbers, `episodeTitle150`,
    `genres`, `entityType`/`showType`, original air date. Check whether
    `models/` and `sd_client/` drop fields we'd need during parsing.
    **No Plex access:** the developer cannot reach Andrew's Plex server.
    Anything that needs Plex (what Plex shows for a given programme, how it
    classifies it, what it does on "record", its logs) is done by Andrew.
    The developer writes step-by-step instructions for him: exactly what to
    look at or run, which programmes or channels to check (by name and air
    time from the generated XMLTV), and what to send back (screenshots,
    exact text, log excerpts). Diagnose as far as possible from the code
    and the generated XMLTV first, then ask for only what's still missing.
    Done means: a real series episode in Plex shows its series name and
    episode info and records as a TV episode; a real movie still records
    as a movie. Andrew confirms this using verification steps the developer
    provides with the fix.

    **Diagnosis (2026-11-06):** confirmed both halves of the starting
    observation.
    - `services/xmltv.py`'s `build_xmltv_document` really did emit only
      `<title>`/`<desc>` per `<programme>` — no `<episode-num>`,
      `<sub-title>`, `<category>`, `<date>`, `<new>`/`<previously-shown>`
      at all, regardless of what SD's cached program data had.
    - `models/sd.py`'s `SdProgram` already carried `episodeTitle150`,
      `originalAirDate`, and `genres` from SD's `/programs` response, but
      silently dropped `entityType`, `showType`, and `metadata` (SD's
      season/episode numbers) — `SdModel`'s `extra="ignore"` means these
      were present in SD's raw JSON (and in `cache/sd/programs/*.json`'s
      underlying data, when passed through) but discarded on parse, not
      recoverable from the cache without a Pydantic field to hold them.
      Verified field names/shapes against SchedulesDirect/JSON-Service's
      wiki (`API-20141201.md`, `API-20141201-Program-Response.md`) rather
      than guessing — see docs/schedulesdirect-integration.md's new
      "Program metadata used for series/episode info" section for the
      specifics, including the exact `programID` structure (`EP`/`SH`/
      `MV`/... 2-letter prefix + 12 digits, last 4 identifying the specific
      episode) and SD's own documented caveat that `entityType`, not the
      prefix, is the authoritative movie-vs-episode signal.
    - Plex's XMLTV importer's recognition rules themselves aren't
      something this developer could pull from a canonical Plex spec
      page (Plex doesn't publish one) — the applicable behavior is
      instead the de facto standard used by the SD-sourced XMLTV
      ecosystem Plex's grabber was built to work with: zap2xml's
      `dd_progid`-system `<episode-num>` (the SD programID itself,
      reformatted) is the strongest signal that a programme belongs to a
      series rather than being a standalone movie, with `xmltv_ns`/
      `onscreen`-system `<episode-num>` and a `<category>` of
      `"Series"`/`"Movie"` as supporting signals. Fixed by implementing
      against the XMLTV DTD's own documented element semantics/ordering
      (vendored at `backend/tests/fixtures/xmltv.dtd`) plus this
      widely-used `dd_progid` convention — not a Plex-specific branch, per
      CLAUDE.md's client-neutral requirement; a standards-compliant XMLTV
      consumer built the same way SD-sourced grabbers are would read this
      correctly regardless of which guide app it is.

    **Fix:**
    - `backend/app/models/sd.py`: `SdProgram` gained `entityType`,
      `showType`, and `metadata` (`list[dict[str, SdProgramMetadataEntry]]`,
      a new `SdProgramMetadataEntry` model for the season/episode/
      totalEpisodes/totalSeasons value) plus a `primary_season_episode()`
      helper. No `sd_client/` changes needed — `get_programs` already
      validates every `/programs` item against `SdProgram`, so the new
      fields flow through automatically once declared on the model.
    - `backend/app/services/xmltv.py`: `build_xmltv_document` now emits,
      in the DTD-required order, `<sub-title>` (from `episodeTitle150`),
      `<date>` (from `originalAirDate`, digits-only), `<category>` (a
      `"Movie"`/`"Series"` classification from the new `_is_movie`/
      `_is_series_episode` helpers, plus every SD genre), `<episode-num>`
      (a `dd_progid` entry for every series episode — even with no
      season/episode numbers from SD, since that alone is the fix for
      "recorded as a movie" — plus `xmltv_ns`/`onscreen` entries when SD's
      `metadata` supplies season/episode numbers), and `<new>`/
      `<previously-shown>` (from the schedule airing's own `new` flag,
      not the program record). Movies get a `"Movie"` category and no
      `<episode-num>`/`<sub-title>` at all. `_is_movie`/`_is_series_episode`
      prefer `entityType` and fall back to the `programID` prefix only
      when `entityType` is absent (see the cache-migration note below).
    - Tests: `backend/tests/services/test_xmltv.py` gained cases for a
      fully-populated series episode, an "SH"-style series reference with
      no season/episode numbers (still gets `dd_progid`), a movie (no
      episode-num), the `entityType`-missing programID-prefix fallback,
      and the `new`/`previously-shown` airing-flag behavior. Full suite
      (`uv run pytest`, 302 tests) and DTD validation both pass; no lint
      tool is currently configured for the backend (checked — not an
      oversight in this fix).
    - `docs/schedulesdirect-integration.md`: new section documenting the
      `/programs` fields consulted above and their provenance.

    **Peer review follow-up (2026-11-06):** `peer-reviewer` caught two
    correctness bugs in the fix above before it shipped, both fixed in
    the same uncommitted change set (test suite now at 304):
    - **`new`/`previously-shown` was inverted.** The original code only
      acted when `airing.new` was explicitly `True` or `False`, treating
      a missing value as "unknown, emit neither." But per SD's own docs
      (`API-20141201.md`), an absent optional boolean means *assume
      false* — SD's real responses never send `"new": false` for a
      rerun, they just omit the key. So in practice `airing.new` is only
      ever `True` or `None`, and the original logic meant every real
      rerun got neither element. Fixed: `<new/>` only when `new is True`;
      everything else (`False` or missing) now emits
      `<previously-shown/>`.
    - **`entityType` classification missed `Show` (and any other
      unenumerated value).** The original `_SERIES_ENTITY_TYPES` allowlist
      named only `Episode`/`Series`/`Miniseries`/`Sport-Related Episode`
      out of SD's ~20-value `entityType` enum, so a `Show`-typed program
      (a real SD value, not a hypothetical) fell through to no
      classification and no `<episode-num>` at all — the exact
      "treated as movie" symptom this item exists to fix. It would also
      have made the "clear `cache/sd/programs/` and refresh" verification
      step actively regress such a program from the correct pre-fix
      fallback behavior to this broken one. Andrew decided (2026-11-06):
      default to **"movie unless proven otherwise"** rather than
      enumerating every series-like type, since SD adding a future
      `entityType` value should fail safe toward the series branch (what
      this bug report complained was missing), not silently regress back
      toward the movie branch (what it complained was wrong). Fixed:
      `_is_movie` now checks an explicit, narrow movie allowlist
      (`Movie`, `TV Movie`, `Paid Program`); `_is_series_episode` is
      `not _is_movie(...)` whenever `entityType` is present, covering
      `Show` and any other current or future non-movie value. The
      `programID`-prefix fallback used when `entityType` is absent is
      unchanged (still narrowly `EP`/`SH` only) — not widened, since an
      unrecognized prefix with no `entityType` at all shouldn't be
      assumed series either.

    **Operational note — existing cached programs won't retroactively
    gain these fields on their own:** `services/refresh.py`'s md5-based
    skip logic means an already-cached, unchanged program is never
    re-fetched just because this app upgraded — nothing in SD's own data
    changed. `cache/sd/` is fully regenerable and safe to delete at any
    time (per `docs/data-model.md`), so after deploying this fix, clear
    `cache/sd/programs/` once and let a refresh repopulate it (see
    verification step 1 below) rather than waiting for stale entries to
    expire naturally.

    **Verification instructions for Andrew** (no Plex/SD access from this
    side — every step below is something only you can run):

    1. **Force a clean program-metadata re-fetch.** On the machine/
       container running epg-editor, stop the app (or just proceed — the
       delete is safe either way, see `docs/data-model.md`), delete the
       contents of `/data/cache/sd/programs/` (adjust the path if you've
       set `EPG_EDITOR_DATA_DIR` to something other than `/data`; this is
       the same volume your `docker-compose.yml` mounts), then either wait
       for the next scheduled refresh or trigger one immediately:
       `curl -X POST http://<your-epg-editor-host>:<port>/api/refresh-now`
       (or just hit that endpoint from a browser/Postman — it's a POST, so
       a plain browser visit won't work, curl or an API client will).
       Confirm it returns a 200 with no `errors` referencing your mapped
       stations.
    2. **Fetch your lineup's regenerated XMLTV** and look at the raw XML,
       not just what Plex shows: `curl http://<your-epg-editor-host>:<port>/xmltv/<your-lineup-id>.xml`
       (or open that URL in a browser and view source/save it). Pick one
       `<programme>` for a channel you know airs a recognizable scripted
       series soon (sitcom, drama, etc. — not news/sports, which may
       legitimately get no episode-num) and one for a channel you know
       airs a movie. For each, confirm by eye:
       - The series one has a `<sub-title>` (unless SD genuinely has no
         episode title for it), a `<category>Series</category>`, and at
         least an `<episode-num system="dd_progid">...</episode-num>`
         (and `xmltv_ns`/`onscreen` ones too, if SD had season/episode
         numbers for it).
       - The movie one has `<category>Movie</category>` and **no**
         `<episode-num>` element at all.
       If a programme you expected to be a series instead looks like the
       movie case (or vice versa), send back: the full `<programme>` block
       for it (copy/paste the XML), the channel name, and the exact
       `start`/`stop` time from that block — that's enough to tell whether
       SD classified it differently than expected (a real content-metadata
       quirk on SD's end) versus a bug in this fix.
    3. **Now check Plex itself**, using the *same* channel/programme/air
       time you just confirmed in step 2's XML (so we know exactly which
       airing you're looking at):
       - Open Plex's guide for that channel at that time. Report back
         (screenshot is easiest): does the guide cell/detail view show a
         series name and episode title/number now, where it didn't
         before?
       - For the series programme specifically: click "Record" (or
         whatever your Plex version's DVR record action is called) on it.
         Report back: does Plex offer "Record Series"/"Record this
         episode"-type options (TV show behavior), or does it still only
         offer to record it as a movie? A screenshot of that record dialog
         is the clearest thing to send.
       - For the movie programme: confirm it still records as a movie
         (we don't want to have broken that case while fixing the other).
       - If Plex's guide hasn't picked up the new XML yet, it may need its
         own EPG/guide data refresh — check Plex's live TV & DVR settings
         for a "refresh guide now"-type action (exact location varies by
         Plex version) and use that before concluding something's wrong.
    4. If anything in step 3 still looks wrong after confirming step 2's
       XML is correct, that narrows it to "Plex isn't reading this
       correctly" rather than "we're not emitting it correctly" — send the
       `<programme>` XML block from step 2 alongside the step 3
       screenshots/description so the next debugging pass has both sides
       side by side.

    Done means: Andrew confirms step 3 for a real series episode and a
    real movie against his real Plex deployment.
41. **Bug: Plex doesn't show channel logos in the guide**
    (`backend-developer`) — Andrew suspects this is about how Plex reads
    XMLTV `<icon>` (or a non-standard `<image>`) on `<channel>`.
    **No Plex access:** same rule as item 40. The developer can't reach
    Andrew's Plex server, so every Plex-side check is done by Andrew from
    step-by-step instructions the developer writes, saying what to run or
    look at and what to send back. Diagnose:
    (a) what `<channel><icon src>` we actually emit for his real lineup;
    many channels may have none if the M3U carried no `tvg-logo` (if the
    developer doesn't have his real `lineups.json`/generated XMLTV, ask
    Andrew for it with instructions on where to find it); (b) whether the
    URLs we do emit can be reached from the Plex server and return an image
    (e.g. an HDHomeRun-local or expired URL). This has to be checked from
    the Plex host itself, so give Andrew the exact command to run there
    (e.g. a `curl -I` against a few of the emitted URLs) and what output to
    report; (c) whether Plex needs anything beyond a standard
    `<icon src="...">`; (d) whether we should fall back to the
    SD station logo (`stationLogo`/`logo` in the cached station roster, and
    the SD logo endpoints noted in docs/schedulesdirect-integration.md)
    when a channel has no `logoUrl`. That last one is a product decision:
    SD logo URLs may need care around SD's image call limits and caching,
    so bring the options to Andrew before building it.
    Done means: channel logos appear in Andrew's real Plex guide. Andrew
    confirms this using verification steps the developer provides with the
    fix (including any Plex-side refresh needed for it to pick up new
    logos).
42. **Bug: episodes show no artwork in Plex** (`backend-developer`) —
    like item 41 but for programmes: we emit no `<programme><icon>` (or
    `<image>`) today. Diagnose what Plex reads for programme artwork, and
    what SD offers for it (program artwork / `hasImageArtwork`, the
    `/metadata/programs` endpoint and image URLs, plus any image-request
    limits and caching SD expects). Expect this to need new `sd_client/`
    calls and caching in `cache/sd/`, so write up the approach and its SD
    call cost and bring it to Andrew before building. Likely depends on
    item 40 (series vs. episode IDs decide which artwork applies).
    **No Plex access:** same rule as items 40 and 41. The developer (and
    any Claude agent working this item) has no direct access to Andrew's
    Plex server and must not try to reach it. Every Plex-side check
    (whether Plex shows programme artwork, what it shows for a specific
    programme, whether the Plex host can fetch the image URLs we emit, Plex
    logs) is done by Andrew from step-by-step instructions the developer
    writes. Those instructions say exactly what to look at or run (e.g. a
    `curl -I` from the Plex host against a few emitted image URLs), which
    programmes to check (by name and air time from the generated XMLTV),
    and what to send back (screenshots, exact text, command output).
    Diagnose as far as possible from the code, cached SD data, and the
    generated XMLTV first, then ask for only what's still missing.
    Done means: series/episode artwork appears in Andrew's real Plex guide
    without breaking SD's call limits. Andrew confirms this using
    verification steps the developer provides with the fix (including any
    Plex-side refresh needed for it to pick up new artwork).
