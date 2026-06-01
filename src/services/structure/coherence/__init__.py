# src/services/structure/coherence/__init__.py

"""Phase 13.7 — Cross-Segment Coherence public API."""

from services.structure.coherence._resolver import CrossSegmentCoherenceResolver
from services.structure.coherence._types import (
    CoherenceLink,
    CrossSegmentCoherenceResult,
)

__all__ = [
    "CrossSegmentCoherenceResolver",
    "CoherenceLink",
    "CrossSegmentCoherenceResult",
]

