"""APScheduler wiring for the periodic SD refresh job (Phase 5, items 29-31).

Wired into `app.main`'s `lifespan` context manager: the scheduler starts
when the app starts and shuts down when the app shuts down, alongside the
existing `ensure_data_dirs()` call. The job itself is thin — it constructs
an `SdClient` and calls straight into `app.services.refresh
.refresh_all_lineups`, the exact same function the manual `POST
/api/refresh-now` endpoint (`app.api.refresh`) calls — per CLAUDE.md's
"jobs are thin, call into services/" rule.

Refresh interval: `EPG_EDITOR_REFRESH_INTERVAL`, a number of **hours**
(deliberately not `EPG_EDITOR_REFRESH_INTERVAL_HOURS` — the product owner
specifically wants the bare name, with the unit documented in prose
wherever it's referenced, per docs/backlog.md item 31's resolution).
Defaults to 12 hours. Clamped up to a 1-hour floor (not rejected) if
configured lower, per SchedulesDirect's own documented request not to sync
more than once an hour (docs/schedulesdirect-integration.md) — clamping
rather than raising on startup means a misconfigured env var degrades to
"syncs somewhat more often than ideal" instead of crashing the whole app.
Likewise clamped *down* to a 720-hour (30-day) ceiling if configured
absurdly high (e.g. `1e9`, `1e12`): APScheduler's `IntervalTrigger` does its
own date arithmetic internally and raises `OverflowError` for an interval
that many hours out, which would otherwise crash `create_scheduler()` (and
thus app startup) the same way the non-finite case above does. 30 days is
just a generous-but-safe ceiling — not a meaningful product decision — picked
to be comfortably larger than any real refresh cadence while staying well
inside what `datetime`/APScheduler's internals can add to "now" without
overflowing.
"""

from __future__ import annotations

import logging
import math
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.sd_client.client import SdClient, SdClientError, SdCredentialsNotConfiguredError
from app.services.refresh import refresh_all_lineups

logger = logging.getLogger(__name__)

#: See module docstring for why this intentionally has no `_HOURS` suffix.
REFRESH_INTERVAL_ENV_VAR = "EPG_EDITOR_REFRESH_INTERVAL"

#: Default refresh interval, in hours, when the env var isn't set.
DEFAULT_REFRESH_INTERVAL_HOURS = 12

#: Floor on the refresh interval, in hours — see module docstring.
MIN_REFRESH_INTERVAL_HOURS = 1

#: Ceiling on the refresh interval, in hours (30 days) — see module
#: docstring. Purely a crash-prevention bound on `IntervalTrigger`'s
#: internal date arithmetic, not a meaningful product limit.
MAX_REFRESH_INTERVAL_HOURS = 24 * 30

#: Stable id for the single recurring refresh job, so tests/ops tooling can
#: look it up on the scheduler (`scheduler.get_job(JOB_ID)`) without relying
#: on job list ordering.
JOB_ID = "sd-refresh"
JOB_NAME = "SchedulesDirect refresh + XMLTV regeneration"


def get_refresh_interval_hours() -> float:
    """Resolve the configured refresh interval, in hours.

    Reads `EPG_EDITOR_REFRESH_INTERVAL` fresh from the environment on every
    call (rather than caching at import time) so tests can
    `monkeypatch.setenv` and get a different value without reloading this
    module. Falls back to `DEFAULT_REFRESH_INTERVAL_HOURS` for an unset or
    non-numeric value; clamps anything below `MIN_REFRESH_INTERVAL_HOURS`
    up to that floor. Either case logs a warning rather than failing
    silently or crashing startup. Also clamps anything above
    `MAX_REFRESH_INTERVAL_HOURS` down to that ceiling, for the same
    crash-prevention reason (see module docstring).
    """
    raw = os.environ.get(REFRESH_INTERVAL_ENV_VAR)
    if not raw:
        return float(DEFAULT_REFRESH_INTERVAL_HOURS)
    try:
        hours = float(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not a valid number (of hours); using the default of %s hours",
            REFRESH_INTERVAL_ENV_VAR,
            raw,
            DEFAULT_REFRESH_INTERVAL_HOURS,
        )
        return float(DEFAULT_REFRESH_INTERVAL_HOURS)
    if not math.isfinite(hours):
        # `float("nan")`/`float("inf")` (or an overflow like `1e400`, which
        # Python's `float()` silently turns into `inf`) both parse
        # successfully above but would later blow up `IntervalTrigger`
        # (`ValueError` for nan, `OverflowError` for inf) inside
        # `create_scheduler()`, which runs during the app's `lifespan` —
        # crashing startup instead of degrading to the default, contrary to
        # this function's own contract.
        logger.warning(
            "%s=%r is not a finite number (of hours); using the default of %s hours",
            REFRESH_INTERVAL_ENV_VAR,
            raw,
            DEFAULT_REFRESH_INTERVAL_HOURS,
        )
        return float(DEFAULT_REFRESH_INTERVAL_HOURS)
    if hours < MIN_REFRESH_INTERVAL_HOURS:
        logger.warning(
            "%s=%s hours is below the %s-hour minimum (SchedulesDirect asks "
            "clients not to sync more than once an hour) — clamping up to %s",
            REFRESH_INTERVAL_ENV_VAR,
            hours,
            MIN_REFRESH_INTERVAL_HOURS,
            MIN_REFRESH_INTERVAL_HOURS,
        )
        return float(MIN_REFRESH_INTERVAL_HOURS)
    if hours > MAX_REFRESH_INTERVAL_HOURS:
        logger.warning(
            "%s=%s hours is above the %s-hour (30-day) ceiling (APScheduler's "
            "IntervalTrigger can't handle an interval that far out) — "
            "clamping down to %s",
            REFRESH_INTERVAL_ENV_VAR,
            hours,
            MAX_REFRESH_INTERVAL_HOURS,
            MAX_REFRESH_INTERVAL_HOURS,
        )
        return float(MAX_REFRESH_INTERVAL_HOURS)
    return hours


