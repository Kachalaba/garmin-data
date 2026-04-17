# 🛠️ Setup guide — з нуля до працюючого pipeline

Цей документ веде від чистого клону репо до повністю працюючої системи: щоденний sync + аналітика + Grafana + Claude-рутини, що пишуть у Notion.

> ⏱️ **Час на повне налаштування:** ~30–45 хв, з них ~15 хв — очікування поки накопичиться перша історія даних для baseline'ів.

---

## 0. Передумови

| Потрібне | Як перевірити |
|----------|---------------|
| Python 3.11+ | `python3 --version` |
| Git | `git --version` |
| Docker Desktop або OrbStack (для Grafana, опційно) | `docker --version` |
| Claude Desktop або Claude Code (для рутин, опційно) | — |
| Garmin-годинник / браслет з активованим обліковим записом Garmin Connect | — |

Якщо Grafana / Claude / Notion тобі не потрібні — достатньо перших двох, зможеш використовувати `health.db` напряму через `sqlite3`.

---

## 1. Клонуй і встанови залежності

```bash
git clone https://github.com/Kachalaba/garmin-data.git
cd garmin-data

python3 -m venv .venv
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
pip install -r requirements.txt
```

Що у `requirements.txt`: `garmy` (Garmin API) + `requests` (Open-Meteo). Все інше — stdlib.

---

## 2. Перший sync — авторизація в Garmin Connect

```bash
python3 garmy_sync.py 1
```

Бібліотека `garmy` запитає логін і пароль Garmin Connect. Credential'и зберігаються у `~/.garth/` — далі цього вводу не буде.

Далі довантаж історію за 30 днів — це дасть baseline'ам першу порцію даних для розрахунку:

```bash
python3 garmy_sync.py 30
```

Перевір, що дані з'явилися:

```bash
python3 garmy_sync.py --status 7
```

Очікувано: 7 рядків, у колонках ✓/✗ переважно ✓.

---

## 3. (Опційно) env-конфіг

За замовчуванням усе працює з defaults (Київ, `./health.db`). Якщо живеш в іншому місті — скопіюй `.env.example` і відредагуй:

```bash
cp .env.example .env
$EDITOR .env
```

Скрипти `.env` **не читають самі** — підхоплюють тільки з експортованих env var. Для автозавантаження використай `direnv` або додай `set -a; source .env; set +a` у свій shell профіль.

---

## 4. Похідна аналітика

```bash
python3 -m analytics.run_all
```

Запустить три ідемпотентні пайплайни:
- `hrv_baseline` — log-HRV baseline + статус SUPPRESSED/NORMAL/ELEVATED
- `rhr_anomaly` — 28-денний z-score RHR + persistent flag
- `weather_enrich` — Open-Meteo погода для кожної активності

На **перші 7–14 днів** статуси будуть `UNKNOWN` / `NULL` — це нормально, математика потребує історії. Після 30 днів даних вони стабілізуються.

Перевір:

```bash
sqlite3 health.db "SELECT metric_date, status FROM hrv_baseline ORDER BY metric_date DESC LIMIT 7;"
```

---

## 5. Автоматичний щоденний sync

### macOS — launchd

Створи `~/Library/LaunchAgents/com.user.garmy-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.garmy-sync</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>-c</string>
      <string>cd ~/garmin-data &amp;&amp; .venv/bin/python garmy_sync.py 2 ; .venv/bin/python -m analytics.run_all</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <key>StandardOutPath</key><string>/tmp/garmy-sync.out</string>
    <key>StandardErrorPath</key><string>/tmp/garmy-sync.err</string>
</dict>
</plist>
```

Зверни увагу: `;` між sync і analytics (а не `&&`) — щоб аналітика перерахувалась навіть якщо sync частково впав (мережа).

```bash
launchctl load ~/Library/LaunchAgents/com.user.garmy-sync.plist
launchctl list | grep garmy-sync            # перевір що завантажилось
launchctl start com.user.garmy-sync         # запусти прямо зараз для тесту
cat /tmp/garmy-sync.out                     # подивись вивід
```

### Linux — cron

```cron
0 8 * * * cd ~/garmin-data && .venv/bin/python garmy_sync.py 2 ; .venv/bin/python -m analytics.run_all
```

---

## 6. (Опційно) Grafana дашборд

Потрібен Docker Desktop або OrbStack.

```bash
cd grafana
docker compose up -d
open http://localhost:3000          # логін: admin / admin (попросить змінити)
```

Дашборд `Garmin — Health overview` з'явиться в `Dashboards` → `Browse`. База монтується як **read-only** volume — дашборд фізично не може нічого зіпсувати.

Зупинити:
```bash
docker compose down                 # зберігає налаштування Grafana
docker compose down -v              # повне очищення
```

Детальніше — у [`grafana/`](../grafana/) теці й у секції "Grafana дашборд" в головному README.

---

