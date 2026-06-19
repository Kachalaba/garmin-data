import sqlite3
from datetime import datetime, timedelta

from garmin_health.config import Settings
from garmin_health.database import create_backup, quick_check


def make_settings(tmp_path):
    return Settings(
        project_root=tmp_path,
        db_path=tmp_path / "health.db",
        log_path=tmp_path / "logs" / "bot.log",
        reports_dir=tmp_path / "reports",
        backups_dir=tmp_path / "backups",
        lock_path=tmp_path / "daily.lock",
        user_id=1,
        backup_keep=2,
    )


def seed_database(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample VALUES ('kept')")


def test_create_backup_is_valid_and_preserves_data(tmp_path):
    settings = make_settings(tmp_path)
    seed_database(settings.db_path)

    backup_path = create_backup(settings, now=datetime(2026, 6, 19, 8, 0, 0), keep=2)

    assert backup_path.name == "health-20260619T080000.db"
    assert quick_check(backup_path) == "ok"
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "kept"


def test_create_backup_keeps_only_newest_files(tmp_path):
    settings = make_settings(tmp_path)
    seed_database(settings.db_path)
    start = datetime(2026, 6, 17, 8, 0, 0)

    for offset in range(3):
        create_backup(settings, now=start + timedelta(days=offset), keep=2)

    assert [path.name for path in sorted(settings.backups_dir.glob("health-*.db"))] == [
        "health-20260618T080000.db",
        "health-20260619T080000.db",
    ]
