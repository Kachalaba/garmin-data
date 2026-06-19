import argparse
import json
from datetime import date, timedelta

from garmin_health.cli import build_parser, main
from garmin_health.pipeline import PipelineResult


def command_names(parser):
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return set(subparsers.choices)


def test_parser_exposes_five_product_commands():
    assert command_names(build_parser()) == {
        "daily",
        "report",
        "healthcheck",
        "backup",
        "analytics",
    }


def test_healthcheck_json_is_machine_readable(health_db_factory, capsys):
    settings = health_db_factory(date.today() - timedelta(days=1))

    exit_code = main(["healthcheck", "--json"], settings=settings)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["usable"] is True
    assert payload["latest_date"] == (date.today() - timedelta(days=1)).isoformat()


def test_daily_partial_result_is_successful_exit(settings_factory):
    result = PipelineResult("partial", settings_factory().reports_dir / "latest.md", ("sync",))

    assert main(["daily"], settings=settings_factory(), daily_fn=lambda _: result) == 0


def test_daily_failed_result_is_nonzero(settings_factory):
    result = PipelineResult("failed", None, ("database",))

    assert main(["daily"], settings=settings_factory(), daily_fn=lambda _: result) == 1


def test_backup_prints_created_path(settings_factory, capsys):
    settings = settings_factory()
    expected = settings.backups_dir / "health-copy.db"

    exit_code = main(
        ["backup", "--keep", "3"],
        settings=settings,
        backup_fn=lambda passed, keep: expected,
    )

    assert exit_code == 0
    assert str(expected) in capsys.readouterr().out
