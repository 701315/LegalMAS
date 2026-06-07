# src/engine/content/segment_chunk_builder_v2.py

"""
SegmentChunkBuilderV2 — построение чанков по логическим сегментам (CHUNKS v2).

Простыми словами для непрофессионального программиста:

- Вход:
  * document_version_id (конкретная версия документа),
  * session (подключение к БД),
  * настройки chunking (target_tokens, max_tokens, overlap_ratio).

- Что делает:
  1) Читает из БД:
     - DocumentVersion (layout_primary_sanitized_ref, file_graph_ref);
     - все DocumentSegment для этой версии.
  2) Для каждого сегмента:
     - грузит segment_clause_tree_ref и общий layout;
     - строит leaf‑чанки по дереву ТОЛЬКО этого сегмента;
     - нормализует текст, добавляет метаданные (segment_id, segment_type, и т.п.);
     - строит subclause‑чанки;
     - собирает snapshot чанков сегмента.
  3) Строит file-level манифест чанков:
     - перечисление сегментов и их будущих segment_chunks_ref;
     - aggregate‑статистика по чанкам;
     - aggregate‑статистика покрытия чанкинга.

Важно:
- Этот builder НЕ пишет в MinIO и НЕ обновляет БД.
- Сохранение segment_chunks_ref и chunks_manifest_v2_ref делает worker.
- Этот builder НЕ использует legacy file-level refs старого chunking/structure контракта.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.models.document import DocumentSegment
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.chunk_canonicalization import (
    add_position_ratio,
    add_summary,
    build_sized_chunks_from_leaf,
    ensure_clause_metadata,
    extract_total_pages,
    normalize_clause_chunk_text,
    propagate_language_filter,
)
from engine.content.clause_tree_builder import ClauseTreeBuilder
from services.structure._models._analysis import RecommendedChunkingMode
from services.structure.chunk_planner import FileChunkPlan
from services.structure.legal_unit_builder import LegalUnitBuilder
from services.structure.legal_unit_models import LegalUnitsSnapshot
from services.structure.semantic_enrichment._types import LegalUnitsEnrichmentResult
from storage.artifact_store import ArtifactStore
from engine.content.layout_fallback_chunker import build_layout_fallback_chunks
from core.config import settings as _app_settings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.telemetry._collector import TelemetryCollector

from services.structure.legal_unit_retrieval import (
    build_retrieval_units_from_legal_units,
)

logger = get_logger(__name__)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _is_technical_fallback_node(node: dict[str, Any]) -> bool:
    """
    Определить technical fallback node по tree-level сигналам.

    ВАЖНО:
    - НЕ используем best-effort recovery как признак technical fallback;
    - НЕ выкидываем recovered but valid clauses;
    - опираемся на те же сигналы, что Phase 9 использует
      для fallback fragment detection.
    """
    if not isinstance(node, dict):
        return False

    title = _normalize_text(node.get("title")).lower()
    node_origin = _normalize_text(node.get("node_origin")).lower()
    content_mode = _normalize_text(node.get("content_mode")).lower()
    fallback_reason = _normalize_text(node.get("fallback_reason")).lower()
    citability_hint = _normalize_text(node.get("citability_hint")).lower()

    diagnostics = node.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    diagnostics_fallback_reason = _normalize_text(
        diagnostics.get("fallback_reason")
    ).lower()
    diagnostics_source_mode = _normalize_text(
        diagnostics.get("source_mode")
    ).lower()
    diagnostics_degraded_chunk = bool(
        diagnostics.get("degraded_chunk", False)
    )

    return any(
        (
            title.startswith("[technical fallback]"),
            node_origin == "technical_fallback",
            content_mode == "technical_fragment",
            fallback_reason == "technical_fallback",
            diagnostics_fallback_reason == "technical_fallback",
            diagnostics_source_mode == "technical_fallback",
            diagnostics_degraded_chunk,
            citability_hint == "technical",
        )
    )


def _filter_technical_fallback_tree(
    tree: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """
    Удалить technical fallback nodes из clause tree dict.

    Поведение:
    - fallback node удаляется;
    - его НЕ-fallback потомки поднимаются вверх (promote children),
      чтобы не потерять полезные узлы если fallback был только оболочкой;
    - остальные поля tree сохраняются как есть.

    Возвращает:
    - filtered_tree
    - removed_nodes_count
    """
    if not isinstance(tree, dict):
        return tree, 0

    root_nodes = tree.get("root") or []
    if not isinstance(root_nodes, list):
        return tree, 0

    removed_nodes_count = 0

    def _filter_node(node: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal removed_nodes_count

        if not isinstance(node, dict):
            return []

        children = node.get("children") or []
        filtered_children: list[dict[str, Any]] = []

        for child in children:
            if isinstance(child, dict):
                filtered_children.extend(_filter_node(child))

        if _is_technical_fallback_node(node):
            removed_nodes_count += 1
            return filtered_children

        cloned = dict(node)
        cloned["children"] = filtered_children
        return [cloned]

    filtered_root: list[dict[str, Any]] = []
    for root_node in root_nodes:
        if isinstance(root_node, dict):
            filtered_root.extend(_filter_node(root_node))

    filtered_tree = dict(tree)
    filtered_tree["root"] = filtered_root

    structure_diagnostics = dict(filtered_tree.get("structure_diagnostics") or {})
    structure_diagnostics["technical_fallback_nodes_filtered"] = removed_nodes_count
    filtered_tree["structure_diagnostics"] = structure_diagnostics

    return filtered_tree, removed_nodes_count


# МЕСТО: добавить после функции _filter_technical_fallback_tree()
# (перед _build_segment_planning_payload)

def _is_tree_technical_fallback_only(clause_tree: dict[str, Any]) -> bool:
    """
    Определить что всё дерево состоит исключительно из technical fallback nodes.

    Используется для P3b Honest Degraded Contract: когда chunk_plan absent
    и дерево полностью деградировано, chunks должны быть маркированы как
    technical_fragment, а не clause.

    Три независимых сигнала — достаточно любого одного:

    1. structure_diagnostics.technical_fallback_only == True
       Явный флаг из _degraded_fallback.py.

    2. structure_diagnostics.technical_fallback_contract.fallback_nodes_are_semantic == False
       Explicit contract из _degraded_fallback.py.

    3. Все non-empty root nodes идентифицированы как technical fallback
       по _is_technical_fallback_node().

    Universal: не зависит от языка, типа документа или контента.
    Работает для любого юридического документа.
    """
    if not isinstance(clause_tree, dict):
        return False

    diagnostics = clause_tree.get("structure_diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    # Сигнал 1: явный флаг из degraded_fallback
    if diagnostics.get("technical_fallback_only") is True:
        return True

    # Сигнал 2: explicit contract
    contract = diagnostics.get("technical_fallback_contract") or {}
    if (
        isinstance(contract, dict)
        and contract.get("fallback_nodes_are_semantic") is False
    ):
        return True

    # Сигнал 3: все root nodes — technical fallback
    root = clause_tree.get("root") or []
    if not isinstance(root, list) or not root:
        return False

    valid_root_nodes = [n for n in root if isinstance(n, dict)]
    if valid_root_nodes and all(
        _is_technical_fallback_node(n) for n in valid_root_nodes
    ):
        return True

    return False


def _remark_as_technical_fragments(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Перемаркировать chunks из technical fallback дерева.

    Изменяет только semantic kind markers в metadata:
    - chunk_kind: "clause" → "technical_fragment"
    - retrieval_safe: False  (downstream не использует для risk analysis)
    - is_technical_fallback: True  (явный флаг для фильтрации)
    - chunking_mode: "technical_fallback"  (traceability)

    Сохраняет без изменений: text, id, segment metadata,
    page info, element_ids, position_ratio.
    Все навигационные данные остаются — только semantic kind меняется.

    Universal: не зависит от языка/типа документа.
    """
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        meta = dict(chunk.get("metadata") or {})
        meta["chunk_kind"] = "technical_fragment"
        meta["retrieval_safe"] = False
        meta["is_technical_fallback"] = True
        meta["chunking_mode"] = "technical_fallback"
        remarked = dict(chunk)
        remarked["metadata"] = meta
        out.append(remarked)
    return out


