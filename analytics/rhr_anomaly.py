#!/usr/bin/env python3
"""
rhr_anomaly.py — detect resting-heart-rate anomalies (early illness signal).

Method (based on Stanford/Snyder lab COVID pre-symptom paper):
  1. For each day, compute rolling 28-day mean and SD of resting_heart_rate
     over the PRECEDING 28 days (excludes today — no leakage).
  2. z-score = (today.rhr - baseline_mean) / baseline_sd.
  3. Classify:
       HIGH     → z >= 2.5 (strong anomaly, illness/overtraining candidate)
       ELEVATED → z >= 1.5
       LOW      → z <= -1.5 (unusual drop — could be improved fitness
                             or measurement issue; flagged for awareness)
       NORMAL   → within band
       UNKNOWN  → not enough history yet
  4. A PERSISTENT flag is set when HIGH occurs 2+ days in a row (core
     signal from the paper — 1-day spikes are usually noise).

Writes to `rhr_anomaly` table keyed by (user_id, metric_date).

Usage:
    python3 -m analytics.rhr_anomaly [DAYS]
"""

from __future__ import annotations

import argparse
import math
import sys

from analytics.common import USER_ID, db_connection, get_logger

log = get_logger("rhr_anomaly")

BASELINE_WINDOW = 28
Z_HIGH = 2.5
Z_ELEVATED = 1.5
Z_LOW = -1.5
MIN_HISTORY = 14  # days of data before we trust the baseline

DDL = """
CREATE TABLE IF NOT EXISTS rhr_anomaly (
    user_id       INTEGER NOT NULL,
    metric_date   DATE    NOT NULL,
    rhr           INTEGER,
    baseline_28d  REAL,
    sd_28d        REAL,
    z_score       REAL,
    level         TEXT,
    persistent    INTEGER,   -- 1 if HIGH for 2+ consecutive days
    computed_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, metric_date)
);
"""


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _classify(z: float) -> str:
    if z >= Z_HIGH:
        return "HIGH"
    if z >= Z_ELEVATED:
        return "ELEVATED"
    if z <= Z_LOW:
        return "LOW"
    return "NORMAL"


def compute(limit_days: int | None = None) -> int:
    with db_connection() as conn:
        conn.execute(DDL)

        rows = conn.execute(
            """
            SELECT metric_date, resting_heart_rate
            FROM daily_health_metrics
            WHERE user_id = ?
              AND resting_heart_rate IS NOT NULL
              AND resting_heart_rate > 0
            ORDER BY metric_date ASC
            """,
            (USER_ID,),
        ).fetchall()

        if not rows:
            log.warning("no RHR data — nothing to compute")
            return 0

        log.info(f"found {len(rows)} days with RHR data")

        series = [(r["metric_date"], float(r["resting_heart_rate"])) for r in rows]

        # First pass: compute z-scores
        computed: list[tuple] = []
        start_idx = max(0, len(series) - limit_days) if limit_days else 0
        for i, (metric_date, rhr) in enumerate(series):
            # baseline from preceding window (exclude today)
            win = [v for _, v in series[max(0, i - BASELINE_WINDOW) : i]]
            if len(win) >= MIN_HISTORY:
                mean = _mean(win)
                sd = _sd(win, mean)
                z = (rhr - mean) / sd if sd > 0 else 0.0
                level = _classify(z)
            else:
                mean = sd = z = None
                level = "UNKNOWN"
            computed.append((metric_date, rhr, mean, sd, z, level))

        # Second pass: persistence flag (HIGH today AND yesterday)
        to_write: list[tuple] = []
        prev_level = None
        for idx, (metric_date, rhr, mean, sd, z, level) in enumerate(computed):
            persistent = 1 if (level == "HIGH" and prev_level == "HIGH") else 0
            prev_level = level
            if idx < start_idx:
                continue
            to_write.append(
                (USER_ID, metric_date, int(rhr), mean, sd, z, level, persistent)
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO rhr_anomaly
                (user_id, metric_date, rhr, baseline_28d, sd_28d,
                 z_score, level, persistent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            to_write,
        )
        log.info(f"wrote {len(to_write)} rows to rhr_anomaly")

        # Surface any recent flags
        alerts = conn.execute(
            """
            SELECT metric_date, rhr, ROUND(z_score, 2) AS z, level, persistent
            FROM rhr_anomaly
            WHERE user_id = ?
              AND metric_date >= date('now', '-14 days')
              AND level IN ('HIGH', 'ELEVATED')
            ORDER BY metric_date DESC
            """,
            (USER_ID,),
        ).fetchall()
        if alerts:
            log.warning(f"⚠️  {len(alerts)} RHR alert(s) in last 14 days:")
            for a in alerts:
                tag = " [PERSISTENT]" if a["persistent"] else ""
                log.warning(f"   {a['metric_date']}: RHR={a['rhr']} z={a['z']} {a['level']}{tag}")
        else:
            log.info("✅ no RHR anomalies in last 14 days")

        return len(to_write)


def main() -> int:
    p = argparse.ArgumentParser(prog="rhr_anomaly")
    p.add_argument("days", type=int, nargs="?", default=None,
                   help="Recompute only last N days (default: all history)")
    args = p.parse_args()
    try:
        compute(args.days)
        return 0
    except Exception:
        log.exception("failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
