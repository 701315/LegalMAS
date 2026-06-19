# src/engine/checks/result_saver.py

"""
Сохранение результатов проверок в БД.

Spec v2:
- canonical display/review semantics формируются через result_semantics.py;
- user-facing explanation больше НЕ пишется в quality_flags;
- quality_flags остаётся техническим/диагностическим слоем;
- в CheckResult сохраняются отдельные canonical поля:
    * ui_mode
    * display_text
    * machine_reason_code
    * review_status
    * review_message
    * needs_manual_review
"""

from __future__ import annotations

import uuid
from typing import Any

from core.constants import CheckExecutionStatus
from core.logging import get_logger
from engine.checks.result_normalizer import (
    normalize_check_result,
    resolve_execution_status,
)
from engine.checks.result_semantics import build_canonical_result_semantics

logger = get_logger(__name__)


def _resolve_persisted_check_name(
    *,
    check_id: str,
    check_name: str | None,
) -> str:
    """
    Гарантирует, что в БД всегда уйдёт валидный check_name.

    Для непрофессионального программиста:
    - в таблице check_results поле check_name обязательное (NOT NULL);
    - иногда upstream-код не знает "красивое" имя проверки
      (например, в кейсе check_not_applicable);
    - в таком случае мы не имеем права писать NULL в БД;
    - поэтому используем безопасный fallback: сам check_id.

    Почему это правильно:
    - check_id всегда есть;
    - это стабильный идентификатор проверки;
    - это лучше, чем падение пайплайна из-за пустого имени.
    """
    cleaned_name = (check_name or "").strip()
    if cleaned_name:
        return cleaned_name
    return check_id


async def save_check_result(
    *,
    repo,
    run_id: uuid.UUID,
    doc,
    check,
    exec_result: dict,
    playbook_version_id: uuid.UUID | None = None,
) -> Any:
    """
    Сохранить результат одной проверки в check_results идемпотентно
    по ключу (run_id, document_id, segment_id, check_id).

    Одна storage-единица результата:
    - single-document: (run, doc, NULL-segment, check)
    - multi-document:  (run, doc, segment_id, check)

    ВАЖНО:
    - здесь мы не решаем result/execution_status — это делает:
        * normalize_check_result(...)
        * resolve_execution_status(...)
    - canonical display/review semantics для UI строятся здесь же
      через build_canonical_result_semantics(...), пока у нас есть:
        * check / ui_mode
        * exec_result
        * execution_status
        * structured_data
    - если на уровне БД произойдёт ошибка, repo.upsert_single_check_result
      поднимет исключение, и вызывающий код (Celery) решит:
        * retry / fail / alerting.
    """
    # Сохраняем doc_id заранее как обычное значение.
    # Это важно: в except-блоке нельзя лишний раз трогать ORM/snapshot-объект,
    # потому что после DB-ошибки это может вызвать вторичную async/ORM ошибку.
    doc_id = getattr(doc, "id", None)

    # Нормализуем «сырые» exec_result + check в единый словарь
    # для persistence-полей (value_text, evidence_ref, quality_flags, structured_data, provenance).
    normalized = normalize_check_result(exec_result, check)

    # Определяем execution_status и error_details на основе результата работы check.
    execution_status, error_details = resolve_execution_status(exec_result)

    # Spec v2: canonical display/review semantics.
    semantics = build_canonical_result_semantics(
        check=check,
        check_name=getattr(check, "name", None) or exec_result.get("check_name"),
        exec_result=exec_result,
        execution_status=execution_status,
        structured_data=normalized.get("structured_data"),
    )

    # Гарантируем валидное имя проверки для записи в БД.
    persisted_check_name = _resolve_persisted_check_name(
        check_id=exec_result["check_id"],
        check_name=exec_result.get("check_name"),
    )

    try:
        return await repo.upsert_single_check_result(
            run_id=run_id,
            document_id=doc_id,
            check_id=exec_result["check_id"],
            check_name=persisted_check_name,
            result=exec_result["result"],
            severity=exec_result["severity"],
            # Spec v2:
            # value_text остаётся secondary raw summary / legacy helper,
            # НЕ дублирует display_text.
            value_text=normalized["value_text"],
            evidence_ref=normalized["evidence_ref"],
            confidence=exec_result.get("confidence"),
            detector_used=normalized["detector_used"],
            quality_flags=normalized["quality_flags"],
            structured_data=normalized["structured_data"],
            conditional_check_triggered=normalized["conditional_check_triggered"],
            trigger_name=normalized["trigger_name"],
            origin=normalized["origin"],
            playbook_version_id=playbook_version_id,
            page=normalized["page"],
            clause_uid=normalized["clause_uid"],
            element_id=normalized["element_id"],
            bbox=normalized["bbox"],
            segment_id=normalized.get("segment_id"),
            segment_type=normalized.get("segment_type"),
            segment_title=normalized.get("segment_title"),
            segment_order=normalized.get("segment_order"),
            is_primary_segment=normalized.get("is_primary_segment"),
            chunk_id=normalized.get("chunk_id"),
            chunk_index=normalized.get("chunk_index"),
            context_trace=normalized.get("context_trace"),
            execution_status=execution_status,
            error_details=error_details,
            # ── Spec v2: canonical display semantics ──────────────────────────
            ui_mode=getattr(check, "ui_mode", None),
            display_text=semantics.display_text,
            machine_reason_code=semantics.machine_reason_code,
            review_status=semantics.review_status,
            review_message=semantics.review_message,
            needs_manual_review=semantics.needs_manual_review,
        )
    except Exception as e:
        logger.exception(
            "save_check_result: failed to upsert check result",
            extra={
                "run_id": str(run_id),
                "doc_id": str(doc_id) if doc_id is not None else None,
                "check_id": exec_result.get("check_id"),
                "execution_status": execution_status,
                "error": str(e),
            },
        )
        raise