async def run_scheduled_refresh() -> None:
    """The APScheduler job body: run the global refresh pipeline once.

    Constructs its own real `SdClient` via `SdClient.from_env()` — the
    scheduler has no per-request dependency-injection container to lean on
    the way `api/refresh.py` does. If `SD_USERNAME`/`SD_PASSWORD` aren't
    configured, this logs a clear, specific warning and returns (skipping
    this cycle) rather than letting `SdCredentialsNotConfiguredError`
    propagate — APScheduler would catch an uncaught exception and log it
    without crashing the scheduler either way, but a deliberate, specific
    message here is far more actionable than APScheduler's generic
    job-error log line, and makes this behavior independently testable.
    Any other `SdClientError` (e.g. an auth/account-level failure raised
    out of `refresh_all_lineups` — see that function's docstring for why
    those propagate rather than being collected) is likewise logged and
    swallowed here: one failed cycle must not take down the scheduler or
    the app, since the next scheduled run (or a manual "refresh now") gets
    another chance.
    """
    try:
        sd_client = SdClient.from_env()
    except SdCredentialsNotConfiguredError:
        logger.warning(
            "Skipping scheduled SchedulesDirect refresh: SD_USERNAME/SD_PASSWORD "
            "are not configured"
        )
        return

    async with sd_client:
        try:
            result = await refresh_all_lineups(sd_client)
        except SdClientError as exc:
            logger.error("Scheduled SchedulesDirect refresh failed: %s", exc)
            return

    logger.info(
        "Scheduled SchedulesDirect refresh complete: %d lineup(s) processed "
        "(%d regenerated), %d station roster(s) refreshed (%d skipped), "
        "%d schedule-day(s) refetched (%d skipped unchanged), %d program(s) "
        "fetched, %d error(s)",
        result.lineupsProcessed,
        result.lineupsRegenerated,
        result.stationRostersRefreshed,
        result.stationRostersSkipped,
        result.scheduleDaysRefetched,
        result.scheduleDaysSkippedUnchanged,
        result.programsFetched,
        len(result.errors),
    )


def create_scheduler() -> AsyncIOScheduler:
    """Build (but don't start) the app's refresh `AsyncIOScheduler`.

    `AsyncIOScheduler`, not `BackgroundScheduler`: the job body
    (`run_scheduled_refresh`) is a coroutine awaiting `SdClient`'s async
    HTTP calls, so it needs to run on the same asyncio event loop uvicorn
    already drives, rather than APScheduler's thread-pool-based scheduler
    needing its own sync-to-async bridge.

    Returns a fresh instance per call (no module-level singleton) so
    `app.main`'s `lifespan` owns its lifecycle explicitly (start on
    startup, `shutdown()` on app shutdown) and tests can build/inspect
    their own scheduler against their own env vars with no shared global
    state to reset between tests. The job is registered but not started —
    call `.start()` on the result.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_refresh,
        trigger=IntervalTrigger(hours=get_refresh_interval_hours()),
        id=JOB_ID,
        name=JOB_NAME,
        # Deliberately no `next_run_time=...`/immediate first run: the job
        # fires for the first time one full interval after the scheduler
        # starts, same as every subsequent run. Andrew's manual "refresh
        # now" endpoint/button covers "I want this to happen right away"
        # without needing the scheduled job itself to behave differently
        # on startup.
    )
    return scheduler
