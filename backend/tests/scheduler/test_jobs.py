"""Tests for `app.scheduler.jobs`: interval resolution, job registration,
and the scheduled job's own error handling (missing credentials / SD
failures must not crash the scheduler).

No real SD credentials or network are touched anywhere in this file.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scheduler import jobs as scheduler_jobs
from app.sd_client.client import SdClientError, SdCredentialsNotConfiguredError


def run(coro):
    return asyncio.run(coro)


# --- `get_refresh_interval_hours` --------------------------------------------


def test_default_interval_is_twelve_hours(monkeypatch):
    monkeypatch.delenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raising=False)
    assert scheduler_jobs.get_refresh_interval_hours() == 12


def test_interval_reads_configured_env_var(monkeypatch):
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, "6")
    assert scheduler_jobs.get_refresh_interval_hours() == 6


def test_interval_below_floor_is_clamped_up_to_one_hour(monkeypatch):
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, "0.1")
    assert scheduler_jobs.get_refresh_interval_hours() == scheduler_jobs.MIN_REFRESH_INTERVAL_HOURS
    assert scheduler_jobs.MIN_REFRESH_INTERVAL_HOURS == 1


@pytest.mark.parametrize("raw_value", ["1e9", "1e12"])
def test_interval_above_ceiling_is_clamped_down_to_thirty_days(monkeypatch, raw_value):
    """Regression test: a very large but finite interval (e.g. `1e9`,
    `1e12` hours) must be clamped down to `MAX_REFRESH_INTERVAL_HOURS`
    rather than passed through — `IntervalTrigger`'s internal date
    arithmetic raises `OverflowError` for an interval that many hours out,
    which would otherwise crash `create_scheduler()` during app startup."""
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raw_value)
    assert scheduler_jobs.get_refresh_interval_hours() == scheduler_jobs.MAX_REFRESH_INTERVAL_HOURS
    assert scheduler_jobs.MAX_REFRESH_INTERVAL_HOURS == 24 * 30


def test_interval_non_numeric_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, "not-a-number")
    assert scheduler_jobs.get_refresh_interval_hours() == scheduler_jobs.DEFAULT_REFRESH_INTERVAL_HOURS


@pytest.mark.parametrize("raw_value", ["nan", "inf", "-inf", "1e400"])
def test_interval_non_finite_falls_back_to_default_instead_of_crashing(monkeypatch, raw_value):
    """Regression test (Finding 4): `float("nan")`/`float("inf")` parse
    successfully but are not finite — `get_refresh_interval_hours()` must
    degrade to the default rather than returning them, since passing a
    non-finite value through to `IntervalTrigger` (inside
    `create_scheduler()`, which runs during app startup) raises `ValueError`
    (nan) or `OverflowError` (inf), crashing the whole app."""
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raw_value)
    assert scheduler_jobs.get_refresh_interval_hours() == scheduler_jobs.DEFAULT_REFRESH_INTERVAL_HOURS


@pytest.mark.parametrize("raw_value", ["nan", "inf", "1e400"])
def test_create_scheduler_does_not_crash_on_non_finite_interval(monkeypatch, raw_value):
    """End-to-end regression test: `create_scheduler()` (called from
    `app.main`'s `lifespan`) must not raise for a non-finite configured
    interval — it should fall back to the default interval instead."""
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raw_value)

    scheduler = scheduler_jobs.create_scheduler()
    job = scheduler.get_job(scheduler_jobs.JOB_ID)

    assert job is not None
    assert job.trigger.interval == timedelta(hours=scheduler_jobs.DEFAULT_REFRESH_INTERVAL_HOURS)


@pytest.mark.parametrize("raw_value", ["1e9", "1e12"])
def test_create_scheduler_does_not_crash_on_huge_interval(monkeypatch, raw_value):
    """End-to-end regression test: `create_scheduler()` must not raise
    `OverflowError` for a very large but finite configured interval — it
    should clamp to `MAX_REFRESH_INTERVAL_HOURS` instead."""
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raw_value)

    scheduler = scheduler_jobs.create_scheduler()
    job = scheduler.get_job(scheduler_jobs.JOB_ID)

    assert job is not None
    assert job.trigger.interval == timedelta(hours=scheduler_jobs.MAX_REFRESH_INTERVAL_HOURS)


# --- `create_scheduler` registers the job at the configured interval -------


def test_create_scheduler_registers_job_at_configured_interval(monkeypatch):
    monkeypatch.setenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, "6")

    scheduler = scheduler_jobs.create_scheduler()
    job = scheduler.get_job(scheduler_jobs.JOB_ID)

    assert job is not None
    assert job.trigger.interval == timedelta(hours=6)
    assert job.func is scheduler_jobs.run_scheduled_refresh


def test_app_startup_registers_the_job_at_the_default_interval(tmp_path, monkeypatch):
    """End-to-end: the real app lifespan (`app.main.lifespan`) actually
    starts a scheduler with this job registered, without needing to wait
    for a real interval to elapse."""
    monkeypatch.setenv("EPG_EDITOR_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(scheduler_jobs.REFRESH_INTERVAL_ENV_VAR, raising=False)

    with TestClient(app) as client:
        scheduler = client.app.state.scheduler
        job = scheduler.get_job(scheduler_jobs.JOB_ID)
        assert job is not None
        assert job.trigger.interval == timedelta(hours=12)
        assert job.next_run_time is not None
        assert scheduler.running

    # Shut down cleanly on app/lifespan exit.
    assert not scheduler.running


# --- `run_scheduled_refresh` error handling ----------------------------------


def test_missing_credentials_is_skipped_without_raising(monkeypatch, caplog):
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)

    def fail_if_called(*args, **kwargs):  # pragma: no cover
        raise AssertionError("refresh_all_lineups must not be called without credentials")

    monkeypatch.setattr(scheduler_jobs, "refresh_all_lineups", fail_if_called)

    with caplog.at_level("WARNING"):
        run(scheduler_jobs.run_scheduled_refresh())

    assert any("not configured" in record.message for record in caplog.records)


def test_sd_credentials_not_configured_error_is_a_clean_skip(monkeypatch):
    """Whitebox: confirms the specific exception type the job is built to
    catch is actually what `SdClient.from_env()` raises."""
    monkeypatch.delenv("SD_USERNAME", raising=False)
    monkeypatch.delenv("SD_PASSWORD", raising=False)
    from app.sd_client.client import SdClient

    with pytest.raises(SdCredentialsNotConfiguredError):
        SdClient.from_env()


def test_sd_client_error_during_refresh_is_logged_and_swallowed(monkeypatch, caplog):
    monkeypatch.setenv("SD_USERNAME", "fake-user")
    monkeypatch.setenv("SD_PASSWORD", "fake-password")

    async def raise_sd_error(*args, **kwargs):
        raise SdClientError("boom", status_code=403)

    monkeypatch.setattr(scheduler_jobs, "refresh_all_lineups", raise_sd_error)

    with caplog.at_level("ERROR"):
        run(scheduler_jobs.run_scheduled_refresh())  # must not raise

    assert any("refresh failed" in record.message.lower() for record in caplog.records)
