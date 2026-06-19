"""Shared helpers for analytics scripts.

All analytics scripts:
  - Read from existing tables (never modified).
  - Write to NEW tables created with CREATE TABLE IF NOT EXISTS.
  - Use INSERT OR REPLACE so they are safe to re-run any number of times.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("GARMIN_DB_PATH", PROJECT_ROOT / "health.db"))
USER_ID = int(os.getenv("GARMIN_USER_ID", "1"))
LOG_PATH = Path(os.getenv("GARMIN_LOG_PATH", PROJECT_ROOT / "logs" / "bot.log"))
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def configure_logging(name: str) -> logging.Logger:
    """Configure project logging with rotation and stderr warnings.

    INFO and above go to ``logs/bot.log`` (or ``GARMIN_LOG_PATH``), while
    WARNING and above are also copied to stderr. Repeated calls are safe.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if any(getattr(handler, "_garmin_logging", False) for handler in logger.handlers):
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler._garmin_logging = True

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    stderr_handler._garmin_logging = True

    logger.addHandler(file_handler)
    logger.addHandler(stderr_handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a logger using the project-wide logging policy."""
    return configure_logging(name)


@contextmanager
def db_connection():
    """SQLite connection with guaranteed close + commit on success."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
