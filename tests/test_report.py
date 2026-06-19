from datetime import date, timedelta

from garmin_health.report import build_report, write_report


def test_build_report_contains_key_metrics_and_disclaimer(health_db_factory):
    target = date(2026, 6, 18)
    settings = health_db_factory(target)

    report = build_report(settings, target_date=target)

    assert report.data_date == target
    assert "# Garmin Health — 2026-06-18" in report.content
    assert "7.5 год" in report.content
    assert "48 мс" in report.content
    assert "52 уд/хв" in report.content
    assert "78/100" in report.content
    assert "LOW" in report.content
    assert "не є медичним діагнозом" in report.content


def test_build_report_marks_missing_metrics_without_guessing(health_db_factory):
    target = date(2026, 6, 18)
    settings = health_db_factory(target, complete=False, analytics=False)

    report = build_report(settings, target_date=target)

    assert report.status == "warning"
    assert "Недостатньо даних" in report.content
    assert "Сон: —" in report.content
    assert "HRV: —" in report.content


def test_write_report_updates_dated_and_latest_files(health_db_factory):
    target = date(2026, 6, 18)
    settings = health_db_factory(target)
    report = build_report(settings, target_date=target)

    path = write_report(report, settings)

    assert path == settings.reports_dir / "2026-06-18.md"
    assert path.read_text() == report.content
    assert (settings.reports_dir / "latest.md").read_text() == report.content


def test_build_report_defaults_to_latest_available_date(health_db_factory):
    latest = date.today() - timedelta(days=1)
    settings = health_db_factory(latest)

    report = build_report(settings)

    assert report.data_date == latest
