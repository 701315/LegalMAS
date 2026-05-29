# src/services/structure/_heading_scoring/_types.py

"""
Типы данных и статусы процесса скоринга заголовков.

Этот модуль задаёт единый контракт для Phases 2–7 structure pipeline:
- извлечение document‑global structural signals;
- скоринг и классификация heading candidates;
- перенос explainable evidence между фазами;
- explainable structure assessment и quality gating.

Важно:
- сохранена обратная совместимость с текущим HeadingScoreResult;
- новые dataclass‑структуры можно вводить постепенно, не ломая старый код;
- downstream‑фазы не должны заново "угадывать" наличие структуры, если
  upstream уже собрал evidence и assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Literal


# ============================================================================
# Enum‑типы
# ============================================================================

class CandidateStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class HeadingScheme(str, Enum):
    DECIMAL = "decimal"
    ROMAN = "roman"
    APPENDIX = "appendix"
    UNNUMBERED = "unnumbered"
    ALPHABETIC = "alphabetic"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ScopeType(str, Enum):
    MAIN = "main"
    TOC = "toc"
    APPENDIX = "appendix"
    ATTACHMENT = "attachment"
    SIGNATURES = "signatures"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecoveryMode(str, Enum):
    NONE = "none"
    PATCH_MISSING_SUBTREE = "patch_missing_subtree"
    PATCH_APPENDICES = "patch_appendices"
    REBUILD_FROM_HEADINGS = "rebuild_from_headings"
    TECHNICAL_FALLBACK = "technical_fallback"


class QualityGateMode(str, Enum):
    ALLOW_SECTION_CHUNKING = "allow_section_chunking"
    ALLOW_SECTION_CHUNKING_WITH_WARNINGS = "allow_section_chunking_with_warnings"
    ALLOW_HYBRID_CHUNKING = "allow_hybrid_chunking"
    BLOCK_AND_FALLBACK = "block_and_fallback"


class CrossRefKind(str, Enum):
    ITEM = "item"
    CLAUSE = "clause"
    SECTION = "section"
    APPENDIX = "appendix"
    DEFINITION = "definition"
    UNKNOWN = "unknown"


class ReferenceResolutionMethod(str, Enum):
    EXACT_UID = "exact_uid"
    SCOPED_EXACT = "scoped_exact"
    HEADING_MATCH = "heading_match"
    FUZZY = "fuzzy"
    UNRESOLVED = "unresolved"


# ============================================================================
# Phase 2 — локальные артефакты (TOC, numbering, anchors)
# ============================================================================

@dataclass(slots=True)
class HeadingCandidate:
    element_id: str
    text: str
    normalized_text: str
    level_hint: int | None = None
    scheme: HeadingScheme = HeadingScheme.UNKNOWN
    score: float = 0.0
    features: dict[str, float | bool | str | int | None] = field(default_factory=dict)
    numbering: str | None = None
    scope_type: ScopeType = ScopeType.UNKNOWN
    is_toc_entry: bool = False
    page_number: int | None = None
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NumberingSequence:
    scope_type: ScopeType
    scheme: HeadingScheme
    values: list[str] = field(default_factory=list)
    normalized_values: list[str] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)
    is_contiguous: bool = False
    continuity_ratio: float = 0.0
    start_value: str | None = None
    end_value: str | None = None
    gaps: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TocEntry:
    element_id: str
    raw_text: str
    normalized_text: str
    numbering: str | None = None
    page_hint: int | None = None
    matched_heading_element_id: str | None = None
    match_score: float = 0.0


@dataclass(slots=True)
class TocBlock:
    heading_element_id: str | None
    title: str
    page_start: int | None = None
    page_end: int | None = None
    entries: list[TocEntry] = field(default_factory=list)
    confidence: float = 0.0
    detection_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppendixMarker:
    element_id: str
    raw_text: str
    normalized_text: str
    appendix_number: str | None = None
    scope_uid: str | None = None
    marker_kind: Literal[
        "appendix",
        "appendices",
        "annex",
        "annexure",
        "schedule",
        "exhibit",
        "attachment",
        "unknown",
    ] = "unknown"
    page_number: int | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class CrossRefAnchor:
    element_id: str
    raw_text: str
    normalized_text: str
    ref_kind: CrossRefKind = CrossRefKind.UNKNOWN
    target_number: str | None = None
    target_scope_hint: str | None = None
    source_scope_type: ScopeType = ScopeType.UNKNOWN
    page_number: int | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class PageStructureSignals:
    page_number: int
    heading_candidate_ids: list[str] = field(default_factory=list)
    toc_entry_ids: list[str] = field(default_factory=list)
    appendix_marker_ids: list[str] = field(default_factory=list)
    crossref_anchor_ids: list[str] = field(default_factory=list)
    page_top_heading_density: float = 0.0
    numbering_density: float = 0.0
    has_toc_title: bool = False
    has_appendix_marker: bool = False


@dataclass(slots=True)
class GlobalStructureSignals:
    toc_detected: bool = False
    toc_confidence: float = 0.0
    main_section_chain_length: int = 0
    appendix_chain_length: int = 0
    crossref_anchor_count: int = 0
    heading_candidates_count: int = 0
    extraction_quality_score: float = 0.0
    document_quality_signals: dict[str, float | bool | str | int | None] = field(
        default_factory=dict
    )
    notes: list[str] = field(default_factory=list)


# ============================================================================
# Phase 5 — confidence & gate
# ============================================================================

@dataclass(slots=True)
class ConfidenceComponents:
    heading_confidence: float = 0.0
    tree_consistency_confidence: float = 0.0
    appendix_confidence: float = 0.0
    crossref_anchor_confidence: float = 0.0
    layout_quality_confidence: float = 0.0
    overall_confidence_score: float = 0.0


@dataclass(slots=True)
class StructureAssessment:
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    section_count: int = 0
    appendix_count: int = 0
    toc_detected: bool = False
    crossref_anchor_count: int = 0
    numbering_health: dict[str, float] = field(default_factory=dict)
    confidence_components: ConfidenceComponents = field(
        default_factory=ConfidenceComponents
    )
    quality_gate_mode: QualityGateMode = QualityGateMode.BLOCK_AND_FALLBACK
    quality_gate_reasons: list[str] = field(default_factory=list)
    recovery_mode: RecoveryMode = RecoveryMode.NONE
    assessment_notes: list[str] = field(default_factory=list)

    @property
    def allows_section_chunking(self) -> bool:
        return self.quality_gate_mode in {
            QualityGateMode.ALLOW_SECTION_CHUNKING,
            QualityGateMode.ALLOW_SECTION_CHUNKING_WITH_WARNINGS,
        }

    @property
    def allows_any_semantic_chunking(self) -> bool:
        return self.quality_gate_mode != QualityGateMode.BLOCK_AND_FALLBACK

    @property
    def allows_hybrid_chunking(self) -> bool:
        return self.quality_gate_mode == QualityGateMode.ALLOW_HYBRID_CHUNKING

    @property
    def is_recoverable(self) -> bool:
        return self.recovery_mode != RecoveryMode.NONE

    @property
    def usable_for_structure(self) -> bool:
        return self.allows_any_semantic_chunking or (
            self.confidence == ConfidenceLevel.MEDIUM and not self.degraded
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Удобная сериализация для артефактов Phase 5/6/7.
        """
        data = asdict(self)
        data["confidence"] = self.confidence.value
        data["quality_gate_mode"] = self.quality_gate_mode.value
        data["recovery_mode"] = self.recovery_mode.value
        data["confidence_components"]["overall_confidence_level"] = self.confidence.value
        return data


