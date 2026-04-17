#!/usr/bin/env python3
"""
garmy_sync.py — Sync Garmin Connect data to local SQLite DB.

Usage:
  python3 garmy_sync.py [DAYS]              # sync last N days (default: 1)
  python3 garmy_sync.py --fill-gaps         # find & fill gaps in last 14 days
  python3 garmy_sync.py --fill-gaps 30      # find & fill gaps in last 30 days
  python3 garmy_sync.py --status            # show sync status for last 7 days

Configuration (environment variables, all optional):
  GARMIN_DB_PATH   — path to SQLite DB    (default: ./health.db)
  GARMIN_LOG_PATH  — path to log file     (default: ./sync.log)
  GARMIN_USER_ID   — user_id in DB        (default: 1)
"""

import argparse
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from garmy import AuthClient, APIClient
from garmy.localdb.sync import SyncManager
from garmy.localdb.progress import ProgressReporter
from garmy.localdb.activities_iterator import ActivitiesIterator

# ── Config ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH  = Path(os.getenv("GARMIN_DB_PATH",  PROJECT_ROOT / "health.db"))
LOG_PATH = Path(os.getenv("GARMIN_LOG_PATH", PROJECT_ROOT / "sync.log"))
USER_ID  = int(os.getenv("GARMIN_USER_ID", "1"))

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("garmy_sync")


# ── DB helper ──────────────────────────────────────────────────────────────
@contextmanager
def db_cursor():
    """SQLite cursor with guaranteed close."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn.cursor()
    finally:
        conn.close()


# ── Manager factory ────────────────────────────────────────────────────────
def build_manager() -> SyncManager:
    auth_client = AuthClient()
    api_client  = APIClient(auth_client=auth_client)
    reporter    = ProgressReporter("simple")
    manager     = SyncManager(db_path=DB_PATH, progress_reporter=reporter)
    manager.api_client = api_client
    manager.activities_iterator = ActivitiesIterator(
        manager.api_client,
        manager.config.sync,
        manager.progress,
    )
    manager.activities_iterator.initialize()
    return manager


# ── Sync ───────────────────────────────────────────────────────────────────
def do_sync(manager: SyncManager, start: date, end: date) -> dict:
    """Sync a date range. garmy handles retries internally (max_retries=3).
    Raises on hard failure; partial failures are logged and reflected in result."""
    log.info(f"Syncing {start} → {end}")
    result = manager.sync_range(USER_ID, start, end)
    log.info(f"Done: {result}")
    if result.get("failed", 0) > 0:
        log.warning(f"⚠️  {result['failed']} tasks failed — check network/tokens")
    return result


# ── Gap detection ──────────────────────────────────────────────────────────
def find_gaps(lookback_days: int = 14) -> list[date]:
    """
    Return dates (excluding today) that are either missing from
    daily_health_metrics or have sleep_duration_hours IS NULL.
    """
    if not DB_PATH.exists():
        log.warning("DB not found — skipping gap check")
        return []

    end   = date.today() - timedelta(days=1)   # exclude today (may still be syncing)
    start = end - timedelta(days=lookback_days - 1)

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT metric_date, sleep_duration_hours
            FROM daily_health_metrics
            WHERE user_id = ?
              AND metric_date BETWEEN ? AND ?
            """,
            (USER_ID, start.isoformat(), end.isoformat()),
        )
        rows = {row[0]: row[1] for row in cur.fetchall()}

    gaps: list[date] = []
    for i in range(lookback_days):
        d = start + timedelta(days=i)
        if rows.get(d.isoformat()) is None:   # missing row OR NULL sleep
            gaps.append(d)
    return gaps


def gaps_to_ranges(gaps: list[date]) -> list[tuple[date, date]]:
    """Compress a list of dates into contiguous (start, end) ranges."""
    if not gaps:
        return []
    ranges = []
    start = prev = gaps[0]
    for d in gaps[1:]:
        if (d - prev).days == 1:
            prev = d
        else:
            ranges.append((start, prev))
            start = prev = d
    ranges.append((start, prev))
    return ranges


# ── Status report ──────────────────────────────────────────────────────────
def show_status(days: int = 7) -> None:
    """Print a quick status table for the last N days."""
    if not DB_PATH.exists():
        print("DB not found.")
        return

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT metric_date,
                   CASE WHEN sleep_duration_hours IS NOT NULL THEN '✓' ELSE '✗' END,
                   CASE WHEN hrv_last_night_avg   IS NOT NULL THEN '✓' ELSE '✗' END,
                   CASE WHEN resting_heart_rate   IS NOT NULL THEN '✓' ELSE '✗' END,
                   training_readiness_score
            FROM daily_health_metrics
            WHERE user_id = ?
              AND metric_date >= date('now', ?)
            ORDER BY metric_date DESC
            """,
            (USER_ID, f"-{days} days"),
        )
        rows = cur.fetchall()

    print(f"\n{'Date':<12} {'Sleep':>5} {'HRV':>4} {'rHR':>4} {'Ready':>6}")
    print("-" * 36)
    for d, sleep, hrv, rhr, ready in rows:
        ready_str = str(ready) if ready is not None else "—"
        print(f"{d:<12} {sleep:>5} {hrv:>4} {rhr:>4} {ready_str:>6}")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="garmy_sync",
        description="Sync Garmin Connect data to a local SQLite DB.",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--fill-gaps", action="store_true",
        help="Find and fill missing days in the lookback window (default: 14)",
    )
    mode.add_argument(
        "--status", action="store_true",
        help="Show sync status for the last N days (default: 7)",
    )
    p.add_argument(
        "days", type=int, nargs="?", default=None,
        help="Number of days (default: 1 sync / 14 fill-gaps / 7 status)",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.status:
            show_status(args.days or 7)
            return 0

        if args.fill_gaps:
            lookback = args.days or 14
            log.info(f"🔍 Checking for gaps in last {lookback} days...")
            gaps = find_gaps(lookback)
            if not gaps:
                log.info(f"✅ No gaps found in last {lookback} days")
                return 0
            log.info(f"📋 Found {len(gaps)} gap(s): {[d.isoformat() for d in gaps]}")
            manager = build_manager()
            failed = 0
            for rng_start, rng_end in gaps_to_ranges(gaps):
                result = do_sync(manager, rng_start, rng_end)
                failed += result.get("failed", 0)
            return 0 if failed == 0 else 1

        # Default: normal sync mode
        days    = args.days or 1
        end     = date.today()
        start   = end - timedelta(days=days - 1)
        manager = build_manager()
        result  = do_sync(manager, start, end)
        return 0 if result.get("failed", 0) == 0 else 1

    except Exception:
        log.exception("Sync failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
