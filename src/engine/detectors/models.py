# src/engine/detectors/models.py

"""
Detection Result Models.

Used by all detectors (Rules, LLM) to return standardized results.
The Check Runner uses these to build final CheckResult records.

Расширенная версия:
- EvidenceChunk и RetrievedChunk несут структурный контекст клаузы:
  path_titles, start_page, end_page, element_ids.
Это позволяет:
  - строить breadcrumbs и навигацию без отдельной metadata-map,
  - прокидывать структурный контекст до HybridDetector / CheckExecutor / UI.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class EvidenceChunk:
    """A piece of evidence found by a detector."""

    # Базовые поля (как было)
    element_id: str              # Element where evidence was found
    text: str                    # The evidence text snippet
    page: int                    # Page number
    clause_uid: str = ""         # Clause that contains this evidence
    bbox: list[float] = field(default_factory=list)
    score: float = 0.0           # Retrieval score (how relevant)

    # Структурный контекст клаузы
    path_titles: List[str] = field(default_factory=list)
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    element_ids: List[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    """Result of a single detector (Rules or LLM)."""

    found: bool                                  # Was the checked condition found?
    evidence_chunks: list[EvidenceChunk] = field(default_factory=list)
    confidence: float = 0.0                      # 0.0 to 1.0
    detector_type: str = "rules"                 # "rules", "llm"
    details: dict[str, Any] = field(default_factory=dict)  # Extra info for debugging


@dataclass
class RetrievedChunk:
    """A text chunk retrieved by the retrieval engine."""

    # Базовые поля для retrieval / подсветки (как было)
    element_id: str
    text: str
    page: int
    clause_uid: str = ""
    bbox: list[float] = field(default_factory=list)

    # Оценки релевантности (как было)
    dense_score: float = 0.0        # Embeddings similarity
    sparse_score: float = 0.0       # BM25 score
    metadata_score: float = 0.0     # Metadata boost
    combined_score: float = 0.0     # Weighted combination

    # Структурный контекст клаузы:
    # - path_titles: "хлебные крошки" от корня до клаузы,
    # - start_page / end_page: диапазон страниц клаузы,
    # - element_ids: все layout-элементы, входящие в эту клаузу.
    path_titles: List[str] = field(default_factory=list)
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    element_ids: List[str] = field(default_factory=list)

    def to_evidence(self) -> EvidenceChunk:
        """Convert to EvidenceChunk, сохраняя структурный контекст."""
        return EvidenceChunk(
            element_id=self.element_id,
            text=self.text,
            page=self.page,
            clause_uid=self.clause_uid,
            bbox=self.bbox,
            score=self.combined_score,
            path_titles=list(self.path_titles or []),
            start_page=self.start_page,
            end_page=self.end_page,
            element_ids=list(self.element_ids or []),
        )