# ============================================================================
# Phase 2–7 shared — evidence bundle
# ============================================================================

@dataclass(slots=True)
class StructureEvidenceBundle:
    heading_candidates: list[HeadingCandidate] = field(default_factory=list)
    numbering_sequences: list[NumberingSequence] = field(default_factory=list)
    toc_blocks: list[TocBlock] = field(default_factory=list)
    appendix_markers: list[AppendixMarker] = field(default_factory=list)
    crossref_anchors: list[CrossRefAnchor] = field(default_factory=list)
    page_signals: list[PageStructureSignals] = field(default_factory=list)
    global_signals: GlobalStructureSignals = field(default_factory=GlobalStructureSignals)

    def get_main_decimal_sequence(self) -> NumberingSequence | None:
        for sequence in self.numbering_sequences:
            if (
                sequence.scope_type == ScopeType.MAIN
                and sequence.scheme == HeadingScheme.DECIMAL
            ):
                return sequence
        return None

    def get_appendix_sequence(self) -> NumberingSequence | None:
        for sequence in self.numbering_sequences:
            if sequence.scheme == HeadingScheme.APPENDIX:
                return sequence
        return None

    @property
    def toc_detected(self) -> bool:
        return self.global_signals.toc_detected or bool(self.toc_blocks)

    @property
    def heading_candidates_count(self) -> int:
        return len(self.heading_candidates)

    @property
    def crossref_anchor_count(self) -> int:
        return len(self.crossref_anchors)

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализация для structure_signals.json.
        """
        return {
            "toc_detected": self.toc_detected,
            "main_section_chain": (
                self.get_main_decimal_sequence().normalized_values
                if self.get_main_decimal_sequence()
                else []
            ),
            "appendix_chain": (
                self.get_appendix_sequence().normalized_values
                if self.get_appendix_sequence()
                else []
            ),
            "heading_candidates_count": self.heading_candidates_count,
            "crossref_anchor_count": self.crossref_anchor_count,
            "global_signals": asdict(self.global_signals),
        }


# ============================================================================
# HeadingScoreResult — результат Phase 2 scoring
# ============================================================================

@dataclass(slots=True)
class HeadingScoreResult:
    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    toc_match_score: float = 0.0
    toc_match_type: str | None = None
    semantic_element_type: str | None = None
    continuity_bonus: float = 0.0
    legal_negative_signals: list[str] = field(default_factory=list)
    structural_evidence: dict[str, Any] = field(default_factory=dict)

    # enriched fields (опциональные, заполняются scorer'ом/обработчиками)
    normalized_text: str | None = None
    numbering: str | None = None
    level_hint: int | None = None
    scope_type: ScopeType = ScopeType.UNKNOWN
    scheme: HeadingScheme = HeadingScheme.UNKNOWN
    candidate_confidence: float = 0.0
    is_toc_entry: bool = False
    is_appendix_marker: bool = False
    quality_flags: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.status == CandidateStatus.ACCEPTED

    @property
    def is_rejected(self) -> bool:
        return self.status == CandidateStatus.REJECTED

    @property
    def is_ambiguous(self) -> bool:
        return self.status == CandidateStatus.AMBIGUOUS

    @property
    def has_structural_confirmation(self) -> bool:
        return bool((self.structural_evidence or {}).get("structural_confirmation"))

    @property
    def has_strong_structural_confirmation(self) -> bool:
        return bool((self.structural_evidence or {}).get("strong_structural_confirmation"))

    @property
    def is_recoverable(self) -> bool:
        if self.is_accepted:
            return True
        if self.is_ambiguous and (
            self.has_structural_confirmation
            or self.score >= 0.60
            or "recoverable" in (self.primary_reason or "")
        ):
            return True
        return False

    @property
    def should_materialize(self) -> bool:
        return self.is_accepted and not self.is_toc_entry

    @property
    def should_materialize_for_recovery(self) -> bool:
        return (
            not self.is_toc_entry
            and (
                self.is_accepted
                or (
                    self.is_ambiguous
                    and self.is_recoverable
                    and not self.is_definition_like_only
                )
            )
        )

    @property
    def is_definition_like_only(self) -> bool:
        negatives = set(self.reject_reasons or []) | set(self.legal_negative_signals or [])
        return (
            "definition_like_title" in negatives
            or "definition_item_by_legal_rules" in negatives
        )

    @property
    def effective_confidence_level(self) -> ConfidenceLevel:
        if self.score >= 0.82 and self.is_accepted:
            return ConfidenceLevel.HIGH
        if self.score >= 0.60 and (self.is_accepted or self.is_recoverable):
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def to_heading_candidate(
        self,
        *,
        element_id: str,
        text: str,
        page_number: int | None = None,
    ) -> HeadingCandidate:
        """
        Преобразовать результат скоринга в HeadingCandidate для
        StructureEvidenceBundle (Phase 2 → Phase 3+).
        """
        normalized_text = self.normalized_text or text.strip()
        features: dict[str, float | bool | str | int | None] = dict(
            self.structural_evidence or {}
        )
        features.update(
            {
                "primary_reason": self.primary_reason,
                "toc_match_score": self.toc_match_score,
                "toc_match_type": self.toc_match_type,
                "semantic_element_type": self.semantic_element_type,
                "continuity_bonus": self.continuity_bonus,
                "candidate_confidence": self.candidate_confidence,
                "is_appendix_marker": self.is_appendix_marker,
                "candidate_status": self.status.value,
                "effective_confidence_level": self.effective_confidence_level.value,
                "is_recoverable": self.is_recoverable,
                "should_materialize_for_recovery": self.should_materialize_for_recovery,
            }
        )
        if self.legal_negative_signals:
            features["legal_negative_signals"] = list(self.legal_negative_signals)
        if self.quality_flags:
            features["quality_flags"] = list(self.quality_flags)

        return HeadingCandidate(
            element_id=element_id,
            text=text,
            normalized_text=normalized_text,
            level_hint=self.level_hint,
            scheme=self.scheme,
            score=self.score,
            features=features,
            numbering=self.numbering,
            scope_type=self.scope_type,
            is_toc_entry=self.is_toc_entry,
            page_number=page_number,
            evidence_refs=list(self.evidence_refs),
        )


# ============================================================================
# Cross‑ref stubs / resolved links (Phase 7)
# ============================================================================

@dataclass(slots=True)
class CrossRefStub:
    source_unit_id: str
    raw_text: str
    ref_kind: CrossRefKind = CrossRefKind.UNKNOWN
    target_number: str | None = None
    target_scope_hint: str | None = None
    confidence: float = 0.0


@dataclass(slots=True)
class ResolvedCrossRef:
    source_unit_id: str
    raw_text: str
    ref_kind: CrossRefKind
    target_unit_id: str | None
    resolution_method: ReferenceResolutionMethod = ReferenceResolutionMethod.UNRESOLVED
    confidence: float = 0.0
    unresolved_reason: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.target_unit_id is not None


__all__ = [
    "AppendixMarker",
    "CandidateStatus",
    "ConfidenceComponents",
    "ConfidenceLevel",
    "CrossRefAnchor",
    "CrossRefKind",
    "CrossRefStub",
    "GlobalStructureSignals",
    "HeadingCandidate",
    "HeadingScheme",
    "HeadingScoreResult",
    "NumberingSequence",
    "PageStructureSignals",
    "QualityGateMode",
    "RecoveryMode",
    "ReferenceResolutionMethod",
    "ResolvedCrossRef",
    "ScopeType",
    "StructureAssessment",
    "StructureEvidenceBundle",
    "TocBlock",
    "TocEntry",
]


