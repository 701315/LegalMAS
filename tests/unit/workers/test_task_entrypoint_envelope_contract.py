"""
Gatekeeper test: все Celery task entrypoints на базе MASBaseTask
должны быть envelope-safe.

Инвариант:
- Каждый task entrypoint должен принимать orchestrator envelope kwargs
  (stage_execution_id, orchestration_strategy) — либо явно, либо через **kwargs.
- Это предотвращает TypeError при добавлении новых envelope fields в orchestrator.
"""
from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

# Импортируем все worker-модули, чтобы tasks зарегистрировались в Celery
import workers.build_legal_units_enrichment  # noqa: F401
import workers.build_primary_language_source  # noqa: F401
import workers.check_runner_worker  # noqa: F401
import workers.chunk_builder  # noqa: F401
import workers.classifier  # noqa: F401
import workers.convert_document_for_language_discovery  # noqa: F401
import workers.convert_worker  # noqa: F401
import workers.debug_dlq_task  # noqa: F401
import workers.detect_document_languages_native  # noqa: F401
import workers.detect_document_languages_ocr  # noqa: F401
import workers.export_pending  # noqa: F401
import workers.exporter  # noqa: F401
import workers.extract_worker  # noqa: F401
import workers.import_worker  # noqa: F401
import workers.language_discovery_orchestrator  # noqa: F401
import workers.outbox_dispatcher  # noqa: F401
import workers.pii_sanitizer  # noqa: F401
import workers.prepare_document_for_language_discovery  # noqa: F401
import workers.relations_worker  # noqa: F401
import workers.run_orchestrator  # noqa: F401
import workers.segment_classifier  # noqa: F401
import workers.structure_builder  # noqa: F401
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app


def _get_mas_base_tasks() -> list[tuple[str, MASBaseTask]]:
    """Собрать все зарегистрированные tasks на базе MASBaseTask."""
    result = []
    for name, task in celery_app.tasks.items():
        if isinstance(task, MASBaseTask):
            result.append((name, task))
    return result


def _is_envelope_safe(task: MASBaseTask) -> tuple[bool, str]:
    """
    Проверить, что entrypoint task-а безопасно принимает envelope kwargs.

    Считается envelope-safe если:
    - имеет **kwargs (VAR_KEYWORD parameter), ИЛИ
    - явно принимает stage_execution_id И orchestration_strategy.

    Возвращает (ok, reason).
    """
    try:
        sig = inspect.signature(task.run)
    except (ValueError, TypeError) as exc:
        return False, f"Cannot inspect signature: {exc}"

    params = sig.parameters

    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in params.values()
    )

    if has_var_keyword:
        return True, "has **kwargs"

    has_stage_execution_id = "stage_execution_id" in params
    has_orchestration_strategy = "orchestration_strategy" in params

    if has_stage_execution_id and has_orchestration_strategy:
        return True, "has explicit stage_execution_id and orchestration_strategy"

    missing = []
    if not has_stage_execution_id:
        missing.append("stage_execution_id")
    if not has_orchestration_strategy:
        missing.append("orchestration_strategy")

    return False, f"missing envelope params: {', '.join(missing)}"


class TestTaskEntrypointEnvelopeContract:
    """Все MASBaseTask entrypoints должны быть envelope-safe."""

    def test_all_tasks_are_discovered(self):
        """Убедиться, что хотя бы один MASBaseTask зарегистрирован."""
        tasks = _get_mas_base_tasks()
        assert len(tasks) > 0, (
            "No MASBaseTask tasks found — workers not imported or registration broken"
        )

    @pytest.mark.parametrize(
        "task_name,task",
        _get_mas_base_tasks(),
        ids=[name for name, _ in _get_mas_base_tasks()],
    )
    def test_task_is_envelope_safe(
        self,
        task_name: str,
        task: MASBaseTask,
    ) -> None:
        """
        Каждый task entrypoint должен принимать orchestrator envelope kwargs.

        Это предотвращает:
        TypeError: got an unexpected keyword argument 'stage_execution_id'

        Чтобы починить: добавьте в сигнатуру entrypoint:
            stage_execution_id: str | None = None,
            orchestration_strategy: str | None = None,
            **kwargs: Any,
        """
        ok, reason = _is_envelope_safe(task)
        assert ok, (
            f"Task '{task_name}' is NOT envelope-safe. {reason}.\n"
            f"Add to the entrypoint signature:\n"
            f"    stage_execution_id: str | None = None,\n"
            f"    orchestration_strategy: str | None = None,\n"
            f"    **kwargs: Any,\n"
        )


        