"""
Pydantic-схемы для Document Layout Pipeline v2.

Три уровня схем:
1. Canonical* — полный multilingual extraction (document-scoped, immutable)
2. Projected* — результат monolingual projection (run-scoped)
3. LayoutPrimaryCompat — финальный JSON для downstream (PII → structure)

Контракт bbox:
- ВСЕ bbox в системе Fitz/PyMuPDF: origin top-left, y растёт вниз.
- Формат: (x0, y0_top, x1, y1_top) где y0_top < y1_top.
- Docling-координаты (origin bottom-left) преобразуются в compatibility_builder.
- bbox может быть None для редких Docling items без provenance — не ошибка.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class ResolutionStatus(str, Enum):
    LANGUAGE_RESOLVING = "LANGUAGE_RESOLVING"
    LANGUAGE_READY = "LANGUAGE_READY"
    LANGUAGE_UNAVAILABLE = "LANGUAGE_UNAVAILABLE"
    LANGUAGE_SELECTION_REQUIRED = "LANGUAGE_SELECTION_REQUIRED"


class MissingTargetLanguagePolicy(str, Enum):
    BLOCK_DOCUMENT_CONTINUE_RUN = "BLOCK_DOCUMENT_CONTINUE_RUN"
    FAIL_RUN_IF_ANY_DOCUMENT_MISSING_LANGUAGE = (
        "FAIL_RUN_IF_ANY_DOCUMENT_MISSING_LANGUAGE"
    )
    FALLBACK_TO_DOCUMENT_LANGUAGE = "FALLBACK_TO_DOCUMENT_LANGUAGE"
    REQUIRE_USER_CONFIRMATION = "REQUIRE_USER_CONFIRMATION"


# ── Language Classification ──────────────────────────────────────────────────


class LanguageEvidence(BaseModel):
    """Доказательная база для классификации языка атома."""

    cyrillic_chars: int = Field(default=0, ge=0)
    latin_chars: int = Field(default=0, ge=0)
    total_letters: int = Field(default=0, ge=0)
    classification_method: str


class LanguageClassification(BaseModel):
    """Результат классификации языка одного атома."""

    language: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: LanguageEvidence


# ── Canonical Layout (document-scoped, immutable) ────────────────────────────


class ElementStyle(BaseModel):
    """Визуальные свойства из PyMuPDF enrichment."""

    font: str | None = None
    font_size: float | None = None
    bold: bool = False
    italic: bool = False
    color: int | None = None
    match_score: float | None = None
    visual_match_status: str = "not_matched"


class CanonicalAtomSource(BaseModel):
    """Провенанс атома в Docling."""

    docling_collection: str
    docling_item_ref: str | None = None


class CanonicalAtom(BaseModel):
    """
    Один текстовый атом из Docling document.texts.
    bbox: в системе Fitz (origin top-left). None допустим.
    """

    element_id: str
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None
    source_reading_order: int
    layout_order: int
    layout_order_confidence: str = "unvalidated"
    text: str
    marker: str | None = None
    is_marker_only: bool = False
    label: str
    parent_ref: str | None = None
    language: str = "shared"
    language_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    language_evidence: LanguageEvidence | None = None
    style: ElementStyle | None = None
    source: CanonicalAtomSource


class CanonicalTableCell(BaseModel):
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    text: str
    language: str = "shared"


class CanonicalTable(BaseModel):
    table_id: str
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None
    num_rows: int = Field(ge=1)
    num_cols: int = Field(ge=1)
    language: str = "shared"
    cells: list[CanonicalTableCell]
    markdown: str
    source: dict[str, Any] = Field(default_factory=dict)


class CanonicalLayoutValidation(BaseModel):
    total_text_atoms: int
    total_tables: int
    marker_count: int
    marker_only_count: int
    language_distribution: dict[str, int]


class CanonicalPage(BaseModel):
    page_number: int = Field(ge=1)
    width: float
    height: float
    atoms: list[CanonicalAtom] = Field(default_factory=list)


class CanonicalLayout(BaseModel):
    """Полный multilingual extraction. Document-scoped, immutable."""

    schema_version: str = "canonical_layout_v1"
    document_id: str
    document_version_id: str
    source_pdf_sha256: str
    page_count: int = Field(ge=1)
    detected_languages: list[str]
    pages: list[CanonicalPage] = Field(default_factory=list)
    tables: list[CanonicalTable] = Field(default_factory=list)
    validation: CanonicalLayoutValidation | None = None


# ── Projected Element (run-scoped) ───────────────────────────────────────────


class ProjectedElement(BaseModel):
    """
    Элемент после monolingual projection.
    Контракт для downstream (structure pipeline):
    - text, page, bbox (Fitz), type (mapped from label)
    - НЕ выдаёт: element_type, segment_id, segment_type, segment_order, scope
    """

    element_id: str
    source_element_ids: list[str]

    text: str
    page: int = Field(ge=1)
    reading_order: int
    reading_order_source: str = "docling_texts"
    layout_order_confidence: str = "unvalidated"

    type: str
    label: str
    marker: str | None = None
    is_marker_only: bool = False

    bbox: tuple[float, float, float, float] | None = None
    parent_ref: str | None = None

    language: str
    needs_review: bool = False
    projection_method: str
    projection_confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    font_size: float | None = None
    bold: bool = False

    is_furniture: bool = False
    is_table: bool = False
    is_heading_candidate: bool = False

    table_ref: str | None = None
    style: ElementStyle | None = None


# ── Layout Primary Compat (run-scoped, downstream artifact) ──────────────────


class UnresolvedMixedAtom(BaseModel):
    element_id: str
    text: str
    language: str = "mixed"
    reason: str


class MarkerTrace(BaseModel):
    projected: int = 0
    unresolved: int = 0
    excluded_with_reason: int = 0


class LayoutPrimaryCompatValidation(BaseModel):
    source_atom_count: int
    projected_atom_count: int
    projected_marker_only_atom_count: int
    shared_atoms_included: int
    mixed_atoms_resolved: int
    mixed_atoms_unresolved: int
    tables_included: int
    marker_trace: MarkerTrace


class LayoutPrimaryCompat(BaseModel):
    """
    Финальный артефакт для downstream (PII → structure).
    Совместим с raw_layout.get("elements", []).
    """

    schema_version: str = "layout_primary_compat_v1"
    document_id: str
    document_version_id: str
    run_id: str
    language: str
    source_canonical_layout_ref: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    elements: list[ProjectedElement] = Field(default_factory=list)
    unresolved_mixed_atoms: list[UnresolvedMixedAtom] = Field(default_factory=list)
    validation: LayoutPrimaryCompatValidation | None = None