def _build_segment_planning_payload(
    *,
    segment_plan: Any | None,
    filtered_technical_fallback_nodes: int,
    effective_params: dict[str, Any],
) -> dict[str, Any]:
    """
    Построить planning metadata для segment snapshot.
    """
    if segment_plan is None:
        return {
            "applied": False,
            "mode": None,
            "retrieval_safe": None,
            "allow_section_chunks": None,
            "allow_subclause_splitting": None,
            "drop_technical_fallback_nodes": None,
            "prefer_layout_fallback": None,
            "filtered_technical_fallback_nodes": filtered_technical_fallback_nodes,
            "token_params": effective_params,
            "warnings": [],
        }

    prefer_layout_fallback = (
        segment_plan.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
    )

    return {
        "applied": True,
        "mode": segment_plan.mode.value,
        "retrieval_safe": segment_plan.retrieval_safe,
        "allow_section_chunks": segment_plan.allow_section_chunks,
        "allow_subclause_splitting": segment_plan.allow_subclause_splitting,
        "drop_technical_fallback_nodes": segment_plan.drop_technical_fallback_nodes,
        "prefer_layout_fallback": prefer_layout_fallback,
        "fallback_fragment_ratio": round(
            float(segment_plan.fallback_fragment_ratio), 4
        ),
        "filtered_technical_fallback_nodes": filtered_technical_fallback_nodes,
        "token_params": effective_params,
        "warnings": list(segment_plan.warnings),
    }


def _build_file_planning_payload(
    *,
    chunk_plan: FileChunkPlan | None,
    segment_snapshots: list["SegmentChunkSnapshotV2"],
) -> dict[str, Any]:
    """
    Построить planning metadata для file manifest.
    """
    if chunk_plan is None:
        return {
            "applied": False,
            "mode": None,
            "retrieval_safe": None,
            "allow_section_chunks": None,
            "allow_subclause_splitting": None,
            "drop_technical_fallback_nodes": None,
            "prefer_layout_fallback": None,
            "warnings": [],
            "segment_modes": {
                snap.segment_id: (snap.planning or {}).get("mode")
                for snap in segment_snapshots
            },
        }

    decision = chunk_plan.mode_decision

    return {
        "applied": True,
        "mode": decision.mode.value,
        "retrieval_safe": decision.retrieval_safe,
        "allow_section_chunks": decision.allow_section_chunks,
        "allow_subclause_splitting": decision.allow_subclause_splitting,
        "drop_technical_fallback_nodes": decision.drop_technical_fallback_nodes,
        "prefer_layout_fallback": decision.prefer_layout_fallback,
        "token_params": decision.token_params.to_dict(),
        "warnings": list(decision.warnings),
        "segment_modes": {
            snap.segment_id: (snap.planning or {}).get("mode")
            for snap in segment_snapshots
        },
    }


