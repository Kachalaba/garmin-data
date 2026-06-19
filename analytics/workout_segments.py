#!/usr/bin/env python3
"""
workout_segments.py — explode each activity into its per-lap / per-interval breakdown.

Why this exists
---------------
The `activities` table only stores workout *summaries* (avg HR, total duration,
training load). For interval work — swim sprint sets, running repeats — the
averages are meaningless: a 4×100m sprint set with rests averages out to a
mediocre middle pace that the swimmer never actually held. Garmin's own
training-readiness/load model also under-rates short sprint efforts.

This module pulls Garmin's device-computed lap breakdown (the `/splits`
endpoint, same data the watch recorded) and stores one row per lap in
`workout_intervals`. A "lap" is a work bout or a rest; for pool swims Garmin
emits them alternately. The digest step then reads these rows and interprets
the structure in human terms (warm-up vs main set vs sprint, pace progression,
HR recovery between reps).

Data source: Garmin Connect, via the authenticated `garmy` client that
garmy_sync already uses. The DB's `activities.activity_id` IS the Garmin
activity id, so no cross-source id matching is needed.

Writes to `workout_intervals`, keyed by (user_id, activity_id, lap_index).
Only fetches activities that don't have rows yet, so re-running is cheap and
idempotent (like weather_enrich).

Usage:
    python3 -m analytics.workout_segments            # all missing activities
    python3 -m analytics.workout_segments --days 30  # only last 30 days
    python3 -m analytics.workout_segments --force    # re-fetch even if stored
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    from garmy import APIClient, AuthClient
except ImportError:
    print("garmy not installed. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

from analytics.common import USER_ID, db_connection, get_logger

log = get_logger("workout_segments")

SPLITS_EP = "/activity-service/activity/{aid}/splits"

# Garmin run/interval lap intensity types that mean "not a work effort".
REST_INTENSITIES = {"REST", "RECOVERY", "WARMUP", "COOLDOWN"}

DDL = """
CREATE TABLE IF NOT EXISTS workout_intervals (
    user_id          INTEGER NOT NULL,
    activity_id      VARCHAR NOT NULL,
    lap_index        INTEGER NOT NULL,
    activity_date    DATE,
    sport            TEXT,
    lap_kind         TEXT,          -- 'work' | 'rest' | 'active'
    duration_s       REAL,
    distance_m       REAL,
    avg_hr           INTEGER,
    max_hr           INTEGER,
    avg_speed_mps    REAL,
    max_speed_mps    REAL,
    pace_s_per_100m  REAL,          -- swim
    pace_s_per_km    REAL,          -- run / walk
    cadence          REAL,          -- swim spm or run spm
    swolf            REAL,          -- swim
    strokes          INTEGER,       -- swim
    stroke_type      TEXT,          -- swim
    avg_power        REAL,          -- run / bike
    elev_gain_m      REAL,
    intensity_type   TEXT,          -- Garmin interval label, if any
    calories         REAL,
    source           TEXT,
    fetched_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, activity_id, lap_index)
);
"""


def _build_api() -> APIClient:
    auth = AuthClient()
    return APIClient(auth_client=auth)


def _f(v) -> float | None:
    """Coerce to float, treating missing/non-numeric as None."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(round(f)) if f is not None else None


def _classify(lap: dict, sport: str) -> str:
    """Decide whether a lap is work, rest, or generic active."""
    intensity = (lap.get("intensityType") or "").upper()
    if intensity in REST_INTENSITIES:
        return "rest"
    dist = _f(lap.get("distance")) or 0.0
    dur = _f(lap.get("duration")) or 0.0
    if sport == "swim":
        # Pool swims emit explicit rest laps with distance 0.
        return "work" if dist > 0 else "rest"
    if sport == "strength":
        # No GPS distance; the lap(s) are the work itself (rests handled above).
        return "active"
    if intensity in ("ACTIVE", "INTERVAL"):
        return "work"
    # Distance sports with no intensity labels: very short laps are transition
    # artifacts (button presses, GPS jitter), and near-stationary laps are rests.
    if dur < 10 or dist <= 1.0:
        return "rest"
    if dist > 0:
        return "work"
    return "active"


def _sport_of(name: str | None) -> str:
    n = (name or "").lower()
    if "плав" in n or "swim" in n or "бас" in n:
        return "swim"
    if "бег" in n or "run" in n or "заб" in n:
        return "run"
    if "ход" in n or "walk" in n:
        return "walk"
    if "сил" in n or "strength" in n:
        return "strength"
    return "other"


