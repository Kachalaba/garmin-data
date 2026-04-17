# 🤖 Scheduled routines

Це публічні шаблони двох Claude-рутин, які формують дайджести у Notion:

| Файл | Коли запускається | Що робить |
|------|--------------------|-----------|
| [`morning-digest.md`](./morning-digest.md) | `0 10 * * *` (щодня о 10:00) | Синк Garmin → аналіз → сторінка "Digest YYYY-MM-DD" у Notion + рядок в архіві |
| [`weekly-summary.md`](./weekly-summary.md) | `15 10 * * 1` (понеділок о 10:15) | Агрегат за минулий тиждень → сторінка "Weekly Summary" у Notion |

Це **не** Python-скрипти. Це промпти для Claude-агента (через MCP-сервер [`scheduled-tasks`](https://github.com/apify/actor-mcp-server)). Логіка "витягни SQL, проаналізуй, запиши в Notion" виконується LLM у момент запуску.

## Як зареєструвати у себе

### Передумови

Встановлено і налаштовано MCP-сервери у твоєму клієнті Claude (Desktop / Code):
- `garmy` — читає локальну `health.db`
- `intervals-icu` — тягне CTL/ATL/TSB + активності
- `notion` — пише сторінки
- `scheduled-tasks` — реєструє cron-завдання всередині Claude

Див. [`docs/setup.md`](../setup.md) для покрокового встановлення.

### Реєстрація

Для обох рутин процедура однакова:

1. У Claude відкрий чат і виконай:
   ```
   Use mcp__scheduled-tasks__create_scheduled_task to register a new task with:
     taskId: morning-health-digest
     cron: 0 10 * * *
     promptFile: docs/routines/morning-digest.md
   ```
   (клієнт сам прочитає файл і запише prompt у scheduled-tasks)

2. Перевір що зареєструвалось:
   ```
   Use mcp__scheduled-tasks__list_scheduled_tasks
   ```

3. Перед першим автоматичним запуском — запусти вручну щоб переконатись що все працює:
   - У чаті: "Run morning-digest prompt" → повинно створитись сторінку в Notion
   - Якщо щось пішло не так — поправ prompt і перезареєструй

### Кастомізація під себе

Обидва шаблони мають внизу секцію `## Контекст користувача` з плейсхолдерами (`{{USER_NAME}}`, `{{INTERVALS_ATHLETE_ID}}`, baseline тощо). **Заповни їх перед реєстрацією** — від цього залежить якість аналізу.

Baseline числа (середнє HRV/rHR/сон за 30 днів) можна або:
- залишити `~0` на початку і оновити через місяць коли накопичаться дані;
- порахувати одразу SQL-запитом:
  ```sql
  SELECT
    ROUND(AVG(hrv_last_night_avg), 0) AS hrv,
    ROUND(AVG(resting_heart_rate), 0) AS rhr,
    ROUND(AVG(sleep_duration_hours), 1) AS sleep,
    ROUND(AVG(training_readiness_score), 0) AS ready
  FROM daily_health_metrics
  WHERE metric_date >= date('now','-30 days');
  ```

### Куди воно пишеться фізично

Після реєстрації Claude зберігає prompt у:
```
~/.claude/scheduled-tasks/{taskId}/SKILL.md
```
(структура може бути іншою залежно від клієнта — перевір у своїй документації MCP). Цей файл **не** комітити: він містить підставлені значення для твого акаунту. Git-версія — публічний шаблон у цій теці.
