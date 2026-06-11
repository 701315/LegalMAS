# src/engine/checks/semantic_context.py

"""
Semantic enrichment context for checks pipeline.

Immutable value object carrying legal-unit semantic signals
from enrichment artifacts into checks execution.

Design principles:
- Pure data container: no DB, no MinIO, no async.
- All fields optional: absence = graceful fallback to base behaviour.
- Frozen dataclass: safe to pass through async call chains.
- Universal: language/doc-type/format agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticEnrichmentContext:
    """
    Semantic signals derived from legal-unit enrichment artifacts.

    Carried from check_runner through executor into retrieval scoring,
    prompt augmentation, and confidence calibration.

    Fields:
        document_id:          UUID string of the document.
        segment_id:           Logical segment identifier (None for single-doc).
        segment_type:         Segment type label (contract/appendix/annex/...).
        segment_title:        Human-readable segment title.
        is_primary_segment:   Whether this is the primary logical document.
        clause_functions:     Set of clause functions present in this segment
                              (confidentiality/assignment/governing_law/...).
        topic_tags:           Set of topic tags across all enriched units.
        enrichment_available: True if enrichment artifact was loaded successfully.
        raw_unit_count:       Number of enriched units in artifact (diagnostic).
    """

    document_id: str
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    is_primary_segment: bool | None = None
    clause_functions: frozenset[str] = field(default_factory=frozenset)
    topic_tags: frozenset[str] = field(default_factory=frozenset)
    enrichment_available: bool = False
    raw_unit_count: int = 0

    @classmethod
    def unavailable(
        cls,
        document_id: str,
        segment_id: str | None = None,
        segment_type: str | None = None,
        segment_title: str | None = None,
        is_primary_segment: bool | None = None,
    ) -> "SemanticEnrichmentContext":
        """
        Build a context with enrichment_available=False.

        Use when enrichment artifact is absent or failed to load.
        Pipeline degrades gracefully: retrieval and prompts work as before.
        """
        return cls(
            document_id=document_id,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            is_primary_segment=is_primary_segment,
            clause_functions=frozenset(),
            topic_tags=frozenset(),
            enrichment_available=False,
            raw_unit_count=0,
        )

    def has_clause_function(self, function_name: str) -> bool:
        """Check if a clause function is present in this segment's enrichment."""
        return function_name.lower().strip() in self.clause_functions

    def has_any_clause_function(self, function_names: list[str]) -> bool:
        """Check if any of the given clause functions is present."""
        normalized = {f.lower().strip() for f in function_names if f and f.strip()}
        return bool(normalized & self.clause_functions)

    def to_prompt_block(self) -> str | None:
        """
        Build a compact structural context block for LLM prompts.

        Returns None if no structural info is available.
        Kept short intentionally: structural preamble should help, not bloat.
        """
        if (
            not self.enrichment_available
            and not self.segment_type
            and not self.segment_title
        ):
            return None

        lines: list[str] = []

        if self.segment_title:
            lines.append(f"Segment: {self.segment_title}")

        if self.segment_type:
            lines.append(f"Type: {self.segment_type}")

        if self.is_primary_segment is not None:
            lines.append(f"Primary: {'yes' if self.is_primary_segment else 'no'}")

        if self.clause_functions:
            lines.append(
                f"Clause functions: {', '.join(sorted(self.clause_functions))}"
            )

        if not lines:
            return None

        inner = "\n".join(lines)
        return f"<document_structure>\n{inner}\n</document_structure>"
    


    