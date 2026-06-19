"""Structured checks for database integrity, freshness and completeness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from garmin_health.config import Settings
from garmin_health.database import connect, quick_check


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str
    value: str | int | None = None


@dataclass(frozen=True)
class HealthResult:
    status: str
    usable: bool
    checks: tuple[Check, ...]
    latest_date: date | None


OPTIONAL_TABLES = (
    "hrv_baseline",
    "rhr_anomaly",
    "risk_scores",
    "activity_weather",
    "workout_intervals",
)


def _failed(checks: list[Check]) -> HealthResult:
    return HealthResult("failed", False, tuple(checks), None)


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _date_column(conn, table: str) -> str | None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for candidate in ("metric_date", "activity_date"):
        if candidate in columns:
            return candidate
    return None


def run_healthcheck(settings: Settings, *, today: date | None = None) -> HealthResult:
    """Inspect the local snapshot without mutating Garmin-owned data."""
    today = today or date.today()
    checks: list[Check] = []

    if not settings.db_path.exists():
        checks.append(Check("database", "failed", "Database file is missing"))
        return _failed(checks)

    integrity = quick_check(settings.db_path)
    if integrity != "ok":
        checks.append(Check("integrity", "failed", f"SQLite quick_check: {integrity}"))
        return _failed(checks)
    checks.append(Check("integrity", "healthy", "SQLite quick_check passed", integrity))

    with connect(settings.db_path) as conn:
        if not _table_exists(conn, "daily_health_metrics"):
            checks.append(Check("daily_data", "failed", "daily_health_metrics is missing"))
            return _failed(checks)

        row = conn.execute(
            """
            SELECT MAX(metric_date)
            FROM daily_health_metrics
            WHERE user_id = ?
            """,
            (settings.user_id,),
        ).fetchone()
        if not row or not row[0]:
            checks.append(Check("daily_data", "failed", "No daily health rows found"))
            return _failed(checks)

        latest = date.fromisoformat(str(row[0])[:10])
        age = (today - latest).days
        if age <= 1:
            checks.append(Check("freshness", "healthy", "Daily data is current", age))
        elif age <= 7:
            checks.append(Check("freshness", "warning", f"Daily data is {age} days old", age))
        else:
            checks.append(Check("freshness", "failed", f"Daily data is {age} days old", age))
            return HealthResult("failed", False, tuple(checks), latest)

        completeness = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN sleep_duration_hours IS NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN hrv_last_night_avg IS NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN resting_heart_rate IS NULL THEN 1 ELSE 0 END)
            FROM (
                SELECT sleep_duration_hours, hrv_last_night_avg, resting_heart_rate
                FROM daily_health_metrics
                WHERE user_id = ? AND metric_date <= ?
                ORDER BY metric_date DESC
                LIMIT 7
            )
            """,
            (settings.user_id, latest.isoformat()),
        ).fetchone()
        total, missing_sleep, missing_hrv, missing_rhr = (int(value or 0) for value in completeness)
        missing = missing_sleep + missing_hrv + missing_rhr
        if total < 3 or missing:
            checks.append(
                Check(
                    "completeness",
                    "warning",
                    f"Recent window has {missing} missing key values across {total} days",
                    missing,
                )
            )
        else:
            checks.append(Check("completeness", "healthy", f"{total} recent days checked", 0))

        for table in OPTIONAL_TABLES:
            if not _table_exists(conn, table):
                checks.append(Check(table, "warning", "Optional analytics table is missing"))
                continue
            column = _date_column(conn, table)
            if not column:
                checks.append(Check(table, "warning", "No supported date column"))
                continue
            analytics_row = conn.execute(
                f"SELECT MAX({column}) FROM {table} WHERE user_id = ?",
                (settings.user_id,),
            ).fetchone()
            value = analytics_row[0] if analytics_row else None
            status = "healthy" if value else "warning"
            message = f"Latest row: {value}" if value else "Analytics table is empty"
            checks.append(Check(table, status, message, value))

    overall = "warning" if any(check.status == "warning" for check in checks) else "healthy"
    return HealthResult(overall, True, tuple(checks), latest)
