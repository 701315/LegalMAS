# src/services/structure/chunk_planner/_retrieval_readiness.py

"""
Phase 11 — Retrieval Readiness Evaluation.

Этот модуль отвечает за финальную оценку пригодности чанков
для downstream risk analysis.

Он НЕ меняет chunk assembly.
Он НЕ вызывает LLM.
Он НЕ читает БД.

Он работает только с уже построенными chunk dict'ами
и их metadata (включая planning metadata из Phase 10).

Основная цель:
- определить сколько чанков retrieval-safe;
- определить есть ли деградация;
- рекомендовать downstream поведение.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalReadinessReport:
    """
    Итоговый audit artifact для retrieval pipeline.

    document_id:
        ID документа.

    total_chunks:
        Общее количество чанков.

    retrieval_safe_chunks:
        Количество чанков с retrieval_safe=True.

    degraded_chunks:
        Количество чанков из деградированных сегментов.

    layout_fallback_chunks:
        Количество чанков из сегментов с prefer_layout_fallback=True.

    overall_retrieval_safe:
        True если ВСЕ чанки retrieval-safe.

    recommended_action:
        - "proceed" — всё хорошо.
        - "proceed_with_caution" — есть деградация.
        - "skip" — структура полностью ненадёжна.

    warnings:
        Дополнительные объяснения.
    """

    document_id: str
    total_chunks: int
    retrieval_safe_chunks: int
    degraded_chunks: int
    layout_fallback_chunks: int
    overall_retrieval_safe: bool
    recommended_action: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_chunks": self.total_chunks,
            "retrieval_safe_chunks": self.retrieval_safe_chunks,
            "degraded_chunks": self.degraded_chunks,
            "layout_fallback_chunks": self.layout_fallback_chunks,
            "overall_retrieval_safe": self.overall_retrieval_safe,
            "recommended_action": self.recommended_action,
            "warnings": list(self.warnings),
        }


def build_retrieval_readiness_report(
    *,
    document_id: str,
    chunks: list[dict[str, Any]],
) -> RetrievalReadinessReport:
    """
    Построить RetrievalReadinessReport на основе canonical chunks.

    Ожидается, что chunks уже enriched planning metadata:
      metadata["retrieval_safe"]
      metadata["prefer_layout_fallback"]
    """
    total = len(chunks)
    retrieval_safe = 0
    degraded = 0
    layout_fallback = 0

    for ch in chunks:
        meta = ch.get("metadata") or {}

        if meta.get("retrieval_safe", True):
            retrieval_safe += 1
        else:
            degraded += 1

        if meta.get("prefer_layout_fallback", False):
            layout_fallback += 1

    overall_safe = retrieval_safe == total if total > 0 else False

    warnings: list[str] = []

    if total == 0:
        warnings.append("no_chunks_available")
        recommended = "skip"
    elif overall_safe:
        recommended = "proceed"
    elif retrieval_safe > 0:
        recommended = "proceed_with_caution"
        warnings.append("some_chunks_not_retrieval_safe")
    else:
        recommended = "skip"
        warnings.append("all_chunks_not_retrieval_safe")

    if layout_fallback > 0:
        warnings.append("layout_fallback_preferred_segments_present")

    return RetrievalReadinessReport(
        document_id=document_id,
        total_chunks=total,
        retrieval_safe_chunks=retrieval_safe,
        degraded_chunks=degraded,
        layout_fallback_chunks=layout_fallback,
        overall_retrieval_safe=overall_safe,
        recommended_action=recommended,
        warnings=tuple(warnings),
    )



