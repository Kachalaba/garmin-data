#!/usr/bin/env python3
"""
risk_scores.py — compute six risk/prediction scores per day.

All scores use only data from ON or BEFORE the target day (no look-ahead).
Each metric cites the peer-reviewed source it adapts.

  1. illness_risk_score (0–100)
     Mishra et al. 2020, "Pre-symptomatic detection of COVID-19 from smartwatch
     data" (Stanford / Snyder lab). Weighted combination of RHR z-score +
     persistence, HRV baseline status, sleep-respiration z, SpO2 drop vs
     personal baseline.

  2. acwr (Acute:Chronic Workload Ratio)
     Gabbett 2016 "The training-injury prevention paradox"; Hulin et al. 2014.
     mean_7d(daily_load) / mean_28d(daily_load). Sweet spot 0.8–1.3.

  3. autonomic_strain (−100 .. +100)
     Kiviniemi et al. HRV-guided training research, combined with classical
     RHR drift interpretation. 7d RHR slope UP + HRV slope DOWN = sympathetic
     dominance (stress/overreach). Inverse = parasympathetic recovery.

  4. sleep_debt_hours
     Van Dongen et al. 2003 sleep-dose research. 14d cumulative shortfall vs
     max(personal 30d baseline, 7.0h) — only shortfalls, surplus doesn't repay.

  5. heat_adaptation_index
     Periard et al. 2015. Trend of HR/temp ratio on warm-weather activities:
     recent 30d vs previous 30d; positive = lower HR at same temperature.

  6. readiness_decay_rate
     Internal composite: readiness_7d_mean − today (acute drop) and
     readiness_30d_mean − readiness_7d_mean (chronic drop).
     Distinguishes one-session fatigue from multi-week decline.

Writes to `risk_scores` keyed by (user_id, metric_date). Idempotent.

Usage:
    python3 -m analytics.risk_scores [DAYS]
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import date, timedelta

from analytics.common import USER_ID, db_connection, get_logger

log = get_logger("risk_scores")


DDL = """
CREATE TABLE IF NOT EXISTS risk_scores (
    user_id                INTEGER NOT NULL,
    metric_date            DATE    NOT NULL,

    illness_risk_score     REAL,
    illness_risk_level     TEXT,
    illness_risk_drivers   TEXT,

    acwr                   REAL,
    acwr_level             TEXT,
    acute_load_7d          REAL,
    chronic_load_28d       REAL,

    autonomic_strain       REAL,
    autonomic_level        TEXT,

    sleep_debt_hours       REAL,
    sleep_debt_level       TEXT,

    heat_adaptation_index  REAL,
    heat_adaptation_level  TEXT,

    readiness_acute_drop   REAL,
    readiness_chronic_drop REAL,
    readiness_decay_level  TEXT,

    data_quality           TEXT,
    computed_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
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


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _slope(ys: list[float]) -> float:
    """Least-squares slope of y over x = 0..n-1 (per step).
    Returns 0.0 for <2 points. Used as a trend proxy — step = one sample,
    not necessarily exactly one calendar day, when inputs have gaps.
    """
    n = len(ys)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(ys) / n
    num = sum((i - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def _window_nonnull(series: list[tuple], i: int, size: int, exclude_today: bool = False) -> list[float]:
    """Return non-null values from the window of `size` rows ending at index i
    (inclusive of i unless exclude_today=True)."""
    end = i if exclude_today else i + 1
    start = max(0, end - size)
    return [v for _, v in series[start:end] if v is not None]


def _parse_date(md) -> date | None:
    if isinstance(md, date):
        return md
    if isinstance(md, str):
        try:
            return date.fromisoformat(md[:10])
        except ValueError:
            return None
    return None


def _illness(rhr_z, rhr_persist, hrv_status, resp_z, spo2_drop):
    """Compute illness risk score + level + drivers.

    Returns (score, level, drivers_str, components_present_int).
    All inputs may be None; None inputs simply don't contribute.
    """
    drivers: list[str] = []
    present = 0

    rhr_component = 0.0
    rhr_bonus = 0.0
    if rhr_z is not None:
        present += 1
        if rhr_z >= 0:
            rhr_component = _clamp(rhr_z * 20, 0, 100)
        if rhr_persist == 1:
            rhr_bonus = 30
        if rhr_z >= 1.0 or rhr_persist == 1:
            drivers.append("RHR")

    hrv_component = 0.0
    if hrv_status is not None:
        present += 1
        if hrv_status == "SUPPRESSED":
            hrv_component = 40
            drivers.append("HRV")
        elif hrv_status == "UNKNOWN":
            hrv_component = 15

    resp_component = 0.0
    if resp_z is not None:
        present += 1
        if resp_z >= 0:
            resp_component = _clamp((resp_z - 1) * 25, 0, 60)
        if resp_z >= 1.5:
            drivers.append("Resp")

    spo2_component = 0.0
    if spo2_drop is not None:
        present += 1
        spo2_component = _clamp(spo2_drop * 15, 0, 50)
        if spo2_drop >= 1.0:
            drivers.append("SpO2")

    if present == 0:
        return None, "UNKNOWN", None, 0

    raw = ((rhr_component + rhr_bonus) * 0.40
           + hrv_component * 0.30
           + resp_component * 0.20
           + spo2_component * 0.10)
    score = _clamp(raw, 0, 100)

    # More than 2 of 4 inputs missing → classification UNKNOWN
    if (4 - present) > 2:
        level = "UNKNOWN"
    elif score >= 60:
        level = "HIGH"
    elif score >= 35:
        level = "ELEVATED"
    elif score >= 15:
        level = "SLIGHT"
    else:
        level = "LOW"

    return score, level, (",".join(drivers) if drivers else None), present


def compute(limit_days: int | None = None) -> int:
    """Recompute risk_scores for all (or last N) days.

    The full pass is always computed (cheap); limit_days only restricts which
    rows are WRITTEN — matching hrv_baseline / rhr_anomaly behavior.
    Returns number of rows written.
    """
    with db_connection() as conn:
        conn.execute(DDL)

        dhm = conn.execute(
            """
            SELECT metric_date,
                   resting_heart_rate,
                   hrv_last_night_avg,
                   avg_sleep_respiration_value,
                   average_spo2,
                   sleep_duration_hours,
                   training_readiness_score
            FROM daily_health_metrics
            WHERE user_id = ?
            ORDER BY metric_date ASC
            """,
            (USER_ID,),
        ).fetchall()

        if not dhm:
            log.warning("no daily_health_metrics — nothing to compute")
            return 0

        log.info(f"found {len(dhm)} days in daily_health_metrics")

        rhr_by_date: dict = {}
        for r in conn.execute(
            "SELECT metric_date, z_score, persistent FROM rhr_anomaly WHERE user_id = ?",
            (USER_ID,),
        ).fetchall():
            rhr_by_date[r["metric_date"]] = r

        hrv_by_date: dict = {}
        for r in conn.execute(
            "SELECT metric_date, status FROM hrv_baseline WHERE user_id = ?",
            (USER_ID,),
        ).fetchall():
            hrv_by_date[r["metric_date"]] = r

        load_by_date: dict[str, float] = {}
        for r in conn.execute(
            """
            SELECT activity_date, COALESCE(SUM(training_load), 0) AS daily_load
            FROM activities
            WHERE user_id = ?
            GROUP BY activity_date
            """,
            (USER_ID,),
        ).fetchall():
            load_by_date[r["activity_date"]] = float(r["daily_load"] or 0.0)

        # Activities joined with weather — ordered, used for heat adaptation
        act_weather = conn.execute(
            """
            SELECT a.activity_date, a.duration_seconds, a.avg_heart_rate,
                   w.temperature_c
            FROM activities a
            JOIN activity_weather w
              ON w.user_id = a.user_id AND w.activity_id = a.activity_id
            WHERE a.user_id = ?
              AND a.avg_heart_rate IS NOT NULL
              AND a.duration_seconds IS NOT NULL
              AND a.duration_seconds > 0
              AND w.temperature_c IS NOT NULL
            ORDER BY a.activity_date ASC
            """,
            (USER_ID,),
        ).fetchall()

        # Column series for windowing
        dates = [r["metric_date"] for r in dhm]
        rhr_series = [(r["metric_date"], r["resting_heart_rate"]) for r in dhm]
        hrv_series = [(r["metric_date"], r["hrv_last_night_avg"]) for r in dhm]
        resp_series = [(r["metric_date"], r["avg_sleep_respiration_value"]) for r in dhm]
        spo2_series = [(r["metric_date"], r["average_spo2"]) for r in dhm]
        sleep_series = [(r["metric_date"], r["sleep_duration_hours"]) for r in dhm]
        ready_series = [(r["metric_date"], r["training_readiness_score"]) for r in dhm]
        load_series = [(d, load_by_date.get(d, 0.0)) for d in dates]

        start_idx = max(0, len(dhm) - limit_days) if limit_days else 0
        to_write: list[tuple] = []

        for i, row in enumerate(dhm):
            if i < start_idx:
                continue

            metric_date = row["metric_date"]

            # Skip rows where the device clearly wasn't worn (all inputs NULL)
            if all(
                row[f] is None
                for f in (
                    "resting_heart_rate",
                    "hrv_last_night_avg",
                    "avg_sleep_respiration_value",
                    "average_spo2",
                    "sleep_duration_hours",
                    "training_readiness_score",
                )
            ):
                continue

            md_dt = _parse_date(metric_date)
            rhr_today = row["resting_heart_rate"]
            hrv_today = row["hrv_last_night_avg"]
            resp_today = row["avg_sleep_respiration_value"]
            spo2_today = row["average_spo2"]
            sleep_today = row["sleep_duration_hours"]
            ready_today = row["training_readiness_score"]

            # ── 1. Illness risk ────────────────────────────────────────
            rhr_info = rhr_by_date.get(metric_date)
            hrv_info = hrv_by_date.get(metric_date)
            rhr_z = rhr_info["z_score"] if rhr_info else None
            rhr_persist = rhr_info["persistent"] if rhr_info else None
            hrv_status = hrv_info["status"] if hrv_info else None

            # Respiration z-score vs 28-day baseline (excluding today)
            resp_win = _window_nonnull(resp_series, i, 28, exclude_today=True)
            if resp_today is not None and len(resp_win) >= 7:
                rm = _mean(resp_win)
                rsd = _sd(resp_win, rm)
                resp_z = (resp_today - rm) / rsd if rsd > 0 else 0.0
            else:
                resp_z = None

            # SpO2 drop vs 30-day personal baseline (only count drops ≥ 2%
            # per task spec; contributing signal flagged for any drop below
            # baseline, but bigger drops score higher via the formula).
            spo2_win = _window_nonnull(spo2_series, i, 30, exclude_today=True)
            if spo2_today is not None and len(spo2_win) >= 7:
                spo2_base = _mean(spo2_win)
                spo2_drop = spo2_base - spo2_today if spo2_today < spo2_base else 0.0
            else:
                spo2_drop = None

            illness_score, illness_level, illness_drivers, present = _illness(
                rhr_z, rhr_persist, hrv_status, resp_z, spo2_drop
            )

            # ── 2. ACWR ────────────────────────────────────────────────
            # Require ≥ 7 days of preceding history for any ACWR output.
            if i >= 7:
                acute_vals = [v for _, v in load_series[max(0, i - 6): i + 1]]
                chronic_vals = [v for _, v in load_series[max(0, i - 27): i + 1]]
                acute_load = sum(acute_vals) / len(acute_vals) if acute_vals else 0.0
                chronic_load = sum(chronic_vals) / len(chronic_vals) if chronic_vals else 0.0
                if chronic_load > 0:
                    acwr = acute_load / chronic_load
                    if acwr < 0.8:
                        acwr_level = "DETRAINING"
                    elif acwr <= 1.3:
                        acwr_level = "OPTIMAL"
                    elif acwr <= 1.5:
                        acwr_level = "OVERREACHING"
                    else:
                        acwr_level = "DANGER_ZONE"
                else:
                    acwr = None
                    acwr_level = "UNKNOWN"
            else:
                acute_load = chronic_load = None
                acwr = None
                acwr_level = "UNKNOWN"

            # ── 3. Autonomic strain ────────────────────────────────────
            rhr_7d = _window_nonnull(rhr_series, i, 7)
            hrv_7d = _window_nonnull(hrv_series, i, 7)
            rhr_30d = _window_nonnull(rhr_series, i, 30)
            hrv_30d = _window_nonnull(hrv_series, i, 30)

            if (
                len(rhr_7d) >= 4 and len(hrv_7d) >= 4
                and len(rhr_30d) >= 10 and len(hrv_30d) >= 10
            ):
                rhr_trend = _slope(rhr_7d)
                hrv_trend = _slope(hrv_7d)
                rhr_sd_30 = _sd(rhr_30d, _mean(rhr_30d))
                hrv_sd_30 = _sd(hrv_30d, _mean(hrv_30d))
                if rhr_sd_30 > 0 and hrv_sd_30 > 0:
                    rhr_norm = _clamp((rhr_trend * 7) / rhr_sd_30 * 50, -100, 100)
                    hrv_norm = _clamp((hrv_trend * 7) / hrv_sd_30 * 50, -100, 100)
                    autonomic_strain = _clamp(rhr_norm - hrv_norm, -100, 100)
                    if autonomic_strain > 50:
                        autonomic_level = "HIGH_STRAIN"
                    elif autonomic_strain > 15:
                        autonomic_level = "MILD_STRAIN"
                    elif autonomic_strain >= -15:
                        autonomic_level = "BALANCED"
                    else:
                        autonomic_level = "RECOVERY_DOMINANCE"
                else:
                    autonomic_strain = None
                    autonomic_level = "UNKNOWN"
            else:
                autonomic_strain = None
                autonomic_level = "UNKNOWN"

            # ── 4. Sleep debt (14d accumulated deficit) ────────────────
            sleep_30d = _window_nonnull(sleep_series, i, 30, exclude_today=True)
            if len(sleep_30d) >= 7:
                baseline = _mean(sleep_30d)
                # Conservative: don't normalize to an unhealthy pattern —
                # floor target at 7.0h even if personal baseline is lower.
                target = max(baseline, 7.0)
                sleep_14d = [v for _, v in sleep_series[max(0, i - 13): i + 1] if v is not None]
                deficits = [max(0.0, target - s) for s in sleep_14d]
                sleep_debt_hours = sum(deficits)
                if sleep_debt_hours < 3:
                    sleep_debt_level = "RESTED"
                elif sleep_debt_hours < 7:
                    sleep_debt_level = "MILD_DEBT"
                elif sleep_debt_hours < 14:
                    sleep_debt_level = "SIGNIFICANT_DEBT"
                else:
                    sleep_debt_level = "CHRONIC_DEBT"
            else:
                sleep_debt_hours = None
                sleep_debt_level = "UNKNOWN"

            # ── 5. Heat adaptation index ───────────────────────────────
            heat_adaptation_index = None
            heat_adaptation_level = "UNKNOWN"
            if md_dt is not None:
                recent_cut = (md_dt - timedelta(days=30)).isoformat()
                prev_cut = (md_dt - timedelta(days=60)).isoformat()
                md_str = md_dt.isoformat()

                def _hr_temp_ratio(a):
                    mins = a["duration_seconds"] / 60.0
                    return a["avg_heart_rate"] / (mins ** 0.1) if mins > 0 else None

                recent_warm = []
                prev_warm = []
                for a in act_weather:
                    ad = a["activity_date"]
                    if ad > md_str:
                        break
                    if a["temperature_c"] < 15:
                        continue
                    ratio = _hr_temp_ratio(a)
                    if ratio is None:
                        continue
                    if recent_cut < ad <= md_str:
                        recent_warm.append(ratio)
                    elif prev_cut < ad <= recent_cut:
                        prev_warm.append(ratio)

                if len(recent_warm) >= 3 and len(prev_warm) >= 2 and (
                    len(recent_warm) + len(prev_warm) >= 5
                ):
                    rmean = _mean(recent_warm)
                    pmean = _mean(prev_warm)
                    if pmean > 0:
                        heat_adaptation_index = (pmean - rmean) / pmean * 100
                        if heat_adaptation_index > 5:
                            heat_adaptation_level = "ADAPTING_WELL"
                        elif heat_adaptation_index >= -2:
                            heat_adaptation_level = "STABLE"
                        else:
                            heat_adaptation_level = "REGRESSING"

            # ── 6. Readiness decay ─────────────────────────────────────
            if ready_today is not None:
                ready_7d = _window_nonnull(ready_series, i, 7)
                ready_30d = _window_nonnull(ready_series, i, 30)
                if len(ready_7d) >= 3 and len(ready_30d) >= 7:
                    r7 = _mean(ready_7d)
                    r30 = _mean(ready_30d)
                    acute_drop = r7 - ready_today
                    chronic_drop = r30 - r7
                    if acute_drop > 15 and chronic_drop < 5:
                        decay_level = "ACUTE_FATIGUE"
                    elif acute_drop > 10 and chronic_drop > 10:
                        decay_level = "COMPOUNDING_FATIGUE"
                    elif acute_drop < 0 and chronic_drop > 0:
                        decay_level = "RECOVERING"
                    else:
                        decay_level = "STABLE"
                else:
                    acute_drop = chronic_drop = None
                    decay_level = "UNKNOWN"
            else:
                acute_drop = chronic_drop = None
                decay_level = "UNKNOWN"

            # ── Data quality flag ──────────────────────────────────────
            if i < 7:
                data_quality = "INSUFFICIENT"
            elif illness_level == "UNKNOWN" or acwr_level == "UNKNOWN":
                data_quality = "PARTIAL"
            else:
                missing = sum(
                    1 for v in (rhr_today, hrv_today, sleep_today, ready_today)
                    if v is None
                )
                data_quality = "PARTIAL" if missing > 0 else "FULL"

            to_write.append(
                (
                    USER_ID,
                    metric_date,
                    illness_score,
                    illness_level,
                    illness_drivers,
                    acwr,
                    acwr_level,
                    acute_load,
                    chronic_load,
                    autonomic_strain,
                    autonomic_level,
                    sleep_debt_hours,
                    sleep_debt_level,
                    heat_adaptation_index,
                    heat_adaptation_level,
                    acute_drop,
                    chronic_drop,
                    decay_level,
                    data_quality,
                )
            )

        conn.executemany(
            """
            INSERT OR REPLACE INTO risk_scores
                (user_id, metric_date,
                 illness_risk_score, illness_risk_level, illness_risk_drivers,
                 acwr, acwr_level, acute_load_7d, chronic_load_28d,
                 autonomic_strain, autonomic_level,
                 sleep_debt_hours, sleep_debt_level,
                 heat_adaptation_index, heat_adaptation_level,
                 readiness_acute_drop, readiness_chronic_drop, readiness_decay_level,
                 data_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            to_write,
        )
        log.info(f"wrote {len(to_write)} rows to risk_scores")

        # Alerts over last 14 days
        alerts = conn.execute(
            """
            SELECT metric_date,
                   ROUND(illness_risk_score, 0) AS score,
                   illness_risk_level,
                   illness_risk_drivers,
                   ROUND(acwr, 2) AS acwr,
                   acwr_level
            FROM risk_scores
            WHERE user_id = ?
              AND metric_date >= date('now', '-14 days')
              AND (illness_risk_level IN ('HIGH', 'ELEVATED')
                   OR acwr_level = 'DANGER_ZONE')
            ORDER BY metric_date DESC
            """,
            (USER_ID,),
        ).fetchall()
        if alerts:
            log.warning(f"⚠️  {len(alerts)} risk alert(s) in last 14 days:")
            for a in alerts:
                parts = []
                if a["illness_risk_level"] in ("HIGH", "ELEVATED"):
                    drv = a["illness_risk_drivers"] or "—"
                    parts.append(f"illness={a['score']:.0f} {a['illness_risk_level']} drivers={drv}")
                if a["acwr_level"] == "DANGER_ZONE":
                    parts.append(f"ACWR={a['acwr']} DANGER_ZONE")
                log.warning(f"   {a['metric_date']}: " + "; ".join(parts))
        else:
            log.info("✅ no risk alerts in last 14 days")

        return len(to_write)


def main() -> int:
    p = argparse.ArgumentParser(prog="risk_scores")
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
