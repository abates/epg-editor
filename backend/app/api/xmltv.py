"""`/xmltv/*` — read-only serving of already-generated XMLTV files.

Reserved top-level prefix (see CLAUDE.md's "Reserved URL path prefixes") —
registered directly on the FastAPI app in `app.main`, not nested under
`/api`. Per CLAUDE.md, XMLTV is never generated on-the-fly per request:
this router only ever reads a file `services.xmltv` already wrote (via
`services.xmltv.get_xmltv_output_path`, which itself delegates to
`storage.output`) — this module makes no direct storage calls, per
CLAUDE.md's module-layering rule (`api/` -> `services/` -> `storage/`). If
generation hasn't run yet, it 404s rather than generating inline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.xmltv import get_xmltv_output_path

router = APIRouter(tags=["xmltv"])


@router.get("/xmltv/{lineup_id}.xml")
@router.head("/xmltv/{lineup_id}.xml", include_in_schema=False)
def get_xmltv(lineup_id: str) -> FileResponse:
    """Serve a lineup's already-generated XMLTV file.

    Also answers `HEAD` (unlike plain `@router.get`, which only registers
    `GET`) so clients can check whether a lineup's file has been generated
    yet without pulling the full body — `FileResponse` already omits the
    body on `HEAD` while still returning the same status/headers as `GET`.

    Registered as two stacked decorators (`@router.get` + `@router.head`)
    rather than `@router.api_route(..., methods=["GET", "HEAD"])`: the
    latter gives GET and HEAD the same auto-derived operation ID, which
    FastAPI warns about as a duplicate when building the OpenAPI schema
    (invalid per the OpenAPI spec) — confirmed that an explicit
    `operation_id=` on `api_route` does *not* fix this, since both methods
    still land on one `APIRoute` object. The HEAD operation is excluded
    from the schema (`include_in_schema=False`) since it's purely a
    same-body existence-check variant of the GET operation, not a
    separately documented capability.
    """
    try:
        path = get_xmltv_output_path(lineup_id)
    except ValueError:
        # `lineup_id` sanitized to an unsafe path segment (e.g. `..`) — no
        # real path-traversal risk (the sanitizer already prevented that),
        # this is purely about returning 404 instead of a 500 for a
        # malformed id that could never have a generated file anyway.
        path = None
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"no generated XMLTV file for lineup {lineup_id!r} yet",
        )
    return FileResponse(path, media_type="application/xml")
