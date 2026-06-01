# src/services/structure/models/_result.py

"""
Composition result model для build_file_structure().

FileStructureResult — агрегированный результат file-level structure builder,
включающий primary tree, segment trees и file graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._graph import FileGraph
from ._normalization import _norm_str
from ._tree import ClauseTree
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.structure.coherence._types import CrossSegmentCoherenceResult

@dataclass
class FileStructureResult:
    """
    Итоговый результат build_file_structure().

    Содержит primary tree, список segment trees и file graph.
    Инварианты:
    - количество segment_trees == количество file_graph.segments
    - segment_id каждого tree присутствует в file_graph.segments
    - primary_tree.segment_id == file_graph.primary_segment_id
    """

    primary_tree: ClauseTree
    segment_trees: list[ClauseTree]
    file_graph: FileGraph
    coherence_result: "CrossSegmentCoherenceResult | None" = None  # Phase 13.7

    def __post_init__(self) -> None:
        if not isinstance(self.primary_tree, ClauseTree):
            raise ValueError("FileStructureResult.primary_tree must be ClauseTree")
        if not isinstance(self.file_graph, FileGraph):
            raise ValueError("FileStructureResult.file_graph must be FileGraph")
        if not isinstance(self.segment_trees, list):
            raise ValueError("FileStructureResult.segment_trees must be list[ClauseTree]")
        for idx, tree in enumerate(self.segment_trees):
            if not isinstance(tree, ClauseTree):
                raise ValueError(f"FileStructureResult.segment_trees[{idx}] must be ClauseTree")

        graph_segments = self.file_graph.segments or []

        if len(self.segment_trees) != len(graph_segments):
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_trees count ({len(self.segment_trees)}) != "
                f"file_graph.segments count ({len(graph_segments)})"
            )

        graph_ids = {str(getattr(segment, "segment_id", "") or "") for segment in graph_segments}
        tree_ids = {str(tree.segment_id or "") for tree in self.segment_trees}

        missing_in_trees = graph_ids - tree_ids
        extra_in_trees = tree_ids - graph_ids

        if missing_in_trees or extra_in_trees:
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_ids mismatch between file_graph.segments and segment_trees. "
                f"missing_in_trees={missing_in_trees}, "
                f"extra_in_trees={extra_in_trees}"
            )

        if self.file_graph.primary_segment_id:
            if self.primary_tree.segment_id != self.file_graph.primary_segment_id:
                raise ValueError(
                    "FileStructureResult invariant violated: "
                    "primary_tree.segment_id must match file_graph.primary_segment_id"
                )

        for tree in self.segment_trees:
            if tree.document_id != self.file_graph.document_id:
                raise ValueError(
                    f"FileStructureResult invariant violated: "
                    f"tree.document_id={tree.document_id!r} != "
                    f"file_graph.document_id={self.file_graph.document_id!r}"
                )

    @property
    def primary_segment_id(self) -> str | None:
        """ID primary segment."""
        return self.file_graph.primary_segment_id

    @property
    def segment_count(self) -> int:
        """Количество segment trees."""
        return len(self.segment_trees)

    def get_tree_for_segment(self, segment_id: str) -> ClauseTree | None:
        """Найти segment tree по segment_id или вернуть None."""
        normalized_segment_id = _norm_str(segment_id)
        if not normalized_segment_id:
            return None
        return next(
            (tree for tree in self.segment_trees if tree.segment_id == normalized_segment_id),
            None,
        )
