# 🏥 garmin-data

> Персональний pipeline аналізу здоров'я: **Garmin Connect → локальна SQLite → Claude-агенти → Notion-дайджести**.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ліцензія: MIT](https://img.shields.io/badge/%D0%9B%D1%96%D1%86%D0%B5%D0%BD%D0%B7%D1%96%D1%8F-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Платформа: macOS | Linux](https://img.shields.io/badge/%D0%BF%D0%BB%D0%B0%D1%82%D1%84%D0%BE%D1%80%D0%BC%D0%B0-macOS%20%7C%20Linux-lightgrey)]()

Скрипт `garmy_sync.py` синхронізує дані здоров'я з Garmin Connect у локальну SQLite-базу. Далі дві scheduled Claude-рутини (щоденна та щотижнева) самостійно читають цю базу і **наживо** дотягують метрики форми з Intervals.icu, формуючи автоматичні дайджести у Notion. Запити перед тренуванням — вручну через чат із Claude.

> 💡 **Важливо про джерела даних.** У локальну `health.db` потрапляють **лише** метрики Garmin Connect через бібліотеку `garmy`. Дані Intervals.icu (CTL/ATL/TSB, активності, wellness) **не синхронізуються** у цю базу — вони читаються наживо з API Intervals у момент формування дайджесту через MCP-сервер. Це свідома архітектурна рішенність: один локальний source of truth (Garmin), а Intervals — як аналітична надбудова.

---

## 📑 Зміст

