# src/services/structure/_models/_artifacts.py

"""
Phase 6 — Canonical Artifact Layer (слой канонических артефактов).

Модуль формализует контракт хранения ссылок на канонические артефакты
для одного документа.

Ключевое архитектурное решение:
- Источник истины по ссылкам на артефакты уже существует в БД/хранилище:
  - DocumentVersion.clause_tree_ref
  - DocumentVersion.file_graph_ref
  - DocumentVersion.chunks_manifest_v2_ref
  - DocumentSegment.segment_clause_tree_ref
  - DocumentSegment.segment_chunks_ref
- Поэтому Phase 6 НЕ вводит параллельный источник истины.
- Вместо этого модуль даёт:
  - неизменяемые dataclass'ы, зеркаляющие сохранённые ссылки,
  - детерминированные проверки готовности для downstream‑стадий,
  - реестр артефактов per-document как рантайм‑фасад.

Это следует принципу v5.2:
Deterministic Core -> Probabilistic Assistance -> Semantic Intelligence.

На практике:
- компоненты structure / retrieval обмениваются стабильными ссылками на артефакты,
  а не сырыми объектами и не неявным поиском файлов.

Текущий реализованный охват:
- structure‑артефакты:
  - file_graph_ref
  - clause_tree_ref (legacy / primary сегмент)
  - segment_clause_tree_ref
- retrieval / chunking‑артефакты:
  - chunks_manifest_v2_ref
  - segment_chunks_ref

Зарезервировано для будущих фаз:
- cross_ref_graph_ref
- confidence_map_ref

Реестр создаётся на документ, НЕ является синглтоном.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class SegmentArtifactRefs:
    """
    Ссылки на канонические артефакты для одного логического сегмента.

    Параметры
    ---------
    segment_id:
        Стабильный идентификатор сегмента из FileGraph / DocumentSegment.
    segment_clause_tree_ref:
        Сохранённая ссылка на ClauseTree этого сегмента.
    segment_chunks_ref:
        Сохранённая ссылка на snapshot чанков этого сегмента.
    legal_units_ref:
        Сохранённая ссылка на legal units snapshot (Phase 12 / Этап 5).
    legal_units_enrichment_ref:
        Сохранённая ссылка на LLM enrichment sidecar (Phase 12).

    Заметки
    -------
    Этот dataclass лишь зеркалирует контракт в DocumentSegment.
    Он не владеет payload'ом — только описывает, где живут канонические данные.
    """

    segment_id: str
    segment_clause_tree_ref: str | None = None
    segment_chunks_ref: str | None = None
    legal_units_ref: str | None = None
    legal_units_enrichment_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.segment_id:
            raise ValueError("segment_id must not be empty")

    @property
    def has_tree(self) -> bool:
        """True, если у сегмента есть ссылка на ClauseTree."""
        return bool(self.segment_clause_tree_ref)

    @property
    def has_chunks(self) -> bool:
        """True, если у сегмента есть ссылка на snapshot чанков."""
        return bool(self.segment_chunks_ref)

    @property
    def has_legal_units(self) -> bool:
        """True, если у сегмента есть ссылка на legal units snapshot."""
        return bool(self.legal_units_ref)

    @property
    def has_enrichment(self) -> bool:
        """True, если у сегмента есть ссылка на enrichment sidecar."""
        return bool(self.legal_units_enrichment_ref)

    def to_dict(self) -> dict[str, Any]:
        """Сериализует ссылки в детерминированный JSON‑совместимый dict."""
        return {
            "segment_id": self.segment_id,
            "segment_clause_tree_ref": self.segment_clause_tree_ref,
            "segment_chunks_ref": self.segment_chunks_ref,
            "legal_units_ref": self.legal_units_ref,
            "legal_units_enrichment_ref": self.legal_units_enrichment_ref,
            "has_tree": self.has_tree,
            "has_chunks": self.has_chunks,
            "has_legal_units": self.has_legal_units,
            "has_enrichment": self.has_enrichment,
        }


@dataclass(slots=True, frozen=True)
class CanonicalArtifactRefs:
    """
    Канонические ссылки на артефакты для одного документа.

    Параметры
    ---------
    document_id:
        Идентификатор физического документа.
    clause_tree_ref:
        Legacy / primary ClauseTree, хранящийся в DocumentVersion.
        В v2‑совместимых сценариях относится к primary‑сегменту.
    file_graph_ref:
        Ссылка на FileGraph, описывающий все логические сегменты.
    chunks_manifest_v2_ref:
        Ссылка на file‑level манифест чанков (CHUNKS v2).
    segment_refs:
        Ссылки по сегментам (зеркало DocumentSegment).
    cross_ref_graph_ref:
        Зарезервировано для Phase 7+ (глобальный граф ссылок).
    confidence_map_ref:
        Зарезервировано для Phase 5/6+ (артефакт confidence).

    Инварианты
    ----------
    - document_id не пустой
    - segment_id уникален внутри одного документа
    - проверки готовности детерминированны и без побочных эффектов

    Заметки
    -------
    Это каноническая точка входа Phase 6 для downstream‑читателей.
    Dataclass зеркалирует существующий контракт БД/хранилища, а не заменяет его.
    """

    document_id: str
    clause_tree_ref: str | None = None
    file_graph_ref: str | None = None
    chunks_manifest_v2_ref: str | None = None
    segment_refs: tuple[SegmentArtifactRefs, ...] = ()

    # будущие фазы
    cross_ref_graph_ref: str | None = None
    confidence_map_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id must not be empty")

        seen: set[str] = set()
        for seg in self.segment_refs:
            if seg.segment_id in seen:
                raise ValueError(f"duplicate segment_id={seg.segment_id!r}")
            seen.add(seg.segment_id)

    @property
    def has_primary_tree(self) -> bool:
        """True, если существует ссылка на primary / legacy ClauseTree."""
        return bool(self.clause_tree_ref)

    @property
    def has_file_graph(self) -> bool:
        """True, если существует ссылка на FileGraph."""
        return bool(self.file_graph_ref)

    @property
    def has_chunk_manifest(self) -> bool:
        """True, если существует ссылка на манифест чанков CHUNKS v2."""
        return bool(self.chunks_manifest_v2_ref)

    @property
    def has_cross_ref_graph(self) -> bool:
        """True, если существует ссылка на будущий граф перекрёстных ссылок."""
        return bool(self.cross_ref_graph_ref)

    @property
    def has_confidence_map(self) -> bool:
        """True, если существует ссылка на будущий confidence‑артефакт."""
        return bool(self.confidence_map_ref)

    @property
    def segment_count(self) -> int:
        """Количество логических сегментов, известных для документа."""
        return len(self.segment_refs)

    @property
    def all_segments_have_trees(self) -> bool:
        """
        True, если у КАЖДОГО сегмента есть ссылка на ClauseTree.

        Для пустого списка сегментов возвращает False, так как
        segment‑aware структура в этом случае ещё не сформирована.
        """
        if not self.segment_refs:
            return False
        return all(seg.has_tree for seg in self.segment_refs)

    @property
    def all_segments_have_chunks(self) -> bool:
        """
        True, если у КАЖДОГО сегмента есть ссылка на snapshot чанков.

        Для пустого списка сегментов возвращает False, так как
        retrieval‑ready покрытие по сегментам ещё не сформировано.
        """
        if not self.segment_refs:
            return False
        return all(seg.has_chunks for seg in self.segment_refs)

    @property
    def structure_ready(self) -> bool:
        """
        Готовность structure‑слоя.

        Текущая логика:
        - есть file_graph_ref
        - есть clause_tree_ref
        - у всех сегментов есть segment_clause_tree_ref
        """
        return (
            self.has_file_graph
            and self.has_primary_tree
            and self.all_segments_have_trees
        )

    @property
    def retrieval_ready(self) -> bool:
        """
        Готовность retrieval / chunking‑слоя.

        Текущая логика:
        - structure_ready == True
        - есть chunks_manifest_v2_ref
        - у всех сегментов есть segment_chunks_ref
        """
        return (
            self.structure_ready
            and self.has_chunk_manifest
            and self.all_segments_have_chunks
        )

    @property
    def is_complete_for_current_phase(self) -> bool:
        """
        Полнота артефактов для текущего охвата Phase 6.

        Специально НЕ требует наличия будущих артефактов вроде:
        - cross_ref_graph_ref
        - confidence_map_ref
        """
        return self.retrieval_ready

    def to_dict(self) -> dict[str, Any]:
        """Детерминированная сериализация ссылок и флагов готовности."""
        return {
            "document_id": self.document_id,
            "clause_tree_ref": self.clause_tree_ref,
            "file_graph_ref": self.file_graph_ref,
            "chunks_manifest_v2_ref": self.chunks_manifest_v2_ref,
            "cross_ref_graph_ref": self.cross_ref_graph_ref,
            "confidence_map_ref": self.confidence_map_ref,
            "segment_count": self.segment_count,
            "segments": [seg.to_dict() for seg in self.segment_refs],
            "structure_ready": self.structure_ready,
            "retrieval_ready": self.retrieval_ready,
            "is_complete_for_current_phase": self.is_complete_for_current_phase,
        }


@dataclass
class CanonicalArtifactRegistry:
    """
    Рантайм‑фасад поверх канонических ссылок на артефакты (per-document).

    Параметры
    ---------
    refs:
        Неизменяемые ссылки на артефакты для данного документа.
    loaded_payloads:
        Необязательный кэш уже загруженных payload'ов по логическим ключам.

    Заметки
    -------
    Этот реестр преднамеренно лёгкий:
    - создаётся на документ,
    - не является синглтоном,
    - не заменяет ссылки в БД/хранилище,
    - может быть «наполнен» объектами через ArtifactStore / сервисы.

    Типичный сценарий:
    - refs остаются долговременным контрактом,
    - loaded_payloads даёт удобство в рамках одного процесса/пайплайна.
    """

    refs: CanonicalArtifactRefs
    loaded_payloads: dict[str, Any] = field(default_factory=dict)

    @property
    def document_id(self) -> str:
        """Идентификатор документа из вложенных refs."""
        return self.refs.document_id

    def attach_payload(self, key: str, payload: Any) -> None:
        """
        Привязать загруженный payload под логическим ключом.

        Параметры
        ---------
        key:
            Стабильное логическое имя, например:
            'file_graph', 'primary_clause_tree', 'chunks_manifest_v2'.
        payload:
            Уже загруженный артефакт (dict / модель / др.).
        """
        if not key:
            raise ValueError("payload key must not be empty")
        self.loaded_payloads[key] = payload

    def get_payload(self, key: str) -> Any | None:
        """
        Вернуть ранее привязанный payload по ключу или None, если его нет.
        """
        return self.loaded_payloads.get(key)

    @property
    def structure_ready(self) -> bool:
        """Прокси‑флаг готовности structure‑слоя из refs."""
        return self.refs.structure_ready

    @property
    def retrieval_ready(self) -> bool:
        """Прокси‑флаг готовности retrieval‑слоя из refs."""
        return self.refs.retrieval_ready

    def to_dict(self) -> dict[str, Any]:
        """Детерминированная сериализация состояния реестра."""
        return {
            "refs": self.refs.to_dict(),
            "loaded_payload_keys": sorted(self.loaded_payloads.keys()),
            "structure_ready": self.structure_ready,
            "retrieval_ready": self.retrieval_ready,
        }

