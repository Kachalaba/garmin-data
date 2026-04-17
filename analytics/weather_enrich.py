#!/usr/bin/env python3
"""
weather_enrich.py — enrich each activity with historical weather + air quality.

Data source: Open-Meteo (https://open-meteo.com)
  - Historical weather:  https://archive-api.open-meteo.com/v1/archive
  - Historical AQI:      https://air-quality-api.open-meteo.com/v1/air-quality
No API key required.

Location: defaults to Kyiv (50.4501, 30.5234). Override with env vars:
  GARMIN_LAT=50.45
  GARMIN_LON=30.52

Writes to `activity_weather` keyed by activity_id. Only fetches for activities
that don't have a row yet, so re-running is cheap and idempotent.

Usage:
    python3 -m analytics.weather_enrich            # enrich all missing
    python3 -m analytics.weather_enrich --days 30  # only last 30 days of activities
    python3 -m analytics.weather_enrich --force    # re-fetch even if already stored
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

from analytics.common import USER_ID, db_connection, get_logger

log = get_logger("weather_enrich")

LAT = float(os.getenv("GARMIN_LAT", "50.4501"))
LON = float(os.getenv("GARMIN_LON", "30.5234"))

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEATHER_HOURLY = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "dew_point_2m",
    "wind_speed_10m",
    "precipitation",
    "cloud_cover",
]
AQ_HOURLY = ["pm10", "pm2_5", "european_aqi"]

DDL = """
CREATE TABLE IF NOT EXISTS activity_weather (
    user_id               INTEGER NOT NULL,
    activity_id           VARCHAR NOT NULL,
    activity_date         DATE,
    start_time            VARCHAR,
    lat                   REAL,
    lon                   REAL,
    temperature_c         REAL,
    apparent_temperature_c REAL,
    dewpoint_c            REAL,
    humidity_pct          REAL,
    wind_mps              REAL,
    precipitation_mm      REAL,
    cloud_cover_pct       REAL,
    pm2_5                 REAL,
    pm10                  REAL,
    european_aqi          REAL,
    source                TEXT,
    fetched_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, activity_id)
);
"""


def _hour_index(iso_hours: list[str], target_dt: datetime) -> int | None:
    """Find the index of the hour in iso_hours closest to target_dt."""
    target_hour = target_dt.replace(minute=0, second=0, microsecond=0).isoformat(
        timespec="minutes"
    )
    for i, h in enumerate(iso_hours):
        # Open-Meteo returns "2026-04-15T19:00"
        if h.startswith(target_hour[:13]):
            return i
    return None


def _fetch_weather(day_iso: str) -> dict | None:
    try:
        resp = requests.get(
            WEATHER_URL,
            params={
                "latitude": LAT,
                "longitude": LON,
                "start_date": day_iso,
                "end_date": day_iso,
                "hourly": ",".join(WEATHER_HOURLY),
                "wind_speed_unit": "ms",
                "timezone": "auto",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.warning(f"weather fetch failed for {day_iso}: {e}")
        return None


def _fetch_aq(day_iso: str) -> dict | None:
    try:
        resp = requests.get(
            AQ_URL,
            params={
                "latitude": LAT,
                "longitude": LON,
                "start_date": day_iso,
                "end_date": day_iso,
                "hourly": ",".join(AQ_HOURLY),
                "timezone": "auto",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.warning(f"air-quality fetch failed for {day_iso}: {e}")
        return None


def _parse_start(start_time: str) -> datetime | None:
    if not start_time:
        return None
    # formats seen: "2026-04-15 19:01:40"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(start_time, fmt)
        except ValueError:
            continue
    return None


def enrich(limit_days: int | None = None, force: bool = False) -> int:
    with db_connection() as conn:
        conn.execute(DDL)

        where = ["a.user_id = ?", "a.start_time IS NOT NULL"]
        params: list = [USER_ID]
        if limit_days:
            where.append(f"a.activity_date >= date('now', '-{int(limit_days)} days')")
        if not force:
            where.append(
                "NOT EXISTS (SELECT 1 FROM activity_weather w "
                "WHERE w.user_id = a.user_id AND w.activity_id = a.activity_id)"
            )
        sql = (
            "SELECT a.activity_id, a.activity_date, a.start_time, a.activity_name "
            "FROM activities a WHERE " + " AND ".join(where) + " ORDER BY a.activity_date ASC"
        )
        targets = conn.execute(sql, params).fetchall()

        if not targets:
            log.info("no activities need weather enrichment")
            return 0

        log.info(f"fetching weather for {len(targets)} activity(ies) at ({LAT}, {LON})")

        written = 0
        # cache per date to avoid duplicate API calls when multiple activities same day
        weather_cache: dict[str, dict] = {}
        aq_cache: dict[str, dict] = {}

        for row in targets:
            act_id = row["activity_id"]
            day_iso = row["activity_date"]
            start_dt = _parse_start(row["start_time"])
            if start_dt is None:
                log.warning(f"skip {act_id}: unparseable start_time={row['start_time']}")
                continue

            if day_iso not in weather_cache:
                weather_cache[day_iso] = _fetch_weather(day_iso) or {}
                time.sleep(0.3)  # gentle throttle
            if day_iso not in aq_cache:
                aq_cache[day_iso] = _fetch_aq(day_iso) or {}
                time.sleep(0.3)

            w_hourly = (weather_cache[day_iso] or {}).get("hourly", {})
            aq_hourly = (aq_cache[day_iso] or {}).get("hourly", {})

            def pick(hourly: dict, key: str) -> float | None:
                times = hourly.get("time") or []
                vals = hourly.get(key) or []
                if not times or not vals:
                    return None
                idx = _hour_index(times, start_dt)
                if idx is None or idx >= len(vals):
                    return None
                v = vals[idx]
                return float(v) if v is not None else None

            record = (
                USER_ID,
                act_id,
                day_iso,
                row["start_time"],
                LAT,
                LON,
                pick(w_hourly, "temperature_2m"),
                pick(w_hourly, "apparent_temperature"),
                pick(w_hourly, "dew_point_2m"),
                pick(w_hourly, "relative_humidity_2m"),
                pick(w_hourly, "wind_speed_10m"),
                pick(w_hourly, "precipitation"),
                pick(w_hourly, "cloud_cover"),
                pick(aq_hourly, "pm2_5"),
                pick(aq_hourly, "pm10"),
                pick(aq_hourly, "european_aqi"),
                "open-meteo",
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO activity_weather
                    (user_id, activity_id, activity_date, start_time, lat, lon,
                     temperature_c, apparent_temperature_c, dewpoint_c, humidity_pct,
                     wind_mps, precipitation_mm, cloud_cover_pct,
                     pm2_5, pm10, european_aqi, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record,
            )
            written += 1
            if record[6] is not None:
                log.info(
                    f"  {day_iso} {row['activity_name'] or act_id}: "
                    f"t={record[6]:.1f}°C, dew={record[8]}, wind={record[10]}, AQI={record[15]}"
                )

        log.info(f"wrote {written} rows to activity_weather")
        return written


def main() -> int:
    p = argparse.ArgumentParser(prog="weather_enrich")
    p.add_argument("--days", type=int, default=None,
                   help="Only process activities within last N days")
    p.add_argument("--force", action="store_true",
                   help="Re-fetch even if a row already exists")
    args = p.parse_args()
    try:
        enrich(args.days, args.force)
        return 0
    except Exception:
        log.exception("failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
