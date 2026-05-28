# src/services/structure/models/_graph.py

"""
Модели file-level graph: сегменты и межсегментные связи.

SegmentDocument описывает один логический документ внутри файла.
FileGraph — контейнер всех сегментов с cross-document links и file-level diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._constants import (
    SEGMENT_CONFIDENCE_MEDIUM,
    STRUCTURE_CONFIDENCE_MEDIUM,
)
from ._identity import generate_scope_name
from ._normalization import (
    _ensure_dict,
    _norm_bool,
    _norm_opt_str,
    _norm_str,
    _normalize_non_negative_int,
    _normalize_positive_int,
    _normalize_probability,
    _normalize_segment_confidence,
    _normalize_segment_type,  # ← ДОБАВЛЕН НЕДОСТАЮЩИЙ ИМПОРТ
    _normalize_string_list,
    _normalize_structure_confidence,
    _validate_scope_name,
)


def _ensure_segments(values: Any, field_name: str) -> list[SegmentDocument]:
    """Валидирует list[SegmentDocument]."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[SegmentDocument]")
    normalized: list[SegmentDocument] = []
    for idx, value in enumerate(values):
        if not isinstance(value, SegmentDocument):
            raise ValueError(f"{field_name}[{idx}] must be SegmentDocument")
        normalized.append(value)
    return normalized


