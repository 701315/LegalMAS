"""
Monolingual Projector Module (Phase 4).

Отвечает за формирование одноязычной проекции из канонических атомов:
- Фильтрация по target_language + shared;
- Safe-split для mixed-атомов (по ' / ', ' — ', '\n');
- Сохранение маркеров без утечки противоположного языка (marker-only elements);
- 100% трассируемость маркеров (MarkerTrace);
- Маппинг label -> type через layout_config.label_to_raw_type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.language_classifier import classify_text
from services.document_layout.schemas import (
    CanonicalAtom,
    MarkerTrace,
    ProjectedElement,
    UnresolvedMixedAtom,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class ProjectionResult:
    """Результат работы моноязычного проектора."""

    elements: list[ProjectedElement] = field(default_factory=list)
    unresolved_mixed_atoms: list[UnresolvedMixedAtom] = field(default_factory=list)
    marker_trace: MarkerTrace = field(default_factory=MarkerTrace)
    source_atom_count: int = 0
    projected_atom_count: int = 0
    projected_marker_only_atom_count: int = 0
    shared_atoms_included: int = 0
    mixed_atoms_resolved: int = 0
    mixed_atoms_unresolved: int = 0


def _try_safe_split(
    text: str,
    target_language: str,
) -> tuple[str | None, str]:
    """
    Пытается безопасно разделить смешанный текст на части по шаблонам safe_split_patterns.
    Возвращает (target_text_part | None, reason).
    """
    for pattern_cfg in layout_config.safe_split_patterns:
        separator = pattern_cfg.get("separator")
        if not separator or separator not in text:
            continue

        parts = [p.strip() for p in text.split(separator) if p.strip()]
        if len(parts) >= 2:
            for part in parts:
                classification = classify_text(part)
                if classification.language == target_language:
                    return part, "safe_split_successful"

    return None, "no_matching_safe_split_pattern"


class MonolingualProjector:
    """
    Сервис формирования одноязычной проекции документа.
    """

    def project(
        self,
        atoms: list[CanonicalAtom],
        target_language: str,
    ) -> ProjectionResult:
        """
        Проецирует список канонических атомов на указанный целевой язык.
        """
        target_lang = target_language.lower().strip()
        result = ProjectionResult(source_atom_count=len(atoms))

        if not atoms:
            return result

        logger.info(
            "Starting monolingual projection",
            target_language=target_lang,
            total_source_atoms=len(atoms),
        )

        projected_elements: list[ProjectedElement] = []
        unresolved_mixed: list[UnresolvedMixedAtom] = []

        # Множество маркеров, уже представленных в целевой проекции
        projected_markers_set: set[str] = set()

        # Список атомов противоположного языка с маркерами для второго прохода
        opposite_language_marker_atoms: list[CanonicalAtom] = []

        for idx, atom in enumerate(atoms):
            raw_type = layout_config.label_to_raw_type.get(atom.label, "text")
            font_size = atom.style.font_size if atom.style else None
            bold = atom.style.bold if atom.style else False

            # ── 1. Нативный атом целевого языка ──────────────────────────────
            if atom.language == target_lang:
                el_id = f"{target_lang}:{atom.element_id}"
                projected_el = ProjectedElement(
                    element_id=el_id,
                    source_element_ids=[atom.element_id],
                    text=atom.text,
                    page=atom.page,
                    reading_order=atom.source_reading_order,
                    reading_order_source="docling_texts",
                    layout_order_confidence=atom.layout_order_confidence,
                    type=raw_type,
                    label=atom.label,
                    marker=atom.marker,
                    is_marker_only=atom.is_marker_only,
                    bbox=atom.bbox,
                    parent_ref=atom.parent_ref,
                    language=target_lang,
                    needs_review=False,
                    projection_method="native_language_atom",
                    projection_confidence=atom.language_confidence,
                    font_size=font_size,
                    bold=bold,
                    style=atom.style,
                )
                projected_elements.append(projected_el)
                if atom.marker:
                    projected_markers_set.add(atom.marker)
                    result.marker_trace.projected += 1

            # ── 2. Shared атом (числа, формулы, нейтральные маркеры) ──────────
            elif atom.language == "shared":
                el_id = f"{target_lang}:shared:{atom.element_id}"
                projected_el = ProjectedElement(
                    element_id=el_id,
                    source_element_ids=[atom.element_id],
                    text=atom.text,
                    page=atom.page,
                    reading_order=atom.source_reading_order,
                    reading_order_source="docling_texts",
                    layout_order_confidence=atom.layout_order_confidence,
                    type=raw_type,
                    label=atom.label,
                    marker=atom.marker,
                    is_marker_only=atom.is_marker_only,
                    bbox=atom.bbox,
                    parent_ref=atom.parent_ref,
                    language="shared",
                    needs_review=atom.is_marker_only,
                    projection_method="shared_atom",
                    projection_confidence=1.0,
                    font_size=font_size,
                    bold=bold,
                    style=atom.style,
                )
                projected_elements.append(projected_el)
                result.shared_atoms_included += 1
                if atom.marker:
                    projected_markers_set.add(atom.marker)
                    result.marker_trace.projected += 1

            # ── 3. Mixed атом (двуязычный текст) ──────────────────────────────
            elif atom.language == "mixed":
                split_text, reason = _try_safe_split(atom.text, target_lang)

                if split_text:
                    # Успешное разделение: извлекаем только целевую часть
                    el_id = f"{target_lang}:split:{atom.element_id}"
                    projected_el = ProjectedElement(
                        element_id=el_id,
                        source_element_ids=[atom.element_id],
                        text=split_text,
                        page=atom.page,
                        reading_order=atom.source_reading_order,
                        reading_order_source="docling_texts",
                        layout_order_confidence=atom.layout_order_confidence,
                        type=raw_type,
                        label=atom.label,
                        marker=atom.marker,
                        is_marker_only=False,
                        bbox=atom.bbox,
                        parent_ref=atom.parent_ref,
                        language=target_lang,
                        needs_review=False,
                        projection_method="safe_split_mixed",
                        projection_confidence=0.90,
                        font_size=font_size,
                        bold=bold,
                        style=atom.style,
                    )
                    projected_elements.append(projected_el)
                    result.mixed_atoms_resolved += 1
                    if atom.marker:
                        projected_markers_set.add(atom.marker)
                        result.marker_trace.projected += 1
                else:
                    # Не удалось разделить безопасно -> включаем целиком с needs_review
                    el_id = f"{target_lang}:mixed:{atom.element_id}"
                    projected_el = ProjectedElement(
                        element_id=el_id,
                        source_element_ids=[atom.element_id],
                        text=atom.text,
                        page=atom.page,
                        reading_order=atom.source_reading_order,
                        reading_order_source="docling_texts",
                        layout_order_confidence=atom.layout_order_confidence,
                        type=raw_type,
                        label=atom.label,
                        marker=atom.marker,
                        is_marker_only=False,
                        bbox=atom.bbox,
                        parent_ref=atom.parent_ref,
                        language="mixed",
                        needs_review=True,
                        projection_method="unresolved_mixed",
                        projection_confidence=0.50,
                        font_size=font_size,
                        bold=bold,
                        style=atom.style,
                    )
                    projected_elements.append(projected_el)
                    result.mixed_atoms_unresolved += 1
                    unresolved_mixed.append(
                        UnresolvedMixedAtom(
                            element_id=atom.element_id,
                            text=atom.text,
                            language="mixed",
                            reason=reason,
                        )
                    )
                    if atom.marker:
                        result.marker_trace.unresolved += 1

            # ── 4. Атом противоположного языка ───────────────────────────────
            else:
                if atom.marker:
                    opposite_language_marker_atoms.append(atom)
                # Обычный текст без маркеров исключается из проекции

        # ── 5. Marker Preservation для противоположного языка ────────────────
        marker_only_count = 0
        for opp_atom in opposite_language_marker_atoms:
            m = opp_atom.marker
            if m and m not in projected_markers_set:
                # Маркер отсутствует в целевой проекции -> создаем marker-only элемент
                marker_el_id = f"{target_lang}:marker:{opp_atom.element_id}"
                marker_el = ProjectedElement(
                    element_id=marker_el_id,
                    source_element_ids=[opp_atom.element_id],
                    text="",  # Текст строго пустой (без утечки foreign text)
                    page=opp_atom.page,
                    reading_order=opp_atom.source_reading_order,
                    reading_order_source="docling_texts",
                    layout_order_confidence=opp_atom.layout_order_confidence,
                    type="list_item",
                    label=opp_atom.label,
                    marker=m,
                    is_marker_only=True,
                    bbox=opp_atom.bbox,
                    parent_ref=opp_atom.parent_ref,
                    language="shared",
                    needs_review=True,
                    projection_method="preserved_marker_without_target_text",
                    projection_confidence=1.0,
                    font_size=None,
                    bold=False,
                    style=None,
                )
                projected_elements.append(marker_el)
                projected_markers_set.add(m)
                result.marker_trace.projected += 1
                marker_only_count += 1
            else:
                # Маркер уже был представлен в целевой проекции
                result.marker_trace.excluded_with_reason += 1

        # Сортируем результирующие элементы по странице и порядку чтения
        projected_elements.sort(key=lambda el: (el.page, el.reading_order))

        result.elements = projected_elements
        result.unresolved_mixed_atoms = unresolved_mixed
        result.projected_atom_count = len(projected_elements)
        result.projected_marker_only_atom_count = marker_only_count

        logger.info(
            "Monolingual projection completed",
            target_language=target_lang,
            projected_atoms=result.projected_atom_count,
            marker_only_atoms=marker_only_count,
            unresolved_mixed=result.mixed_atoms_unresolved,
        )

        return result
