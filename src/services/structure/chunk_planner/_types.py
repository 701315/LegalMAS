# src/services/structure/chunk_planner/_types.py

"""
Phase 10 — Chunk Planner: data contracts.

Определяет immutable типы для планирования chunking strategy:
- ChunkingModeDecision — решение о режиме для всего файла
- SegmentChunkPlan     — plan для одного сегмента
- FileChunkPlan        — главный output Phase 10

Архитектурные принципы:
- типы immutable (frozen=True);
- Phase 10 НЕ собирает чанки — она планирует как их собирать;
- Phase 10 читает FileStructureAnalysisResult (Phase 9 output);
- plan является входом для chunk assembly layer (engine/content);
- все типы сериализуемы через to_dict() для audit/telemetry.

Зависимости:
- RecommendedChunkingMode из Phase 9 (_models/_analysis.py)
- НЕ зависит от engine/content
- НЕ зависит от ClauseTreeBuilder
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.structure._models._analysis import RecommendedChunkingMode


# ─── Chunking Token Parameters ────────────────────────────────────────────────

@dataclass(frozen=True)
class ChunkingTokenParams:
    """
    Параметры размера чанков для chunk assembly layer.

    Эти значения соответствуют доменному принципу:
    "один пункт = один chunk".

    target_tokens:
        Целевой размер clause chunk в токенах.
        Пункт меньше этого значения → один chunk, не режем.

    max_tokens:
        Максимальный размер. Пункт больше этого → сплит через
        split_text_to_sized_chunks().

    overlap_ratio:
        Доля overlap при сплите длинных пунктов.
        Увеличивается в HYBRID для стабильности анализа рисков.

    Defaults соответствуют текущему production поведению
    (target=300, max=800, overlap=0.15).
    """

    target_tokens: int = 300
    max_tokens: int = 800
    overlap_ratio: float = 0.15

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError(
                f"ChunkingTokenParams.target_tokens must be > 0, "
                f"got {self.target_tokens}"
            )
        if self.max_tokens < self.target_tokens:
            raise ValueError(
                f"ChunkingTokenParams.max_tokens ({self.max_tokens}) "
                f"must be >= target_tokens ({self.target_tokens})"
            )
        if not (0.0 <= self.overlap_ratio <= 1.0):
            raise ValueError(
                f"ChunkingTokenParams.overlap_ratio must be in [0.0, 1.0], "
                f"got {self.overlap_ratio}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_tokens": self.target_tokens,
            "max_tokens": self.max_tokens,
            "overlap_ratio": self.overlap_ratio,
        }


# ─── Default Token Params Per Mode ───────────────────────────────────────────

# Mode A: структура надёжна, используем production defaults.
TOKENS_MODE_A = ChunkingTokenParams(
    target_tokens=300,
    max_tokens=800,
    overlap_ratio=0.15,
)

# Mode B: структура частично повреждена, чуть консервативнее.
# Overlap увеличен для снижения риска потери контекста при анализе рисков.
TOKENS_MODE_B = ChunkingTokenParams(
    target_tokens=300,
    max_tokens=700,
    overlap_ratio=0.20,
)

# Mode C: layout fallback, splitting не используется как primary mechanism.
# Параметры минимальные, т.к. clause-based chunking ненадёжен.
TOKENS_MODE_C = ChunkingTokenParams(
    target_tokens=300,
    max_tokens=800,
    overlap_ratio=0.15,
)


# ─── ChunkingModeDecision ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChunkingModeDecision:
    """
    Решение Phase 10 о режиме chunking для файла/сегмента.

    mode:
        Выбранный режим из RecommendedChunkingMode.
        Приоритет 1: берём из StructureQualityReport.recommended_chunking_mode.
        Приоритет 2: fallback по метрикам если report недоступен.

    retrieval_safe:
        True → chunks пригодны для risk analysis.
        False → chunks могут содержать structural noise.

    reason:
        Human-readable объяснение почему выбран этот mode.
        Используется для audit и telemetry.

    token_params:
        Рекомендованные параметры размера чанков для assembly layer.

    allow_section_chunks:
        True → assembly layer может строить section-level chunks.
        False → только clause-level (leaf node) chunks.
        Выключается в HYBRID и LAYOUT_FALLBACK.

    allow_subclause_splitting:
        True → длинные пункты разбиваются через split_text_to_sized_chunks.
        False → каждый пункт = ровно один chunk, без сплита.

    drop_technical_fallback_nodes:
        True → technical fallback nodes НЕ попадают в risk analysis chunks.
        False → все nodes используются.
        Включается в HYBRID и LAYOUT_FALLBACK.

    prefer_layout_fallback:
        True → assembly layer должен использовать layout-based chunking.
        False → используем clause-based chunking.
        True только в LAYOUT_FALLBACK mode.

    warnings:
        Tuple строк с объяснениями решений.
        Используется для audit trail.
    """

    mode: RecommendedChunkingMode
    retrieval_safe: bool
    reason: str

    token_params: ChunkingTokenParams

    allow_section_chunks: bool
    allow_subclause_splitting: bool
    drop_technical_fallback_nodes: bool
    prefer_layout_fallback: bool

    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError(
                "ChunkingModeDecision.reason must not be empty"
            )

    @property
    def is_structure_first(self) -> bool:
        return self.mode == RecommendedChunkingMode.STRUCTURE_FIRST

    @property
    def is_hybrid(self) -> bool:
        return self.mode == RecommendedChunkingMode.HYBRID

    @property
    def is_layout_fallback(self) -> bool:
        return self.mode == RecommendedChunkingMode.LAYOUT_FALLBACK

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "retrieval_safe": self.retrieval_safe,
            "reason": self.reason,
            "token_params": self.token_params.to_dict(),
            "allow_section_chunks": self.allow_section_chunks,
            "allow_subclause_splitting": self.allow_subclause_splitting,
            "drop_technical_fallback_nodes": self.drop_technical_fallback_nodes,
            "prefer_layout_fallback": self.prefer_layout_fallback,
            "warnings": list(self.warnings),
        }


# ─── SegmentChunkPlan ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SegmentChunkPlan:
    """
    Plan chunking для одного логического сегмента документа.

    segment_id:
        ID сегмента из ClauseTree.segment_id.

    segment_type:
        Тип сегмента (contract / appendix / amendment / ...).
        Используется для аудита.

    mode:
        Mode для этого конкретного сегмента.
        Может отличаться от file-level mode если сегмент
        имеет индивидуально плохую структуру.

    token_params:
        Параметры размера чанков для этого сегмента.

    allow_section_chunks:
        Разрешены ли section chunks для этого сегмента.

    allow_subclause_splitting:
        Разрешён ли сплит длинных пунктов для этого сегмента.

    drop_technical_fallback_nodes:
        Нужно ли исключить technical fallback nodes из risk analysis
        для этого сегмента.

    retrieval_safe:
        True → chunks этого сегмента пригодны для risk analysis.

    fallback_fragment_ratio:
        Сохраняем из Phase 9 для downstream audit.

    warnings:
        Специфичные предупреждения для этого сегмента.
    """

    segment_id: str | None
    segment_type: str

    mode: RecommendedChunkingMode
    token_params: ChunkingTokenParams

    allow_section_chunks: bool
    allow_subclause_splitting: bool
    drop_technical_fallback_nodes: bool

    retrieval_safe: bool
    fallback_fragment_ratio: float

    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not (0.0 <= self.fallback_fragment_ratio <= 1.0):
            raise ValueError(
                f"SegmentChunkPlan.fallback_fragment_ratio must be in "
                f"[0.0, 1.0], got {self.fallback_fragment_ratio}"
            )

    @property
    def is_full_fallback(self) -> bool:
        """True если сегмент практически полностью состоит из fallback nodes."""
        return self.fallback_fragment_ratio >= 0.90

    @property
    def has_significant_fallback(self) -> bool:
        """True если сегмент имеет значительную долю fallback nodes."""
        return self.fallback_fragment_ratio >= 0.50

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_type": self.segment_type,
            "mode": self.mode.value,
            "token_params": self.token_params.to_dict(),
            "allow_section_chunks": self.allow_section_chunks,
            "allow_subclause_splitting": self.allow_subclause_splitting,
            "drop_technical_fallback_nodes": self.drop_technical_fallback_nodes,
            "retrieval_safe": self.retrieval_safe,
            "fallback_fragment_ratio": round(self.fallback_fragment_ratio, 4),
            "is_full_fallback": self.is_full_fallback,
            "has_significant_fallback": self.has_significant_fallback,
            "warnings": list(self.warnings),
        }


# ─── FileChunkPlan ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FileChunkPlan:
    """
    Главный output Phase 10 — план chunking для всего файла.

    document_id:
        ID документа из FileStructureResult.

    mode_decision:
        File-level chunking decision.
        Используется как default для сегментов без индивидуального plan.

    segment_plans:
        Per-segment plans. Tuple сохраняет порядок сегментов.

    schema_version:
        Версия контракта. Для audit и совместимости.

    Relationship с assembly layer:
        - FileChunkPlan передаётся в chunk assembly (engine/content)
        - assembly читает mode_decision и segment_plans
        - assembly НЕ меняет chunk IDs (они deterministic из effective_uid)
        - assembly использует token_params из SegmentChunkPlan
    """

    document_id: str
    mode_decision: ChunkingModeDecision
    segment_plans: tuple[SegmentChunkPlan, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError(
                "FileChunkPlan.document_id must not be empty"
            )

    @property
    def overall_retrieval_safe(self) -> bool:
        """
        True если ВСЕ сегменты retrieval-safe.
        Консервативная политика — совпадает с Phase 9.
        """
        if not self.segment_plans:
            return self.mode_decision.retrieval_safe
        return all(p.retrieval_safe for p in self.segment_plans)

    @property
    def any_layout_fallback(self) -> bool:
        """True если хотя бы один сегмент требует layout fallback."""
        return any(
            p.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
            for p in self.segment_plans
        )

    @property
    def all_segments_full_fallback(self) -> bool:
        """True если все сегменты являются полными technical fallback."""
        if not self.segment_plans:
            return False
        return all(p.is_full_fallback for p in self.segment_plans)

    def plan_for_segment(
        self, segment_id: str | None
    ) -> SegmentChunkPlan | None:
        """Найти plan для конкретного сегмента по ID."""
        for plan in self.segment_plans:
            if plan.segment_id == segment_id:
                return plan
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "overall_retrieval_safe": self.overall_retrieval_safe,
            "any_layout_fallback": self.any_layout_fallback,
            "all_segments_full_fallback": self.all_segments_full_fallback,
            "mode_decision": self.mode_decision.to_dict(),
            "segment_count": len(self.segment_plans),
            "segment_plans": [p.to_dict() for p in self.segment_plans],
        }


# ─── Public API ───────────────────────────────────────────────────────────────

__all__ = [
    "ChunkingModeDecision",
    "ChunkingTokenParams",
    "FileChunkPlan",
    "SegmentChunkPlan",
    "TOKENS_MODE_A",
    "TOKENS_MODE_B",
    "TOKENS_MODE_C",
]



