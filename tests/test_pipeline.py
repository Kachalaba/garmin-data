import sqlite3
from datetime import date, timedelta

import pytest

from garmin_health.healthcheck import Check, HealthResult
from garmin_health.pipeline import AlreadyRunningError, run_daily


def healthy_result():
    return HealthResult(
        status="healthy",
        usable=True,
        checks=(Check("database", "healthy", "ok"),),
        latest_date=date(2026, 6, 18),
    )


def failed_result():
    return HealthResult(
        status="failed",
        usable=False,
        checks=(Check("database", "failed", "empty"),),
        latest_date=None,
    )


def test_daily_pipeline_runs_steps_in_order_and_records_success(health_db_factory):
    settings = health_db_factory(date.today() - timedelta(days=1))
    calls = []
    report_path = settings.reports_dir / "latest.md"

    result = run_daily(
        settings,
        backup_fn=lambda _: calls.append("backup") or settings.backups_dir / "copy.db",
        sync_fn=lambda: calls.append("sync") or True,
        analytics_fn=lambda: calls.append("analytics") or True,
        healthcheck_fn=lambda _: calls.append("healthcheck") or healthy_result(),
        report_fn=lambda _: calls.append("report") or report_path,
    )

    assert calls == ["backup", "sync", "analytics", "healthcheck", "report"]
    assert result.status == "success"
    assert result.report_path == report_path
    with sqlite3.connect(settings.db_path) as conn:
        assert conn.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "success"


def test_sync_failure_still_writes_report_from_usable_snapshot(health_db_factory):
    settings = health_db_factory(date.today() - timedelta(days=1))
    calls = []

    result = run_daily(
        settings,
        backup_fn=lambda _: settings.backups_dir / "copy.db",
        sync_fn=lambda: False,
        analytics_fn=lambda: True,
        healthcheck_fn=lambda _: healthy_result(),
        report_fn=lambda _: calls.append("report") or settings.reports_dir / "latest.md",
    )

    assert result.status == "partial"
    assert calls == ["report"]
    assert "Garmin sync failed" in result.warnings


def test_unusable_snapshot_fails_without_writing_report(health_db_factory):
    settings = health_db_factory(date.today() - timedelta(days=1))
    calls = []

    result = run_daily(
        settings,
        backup_fn=lambda _: settings.backups_dir / "copy.db",
        sync_fn=lambda: False,
        analytics_fn=lambda: False,
        healthcheck_fn=lambda _: failed_result(),
        report_fn=lambda _: calls.append("report"),
    )

    assert result.status == "failed"
    assert result.report_path is None
    assert calls == []


def test_existing_lock_prevents_second_daily_run(health_db_factory):
    settings = health_db_factory(date.today() - timedelta(days=1))
    settings.lock_path.write_text("123")

    with pytest.raises(AlreadyRunningError):
        run_daily(settings)
