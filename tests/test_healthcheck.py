import sqlite3
from datetime import date, timedelta

from garmin_health.healthcheck import run_healthcheck


def test_healthcheck_accepts_fresh_complete_snapshot(health_db_factory):
    today = date(2026, 6, 19)
    settings = health_db_factory(today - timedelta(days=1))

    result = run_healthcheck(settings, today=today)

    assert result.status == "healthy"
    assert result.usable is True
    assert result.latest_date == today - timedelta(days=1)


def test_healthcheck_warns_but_accepts_stale_snapshot(health_db_factory):
    today = date(2026, 6, 19)
    settings = health_db_factory(today - timedelta(days=2))

    result = run_healthcheck(settings, today=today)

    assert result.status == "warning"
    assert result.usable is True
    assert any(check.name == "freshness" and check.status == "warning" for check in result.checks)


def test_healthcheck_warns_about_incomplete_metrics(health_db_factory):
    today = date(2026, 6, 19)
    settings = health_db_factory(today - timedelta(days=1), complete=False)

    result = run_healthcheck(settings, today=today)

    assert result.status == "warning"
    assert result.usable is True
    assert any(
        check.name == "completeness" and check.status == "warning" for check in result.checks
    )


def test_healthcheck_rejects_database_without_daily_data(settings_factory):
    settings = settings_factory()
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("CREATE TABLE unrelated (value TEXT)")

    result = run_healthcheck(settings, today=date(2026, 6, 19))

    assert result.status == "failed"
    assert result.usable is False
    assert result.latest_date is None
