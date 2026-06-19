import sqlite3
from datetime import timedelta

import pytest

from garmin_health.config import Settings


@pytest.fixture
def settings_factory(tmp_path):
    def factory():
        return Settings(
            project_root=tmp_path,
            db_path=tmp_path / "health.db",
            log_path=tmp_path / "logs" / "bot.log",
            reports_dir=tmp_path / "reports",
            backups_dir=tmp_path / "backups",
            lock_path=tmp_path / "daily.lock",
            user_id=1,
            backup_keep=7,
        )

    return factory


@pytest.fixture
def health_db_factory(settings_factory):
    def factory(latest_date, *, complete=True, analytics=True):
        settings = settings_factory()
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute("""
                CREATE TABLE daily_health_metrics (
                    user_id INTEGER NOT NULL,
                    metric_date TEXT NOT NULL,
                    sleep_duration_hours REAL,
                    hrv_last_night_avg REAL,
                    resting_heart_rate REAL,
                    training_readiness_score REAL,
                    avg_sleep_respiration_value REAL,
                    average_spo2 REAL,
                    PRIMARY KEY (user_id, metric_date)
                )
                """)
            for offset in range(7):
                day = latest_date - timedelta(days=offset)
                values = (7.5, 48.0, 52.0) if complete else (None, None, 52.0)
                conn.execute(
                    """
                    INSERT INTO daily_health_metrics
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, day.isoformat(), *values, 78.0, 14.0, 97.0),
                )

            if analytics:
                conn.execute("""
                    CREATE TABLE hrv_baseline (
                        user_id INTEGER, metric_date TEXT, status TEXT,
                        baseline_7d REAL, PRIMARY KEY (user_id, metric_date)
                    )
                    """)
                conn.execute(
                    "INSERT INTO hrv_baseline VALUES (1, ?, 'NORMAL', 3.8)",
                    (latest_date.isoformat(),),
                )
                conn.execute("""
                    CREATE TABLE rhr_anomaly (
                        user_id INTEGER, metric_date TEXT, level TEXT,
                        z_score REAL, persistent INTEGER,
                        PRIMARY KEY (user_id, metric_date)
                    )
                    """)
                conn.execute(
                    "INSERT INTO rhr_anomaly VALUES (1, ?, 'NORMAL', 0.2, 0)",
                    (latest_date.isoformat(),),
                )
                conn.execute("""
                    CREATE TABLE risk_scores (
                        user_id INTEGER, metric_date TEXT,
                        illness_risk_score REAL, illness_risk_level TEXT,
                        illness_risk_drivers TEXT, data_quality TEXT,
                        PRIMARY KEY (user_id, metric_date)
                    )
                    """)
                conn.execute(
                    "INSERT INTO risk_scores VALUES (1, ?, 8, 'LOW', NULL, 'GOOD')",
                    (latest_date.isoformat(),),
                )
                for table in ("activity_weather", "workout_intervals"):
                    conn.execute(f"""
                        CREATE TABLE {table} (
                            user_id INTEGER, metric_date TEXT,
                            PRIMARY KEY (user_id, metric_date)
                        )
                        """)
                    conn.execute(
                        f"INSERT INTO {table} VALUES (1, ?)",
                        (latest_date.isoformat(),),
                    )
        return settings

    return factory
