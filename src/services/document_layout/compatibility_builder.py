# src/services/document_layout/compatibility_builder.py

r"""
Compatibility Builder Module (Phase 5 / Layer 10 v3).

Отвечает за сборку финального JSON-макета layout_primary.json:
- Интеграция с TableSemanticsProcessor (Layer 7);
- Ячеечная фильтрация таблиц (отбрасывание ячеек чужого языка);
- Построчное Markdown-форматирование таблиц;
- Разворачивание clause-строк таблиц в отдельные элементы (v3.1);
- Сборка простого layout_primary.json для downstream.
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.schemas import (
    CanonicalTable,
    LayoutPrimaryCompat,
    LayoutPrimaryCompatValidation,
    ProjectedElement,
    ProjectedTableRow,
)
from services.document_layout.table_semantics import TableSemanticsProcessor
from services.document_layout.marker_recovery import recover_markers_from_tables

logger = get_logger(__name__)

# Универсальный паттерн clause-маркера (языко-независимый):
# 1.1, 2.1, 10.3.1, (a), (б), а), b), I., IV.
_CLAUSE_MARKER_RE = re.compile(
    r"^\s*("
    r"\d+(?:\.\d+)*\.?"
    r"|\(?\d+\)"
    r"|\(?[a-zA-Zа-яА-Я]\)?"
    r"|[IVXLCDMivxlcdm]+\."
    r")\s*$"
)


def _is_clause_marker_cell(text: str) -> bool:
    """
    Универсальная проверка: является ли содержимое ячейки clause-маркером.
    Работает для любого языка и любого формата нумерации.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 12:
        return False
    return bool(_CLAUSE_MARKER_RE.match(stripped))


def _try_expand_clause_rows(
    table: CanonicalTable,
    rows: list[ProjectedTableRow],
    target_lang: str,
    base_reading_order: int,
) -> tuple[list[ProjectedElement], set[int]]:
    """
    Разворачивает clause-строки таблицы в отдельные текстовые элементы.

    Clause-строка = строка, где первая ячейка содержит короткий маркер (2.1, (a)),
    а вторая ячейка содержит содержательный текст (>10 символов).

    Returns:
        (clause_elements, clause_row_indices)
    """
    clause_elements: list[ProjectedElement] = []
    clause_row_indices: set[int] = set()

    for row in rows:
        cells = sorted(row.cells, key=lambda c: c.col)
        if len(cells) < 2:
            continue

        first_text = cells[0].text.strip()
        second_text = cells[1].text.strip()

        if _is_clause_marker_cell(first_text) and len(second_text) > 10:
            clause_row_indices.add(row.row_index)
            merged_text = f"{first_text} {second_text}".strip()

            clause_el = ProjectedElement(
                element_id=(
                    f"{target_lang}:clause:"
                    f"{table.table_id.replace('table:', '')}:r{row.row_index}"
                ),
                source_element_ids=[table.table_id],
                text=merged_text,
                page=table.page,
                reading_order=base_reading_order + row.row_index,
                reading_order_source="docling_tables_clause_expansion",
                layout_order_confidence="unvalidated",
                type="list_item",
                label="list_item",
                marker=first_text,
                is_marker_only=False,
                bbox=table.bbox,
                parent_ref=None,
                language=target_lang,
                needs_review=False,
                projection_method="clause_table_expansion",
                projection_confidence=0.95,
                is_table=False,
            )
            clause_elements.append(clause_el)

    return clause_elements, clause_row_indices