def _ensure_cross_links(values: Any, field_name: str) -> list[CrossDocumentLink]:
    """Валидирует list[CrossDocumentLink]."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[CrossDocumentLink]")
    normalized: list[CrossDocumentLink] = []
    for idx, value in enumerate(values):
        if not isinstance(value, CrossDocumentLink):
            raise ValueError(f"{field_name}[{idx}] must be CrossDocumentLink")
        normalized.append(value)
    return normalized


@dataclass
class SegmentDocument:
    """
    Описание одного логического сегмента документа внутри файла.

    Canonical identity: segment_id (обычно UUID v5).
    Содержит page/element range, тип, confidence и diagnostics.
    """

    segment_id: str
    document_id: str
    segment_order: int
    segment_type: str
    page_start: int
    page_end: int
    element_start: int
    element_end: int
    document_version_id: str | None = None
    segment_title: str | None = None
    scope_name: str | None = None
    confidence: str = SEGMENT_CONFIDENCE_MEDIUM
    segmentation_confidence_score: float = 0.0
    segmentation_reasons: list[str] = field(default_factory=list)
    is_primary: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.segment_id = _norm_str(self.segment_id)
        self.document_id = _norm_str(self.document_id)
        self.document_version_id = _norm_opt_str(self.document_version_id)
        self.segment_title = _norm_opt_str(self.segment_title)
        self.segment_type = _normalize_segment_type(self.segment_type)
        self.segment_order = _normalize_non_negative_int(
            self.segment_order,
            "SegmentDocument.segment_order",
        )
        self.page_start = _normalize_positive_int(self.page_start, "SegmentDocument.page_start")
        self.page_end = _normalize_positive_int(self.page_end, "SegmentDocument.page_end")
        self.element_start = _normalize_non_negative_int(
            self.element_start,
            "SegmentDocument.element_start",
        )
        self.element_end = _normalize_non_negative_int(
            self.element_end,
            "SegmentDocument.element_end",
        )
        self.confidence = _normalize_segment_confidence(self.confidence)
        self.segmentation_confidence_score = _normalize_probability(
            self.segmentation_confidence_score,
            "SegmentDocument.segmentation_confidence_score",
        )
        self.segmentation_reasons = _normalize_string_list(
            self.segmentation_reasons,
            "SegmentDocument.segmentation_reasons",
        )
        self.is_primary = _norm_bool(self.is_primary)
        self.diagnostics = _ensure_dict(self.diagnostics, "SegmentDocument.diagnostics")

        if not self.segment_id:
            raise ValueError("SegmentDocument.segment_id must be non-empty")
        if not self.document_id:
            raise ValueError("SegmentDocument.document_id must be non-empty")
        if self.page_end < self.page_start:
            raise ValueError("SegmentDocument page range must satisfy 1 <= page_start <= page_end")
        if self.element_end < self.element_start:
            raise ValueError(
                "SegmentDocument element range must satisfy 0 <= element_start <= element_end"
            )

        if self.scope_name is None:
            self.scope_name = generate_scope_name(self.segment_type, self.segment_order)
        else:
            self.scope_name = _validate_scope_name(self.scope_name)

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "segment_id": self.segment_id,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment_order": self.segment_order,
            "segment_type": self.segment_type,
            "segment_title": self.segment_title,
            "scope_name": self.scope_name,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "element_start": self.element_start,
            "element_end": self.element_end,
            "confidence": self.confidence,
            "segmentation_confidence_score": self.segmentation_confidence_score,
            "segmentation_reasons": list(self.segmentation_reasons),
            "is_primary": self.is_primary,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass
class CrossDocumentLink:
    """
    Связь между двумя сегментами внутри одного FileGraph.

    Canonical identity: (source_segment_id, target_segment_id, link_type).
    """

    source_segment_id: str
    target_segment_id: str
    link_type: str
    reference_text: str | None = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        self.source_segment_id = _norm_str(self.source_segment_id)
        self.target_segment_id = _norm_str(self.target_segment_id)
        self.link_type = _norm_str(self.link_type)
        self.reference_text = _norm_opt_str(self.reference_text)
        self.confidence = _normalize_probability(
            self.confidence,
            "CrossDocumentLink.confidence",
        )

        if not self.source_segment_id or not self.target_segment_id:
            raise ValueError(
                "CrossDocumentLink source_segment_id and target_segment_id must be non-empty"
            )
        if not self.link_type:
            raise ValueError("CrossDocumentLink.link_type must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "source_segment_id": self.source_segment_id,
            "target_segment_id": self.target_segment_id,
            "link_type": self.link_type,
            "reference_text": self.reference_text,
            "confidence": self.confidence,
        }


@dataclass
class FileGraph:
    """
    File-level контейнер: список сегментов + межсегментные связи + file diagnostics.

    Canonical model для результата file_graph_builder.
    """

    document_id: str
    segments: list[SegmentDocument]
    cross_links: list[CrossDocumentLink]
    primary_segment_id: str | None
    document_version_id: str | None = None
    degraded: bool = False
    structural_confidence: str = STRUCTURE_CONFIDENCE_MEDIUM
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "3.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.segments = _ensure_segments(self.segments, "FileGraph.segments")
        self.cross_links = _ensure_cross_links(self.cross_links, "FileGraph.cross_links")
        self.primary_segment_id = _norm_opt_str(self.primary_segment_id)
        self.document_version_id = _norm_opt_str(self.document_version_id)
        self.degraded = _norm_bool(self.degraded)
        self.structural_confidence = _normalize_structure_confidence(self.structural_confidence)
        self.diagnostics = _ensure_dict(self.diagnostics, "FileGraph.diagnostics")

        if not self.document_id:
            raise ValueError("FileGraph.document_id must be non-empty")

        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError(f"FileGraph contains duplicate segment_ids: {segment_ids}")

        segment_orders = [segment.segment_order for segment in self.segments]
        if len(segment_orders) != len(set(segment_orders)):
            raise ValueError(f"FileGraph contains duplicate segment_order values: {segment_orders}")

        for segment in self.segments:
            if segment.document_id != self.document_id:
                raise ValueError(
                    f"FileGraph segment document_id mismatch: "
                    f"graph.document_id={self.document_id!r}, "
                    f"segment.document_id={segment.document_id!r}, "
                    f"segment_id={segment.segment_id!r}"
                )
            if self.document_version_id is not None:
                if (
                    segment.document_version_id is not None
                    and segment.document_version_id != self.document_version_id
                ):
                    raise ValueError(
                        f"FileGraph segment document_version_id mismatch: "
                        f"graph.document_version_id={self.document_version_id!r}, "
                        f"segment.document_version_id={segment.document_version_id!r}, "
                        f"segment_id={segment.segment_id!r}"
                    )

        if self.primary_segment_id:
            if self.primary_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.primary_segment_id={self.primary_segment_id!r} "
                    f"is not present in segments"
                )

        primary_marked = [segment.segment_id for segment in self.segments if segment.is_primary]

        if len(primary_marked) > 1:
            raise ValueError(
                f"FileGraph invariant violated: multiple primary segments marked: {primary_marked}"
            )

        if self.primary_segment_id:
            if primary_marked and primary_marked[0] != self.primary_segment_id:
                raise ValueError(
                    f"FileGraph invariant violated: primary_segment_id={self.primary_segment_id!r} "
                    f"does not match segment marked is_primary=True ({primary_marked[0]!r})"
                )
        elif primary_marked:
            self.primary_segment_id = primary_marked[0]

        for link in self.cross_links:
            if link.source_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.cross_links contains unknown source_segment_id="
                    f"{link.source_segment_id!r}"
                )
            if link.target_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.cross_links contains unknown target_segment_id="
                    f"{link.target_segment_id!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "structural_confidence": self.structural_confidence,
            "diagnostics": self.diagnostics,
            "segments": [segment.to_dict() for segment in self.segments],
            "cross_links": [link.to_dict() for link in self.cross_links],
        }

    @property
    def primary_segment(self) -> SegmentDocument | None:
        """Получить primary segment или None."""
        if not self.primary_segment_id:
            return None
        return next(
            (segment for segment in self.segments if segment.segment_id == self.primary_segment_id),
            None,
        )

    @property
    def segment_count(self) -> int:
        """Количество сегментов в файле."""
        return len(self.segments)

    def get_segment(self, segment_id: str) -> SegmentDocument | None:
        """Найти segment по ID или вернуть None."""
        normalized_segment_id = _norm_str(segment_id)
        if not normalized_segment_id:
            return None
        return next(
            (segment for segment in self.segments if segment.segment_id == normalized_segment_id),
            None,
        )
