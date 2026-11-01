"""Typed async client for SchedulesDirect's JSON API.

The only module that issues HTTP requests to SchedulesDirect — everything
else in this app goes through `SdClient`. Knows nothing about epg-editor's
own domain concepts (`Lineup`, `Channel`, mappings); it's a thin, reusable
wrapper that could live outside this app.

The HTTP transport is injected (an `httpx.AsyncClient` passed in by the
caller) rather than constructed internally against a hardcoded base URL, so
tests can swap in `httpx.MockTransport` and never touch the real network —
see `tests/sd_client/test_client.py`.

`SD_USERNAME`/`SD_PASSWORD` are read from the environment by default (never
written to `config/lineups.json`, never logged) but can be passed explicitly
to the constructor, which is what tests do with fake credentials.

Every public method here funnels its HTTP call through `_request()`, which
translates *transport*-level failures (timeouts, connection errors, any
other `httpx.HTTPError`) and non-2xx HTTP responses into `SdClientError`.
JSON decoding and Pydantic validation of the response body are likewise
wrapped (`_decode_json()` / `_validate()`) so a malformed/non-JSON body or a
response that doesn't match the expected shape also comes out as
`SdClientError` rather than a raw `json.JSONDecodeError` or
`pydantic.ValidationError` escaping to callers. This matters because
`services/refresh.py` only catches `SdClientError` per-station — anything else
would abort the whole sync instead of being recorded against just that
station.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from app.models.sd import (
    SdAccountLineupsResponse,
    SdAddRemoveLineupResponse,
    SdLineupStationsResponse,
    SdProgram,
    SdScheduleMd5Response,
    SdScheduleRequest,
    SdStationSchedule,
    SdStatusResponse,
    SdTokenResponse,
)

#: SD's documented JSON Service API version path.
DEFAULT_BASE_URL = "https://json.schedulesdirect.org/20141201"

#: SD tokens are valid for roughly 24h per docs/schedulesdirect-integration.md.
TOKEN_LIFETIME = timedelta(hours=24)

#: Refresh a bit before actual expiry to avoid a request racing expiry.
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)

#: Generous timeout for real network calls to SD's endpoints (`/schedules`
#: and `/programs` in particular can be slow against a real account/large
#: lineup). Only applies when `SdClient.from_env()` constructs its own
#: `httpx.AsyncClient()` — httpx's default of 5s was flagged during review
#: as the first thing likely to break against real SD traffic.
DEFAULT_HTTP_TIMEOUT: float = 30.0

#: HTTP statuses that represent an auth/account-wide SD failure (bad/expired
#: token, blocked account, etc.) rather than a problem specific to one
#: station's data.
_AUTH_HTTP_STATUSES = frozenset({401, 403})

#: SD's documented hard cap on `programID`s per `POST /programs` request.
#: `get_programs` chunks internally so callers (`services/refresh.py`) can
#: pass however many program IDs the guide window actually needs without
#: needing to know about this SD-specific limit themselves.
PROGRAMS_REQUEST_CHUNK_SIZE = 5000

#: SD's documented error "code" family for token/account-level problems
#: (e.g. TOKEN_MISSING, TOKEN_EXPIRED, ACCOUNT_EXPIRED, ACCOUNT_DISABLED,
#: ACCOUNT_LOCKOUT — see https://json.schedulesdirect.org/). SD's docs don't
#: enumerate this as cleanly as an HTTP status table, so this range is a
#: judgment call made during implementation, not a value lifted verbatim
#: from a spec page — revisit/widen it if real-account testing turns up an
#: account-level failure whose code falls outside 4000-4999.
_AUTH_SD_CODE_RANGE = range(4000, 5000)


class SdClientError(Exception):
    """Raised for a non-2xx SD HTTP response or an SD-level error code.

    Also raised (without a `status_code`/`sd_code`) for transport-level
    failures (timeouts, connection errors), non-JSON response bodies, and
    responses that fail Pydantic validation against the expected SD shape —
    see `SdClient._request()`/`_decode_json()`/`_validate()`. Callers that
    only want "did something about talking to SD go wrong" can catch this
    one type regardless of which of those cases it was.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        sd_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.sd_code = sd_code

    @property
    def is_auth_error(self) -> bool:
        """Whether this looks like an auth/account-wide failure.

        Used by `services/refresh.py` to distinguish "the whole account/token
        is broken, stop burning SD calls and surface this clearly" from "this
        one station's data had a problem, record it and move on to the next
        station." See `_AUTH_HTTP_STATUSES`/`_AUTH_SD_CODE_RANGE` above for
        what's currently considered auth/account-level.
        """
        if self.status_code in _AUTH_HTTP_STATUSES:
            return True
        if self.sd_code is not None and self.sd_code in _AUTH_SD_CODE_RANGE:
            return True
        return False


