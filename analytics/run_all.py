#!/usr/bin/env python3
"""
run_all.py — run all analytics pipelines after a sync.

Intended to be chained AFTER garmy_sync.py, e.g. in a cron/launchd job:

    python3 garmy_sync.py && python3 -m analytics.run_all

Each step is independent — a failure in one doesn't stop the others.
"""

from __future__ import annotations

import sys

from analytics.common import get_logger
from analytics import hrv_baseline, rhr_anomaly, weather_enrich

log = get_logger("run_all")


STEPS = [
    ("hrv_baseline", lambda: hrv_baseline.compute(limit_days=90)),
    ("rhr_anomaly",  lambda: rhr_anomaly.compute(limit_days=90)),
    ("weather_enrich", lambda: weather_enrich.enrich(limit_days=60, force=False)),
]


def main() -> int:
    failed = 0
    for name, fn in STEPS:
        log.info(f"▶ {name}")
        try:
            fn()
        except Exception:
            log.exception(f"✗ {name} failed")
            failed += 1
        else:
            log.info(f"✓ {name} done")
    if failed:
        log.warning(f"{failed}/{len(STEPS)} steps failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
