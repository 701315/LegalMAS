# src/services/structure/_hierarchy_builder/_embedding_recovery.py

"""
Phase 13.4 — Embedding Recovery Engine.

Активирует RecoveryStrategyType.EMBEDDINGS для orphan nodes,
которые HierarchyStateMachine прикрепил как best_effort_root.

Архитектурные принципы:
- Bounded search: поиск parent ограничен CandidateWindow (не O(N²)).
- Non-destructive: если embedding similarity ниже threshold — оставляем
  FSM-решение (best_effort_root). Fallback сохраняется.
- Failure-isolated: любая ошибка encode/similarity → orphan остаётся
  best_effort_root, pipeline не падает, исключение логируется.
- Deterministic tie-break: TieBreakPolicy из _recovery.py.
- EmbeddingService переиспользует уже загруженную модель (multilingual-e5-small),
  не загружает новую модель.
- Batch encode: все тексты кодируются одним вызовом encode() для эффективности.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from core.config import settings
from core.logging import get_logger
from services.structure.models import MutableHierarchyNode
from services.structure._models._recovery import (
    CandidateWindow,
    RecoveryCandidate,
    RecoveryDecision,
    RecoveryStrategyType,
    TieBreakPolicy,
)

logger = get_logger(__name__)

_TIEBREAK_POLICY = TieBreakPolicy()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EmbeddingRecoveryResult:
    """Итог embedding recovery pass для одного сегмента документа."""

    recovered_count: int = 0
    skipped_count: int = 0      # orphans без подходящего кандидата выше threshold
    disabled_count: int = 0     # embedding отключён или модель недоступна
    error_count: int = 0        # исключения при encode или similarity
    decisions: list[RecoveryDecision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered_count": self.recovered_count,
            "skipped_count": self.skipped_count,
            "disabled_count": self.disabled_count,
            "error_count": self.error_count,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_best_effort_orphan(node: MutableHierarchyNode) -> bool:
    """True если FSM прикрепил node как best_effort_root."""
    return bool(node.diagnostics.get("recovered_via_best_effort", False))


def _get_node_text(node: MutableHierarchyNode) -> str:
    """
    Собирает текст для embedding из node.

    Используем title + первые 200 символов own_text для семантического контекста.
    Если own_text пустой — только title.
    """
    title = str(getattr(node, "title", "") or "").strip()
    own_text = str(getattr(node, "own_text", "") or "").strip()
    if own_text:
        return f"{title} {own_text[:200]}".strip()
    return title


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity между двумя L2-нормированными или произвольными векторами."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _build_candidate_pool(
    mutable_nodes: dict[str, MutableHierarchyNode],
    orphan_uid: str,
    orphan_level: int,
    orphan_page: int,
    window: CandidateWindow,
) -> list[MutableHierarchyNode]:
    """
    Собирает кандидатов на роль parent для orphan в пределах CandidateWindow.

    Кандидат подходит если:
    - не сам orphan;
    - не является best_effort_orphan (они сами без parent);
    - его level < orphan_level (может быть parent по иерархии);
    - page_distance и level_delta не превышают window limits.
    """
    candidates: list[MutableHierarchyNode] = []
    for uid, node in mutable_nodes.items():
        if uid == orphan_uid:
            continue
        if _is_best_effort_orphan(node):
            continue

        node_level = int(getattr(node, "level", 1) or 1)
        node_page = int(getattr(node, "start_page", 0) or 0)
        page_distance = abs(orphan_page - node_page)
        level_delta = orphan_level - node_level

        # Parent должен быть выше по иерархии (меньший номер уровня)
        if level_delta <= 0:
            continue

        if window.allows(page_distance=page_distance, level_delta=level_delta):
            candidates.append(node)

    return candidates


def _mark_embedding_recovered(
    node: MutableHierarchyNode,
    *,
    parent_uid: str,
    confidence: float,
) -> None:
    """Обновляет diagnostics node после успешного embedding recovery."""
    node.diagnostics["recovered_via_best_effort"] = False
    node.diagnostics["recovered_via_embedding"] = True
    node.diagnostics["embedding_recovery_parent_uid"] = parent_uid
    node.diagnostics["embedding_recovery_confidence"] = round(confidence, 4)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class EmbeddingRecoveryEngine:
    """
    Применяет embedding-based recovery к best_effort_root orphan nodes.

    Алгоритм:
    1. Собрать все best_effort_root nodes (orphans).
    2. Batch-encode все nodes одним вызовом encode().
    3. Для каждого orphan:
       a. Найти кандидатов в CandidateWindow (bounded, не O(N²)).
       b. Вычислить cosine similarity orphan vs каждый кандидат.
       c. Если max_similarity >= threshold → выбрать лучшего по TieBreakPolicy.
       d. Переприаттачить orphan как child к выбранному parent.
    4. Вернуть EmbeddingRecoveryResult с audit stats.

    Мутирует mutable_nodes in-place.
    """

    def __init__(
        self,
        *,
        threshold: float | None = None,
        window: CandidateWindow | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._threshold = (
            threshold
            if threshold is not None
            else float(getattr(settings, "RECOVERY_EMBEDDING_SIMILARITY_THRESHOLD", 0.72))
        )
        self._enabled = (
            enabled
            if enabled is not None
            else bool(getattr(settings, "RECOVERY_EMBEDDING_ENABLED", True))
        )
        self._window = window or CandidateWindow(
            max_page_distance=int(
                getattr(settings, "RECOVERY_EMBEDDING_MAX_PAGE_DISTANCE", 3)
            ),
            max_level_delta=int(
                getattr(settings, "RECOVERY_EMBEDDING_MAX_LEVEL_DELTA", 2)
            ),
        )

    def _get_embedding_service(self):
        """Lazy import — не загружаем модель если recovery отключён."""
        from services.embeddings.embedding_service import embedding_service
        return embedding_service

    def recover(
        self,
        mutable_nodes: dict[str, MutableHierarchyNode],
        *,
        document_id: str = "",
    ) -> EmbeddingRecoveryResult:
        """
        Основной entry point. Мутирует mutable_nodes in-place.

        Returns EmbeddingRecoveryResult с audit информацией.
        Никогда не бросает исключений — failure-isolated.
        """
        result = EmbeddingRecoveryResult()

        if not self._enabled:
            return result

        orphans = [
            node for node in mutable_nodes.values()
            if _is_best_effort_orphan(node)
        ]

        if not orphans:
            return result

        # Проверяем доступность embedding service
        try:
            emb_service = self._get_embedding_service()
            if not emb_service.is_enabled:
                result.disabled_count = len(orphans)
                logger.debug(
                    "STRUCTURE embedding_recovery_service_disabled",
                    extra={"document_id": document_id, "orphans": len(orphans)},
                )
                return result
        except Exception as exc:
            logger.warning(
                "STRUCTURE embedding_recovery_service_unavailable",
                extra={"document_id": document_id, "error": str(exc)},
            )
            result.error_count = len(orphans)
            return result

        # Batch encode всех nodes
        all_uids = list(mutable_nodes.keys())
        all_texts = [_get_node_text(mutable_nodes[uid]) for uid in all_uids]
        uid_to_idx = {uid: i for i, uid in enumerate(all_uids)}

        try:
            # Nodes иерархии кодируются как "passage" —
            # они являются документными фрагментами для поиска parent.
            all_embeddings: np.ndarray = emb_service.encode(all_texts, role="passage")
        except Exception as exc:
            logger.warning(
                "STRUCTURE embedding_recovery_encode_failed",
                extra={"document_id": document_id, "error": str(exc)},
            )
            result.error_count = len(orphans)
            return result

        # Per-orphan recovery
        for orphan in orphans:
            decision = self._recover_single(
                orphan=orphan,
                mutable_nodes=mutable_nodes,
                all_embeddings=all_embeddings,
                uid_to_idx=uid_to_idx,
                document_id=document_id,
            )
            result.decisions.append(decision)

            if decision.recovered and decision.parent_uid is not None:
                parent_node = mutable_nodes.get(decision.parent_uid)
                if parent_node is not None:
                    parent_node.children.append(orphan)
                    _mark_embedding_recovered(
                        orphan,
                        parent_uid=decision.parent_uid,
                        confidence=decision.recovery_confidence,
                    )
                    result.recovered_count += 1
                else:
                    # parent_uid не найден в mutable_nodes — не мутируем
                    result.skipped_count += 1
            else:
                result.skipped_count += 1

        if result.recovered_count > 0:
            logger.info(
                "STRUCTURE embedding_recovery_completed",
                extra={
                    "document_id": document_id,
                    "recovered": result.recovered_count,
                    "skipped": result.skipped_count,
                    "threshold": self._threshold,
                },
            )

        return result

    def _recover_single(
        self,
        *,
        orphan: MutableHierarchyNode,
        mutable_nodes: dict[str, MutableHierarchyNode],
        all_embeddings: np.ndarray,
        uid_to_idx: dict[str, int],
        document_id: str,
    ) -> RecoveryDecision:
        """
        Embedding recovery для одного orphan node.

        Returns RecoveryDecision. Никогда не бросает — failure-isolated.
        """
        orphan_uid = str(orphan.effective_uid or "")
        orphan_level = int(getattr(orphan, "level", 1) or 1)
        orphan_page = int(getattr(orphan, "start_page", 0) or 0)

        try:
            orphan_idx = uid_to_idx.get(orphan_uid)
            if orphan_idx is None:
                return self._unrecovered(orphan_uid)

            orphan_vec = all_embeddings[orphan_idx]

            candidate_nodes = _build_candidate_pool(
                mutable_nodes,
                orphan_uid,
                orphan_level,
                orphan_page,
                self._window,
            )

            if not candidate_nodes:
                return self._unrecovered(orphan_uid)

            scored: list[RecoveryCandidate] = []
            for cnode in candidate_nodes:
                cuid = str(cnode.effective_uid or "")
                cidx = uid_to_idx.get(cuid)
                if cidx is None:
                    continue

                sim = _cosine_similarity(orphan_vec, all_embeddings[cidx])
                if sim < self._threshold:
                    continue

                cpage = int(getattr(cnode, "start_page", 0) or 0)
                clevel = int(getattr(cnode, "level", 1) or 1)
                celem_i = int(cnode.diagnostics.get("source_elem_i") or 0)

                scored.append(RecoveryCandidate(
                    parent_uid=cuid,
                    strategy=RecoveryStrategyType.EMBEDDINGS,
                    confidence=round(min(1.0, max(0.0, sim)), 4),
                    page_distance=abs(orphan_page - cpage),
                    level_delta=orphan_level - clevel,
                    elem_i=celem_i,
                    reason=f"cosine_similarity={sim:.4f}",
                ))

            if not scored:
                return self._unrecovered(orphan_uid)

            # max confidence первично; среди равных — min tiebreak_key (page_distance, level_delta, elem_i, uid)
            best = min(
                scored,
                key=lambda c: (-c.confidence, *c.tiebreak_key(_TIEBREAK_POLICY)),
            )

            return RecoveryDecision(
                recovered=True,
                orphan_uid=orphan_uid,
                strategy_used=RecoveryStrategyType.EMBEDDINGS,
                chosen_parent=best,
                all_candidates=scored,
                window=self._window,
            )

        except Exception as exc:
            logger.warning(
                "STRUCTURE embedding_recovery_single_failed",
                extra={
                    "document_id": document_id,
                    "orphan_uid": orphan_uid,
                    "error": str(exc),
                },
            )
            return self._unrecovered(orphan_uid)

    @staticmethod
    def _unrecovered(orphan_uid: str) -> RecoveryDecision:
        """Возвращает RecoveryDecision для неудавшегося recovery."""
        return RecoveryDecision(
            recovered=False,
            orphan_uid=orphan_uid,
            strategy_used=RecoveryStrategyType.UNRECOVERED,
        )
    

