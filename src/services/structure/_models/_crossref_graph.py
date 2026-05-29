# src/services/structure/_models/_crossref_graph.py

"""
Cross-reference graph artifact for one logical document / segment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._nodes import CrossReference
from ._normalization import (
    _ensure_dict,
    _norm_str,
    _normalize_non_negative_int,
    _normalize_string_tuple_mapping,
)


def _ensure_cross_references_tuple(values: Any, field_name: str) -> tuple[CrossReference, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a list|tuple[CrossReference]")
    normalized: list[CrossReference] = []
    for idx, value in enumerate(values):
        if not isinstance(value, CrossReference):
            raise ValueError(f"{field_name}[{idx}] must be CrossReference")
        normalized.append(value)
    return tuple(normalized)


@dataclass(frozen=True)
class CrossReferenceStats:
    references_count: int = 0
    unique_sources_count: int = 0
    unique_targets_count: int = 0
    unresolved_count: int = 0
    ambiguous_count: int = 0
    invalid_source_mapping_count: int = 0
    malformed_stable_element_id_count: int = 0
    duplicate_reference_count: int = 0
    skipped_self_reference_count: int = 0
    index_node_skipped_count: int = 0
    duplicate_effective_uid_count: int = 0
    duplicate_scoped_raw_uid_count: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "references_count",
            "unique_sources_count",
            "unique_targets_count",
            "unresolved_count",
            "ambiguous_count",
            "invalid_source_mapping_count",
            "malformed_stable_element_id_count",
            "duplicate_reference_count",
            "skipped_self_reference_count",
            "index_node_skipped_count",
            "duplicate_effective_uid_count",
            "duplicate_scoped_raw_uid_count",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                _normalize_non_negative_int(value, f"CrossReferenceStats.{field_name}"),
            )

    def to_dict(self) -> dict[str, int]:
        return {
            "references_count": self.references_count,
            "unique_sources_count": self.unique_sources_count,
            "unique_targets_count": self.unique_targets_count,
            "unresolved_count": self.unresolved_count,
            "ambiguous_count": self.ambiguous_count,
            "invalid_source_mapping_count": self.invalid_source_mapping_count,
            "malformed_stable_element_id_count": self.malformed_stable_element_id_count,
            "duplicate_reference_count": self.duplicate_reference_count,
            "skipped_self_reference_count": self.skipped_self_reference_count,
            "index_node_skipped_count": self.index_node_skipped_count,
            "duplicate_effective_uid_count": self.duplicate_effective_uid_count,
            "duplicate_scoped_raw_uid_count": self.duplicate_scoped_raw_uid_count,
        }


@dataclass(frozen=True)
class CrossReferenceGraph:
    document_id: str
    references: tuple[CrossReference, ...]
    outgoing_index: dict[str, tuple[str, ...]]
    incoming_index: dict[str, tuple[str, ...]]
    stats: CrossReferenceStats
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        document_id = _norm_str(self.document_id)
        if not document_id:
            raise ValueError("CrossReferenceGraph.document_id must be non-empty")

        references = _ensure_cross_references_tuple(self.references, "CrossReferenceGraph.references")
        outgoing_index = _normalize_string_tuple_mapping(
            self.outgoing_index,
            "CrossReferenceGraph.outgoing_index",
        )
        incoming_index = _normalize_string_tuple_mapping(
            self.incoming_index,
            "CrossReferenceGraph.incoming_index",
        )

        if not isinstance(self.stats, CrossReferenceStats):
            raise ValueError("CrossReferenceGraph.stats must be CrossReferenceStats")

        schema_version = _norm_str(self.schema_version) or "1.0"

        referenced_pairs = {(ref.source_effective_uid, ref.target_effective_uid) for ref in references}
        outgoing_pairs = {
            (source_uid, target_uid)
            for source_uid, targets in outgoing_index.items()
            for target_uid in targets
        }
        incoming_pairs = {
            (source_uid, target_uid)
            for target_uid, sources in incoming_index.items()
            for source_uid in sources
        }

        if referenced_pairs != outgoing_pairs:
            raise ValueError(
                "CrossReferenceGraph.outgoing_index does not match references exactly: "
                f"missing={sorted(referenced_pairs - outgoing_pairs)}, "
                f"extra={sorted(outgoing_pairs - referenced_pairs)}"
            )
        if referenced_pairs != incoming_pairs:
            raise ValueError(
                "CrossReferenceGraph.incoming_index does not match references exactly: "
                f"missing={sorted(referenced_pairs - incoming_pairs)}, "
                f"extra={sorted(incoming_pairs - referenced_pairs)}"
            )

        unique_sources = {ref.source_effective_uid for ref in references}
        unique_targets = {ref.target_effective_uid for ref in references}

        if self.stats.references_count != len(references):
            raise ValueError(
                "CrossReferenceGraph.stats.references_count mismatch: "
                f"stats={self.stats.references_count}, actual={len(references)}"
            )
        if self.stats.unique_sources_count != len(unique_sources):
            raise ValueError(
                "CrossReferenceGraph.stats.unique_sources_count mismatch: "
                f"stats={self.stats.unique_sources_count}, actual={len(unique_sources)}"
            )
        if self.stats.unique_targets_count != len(unique_targets):
            raise ValueError(
                "CrossReferenceGraph.stats.unique_targets_count mismatch: "
                f"stats={self.stats.unique_targets_count}, actual={len(unique_targets)}"
            )

        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "references", references)
        object.__setattr__(self, "outgoing_index", outgoing_index)
        object.__setattr__(self, "incoming_index", incoming_index)
        object.__setattr__(self, "schema_version", schema_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "references": [ref.to_dict() for ref in self.references],
            "outgoing_index": {key: list(value) for key, value in self.outgoing_index.items()},
            "incoming_index": {key: list(value) for key, value in self.incoming_index.items()},
            "stats": self.stats.to_dict(),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_references(
        cls,
        *,
        document_id: str,
        references: list[CrossReference] | tuple[CrossReference, ...],
        stats: CrossReferenceStats,
        schema_version: str = "1.0",
    ) -> "CrossReferenceGraph":
        outgoing_temp: dict[str, list[str]] = {}
        incoming_temp: dict[str, list[str]] = {}

        for ref in references:
            outgoing_targets = outgoing_temp.setdefault(ref.source_effective_uid, [])
            if ref.target_effective_uid not in outgoing_targets:
                outgoing_targets.append(ref.target_effective_uid)

            incoming_sources = incoming_temp.setdefault(ref.target_effective_uid, [])
            if ref.source_effective_uid not in incoming_sources:
                incoming_sources.append(ref.source_effective_uid)

        outgoing_index = {key: tuple(value) for key, value in sorted(outgoing_temp.items())}
        incoming_index = {key: tuple(value) for key, value in sorted(incoming_temp.items())}

        return cls(
            document_id=document_id,
            references=tuple(references),
            outgoing_index=outgoing_index,
            incoming_index=incoming_index,
            stats=stats,
            schema_version=schema_version,
        )

