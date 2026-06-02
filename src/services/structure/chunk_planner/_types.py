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
- все типы сериализуемы через to_dict() / десериализуемы через from_dict()
  для хранения в MinIO и загрузки в chunk_builder.

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

    target_tokens:
        Целевой размер clause chunk в токенах.
        Пункт меньше этого значения → один chunk, не режем.

    max_tokens:
        Максимальный размер. Пункт больше этого → сплит через
        split_text_to_sized_chunks().

    overlap_ratio:
        Доля overlap при сплите длинных пунктов.
        Увеличивается в HYBRID для стабильности анализа рисков.
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkingTokenParams":
        """
        Десериализовать из dict.

        Tolerant: использует production defaults для отсутствующих полей.
        Используется при загрузке chunk_plan.json из MinIO в chunk_builder.
        """
        return cls(
            target_tokens=int(data.get("target_tokens", 300)),
            max_tokens=int(data.get("max_tokens", 800)),
            overlap_ratio=float(data.get("overlap_ratio", 0.15)),
        )


# ─── Default Token Params Per Mode ───────────────────────────────────────────

TOKENS_MODE_A = ChunkingTokenParams(
    target_tokens=300,
    max_tokens=800,
    overlap_ratio=0.15,
)

TOKENS_MODE_B = ChunkingTokenParams(
    target_tokens=300,
    max_tokens=700,
    overlap_ratio=0.20,
)

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

    mode:              Выбранный режим из RecommendedChunkingMode.
    retrieval_safe:    True → chunks пригодны для risk analysis.
    reason:            Human-readable объяснение выбора режима.
    token_params:      Рекомендованные параметры размера чанков.
    allow_section_chunks:       True → можно строить section-level chunks.
    allow_subclause_splitting:  True → длинные пункты разбиваются.
    drop_technical_fallback_nodes: True → fallback nodes исключаются.
    prefer_layout_fallback:     True → использовать layout-based chunking.
    warnings:          Tuple строк для audit trail.
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkingModeDecision":
        """
        Десериализовать из dict.

        Strict для обязательных полей (mode, flags) —
        ошибка при отсутствии означает повреждённый артефакт.
        Tolerant для reason и warnings.
        """
        return cls(
            mode=RecommendedChunkingMode(data["mode"]),
            retrieval_safe=bool(data["retrieval_safe"]),
            reason=str(data.get("reason", "")),
            token_params=ChunkingTokenParams.from_dict(
                data.get("token_params") or {}
            ),
            allow_section_chunks=bool(data["allow_section_chunks"]),
            allow_subclause_splitting=bool(data["allow_subclause_splitting"]),
            drop_technical_fallback_nodes=bool(
                data["drop_technical_fallback_nodes"]
            ),
            prefer_layout_fallback=bool(data["prefer_layout_fallback"]),
            warnings=tuple(data.get("warnings") or []),
        )


# ─── SegmentChunkPlan ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SegmentChunkPlan:
    """
    Plan chunking для одного логического сегмента документа.

    segment_id:                  ID сегмента из ClauseTree.
    segment_type:                Тип сегмента (contract/appendix/...).
    mode:                        Mode для этого сегмента.
    token_params:                Параметры размера чанков.
    allow_section_chunks:        Разрешены ли section chunks.
    allow_subclause_splitting:   Разрешён ли сплит длинных пунктов.
    drop_technical_fallback_nodes: Исключить ли fallback nodes.
    retrieval_safe:              Пригодны ли chunks для risk analysis.
    fallback_fragment_ratio:     Доля fallback nodes из Phase 9.
    warnings:                    Предупреждения для этого сегмента.
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
        return self.fallback_fragment_ratio >= 0.90

    @property
    def has_significant_fallback(self) -> bool:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SegmentChunkPlan":
        """
        Десериализовать из dict.

        Примечание: is_full_fallback и has_significant_fallback —
        computed properties, не читаются из dict (вычисляются автоматически).
        """
        return cls(
            segment_id=data.get("segment_id"),
            segment_type=str(data.get("segment_type", "unknown")),
            mode=RecommendedChunkingMode(data["mode"]),
            token_params=ChunkingTokenParams.from_dict(
                data.get("token_params") or {}
            ),
            allow_section_chunks=bool(data["allow_section_chunks"]),
            allow_subclause_splitting=bool(data["allow_subclause_splitting"]),
            drop_technical_fallback_nodes=bool(
                data["drop_technical_fallback_nodes"]
            ),
            retrieval_safe=bool(data["retrieval_safe"]),
            fallback_fragment_ratio=float(
                data.get("fallback_fragment_ratio", 0.0)
            ),
            warnings=tuple(data.get("warnings") or []),
        )


# ─── FileChunkPlan ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FileChunkPlan:
    """
    Главный output Phase 10 — план chunking для всего файла.

    document_id:      ID документа из FileStructureResult.
    mode_decision:    File-level chunking decision.
    segment_plans:    Per-segment plans. Tuple сохраняет порядок.
    schema_version:   Версия контракта для audit и совместимости.

    Lifecycle:
    - Создаётся plan_chunking(analysis) в structure_builder.
    - Сохраняется как chunk_plan.json в MinIO.
    - Загружается chunk_builder через FileChunkPlan.from_dict().
    - Передаётся в SegmentChunkBuilderV2.build_for_version().
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
        if not self.segment_plans:
            return self.mode_decision.retrieval_safe
        return all(p.retrieval_safe for p in self.segment_plans)

    @property
    def any_layout_fallback(self) -> bool:
        return any(
            p.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
            for p in self.segment_plans
        )

    @property
    def all_segments_full_fallback(self) -> bool:
        if not self.segment_plans:
            return False
        return all(p.is_full_fallback for p in self.segment_plans)

    def plan_for_segment(
        self, segment_id: str | None
    ) -> SegmentChunkPlan | None:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileChunkPlan":
        """
        Десериализовать FileChunkPlan из dict.

        Используется chunk_builder для загрузки плана из MinIO.
        Strict для обязательных полей, tolerant для schema_version.

        Raises
        ------
        KeyError
            Если отсутствует обязательное поле (document_id, mode_decision).
        ValueError
            Если значение поля невалидно (неизвестный mode enum).
        """
        return cls(
            document_id=str(data["document_id"]),
            mode_decision=ChunkingModeDecision.from_dict(data["mode_decision"]),
            segment_plans=tuple(
                SegmentChunkPlan.from_dict(sp)
                for sp in (data.get("segment_plans") or [])
            ),
            schema_version=str(data.get("schema_version", "1.0")),
        )


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


