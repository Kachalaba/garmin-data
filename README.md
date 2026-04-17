# garmin-data

Персональний інструмент для синхронізації даних з **Garmin Connect** у локальну базу **SQLite**. Працює поверх бібліотеки [`garmy`](https://pypi.org/project/garmy/) і дає змогу тримати власні дані здоров'я (сон, HRV, пульс спокою, готовність до тренувань, активності) під рукою — без залежності від Garmin API в момент аналізу.

> Увага: репозиторій містить лише код. Файли `health.db` та `sync.log` виключені через `.gitignore`, оскільки містять персональні дані здоров'я.

---

## Що вміє скрипт

`garmy_sync.py` — єдина точка входу. Підтримує три режими роботи:

| Режим | Команда | Опис |
|-------|---------|------|
| Звичайна синхронізація | `python3 garmy_sync.py [N]` | Синхронізує останні `N` днів (за замовчуванням — 1) |
| Заповнення пропусків | `python3 garmy_sync.py --fill-gaps [N]` | Шукає дні без даних за останні `N` днів (за замовчуванням — 14) і довантажує їх |
| Статус | `python3 garmy_sync.py --status [N]` | Виводить таблицю наявності метрик за останні `N` днів (за замовчуванням — 7) |

### Приклади

```bash
# Синхронізувати сьогоднішній день
python3 garmy_sync.py 1

# Синхронізувати останній тиждень
python3 garmy_sync.py 7

# Залатати будь-які прогалини за останні 14 днів
python3 garmy_sync.py --fill-gaps

# Подивитись, що є в базі за останні 7 днів
python3 garmy_sync.py --status
```

### Приклад виводу `--status`

```
Date         Sleep  HRV  rHR  Ready
------------------------------------
2026-04-16       ✓    ✓    ✓     82
2026-04-15       ✓    ✓    ✓     75
2026-04-14       ✓    ✓    ✓     68
```

---

## Як працює виявлення пропусків

Функція `find_gaps()` визначає пропущений день за одним із двох критеріїв:

1. У таблиці `daily_health_metrics` немає рядка на цю дату взагалі.
2. Рядок є, але поле `sleep_duration_hours IS NULL` — тобто ніч не підтягнулась.

Сьогоднішній день завжди виключається (може ще синхронізуватись). Послідовні пропущені дати об'єднуються у діапазони (`gaps_to_ranges`), щоб `sync_range` викликався один раз на суцільний інтервал замість окремих днів.

---

## Структура бази даних

База `health.db` створюється бібліотекою `garmy` і містить чотири таблиці.

### `daily_health_metrics`
Одна агрегована метрика на день. Ключові поля:

- **Активність**: `total_steps`, `step_goal`, `total_distance_meters`, `total_calories`, `active_calories`, `bmr_calories`
- **Серце**: `resting_heart_rate`, `max_heart_rate`, `min_heart_rate`, `average_heart_rate`
- **Стрес / батарея тіла**: `avg_stress_level`, `max_stress_level`, `body_battery_high`, `body_battery_low`
- **Сон**: `sleep_duration_hours`, `deep_sleep_hours`, `light_sleep_hours`, `rem_sleep_hours`, `awake_hours` та відповідні відсотки
- **Дихання / SpO₂**: `average_spo2`, `average_respiration`, `avg_waking_respiration_value`, `avg_sleep_respiration_value`, `lowest_respiration_value`, `highest_respiration_value`
- **Готовність до тренувань**: `training_readiness_score`, `training_readiness_level`, `training_readiness_feedback`
- **HRV**: `hrv_weekly_avg`, `hrv_last_night_avg`, `hrv_status`

Первинний ключ: `(user_id, metric_date)`.

### `activities`
Окремі активності (тренування):
`activity_id`, `activity_date`, `activity_name`, `duration_seconds`, `avg_heart_rate`, `training_load`, `start_time`.

### `timeseries`
Деталізовані часові ряди (наприклад, пульс або стрес по хвилинах) у форматі: `metric_type`, `timestamp`, `value`, `meta_data` (JSON).

### `sync_status`
Журнал синхронізації по типу метрики: `sync_date`, `metric_type`, `status`, `synced_at`, `error_message`.

---

## Встановлення

### Вимоги

- macOS або Linux
- Python 3.11+
- Обліковий запис Garmin Connect

### Залежності

Рекомендований спосіб — окремий venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Конфігурація

Шляхи до БД і логів та `user_id` за замовчуванням беруться відносно теки скрипта. Перевизначити можна через змінні середовища:

| Змінна | За замовчуванням | Призначення |
|--------|------------------|-------------|
| `GARMIN_DB_PATH`  | `./health.db` | Шлях до SQLite БД |
| `GARMIN_LOG_PATH` | `./sync.log`  | Шлях до лог-файла |
| `GARMIN_USER_ID`  | `1`           | `user_id` у таблицях |

Приклад:

```bash
export GARMIN_DB_PATH=~/data/health.db
export GARMIN_LOG_PATH=~/data/sync.log
python3 garmy_sync.py 1
```

### Авторизація

Бібліотека `garmy` при першому запуску запитає логін і пароль Garmin Connect. Токени кешуються всередині garmy і використовуються для наступних запусків.

---

## Автоматизація

Типовий сценарій — щоденний запуск через `launchd` (macOS) або `cron` (Linux).

**cron (Linux):**

```cron
# Щодня о 10:00 — синхронізація останнього дня
0 10 * * * cd /path/to/garmin-data && .venv/bin/python garmy_sync.py 1

# Щоденно о 11:00 — перевірка та заповнення пропусків за 2 тижні
0 11 * * * cd /path/to/garmin-data && .venv/bin/python garmy_sync.py --fill-gaps 14
```

**launchd (macOS):** створіть `~/Library/LaunchAgents/com.user.garmy-sync.plist` із розкладом `StartCalendarInterval` та командою `cd /path/to/garmin-data && .venv/bin/python garmy_sync.py 1`, потім завантажте через `launchctl load …`.

Всі запуски пишуть у `sync.log` (формат `YYYY-MM-DD HH:MM:SS LEVEL message`).

---

## Архітектура

```
┌─────────────────────┐
│  Garmin Connect API │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  garmy (AuthClient, │
│  APIClient,         │
│  SyncManager)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐     ┌──────────────┐
│  garmy_sync.py      │────▶│  sync.log    │
│  • build_manager    │     └──────────────┘
│  • do_sync          │
│  • find_gaps        │     ┌──────────────┐
│  • gaps_to_ranges   │────▶│  health.db   │
│  • show_status      │     │  (SQLite)    │
└─────────────────────┘     └──────────────┘
```

Скрипт — тонка обгортка над `garmy.localdb.sync.SyncManager`. Вся логіка викликів API, ретраїв (`max_retries=3`) і маппінгу у таблиці — на стороні `garmy`. `garmy_sync.py` додає:

- зручний CLI з трьома режимами,
- окремий шар виявлення пропусків (`find_gaps` + `gaps_to_ranges`),
- стислий звіт про статус (`show_status`),
- єдине логування у файл і stdout.

---

## Ліцензія

MIT — для особистого використання та форків.
