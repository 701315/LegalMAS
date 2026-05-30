# src/services/structure/heading_builder.py

"""
Построение списка heading candidates и structure evidence из layout-элементов документа.
Публичный фасад.
"""

from __future__ import annotations

from ._heading_builder._core import (
    Phase2Result,
    build_heading_candidates,
    build_structure_evidence_bundle,
    collect_scored_heading_candidates,
    filter_heading_sequence,
    run_phase2,
)
from ._heading_builder._ranking import _candidate_priority_tuple

__all__ = [
    # Canonical Phase 2 entry point (новый, рекомендуемый)
    "run_phase2",
    "Phase2Result",
    # Backward-compatible adapters (сохранены для существующих call sites)
    "build_heading_candidates",
    "build_structure_evidence_bundle",
    # Утилиты
    "filter_heading_sequence",
    "collect_scored_heading_candidates",
    "_candidate_priority_tuple",
]

