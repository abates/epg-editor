"""M3U import routes under `/api/lineups` (see `app.services.m3u`).

Thin HTTP layer only: decodes/size-caps the uploaded file and maps
service-layer exceptions to HTTP status codes; all parsing and merge logic
lives in `app.services.m3u` (see CLAUDE.md's backend module layout).
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.models.lineup import Lineup
from app.models.m3u import M3UEntry, M3UImportResult
from app.services import lineups as lineups_service
from app.services import m3u as m3u_service
from app.services import suggestions as suggestions_service

router = APIRouter(tags=["m3u"])

#: A homelab M3U playlist (a plain-text list of channel entries) is nowhere
#: near this size even with a few thousand channels — this guards only
#: against an absurdly large accidental upload, not a limit a correct
#: client would ever actually hit.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB


class M3UImportResponse(BaseModel):
    """Response body for both M3U import endpoints.

    `lineup` is the full, up-to-date lineup (including its merged channel
    list) after the import; `result` is the `added`/`updated`/
    `flaggedMissing` breakdown of what changed in this import specifically.
    """

    lineup: Lineup
    result: M3UImportResult


async def _read_and_decode_upload(file: UploadFile) -> str:
    """Read an uploaded file, enforcing the size cap and decoding as text.

    Reads at most `MAX_UPLOAD_BYTES + 1` bytes — one byte past the cap —
    rather than `file.read()` (the whole upload) followed by a length
    check. That ordering would only produce a clean 400 *after* already
    buffering an arbitrarily large upload in memory, defeating the point
    of having a cap at all; reading one byte past the limit is enough to
    detect "too large" without ever buffering more than
    `MAX_UPLOAD_BYTES + 1` bytes regardless of the real upload size.

    Tries UTF-8 first (a leading BOM survives decoding — `parse_m3u`
    strips it), then falls back to latin-1, which can decode *any* byte
    sequence, rather than letting an unhandled `UnicodeDecodeError` escape
    as a 500 for a playlist saved in some other 8-bit encoding. M3U is
    plain text with no binary payload, so a best-effort decode here is
    preferable to a hard failure; genuinely garbled content still gets
    rejected by `parse_m3u`'s `#EXTM3U`-header check right after.
    """
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"uploaded file exceeds the {MAX_UPLOAD_BYTES}-byte limit",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _parse_or_400(text: str) -> list[M3UEntry]:
    try:
        return m3u_service.parse_m3u(text)
    except m3u_service.M3UParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lineups/import-m3u", response_model=M3UImportResponse, status_code=201)
async def import_m3u_new_lineup(
    name: str = Form(...), file: UploadFile = File(...)
) -> M3UImportResponse:
    """Create a new `m3u`-sourced lineup from an uploaded M3U playlist.

    Multipart form fields: `name` (the new epg-editor lineup's name,
    string) and `file` (the `.m3u` playlist). The new lineup starts with
    no channels, so every parsed entry comes back in `result.added`.

    400 if the upload is too large or isn't parseable as M3U at all.

    A brand-new import's channels have no `mapping`/suggestions yet, so
    enriching before returning is a no-op in practice today — applied
    anyway for consistency with `import_m3u_existing_lineup` below and
    every `Lineup`-returning route in `api/lineups.py` (see the
    suggestion-enrichment follow-on review finding).
    """
    text = await _read_and_decode_upload(file)
    entries = _parse_or_400(text)
    # `create_lineup_from_m3u` takes `storage/lineups.py`'s process-wide
    # lock and does synchronous file I/O; run it off the event loop (this
    # route is `async def` only because of the earlier `await file.read()`
    # — see `app.services.m3u` module docstring / CLAUDE.md module
    # layering) so a merge in progress never stalls unrelated requests
    # (e.g. `/xmltv/*` serving) for its duration.
    lineup, result = await run_in_threadpool(
        m3u_service.create_lineup_from_m3u, name, entries
    )
    return M3UImportResponse(
        lineup=suggestions_service.enrich_lineup_suggestions(lineup), result=result
    )


@router.post("/lineups/{lineup_id}/import-m3u", response_model=M3UImportResponse)
async def import_m3u_existing_lineup(
    lineup_id: str, file: UploadFile = File(...)
) -> M3UImportResponse:
    """Re-import an uploaded M3U playlist into an existing `m3u`-sourced
    lineup, merging by `tvgId` (fallback: channel number) — see
    `app.services.m3u.import_m3u_entries` for the full merge contract.

    Multipart form field: `file` (the `.m3u` playlist).

    404 if `lineup_id` doesn't exist. 400 if the upload is too large,
    isn't parseable as M3U at all, or the target lineup's `source` isn't
    `"m3u"` (re-importing an M3U file into a manually-curated lineup is
    intentionally unsupported — see `app.services.m3u.import_m3u_entries`'s
    docstring).

    A re-import preserves an existing channel's `mapping` (including any
    pending `suggestions`) untouched on update, so this response can
    legitimately carry stale-looking (but accurate) suggestion display data
    for an unmapped channel — enriched before returning for the same
    reason as every other `Lineup`-returning route (see the suggestion-
    enrichment follow-on review finding).
    """
    text = await _read_and_decode_upload(file)
    entries = _parse_or_400(text)
    try:
        # Same event-loop/threadpool rationale as the other route above;
        # `import_m3u_entries` also returns the lineup snapshot from the
        # same atomic transaction as `result` (see its docstring) rather
        # than this route doing a second, separate `get_lineup` read.
        lineup, result = await run_in_threadpool(
            m3u_service.import_m3u_entries, lineup_id, entries
        )
    except lineups_service.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except lineups_service.ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return M3UImportResponse(
        lineup=suggestions_service.enrich_lineup_suggestions(lineup), result=result
    )