class SdCredentialsNotConfiguredError(SdClientError):
    """Raised by `SdClient.from_env()` when credentials aren't set.

    A distinct, specific subclass of `SdClientError` (rather than that
    generic base, or a bare crash) so a caller like `api/dependencies.py`'s
    `get_sd_client` FastAPI dependency can map *this* case to a clean,
    unambiguous 4xx (e.g. 503 "SchedulesDirect credentials are not
    configured") instead of a confusing 500 — while code that only cares
    about "something about SD failed" can still catch `SdClientError`
    broadly and get this too.
    """


class SdClient:
    """Thin async wrapper around SchedulesDirect's JSON API."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        username: str | None = None,
        password: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._http = http_client
        self._username = username if username is not None else os.environ.get("SD_USERNAME")
        self._password = password if password is not None else os.environ.get("SD_PASSWORD")
        self._base_url = base_url.rstrip("/")

        # In-memory token cache only. Persisting the session token to
        # `cache/sd/` would require this module to depend on `storage/`,
        # which would cut across CLAUDE.md's one-directional module layering
        # (`services/` -> `sd_client/` + `storage/`, not `sd_client/` ->
        # `storage/`). An in-memory cache already satisfies "cached in
        # memory and/or under cache/sd/" from the architecture notes, and
        # keeps this module a dependency-free, reusable SD wrapper.
        self._cached_token: str | None = None
        self._cached_token_expires_at: datetime | None = None

    @classmethod
    def from_env(
        cls,
        http_client: httpx.AsyncClient | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float | httpx.Timeout = DEFAULT_HTTP_TIMEOUT,
    ) -> "SdClient":
        """Construct a real `SdClient` using env-var SD credentials.

        Per CLAUDE.md, `SD_USERNAME`/`SD_PASSWORD` are the *only* source of
        SD credentials and are never written to `config/lineups.json` or
        logged — this reads them from the environment and nowhere else.
        Raises `SdCredentialsNotConfiguredError` immediately if either is
        missing/empty, rather than deferring to a lazy, harder-to-diagnose
        failure the first time `get_token()` happens to be called — callers
        (`api/dependencies.py`'s `get_sd_client`) turn that into a clean 4xx.

        `http_client` defaults to a fresh `httpx.AsyncClient(timeout=timeout)`
        (the real network) if not supplied. This is the one and only place
        in the codebase that is allowed to construct a real client — every
        other construction of `SdClient` (including every test) must pass
        its own transport explicitly, per `sd_client/`'s module docstring.
        Nothing in the test suite calls `from_env()` with a real transport:
        tests either pass their own `httpx.MockTransport`-backed client
        explicitly, or (for the missing-credentials case) never get far
        enough to construct one at all.

        `timeout` is only used when `http_client` isn't supplied — it exists
        so callers (e.g. `api/dependencies.py`'s `get_sd_client` FastAPI
        dependency) can get a fully configured, ready-to-use `SdClient`
        back without ever importing or constructing `httpx.AsyncClient`
        themselves. Use the returned
        client as an async context manager (`async with`) or call
        `aclose()` explicitly when done, so the underlying connection pool
        is cleaned up.
        """
        username = os.environ.get("SD_USERNAME")
        password = os.environ.get("SD_PASSWORD")
        if not username or not password:
            raise SdCredentialsNotConfiguredError(
                "SchedulesDirect credentials are not configured: both "
                "SD_USERNAME and SD_PASSWORD environment variables must be "
                "set"
            )
        resolved_http_client = (
            http_client if http_client is not None else httpx.AsyncClient(timeout=timeout)
        )
        return cls(
            resolved_http_client,
            username=username,
            password=password,
            base_url=base_url,
        )

    async def __aenter__(self) -> "SdClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP transport.

        Mainly meaningful for a client constructed via `from_env()`, which
        owns a real `httpx.AsyncClient`; calling it on a test-constructed,
        `MockTransport`-backed client is also safe (just closes that
        transport), so this is fine to call unconditionally.
        """
        await self._http.aclose()

    async def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid SD session token, fetching/refreshing as needed."""
        if not force_refresh and self._cached_token is not None:
            assert self._cached_token_expires_at is not None
            if datetime.now(timezone.utc) < self._cached_token_expires_at - TOKEN_REFRESH_MARGIN:
                return self._cached_token

        if not self._username or not self._password:
            raise SdClientError("SD_USERNAME/SD_PASSWORD are not configured")

        hashed_password = hashlib.sha1(self._password.encode("utf-8")).hexdigest()  # noqa: S324 — SD-mandated scheme, not for secret storage
        response = await self._request(
            "POST",
            f"{self._base_url}/token",
            json={"username": self._username, "password": hashed_password},
        )
        parsed = self._validate(SdTokenResponse, self._decode_json(response))
        if parsed.code != 0 or not parsed.token:
            raise SdClientError(
                parsed.message or "SD token request failed", sd_code=parsed.code
            )

        self._cached_token = parsed.token
        self._cached_token_expires_at = datetime.now(timezone.utc) + TOKEN_LIFETIME
        return self._cached_token

    async def _auth_headers(self) -> dict[str, str]:
        return {"token": await self.get_token()}

    async def list_account_lineups(self) -> SdAccountLineupsResponse:
        """`GET /lineups` — the account's currently-subscribed SD lineups.

        SD can return HTTP 200 with an error payload (e.g.
        `{"code": 4003, "response": "ACCOUNT_LOCKOUT"}`) for an account-level
        failure. Every field on `SdAccountLineupsResponse` is optional, so
        that would otherwise validate cleanly as "zero lineups" instead of
        surfacing the error — explicitly check `code` the same way
        `add_account_lineup`/`remove_account_lineup` already do.
        """
        response = await self._request(
            "GET", f"{self._base_url}/lineups", headers=await self._auth_headers()
        )
        parsed = self._validate(SdAccountLineupsResponse, self._decode_json(response))
        if parsed.code not in (0, None):
            raise SdClientError(
                parsed.message or parsed.response or "SD account lineups request failed",
                sd_code=parsed.code,
            )
        return parsed

    async def add_account_lineup(self, lineup_id: str) -> SdAddRemoveLineupResponse:
        """`PUT /lineups/{lineupID}` — subscribe the account to a lineup."""
        response = await self._request(
            "PUT", f"{self._base_url}/lineups/{lineup_id}", headers=await self._auth_headers()
        )
        parsed = self._validate(SdAddRemoveLineupResponse, self._decode_json(response))
        if parsed.code != 0:
            raise SdClientError(
                parsed.message or "add lineup failed", sd_code=parsed.code
            )
        return parsed

    async def remove_account_lineup(self, lineup_id: str) -> SdAddRemoveLineupResponse:
        """`DELETE /lineups/{lineupID}` — unsubscribe the account from a lineup."""
        response = await self._request(
            "DELETE", f"{self._base_url}/lineups/{lineup_id}", headers=await self._auth_headers()
        )
        parsed = self._validate(SdAddRemoveLineupResponse, self._decode_json(response))
        if parsed.code != 0:
            raise SdClientError(
                parsed.message or "remove lineup failed", sd_code=parsed.code
            )
        return parsed

    async def get_account_status(self) -> SdStatusResponse:
        """`GET /status` — account info, including the account-wide lineup-
        slot limit (`account.maxLineups`).

        Verified against SchedulesDirect/JSON-Service's wiki ("Getting
        status" section of API-20141201.md) during implementation — see
        `SdAccountStatusInfo`'s docstring for the distinction from
        `SdAddRemoveLineupResponse.changesRemaining`.

        Like `list_account_lineups`, SD can return HTTP 200 with an
        error-coded body (every field on `SdStatusResponse` is optional, so
        that would otherwise validate as an under-populated "no data"
        result — e.g. `maxLineups=None, lineups=[]` — rather than raising).
        Explicitly check `code` so that case surfaces as an `SdClientError`
        instead.
        """
        response = await self._request(
            "GET", f"{self._base_url}/status", headers=await self._auth_headers()
        )
        parsed = self._validate(SdStatusResponse, self._decode_json(response))
        if parsed.code not in (0, None):
            raise SdClientError(
                parsed.message or parsed.response or "SD account status request failed",
                sd_code=parsed.code,
            )
        return parsed

    async def get_lineup_stations(self, lineup_id: str) -> SdLineupStationsResponse:
        """`GET /lineups/{lineupID}` — a lineup's station roster (candidate pool).

        Like `list_account_lineups`/`get_account_status`, SD can return HTTP
        200 with an error-coded body (e.g. `{"code": 2100, "response":
        "LINEUP_NOT_FOUND"}`) — every field on `SdLineupStationsResponse` is
        optional, so that would otherwise validate as an empty-but-successful
        roster instead of raising. Explicitly check `code` so that case
        surfaces as an `SdClientError` instead (reviewer finding: a good
        cached roster must not get silently overwritten with an empty one).
        """
        response = await self._request(
            "GET", f"{self._base_url}/lineups/{lineup_id}", headers=await self._auth_headers()
        )
        parsed = self._validate(SdLineupStationsResponse, self._decode_json(response))
        if parsed.code not in (0, None):
            raise SdClientError(
                parsed.message or parsed.response or "SD lineup stations request failed",
                sd_code=parsed.code,
            )
        return parsed

    async def get_schedules(
        self, requests: list[SdScheduleRequest]
    ) -> list[SdStationSchedule]:
        """`POST /schedules` — per-station/day schedules, each with an md5.

        Callers (`services/`) should request only stations actually mapped
        to a channel — never speculatively fetch an entire lineup's roster.

        A healthy response body is a JSON array of per-station/day schedule
        objects. SD can also report an account-wide failure (e.g. a token
        that was valid when fetched but has since been revoked) as a single
        JSON *object* with its own `code` instead of the expected array —
        `_raise_for_top_level_sd_error` turns that into an `SdClientError`
        with `sd_code` set (so `SdClientError.is_auth_error` can classify
        it) rather than letting list-iteration/validation fail confusingly
        on the unexpected shape. A per-station/day *item* reporting its own
        non-zero `code` (e.g. 7100 SCHEDULE_QUEUED — the schedule isn't
        ready yet) is a data-quality problem, not a transport/shape one, so
        it's intentionally left for `services/refresh.py` to inspect via
        `SdStationSchedule.code` rather than raised here.
        """
        body = [item.model_dump(exclude_none=True) for item in requests]
        response = await self._request(
            "POST", f"{self._base_url}/schedules", json=body, headers=await self._auth_headers()
        )
        data = self._decode_json(response)
        self._raise_for_top_level_sd_error(data)
        return [self._validate(SdStationSchedule, item) for item in data]

    async def get_schedule_md5s(
        self, requests: list[SdScheduleRequest]
    ) -> SdScheduleMd5Response:
        """`POST /schedules/md5` — per-station/day md5 + lastModified only.

        The same request body shape as `get_schedules` (an array of
        `{stationID, date[]}`), but a much lighter response: no program
        data, just an md5/lastModified per station/day so a caller can
        decide whether a full `get_schedules` re-fetch is actually needed —
        this is the mechanism docs/backlog.md item 29 calls for ("skip
        unchanged schedules"), used by `services/refresh.py`.

        Per SD's docs (verified during Phase 5 implementation — see
        `SdScheduleMd5Response`'s docstring), the response is a JSON object
        keyed by `stationID` then `date`, not an array — unlike
        `get_schedules`/`get_programs`. SD's "single error object instead
        of the expected shape" account-wide-failure pattern still applies
        (e.g. a revoked token discovered mid-batch), so this still routes
        through `_raise_for_top_level_sd_error` before validation. SD
        documents a hard cap of 5000 stationIDs per request; callers are
        responsible for chunking if they might exceed that (see
        `services/refresh.py`'s equivalent un-chunked `get_programs` call for
        the precedent of deferring that until a real lineup is large enough
        to hit it).
        """
        body = [item.model_dump(exclude_none=True) for item in requests]
        response = await self._request(
            "POST",
            f"{self._base_url}/schedules/md5",
            json=body,
            headers=await self._auth_headers(),
        )
        data = self._decode_json(response)
        self._raise_for_top_level_sd_error(data)
        return self._validate(SdScheduleMd5Response, data)

    async def get_programs(self, program_ids: list[str]) -> list[SdProgram]:
        """`POST /programs` — batched program metadata lookup by program ID.

        See `get_schedules`'s docstring: the same "single error object
        instead of the expected array" possibility applies here too.

        SD documents a hard cap of `PROGRAMS_REQUEST_CHUNK_SIZE` program IDs
        per request; a caller like `services/refresh.py` can end up with far
        more than that across every mapped station's guide window on a large
        real account, so this chunks internally (one `POST /programs` call
        per `PROGRAMS_REQUEST_CHUNK_SIZE`-sized slice of `program_ids`,
        results concatenated) rather than pushing that SD-specific limit up
        onto callers — unlike `get_schedule_md5s`, which currently still
        defers chunking to its caller (see that method's docstring); this
        one makes the cleaner call to own it here since there's no
        meaningful "partial batch" request shape a caller would want control
        over.
        """
        programs: list[SdProgram] = []
        for start in range(0, len(program_ids), PROGRAMS_REQUEST_CHUNK_SIZE):
            chunk = program_ids[start : start + PROGRAMS_REQUEST_CHUNK_SIZE]
            response = await self._request(
                "POST",
                f"{self._base_url}/programs",
                json=chunk,
                headers=await self._auth_headers(),
            )
            data = self._decode_json(response)
            self._raise_for_top_level_sd_error(data)
            programs.extend(self._validate(SdProgram, item) for item in data)
        return programs

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Perform one HTTP request, translating failures into `SdClientError`.

        Catches every `httpx.HTTPError` subclass — timeouts
        (`httpx.ReadTimeout`, `httpx.ConnectTimeout`), connection failures
        (`httpx.ConnectError`), protocol errors, etc. — so a transport-level
        failure comes out the same way a non-2xx HTTP response already did
        (`_raise_for_http_error`, called here too): as an `SdClientError`.
        This matters because `services/refresh.py` only catches `SdClientError`
        per-station; an uncaught `httpx.HTTPError` would otherwise abort the
        entire sync instead of being recorded against just that station.
        """
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise SdClientError(f"SD request failed: {exc}") from exc
        self._raise_for_http_error(response)
        return response

    @staticmethod
    def _decode_json(response: httpx.Response) -> Any:
        """Decode a response body as JSON, wrapping decode failures.

        SD is expected to always return JSON, but a proxy/outage/partial
        response in front of SD could return an HTML error page or a
        truncated body with a 200 status — treat that as an `SdClientError`
        rather than letting the raw `json.JSONDecodeError` (a `ValueError`
        subclass) escape.
        """
        try:
            return response.json()
        except ValueError as exc:
            raise SdClientError(f"SD returned a non-JSON response body: {exc}") from exc

    @staticmethod
    def _validate(model: type[Any], data: Any) -> Any:
        """Validate `data` against a Pydantic SD response model.

        Wraps `pydantic.ValidationError` (e.g. SD's response shape not
        matching what we modeled) into `SdClientError` for the same reason
        as `_decode_json`/`_request`: so `services/refresh.py`'s per-station
        `except SdClientError` actually catches it.
        """
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise SdClientError(
                f"SD response did not match the expected {model.__name__} shape: {exc}"
            ) from exc

    @staticmethod
    def _raise_for_top_level_sd_error(data: Any) -> None:
        """Raise if `data` looks like a single SD error object, not a list.

        `get_schedules`/`get_programs` normally return a JSON array; SD can
        instead return a single JSON object with its own `code` for an
        account-wide failure. See `get_schedules`'s docstring for more.
        """
        if isinstance(data, dict) and data.get("code") not in (0, None):
            raise SdClientError(
                data.get("message") or data.get("response") or "SD request failed",
                sd_code=data.get("code"),
            )

    @staticmethod
    def _raise_for_http_error(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise SdClientError(
                f"SD request failed with HTTP {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
