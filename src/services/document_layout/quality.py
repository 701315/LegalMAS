"""
Quality Gates Module (Phase 6).

Реализует 3 рубежа валидации качества артефактов:
1. validate_canonical_layout  -> проверка полноты и целостности CanonicalLayout;
2. validate_projection        -> проверка моноязычной проекции и отсутствия утечек;
3. validate_compatibility     -> проверка структуры layout_primary перед сохранением.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.schemas import CanonicalLayout, LayoutPrimaryCompat

logger = get_logger(__name__)


@dataclass(slots=True)
class QualityResult:
    """Результат проверки гейта качества."""

    passed: bool
    quarantine: bool = False
    reason_code: str | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def validate_canonical_layout(canonical: CanonicalLayout) -> QualityResult:
    """
    Gate 1: Валидация канонического многоязычного макета.
    """
    total_atoms = sum(len(page.atoms) for page in canonical.pages)

    if total_atoms == 0:
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="CANONICAL_EXTRACTION_EMPTY",
            message="Canonical extraction returned 0 text atoms",
            details={"total_pages": canonical.page_count, "total_atoms": 0},
        )

    element_ids: set[str] = set()
    for page in canonical.pages:
        if page.page_number < 1:
            return QualityResult(
                passed=False,
                quarantine=True,
                reason_code="INVALID_PAGE_NUMBER",
                message=f"Invalid page number {page.page_number}",
            )
        for atom in page.atoms:
            if atom.element_id in element_ids:
                return QualityResult(
                    passed=False,
                    quarantine=True,
                    reason_code="DUPLICATE_CANONICAL_ELEMENT_ID",
                    message=f"Duplicate element_id: {atom.element_id}",
                    details={"duplicate_id": atom.element_id},
                )
            element_ids.add(atom.element_id)

    return QualityResult(
        passed=True,
        details={
            "total_atoms": total_atoms,
            "total_tables": len(canonical.tables),
            "detected_languages": canonical.detected_languages,
        },
    )


def validate_projection(
    canonical: CanonicalLayout,
    projection: ProjectionResult,
    target_language: str,
) -> QualityResult:
    """
    Gate 2: Валидация моноязычной проекции.
    """
    target_lang = target_language.lower().strip()

    if projection.projected_atom_count == 0:
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="TARGET_LANGUAGE_NOT_MATERIALLY_PRESENT",
            message=f"Target language '{target_lang}' not materially present (0 atoms projected)",
            details={"target_language": target_lang, "source_atoms": projection.source_atom_count},
        )

    # 1. Проверка на отсутствие утечек противоположного языка (structural invariant - first priority)
    for el in projection.elements:
        if el.language not in (target_lang, "shared", "mixed") and not el.is_marker_only:
            return QualityResult(
                passed=False,
                quarantine=True,
                reason_code="OPPOSITE_LANGUAGE_LEAKAGE",
                message=(
                    f"Opposite language atom '{el.language}' leaked into "
                    f"'{target_lang}' projection: {el.element_id}"
                ),
                details={"leaked_element_id": el.element_id, "language": el.language},
            )

    # 2. Проверка минимальной доли целевого языка
    native_target_count = sum(
        1 for el in projection.elements if el.language == target_lang and not el.is_marker_only
    )
    target_ratio = native_target_count / max(projection.source_atom_count, 1)

    if target_ratio < layout_config.min_target_language_ratio:
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="TARGET_LANGUAGE_RATIO_TOO_LOW",
            message=(
                f"Target language ratio {target_ratio:.3f} is below "
                f"threshold {layout_config.min_target_language_ratio}"
            ),
            details={
                "target_ratio": round(target_ratio, 3),
                "threshold": layout_config.min_target_language_ratio,
                "target_count": native_target_count,
            },
        )

    # 3. Проверка уникальности element_id
    element_ids: set[str] = set()
    for el in projection.elements:
        if el.element_id in element_ids:
            return QualityResult(
                passed=False,
                quarantine=True,
                reason_code="DUPLICATE_PROJECTED_ELEMENT_ID",
                message=f"Duplicate element_id in projection: {el.element_id}",
            )
        element_ids.add(el.element_id)

    # 4. Проверка падения количества атомов
    drop_ratio = 1.0 - (projection.projected_atom_count / max(projection.source_atom_count, 1))
    if drop_ratio > layout_config.max_atom_count_drop_ratio:
        logger.warning(
            "High atom count drop during projection",
            drop_ratio=round(drop_ratio, 3),
            threshold=layout_config.max_atom_count_drop_ratio,
        )

    return QualityResult(
        passed=True,
        details={
            "target_language": target_lang,
            "projected_atoms": projection.projected_atom_count,
            "marker_only_atoms": projection.projected_marker_only_atom_count,
            "target_ratio": round(target_ratio, 3),
            "drop_ratio": round(drop_ratio, 3),
        },
    )


def validate_compatibility(layout_dict: dict[str, Any]) -> QualityResult:
    """
    Gate 3: Валидация структуры compatibility JSON перед отправкой downstream.
    """
    elements = layout_dict.get("elements")
    if not isinstance(elements, list):
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="MISSING_ELEMENTS_ROOT_KEY",
            message="Root layout dictionary has no 'elements' list",
        )

    if not layout_dict.get("schema_version"):
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="MISSING_SCHEMA_VERSION",
            message="Missing 'schema_version' in layout dictionary",
        )

    # Проверка обязательных полей контракта L1
    required_l1 = ("element_id", "text", "page", "reading_order", "label")
    for idx, el in enumerate(elements):
        if not isinstance(el, dict):
            return QualityResult(
                passed=False,
                quarantine=True,
                reason_code="NON_DICT_ELEMENT_IN_ARRAY",
                message=f"Element at index {idx} is not a dictionary",
            )
        for req_field in required_l1:
            if req_field not in el or el[req_field] is None:
                return QualityResult(
                    passed=False,
                    quarantine=True,
                    reason_code="MISSING_L1_REQUIRED_FIELD",
                    message=f"Element {el.get('element_id', idx)} missing required field '{req_field}'",
                )

    # Валидация Pydantic-схемы
    try:
        LayoutPrimaryCompat.model_validate(layout_dict)
    except Exception as exc:
        return QualityResult(
            passed=False,
            quarantine=True,
            reason_code="PYDANTIC_COMPAT_VALIDATION_FAILED",
            message=f"Pydantic schema validation failed: {exc}",
        )

    return QualityResult(passed=True, details={"elements_count": len(elements)})
