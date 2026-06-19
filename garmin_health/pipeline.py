"""Daily orchestration with explicit degraded-mode behavior."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from garmin_health.config import Settings
from garmin_health.database import connect, create_backup, ensure_operational_schema
from garmin_health.healthcheck import HealthResult, run_healthcheck
from garmin_health.report import build_report, write_report


class AlreadyRunningError(RuntimeError):
    """Raised when the daily pipeline lock is already held."""


@dataclass(frozen=True)
class PipelineResult:
    status: str
    report_path: Path | None
    warnings: tuple[str, ...]


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise AlreadyRunningError(f"Daily pipeline is already running: {path}") from exc
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        path.unlink(missing_ok=True)


def _default_sync() -> bool:
    import garmy_sync

    end = date.today()
    start = end - timedelta(days=1)
    result = garmy_sync.do_sync(garmy_sync.build_manager(), start, end)
    return result.get("failed", 0) == 0


def _default_analytics() -> bool:
    from analytics import run_all

    return run_all.main() == 0


def _default_report(settings: Settings) -> Path:
    return write_report(build_report(settings), settings)


def _start_run(settings: Settings) -> int:
    with connect(settings.db_path) as conn:
        ensure_operational_schema(conn)
        cursor = conn.execute(
            "INSERT INTO pipeline_runs (started_at, status) VALUES (?, 'running')",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _finish_run(
    settings: Settings,
    run_id: int,
    status: str,
    report_path: Path | None,
    warnings: list[str],
) -> None:
    with connect(settings.db_path) as conn:
        conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = ?, status = ?, report_path = ?, message = ?
            WHERE id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                status,
                str(report_path) if report_path else None,
                "; ".join(warnings) if warnings else None,
                run_id,
            ),
        )
        conn.commit()


def run_daily(
    settings: Settings,
    *,
    backup_fn: Callable[[Settings], Path] = create_backup,
    sync_fn: Callable[[], bool] = _default_sync,
    analytics_fn: Callable[[], bool] = _default_analytics,
    healthcheck_fn: Callable[[Settings], HealthResult] = run_healthcheck,
    report_fn: Callable[[Settings], Path] = _default_report,
) -> PipelineResult:
    """Run the daily workflow and preserve a report when local data is usable."""
    with _exclusive_lock(settings.lock_path):
        run_id = _start_run(settings)
        warnings: list[str] = []
        report_path: Path | None = None

        try:
            backup_fn(settings)
        except Exception as exc:  # backup failure makes the run unsafe
            warnings.append(f"Backup failed: {exc}")
            _finish_run(settings, run_id, "failed", None, warnings)
            return PipelineResult("failed", None, tuple(warnings))

        try:
            if not sync_fn():
                warnings.append("Garmin sync failed")
        except Exception as exc:
            warnings.append(f"Garmin sync failed: {exc}")

        try:
            if not analytics_fn():
                warnings.append("One or more analytics steps failed")
        except Exception as exc:
            warnings.append(f"Analytics failed: {exc}")

        try:
            health = healthcheck_fn(settings)
        except Exception as exc:
            warnings.append(f"Healthcheck failed: {exc}")
            _finish_run(settings, run_id, "failed", None, warnings)
            return PipelineResult("failed", None, tuple(warnings))

        if not health.usable:
            warnings.append("Local database snapshot is not usable")
            _finish_run(settings, run_id, "failed", None, warnings)
            return PipelineResult("failed", None, tuple(warnings))
        if health.status == "warning":
            warnings.append("Healthcheck reported data-quality warnings")

        try:
            report_path = report_fn(settings)
        except Exception as exc:
            warnings.append(f"Report generation failed: {exc}")
            _finish_run(settings, run_id, "failed", None, warnings)
            return PipelineResult("failed", None, tuple(warnings))

        status = "partial" if warnings else "success"
        _finish_run(settings, run_id, status, report_path, warnings)
        return PipelineResult(status, report_path, tuple(warnings))