## 7. (Опційно) Claude-рутини + Notion

Цей крок дає щоденний і щотижневий health-digest у Notion з автоматичною інтерпретацією. Якщо не використовуєш Claude — пропусти.

### 7.1. Створи parent-сторінку у Notion

Див. [`notion-template.md`](./notion-template.md) — покроково. Забери URL сторінки.

### 7.2. Налаштуй MCP-сервери у Claude

У конфігу Claude (`~/Library/Application Support/Claude/claude_desktop_config.json` на macOS або через `claude mcp add` для Claude Code) додай:

- **garmy** — читає `health.db`. Конфіг у [docs garmy](https://github.com/mberaty/garmy).
- **intervals-icu** — CTL/ATL/TSB. Потрібен API-key з [intervals.icu/settings](https://intervals.icu/settings).
- **notion** — пише сторінки. Потрібен integration token (див. [`notion-template.md`](./notion-template.md) секція MCP-доступ).
- **scheduled-tasks** — реєструє cron-таски. Встановлюється як npm-пакет у Claude.

### 7.3. Заповни плейсхолдери в prompt-шаблонах

Відкрий [`routines/morning-digest.md`](./routines/morning-digest.md) і [`routines/weekly-summary.md`](./routines/weekly-summary.md), заповни всі `{{PLACEHOLDERS}}` у секції "Контекст користувача" внизу файлу:

- `{{USER_NAME}}` — твоє ім'я
- `{{PYTHON_PATH}}` — абсолютний шлях до Python у venv
- `{{GARMIN_DATA_DIR}}` — абсолютний шлях до клонованого репо
- `{{NOTION_DIGEST_PARENT_URL}}` — URL зі кроку 7.1
- `{{INTERVALS_ATHLETE_ID}}` — зі [intervals.icu/settings](https://intervals.icu/settings)
- `{{PERSONAL_BASELINE}}` — твої типові HRV / rHR / сон за 30 днів (порахуй SQL-запитом з `routines/README.md`)
- `{{LIFESTYLE_CONTEXT}}` — що ще впливає на readiness (або видали секцію)

> ⚠️ **Не коміть заповнені версії у публічний репо.** Зазвичай заповнюєш на льоту, коли реєструєш task у Claude — заповнені prompt'и зберігаються у `~/.claude/scheduled-tasks/{taskId}/SKILL.md` і у git **не** потрапляють.

### 7.4. Зареєструй scheduled-tasks

У чаті з Claude:

```
Use mcp__scheduled-tasks__create_scheduled_task to register:
  taskId: morning-health-digest
  cron: 0 10 * * *
  promptFile: docs/routines/morning-digest.md
```

І те саме для weekly:

```
Use mcp__scheduled-tasks__create_scheduled_task to register:
  taskId: weekly-health-summary
  cron: 15 10 * * 1
  promptFile: docs/routines/weekly-summary.md
```

Перевір:

```
Use mcp__scheduled-tasks__list_scheduled_tasks
```

### 7.5. Тестовий запуск вручну

```
У Claude: "Run morning-health-digest prompt now"
```

Має з'явитись новий рядок в архівній таблиці Notion і дочірня сторінка `Digest YYYY-MM-DD`. Якщо щось не так — поправ prompt і перезареєструй.

---

## 8. Як усе оновлювати

```bash
cd ~/garmin-data
git pull
source .venv/bin/activate
pip install -r requirements.txt --upgrade
```

Аналітичні таблиці залишаться — скрипти ідемпотентні, нічого не зламають. Якщо додались нові поля в `daily_health_metrics` — перезапусти `python3 -m analytics.run_all`.

---

## 🐛 Troubleshooting

| Симптом | Причина | Фікс |
|---------|---------|------|
| `garmy_sync.py` падає з 401 | expired token | Видалити `~/.garth/` і залогінитись знову |
| `--status` показує ✗ у Sleep за вчорашню ніч | дані ще не синхронізувались у Garmin Cloud | Подихай годинником ще раз через годину; або `--fill-gaps 3` пізніше |
| `hrv_baseline.status = UNKNOWN` для всіх днів | менше 7 днів історії HRV | Почекати тиждень або `python3 garmy_sync.py 30` |
| Grafana показує "No data" у всіх панелях | datasource UID не збігається | Перевір `grafana/provisioning/datasources/sqlite.yml` — має бути `uid: health-db` |
| Grafana показує дати у 55 тисячному році | SQL string→int coercion у старій версії dashboard | `git pull` — фікс у `CAST(strftime('%s', X) AS INTEGER)` |
| Claude-рутина не знаходить архівну таблицю в Notion | не той заголовок у parent-сторінці | Перейменуй секцію у Notion на `## 📋 Архів дайджестів` (саме так) |

---

_Якщо щось не покрите цим гайдом — відкрий issue на [github.com/Kachalaba/garmin-data](https://github.com/Kachalaba/garmin-data/issues)._
