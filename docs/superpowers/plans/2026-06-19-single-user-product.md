# Single-User Garmin Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the repository into a reliable single-user local product that backs up Garmin data, runs analytics, checks data quality, and writes a deterministic daily report through one CLI.

**Architecture:** Add a focused `garmin_health` package around the existing sync and analytics modules. Keep Garmin-owned tables untouched, add only operational metadata, and make every network dependency degradable so the latest valid SQLite snapshot can still produce a report.

**Tech Stack:** Python 3.11, argparse, sqlite3, pathlib, pytest, Black, isort, flake8, GitHub Actions.

---

## File map

- `garmin_health/config.py`: runtime paths and single-user settings.
- `garmin_health/database.py`: SQLite connection policy, operational schema, backup and retention.
- `garmin_health/healthcheck.py`: structured freshness and completeness checks.
- `garmin_health/report.py`: SQLite-to-Markdown daily report.
- `garmin_health/pipeline.py`: daily orchestration, partial-failure policy and run history.
- `garmin_health/cli.py`: command parsing and terminal/JSON output.
- `garmin_health/__main__.py`: `python -m garmin_health` entrypoint.
- `tests/conftest.py`: representative temporary Garmin database fixture.
- `tests/test_database.py`: backup, integrity and retention behavior.
- `tests/test_healthcheck.py`: healthy, stale and incomplete snapshots.
- `tests/test_report.py`: complete and degraded Markdown reports.
- `tests/test_pipeline.py`: success, partial network failure and unusable DB.
- `tests/test_cli.py`: command routing and exit codes.
- `tests/test_sync_helpers.py`: date gap behavior and CLI validation.
- `tests/test_analytics.py`: stable helper boundaries in existing analytics.
- `.github/workflows/ci.yml`: actual quality gates.
- `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.flake8`: dependency and tool policy.
- `README.md`, `docs/setup.md`: one supported daily workflow and recovery instructions.

### Task 1: Reproducible developer environment and logging contract

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pyproject.toml`
- Modify: `.flake8`
- Modify: `analytics/common.py`
- Modify: `tests/test_logging.py`

- [ ] **Step 1: Extend the logging test before changing production code**

Add assertions that a warning is persisted in the rotating file and also emitted to stderr:

```python
configured.warning("visible warning")
for handler in configured.handlers:
    handler.flush()
assert "visible warning" in Path(file_handlers[0].baseFilename).read_text()
assert "visible warning" in capsys.readouterr().err
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv/bin/python -m pytest tests/test_logging.py -q`

Expected: FAIL because `_MaxLevelFilter(logging.INFO)` excludes warnings from the file.

- [ ] **Step 3: Implement the logging contract and tool configuration**

Remove the maximum-level filter from the rotating handler so it records `INFO+`; retain the `WARNING` stderr handler. Move pytest/Black/isort/flake8 to `requirements-dev.txt`, make that file include `-r requirements.txt`, and configure line length 100 consistently in `pyproject.toml` and `.flake8`.

- [ ] **Step 4: Install and verify the focused test GREEN**

Run: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest tests/test_logging.py -q`

Expected: PASS.

### Task 2: Runtime configuration and safe database operations

**Files:**
- Create: `garmin_health/__init__.py`
- Create: `garmin_health/config.py`
- Create: `garmin_health/database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write failing backup and retention tests**

Tests create a temporary SQLite source, call `create_backup(settings, keep=2)`, open the returned file, assert `PRAGMA quick_check == "ok"`, create two older backup files, call retention, and assert only the two newest backups remain.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/test_database.py -q`

Expected: collection error because `garmin_health.database` does not exist.

- [ ] **Step 3: Implement configuration and database helpers**

Define an immutable `Settings` dataclass with `project_root`, `db_path`, `log_path`, `reports_dir`, `backups_dir`, `lock_path`, `user_id`, and `backup_keep`. Implement `get_settings()` from env, `connect()` with row factory and `PRAGMA busy_timeout=5000`, `quick_check()`, `ensure_operational_schema()`, `create_backup()` using `sqlite3.Connection.backup`, and deterministic retention sorted by filename timestamp.

