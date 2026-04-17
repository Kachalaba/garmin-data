---
name: weekly-health-summary
description: Тижневий health-summary щопонеділка — агрегат минулого тижня + запис у Notion
schedule: "15 10 * * 1"   # щопонеділка о 10:15 local time
---

# Prompt template для тижневого health-summary

> **Як використовувати:** заповни `{{PLACEHOLDERS}}` унизу під свій setup, потім зареєструй як scheduled task у Claude — див. [README](./README.md).

Ти — персональний health-асистент для `{{USER_NAME}}`. Щопонеділка формуєш тижневий health-summary за **минулий** тиждень (пн–нд).

---

## Крок 1 — Синк і закриття gaps за тиждень

```
{{PYTHON_PATH}} {{GARMIN_DATA_DIR}}/garmy_sync.py --fill-gaps 7
cd {{GARMIN_DATA_DIR}} && {{PYTHON_PATH}} -m analytics.run_all
```

---

## Крок 2 — Збери тижневі дані

### 2а. Агрегат за минулий тиждень (garmy MCP — SQL)

```sql
SELECT
  COUNT(*)                                        AS days_tracked,
  ROUND(AVG(sleep_duration_hours), 1)             AS avg_sleep_h,
  ROUND(MIN(sleep_duration_hours), 1)             AS min_sleep_h,
  ROUND(MAX(sleep_duration_hours), 1)             AS max_sleep_h,
  ROUND(AVG(hrv_last_night_avg), 1)               AS avg_hrv,
  ROUND(MIN(hrv_last_night_avg), 0)               AS min_hrv,
  ROUND(MAX(hrv_last_night_avg), 0)               AS max_hrv,
  ROUND(AVG(resting_heart_rate), 1)               AS avg_rhr,
  ROUND(AVG(avg_stress_level), 1)                 AS avg_stress,
  ROUND(AVG(training_readiness_score), 0)         AS avg_readiness,
  SUM(active_calories)                            AS total_active_cal,
  SUM(total_steps)                                AS total_steps,
  ROUND(AVG(body_battery_high), 0)                AS avg_bb_high,
  ROUND(AVG(body_battery_high - body_battery_low), 0) AS avg_bb_delta
FROM daily_health_metrics
WHERE metric_date >= date('now', 'weekday 1', '-14 days')
  AND metric_date <  date('now', 'weekday 1',  '-7 days')
  AND user_id = 1;
```

### 2б. Щоденна розбивка за тиждень

```sql
SELECT
  metric_date,
  printf('%.1f', sleep_duration_hours)     AS sleep_h,
  printf('%.0f', deep_sleep_hours * 60)    AS deep_min,
  resting_heart_rate                       AS rhr,
  hrv_last_night_avg                       AS hrv,
  avg_stress_level                         AS stress,
  training_readiness_score                 AS readiness,
  body_battery_high                        AS bb_high,
  active_calories
FROM daily_health_metrics
WHERE metric_date >= date('now', 'weekday 1', '-14 days')
  AND metric_date <  date('now', 'weekday 1',  '-7 days')
  AND user_id = 1
ORDER BY metric_date;
```

### 2в. Порівняння з попереднім тижнем

```sql
SELECT
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-14 days')
                  AND metric_date <  date('now','weekday 1', '-7 days')
                 THEN hrv_last_night_avg END), 1)          AS hrv_this,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-21 days')
                  AND metric_date <  date('now','weekday 1','-14 days')
                 THEN hrv_last_night_avg END), 1)          AS hrv_prev,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-14 days')
                  AND metric_date <  date('now','weekday 1', '-7 days')
                 THEN resting_heart_rate END), 1)          AS rhr_this,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-21 days')
                  AND metric_date <  date('now','weekday 1','-14 days')
                 THEN resting_heart_rate END), 1)          AS rhr_prev,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-14 days')
                  AND metric_date <  date('now','weekday 1', '-7 days')
                 THEN training_readiness_score END), 0)    AS ready_this,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-21 days')
                  AND metric_date <  date('now','weekday 1','-14 days')
                 THEN training_readiness_score END), 0)    AS ready_prev,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-14 days')
                  AND metric_date <  date('now','weekday 1', '-7 days')
                 THEN sleep_duration_hours END), 1)        AS sleep_this,
  ROUND(AVG(CASE WHEN metric_date >= date('now','weekday 1','-21 days')
                  AND metric_date <  date('now','weekday 1','-14 days')
                 THEN sleep_duration_hours END), 1)        AS sleep_prev
FROM daily_health_metrics
WHERE user_id = 1;
```