async def save_not_applicable_result(
    *,
    repo,
    run_id: uuid.UUID,
    doc,
    check_id: str,
    playbook_version_id: uuid.UUID | None = None,
) -> Any:
    """
    Сохранить результат для check, который не применим к документу.

    ВАЖНО:
    - это НЕ техническая ошибка пайплайна;
    - система успешно определила, что check не подходит этому документу;
    - поэтому execution_status здесь должен быть SUCCESS,
      чтобы такой кейс не помечал весь Run как ошибочный.

    Доменная семантика пока сохраняется как:
    - result="unclear"
    - severity="unclear"

    Но Spec v2 поверх этого строит canonical review semantics:
    - review_status = "not_applicable"
    - review_message = "Проверка не применима ..."
    - display_text = None
    """
    doc_id = getattr(doc, "id", None)

    exec_result: dict[str, Any] = {
        "doc_id": str(doc_id) if doc_id is not None else None,
        "check_id": check_id,
        # Даже если красивого имени нет — сохраняем валидный fallback.
        "check_name": check_id,
        "result": "unclear",
        "severity": "unclear",
        "confidence": None,
        "detector_method": None,
        "reason": "check_not_applicable",
        "sources": [],
        "location": None,
        "raw": {
            "source": "check_runner",
            "error": "check_not_applicable_for_document",
        },
        "structured_data": None,
        "page": None,
        "clause_uid": None,
        "element_id": None,
        "bbox": None,
    }

    # Нормализуем как обычный exec_result.
    normalized = normalize_check_result(exec_result, check=None)

    # Для not_applicable execution считается SUCCESS:
    # проверка не "сломалась", а корректно определила неприменимость.
    execution_status = CheckExecutionStatus.SUCCESS.value

    semantics = build_canonical_result_semantics(
        check=None,
        check_name=check_id,
        exec_result=exec_result,
        execution_status=execution_status,
        structured_data=normalized.get("structured_data"),
    )

    persisted_check_name = _resolve_persisted_check_name(
        check_id=check_id,
        check_name=exec_result.get("check_name"),
    )

    try:
        return await repo.upsert_single_check_result(
            run_id=run_id,
            document_id=doc_id,
            check_id=check_id,
            check_name=persisted_check_name,
            result=exec_result["result"],
            severity=exec_result["severity"],
            # Spec v2: raw summary остаётся независимым от display_text.
            value_text=normalized["value_text"],
            evidence_ref=normalized["evidence_ref"],
            confidence=exec_result.get("confidence"),
            detector_used=normalized["detector_used"],
            quality_flags=normalized["quality_flags"],
            structured_data=normalized["structured_data"],
            conditional_check_triggered=normalized["conditional_check_triggered"],
            trigger_name=normalized["trigger_name"],
            origin=normalized["origin"],
            playbook_version_id=playbook_version_id,
            page=normalized["page"],
            clause_uid=normalized["clause_uid"],
            element_id=normalized["element_id"],
            bbox=normalized["bbox"],
            segment_id=normalized.get("segment_id"),
            segment_type=normalized.get("segment_type"),
            segment_title=normalized.get("segment_title"),
            segment_order=normalized.get("segment_order"),
            is_primary_segment=normalized.get("is_primary_segment"),
            chunk_id=normalized.get("chunk_id"),
            chunk_index=normalized.get("chunk_index"),
            context_trace=normalized.get("context_trace"),
            execution_status=execution_status,
            error_details={
                "type": "check_not_applicable",
                "message": "check not found or not applicable for this document",
            },
            # ── Spec v2: canonical display semantics ──────────────────────────
            ui_mode=None,
            display_text=semantics.display_text,
            machine_reason_code=semantics.machine_reason_code,
            review_status=semantics.review_status,
            review_message=semantics.review_message,
            needs_manual_review=semantics.needs_manual_review,
        )
    except Exception as e:
        logger.exception(
            "save_not_applicable_result: failed to upsert not-applicable check result",
            extra={
                "run_id": str(run_id),
                "doc_id": str(doc_id) if doc_id is not None else None,
                "check_id": check_id,
                "error": str(e),
            },
        )
        raise

    
