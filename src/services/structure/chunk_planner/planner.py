# src/services/structure/chunk_planner/planner.py

"""
Phase 10 — Chunk Planner: public facade.

Точка входа для downstream:
    from services.structure.chunk_planner import plan_chunking

Использование:
    from services.structure._pipeline._core_builder import build_file_structure_with_analysis

    from services.structure.chunk_planner import plan_chunking

    analysis = build_file_structure_with_analysis(
        document_id=doc_id,
        elements=elements,
    )
    plan = plan_chunking(analysis)

    # Downstream chunk assembly читает plan:
    # plan.mode_decision.mode
    # plan.mode_decision.token_params
    # plan.mode_decision.drop_technical_fallback_nodes
    # plan.plan_for_segment(segment_id)
"""

from __future__ import annotations

from services.structure.chunk_planner._planner import plan_chunking
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
    TOKENS_MODE_C,
)

__all__ = [
    "ChunkingModeDecision",
    "ChunkingTokenParams",
    "FileChunkPlan",
    "plan_chunking",
    "SegmentChunkPlan",
    "TOKENS_MODE_A",
    "TOKENS_MODE_B",
    "TOKENS_MODE_C",
]

