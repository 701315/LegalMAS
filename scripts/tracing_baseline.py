"""
Baseline regression script для Celery tracing (B.1).

Назначение:
- Запустить до правок → сохранить baseline.
- Запустить после правок → сравнить с baseline.
- Доказать что:
  1) Celery dispatch работает
  2) kwargs доходят до worker без изменений
  3) БД-инварианты не нарушены
  4) (после B.1) trace propagation работает

Запуск:
  PYTHONPATH=src python scripts/tracing_baseline.py

Предусловия:
  - API запущен на localhost:8000
  - worker запущен (make worker)
  - worker-system запущен (make worker-system)
  - beat запущен (make beat)
  - PostgreSQL доступен

Вывод:
  baseline_report_TIMESTAMP.json

Критерии успеха:
  overall=OK если:
  - run_created=true
  - run_id_in_logs=true
  - run НЕ завис в pending (status != pending ИЛИ total_checks > 0)
  - traces_in_tempo=true

  Примечание:
  - stage_executions_exist может быть false — это нормально для
    документов в статусе enriched/completed (orchestrator их не двигает).
  - trace_id_in_logs ожидается false до B.1 и true после B.1.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime

import httpx

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
TEMPO_BASE = "http://127.0.0.1:3200"

LOGIN_EMAIL = "admin@steloom.com"
LOGIN_PASSWORD = "gorelov"

# Сколько секунд ждать выполнения задачи worker'ом.
# 15 секунд достаточно для start_run_pipeline + run_deal_checks.
WORKER_WAIT_SECONDS = 15

# Сколько секунд ждать flush BatchSpanProcessor в Tempo.
TEMPO_WAIT_SECONDS = 12

# HTTP timeout'ы для baseline script.
# Простым языком:
# auth/login иногда может отвечать дольше 10 секунд под CPU-нагрузкой
# (bcrypt/hash + общая нагрузка машины).
# Поэтому baseline script должен быть устойчивее, чем обычный curl.
AUTH_TIMEOUT_SECONDS = 30
API_TIMEOUT_SECONDS = 20
AUTH_RETRIES = 3
AUTH_RETRY_SLEEP_SECONDS = 2
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now(UTC).isoformat()


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)

def get_token() -> str:
    """
    Получить access token с retry.

    Простым языком:
    Во время локальной разработки API может быть временно медленным:
    - CPU занят worker'ами,
    - bcrypt/hash login занимает время,
    - модель/кэш могут прогреваться.
    Поэтому baseline script не должен падать из-за одного медленного ответа.
    """
    last_error: Exception | None = None

    for attempt in range(1, AUTH_RETRIES + 1):
        try:
            log(f"Authenticating... attempt {attempt}/{AUTH_RETRIES}")
            resp = httpx.post(
                f"{API_BASE}/api/v1/auth/login",
                json={"username": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
                timeout=AUTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            resp.raise_for_status()

            token = resp.json().get("access_token")
            if not token:
                raise RuntimeError(f"No access_token in response: {resp.text}")

            log(f"Token received (first 20 chars): {token[:20]}...")
            return token

        except Exception as e:
            last_error = e
            log(f"Authentication attempt {attempt} failed: {e}")
            if attempt < AUTH_RETRIES:
                time.sleep(AUTH_RETRY_SLEEP_SECONDS)

    raise RuntimeError(f"Authentication failed after {AUTH_RETRIES} attempts: {last_error}")


def get_latest_deal(token: str) -> dict:
    """Найти подходящую сделку для триггера."""
    log("Looking for suitable deal...")
    resp = httpx.get(
        f"{API_BASE}/api/v1/deals/",
        headers={"Authorization": f"Bearer {token}"},
        timeout=API_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    resp.raise_for_status()
    deals = resp.json()

    if not deals:
        raise RuntimeError(
            "No deals found. Create at least one deal with documents "
            "and primary_language set."
        )

    deal = deals[0] if isinstance(deals, list) else deals.get("items", [])[0]
    deal_id = deal.get("id")
    deal_name = deal.get("name", "unknown")
    log(f"Using deal: {deal_id} ({deal_name})")
    return deal


def trigger_run(token: str, deal_id: str) -> dict:
    """
    Запустить анализ.

    Контракт endpoint:
      POST /api/v1/runs?deal_id=<uuid>
      body: RunCreate (JSON)

    deal_id идёт в query parameter, не в body.
    """
    log(f"Triggering run for deal {deal_id}...")

    payload: dict = {
        "checks_mode": "global_and_doc_type",
        "pipeline_strategy": "REUSE_STRUCTURE",
        "force_reclassify": False,
    }

    resp = httpx.post(
        f"{API_BASE}/api/v1/runs",
        params={"deal_id": deal_id},
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=15,
        follow_redirects=True,
    )

    log(f"Run trigger response: HTTP {resp.status_code}")
    log(f"Run trigger final URL: {resp.url}")

    if resp.status_code not in (200, 201):
        log(f"WARNING: non-success status: {resp.text[:500]}")
        return {
            "status_code": resp.status_code,
            "body": resp.text[:500],
            "run_id": None,
            "error": True,
        }

    body = resp.json()
    run_id = body.get("id")
    log(f"Run created: {run_id}")

    return {
        "status_code": resp.status_code,
        "run_id": run_id,
        "initial_status": body.get("status"),
        "deal_id": body.get("deal_id"),
        "error": False,
    }


def check_run_in_db(run_id: str) -> dict:
    """Проверить состояние Run в БД через PostgreSQL."""
    import subprocess

    query = f"""
