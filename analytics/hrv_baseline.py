#!/usr/bin/env python3
"""
hrv_baseline.py — compute HRV 7-day baseline and 60-day coefficient of variation.

Method (Altini / HRV4Training / Elite HRV):
  1. Transform nightly HRV (hrv_last_night_avg, ~RMSSD) with natural log → lnHRV.
  2. Baseline = rolling 7-day mean of lnHRV (trend).
  3. Normal range = ±1 SD around the 60-day rolling mean of lnHRV.
  4. Status:
       SUPPRESSED → today's lnHRV below lower bound (fatigue/illness risk)
       ELEVATED   → today's lnHRV above upper bound (supercompensation)
       NORMAL     → within band
       UNKNOWN    → not enough history yet

Writes to a new `hrv_baseline` table keyed by (user_id, metric_date).
Re-running is safe — rows are upserted.

Usage:
    python3 -m analytics.hrv_baseline [DAYS]     # recompute last N days (default: all)
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date

from analytics.common import USER_ID, db_connection, get_logger

log = get_logger("hrv_baseline")

BASELINE_WINDOW = 7       # days for rolling baseline (trend)
BAND_WINDOW = 60          # days for rolling mean/SD (normal range)
BAND_SD_MULT = 1.0        # ±1 SD band


DDL = """
CREATE TABLE IF NOT EXISTS hrv_baseline (
    user_id       INTEGER NOT NULL,
    metric_date   DATE    NOT NULL,
    hrv_raw       REAL,
    ln_hrv        REAL,
    baseline_7d   REAL,
    mean_60d      REAL,
    sd_60d        REAL,
    cv_60d_pct    REAL,
    lower_bound   REAL,
    upper_bound   REAL,
    status        TEXT,
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


def compute(limit_days: int | None = None) -> int:
    """Recompute HRV baseline for all (or last N) days with HRV data.

    Returns number of rows written.
    """
    with db_connection() as conn:
        conn.execute(DDL)

        rows = conn.execute(
            """
            SELECT metric_date, hrv_last_night_avg
            FROM daily_health_metrics
            WHERE user_id = ?
              AND hrv_last_night_avg IS NOT NULL
              AND hrv_last_night_avg > 0
            ORDER BY metric_date ASC
            """,
            (USER_ID,),
        ).fetchall()

        if not rows:
            log.warning("no HRV data — nothing to compute")
            return 0

        log.info(f"found {len(rows)} days with HRV data")

        series = [(r["metric_date"], float(r["hrv_last_night_avg"])) for r in rows]
        ln_series = [(d, math.log(v)) for d, v in series]

        to_write: list[tuple] = []
        start_idx = max(0, len(ln_series) - limit_days) if limit_days else 0

        for i in range(start_idx, len(ln_series)):
            metric_date, ln_hrv = ln_series[i]
            hrv_raw = series[i][1]

            # 7-day rolling baseline (current day + 6 previous)
            win7 = [v for _, v in ln_series[max(0, i - BASELINE_WINDOW + 1) : i + 1]]
            baseline_7d = _mean(win7) if win7 else None

            # 60-day band: exclude today to avoid self-referential bound
            win60 = [v for _, v in ln_series[max(0, i - BAND_WINDOW) : i]]
            if len(win60) >= 14:  # need reasonable history
                mean_60d = _mean(win60)
                sd_60d = _sd(win60, mean_60d)
                cv_60d_pct = (sd_60d / mean_60d * 100) if mean_60d else None
                lower_bound = mean_60d - BAND_SD_MULT * sd_60d
                upper_bound = mean_60d + BAND_SD_MULT * sd_60d

                if ln_hrv < lower_bound:
                    status = "SUPPRESSED"
                elif ln_hrv > upper_bound:
                    status = "ELEVATED"
                else:
                    status = "NORMAL"
            else:
                mean_60d = sd_60d = cv_60d_pct = lower_bound = upper_bound = None
                status = "UNKNOWN"

            to_write.append(
                (
                    USER_ID,
                    metric_date,
                    hrv_raw,
                    ln_hrv,
                    baseline_7d,
                    mean_60d,
                    sd_60d,
                    cv_60d_pct,
                    lower_bound,
                    upper_bound,
                    status,
                )
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO hrv_baseline
                (user_id, metric_date, hrv_raw, ln_hrv, baseline_7d,
                 mean_60d, sd_60d, cv_60d_pct, lower_bound, upper_bound, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            to_write,
        )
        log.info(f"wrote {len(to_write)} rows to hrv_baseline")

        # summary of statuses over last 7 days
        recent = conn.execute(
            """
            SELECT status, COUNT(*) as n
            FROM hrv_baseline
            WHERE user_id = ? AND metric_date >= date('now', '-7 days')
            GROUP BY status
            ORDER BY n DESC
            """,
            (USER_ID,),
        ).fetchall()
        if recent:
            log.info("last 7d status distribution: " + ", ".join(f"{r['status']}={r['n']}" for r in recent))

        return len(to_write)


def main() -> int:
    p = argparse.ArgumentParser(prog="hrv_baseline")
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