@dataclass
class SegmentChunkSnapshotV2:
    """
    Snapshot чанков одного логического сегмента.

    Для непрофессионального программиста:
    - Один physical file может содержать несколько logical segments.
    - Для каждого сегмента строится отдельный snapshot.
    - Это позволяет не смешивать чанки договора и приложения в одном JSON.

    Этап 3:
    - Мы дополнительно сохраняем coverage‑метрики по leaf-узлам.
    - Это нужно, чтобы downstream видел не только "сколько чанков получилось",
      но и "сколько leaf-узлов потерялось по дороге".

    P8.8d — Retrieval Truth Migration:
    - Помимо legacy retrieval substrate (`subclause`) snapshot теперь может
      содержать новый retrieval level `legal_unit`.
    - `legal_unit` строится из exact legal units и является новым source of truth
      для retrieval/checks.
    - В отличие от blind sized split:
        * границы совпадают с legal units,
        * definitions materialized как отдельные retrieval items,
        * context добавляется через parent-prefix, а не через sibling spill.
    - `subclause` пока ещё материализуется как технический артефакт CHUNKS,
      но больше не считается retrieval truth после hard switch.
    """

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    segment_id: str
    segment_type: str
    segment_title: str | None
    segment_order: int
    is_primary_segment: bool
    segment_page_start: int
    segment_page_end: int
    layout_ref: str
    file_graph_ref: str
    segment_clause_tree_ref: str
    params: dict[str, Any]
    section_chunks: list[dict[str, Any]]
    clause_chunks: list[dict[str, Any]]
    subclause_chunks: list[dict[str, Any]]

    # P8.8d:
    # Новый retrieval-visible слой поверх exact legal units.
    # Каждый item уже приведён к canonical chunk dict contract:
    # {"id": ..., "text": ..., "metadata": {...}}
    legal_unit_chunks: list[dict[str, Any]] = field(default_factory=list)

    degraded: bool = False
    degradation_reason: str | None = None

    # Этап 3: coverage‑метрики сегмента.
    total_leaf_nodes: int | None = None
    leaf_nodes_without_chunks: int | None = None
    leaf_nodes_without_element_ids: int | None = None
    leaf_nodes_empty_after_filtering: int | None = None
    chunking_incomplete: bool = False

    # ── Этап 4: новые счётчики из ClauseTreeBuilder ───────────────────────────
    # heading_only_leaf_nodes: leaf узлы которые содержали только heading
    # без body — правильно пропускаются, не создают шумных чанков.
    heading_only_leaf_nodes: int = 0
    # best_effort_leaf_nodes: leaf узлы прикреплённые через best-effort recovery.
    best_effort_leaf_nodes: int = 0

    # ── Этап 5: legal units snapshot (опциональный dual-write) ───────────────
    # None если legal unit builder был отключён или упал с ошибкой.
    # Это НЕ ломает основной chunk pipeline — всегда опциональный.
    legal_units_snapshot: LegalUnitsSnapshot | None = None

    # ── Phase 12: semantic enrichment sidecar (опциональный) ─────────────────
    # None если LLM недоступна, не сконфигурирована или упала с ошибкой.
    # Это НЕ ломает основной chunk pipeline — всегда опциональный.
    # Сохраняется worker-ом в MinIO как legal_units_enrichment_v1.json.
    # Ссылка пишется в DocumentSegment.segment_meta["legal_units_enrichment_ref"].
    legal_units_enrichment_result: LegalUnitsEnrichmentResult | None = None

    # ── Phase 10: planning metadata ─────────────────────────────────────────
    planning: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать segment snapshot в storage contract CHUNKS v2.

        P8.8d:
        - В payload `chunks` теперь добавляется новый level `legal_unit`.
        - Reader V2 читает levels по ключам из `chunks`, поэтому новый уровень
          становится доступен retrieval/runtime без отдельного reader-specific кода.
        """
        return {
            "schema_version": 2,
            "scope": "segment",
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "segment": {
                "segment_id": self.segment_id,
                "segment_type": self.segment_type,
                "segment_title": self.segment_title,
                "segment_order": self.segment_order,
                "is_primary_segment": self.is_primary_segment,
                "page_start": self.segment_page_start,
                "page_end": self.segment_page_end,
            },
            "built_at": datetime.now(tz=UTC).isoformat(),
            "source": {
                "layout_ref": self.layout_ref,
                "file_graph_ref": self.file_graph_ref,
                "segment_clause_tree_ref": self.segment_clause_tree_ref,
            },
            "params": self.params,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "coverage": {
                "total_leaf_nodes": self.total_leaf_nodes,
                "leaf_nodes_without_chunks": self.leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": self.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": self.leaf_nodes_empty_after_filtering,
                "chunking_incomplete": self.chunking_incomplete,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": self.heading_only_leaf_nodes,
                "best_effort_leaf_nodes": self.best_effort_leaf_nodes,
            },
            "chunks": {
                "section": self.section_chunks,
                "clause": self.clause_chunks,
                "subclause": self.subclause_chunks,
                "legal_unit": self.legal_unit_chunks,
            },
            "planning": (
                dict(self.planning)
                if isinstance(self.planning, dict)
                else None
            ),
            "semantic_enrichment": (
                {
                    "applied": True,
                    "status_counts": self.legal_units_enrichment_result.status_counts,
                    "policy_version": self.legal_units_enrichment_result.policy_version,
                    "llm_model": self.legal_units_enrichment_result.llm_model,
                }
                if self.legal_units_enrichment_result is not None
                else {"applied": False}
            ),
        }


@dataclass
class FileChunkManifestSegmentV2:
    """
    Один элемент file-level manifest: описание сегмента и его чанков.

    P8.8d:
    - Добавлен `legal_unit_count`, чтобы manifest отражал новый retrieval corpus
      поверх exact legal units.
    """

    segment_id: str
    segment_type: str
    segment_title: str | None
    segment_order: int
    is_primary: bool
    page_start: int
    page_end: int
    segment_clause_tree_ref: str
    segment_chunks_ref: str | None
    section_count: int
    clause_count: int
    subclause_count: int
    legal_unit_count: int = 0
    planning: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileChunkManifestV2:
    """
    File-level манифест чанков для всей версии документа.

    Для непрофессионального программиста:
    - Это один JSON на весь файл.
    - Он не хранит весь текст чанков.
    - Он говорит:
      * какие сегменты есть,
      * какой из них primary,
      * где лежат чанки каждого сегмента,
      * сколько там чанков,
      * и есть ли проблемы покрытия чанкинга.

    P8.8d:
    - Манифест теперь считает также `legal_unit_count`.
    - Это позволяет наблюдать migration retrieval corpus от blind sized split
      к exact legal units на уровне telemetry/debug/audit.
    """

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    layout_ref: str
    file_graph_ref: str
    primary_segment_id: str
    segments: list[FileChunkManifestSegmentV2]
    degraded: bool = False
    degradation_reason: str | None = None

    # Этап 3: aggregate coverage‑метрики по всему файлу.
    total_leaf_nodes: int | None = None
    leaf_nodes_without_chunks: int | None = None
    leaf_nodes_without_element_ids: int | None = None
    leaf_nodes_empty_after_filtering: int | None = None
    chunking_incomplete: bool = False

    # ── Этап 4: агрегированные счётчики по всем сегментам ────────────────────
    heading_only_leaf_nodes: int = 0
    best_effort_leaf_nodes: int = 0
    planning: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "scope": "file",
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "built_at": datetime.now(tz=UTC).isoformat(),
            "source": {
                "layout_ref": self.layout_ref,
                "file_graph_ref": self.file_graph_ref,
            },
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "planning": (
                dict(self.planning)
                if isinstance(self.planning, dict)
                else None
            ),
            "segments": [s.to_dict() for s in self.segments],
            "totals": {
                "segment_count": len(self.segments),
                "section_count": sum(s.section_count for s in self.segments),
                "clause_count": sum(s.clause_count for s in self.segments),
                "subclause_count": sum(s.subclause_count for s in self.segments),
                "legal_unit_count": sum(s.legal_unit_count for s in self.segments),
                "total_leaf_nodes": self.total_leaf_nodes,
                "leaf_nodes_without_chunks": self.leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": self.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": self.leaf_nodes_empty_after_filtering,
                "chunking_incomplete": self.chunking_incomplete,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": self.heading_only_leaf_nodes,
                "best_effort_leaf_nodes": self.best_effort_leaf_nodes,
            },
        }

class SegmentChunkBuilderV2:
    """
    Основной сервис CHUNKS v2 (segment-aware).

    Важно:
    - Работает только через:
      * layout_primary_sanitized_ref,
      * file_graph_ref,
      * DocumentSegment.segment_clause_tree_ref.
    - Не использует legacy:
      * DocumentVersion.clause_tree_ref
      * legacy file-level chunk snapshot (schema v1)
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def build_for_version(
        self,
        *,
        session: AsyncSession,
        document_version_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
        chunk_plan: FileChunkPlan | None = None,
        collector: "TelemetryCollector | None" = None,
    ) -> tuple[FileChunkManifestV2, list[SegmentChunkSnapshotV2]]:
        
        logger.info(
            "SegmentChunkBuilderV2: build_for_version start",
            extra={
                "document_version_id": str(document_version_id),
                "target_tokens": target_tokens,
                "max_tokens": max_tokens,
                "overlap_ratio": overlap_ratio,
                "chunk_plan_applied": chunk_plan is not None,
                "chunk_plan_mode": (
                    chunk_plan.mode_decision.mode.value
                    if chunk_plan is not None
                    else None
                ),
            },
        )

        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)
        seg_repo = DocumentSegmentRepository(session)

        version = await ver_repo.get_by_id(document_version_id)
        if not version:
            raise PermanentError(f"DocumentVersion {document_version_id} not found")

        doc = await doc_repo.get_by_id(version.document_id)
        if not doc:
            raise PermanentError(
                f"Document {version.document_id} not found for version {document_version_id}"
            )

        layout_ref = getattr(version, "layout_primary_sanitized_ref", None)
        if not layout_ref:
            raise PermanentError(
                f"No layout_primary_sanitized_ref for version {document_version_id}. "
                f"CHUNKS v2 requires sanitized primary layout."
            )

        file_graph_ref = getattr(version, "file_graph_ref", None)
        if not file_graph_ref:
            raise PermanentError(
                f"No file_graph_ref for version {document_version_id}. "
                f"STRUCTURE v2 must be completed before CHUNKS v2."
            )

        logger.info(
            "SegmentChunkBuilderV2: version source refs resolved",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "layout_ref": layout_ref,
                "file_graph_ref": file_graph_ref,
            },
        )

        segments = await seg_repo.list_by_version(version.id)
        if not segments:
            raise PermanentError(
                f"No DocumentSegment rows found for version {document_version_id}. "
                f"CHUNKS v2 requires materialized segments."
            )

        primary_segments = [s for s in segments if bool(getattr(s, "is_primary", False))]
        if len(primary_segments) != 1:
            raise PermanentError(
                f"Invalid DocumentSegment state for version {document_version_id}: "
                f"expected exactly 1 primary segment, got {len(primary_segments)}"
            )

        logger.info(
            "SegmentChunkBuilderV2: segments loaded",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "segments_count": len(segments),
                "primary_segment_id": primary_segments[0].segment_id,
                "segments": [
                    {
                        "segment_id": s.segment_id,
                        "segment_type": s.segment_type,
                        "segment_order": s.segment_order,
                        "is_primary": bool(s.is_primary),
                    }
                    for s in segments
                ],
            },
        )


        file_graph = self.store.get_json(file_graph_ref)
        if not isinstance(file_graph, dict):
            raise PermanentError(
                f"FileGraph artifact {file_graph_ref} is invalid for version "
                f"{document_version_id}: expected dict"
            )

        file_graph_document_id = str(file_graph.get("document_id") or "")
        if file_graph_document_id != str(doc.id):
            raise PermanentError(
                f"FileGraph document_id mismatch for version {document_version_id}: "
                f"expected={str(doc.id)!r}, actual={file_graph_document_id!r}"
            )

        file_graph_document_version_id = str(file_graph.get("document_version_id") or "")
        if file_graph_document_version_id and file_graph_document_version_id != str(version.id):
            raise PermanentError(
                f"FileGraph document_version_id mismatch for version {document_version_id}: "
                f"expected={str(version.id)!r}, actual={file_graph_document_version_id!r}"
            )

        file_graph_segments = file_graph.get("segments") or []
        if not isinstance(file_graph_segments, list):
            raise PermanentError(
                f"FileGraph artifact {file_graph_ref} has invalid segments: expected list"
            )

        file_graph_segments_by_id: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(file_graph_segments):
            if not isinstance(item, dict):
                raise PermanentError(
                    f"FileGraph artifact {file_graph_ref} has invalid segment at index {index}: "
                    f"expected dict"
                )

            seg_id = str(item.get("segment_id") or "")
            if not seg_id:
                raise PermanentError(
                    f"FileGraph artifact {file_graph_ref} has empty segment_id at index {index}"
                )

            if seg_id in file_graph_segments_by_id:
                raise PermanentError(
                    f"FileGraph artifact {file_graph_ref} contains duplicate segment_id {seg_id!r}"
                )

            file_graph_segments_by_id[seg_id] = item

        db_segment_ids = {str(s.segment_id) for s in segments}
        file_graph_segment_ids = set(file_graph_segments_by_id.keys())

        if file_graph_segment_ids != db_segment_ids:
            raise PermanentError(
                f"FileGraph/DocumentSegment mismatch for version {document_version_id}: "
                f"file_graph_segment_ids={sorted(file_graph_segment_ids)}, "
                f"db_segment_ids={sorted(db_segment_ids)}"
            )

        file_graph_primary_segment_id = str(file_graph.get("primary_segment_id") or "")
        db_primary_segment_id = str(primary_segments[0].segment_id)

        if file_graph_primary_segment_id and file_graph_primary_segment_id != db_primary_segment_id:
            raise PermanentError(
                f"FileGraph primary_segment_id mismatch for version {document_version_id}: "
                f"expected={db_primary_segment_id!r}, actual={file_graph_primary_segment_id!r}"
            )

        logger.info(
            "SegmentChunkBuilderV2: file_graph validated",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "file_graph_ref": file_graph_ref,
                "segments_count": len(file_graph_segment_ids),
                "primary_segment_id": db_primary_segment_id,
            },
        )


        layout = self.store.get_json(layout_ref)
        if not isinstance(layout, dict):
            raise PermanentError(
                f"Layout artifact {layout_ref} is invalid for version {document_version_id}: expected dict"
            )

        layout_meta = layout.get("metadata") or {}
        total_pages = extract_total_pages(layout_meta)

        logger.debug(
            "SegmentChunkBuilderV2: layout loaded",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "layout_has_metadata": isinstance(layout_meta, dict),
                "total_pages": total_pages,
            },
        )

        params = {
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
        }

        segment_snapshots: list[SegmentChunkSnapshotV2] = []

        for segment in sorted(segments, key=lambda s: int(s.segment_order)):
            graph_segment = file_graph_segments_by_id.get(str(segment.segment_id))
            if graph_segment is None:
                raise PermanentError(
                    f"Segment {segment.segment_id} is missing in validated FileGraph "
                    f"for version {document_version_id}"
                )

            snapshot = await self._build_single_segment_snapshot(
                document_id=doc.id,
                document_version_id=version.id,
                segment=segment,
                layout=layout,
                layout_meta=layout_meta if isinstance(layout_meta, dict) else {},
                layout_ref=layout_ref,
                file_graph_ref=file_graph_ref,
                file_graph_segment=graph_segment,
                params=params,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
                total_pages=total_pages,
                chunk_plan=chunk_plan,
                collector=collector,
            )
            segment_snapshots.append(snapshot)

        primary_segment_id = primary_segments[0].segment_id

        manifest_segments: list[FileChunkManifestSegmentV2] = []
        by_segment_id = {s.segment_id: s for s in segment_snapshots}

        for segment in sorted(segments, key=lambda s: int(s.segment_order)):
            snap = by_segment_id.get(segment.segment_id)
            if snap is None:
                raise PermanentError(
                    f"Internal error: snapshot for segment {segment.segment_id} was not built"
                )

            manifest_segments.append(
                FileChunkManifestSegmentV2(
                    segment_id=segment.segment_id,
                    segment_type=segment.segment_type,
                    segment_title=segment.segment_title,
                    segment_order=segment.segment_order,
                    is_primary=bool(segment.is_primary),
                    page_start=segment.page_start,
                    page_end=segment.page_end,
                    segment_clause_tree_ref=segment.segment_clause_tree_ref or "",
                    segment_chunks_ref=None,
                    section_count=len(snap.section_chunks),
                    clause_count=len(snap.clause_chunks),
                    subclause_count=len(snap.subclause_chunks),
                    legal_unit_count=len(snap.legal_unit_chunks),
                    planning=snap.planning,
                )
            )

        # Этап 3 + Этап 4: агрегированные coverage‑метрики по всем сегментам.
        total_leaf_nodes = 0
        leaf_nodes_without_chunks = 0
        leaf_nodes_without_element_ids = 0
        leaf_nodes_empty_after_filtering = 0
        any_chunking_incomplete = False
        # ── Этап 4 ───────────────────────────────────────────────────────────
        total_heading_only_leaf_nodes = 0
        total_best_effort_leaf_nodes = 0

        for snap in segment_snapshots:
            if snap.total_leaf_nodes is not None:
                total_leaf_nodes += snap.total_leaf_nodes
            if snap.leaf_nodes_without_chunks is not None:
                leaf_nodes_without_chunks += snap.leaf_nodes_without_chunks
            if snap.leaf_nodes_without_element_ids is not None:
                leaf_nodes_without_element_ids += snap.leaf_nodes_without_element_ids
            if snap.leaf_nodes_empty_after_filtering is not None:
                leaf_nodes_empty_after_filtering += snap.leaf_nodes_empty_after_filtering
            if snap.chunking_incomplete:
                any_chunking_incomplete = True
            # ── Этап 4 ───────────────────────────────────────────────────────
            total_heading_only_leaf_nodes += snap.heading_only_leaf_nodes or 0
            total_best_effort_leaf_nodes += snap.best_effort_leaf_nodes or 0

        any_snapshot_degraded = any(bool(snap.degraded) for snap in segment_snapshots)
        any_layout_fallback_preferred = any(
            bool((snap.planning or {}).get("prefer_layout_fallback", False))
            for snap in segment_snapshots
        )

        file_degradation_reasons: list[str] = []
        if any_chunking_incomplete:
            file_degradation_reasons.append("chunking_incomplete_in_segments")
        if any_layout_fallback_preferred:
            file_degradation_reasons.append(
                "layout_fallback_preferred_but_not_yet_implemented"
            )

        file_degradation_reason = (
            ",".join(file_degradation_reasons)
            if file_degradation_reasons
            else None
        )


        file_manifest = FileChunkManifestV2(
            document_id=doc.id,
            document_version_id=version.id,
            layout_ref=layout_ref,
            file_graph_ref=file_graph_ref,
            primary_segment_id=primary_segment_id,
            segments=manifest_segments,
            degraded=any_snapshot_degraded,
            degradation_reason=file_degradation_reason,
            total_leaf_nodes=total_leaf_nodes,
            leaf_nodes_without_chunks=leaf_nodes_without_chunks,
            leaf_nodes_without_element_ids=leaf_nodes_without_element_ids,
            leaf_nodes_empty_after_filtering=leaf_nodes_empty_after_filtering,
            chunking_incomplete=any_chunking_incomplete,
            heading_only_leaf_nodes=total_heading_only_leaf_nodes,
            best_effort_leaf_nodes=total_best_effort_leaf_nodes,
            planning=_build_file_planning_payload(
                chunk_plan=chunk_plan,
                segment_snapshots=segment_snapshots,
            ),
        )

        logger.info(
            "SegmentChunkBuilderV2: build_for_version done",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "segments_count": len(segment_snapshots),
                "primary_segment_id": primary_segment_id,
                "total_section_count": sum(len(s.section_chunks) for s in segment_snapshots),
                "total_clause_count": sum(len(s.clause_chunks) for s in segment_snapshots),
                "total_subclause_count": sum(len(s.subclause_chunks) for s in segment_snapshots),
                "total_leaf_nodes": total_leaf_nodes,
                "leaf_nodes_without_chunks": leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_nodes_empty_after_filtering,
                "chunking_incomplete": any_chunking_incomplete,
                "file_planning_mode": (
                    file_manifest.planning.get("mode")
                    if isinstance(file_manifest.planning, dict)
                    else None
                ),
                "file_planning_applied": (
                    file_manifest.planning.get("applied")
                    if isinstance(file_manifest.planning, dict)
                    else False
                ),
                "total_legal_unit_count": sum(len(s.legal_unit_chunks) for s in segment_snapshots),
            },
        )

        return file_manifest, segment_snapshots

    async def _build_single_segment_snapshot(
        self,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        segment: DocumentSegment,
        layout: dict[str, Any],
        layout_meta: dict[str, Any],
        layout_ref: str,
        file_graph_ref: str,
        file_graph_segment: dict[str, Any],
        params: dict[str, Any],
        target_tokens: int,
        max_tokens: int,
        overlap_ratio: float,
        total_pages: int | None,
        chunk_plan: FileChunkPlan | None = None,
        collector: "TelemetryCollector | None" = None,
    ) -> SegmentChunkSnapshotV2:
        segment_clause_tree_ref = getattr(segment, "segment_clause_tree_ref", None)
        if not segment_clause_tree_ref:
            raise PermanentError(
                f"No segment_clause_tree_ref for segment {segment.segment_id} "
                f"(document_version_id={document_version_id}). "
                f"This is a STRUCTURE stage bug, not a CHUNKS bug."
            )

        logger.info(
            "SegmentChunkBuilderV2: build single segment start",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "segment_type": segment.segment_type,
                "segment_order": segment.segment_order,
                "segment_clause_tree_ref": segment_clause_tree_ref,
            },
        )

        clause_tree = self.store.get_json(segment_clause_tree_ref)
        if not isinstance(clause_tree, dict):
            raise PermanentError(
                f"Segment clause tree artifact {segment_clause_tree_ref} is invalid: expected dict"
            )

        clause_root = clause_tree.get("root") or []
        if not isinstance(clause_root, list):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} has invalid root: expected list"
            )

        clause_tree_document_id = str(clause_tree.get("document_id") or "")
        if clause_tree_document_id != str(document_id):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} document_id mismatch: "
                f"expected={str(document_id)!r}, actual={clause_tree_document_id!r}"
            )

        clause_tree_segment_id = str(clause_tree.get("segment_id") or "")
        if clause_tree_segment_id and clause_tree_segment_id != str(segment.segment_id):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} segment_id mismatch: "
                f"expected={str(segment.segment_id)!r}, actual={clause_tree_segment_id!r}"
            )

        clause_tree_segment_type = str(clause_tree.get("segment_type") or "")
        if clause_tree_segment_type and clause_tree_segment_type != str(segment.segment_type or ""):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} segment_type mismatch: "
                f"expected={str(segment.segment_type or '')!r}, actual={clause_tree_segment_type!r}"
            )

        clause_tree_segment_order = clause_tree.get("segment_order")
        if clause_tree_segment_order is not None and int(clause_tree_segment_order) != int(segment.segment_order):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} segment_order mismatch: "
                f"expected={int(segment.segment_order)}, actual={int(clause_tree_segment_order)}"
            )

        clause_tree_is_primary = clause_tree.get("is_primary_segment")
        if clause_tree_is_primary is not None and bool(clause_tree_is_primary) != bool(segment.is_primary):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} is_primary mismatch: "
                f"expected={bool(segment.is_primary)}, actual={bool(clause_tree_is_primary)}"
            )

        if not isinstance(file_graph_segment, dict):
            raise PermanentError(
                f"Invalid file_graph_segment for segment {segment.segment_id}: expected dict"
            )

        graph_segment_id = str(file_graph_segment.get("segment_id") or "")
        if graph_segment_id != str(segment.segment_id):
            raise PermanentError(
                f"FileGraph segment_id mismatch for segment {segment.segment_id}: "
                f"file_graph={graph_segment_id!r}"
            )

        graph_segment_type = str(file_graph_segment.get("segment_type") or "")
        if graph_segment_type and graph_segment_type != str(segment.segment_type or ""):
            raise PermanentError(
                f"FileGraph segment_type mismatch for segment {segment.segment_id}: "
                f"db={str(segment.segment_type or '')!r}, file_graph={graph_segment_type!r}"
            )

        graph_segment_order = file_graph_segment.get("segment_order")
        if (
            graph_segment_order is not None
            and int(graph_segment_order) != int(segment.segment_order)
        ):
            raise PermanentError(
                f"FileGraph segment_order mismatch for segment {segment.segment_id}: "
                f"db={int(segment.segment_order)}, file_graph={int(graph_segment_order)}"
            )

        graph_segment_is_primary = file_graph_segment.get("is_primary")
        if (
            graph_segment_is_primary is not None
            and bool(graph_segment_is_primary) != bool(segment.is_primary)
        ):
            raise PermanentError(
                f"FileGraph is_primary mismatch for segment {segment.segment_id}: "
                f"db={bool(segment.is_primary)}, file_graph={bool(graph_segment_is_primary)}"
            )

        segment_plan = (
            chunk_plan.plan_for_segment(segment.segment_id)
            if chunk_plan is not None
            else None
        )

        effective_target_tokens = target_tokens
        effective_max_tokens = max_tokens
        effective_overlap_ratio = overlap_ratio

        if segment_plan is not None:
            effective_target_tokens = segment_plan.token_params.target_tokens
            effective_max_tokens = segment_plan.token_params.max_tokens
            effective_overlap_ratio = segment_plan.token_params.overlap_ratio

        working_clause_tree = clause_tree
        filtered_technical_fallback_nodes = 0

        if (
            segment_plan is not None
            and segment_plan.drop_technical_fallback_nodes
        ):
            working_clause_tree, filtered_technical_fallback_nodes = (
                _filter_technical_fallback_tree(clause_tree)
            )

        working_clause_root = working_clause_tree.get("root") or []
        if not isinstance(working_clause_root, list):
            raise PermanentError(
                f"Filtered segment clause tree {segment_clause_tree_ref} "
                f"has invalid root: expected list"
            )

        leaf_result = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=document_id,
            tree=working_clause_tree,
            layout=layout,
        )

        leaf_chunks = leaf_result.chunks

        # ── Этап 4: читаем новые счётчики ────────────────────────────────────
        heading_only_leaf_nodes = getattr(leaf_result, "heading_only_leaf_nodes", 0) or 0
        best_effort_leaf_nodes = getattr(leaf_result, "best_effort_leaf_nodes", 0) or 0

        logger.info(
            "SegmentChunkBuilderV2: leaf chunks built",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "leaf_count": len(leaf_chunks),
                "clause_tree_root_count": len(working_clause_root),
                "segment_plan_mode": (
                    segment_plan.mode.value
                    if segment_plan is not None
                    else None
                ),
                "filtered_technical_fallback_nodes": filtered_technical_fallback_nodes,
                "total_leaf_nodes": leaf_result.total_leaf_nodes,
                "leaf_nodes_without_element_ids": leaf_result.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_result.leaf_nodes_empty_after_filtering,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": heading_only_leaf_nodes,
                "best_effort_leaf_nodes": best_effort_leaf_nodes,
            },
        )

        for ch in leaf_chunks:
            meta = ch.get("metadata") or {}
            before = ch.get("text") or ""
            after = normalize_clause_chunk_text(
                text=before,
                raw_uid=str(meta.get("raw_uid")) if meta.get("raw_uid") is not None else None,
                title=meta.get("title"),
            )
            ch["text"] = after

        propagate_language_filter(leaf_chunks, layout_meta)
        if total_pages:
            add_position_ratio(leaf_chunks, total_pages)

        clause_chunks = ensure_clause_metadata(document_id, leaf_chunks)

        invalid_clause_chunks = [
            ch for ch in clause_chunks if not ((ch.get("metadata") or {}).get("effective_uid"))
        ]
        if invalid_clause_chunks:
            logger.warning(
                "SegmentChunkBuilderV2: clause chunks without effective_uid after ensure",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_clause_chunks),
                },
            )

        invalid_clause_kinds = [
            ch for ch in clause_chunks if (ch.get("metadata") or {}).get("chunk_kind") != "clause"
        ]
        if invalid_clause_kinds:
            logger.warning(
                "SegmentChunkBuilderV2: non-clause chunks detected in clause collection",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_clause_kinds),
                },
            )

        clause_chunks = self._enrich_segment_metadata(
            chunks=clause_chunks,
            segment=segment,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )
        clause_chunks = add_summary(clause_chunks)

        # ПЕРЕД блоком:
        #   if (segment_plan is not None and not segment_plan.allow_section_chunks):

        # ── P3b: Honest Degraded Contract ────────────────────────────────────────────
        # Когда chunk_plan absent (plan не был передан из structure stage):
        # gate'ы drop_technical_fallback_nodes не срабатывают, потому что
        # segment_plan is None. Если при этом дерево полностью деградировано
        # (technical_fallback_only), clause_chunks несут chunk_kind="clause" — ложь.
        #
        # Исправление: форсировать chunk_kind="technical_fragment" + отключить
        # subclause splitting (нарезка технических фрагментов бессмысленна).
        #
        # Когда chunk_plan present: gate drop_technical_fallback_nodes уже удалил
        # fallback nodes ДО build_leaf_chunks(). Этот guard — defense-in-depth
        # только для plan-absent case.
        _tree_is_technical_fallback_only = _is_tree_technical_fallback_only(clause_tree)

        if chunk_plan is None and _tree_is_technical_fallback_only:
            clause_chunks = _remark_as_technical_fragments(clause_chunks)
            subclause_chunks = []
            logger.info(
                "SegmentChunkBuilderV2: technical_fallback_only tree without "
                "chunk plan — chunks remarked as technical_fragment, "
                "subclause splitting disabled",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "remarked_chunks_count": len(clause_chunks),
                },
            )


        if (
            segment_plan is not None
            and not segment_plan.allow_subclause_splitting
        ):
            logger.info(
                "SegmentChunkBuilderV2: subclause splitting disabled by chunk plan",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "segment_mode": segment_plan.mode.value,
                },
            )
            subclause_chunks = []
        else:
            subclause_chunks = build_sized_chunks_from_leaf(
                doc_id=document_id,
                leaf_chunks=leaf_chunks,
                target_tokens=effective_target_tokens,
                max_tokens=effective_max_tokens,
                overlap_ratio=effective_overlap_ratio,
                total_pages=total_pages,
            )

        invalid_subclause_kinds = [
            ch
            for ch in subclause_chunks
            if (ch.get("metadata") or {}).get("chunk_kind") != "subclause"
        ]
        if invalid_subclause_kinds:
            logger.warning(
                "SegmentChunkBuilderV2: non-subclause chunks detected in subclause collection",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_subclause_kinds),
                },
            )

        subclause_chunks = self._enrich_segment_metadata(
            chunks=subclause_chunks,
            segment=segment,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )
        subclause_chunks = add_summary(subclause_chunks)

        if segment_plan is not None and not segment_plan.allow_section_chunks:
            logger.info(
                "SegmentChunkBuilderV2: section chunks disabled by chunk plan",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "segment_mode": segment_plan.mode.value,
                },
            )
            section_chunks = []
        else:
            section_chunks = self._build_section_chunks_safe(
                document_id=document_id,
                document_version_id=document_version_id,
                segment=segment,
                clause_tree=working_clause_tree,
                layout=layout,
                file_graph_ref=file_graph_ref,
                layout_ref=layout_ref,
                segment_clause_tree_ref=segment_clause_tree_ref,
                total_pages=total_pages,
            )

        effective_params = {
            "target_tokens": effective_target_tokens,
            "max_tokens": effective_max_tokens,
            "overlap_ratio": effective_overlap_ratio,
        }

        planning_payload = _build_segment_planning_payload(
            segment_plan=segment_plan,
            filtered_technical_fallback_nodes=filtered_technical_fallback_nodes,
            effective_params=effective_params,
        )

        total_leaf_nodes = leaf_result.total_leaf_nodes
        leaf_nodes_without_element_ids = leaf_result.leaf_nodes_without_element_ids
        leaf_nodes_empty_after_filtering = leaf_result.leaf_nodes_empty_after_filtering

        # Coverage считается по leaf -> clause chunk mapping.
        # leaf_nodes_without_chunks = сколько leaf узлов не дали ни одного clause chunk.
        #
        # Этап 4: heading_only_leaf_nodes правильно пропускаются (без body текста
        # они не создают чанк — это нормально, не деградация).
        # Поэтому вычитаем их из расчёта чтобы не получить ложный chunking_incomplete.
        #
        # Пример: 10 leaf узлов, 2 heading-only, 8 реальных.
        # clause_chunks = 8. Без вычитания: 10 - 8 = 2 > 0 -> chunking_incomplete=True.
        # С вычитанием: (10 - 2) - 8 = 0 -> chunking_incomplete=False. Правильно.
        effective_leaf_nodes = max(0, total_leaf_nodes - heading_only_leaf_nodes)
        leaf_nodes_without_chunks = max(0, effective_leaf_nodes - len(clause_chunks))

        # chunking_incomplete = True только если есть реальные потери,
        # не считая нормально пропущенных heading-only узлов.
        chunking_incomplete = any(
            (
                leaf_nodes_without_chunks > 0,
                leaf_nodes_without_element_ids > 0,
                # leaf_nodes_empty_after_filtering уже не включает heading-only
                # (они считаются отдельно в heading_only_leaf_nodes).
                # Поэтому этот счётчик = реальные потери текста.
                leaf_nodes_empty_after_filtering > 0,
            )
        )

        degradation_reasons: list[str] = []
        if leaf_nodes_without_chunks > 0:
            degradation_reasons.append("leaf_nodes_without_chunks>0")
        if leaf_nodes_without_element_ids > 0:
            degradation_reasons.append("leaf_nodes_without_element_ids>0")
        if leaf_nodes_empty_after_filtering > 0:
            degradation_reasons.append("leaf_nodes_empty_after_filtering>0")

        prefer_layout_fallback = (
            segment_plan is not None
            and segment_plan.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
        )

        # ── Phase 11: Layout Fallback Builder ────────────────────────────────
        # Если Mode C → строим snapshot через layout fallback chunker
        # и возвращаем его сразу, минуя clause-based logic.
        if prefer_layout_fallback:
            return self._build_layout_fallback_snapshot(
                document_id=document_id,
                document_version_id=document_version_id,
                segment=segment,
                layout=layout,
                layout_ref=layout_ref,
                file_graph_ref=file_graph_ref,
                segment_clause_tree_ref=segment_clause_tree_ref,
                total_pages=total_pages,
                segment_plan=segment_plan,
            )

        degradation_reason = (
            ",".join(degradation_reasons)
            if degradation_reasons
            else None
        )

        logger.info(
            "SegmentChunkBuilderV2: segment coverage stats",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "total_leaf_nodes": total_leaf_nodes,
                "effective_leaf_nodes": effective_leaf_nodes,
                "leaf_nodes_without_chunks": leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_nodes_empty_after_filtering,
                "chunking_incomplete": chunking_incomplete,
                "degradation_reason": degradation_reason,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": heading_only_leaf_nodes,
                "best_effort_leaf_nodes": best_effort_leaf_nodes,
            },
        )

        # ── vNext: reusable layout element index for legal unit extraction ──
        element_index = ClauseTreeBuilder.build_element_index(layout)


        # ── Этап 5 + Phase 12: legal units + semantic enrichment ─────────────
        legal_units_snapshot: LegalUnitsSnapshot | None = None
        legal_units_enrichment_result: LegalUnitsEnrichmentResult | None = None
        legal_unit_chunks: list[dict[str, Any]] = []

        try:
            lu_builder = LegalUnitBuilder()
            legal_units_snapshot = lu_builder.build_from_clause_tree(
                clause_tree=working_clause_tree,
                segment_id=segment.segment_id,
                segment_type=segment.segment_type,
                segment_order=segment.segment_order,
                is_primary_segment=bool(segment.is_primary),
                document_id=str(document_id),
                document_version_id=str(document_version_id),
                element_index=element_index,
            )
            logger.info(
                "SegmentChunkBuilderV2: legal units snapshot built",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "total_units": len(legal_units_snapshot.units),
                    "units_with_known_type": legal_units_snapshot.units_with_known_type,
                },
            )

            legal_unit_chunks = build_retrieval_units_from_legal_units(
                snapshot=legal_units_snapshot,
                doc_id=document_id,
            )
            logger.info(
                "SegmentChunkBuilderV2: legal_unit retrieval chunks built",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "legal_unit_chunk_count": len(legal_unit_chunks),
                },
            )

        except Exception as lu_exc:
            legal_unit_chunks = []
            logger.warning(
                "SegmentChunkBuilderV2: legal unit builder failed, "
                "continuing without legal units",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "error": str(lu_exc),
                },
            )

        # Phase 12: semantic enrichment is now a dedicated formal pipeline stage.
        # SegmentChunkBuilderV2 no longer performs inline enrichment.
        # The sidecar is built by workers.build_legal_units_enrichment
        # after classification is complete, as a separate orchestrated stage.
        legal_units_enrichment_result: LegalUnitsEnrichmentResult | None = None
        
        logger.info(
            "SegmentChunkBuilderV2: single segment snapshot built",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "section_count": len(section_chunks),
                "clause_count": len(clause_chunks),
                "subclause_count": len(subclause_chunks),
                "legal_unit_count": len(legal_unit_chunks),
                "chunking_incomplete": chunking_incomplete,
            },
        )

        return SegmentChunkSnapshotV2(
            document_id=document_id,
            document_version_id=document_version_id,
            segment_id=segment.segment_id,
            segment_type=segment.segment_type,
            segment_title=segment.segment_title,
            segment_order=segment.segment_order,
            is_primary_segment=bool(segment.is_primary),
            segment_page_start=segment.page_start,
            segment_page_end=segment.page_end,
            layout_ref=layout_ref,
            file_graph_ref=file_graph_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            params=effective_params,
            section_chunks=section_chunks,
            clause_chunks=clause_chunks,
            subclause_chunks=subclause_chunks,
            legal_unit_chunks=legal_unit_chunks,
            degraded=(chunking_incomplete or prefer_layout_fallback),
            degradation_reason=degradation_reason,
            total_leaf_nodes=total_leaf_nodes,
            leaf_nodes_without_chunks=leaf_nodes_without_chunks,
            leaf_nodes_without_element_ids=leaf_nodes_without_element_ids,
            leaf_nodes_empty_after_filtering=leaf_nodes_empty_after_filtering,
            chunking_incomplete=chunking_incomplete,
            heading_only_leaf_nodes=heading_only_leaf_nodes,
            best_effort_leaf_nodes=best_effort_leaf_nodes,
            legal_units_snapshot=legal_units_snapshot,
            legal_units_enrichment_result=legal_units_enrichment_result,
            planning=planning_payload,
        )

    def _build_layout_fallback_snapshot(
        self,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        segment: DocumentSegment,
        layout: dict[str, Any],
        layout_ref: str,
        file_graph_ref: str,
        segment_clause_tree_ref: str,
        total_pages: int | None,
        segment_plan: Any | None,
    ) -> SegmentChunkSnapshotV2:
        """
        Построить snapshot через layout fallback chunker (Mode C).

        Используется когда prefer_layout_fallback=True.
        Clause tree полностью игнорируется.
        """
        logger.info(
            "SegmentChunkBuilderV2: building layout fallback snapshot",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
            },
        )

        max_tokens = (
            segment_plan.token_params.max_tokens
            if segment_plan is not None
            else 800
        )

        layout_chunks = build_layout_fallback_chunks(
            doc_id=document_id,
            layout=layout,
            segment_id=segment.segment_id,
            segment_type=segment.segment_type,
            max_tokens=max_tokens,
        )

        # Enrich с segment metadata
        layout_chunks = self._enrich_segment_metadata(
            chunks=layout_chunks,
            segment=segment,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )
        layout_chunks = add_summary(layout_chunks)

        effective_params = {
            "target_tokens": max_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": 0.0,
        }

        filtered_technical_fallback_nodes = 0
        planning_payload = _build_segment_planning_payload(
            segment_plan=segment_plan,
            filtered_technical_fallback_nodes=filtered_technical_fallback_nodes,
            effective_params=effective_params,
        )

        degradation_reason = "layout_fallback_chunker_used"

        logger.info(
            "SegmentChunkBuilderV2: layout fallback snapshot built",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "layout_fallback_chunks": len(layout_chunks),
            },
        )

        return SegmentChunkSnapshotV2(
            document_id=document_id,
            document_version_id=document_version_id,
            segment_id=segment.segment_id,
            segment_type=segment.segment_type,
            segment_title=segment.segment_title,
            segment_order=segment.segment_order,
            is_primary_segment=bool(segment.is_primary),
            segment_page_start=segment.page_start,
            segment_page_end=segment.page_end,
            layout_ref=layout_ref,
            file_graph_ref=file_graph_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            params=effective_params,
            section_chunks=[],
            clause_chunks=layout_chunks,
            subclause_chunks=[],
            legal_unit_chunks=[],
            degraded=True,
            degradation_reason=degradation_reason,
            total_leaf_nodes=None,
            leaf_nodes_without_chunks=None,
            leaf_nodes_without_element_ids=None,
            leaf_nodes_empty_after_filtering=None,
            chunking_incomplete=False,
            heading_only_leaf_nodes=0,
            best_effort_leaf_nodes=0,
            legal_units_snapshot=None,
            planning=planning_payload,
        )


    def _build_section_chunks_safe(
        self,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        segment: DocumentSegment,
        clause_tree: dict[str, Any],
        layout: dict[str, Any],
        file_graph_ref: str,
        layout_ref: str,
        segment_clause_tree_ref: str,
        total_pages: int | None,
    ) -> list[dict[str, Any]]:
        """
        Построить section chunks для сегмента.

        Важно:
        - Если section chunks не удалось построить, это не ломает весь сегмент.
        - Мы продолжаем с пустым списком section chunks.
        """
        try:
            section_chunks = ClauseTreeBuilder.build_section_chunks(
                doc_id=document_id,
                tree=clause_tree,
                layout=layout,
            )
            if not isinstance(section_chunks, list):
                logger.warning(
                    "SegmentChunkBuilderV2: section builder returned non-list, using empty sections",
                    extra={
                        "document_id": str(document_id),
                        "document_version_id": str(document_version_id),
                        "segment_id": segment.segment_id,
                        "returned_type": type(section_chunks).__name__,
                    },
                )
                return []

            invalid_section_kinds = [
                ch
                for ch in section_chunks
                if (ch.get("metadata") or {}).get("chunk_kind") != "section"
            ]
            if invalid_section_kinds:
                logger.warning(
                    "SegmentChunkBuilderV2: non-section chunks detected in section collection",
                    extra={
                        "document_id": str(document_id),
                        "document_version_id": str(document_version_id),
                        "segment_id": segment.segment_id,
                        "invalid_count": len(invalid_section_kinds),
                    },
                )

            enriched = self._enrich_segment_metadata(
                chunks=section_chunks,
                segment=segment,
                file_graph_ref=file_graph_ref,
                layout_ref=layout_ref,
                segment_clause_tree_ref=segment_clause_tree_ref,
                total_pages=total_pages,
            )
            return add_summary(enriched)

        except Exception as e:
            logger.warning(
                "SegmentChunkBuilderV2: failed to build section chunks, continuing without sections",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "error": str(e),
                },
            )
            return []

    def _enrich_segment_metadata(
        self,
        *,
        chunks: list[dict[str, Any]],
        segment: DocumentSegment,
        file_graph_ref: str,
        layout_ref: str,
        segment_clause_tree_ref: str,
        total_pages: int | None,
    ) -> list[dict[str, Any]]:
        """
        Добавить в metadata каждого чанка segment-aware поля.

        Это ключевая часть CHUNKS v2:
        - downstream должен понимать, из какого logical segment пришёл чанк;
        - по какому tree он построен;
        - primary это сегмент или secondary;
        - каков его page-range в контексте сегмента и файла.
        """
        out: list[dict[str, Any]] = []

        for ch in chunks:
            if not isinstance(ch, dict):
                continue

            text = ch.get("text") or ""
            if not text.strip():
                continue

            meta = dict(ch.get("metadata") or {})
            start_page = meta.get("start_page")
            end_page = meta.get("end_page")

            position_ratio_within_file = meta.get("position_ratio")
            position_ratio_within_segment = self._calc_position_ratio_within_segment(
                start_page=start_page,
                end_page=end_page,
                segment_page_start=segment.page_start,
                segment_page_end=segment.page_end,
            )

            meta["segment_id"] = segment.segment_id
            meta["segment_type"] = segment.segment_type
            meta["segment_title"] = segment.segment_title
            meta["segment_order"] = segment.segment_order
            meta["is_primary_segment"] = bool(segment.is_primary)
            meta["segment_page_start"] = segment.page_start
            meta["segment_page_end"] = segment.page_end

            meta["layout_ref"] = layout_ref
            meta["file_graph_ref"] = file_graph_ref
            meta["segment_clause_tree_ref"] = segment_clause_tree_ref

            meta["position_ratio_within_file"] = position_ratio_within_file
            meta["position_ratio_within_segment"] = position_ratio_within_segment

            if total_pages is not None and "total_pages" not in meta:
                meta["total_pages"] = total_pages

            enriched = dict(ch)
            enriched["metadata"] = meta
            out.append(enriched)

        return out

    def _calc_position_ratio_within_segment(
        self,
        *,
        start_page: int | None,
        end_page: int | None,
        segment_page_start: int,
        segment_page_end: int,
    ) -> float | None:
        """
        Нормализованная позиция чанка внутри сегмента.

        Пример:
        - если сегмент занимает страницы 10..20,
        - а чанк находится на 15..16,
        - то позиция считается относительно диапазона 10..20, а не всего файла.
        """
        if segment_page_end < segment_page_start:
            return None

        span = segment_page_end - segment_page_start + 1
        if span <= 0:
            return None

        if start_page is None and end_page is None:
            return None

        s = start_page if isinstance(start_page, int) else end_page
        e = end_page if isinstance(end_page, int) else start_page
        if s is None or e is None:
            return None

        mid = (s + e) / 2.0
        relative = (mid - segment_page_start + 1.0) / float(span)

        if relative < 0.0:
            return 0.0
        if relative > 1.0:
            return 1.0
        return relative


