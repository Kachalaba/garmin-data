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
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("GARMIN_DB_PATH", PROJECT_ROOT / "health.db"))
USER_ID = int(os.getenv("GARMIN_USER_ID", "1"))


def get_logger(name: str) -> logging.Logger:
    """Consistent logger setup matching garmy_sync style."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


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
