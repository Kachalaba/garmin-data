"""Runtime configuration for the local single-user product."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Resolved paths and small policy values used by the local workflow."""

    project_root: Path
    db_path: Path
    log_path: Path
    reports_dir: Path
    backups_dir: Path
    lock_path: Path
    user_id: int = 1
    backup_keep: int = 7


def get_settings() -> Settings:
    """Resolve settings on demand so tests and shell env overrides stay isolated."""
    root = Path(__file__).resolve().parent.parent
    return Settings(
        project_root=root,
        db_path=Path(os.getenv("GARMIN_DB_PATH", root / "health.db")).expanduser(),
        log_path=Path(os.getenv("GARMIN_LOG_PATH", root / "logs" / "bot.log")).expanduser(),
        reports_dir=Path(os.getenv("GARMIN_REPORTS_DIR", root / "reports")).expanduser(),
        backups_dir=Path(os.getenv("GARMIN_BACKUPS_DIR", root / "backups")).expanduser(),
        lock_path=Path(os.getenv("GARMIN_LOCK_PATH", root / ".garmin-health.lock")).expanduser(),
        user_id=int(os.getenv("GARMIN_USER_ID", "1")),
        backup_keep=int(os.getenv("GARMIN_BACKUP_KEEP", "7")),
    )