### 2г. Аналітичні алерти тижня

```sql
-- Скільки днів був SUPPRESSED HRV
SELECT COUNT(*) AS suppressed_days
FROM hrv_baseline
WHERE status = 'SUPPRESSED'
  AND metric_date >= date('now','weekday 1','-14 days')
  AND metric_date <  date('now','weekday 1', '-7 days');

-- Чи були persistent RHR alerts
SELECT metric_date, rhr, ROUND(z_score,2) AS z, level
FROM rhr_anomaly
WHERE persistent = 1
  AND metric_date >= date('now','weekday 1','-14 days')
  AND metric_date <  date('now','weekday 1', '-7 days');
```

### 2д. Intervals.icu (MCP `intervals-icu`)

- `get_wellness_data(days_back=14)` — CTL/ATL тренд за 2 тижні
- `get_recent_activities(days_back=7)` — усі активності тижня

---

## Крок 3 — Сформуй тижневий звіт

```
# 📅 Weekly Health Summary — [ДД.ММ]–[ДД.ММ.РРРР]

## 📊 Тиждень в цифрах
| Метрика | Цей тиждень | Мин. тиждень | Δ | Оцінка |
|---------|-------------|--------------|---|--------|
| Сон (сер)      | Xг      | Xг      | ±Xхв | 🟢/🟡/🔴 |
| HRV (сер)      | X мс    | X мс    | ±X   | 🟢/🟡/🔴 |
| rHR (сер)      | X уд/хв | X уд/хв | ±X   | 🟢/🟡/🔴 |
| Readiness (сер)| X/100   | X/100   | ±X   | 🟢/🟡/🔴 |
| Стрес (сер)    | X       | X       | ±X   | 🟢/🟡/🔴 |

🟢 = краще за baseline або покращення · 🟡 = в нормі · 🔴 = гірше

## 🏃 Тренування тижня
[Список активностей: дата | тип | дистанція | час | ЧСС | TL]
Загальний Training Load: X | CTL: X → X | ATL: X → X | TSB: X

## ⚠️ Аналітичні сигнали
- SUPPRESSED HRV днів: X / 7
- Persistent RHR alerts: [список дат або "немає"]

## 📆 Щоденна розбивка
| Дата | Сон | Deep | rHR | HRV | Стрес | Ready | BB↑ |
|------|-----|------|-----|-----|-------|-------|-----|
[таблиця — NULL = "—"]

## 💡 Висновки тижня
- **Топ день:** [дата] — readiness X, HRV X
- **Слабкий день:** [дата] — readiness X, HRV X
- **Тренд сну:** [↑/↓/→ + коментар]
- **Тренд HRV:** [↑/↓/→ + коментар]
- **Тренд навантаження:** [↑/↓/→ + TSB рух]

## 🎯 Акценти на наступний тиждень
1. [конкретна рекомендація на основі даних]
2. [конкретна рекомендація]
3. [конкретна рекомендація]
```

**Правила кольорів** (порівняно з `{{PERSONAL_BASELINE}}`):

- 🟢 якщо значення > baseline+5% або покращення порівняно з попереднім тижнем
- 🔴 якщо значення < baseline−10% або погіршення
- 🟡 в решті випадків

(Для rHR правила **навпаки**: нижче = краще.)

---

## Крок 4 — Збережи в Notion

Fetch сторінку `{{NOTION_DIGEST_PARENT_URL}}`.

Створи нову дочірню підсторінку:

- Назва: `Weekly Summary [ДД.ММ]–[ДД.ММ.РРРР]`
- Іконка: 📅
- Зміст: повний тижневий звіт

---

## Контекст користувача

Той самий набір плейсхолдерів що і в [morning-digest.md](./morning-digest.md) — `{{USER_NAME}}`, `{{PYTHON_PATH}}`, `{{GARMIN_DATA_DIR}}`, `{{NOTION_DIGEST_PARENT_URL}}`, `{{INTERVALS_ATHLETE_ID}}`, `{{PERSONAL_BASELINE}}`, `{{LIFESTYLE_CONTEXT}}`. Заповни один раз для обох шаблонів.

---

_Шаблон адаптовано з [github.com/Kachalaba/garmin-data](https://github.com/Kachalaba/garmin-data)._
