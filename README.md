# 🏥 garmin-data

> Персональний pipeline аналізу здоров'я: **Garmin Connect → локальна SQLite → похідна аналітика → Claude-агенти + Grafana → Notion-дайджести**.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ліцензія: MIT](https://img.shields.io/badge/%D0%9B%D1%96%D1%86%D0%B5%D0%BD%D0%B7%D1%96%D1%8F-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Платформа: macOS | Linux](https://img.shields.io/badge/%D0%BF%D0%BB%D0%B0%D1%82%D1%84%D0%BE%D1%80%D0%BC%D0%B0-macOS%20%7C%20Linux-lightgrey)]()
[![Grafana](https://img.shields.io/badge/grafana-11.3-F46800?logo=grafana&logoColor=white)](https://grafana.com/)

Скрипт `garmy_sync.py` синхронізує дані здоров'я з Garmin Connect у локальну SQLite-базу. Пакет `analytics/` обчислює похідні метрики (HRV baseline, RHR anomaly, погоду для активностей) у додаткові таблиці тієї ж БД. Далі — дві scheduled Claude-рутини читають усе разом і дотягують метрики форми з Intervals.icu наживо, формуючи Notion-дайджести. Grafana-дашборд у `grafana/` дає always-on візуальний шар над тими ж даними.

> 💡 **Важливо про джерела даних.** У локальну `health.db` потрапляють **лише** метрики Garmin Connect (через `garmy`) + похідні аналітичні таблиці. Дані Intervals.icu (CTL/ATL/TSB, активності, wellness) **не синхронізуються** у цю базу — читаються наживо з API Intervals у момент формування дайджесту через MCP-сервер.

---

## 📑 Зміст

- [Архітектура](#-архітектура)
- [Швидкий старт](#-швидкий-старт)
- [CLI-довідник](#-cli-довідник)
- [Аналітика (похідні метрики)](#-аналітика-похідні-метрики)
- [Grafana дашборд](#-grafana-дашборд)
- [Конфігурація (env)](#️-конфігурація-env)
- [Автоматизація](#-автоматизація)
- [Документація](#-документація)
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
│                                │   • sync / fill-gaps    │         │
│                                └──────────┬──────────────┘         │
│                                           ▼                        │
│                        ┌──────────────────────────────────┐        │
│                        │        health.db  (SQLite)       │        │
│                        │  • daily_health_metrics  (Garmin)│        │
│                        │  • activities, timeseries        │        │
│                        └──────────┬───────────────────────┘        │
│                                   ▼                                │
│                        ┌─────────────────────────┐                 │
│                        │ analytics/run_all.py    │                 │
│                        │  (після sync-у)         │                 │
│                        │  • hrv_baseline  ←──────┼─ Altini метод   │
│                        │  • rhr_anomaly   ←──────┼─ z-score        │
│                        │  • weather_enrich ←─────┼─ Open-Meteo API │
│                        └──────────┬──────────────┘                 │
│                                   ▼                                │
│                        ┌──────────────────────────────────┐        │
│                        │  health.db (доповнена)           │        │
│                        │  + hrv_baseline                  │        │
│                        │  + rhr_anomaly                   │        │
│                        │  + activity_weather              │        │
│                        └──────────┬───────────────────────┘        │
└─────────────────────────────────────┼──────────────────────────────┘
                                      │
┌─────────────────────────────────────┼──────────────────────────────┐
│                              СПОЖИВАЧІ                              │
│                                     │                               │
│       ┌─────────────────────────────┼─────────────────────────┐     │
│       ▼                             ▼                         ▼     │
│ ┌───────────────┐         ┌──────────────────────┐   ┌─────────────┐│
│ │  Grafana      │         │ Claude + MCP:        │   │  SQLite CLI ││
│ │  localhost    │         │   garmy / intervals  │   │  ad-hoc     ││
│ │  :3000        │         │   / notion           │   │  запити     ││
│ │  (read-only)  │         │                      │   │             ││
│ └───────────────┘         └──────────┬───────────┘   └─────────────┘│
│                                      │                              │
│                   ┌──────────────────┼──────────────────┐           │
│                   ▼                  ▼                  ▼           │
│             ┌──────────┐      ┌────────────┐      ┌──────────┐      │
│             │ ЩОДЕННИЙ │      │ ЩОТИЖНЕВИЙ │      │ AD-HOC   │      │
│             │ 10:03    │      │ пн 10:20   │      │ чат      │      │
│             │ scheduled│      │ scheduled  │      │ вручну   │      │
│             └────┬─────┘      └─────┬──────┘      └────┬─────┘      │
│                  ▼                  ▼                  ▼            │
│             ┌──────────────────────────────────────────────┐        │
│             │        Notion: Daily Health Digest           │        │
│             └──────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

**У репозиторії** — увесь лівий ланцюжок: `garmy_sync.py`, `analytics/`, `grafana/`. База `health.db` виключена через `.gitignore` (персональні дані). Notion / Claude-рутини — поза репо, через MCP-конфігурацію клієнта.

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

# 4. Порахувати похідні метрики (HRV baseline, RHR anomaly, weather)
python3 -m analytics.run_all

# 5. Перевірити, що дані з'явилися
python3 garmy_sync.py --status

# 6. (Опціонально) підняти Grafana дашборд
cd grafana && docker compose up -d
# → відкрити http://localhost:3000  (admin / admin)
```

---

## 📋 CLI-довідник

### Синхронізація (`garmy_sync.py`)

| Команда | Опис | За замовчуванням |
|---------|------|------------------|
| `garmy_sync.py [N]` | Синхронізувати останні N днів | `N=1` |
| `garmy_sync.py --fill-gaps [N]` | Знайти та довантажити пропуски | `N=14` |
| `garmy_sync.py --status [N]` | Статусна таблиця метрик | `N=7` |

### Аналітика (`analytics/`)

| Команда | Опис |
|---------|------|
| `python3 -m analytics.run_all` | Запустити всі чотири пайплайни підряд |
| `python3 -m analytics.hrv_baseline [DAYS]` | Перерахувати HRV baseline (за потреби — лише останні DAYS) |
| `python3 -m analytics.rhr_anomaly [DAYS]` | Перерахувати RHR anomaly z-score |
| `python3 -m analytics.weather_enrich --days 60` | Дотягнути погоду для активностей за останні 60 днів |
| `python3 -m analytics.weather_enrich --force` | Перезабрати погоду навіть якщо вже є |
| `python3 -m analytics.risk_scores [DAYS]` | Перерахувати шість прогностичних score'ів |

Усі аналітичні скрипти **ідемпотентні** (CREATE TABLE IF NOT EXISTS + INSERT OR REPLACE) і читають існуючі таблиці **не модифікуючи** їх. Запускати можна безпечно скільки завгодно разів.

---

## 🧠 Аналітика (похідні метрики)

Пакет `analytics/` читає `daily_health_metrics` / `activities` і пише чотири нові таблиці. Це **надбудова**, а не заміна — `garmy_sync.py` і Garmin-таблиці не торкаються.

### 📉 `hrv_baseline` — HRV 7-денний baseline + коефіцієнт варіації

**Метод** (Altini / HRV4Training / Elite HRV): нічний HRV log-трансформується (`lnHRV = ln(rmssd)`), щоб розподіл був близький до нормального. Далі:
- **baseline_7d** — ковзне середнє lnHRV за 7 днів (тренд відновлення);
- **normal band** — середнє ± 1·SD за попередні 60 днів (персональна "норма");
- **status**: `SUPPRESSED` (нижче band — ризик перевантаження/хвороби) / `NORMAL` / `ELEVATED` (суперкомпенсація) / `UNKNOWN` (мало історії).

Використання в дайджесті: замість читати сирий `hrv_last_night_avg` — Claude-агент бере `status` і `baseline_7d` як кількісний сигнал відновлення.

### ❤️ `rhr_anomaly` — RHR z-score + раннє попередження хвороби

**Метод** (на основі Stanford / Snyder lab COVID-paper): для кожного дня обчислюється 28-денне середнє + SD resting HR **за попередні дні** (без today, щоб не було self-leakage). Z-score поточного дня:
- `z ≥ 2.5` → **HIGH** (сильна аномалія)
- `z ≥ 1.5` → **ELEVATED**
- `z ≤ −1.5` → **LOW** (нетипово низький — або супер-форма, або артефакт)
- інакше → **NORMAL**

Прапор `persistent = 1` виставляється, коли HIGH тримається 2+ дні поспіль — саме цей патерн із paper'у передує симптомам хвороби на дні-тижні.

### 🌡️ `activity_weather` — погода + якість повітря для кожного тренування

Для кожної активності через Open-Meteo (безкоштовне API, без ключа) дотягуються:
- температура + відчувана температура + dewpoint
- вологість, вітер (м/с), опади, хмарність
- PM2.5, PM10, European AQI

Локація за замовчуванням — **Київ** (50.45, 30.52); можна перевизначити через `GARMIN_LAT` / `GARMIN_LON`. Використання: кореляція avg_hr / pace з умовами → персональна теплова крива, відповідь на "сьогодні було важко через мене чи через повітря".

### 🎲 `risk_scores` — прогностичні індекси

Шість показників, обчислених на основі вже збережених сирих та похідних метрик — всі з посиланнями на peer-reviewed джерела, щоб можна було відслідкувати методологію.

**Illness Risk Score** (0–100) — ймовірність захворіти у найближчі 48–72г, на основі методики Stanford/Snyder COVID-paper. Компоненти: RHR z-score + persistence, HRV status, sleep respiration, SpO₂ drop. Класифікується як LOW / SLIGHT / ELEVATED / HIGH.

**ACWR** (Acute:Chronic Workload Ratio) — співвідношення середнього навантаження за 7 vs 28 днів (Gabbett 2016). Зона 0.8–1.3 — sweet spot приросту форми, >1.5 — небезпечна зона травм (×2-4 ризик), <0.8 — детренування.

**Autonomic Strain** (−100..+100) — комбінований тренд RHR та HRV за 7 днів. Додатні значення = симпатична домінанта (стрес, перетренування). Від'ємні = парасимпатична домінанта (відновлення, суперкомпенсація).

**Sleep Debt** (години за 14 днів) — кумулятивний дефіцит сну проти персональної бази або 7.0г (залежно що більше).

**Heat Adaptation Index** — тренд співвідношення HR/температура на активностях. >5 = поліпшення теплової адаптації, <−2 = втрата.

**Readiness Decay** — різниця гострого (7д) та хронічного (30д) падіння readiness. Дозволяє відрізнити гостру втому (одна важка сесія) від накопиченої (багатотижневий спад).

Всі score'и обчислюються скриптом `analytics/risk_scores.py`, записуються у таблицю `risk_scores` і автоматично потрапляють у Claude-дайджести через оновлений prompt у `docs/routines/morning-digest.md`.

### Щоденний цикл

```bash
# Типовий cron/launchd job:
python3 garmy_sync.py 1 && python3 -m analytics.run_all
```

`run_all` запускає чотири скрипти незалежно — збій в одному не блокує інші. `risk_scores` виконується останнім, бо читає `hrv_baseline` / `rhr_anomaly` / `activity_weather`.

---

## 📈 Grafana дашборд

У теці `grafana/` — готовий Docker Compose стек із preprovisioned datasource та дашбордом `Garmin — Health overview`.

### Запуск

```bash
cd grafana
docker compose up -d
open http://localhost:3000   # логін: admin / admin (змінити на першому вході)
```

### Що показує

Дашборд має 8 панелей у три ряди:

1. **Resting HR vs 28-day baseline** — лінія RHR + baseline dashed, бачиш коли RHR "відривається" від норми.
2. **RHR anomaly z-score** — бар-чарт з thresholds (жовтий > 1.5, червоний > 2.5).
3. **HRV raw vs 7-day baseline** — сирий HRV + baseline; дивишся чи тренд падає.
4. **HRV status timeline** — стрічка SUPPRESSED / NORMAL / ELEVATED.
5. **Sleep stages** — stacked bars: deep + light + REM.
6. **Training readiness** — бари з колірними бендами (червоний <50, жовтий 50-75, зелений ≥75).
7. **Daily training load** — сума load по днях із `activities`.
8. **Avg HR vs temperature** — scatter, видно особистий heat penalty.

### Як воно працює

- Grafana монтує `../health.db` як **read-only volume** — записи з дашборду у базу неможливі фізично.
- Datasource — [`frser-sqlite-datasource`](https://grafana.com/grafana/plugins/frser-sqlite-datasource/) plugin, встановлюється автоматично через `GF_INSTALL_PLUGINS`.
- Дашборд провіжениться з `grafana/dashboards/health-overview.json`; зміни в UI не перезатруть його (оновлюється з файла раз на 30 с).
- Жодної синхронізації в InfluxDB — одна база, єдине джерело правди.

### Зупинити

```bash
docker compose down         # зупинити контейнер, volume з налаштуваннями зберегти
docker compose down -v      # повне очищення, включно з налаштуваннями Grafana
```

---

## ⚙️ Конфігурація (env)

| Змінна | За замовчуванням | Призначення |
|--------|------------------|-------------|
| `GARMIN_DB_PATH`  | `./health.db` | Шлях до SQLite БД |
| `GARMIN_LOG_PATH` | `./sync.log`  | Шлях до лог-файла |
| `GARMIN_USER_ID`  | `1`           | `user_id` у таблицях |
| `GARMIN_LAT`      | `50.4501` (Київ) | Широта для `weather_enrich` |
| `GARMIN_LON`      | `30.5234` (Київ) | Довгота для `weather_enrich` |

```bash
export GARMIN_DB_PATH=~/data/health.db
export GARMIN_LAT=50.4501
export GARMIN_LON=30.5234
python3 garmy_sync.py 1 && python3 -m analytics.run_all
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
      <string>cd ~/garmin-data && .venv/bin/python garmy_sync.py 1 &amp;&amp; .venv/bin/python garmy_sync.py --fill-gaps 14 &amp;&amp; .venv/bin/python -m analytics.run_all</string>
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
0  8 * * * cd ~/garmin-data && .venv/bin/python garmy_sync.py 1 && .venv/bin/python -m analytics.run_all
15 8 * * * cd ~/garmin-data && .venv/bin/python garmy_sync.py --fill-gaps 14
```

### Дайджести — scheduled Claude-агенти

Налаштовано поза репо, через MCP-сервер `scheduled-tasks`:

| Рутина | Cron | Що робить |
|--------|------|-----------|
| [`morning-health-digest`](./docs/routines/morning-digest.md) | `0 10 * * *` | Щодня читає останні 2–3 дні з `garmy` MCP (включно з `hrv_baseline` / `rhr_anomaly` / `activity_weather`) + Intervals наживо, формує сторінку в Notion |
| [`weekly-health-summary`](./docs/routines/weekly-summary.md) | `15 10 * * 1` | Щопонеділка агрегує минулий тиждень |

Prompt-шаблони обох рутин — у [`docs/routines/`](./docs/routines/), з плейсхолдерами для власного setup'у. Реєстрація — через MCP-сервер `scheduled-tasks` (див. [`docs/setup.md`](./docs/setup.md) крок 7).

Запити перед тренуванням — без розкладу: відкриваєш Claude і питаєш, як тренуватись сьогодні.

---

## 📚 Документація

| Файл | Для чого |
|------|----------|
| [`docs/setup.md`](./docs/setup.md) | Bootstrap гайд з нуля до працюючого pipeline (~30–45 хв) |
| [`docs/routines/README.md`](./docs/routines/README.md) | Як реєструвати Claude scheduled-tasks |
| [`docs/routines/morning-digest.md`](./docs/routines/morning-digest.md) | Prompt-шаблон щоденного дайджесту |
| [`docs/routines/weekly-summary.md`](./docs/routines/weekly-summary.md) | Prompt-шаблон тижневого зведення |
| [`docs/notion-template.md`](./docs/notion-template.md) | Структура parent-сторінки в Notion для архіву дайджестів |
| [`.env.example`](./.env.example) | Шаблон env-конфігу |

---

## 🔌 Джерела даних

| Джерело | Як потрапляє в pipeline | Зберігається у `health.db`? | Онлайн-залежність у момент дайджесту |
|---------|------------------------|------------------------------|--------------------------------------|
| **Garmin Connect** | `garmy_sync.py` за cron/launchd через бібліотеку [`garmy`](https://pypi.org/project/garmy/) | ✅ так, повний набір | ❌ ні |
| **Open-Meteo** (погода + AQI) | `analytics/weather_enrich.py` за cron — REST API без ключа | ✅ так, у `activity_weather` | ❌ ні (погода вже записана) |
| **Intervals.icu** | Claude-агент читає наживо через MCP `intervals-icu` | ❌ ні (свідомо) | ✅ так |

**Чому Intervals не синкається локально:** MCP-сервер уже дає прямий доступ до API, а метрики CTL/ATL/TSB — похідні й так перераховуються Intervals. Менше коду, менше API-ключів у env, менше дубляжу.

---

## 📊 Структура БД

База `health.db` створюється бібліотекою [`garmy`](https://pypi.org/project/garmy/) + доповнюється пакетом `analytics/`.

### Таблиці від `garmy`

| Таблиця | Призначення | Ключ |
|---------|-------------|------|
| `daily_health_metrics` | Одна агрегована метрика на день (~43 поля) | `(user_id, metric_date)` |
| `activities` | Окремі тренування | `(user_id, activity_id)` |
| `timeseries` | Деталізовані часові ряди (HR по хвилинах і т. п.) | — |
| `sync_status` | Журнал синхронізації | — |

<details>
<summary>Поля <code>daily_health_metrics</code> (розкрити)</summary>

- **Активність:** `total_steps`, `step_goal`, `total_distance_meters`, `total_calories`, `active_calories`, `bmr_calories`
- **Серце:** `resting_heart_rate`, `max_heart_rate`, `min_heart_rate`, `average_heart_rate`
- **Стрес / Body Battery:** `avg_stress_level`, `max_stress_level`, `body_battery_high`, `body_battery_low`
- **Сон:** `sleep_duration_hours`, `deep_sleep_hours`, `light_sleep_hours`, `rem_sleep_hours`, `awake_hours` + відповідні %
- **Дихання / SpO₂:** `average_spo2`, `average_respiration`, `avg_waking_respiration_value`, `avg_sleep_respiration_value`, `lowest_respiration_value`, `highest_respiration_value`
- **Готовність:** `training_readiness_score`, `training_readiness_level`, `training_readiness_feedback`
- **HRV:** `hrv_weekly_avg`, `hrv_last_night_avg`, `hrv_status`

</details>

### Таблиці від `analytics/`

| Таблиця | Призначення | Ключ |
|---------|-------------|------|
| `hrv_baseline` | Log-HRV baseline, 60d CV, status | `(user_id, metric_date)` |
| `rhr_anomaly` | RHR z-score, persistence flag | `(user_id, metric_date)` |
| `activity_weather` | Погода + AQI для кожної активності | `(user_id, activity_id)` |
| `risk_scores` | Шість прогностичних індексів (illness, ACWR, autonomic, sleep debt, heat, decay) | `(user_id, metric_date)` |

---

## 🔍 Виявлення пропусків

Функція `find_gaps()` вважає дату пропущеною за одним з двох критеріїв:

1. У `daily_health_metrics` **немає рядка** на цю дату.
2. Рядок є, але **`sleep_duration_hours IS NULL`** — ніч не підтягнулась.

Сьогоднішній день виключається. Послідовні пропущені дати об'єднуються у суцільні діапазони, щоб `sync_range` викликався один раз на інтервал.

---

## 🛠️ Розробка

### Структура репо

```
garmin-data/
├── garmy_sync.py                # CLI sync
├── analytics/                   # похідні метрики (ідемпотентні)
│   ├── common.py                #   DB helper, env config
│   ├── hrv_baseline.py          #   HRV 7d baseline (пт 4)
│   ├── rhr_anomaly.py           #   RHR z-score (пт 7)
│   ├── weather_enrich.py        #   Open-Meteo (пт 11)
│   ├── risk_scores.py           #   шість прогностичних score'ів
│   └── run_all.py               #   one-shot runner
├── grafana/                     # дашборд (пт 9)
│   ├── docker-compose.yml       #   Grafana з health.db read-only
│   ├── provisioning/
│   │   ├── datasources/         #   sqlite datasource
│   │   └── dashboards/          #   provider
│   └── dashboards/
│       └── health-overview.json #   8-панельний дашборд
├── requirements.txt             # garmy + requests
├── README.md                    # цей файл
├── .gitignore                   # виключає health.db, sync.log, venv
├── health.db                    # НЕ комітиться
└── sync.log                     # НЕ комітиться
```

### Принципи

- **Тонкий шар над `garmy`.** Уся робота з Garmin API, ретраями, маппінгом — на боці бібліотеки.
- **Additive-only аналітика.** Пакет `analytics/` **нічого не модифікує** у Garmin-таблицях — лише читає їх і пише у власні нові таблиці через `CREATE TABLE IF NOT EXISTS` + `INSERT OR REPLACE`. Безпечно запускати будь-коли.
- **Мінімум залежностей.** Тільки `garmy` + `requests` (для Open-Meteo). Усе інше — stdlib.
- **Grafana read-only.** `health.db` монтується в контейнер як `:ro` volume — дашборд фізично не може щось зіпсувати.
- **Env-конфіг замість редагування коду.** Усі шляхи і координати виносяться у env.
- **Intervals — поза кодом.** Інтеграція через MCP-сервер, щоб не плодити API-ключі та не дублювати дані.

### Перевірка локально

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Синтаксис
python3 -m py_compile garmy_sync.py analytics/*.py

# CLI help
python3 garmy_sync.py --help
python3 -m analytics.hrv_baseline --help
python3 -m analytics.weather_enrich --help

# JSON дашборду
python3 -c "import json; json.load(open('grafana/dashboards/health-overview.json'))"
```

---

## 📜 Ліцензія

MIT — вільне використання, модифікація, форки.

---

<p align="center">
  <sub>Побудовано поверх <a href="https://pypi.org/project/garmy/">garmy</a> · HRV baseline на основі методу <a href="https://marcoaltini.substack.com/">Marco Altini</a> · RHR anomaly на основі Stanford/Snyder lab paper · Погода від <a href="https://open-meteo.com/">Open-Meteo</a>.</sub>
</p>
