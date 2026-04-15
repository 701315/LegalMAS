# src/engine/checks/result_saver.py

"""
Сохранение результатов проверок в БД.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.logging import get_logger
from engine.checks.result_normalizer import (
    normalize_check_result,
    resolve_execution_status,
)

logger = get_logger(__name__)


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
    по ключу (run_id, document_id, check_id).

    Одна пара (run, doc, check) имеет одну запись,
    которая обновляется при retry / rerun / timeout recovery.
    """
    normalized = normalize_check_result(exec_result, check)
    execution_status, error_details = resolve_execution_status(exec_result)

    return await repo.upsert_single_check_result(
        run_id=run_id,
        document_id=doc.id,
        check_id=exec_result["check_id"],
        check_name=exec_result["check_name"],
        result=exec_result["result"],
        severity=exec_result["severity"],
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
        execution_status=execution_status,
        error_details=error_details,
    )


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
    """
    exec_result: dict[str, Any] = {
        "doc_id": str(getattr(doc, "id", None)),
        "check_id": check_id,
        "check_name": None,
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

    normalized = normalize_check_result(exec_result, check=None)

    return await repo.upsert_single_check_result(
        run_id=run_id,
        document_id=doc.id,
        check_id=check_id,
        check_name=exec_result["check_name"],
        result=exec_result["result"],
        severity=exec_result["severity"],
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
        execution_status="FAILED",
        error_details={
            "type": "check_not_applicable",
            "message": "check not found or not applicable for this document",
        },
    )

