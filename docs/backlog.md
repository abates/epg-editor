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
    name/call sign/alt names; populate `mapping.suggestions` (recomputed,
    not accumulated).
22. **Bulk-accept** (`backend-developer`) — accept all suggestions ≥ fixed
    backend threshold (start at 0.85 — not a UI control).
23. **Frontend: suggestion review UI** (`frontend-developer`) — per-channel
    accept/reject, bulk-accept action, confidence display.
24. **Review** (`peer-reviewer`).

25. 🛑 **USER CHECKPOINT — real match quality**
    What to do: run suggestion generation against one of your real SD
    lineups and review the actual suggestions and scores produced for your
    real channels (not synthetic test data).
    Confirmed means: you're satisfied the 0.85 bulk-accept threshold is
    neither accepting bad matches nor requiring manual review of obviously
    correct ones for your real lineup. Adjust the fixed default if not, then
    re-review.
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
    and regenerating XMLTV; thin jobs calling into `services/`.
30. **Manual "refresh now"** (`backend-developer` + `frontend-developer`) —
    API endpoint running the same pipeline on demand, triggered from the UI.
31. **Decide refresh interval + env var name** (`backend-developer`) —
    propose default + name, confirm with Andrew (open decision per
    CLAUDE.md).
32. **Review** (`peer-reviewer`).

33. 🛑 **USER CHECKPOINT — real scheduled refresh**
    What to do: let the real app run with the scheduler active against your
    real SD account for at least one full refresh interval; separately,
    trigger "refresh now" manually.
    Confirmed means: refresh completed without errors, cache/output updated
    as expected, and no excessive SD API calls were made (md5 short-circuit
    is working).
    Development does not continue past this point until you confirm.