The operational table is:

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','partial','failed')),
    report_path TEXT,
    message TEXT
)
```

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_database.py -q`

Expected: PASS.

### Task 3: Structured healthcheck

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_healthcheck.py`
- Create: `garmin_health/healthcheck.py`

- [ ] **Step 1: Write failing healthy/stale/incomplete tests**

Build a fixture with `daily_health_metrics` plus optional analytics tables. Assert a current snapshot returns `usable=True` and `status="healthy"`; a two-day-old snapshot returns `usable=True` and `status="warning"`; a missing/empty daily table returns `usable=False` and `status="failed"`. Freeze the reference date by passing it explicitly to `run_healthcheck(settings, today=date(...))`.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/test_healthcheck.py -q`

Expected: collection error because the healthcheck module is absent.

- [ ] **Step 3: Implement healthcheck result models and checks**

Use dataclasses `Check(name, status, message, value)` and `HealthResult(status, usable, checks, latest_date)`. Inspect table existence through `sqlite_master`; query latest dates and seven completed days; treat optional analytics tables as warnings; treat missing DB, failed quick check, missing `daily_health_metrics`, or no daily rows as unusable.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_healthcheck.py -q`

Expected: PASS.

### Task 4: Deterministic daily report

**Files:**
- Create: `tests/test_report.py`
- Create: `garmin_health/report.py`

- [ ] **Step 1: Write failing complete and degraded report tests**

For a populated date assert the report contains the data date, sleep, HRV, resting HR, readiness, risk signal level, a data-quality section, and the medical disclaimer. For missing optional metrics assert report generation still succeeds and contains `Недостаточно данных` rather than fabricated values.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/test_report.py -q`

Expected: collection error because `garmin_health.report` is absent.

- [ ] **Step 3: Implement report queries, recommendation rules and atomic writes**

Implement `build_report(settings, target_date=None) -> Report` and `write_report(report, settings) -> Path`. Select the target row and optional joined analytics rows only when tables exist. Recommendation priority is: unusable data → no training recommendation; high anomaly or suppressed HRV → recovery; low readiness or short sleep → easy day; otherwise normal planned training. Write to a temporary file and replace both the dated report and `latest.md` atomically.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_report.py -q`

Expected: PASS.

### Task 5: Daily pipeline and concurrency lock

**Files:**
- Create: `tests/test_pipeline.py`
- Create: `garmin_health/pipeline.py`
- Modify: `analytics/run_all.py`
- Modify: `garmy_sync.py`

- [ ] **Step 1: Write failing pipeline tests**

Inject fake `backup`, `sync`, `analytics`, `healthcheck`, and `report` callables. Assert successful order is backup → sync → analytics → healthcheck → report and status is success. Make sync return failure while healthcheck is usable and assert status partial plus report creation. Make healthcheck unusable and assert failed plus no report. Assert a pre-existing lock raises an `AlreadyRunningError`.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -q`

Expected: collection error because `garmin_health.pipeline` is absent.

- [ ] **Step 3: Implement orchestration and adapters**

Create `PipelineResult(status, report_path, warnings)` and `run_daily(...)`. Record `running` before work and finalize the same `pipeline_runs` row. Use an exclusive lock-file create and always remove it in `finally`. Default adapters call `garmy_sync` for two days and `analytics.run_all.main()` without shelling out. Preserve independent analytics step handling and return details instead of only logging counts.