- [Архітектура](#-архітектура)
- [Швидкий старт](#-швидкий-старт)
- [CLI-довідник](#-cli-довідник)
- [Конфігурація (env)](#️-конфігурація-env)
- [Автоматизація](#-автоматизація)
- [Джерела даних](#-джерела-даних)
- [Структура БД](#-структура-бд)
- [Виявлення пропусків](#-виявлення-пропусків)
- [Розробка](#️-розробка)
- [Ліцензія](#-ліцензія)

---

## 🏗️ Архітектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ЗБІР ДАНИХ                                  │
│                                                                     │
│   ┌──────────────────────┐   launchd 08:00 щоденно                 │
│   │  Garmin Connect API  │──────────────────┐                      │
│   └──────────────────────┘                  ▼                      │
│                                ┌─────────────────────────┐         │
│                                │ garmy_sync.py           │         │
│                                │   • синхронізація N днів│         │
│                                │   • --fill-gaps         │         │
│                                │   • --status            │         │
│                                └──────────┬──────────────┘         │
│                                           ▼                        │
│                                ┌─────────────────────────┐         │
│                                │  health.db  (SQLite)    │         │
│                                │  ~43 метрики × день     │         │
│                                └─────────────────────────┘         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│                       АНАЛІЗ (поза репо)                            │
│                               ▼                                     │
│         ┌─────────────────────────────────────────┐                 │
│         │   Claude + MCP-сервери:                 │                 │
│         │   • garmy         (SQL → health.db)     │                 │
│         │   • intervals-icu (CTL/ATL/TSB, наживо) │                 │
│         │   • notion        (запис у сторінки)    │                 │
│         └─────────────────────────────────────────┘                 │
│                               │                                     │
│         ┌─────────────────────┼─────────────────────┐               │
│         ▼                     ▼                     ▼               │
│   ┌───────────┐      ┌─────────────────┐      ┌──────────┐         │
│   │ ЩОДЕННИЙ  │      │  ЩОТИЖНЕВИЙ     │      │ AD-HOC   │         │
│   │ 10:03 щдн │      │  пн 10:20       │      │ чат      │         │
│   │ scheduled │      │  scheduled      │      │ вручну   │         │
│   └─────┬─────┘      └────────┬────────┘      └─────┬────┘         │
│         ▼                     ▼                     ▼               │
│   ┌────────────────────────────────────────────────────┐            │
│   │            Notion: Daily Health Digest             │            │
│   │   • архів дайджестів (одна сторінка × день)        │            │
│   │   • weekly summary (один пост × тиждень)           │            │
│   └────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

**У репозиторії** — тільки лівий верхній блок: скрипт `garmy_sync.py` + `health.db` (виключена через `.gitignore`). Правий блок — це MCP-конфігурація клієнта Claude і scheduled-агенти; вони живуть за межами коду.

---

## 🚀 Швидкий старт

```bash
# 1. Клонувати
git clone https://github.com/Kachalaba/garmin-data.git
cd garmin-data

# 2. Virtualenv + залежності
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Перший запуск — garmy запитає логін/пароль Garmin Connect
python3 garmy_sync.py 1

# 4. Перевірити, що дані з'явилися
python3 garmy_sync.py --status
```

Приклад виводу:

```
Date         Sleep  HRV  rHR  Ready
------------------------------------
2026-04-17       ✓    ✓    ✓     —
2026-04-16       ✗    ✗    ✓    59
2026-04-15       ✓    ✓    ✓    51
2026-04-14       ✓    ✓    ✓    60
```

---

## 📋 CLI-довідник

| Команда | Опис | За замовчуванням |
|---------|------|------------------|
| `garmy_sync.py [N]` | Синхронізувати останні N днів | `N=1` (сьогодні) |
| `garmy_sync.py --fill-gaps [N]` | Знайти та довантажити пропуски | `N=14` |
| `garmy_sync.py --status [N]` | Статусна таблиця метрик | `N=7` |
| `garmy_sync.py --help` | Повна довідка argparse | — |

### Приклади

```bash
# Типовий щоденний запуск
python3 garmy_sync.py 1

# Розширена синхронізація за тиждень
python3 garmy_sync.py 7

# Залатати будь-які прогалини за 2 тижні
python3 garmy_sync.py --fill-gaps 14

# Статус за останні 30 днів
python3 garmy_sync.py --status 30
```

---

## ⚙️ Конфігурація (env)

Усі шляхи й `user_id` беруться відносно теки скрипта. Перевизначається через змінні середовища:

| Змінна | За замовчуванням | Призначення |
|--------|------------------|-------------|
| `GARMIN_DB_PATH`  | `./health.db` | Шлях до SQLite БД |
| `GARMIN_LOG_PATH` | `./sync.log`  | Шлях до лог-файла |
| `GARMIN_USER_ID`  | `1`           | `user_id` у таблицях (якщо мульти-акаунт) |

```bash
export GARMIN_DB_PATH=~/data/health.db
export GARMIN_LOG_PATH=~/data/sync.log
python3 garmy_sync.py 1
```

---

## 🤖 Автоматизація

### Локальна синхронізація — `launchd` (macOS)

Створити `~/Library/LaunchAgents/com.user.garmy-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.garmy-sync</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>-c</string>
      <string>cd ~/garmin-data && .venv/bin/python garmy_sync.py 1 &amp;&amp; .venv/bin/python garmy_sync.py --fill-gaps 14</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key><integer>8</integer>
      <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>/tmp/garmy-sync.out</string>
    <key>StandardErrorPath</key><string>/tmp/garmy-sync.err</string>
</dict>
</plist>
```

Завантажити:

```bash
launchctl load ~/Library/LaunchAgents/com.user.garmy-sync.plist
```

### Локальна синхронізація — `cron` (Linux)

```cron
0  8 * * * cd ~/garmin-data && .venv/bin/python garmy_sync.py 1
15 8 * * * cd ~/garmin-data && .venv/bin/python garmy_sync.py --fill-gaps 14
```

### Дайджести — scheduled Claude-агенти

Налаштовано поза репо, через MCP-сервер `scheduled-tasks`. Дві рутини:

| Рутина | Cron | Що робить |
|--------|------|-----------|
| `morning-health-digest` | `0 10 * * *` | Щодня читає останні 2–3 дні з `garmy` MCP + Intervals наживо, формує сторінку в Notion |
| `weekly-health-summary` | `15 10 * * 1` | Щопонеділка агрегує минулий тиждень, створює окрему Notion-сторінку |

Запити перед тренуванням — без розкладу: відкриваєш Claude і питаєш, як тренуватись сьогодні.

---

## 🔌 Джерела даних

Проєкт працює з двома джерелами, але інтеграція з ними принципово різна:

| Джерело | Як потрапляє в pipeline | Зберігається у `health.db`? | Онлайн-залежність у момент дайджесту |
|---------|------------------------|------------------------------|--------------------------------------|
| **Garmin Connect** | `garmy_sync.py` за cron/launchd синхронізує через бібліотеку [`garmy`](https://pypi.org/project/garmy/) | ✅ так, повний набір метрик | ❌ ні, аналіз йде з локальної БД |
| **Intervals.icu** | Claude-агент читає наживо через MCP-сервер `intervals-icu` у момент формування дайджесту | ❌ ні (архітектурне рішення) | ✅ так, потрібен доступ до API Intervals |

**Чому Intervals не синкається локально:**

1. MCP-сервер `intervals-icu` уже дає прямий SQL-подібний доступ до API — немає сенсу дублювати дані.
2. Метрики форми (CTL/ATL/TSB) — похідні; вони й так перераховуються Intervals на льоту.
3. Менше коду, менше залежностей, менше токенів/ключів у env.

Якщо в майбутньому знадобиться офлайн-аналіз з Intervals-даних — додасться окремий скрипт, але не зараз.

---

## 📊 Структура БД

База `health.db` створюється бібліотекою [`garmy`](https://pypi.org/project/garmy/). Чотири таблиці:

### `daily_health_metrics` — одна агрегована метрика на день

Первинний ключ: `(user_id, metric_date)`. Основні групи полів:

<details>
<summary>Розкрити перелік (~43 поля)</summary>

- **Активність:** `total_steps`, `step_goal`, `total_distance_meters`, `total_calories`, `active_calories`, `bmr_calories`
- **Серце:** `resting_heart_rate`, `max_heart_rate`, `min_heart_rate`, `average_heart_rate`
- **Стрес / Body Battery:** `avg_stress_level`, `max_stress_level`, `body_battery_high`, `body_battery_low`
- **Сон:** `sleep_duration_hours`, `deep_sleep_hours`, `light_sleep_hours`, `rem_sleep_hours`, `awake_hours` + відповідні %
- **Дихання / SpO₂:** `average_spo2`, `average_respiration`, `avg_waking_respiration_value`, `avg_sleep_respiration_value`, `lowest_respiration_value`, `highest_respiration_value`
- **Готовність:** `training_readiness_score`, `training_readiness_level`, `training_readiness_feedback`
- **HRV:** `hrv_weekly_avg`, `hrv_last_night_avg`, `hrv_status`

</details>

### `activities` — окремі тренування

`activity_id`, `activity_date`, `activity_name`, `duration_seconds`, `avg_heart_rate`, `training_load`, `start_time`.

### `timeseries` — деталізовані часові ряди

`metric_type`, `timestamp`, `value`, `meta_data` (JSON). Наприклад, пульс по хвилинах.

### `sync_status` — журнал синхронізації

`sync_date`, `metric_type`, `status`, `synced_at`, `error_message`.

---

## 🔍 Виявлення пропусків

Функція `find_gaps()` вважає дату пропущеною за одним з двох критеріїв:

1. У `daily_health_metrics` **немає рядка** на цю дату.
2. Рядок є, але **`sleep_duration_hours IS NULL`** — ніч не підтягнулась.

Сьогоднішній день виключається (може ще синхронізуватись). Послідовні пропущені дати об'єднуються у суцільні діапазони (`gaps_to_ranges`), щоб `sync_range` викликався один раз на інтервал замість окремих днів.

---

## 🛠️ Розробка

### Структура репо

```
garmin-data/
├── garmy_sync.py       # CLI + уся логіка
├── requirements.txt    # garmy==2.0.0
├── README.md           # цей файл
├── .gitignore          # виключає health.db, sync.log, venv
├── health.db           # створюється garmy, НЕ комітиться
└── sync.log            # створюється скриптом, НЕ комітиться
```

### Принципи

- **Тонкий шар над `garmy`.** Уся робота з Garmin API, ретраями (`max_retries=3`), маппінгом у схему БД — на стороні бібліотеки. Власний код лише додає CLI, виявлення пропусків, статусний звіт і єдиний log-потік.
- **Нульові залежності понад `garmy`.** Усе інше — stdlib (`argparse`, `sqlite3`, `logging`, `pathlib`, `contextmanager`).
- **Env-конфіг замість редагування коду.** Репо портабельне між машинами.
- **Inteвrvals — не в коді.** Інтеграція з Intervals.icu реалізована поза репо (MCP-сервер), щоб не плодити API-ключі в скрипті та не дублювати дані.

### Запуск локально

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Перевірити синтаксис
python3 -c "import ast; ast.parse(open('garmy_sync.py').read())"

# Перевірити CLI
python3 garmy_sync.py --help
```

---

## 📜 Ліцензія

MIT — вільне використання, модифікація, форки. Використовуйте на свій розсуд для особистих проєктів.

---

<p align="center">
  <sub>Побудовано поверх <a href="https://pypi.org/project/garmy/">garmy</a>. Натхненно ідеєю <i>«мої дані — у мене під рукою»</i>.</sub>
</p>
