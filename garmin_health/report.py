"""Deterministic Markdown reporting from the local Garmin snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from garmin_health.config import Settings
from garmin_health.database import connect


class ReportUnavailableError(RuntimeError):
    """Raised when no daily row exists for a requested report."""


@dataclass(frozen=True)
class Report:
    data_date: date
    status: str
    content: str


def _table_exists(conn, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _value(value, suffix: str = "") -> str:
    if value is None:
        return "—"
    number = float(value)
    rendered = str(int(number)) if number.is_integer() else f"{number:.1f}"
    return f"{rendered}{suffix}"


def _optional_row(conn, table: str, columns: str, user_id: int, day: str):
    if not _table_exists(conn, table):
        return None
    return conn.execute(
        f"SELECT {columns} FROM {table} WHERE user_id = ? AND metric_date = ?",
        (user_id, day),
    ).fetchone()


def _recommendation(row, hrv, rhr, risk) -> str:
    hrv_status = hrv[0] if hrv else None
    rhr_status = rhr[0] if rhr else None
    risk_level = risk[1] if risk else None
    if risk_level in {"HIGH", "ELEVATED"} or rhr_status == "HIGH" or hrv_status == "SUPPRESSED":
        return "Відновлювальний день: сон, спокійна рухливість і без інтенсивної роботи."
    readiness = row[5]
    sleep = row[2]
    if (readiness is not None and readiness < 40) or (sleep is not None and sleep < 6.5):
        return "Легкий день: знизь інтенсивність і оціни самопочуття перед тренуванням."
    if sleep is None or row[3] is None or row[4] is None:
        return "Недостатньо даних для рекомендації щодо навантаження."
    return "Дані не показують явних обмежень: можна виконувати заплановане тренування."


def build_report(settings: Settings, *, target_date: date | None = None) -> Report:
    """Build a transparent report for a requested or latest available day."""
    if not settings.db_path.exists():
        raise ReportUnavailableError(f"Database not found: {settings.db_path}")

    with connect(settings.db_path) as conn:
        if not _table_exists(conn, "daily_health_metrics"):
            raise ReportUnavailableError("daily_health_metrics is missing")
        day = target_date.isoformat() if target_date else None
        if day is None:
            latest = conn.execute(
                "SELECT MAX(metric_date) FROM daily_health_metrics WHERE user_id = ?",
                (settings.user_id,),
            ).fetchone()
            day = latest[0] if latest else None
        if not day:
            raise ReportUnavailableError("No daily health data available")

        row = conn.execute(
            """
            SELECT user_id, metric_date, sleep_duration_hours, hrv_last_night_avg,
                   resting_heart_rate, training_readiness_score,
                   avg_sleep_respiration_value, average_spo2
            FROM daily_health_metrics
            WHERE user_id = ? AND metric_date = ?
            """,
            (settings.user_id, day),
        ).fetchone()
        if row is None:
            raise ReportUnavailableError(f"No daily health data for {day}")

        hrv = _optional_row(conn, "hrv_baseline", "status, baseline_7d", settings.user_id, day)
        rhr = _optional_row(
            conn, "rhr_anomaly", "level, z_score, persistent", settings.user_id, day
        )
        risk = _optional_row(
            conn,
            "risk_scores",
            "illness_risk_score, illness_risk_level, illness_risk_drivers, data_quality",
            settings.user_id,
            day,
        )

    missing = [
        name
        for name, value in (("сон", row[2]), ("HRV", row[3]), ("пульс у спокої", row[4]))
        if value is None
    ]
    status = "warning" if missing else "healthy"
    quality = (
        "Недостатньо даних: " + ", ".join(missing) + "."
        if missing
        else "Ключові добові метрики присутні."
    )
    hrv_status = hrv[0] if hrv else "—"
    rhr_status = rhr[0] if rhr else "—"
    risk_level = risk[1] if risk else "—"
    risk_score = _value(risk[0], "/100") if risk else "—"
    recommendation = _recommendation(row, hrv, rhr, risk)

    content = f"""# Garmin Health — {day}

## Стан

- Готовність: {_value(row[5], "/100")}
- Сон: {_value(row[2], " год")}
- HRV: {_value(row[3], " мс")} ({hrv_status})
- Пульс у спокої: {_value(row[4], " уд/хв")} ({rhr_status})
- SpO₂: {_value(row[7], "%")}
- Дихання уві сні: {_value(row[6], "/хв")}

## Сигнали

- Індикатор фізіологічного відхилення: {risk_score} ({risk_level})

## Рекомендація

{recommendation}

## Якість даних

{quality}

> Цей звіт показує персональні сигнали з wearable-даних, не є медичним діагнозом
> і не замінює консультацію лікаря.
"""
    return Report(date.fromisoformat(day[:10]), status, content)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_report(report: Report, settings: Settings) -> Path:
    """Write both the dated report and the stable latest pointer atomically."""
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    dated = settings.reports_dir / f"{report.data_date.isoformat()}.md"
    _atomic_write(dated, report.content)
    _atomic_write(settings.reports_dir / "latest.md", report.content)
    return dated
