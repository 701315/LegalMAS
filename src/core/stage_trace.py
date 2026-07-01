# src/core/stage_trace.py

"""
Stage trace helpers — Explainability Schema v1.

Назначение:
- стандартизировать result_details для document_stage_executions;
- дать worker'ам простой API для формирования explainability payload;
- убрать дублирование envelope-полей (stage/status/duration) из worker'ов.

Контракт v1:

{
    "schema_version": 1,
    "stage": str,
    "status": str,               # succeeded | failed | skipped | partial
    "finished_at": str,          # ISO 8601 (UTC)
    "duration_ms": int,
    "strategy": str | None,
    "input_summary": dict,
    "output_summary": dict,
    "warnings": list,
    "artifact_refs": dict,
    "decision_details": dict | None,
}
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


STAGE_TRACE_SCHEMA_VERSION = 1


def build_stage_trace_fragment(
    *,
    strategy: str | None = None,
    input_summary: dict[str, Any] | None = None,
    output_summary: dict[str, Any] | None = None,
    warnings: list[Any] | None = None,
    artifact_refs: dict[str, Any] | None = None,
    decision_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Построить stage-specific fragment.

    Worker возвращает его в:
        retval["stage_execution_result_details"]
    """
    return {
        "strategy": strategy,
        "input_summary": input_summary or {},
        "output_summary": output_summary or {},
        "warnings": warnings or [],
        "artifact_refs": artifact_refs or {},
        "decision_details": decision_details,
    }


def enrich_trace_with_base_envelope(
    fragment: dict[str, Any] | None,
    *,
    stage: str,
    status: str,
    started_at: float | None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    Обогатить fragment системными полями.

    Вызывается из MASBaseTask.
    """
    import time

    now = datetime.now(UTC)
    finished_at_iso = now.isoformat()

    if started_at is not None:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
    else:
        duration_ms = 0

    base: dict[str, Any] = {
        "schema_version": STAGE_TRACE_SCHEMA_VERSION,
        "stage": stage,
        "status": status,
        "finished_at": finished_at_iso,
        "duration_ms": duration_ms,
    }

    if task_id is not None:
        base["task_id"] = task_id

    if fragment:
        merged = {**fragment, **base}
        # Явно гарантируем сохранность доменных ключей
        for key in (
            "strategy",
            "input_summary",
            "output_summary",
            "warnings",
            "artifact_refs",
            "decision_details",
        ):
            if key in fragment:
                merged[key] = fragment[key]
        return merged

    return {
        **base,
        "strategy": None,
        "input_summary": {},
        "output_summary": {},
        "warnings": [],
        "artifact_refs": {},
        "decision_details": None,
    }


    