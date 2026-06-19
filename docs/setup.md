# Налаштування особистого Garmin pipeline

Це локальний продукт для одного користувача. Обов'язковий шлях не залежить від Claude,
Notion, Grafana або постійно запущеного сервера: одна команда створює backup, оновлює
Garmin-дані, запускає аналітику, перевіряє якість і записує Markdown-звіт.

## 1. Передумови

- Python 3.11+
- Git
- Garmin Connect account із синхронізованим годинником
- macOS або Linux

Docker потрібен лише для опціональної Grafana.

## 2. Встановлення

```bash
git clone https://github.com/Kachalaba/garmin-data.git
cd garmin-data
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Для розробки та перевірок:

```bash
pip install -r requirements-dev.txt
```

`garmy[localdb]` включає Garmin-клієнт та його SQLite-залежності; `requests` потрібен
для Open-Meteo.

## 3. Перший запуск

Перший виклик запитає Garmin credentials і збереже токени через `garmy` у домашній
директорії:

```bash
.venv/bin/python garmy_sync.py 30
.venv/bin/python -m garmin_health analytics
.venv/bin/python -m garmin_health healthcheck
.venv/bin/python -m garmin_health report
```

Після цього у корені з'явиться `health.db`, а звіт буде у `reports/latest.md`.
Перші 7–14 днів частина baseline-показників може мати статус `UNKNOWN`.

## 4. Головна щоденна команда

```bash
.venv/bin/python -m garmin_health daily
```

Порядок операцій:

1. перевірений SQLite backup у `backups/`;
2. Garmin sync за останні два дні;
3. `hrv_baseline`, `rhr_anomaly`, `weather_enrich`, `workout_segments`, `risk_scores`;
4. healthcheck цілісності, свіжості та пропусків;
5. `reports/YYYY-MM-DD.md` і `reports/latest.md`;
6. результат у таблиці `pipeline_runs` і rotating log `logs/bot.log`.

Якщо Garmin або Open-Meteo тимчасово недоступні, команда формує звіт із останнього
придатного локального знімка і повертає статус `partial`. Порожня, пошкоджена або надто
стара база повертає exit code 1.

## 5. CLI

```bash
# Повний цикл
python -m garmin_health daily

# Звіт без мережі, остання або конкретна дата
python -m garmin_health report
python -m garmin_health report --date 2026-06-18

# Людиночитна або JSON-діагностика
python -m garmin_health healthcheck
python -m garmin_health healthcheck --json

# Перевірений backup; залишити останні 14
python -m garmin_health backup --keep 14

# Лише локальна аналітика
python -m garmin_health analytics
```

Низькорівневі `garmy_sync.py` і `python -m analytics.run_all` залишені для ручної
діагностики та backfill.

## 6. Конфігурація

Скрипти читають експортовані env variables; `.env` автоматично не завантажується.

| Variable | Default | Призначення |
|---|---|---|
| `GARMIN_DB_PATH` | `./health.db` | SQLite база |
| `GARMIN_LOG_PATH` | `./logs/bot.log` | rotating log |
| `GARMIN_REPORTS_DIR` | `./reports` | Markdown-звіти |
| `GARMIN_BACKUPS_DIR` | `./backups` | SQLite backups |
| `GARMIN_LOCK_PATH` | `./.garmin-health.lock` | захист від паралельного daily run |
| `GARMIN_BACKUP_KEEP` | `7` | кількість backup-файлів |
| `GARMIN_USER_ID` | `1` | локальний Garmin user id |
| `GARMIN_LAT` / `GARMIN_LON` | Київ | координати для погоди |

Приклад:

```bash
export GARMIN_DB_PATH="$HOME/Library/Application Support/garmin-data/health.db"
export GARMIN_BACKUPS_DIR="$HOME/Library/Application Support/garmin-data/backups"
```

## 7. Автоматичний запуск macOS

Створи `~/Library/LaunchAgents/com.user.garmin-health.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.garmin-health</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "$HOME/garmin-data" &amp;&amp; .venv/bin/python -m garmin_health daily</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/garmin-health.out</string>
  <key>StandardErrorPath</key><string>/tmp/garmin-health.err</string>
</dict>
</plist>
```

Завантаж і перевір:

```bash
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.user.garmin-health.plist
launchctl kickstart -k "gui/$(id -u)/com.user.garmin-health"
tail -f /tmp/garmin-health.out /tmp/garmin-health.err
```

Якщо репозиторій лежить не в `~/garmin-data`, зміни шлях у plist.

## 8. Автоматичний запуск Linux

```cron
0 8 * * * cd "$HOME/garmin-data" && .venv/bin/python -m garmin_health daily
```

## 9. Backup і відновлення

Перевір backups:

```bash
ls -lt backups/
sqlite3 backups/health-YYYYMMDDTHHMMSS.db 'PRAGMA quick_check;'
```

Для відновлення спочатку зупини scheduled job, потім:

```bash
cp health.db "health.db.before-restore"
cp backups/health-YYYYMMDDTHHMMSS.db health.db
sqlite3 health.db 'PRAGMA quick_check;'
python -m garmin_health healthcheck
```

Не відновлюй backup поверх бази під час активного `daily` запуску.

## 10. Опціональні інтеграції

- Grafana: `cd grafana && docker compose up -d`, потім `http://localhost:3000`.
- Claude/Notion/Intervals: шаблони залишаються у `docs/routines/`; локальний звіт від
  них не залежить.

## 11. Оновлення і перевірка

```bash
git pull
.venv/bin/pip install -r requirements.txt --upgrade
.venv/bin/python -m garmin_health healthcheck
```

Повний developer gate:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m black --check .
.venv/bin/python -m isort --check-only .
.venv/bin/python -m flake8 .
.venv/bin/python -m compileall -q garmin_health analytics garmy_sync.py
```

## Troubleshooting

| Симптом | Дія |
|---|---|
| Garmin повертає 401 | видали прострочені токени `~/.garth/` і повтори sync |
| `daily` повідомляє про lock | переконайся, що процес не працює, потім видали `.garmin-health.lock` |
| healthcheck показує missing Sleep/HRV | повтори `garmy_sync.py --fill-gaps 14` після Garmin Cloud sync |
| analytics має partial failure | дивись `logs/bot.log`; інші модулі та локальний звіт продовжують працювати |
| база failed integrity check | не запускай sync; віднови останній backup із результатом `ok` |
