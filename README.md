# 🏥 garmin-data

> Локальний щоденний health-звіт: Garmin → SQLite → персональні сигнали → Markdown. Claude, Notion і Grafana опціональні.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ліцензія: MIT](https://img.shields.io/badge/%D0%9B%D1%96%D1%86%D0%B5%D0%BD%D0%B7%D1%96%D1%8F-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Платформа: macOS | Linux](https://img.shields.io/badge/%D0%BF%D0%BB%D0%B0%D1%82%D1%84%D0%BE%D1%80%D0%BC%D0%B0-macOS%20%7C%20Linux-lightgrey)]()
[![Grafana](https://img.shields.io/badge/grafana-11.3-F46800?logo=grafana&logoColor=white)](https://grafana.com/)

## 🤷 Про що це взагалі?

Якщо у тебе є годинник Garmin — він 24/7 пише купу цифр про тебе: як ти спав, який у тебе пульс у спокої, скільки кроків, чи є стрес. Усе це зберігається в офіційному застосунку Garmin Connect, але там воно показане по одному дню й зрозуміти **тренд** важко: "а мені сьогодні гірше, ніж зазвичай, чи нормально?".

Цей проєкт робить чотири прості речі:

1. **Забирає твої дані з Garmin** і складає у файл на комп'ютері (`health.db`). Так ти маєш свою історію, навіть якщо Garmin завтра закриє сервіс.
2. **Створює перевірений backup**, перш ніж змінювати локальну базу.
3. **Щодня порівнює метрики з твоєю особистою нормою** і перевіряє свіжість даних.
4. **Пише локальний Markdown-звіт** у `reports/latest.md`, навіть якщо зовнішні інтеграції недоступні.

Додатково є **Grafana-дашборд** — якщо любиш графіки, можна відкрити у браузері й побачити весь твій стан за місяць одразу.

> **Кому це корисно:** людям, які носять Garmin і хочуть бачити тренди, а не окремі цифри. Не обов'язково бути спортсменом — ці ж метрики (сон, пульс, стрес) важливі й для звичайного життя.

> **Що потрібно:** годинник Garmin, який синхронізується з Garmin Connect + комп'ютер з macOS або Linux, який уміє увімкнутись о 8 ранку (або просто завжди увімкнений).

## 📖 Словничок — що означають ці скорочення

Якщо ти далекий від спорту чи біохакінгу, ось головні терміни простою мовою:

| Термін | Що це | Коли важливо |
|--------|-------|--------------|
| **RHR** (resting heart rate) | Пульс у спокої — скільки ударів за хвилину, коли ти лежиш і нічого не робиш | Нетипова зміна має багато можливих причин; дивись на тренд і контекст |
| **HRV** (heart rate variability) | Варіативність інтервалів між ударами серця за ніч | Дуже персональна метрика; порівнюй себе із власним baseline, а не з іншими |
| **SpO₂** | Оцінка насичення крові киснем від wearable-сенсора | Корисна як тренд, але показник годинника не є медичним вимірюванням |
| **Readiness** | Готовність до навантажень (Garmin рахує сам, 0–100) | Комбінований показник: сон + HRV + стрес. Чим вище — тим більше організм готовий напружуватись |
| **Training load** | Скільки ти тренувався (Garmin рахує від тривалості та пульсу) | Сума за день. Використовується, щоб не перестаратися за тиждень |
| **ACWR** | Співвідношення навантаження за 7 днів до 28 днів | Показує різку зміну обсягу, але не прогнозує травму сам по собі |
| **Sleep debt** | Борг сну — скільки годин ти недоспав за 2 тижні проти своєї норми | Якщо >14г за 2 тижні — накопичене недосипання, впливає на імунітет, увагу, настрій |

Решту термінів (Altini, Stanford/Snyder, Gabbett тощо) — це просто **прізвища науковців**, чиї формули я використав. У README вони залишені для тих, хто хоче перевірити методологію, але розуміти їх не обов'язково.

---

## ⚙️ Як це працює технічно (коротко)

Для тих, хто все-таки хоче знати технічні деталі:

Команда `python -m garmin_health daily` об'єднує backup, `garmy_sync.py`, усі модулі `analytics/`, healthcheck і локальний Markdown-звіт. Claude/Notion можуть використати ту саму базу додатково, а Grafana дає read-only візуальний шар.

> 💡 **Важливо про джерела даних.** У локальну `health.db` потрапляють **лише** метрики Garmin Connect (через `garmy`) + похідні аналітичні таблиці. Дані Intervals.icu (CTL/ATL/TSB, активності, wellness) **не синхронізуються** у цю базу — читаються наживо з API Intervals у момент формування дайджесту через MCP-сервер.

---

## 📑 Зміст

- [Про що це взагалі?](#-про-що-це-взагалі)
- [Словничок термінів](#-словничок--що-означають-ці-скорочення)
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

**Основний локальний ланцюжок:** `garmin_health` → backup → `garmy_sync.py` → п'ять `analytics`-модулів → healthcheck → `reports/latest.md`. База, backups, звіти й логи виключені через `.gitignore`. Notion / Claude / Grafana — необов'язкові споживачі.

---

## 🚀 Швидкий старт

```bash
# 1. Клонувати
git clone https://github.com/Kachalaba/garmin-data.git
cd garmin-data

# 2. Virtualenv + залежності
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Перший backfill — garmy запитає логін/пароль Garmin Connect
python3 garmy_sync.py 30

# 4. Основний щоденний цикл
python3 -m garmin_health daily

# 5. Перевірити стан і відкрити звіт
python3 -m garmin_health healthcheck
open reports/latest.md

# 6. (Опціонально) підняти Grafana дашборд
cd grafana && docker compose up -d
# → відкрити http://localhost:3000  (admin / admin)
```

---

## 📋 CLI-довідник

### Основний продукт (`python -m garmin_health`)

| Команда | Опис |
|---------|------|
| `python3 -m garmin_health daily` | Backup → sync → analytics → healthcheck → звіт |
| `python3 -m garmin_health report [--date YYYY-MM-DD]` | Створити звіт без мережі |
| `python3 -m garmin_health healthcheck [--json]` | Перевірити цілісність, свіжість і пропуски |
| `python3 -m garmin_health backup [--keep N]` | Створити перевірений SQLite backup |
| `python3 -m garmin_health analytics` | Запустити п'ять analytics-модулів |

### Синхронізація (`garmy_sync.py`)

| Команда | Опис | За замовчуванням |
|---------|------|------------------|
| `garmy_sync.py [N]` | Синхронізувати останні N днів | `N=1` |
| `garmy_sync.py --fill-gaps [N]` | Знайти та довантажити пропуски | `N=14` |
| `garmy_sync.py --status [N]` | Статусна таблиця метрик | `N=7` |

### Аналітика (`analytics/`)

| Команда | Опис |
|---------|------|
| `python3 -m analytics.run_all` | Запустити всі п'ять пайплайнів підряд |
| `python3 -m analytics.hrv_baseline [DAYS]` | Перерахувати HRV baseline (за потреби — лише останні DAYS) |
| `python3 -m analytics.rhr_anomaly [DAYS]` | Перерахувати RHR anomaly z-score |
| `python3 -m analytics.weather_enrich --days 60` | Дотягнути погоду для активностей за останні 60 днів |
| `python3 -m analytics.weather_enrich --force` | Перезабрати погоду навіть якщо вже є |
| `python3 -m analytics.risk_scores [DAYS]` | Перерахувати шість wearable-індикаторів |

Усі аналітичні скрипти **ідемпотентні** (CREATE TABLE IF NOT EXISTS + INSERT OR REPLACE) і читають існуючі таблиці **не модифікуючи** їх. Запускати можна безпечно скільки завгодно разів.

---

## 🧠 Аналітика (похідні метрики)

Пакет `analytics/` читає `daily_health_metrics` / `activities` і пише п'ять власних таблиць. Це **надбудова**, а не заміна — Garmin-таблиці не змінюються.

> 💡 **Людською мовою:** Garmin дає тобі сирі цифри (пульс був 55, HRV був 42 мс). Цей пакет щодня порівнює сьогоднішні цифри з твоєю особистою нормою за минулий місяць і каже — "це в межах звичайного" або "щось нетипове, зверни увагу". Без таких порівнянь сира цифра нічого не означає.

### 📉 `hrv_baseline` — твоя "норма" відновлення за HRV

> 🙂 **Простими словами:** Garmin щоночі міряє, наскільки нерівномірно бʼється твоє серце (HRV). Цей показник дуже персональний — у одного норма 35 мс, у іншого 80 мс. Скрипт дивиться на твої останні 60 ночей, рахує твій особистий "коридор нормальності" і показує, чи поточне значення всередині звичного діапазону.

**Метод** (Altini / HRV4Training / Elite HRV): нічний HRV log-трансформується (`lnHRV = ln(rmssd)`), щоб розподіл був близький до нормального. Далі:
- **baseline_7d** — ковзне середнє lnHRV за 7 днів (тренд відновлення);
- **normal band** — середнє ± 1·SD за попередні 60 днів (персональна "норма");
- **status**: `SUPPRESSED` (нижче band — сигнал можливого недовідновлення) / `NORMAL` / `ELEVATED` (вище персонального діапазону) / `UNKNOWN` (мало історії).

Використання в дайджесті: замість читати сирий `hrv_last_night_avg` — Claude-агент бере `status` і `baseline_7d` як кількісний сигнал відновлення.

### ❤️ `rhr_anomaly` — нетипові зміни пульсу у спокої

> 🙂 **Простими словами:** пульс у спокої може змінюватися через навантаження, недосип, стрес, температуру, хворобу або похибку вимірювання. Скрипт лише порівнює поточне значення з твоїм 28-денним діапазоном і виділяє нетипові відхилення, особливо якщо вони повторюються.

**Метод** (на основі Stanford / Snyder lab COVID-paper): для кожного дня обчислюється 28-денне середнє + SD resting HR **за попередні дні** (без today, щоб не було self-leakage). Z-score поточного дня:
- `z ≥ 2.5` → **HIGH** (сильна аномалія)
- `z ≥ 1.5` → **ELEVATED**
- `z ≤ −1.5` → **LOW** (нетипово низький — або супер-форма, або артефакт)
- інакше → **NORMAL**

Прапор `persistent = 1` виставляється, коли HIGH тримається 2+ дні поспіль. Це привід перевірити контекст і самопочуття, а не діагноз.

### 🌡️ `activity_weather` — погода + якість повітря для кожного тренування

> 🙂 **Простими словами:** коли ти йдеш на пробіжку і пульс був вищий ніж зазвичай — це через тебе (втомлений) чи через погоду (+30°C, задуха)? Скрипт автоматично дотягує історичну погоду й якість повітря на час та місце твого тренування. Далі легко побачити: "у жарку погоду мій пульс росте на 8 ударів — це нормальна реакція тіла на спеку, а не я в поганій формі".

Для кожної активності через Open-Meteo (безкоштовне API, без ключа) дотягуються:
- температура + відчувана температура + dewpoint
- вологість, вітер (м/с), опади, хмарність
- PM2.5, PM10, European AQI

Локація за замовчуванням — **Київ** (50.45, 30.52); можна перевизначити через `GARMIN_LAT` / `GARMIN_LON`. Використання: кореляція avg_hr / pace з умовами → персональна теплова крива, відповідь на "сьогодні було важко через мене чи через повітря".

### 🎲 `risk_scores` — шість щоденних індикаторів

> 🙂 **Простими словами:** це прозорі евристики, які стискають історію wearable-даних до шести сигналів: фізіологічні відхилення, зміна навантаження, автономне напруження, борг сну, реакція на спеку і тренд readiness.

> ⚠️ Ці індикатори не є медичним діагнозом, клінічною ймовірністю або персональним прогнозом травми. Вони лише допомагають помітити зміни у власних даних.

Нижче — розшифровка кожного показника. Кожен має посилання на наукову роботу, на якій побудована формула:

**Physiological Deviation Signal** (у БД збережена сумісна назва `illness_risk_score`, 0–100) — зважена комбінація відхилень rHR, HRV, дихання уві сні та SpO₂ від персонального baseline. Рівні LOW / SLIGHT / ELEVATED / HIGH описують силу одночасного відхилення доступних метрик, а не причину цього відхилення.

**ACWR** — **навантаження за тиждень проти навантаження за місяць.** Значення допомагає помітити різку зміну обсягу, але саме по собі не прогнозує травму і не визначає безпечне навантаження для конкретної людини.

**Autonomic Strain** (−100…+100) — **сумарний показник "ти в стресі чи відновлюєшся?".** Якщо пульс повзе вгору, а HRV — вниз за останні 7 днів, організм перемкнувся у режим "треба виживати" — класична картина перетренування або затяжного стресу. Якщо навпаки (пульс падає, HRV росте) — ти у фазі суперкомпенсації, саме час для важливої роботи.

**Sleep Debt** — **скільки годин сну ти винен собі за останні 2 тижні.** Рахує тільки недосипи, переспані години не "погашають" борг (як у реальному житті). Більше 14г боргу — помітно б'є по імунітету та концентрації.

**Heat Adaptation Index** — **наскільки тіло звикло до спеки.** Якщо влітку твій пульс на тій самій швидкості поступово падає, тіло адаптується. Якщо навпаки росте — зворотний процес (наприклад, після хвороби чи перерви).

**Readiness Decay** — **відрізняє "вчора перебрав" від "системно втомлююся".** Якщо готовність впала за останні 3–5 днів, але за місяць стабільна — це разова втома, відпочинок за 2–3 дні виправить. Якщо падає тиждень і місяць одночасно — це серйозний системний спад, треба розвантаження.

Усі індикатори обчислюються скриптом `analytics/risk_scores.py`, записуються у таблицю `risk_scores` і потрапляють у локальний звіт. Claude-шаблони можуть читати їх додатково.

### Щоденний цикл

```bash
# Типовий cron/launchd job:
python3 -m garmin_health daily
```

`run_all` запускає п'ять модулів незалежно — збій в одному не блокує інші. `risk_scores` виконується останнім, бо читає інші похідні таблиці.

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
| `GARMIN_LOG_PATH` | `./logs/bot.log`  | Шлях до rotating log |
| `GARMIN_REPORTS_DIR` | `./reports` | Каталог локальних звітів |
| `GARMIN_BACKUPS_DIR` | `./backups` | Каталог SQLite backups |
| `GARMIN_BACKUP_KEEP` | `7` | Кількість backup-файлів |
| `GARMIN_USER_ID`  | `1`           | `user_id` у таблицях |
| `GARMIN_LAT`      | `50.4501` (Київ) | Широта для `weather_enrich` |
| `GARMIN_LON`      | `30.5234` (Київ) | Довгота для `weather_enrich` |

```bash
export GARMIN_DB_PATH=~/data/health.db
export GARMIN_LAT=50.4501
export GARMIN_LON=30.5234
python3 -m garmin_health daily
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
      <string>cd "$HOME/garmin-data" &amp;&amp; .venv/bin/python -m garmin_health daily</string>
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
0 8 * * * cd "$HOME/garmin-data" && .venv/bin/python -m garmin_health daily
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
| `risk_scores` | Шість персональних індикаторів (deviation, ACWR, autonomic, sleep debt, heat, decay) | `(user_id, metric_date)` |

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
├── garmin_health/               # основний CLI, backup, healthcheck, report
├── garmy_sync.py                # CLI sync
├── analytics/                   # похідні метрики (ідемпотентні)
│   ├── common.py                #   DB helper, env config
│   ├── hrv_baseline.py          #   HRV 7d baseline (пт 4)
│   ├── rhr_anomaly.py           #   RHR z-score (пт 7)
│   ├── weather_enrich.py        #   Open-Meteo (пт 11)
│   ├── workout_segments.py      #   деталізація інтервалів
│   ├── risk_scores.py           #   шість wearable-індикаторів
│   └── run_all.py               #   one-shot runner
├── grafana/                     # дашборд (пт 9)
│   ├── docker-compose.yml       #   Grafana з health.db read-only
│   ├── provisioning/
│   │   ├── datasources/         #   sqlite datasource
│   │   └── dashboards/          #   provider
│   └── dashboards/
│       └── health-overview.json #   8-панельний дашборд
├── requirements.txt             # runtime-залежності
├── requirements-dev.txt         # тести та quality tools
├── README.md                    # цей файл
├── .gitignore                   # виключає БД, backups, reports, logs, venv
├── health.db                    # НЕ комітиться
├── backups/                     # НЕ комітиться
├── reports/                     # НЕ комітиться
└── logs/bot.log                 # НЕ комітиться
```

### Принципи

- **Тонкий шар над `garmy`.** Уся робота з Garmin API, ретраями, маппінгом — на боці бібліотеки.
- **Additive-only аналітика.** Пакет `analytics/` **нічого не модифікує** у Garmin-таблицях — лише читає їх і пише у власні нові таблиці через `CREATE TABLE IF NOT EXISTS` + `INSERT OR REPLACE`. Безпечно запускати будь-коли.
- **Мінімум runtime-залежностей.** `garmy[localdb]` + `requests`; product layer використовує stdlib.
- **Grafana read-only.** `health.db` монтується в контейнер як `:ro` volume — дашборд фізично не може щось зіпсувати.
- **Env-конфіг замість редагування коду.** Усі шляхи і координати виносяться у env.
- **Intervals — поза кодом.** Інтеграція через MCP-сервер, щоб не плодити API-ключі та не дублювати дані.

### Перевірка локально

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

python3 -m pytest -q
python3 -m black --check .
python3 -m isort --check-only .
python3 -m flake8 .
python3 -m compileall -q garmin_health analytics garmy_sync.py
```

---

## 📜 Ліцензія

MIT — вільне використання, модифікація, форки.

---

<p align="center">
  <sub>Побудовано поверх <a href="https://pypi.org/project/garmy/">garmy</a> · HRV baseline на основі методу <a href="https://marcoaltini.substack.com/">Marco Altini</a> · RHR anomaly на основі Stanford/Snyder lab paper · Погода від <a href="https://open-meteo.com/">Open-Meteo</a>.</sub>
</p>
