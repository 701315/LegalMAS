# src/services/structure/heading_builder.py

"""
Построение списка heading candidates и structure evidence из layout-элементов документа.
Публичный фасад.
"""

from __future__ import annotations

from ._heading_builder._core import (
    build_heading_candidates,
    build_structure_evidence_bundle,
    collect_scored_heading_candidates,
    filter_heading_sequence,
)
from ._heading_builder._ranking import _candidate_priority_tuple

__all__ = [
    "build_heading_candidates",
    "build_structure_evidence_bundle",
    "filter_heading_sequence",
    "collect_scored_heading_candidates",
    "_candidate_priority_tuple",
]

