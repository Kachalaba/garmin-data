"""SQLite reliability helpers and product-owned operational schema."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from garmin_health.config import Settings

PIPELINE_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed')),
    report_path TEXT,
    message TEXT
)
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open SQLite with the connection policy used by product-owned code."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def quick_check(path: Path) -> str:
    """Return SQLite's quick integrity result without creating a missing database."""
    if not path.exists():
        return "missing"
    try:
        with connect(path) as conn:
            row = conn.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as exc:
        return f"error: {exc}"
    return str(row[0]) if row else "no result"


def ensure_operational_schema(conn: sqlite3.Connection) -> None:
    """Create tables owned by this project without touching Garmin-owned tables."""
    conn.execute(PIPELINE_RUNS_DDL)
    conn.commit()


def _prune_backups(backups_dir: Path, keep: int) -> None:
    keep = max(1, keep)
    paths = sorted(backups_dir.glob("health-*.db"), reverse=True)
    for path in paths[keep:]:
        path.unlink()


def create_backup(
    settings: Settings,
    *,
    keep: int | None = None,
    now: datetime | None = None,
) -> Path:
    """Create and validate a consistent SQLite backup, then apply retention."""
    if not settings.db_path.exists():
        raise FileNotFoundError(f"Database not found: {settings.db_path}")

    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    destination = settings.backups_dir / f"health-{timestamp}.db"

    with connect(settings.db_path) as source, connect(destination) as target:
        source.backup(target)

    result = quick_check(destination)
    if result != "ok":
        destination.unlink(missing_ok=True)
        raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")

    _prune_backups(settings.backups_dir, keep or settings.backup_keep)
    return destination
