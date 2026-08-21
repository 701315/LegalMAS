"""
Pydantic-схемы для Document Layout Pipeline v3.

Три уровня схем:
1. Canonical* — полный multilingual extraction (document-scoped, immutable)
2. Projected* — результат monolingual projection (run-scoped)
3. LayoutPrimaryCompat — финальный JSON для downstream (PII → structure)

Дополнительные типы v3 (Layered Architecture):
- PageRegion / PageRegionType — сегментация страницы по геометрии
- StructuralNodeCandidate — составной узел (marker + bbox + hierarchy_path)
- TableTopologyType — тип многоязычной таблицы
- ProjectionMode — режим работы проектора
- QuarantineEntry / QuarantineReason — учёт неопределённого контента

Контракт bbox:
- ВСЕ bbox в системе Fitz/PyMuPDF: origin top-left, y растёт вниз.
- Формат: (x0, y0_top, x1, y1_top) где y0_top < y1_top.
- bbox может быть None для редких Docling items без provenance — не ошибка.

Универсальность:
- Никаких хардкод-языковых констант.
- Все типы работают для любой пары языков и любой верстки.
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


class PageRegionType(str, Enum):
    """Тип региона страницы, определяется через height-gating геометрии."""
    COLUMN = "column"                    # высокая текстовая колонка (>= column_min_height_ratio)
    FULL_WIDTH = "full_width"            # полноширинный блок (заголовок, абзац)
    GRID_BLOCK = "grid_block"            # короткий блок (титульный блок сторон, подписи)


class TableTopologyType(str, Enum):
    """
    Тип многоязычной таблицы, определяется статистически 
    по распределению языков в столбцах/строках/ячейках.
    """
    PARALLEL_COLUMN = "parallel_column"       # столбцы разделены по языку (оглавление EN|RU)
    MIXED_ROW = "mixed_row"                   # язык — атрибут значения строки
    INLINE_CELL = "inline_cell"               # склейка языков внутри одной ячейки через разделитель
    HEADER_ONLY_BILINGUAL = "header_only"     # двуязычны только заголовки
    MONOLINGUAL = "monolingual"               # одноязычная таблица
    UNKNOWN = "unknown"                       # не удалось классифицировать


class ProjectionMode(str, Enum):
    """
    Режим работы monolingual_projector.
    Формализация trade-off между 'нулевой утечкой' и 'сохранением контента'.
    """
    STRICT = "strict_projection"              # production default: сомнительное в quarantine
    LOSSLESS_REVIEW = "lossless_review"       # параллельный артефакт для аудита
    AUTO_ACCEPT = "auto_accept"               # компромисс: split только при высокой confidence


class QuarantineReason(str, Enum):
    """Причина, по которой элемент попал в quarantine."""
    LOW_ALIGNMENT_CONFIDENCE = "low_alignment_confidence"
    AMBIGUOUS_SPLIT = "ambiguous_split"
    UNRESOLVED_MIXED_SCRIPT = "unresolved_mixed_script"
    TABLE_STRUCTURE_UNCERTAIN = "table_structure_uncertain"
    UNRESOLVED_TABLE_TOPOLOGY = "unresolved_table_topology"
    ORPHAN_MARKER_WITHOUT_TEXT = "orphan_marker_without_text"


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


# ── Layered Architecture v3: Geometry Layer ──────────────────────────────────


class PageRegion(BaseModel):
    """
    Регион страницы, определённый на основе геометрического анализа.
    
    Универсально: работает для любого числа колонок и любых версток.
    """
    region_id: str
    region_type: PageRegionType
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    column_index: int | None = None           # если region_type == COLUMN
    atom_ids: list[str] = Field(default_factory=list)


# ── Layered Architecture v3: Structural Layer ────────────────────────────────


class StructuralNodeCandidate(BaseModel):
    """
    Составной узел документа для parallel alignment.
    
    Ключ для дедупликации — не marker в изоляции, а составной объект:
    marker + bbox + page + region_id + hierarchy_path.
    Это устраняет ложные совпадения повторяющихся маркеров 
    в разных разделах документа.
    """
    node_id: str
    marker: str | None
    bbox: tuple[float, float, float, float] | None
    page: int = Field(ge=1)
    region_id: str | None = None
    hierarchy_path: list[str] = Field(default_factory=list)
    source_atom_ids: list[str] = Field(default_factory=list)
    language: str
    text: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ── Layered Architecture v3: Quarantine ──────────────────────────────────────


class QuarantineEntry(BaseModel):
    """
    Элемент, попавший в quarantine из-за низкой confidence.
    
    Хранится в параллельном потоке layout_primary.quarantined_elements[]
    для аудита юристом, но НЕ попадает в основной поток elements[]
    в режиме strict_projection.
    """
    element_id: str
    source_atom_ids: list[str] = Field(default_factory=list)
    reason: QuarantineReason
    original_text: str
    detected_language: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_alternatives: list[str] = Field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    page: int | None = None


# ── Projected Element (run-scoped) ───────────────────────────────────────────


class ProjectedElement(BaseModel):
    """
    Элемент после monolingual projection.
    Контракт для downstream (structure pipeline).
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
    
    # v3: связь с исходным регионом страницы
    region_id: str | None = None
    hierarchy_path: list[str] = Field(default_factory=list)


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
    deduplicated: int = 0                     # v3: сколько маркеров-дублей отфильтровано


class LayoutPrimaryCompatValidation(BaseModel):
    source_atom_count: int
    projected_atom_count: int
    projected_marker_only_atom_count: int
    shared_atoms_included: int
    mixed_atoms_resolved: int
    mixed_atoms_unresolved: int
    tables_included: int
    marker_trace: MarkerTrace
    
    # v3: quality metrics
    quarantined_atoms_count: int = 0
    quality_scores: dict[str, float] = Field(default_factory=dict)


class LayoutPrimaryCompat(BaseModel):
    """
    Финальный артефакт для downstream (PII → structure).
    Совместим с raw_layout.get("elements", []).
    
    v3: добавлены quarantined_elements[] для аудита.
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
    
    # v3: quarantine поток для аудита
    quarantined_elements: list[QuarantineEntry] = Field(default_factory=list)
    projection_mode: ProjectionMode = ProjectionMode.STRICT