class CompatibilityBuilder:
    def __init__(self, table_processor: TableSemanticsProcessor | None = None):
        self.table_processor = table_processor or TableSemanticsProcessor()

    def build_layout_primary(
        self,
        projection_result: ProjectionResult,
        canonical_tables: list[CanonicalTable],
        document_id: str,
        document_version_id: str,
        run_id: str,
        target_language: str,
        source_canonical_layout_ref: str,
    ) -> dict[str, Any]:
        target_lang = target_language.lower().strip()
        elements: list[ProjectedElement] = list(projection_result.elements)

        clause_tables_count = 0
        clause_rows_expanded = 0

        for table in canonical_tables:
            table_result = self.table_processor.process_table(table, target_lang)

            table_element_id = (
                f"{target_lang}:table:{table.table_id.replace('table:', '')}"
            )
            table_reading_order = (
                int(table.bbox[1] * 10) if table.bbox else table.page * 1000
            )

            # Попытка разворачивания clause-строк таблицы
            clause_els, clause_indices = _try_expand_clause_rows(
                table, table_result.rows, target_lang, table_reading_order
            )

            if clause_els:
                elements.extend(clause_els)
                clause_tables_count += 1
                clause_rows_expanded += len(clause_els)
            
            # Восстановить маркеры из всех таблиц (включая data tables)
            table_elements = recover_markers_from_tables([table], target_lang)
            if table_elements:
                for el_data in table_elements:
                    elements.append(ProjectedElement(**el_data))
                clause_tables_count += 1
                clause_rows_expanded += len(table_elements)

                # Оставшиеся строки (не clause) сохраняем как таблицу
                remaining_rows = [
                    r for r in table_result.rows
                    if r.row_index not in clause_indices
                ]
                if remaining_rows:
                    remaining_text = "\n".join(
                        r.text for r in remaining_rows if r.text.strip()
                    )
                    if remaining_text.strip():
                        table_projected_el = ProjectedElement(
                            element_id=table_element_id,
                            source_element_ids=[table.table_id],
                            text=remaining_text,
                            page=table.page,
                            reading_order=table_reading_order,
                            reading_order_source="docling_tables",
                            layout_order_confidence="unvalidated",
                            type="table",
                            label="table",
                            marker=None,
                            is_marker_only=False,
                            bbox=table.bbox,
                            parent_ref=None,
                            language="shared",
                            needs_review=False,
                            projection_method=(
                                f"table_filtered_{table_result.topology.value}"
                            ),
                            projection_confidence=1.0,
                            is_table=True,
                            table_ref=f"canonical:{table.table_id}",
                            table_rows=remaining_rows,
                            table_topology=table_result.topology,
                        )
                        elements.append(table_projected_el)
            else:
                # Обычная таблица (без clause-строк) — существующая логика
                table_projected_el = ProjectedElement(
                    element_id=table_element_id,
                    source_element_ids=[table.table_id],
                    text=table_result.markdown_text,
                    page=table.page,
                    reading_order=table_reading_order,
                    reading_order_source="docling_tables",
                    layout_order_confidence="unvalidated",
                    type="table",
                    label="table",
                    marker=None,
                    is_marker_only=False,
                    bbox=table.bbox,
                    parent_ref=None,
                    language="shared",
                    needs_review=False,
                    projection_method=(
                        f"table_filtered_{table_result.topology.value}"
                    ),
                    projection_confidence=1.0,
                    is_table=True,
                    table_ref=f"canonical:{table.table_id}",
                    table_rows=table_result.rows,
                    table_topology=table_result.topology,
                )
                elements.append(table_projected_el)

        # v3.1: Normalize reading_order from physical coordinates.
        # Fixes inverted order when PageRegionSegmenter creates overlapping bands.
        for el in elements:
            if el.bbox is not None:
                el.reading_order = int(el.bbox[1] * 1000 + el.bbox[0])
                el.reading_order_source = "physical_bbox_normalized"

        elements.sort(key=lambda el: (el.page, el.reading_order))

        if clause_rows_expanded > 0:
            logger.info(
                "Clause table expansion completed",
                document_id=document_id,
                clause_tables=clause_tables_count,
                clause_rows_expanded=clause_rows_expanded,
            )

        metadata: dict[str, Any] = {
            "language_filter": {
                "analysis_source_kind": "canonical_filtered_layout_v2",
                "downstream_requires_primary_source": False,
                "target_language": target_lang,
            },
            "schema_contract": "layout_primary_compat_v2",
            "clause_table_expansion": {
                "tables_expanded": clause_tables_count,
                "rows_expanded": clause_rows_expanded,
            },
        }

        validation = LayoutPrimaryCompatValidation(
            source_atom_count=projection_result.source_atom_count,
            projected_atom_count=len(elements),
            projected_marker_only_atom_count=(
                projection_result.projected_marker_only_atom_count
            ),
            shared_atoms_included=projection_result.shared_atoms_included,
            mixed_atoms_resolved=projection_result.mixed_atoms_resolved,
            mixed_atoms_unresolved=projection_result.mixed_atoms_unresolved,
            tables_included=len(canonical_tables),
            marker_trace=projection_result.marker_trace,
        )

        compat_model = LayoutPrimaryCompat(
            schema_version="layout_primary_compat_v2",
            document_id=document_id,
            document_version_id=document_version_id,
            run_id=run_id,
            language=target_lang,
            source_canonical_layout_ref=source_canonical_layout_ref,
            metadata=metadata,
            elements=elements,
            unresolved_mixed_atoms=projection_result.unresolved_mixed_atoms,
            validation=validation,
        )

        return compat_model.model_dump()