def _lap_record(lap: dict, sport: str, act_id: str, act_date: str) -> tuple:
    dist = _f(lap.get("distance"))
    dur = _f(lap.get("duration"))
    avg_speed = _f(lap.get("averageSpeed"))

    pace_100 = None
    pace_km = None
    if dist and dist > 0 and dur and dur > 0:
        pace_100 = dur / dist * 100.0
        pace_km = dur / dist * 1000.0

    # Cadence field name differs by sport.
    cadence = _f(lap.get("averageSwimCadence")) or _f(lap.get("averageRunCadence"))

    return (
        USER_ID,
        act_id,
        _i(lap.get("lapIndex")),
        act_date,
        sport,
        _classify(lap, sport),
        dur,
        dist,
        _i(lap.get("averageHR")),
        _i(lap.get("maxHR")),
        avg_speed,
        _f(lap.get("maxSpeed")),
        pace_100,
        pace_km,
        cadence,
        _f(lap.get("averageSWOLF")),
        _i(lap.get("totalNumberOfStrokes")),
        lap.get("swimStroke"),
        _f(lap.get("averagePower")),
        _f(lap.get("elevationGain")),
        lap.get("intensityType"),
        _f(lap.get("calories")),
        "garmin",
    )


def _fetch_laps(api: APIClient, act_id: str) -> list[dict]:
    try:
        resp = api.connectapi(SPLITS_EP.format(aid=act_id))
    except Exception as e:  # noqa: BLE001 — network/auth, keep pipeline alive
        log.warning(f"splits fetch failed for {act_id}: {str(e)[:100]}")
        return []
    if not isinstance(resp, dict):
        return []
    return resp.get("lapDTOs") or []


def compute(limit_days: int | None = None, force: bool = False) -> int:
    with db_connection() as conn:
        conn.execute(DDL)

        where = ["a.user_id = ?"]
        params: list = [USER_ID]
        if limit_days:
            where.append(f"a.activity_date >= date('now', '-{int(limit_days)} days')")
        if not force:
            where.append(
                "NOT EXISTS (SELECT 1 FROM workout_intervals w "
                "WHERE w.user_id = a.user_id AND w.activity_id = a.activity_id)"
            )
        sql = (
            "SELECT a.activity_id, a.activity_date, a.activity_name "
            "FROM activities a WHERE " + " AND ".join(where) + " ORDER BY a.activity_date ASC"
        )
        targets = conn.execute(sql, params).fetchall()

        if not targets:
            log.info("no activities need interval breakdown")
            return 0

        log.info(f"fetching lap breakdown for {len(targets)} activity(ies)")
        api = _build_api()

        total_laps = 0
        for row in targets:
            act_id = row["activity_id"]
            sport = _sport_of(row["activity_name"])
            laps = _fetch_laps(api, act_id)
            time.sleep(0.3)  # gentle throttle
            if not laps:
                continue

            # Re-fetch replaces: clear old rows for this activity first.
            conn.execute(
                "DELETE FROM workout_intervals WHERE user_id = ? AND activity_id = ?",
                (USER_ID, act_id),
            )
            records = [_lap_record(lap, sport, act_id, row["activity_date"]) for lap in laps]
            conn.executemany(
                """
                INSERT OR REPLACE INTO workout_intervals
                    (user_id, activity_id, lap_index, activity_date, sport, lap_kind,
                     duration_s, distance_m, avg_hr, max_hr, avg_speed_mps, max_speed_mps,
                     pace_s_per_100m, pace_s_per_km, cadence, swolf, strokes, stroke_type,
                     avg_power, elev_gain_m, intensity_type, calories, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            work = sum(1 for r in records if r[5] == "work")
            total_laps += len(records)
            log.info(
                f"  {row['activity_date']} {row['activity_name'] or act_id} "
                f"[{sport}]: {len(records)} laps ({work} work)"
            )

        log.info(f"wrote {total_laps} lap rows to workout_intervals")
        return total_laps


def main() -> int:
    p = argparse.ArgumentParser(prog="workout_segments")
    p.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only process activities within last N days",
    )
    p.add_argument("--force", action="store_true", help="Re-fetch even if rows already exist")
    args = p.parse_args()
    try:
        compute(args.days, args.force)
        return 0
    except Exception:
        log.exception("failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