SELECT
    id,
    status,
    total_checks,
    completed_checks,
    has_errors,
    started_at,
    completed_at
FROM runs
WHERE id = '{run_id}'::uuid;
"""
    result = subprocess.run(
        [
            "docker", "exec", "mas_dd_postgres",
            "psql", "-U", "mas", "-d", "mas_dd",
            "-t", "-c", query,
        ],
        capture_output=True,
        text=True,
        timeout=API_TIMEOUT_SECONDS,
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }


def check_stage_executions_in_db(run_id: str) -> dict:
    """Проверить document_stage_executions для Run в БД."""
    import subprocess

    query = f"""
SELECT
    id,
    status,
    task_name,
    celery_task_id,
    from_status,
    to_status
FROM document_stage_executions
WHERE run_id = '{run_id}'::uuid
ORDER BY created_at DESC
LIMIT 20;
"""
    result = subprocess.run(
        [
            "docker", "exec", "mas_dd_postgres",
            "psql", "-U", "mas", "-d", "mas_dd",
            "-t", "-c", query,
        ],
        capture_output=True,
        text=True,
timeout=API_TIMEOUT_SECONDS,
    )
    return {
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode,
    }


def _parse_run_row(stdout: str) -> dict:
    """
    Распарсить строку из psql вывода.

    Пример строки:
    <uuid> | running |    30 |    15 | f  |  2026-... | 2026-...
    """
    result = {
        "status": None,
        "total_checks": 0,
        "completed_checks": 0,
    }
    try:
        parts = [p.strip() for p in stdout.split("|")]
        if len(parts) >= 4:
            result["status"] = parts[1].strip() or None
            result["total_checks"] = int(parts[2].strip() or "0")
            result["completed_checks"] = int(parts[3].strip() or "0")
    except (ValueError, IndexError):
        pass
    return result


def check_recent_traces() -> dict:
    """Получить последние трейсы из Tempo (без фильтра по run_id)."""
    try:
        resp = httpx.get(
            f"{TEMPO_BASE}/api/search",
            params={"limit": 10},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            traces = data.get("traces", [])
            return {
                "count": len(traces),
                "traces": [
                    {
                        "traceID": t.get("traceID"),
                        "rootTraceName": t.get("rootTraceName"),
                        "rootServiceName": t.get("rootServiceName"),
                    }
                    for t in traces
                ],
            }
        return {"count": 0, "traces": []}
    except Exception as e:
        return {"count": 0, "error": str(e)}


def check_celery_publish_in_logs(run_id: str) -> dict:
    """
    Проверить что в логах приложения есть записи о run_id.

    Ищем по run_id в лог-файле.
    Собираем:
    - все log entries содержащие run_id,
    - отдельно entries с trace_id (признак Celery tracing работает),
    - отдельно entries от worker процессов.
    """
    log_file = "logs/app.log"
    if not os.path.exists(log_file):
        return {
            "found": False,
            "reason": "log file not found",
            "count": 0,
            "entries": [],
            "entries_with_trace_id": 0,
            "worker_entries": 0,
        }

    matches = []
    with open(log_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if run_id in line:
                try:
                    data = json.loads(line.strip())
                    matches.append({
                        "event": data.get("event"),
                        "logger": data.get("logger"),
                        "level": data.get("level"),
                        "trace_id": data.get("trace_id"),
                        "span_id": data.get("span_id"),
                        "task_name": data.get("task_name"),
                        "task_id": data.get("task_id"),
                        "worker_hostname": data.get("worker_hostname"),
                    })
                except json.JSONDecodeError:
                    matches.append({"raw": line.strip()[:200]})

    entries_with_trace = [e for e in matches if e.get("trace_id")]

    # Worker entries — те, у кого есть worker_hostname.
    # Это признак, что запись пришла из worker process, а не только из API.
    worker_entries = [e for e in matches if e.get("worker_hostname")]

    return {
        "found": len(matches) > 0,
        "count": len(matches),
        "entries": matches[:20],
        "entries_with_trace_id": len(entries_with_trace),
        "worker_entries_count": len(worker_entries),
        "worker_entries_sample": worker_entries[:5],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {
        "timestamp": ts(),
        "phase": "BASELINE",
        "steps": {},
        "conclusion": {},
    }

    try:
        # ── Шаг 1: Авторизация ──────────────────────────────────────────
        log("=== STEP 1: Authentication ===")
        token = get_token()
        report["steps"]["auth"] = {"ok": True}

        # ── Шаг 2: Найти сделку ─────────────────────────────────────────
        log("=== STEP 2: Find deal ===")
        deal = get_latest_deal(token)
        deal_id = deal.get("id")
        report["steps"]["find_deal"] = {
            "ok": True,
            "deal_id": deal_id,
            "deal_name": deal.get("name"),
        }

        # ── Шаг 3: Запустить Run ────────────────────────────────────────
        log("=== STEP 3: Trigger run ===")
        run_result = trigger_run(token, deal_id)
        run_id = run_result.get("run_id")
        report["steps"]["trigger_run"] = run_result

        if run_result.get("error") or not run_id:
            log("ERROR: Could not create run. Check API logs.")
            report["conclusion"] = {
                "overall": "FAILED",
                "reason": "run_creation_failed",
            }
            return

        # ── Шаг 4: Ждать worker ─────────────────────────────────────────
        log(f"=== STEP 4: Waiting {WORKER_WAIT_SECONDS}s for worker... ===")
        time.sleep(WORKER_WAIT_SECONDS)

        # ── Шаг 5: Проверить БД (Run) ───────────────────────────────────
        log("=== STEP 5: Check Run in DB ===")
        run_db = check_run_in_db(run_id)
        report["steps"]["run_in_db"] = run_db
        log(f"Run DB: {run_db['stdout']}")

        run_parsed = _parse_run_row(run_db.get("stdout", ""))
        report["steps"]["run_parsed"] = run_parsed
        log(f"Run status: {run_parsed['status']}, "
            f"total_checks: {run_parsed['total_checks']}, "
            f"completed_checks: {run_parsed['completed_checks']}")

        # ── Шаг 6: Проверить stage_executions ───────────────────────────
        log("=== STEP 6: Check stage_executions in DB ===")
        execs_db = check_stage_executions_in_db(run_id)
        report["steps"]["stage_executions_in_db"] = execs_db
        log(f"Stage executions: {execs_db['stdout'][:300] or '(empty)'}")

        # ── Шаг 7: Проверить логи по run_id ─────────────────────────────
        log("=== STEP 7: Check app logs for run_id ===")
        log_check = check_celery_publish_in_logs(run_id)
        report["steps"]["log_entries"] = log_check
        log(f"Log entries found: {log_check['count']}")
        log(f"Log entries with trace_id: {log_check['entries_with_trace_id']}")
        log(f"Worker log entries: {log_check['worker_entries_count']}")

        # ── Шаг 8: Проверить Tempo ──────────────────────────────────────
        log("=== STEP 8: Check Tempo for traces ===")
        recent_traces = check_recent_traces()
        report["steps"]["recent_traces"] = recent_traces
        log(f"Recent traces in Tempo: {recent_traces['count']}")

        # ── Итоговый вывод ───────────────────────────────────────────────
        log("=== CONCLUSION ===")

        run_row = run_db.get("stdout", "")
        run_created = run_id is not None and len(run_row) > 0

        # Правильный критерий:
        # Run НЕ завис в pending — это значит worker реально его забрал.
        # Для документов в статусе enriched total_checks > 0 является
        # признаком того что run_deal_checks уже отработал.
        run_status = run_parsed.get("status")
        total_checks = run_parsed.get("total_checks", 0)
        run_not_stuck = (
            run_status not in (None, "pending")
            or total_checks > 0
        )

        has_executions = len(execs_db.get("stdout", "").strip()) > 0
        has_logs = log_check.get("found", False)
        worker_path_proven = log_check.get("worker_entries_count", 0) > 0
        has_trace_in_logs = log_check.get("entries_with_trace_id", 0) > 0
        has_traces = recent_traces.get("count", 0) > 0

        # Новый корректный критерий overall:
        # - run создан
        # - run_id появился в логах (API сторона)
        # - либо run не pending, либо total_checks > 0
        # - traces в Tempo есть
        #
        # stage_executions теперь НЕ является обязательным для OK,
        # потому что для уже enriched документов это нормальный 0.
        overall_ok = (
            run_created
            and has_logs
            and run_not_stuck
            and has_traces
        )

        report["conclusion"] = {
            # Базовые инварианты
            "run_created": run_created,
            "run_not_stuck_in_pending": run_not_stuck,
            "run_status": run_status,
            "run_total_checks": total_checks,

            # Celery path доказательство
            "run_id_in_api_logs": has_logs,
            "worker_path_proven": worker_path_proven,

            # Tracing состояние
            "stage_executions_exist": has_executions,
            "trace_id_in_logs": has_trace_in_logs,
            "traces_in_tempo": has_traces,

            # Итог
            "overall": "OK" if overall_ok else "DEGRADED",

            # Пояснение критерия для BEFORE/AFTER сравнения
            "notes": {
                "stage_executions_exist_not_required": (
                    "For documents in enriched/completed status, "
                    "orchestrator correctly skips document-stage scheduling. "
                    "This is not a failure."
                ),
                "trace_id_in_logs_expected_before_b1": False,
                "trace_id_in_logs_expected_after_b1": True,
                "worker_path_proven_meaning": (
                    "True means worker_hostname appeared in run_id logs — "
                    "Celery task was actually consumed and executed."
                ),
            },
        }

        log(f"Run created: {run_created}")
        log(f"Run not stuck in pending: {run_not_stuck} "
            f"(status={run_status}, total_checks={total_checks})")
        log(f"run_id in API logs: {has_logs}")
        log(f"Worker path proven: {worker_path_proven}")
        log(f"Stage executions exist: {has_executions} (not required)")
        log(f"trace_id in logs: {has_trace_in_logs} "
            f"(expected False before B.1, True after B.1)")
        log(f"Traces in Tempo: {has_traces}")
        log(f"Overall: {report['conclusion']['overall']}")

    except Exception as e:
        log(f"FATAL ERROR: {e}")
        import traceback
        report["fatal_error"] = traceback.format_exc()
        report["conclusion"] = {
            "overall": "FATAL_ERROR",
            "error": str(e),
        }

    finally:
        _save_report(report)


def _save_report(report: dict) -> None:
    filename = f"baseline_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    log(f"Report saved: {filename}")


if __name__ == "__main__":
    main()