"""Unified command-line interface for the local Garmin product."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from typing import Callable, Sequence

from garmin_health.config import Settings, get_settings
from garmin_health.database import create_backup
from garmin_health.healthcheck import HealthResult, run_healthcheck
from garmin_health.pipeline import PipelineResult, run_daily
from garmin_health.report import build_report, write_report


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="garmin-health",
        description="Reliable local Garmin sync, analytics and daily reporting.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("daily", help="Run backup, sync, analytics and report")

    report = commands.add_parser("report", help="Generate a report without syncing")
    report.add_argument("--date", type=iso_date, default=None, help="Target date (YYYY-MM-DD)")

    health = commands.add_parser("healthcheck", help="Check local data quality")
    health.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    backup = commands.add_parser("backup", help="Create a verified SQLite backup")
    backup.add_argument("--keep", type=positive_int, default=None, help="Number of backups to keep")

    commands.add_parser("analytics", help="Run local analytics without syncing")
    return parser


def _print_health(result: HealthResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return
    print(f"Status: {result.status}; usable: {'yes' if result.usable else 'no'}")
    for check in result.checks:
        print(f"[{check.status}] {check.name}: {check.message}")


def _default_backup(settings: Settings, keep: int) -> object:
    return create_backup(settings, keep=keep)


def _default_analytics() -> bool:
    from analytics import run_all

    return run_all.main() == 0


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    daily_fn: Callable[[Settings], PipelineResult] = run_daily,
    backup_fn: Callable[[Settings, int], object] = _default_backup,
    healthcheck_fn: Callable[[Settings], HealthResult] = run_healthcheck,
    analytics_fn: Callable[[], bool] = _default_analytics,
) -> int:
    args = build_parser().parse_args(argv)
    settings = settings or get_settings()
    try:
        if args.command == "daily":
            result = daily_fn(settings)
            print(f"Daily pipeline: {result.status}")
            if result.report_path:
                print(f"Report: {result.report_path}")
            for warning in result.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
            return 1 if result.status == "failed" else 0

        if args.command == "report":
            path = write_report(build_report(settings, target_date=args.date), settings)
            print(f"Report: {path}")
            return 0

        if args.command == "healthcheck":
            result = healthcheck_fn(settings)
            _print_health(result, args.json)
            return 0 if result.usable else 1

        if args.command == "backup":
            path = backup_fn(settings, args.keep or settings.backup_keep)
            print(f"Backup: {path}")
            return 0

        if args.command == "analytics":
            success = analytics_fn()
            print("Analytics: success" if success else "Analytics: partial failure")
            return 0 if success else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 1