- [ ] **Step 4: Verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -q`

Expected: PASS.

### Task 6: Unified CLI

**Files:**
- Create: `tests/test_cli.py`
- Create: `tests/test_sync_helpers.py`
- Create: `garmin_health/cli.py`
- Create: `garmin_health/__main__.py`
- Modify: `garmy_sync.py`

- [ ] **Step 1: Write failing CLI and validation tests**

Assert parsers expose exactly `daily`, `report`, `healthcheck`, `backup`, and `analytics`; JSON healthcheck output parses; partial daily result exits 0; failed daily exits 1; backup prints its path. Add sync helper tests for contiguous gap ranges and reject `days <= 0` using `argparse.ArgumentTypeError`.

- [ ] **Step 2: Verify RED**

Run: `.venv/bin/python -m pytest tests/test_cli.py tests/test_sync_helpers.py -q`

Expected: collection error or parser assertion failure.

- [ ] **Step 3: Implement CLI routing and positive-day validation**

Build one parser with five subcommands, inject command services into `main()` for tests, and serialize healthcheck dataclasses with `dataclasses.asdict`. Add `positive_int()` to `garmy_sync.py` and use it for the positional days argument.

- [ ] **Step 4: Verify GREEN and smoke help**

Run: `.venv/bin/python -m pytest tests/test_cli.py tests/test_sync_helpers.py -q && .venv/bin/python -m garmin_health --help`

Expected: tests PASS and help lists five commands.

### Task 7: Analytics boundary regression tests and claim cleanup

**Files:**
- Create: `tests/test_analytics.py`
- Modify: `analytics/rhr_anomaly.py`
- Modify: `analytics/risk_scores.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing or characterizing tests for public helper boundaries**

Test RHR classification immediately below/at 1.5 and 2.5, zero-variance handling, sleep-debt levels, ACWR zero chronic load, and lap classification for warmup/work/recovery. If existing behavior is internally consistent, tests characterize it before wording-only changes; if a boundary contradicts the module docstring, assert the documented behavior and observe RED.

- [ ] **Step 2: Run focused analytics tests**

Run: `.venv/bin/python -m pytest tests/test_analytics.py -q`

Expected: PASS for characterized behavior or a specific boundary FAIL documented by the test.

- [ ] **Step 3: Make only required boundary fixes and replace medical claims**

Keep persisted column names for compatibility, but describe illness score as `індикатор фізіологічного відхилення`, remove `автоматичний лікар`, probability and diagnostic language, and add a clear non-medical disclaimer.

- [ ] **Step 4: Verify analytics suite GREEN**

Run: `.venv/bin/python -m pytest tests/test_analytics.py -q`

Expected: PASS.

### Task 8: CI, setup docs and end-to-end acceptance

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/setup.md`

- [ ] **Step 1: Update CI gates and ignored runtime artifacts**

Install `requirements-dev.txt`; run pytest, Black check, isort check, flake8, compileall, Grafana JSON and YAML validation. Ignore `reports/`, `backups/`, `logs/` and `*.lock` while keeping templates tracked.

- [ ] **Step 2: Rewrite the supported operating path**

Document virtualenv setup, first sync, `python -m garmin_health daily`, healthcheck, report locations, launchd configuration, backup retention and restore. Correct stale statements about three analytics modules, two dependencies and `sync.log`. Keep Claude/Notion/Grafana under optional integrations.

- [ ] **Step 3: Run the complete quality gate**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m black --check .
.venv/bin/python -m isort --check-only .
.venv/bin/python -m flake8 .
.venv/bin/python -m compileall -q garmin_health analytics garmy_sync.py
```

Expected: every command exits 0.

- [ ] **Step 4: Run isolated end-to-end acceptance**

Create a temporary representative database through the test fixture or a dedicated test helper, set `GARMIN_DB_PATH`, `GARMIN_REPORTS_DIR`, `GARMIN_BACKUPS_DIR`, and run `report`, `healthcheck --json`, and `backup`. Run the real local database in read-only product modes `healthcheck --json` and `report`, then verify `PRAGMA quick_check`, report content and that no Garmin-owned table schema changed.

- [ ] **Step 5: Audit every design criterion**

Map the eight criteria in `docs/superpowers/specs/2026-06-18-single-user-product-design.md` to command output, tests or schema inspection. Do not claim completion while any criterion lacks direct evidence.
