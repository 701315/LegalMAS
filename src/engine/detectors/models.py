"""
Detection Result Models.

Used by all detectors (Rules, LLM) to return standardized results.
The Check Runner uses these to build final CheckResult records.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceChunk:
    """A piece of evidence found by a detector."""

    element_id: str           # Element where evidence was found
    text: str                 # The evidence text snippet
    page: int                 # Page number
    clause_uid: str = ""      # Clause that contains this evidence
    bbox: list[float] = field(default_factory=list)
    score: float = 0.0        # Retrieval score (how relevant)


@dataclass
class DetectionResult:
    """Result of a single detector (Rules or LLM)."""

    found: bool                   # Was the checked condition found?
    evidence_chunks: list[EvidenceChunk] = field(default_factory=list)
    confidence: float = 0.0       # 0.0 to 1.0
    detector_type: str = "rules"  # "rules", "llm"
    details: dict[str, Any] = field(default_factory=dict)  # Extra info for debugging


@dataclass
class RetrievedChunk:
    """A text chunk retrieved by the retrieval engine."""

    element_id: str
    text: str
    page: int
    clause_uid: str = ""
    bbox: list[float] = field(default_factory=list)
    dense_score: float = 0.0     # Embeddings similarity
    sparse_score: float = 0.0    # BM25 score
    metadata_score: float = 0.0  # Metadata boost
    combined_score: float = 0.0  # Weighted combination

    def to_evidence(self) -> EvidenceChunk:
        """Convert to EvidenceChunk."""
        return EvidenceChunk(
            element_id=self.element_id,
            text=self.text,
            page=self.page,
            clause_uid=self.clause_uid,
            bbox=self.bbox,
            score=self.combined_score,
        )
