"""
Compatibility Builder Module (Phase 5).

Отвечает за сборку финального JSON-макета layout_primary.json:
- Преобразование ProjectedElement и CanonicalTable в LayoutPrimaryCompat;
- Формирование плоского списка root elements[];
- Встраивание таблиц как элементов с table_ref и plain-text представлением;
- Установка метаданных analysis_source_kind = 'canonical_filtered_layout_v2';
- Валидация выходной структуры через Pydantic.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.schemas import (
    CanonicalTable,
    LayoutPrimaryCompat,
    LayoutPrimaryCompatValidation,
    ProjectedElement,
)

logger = get_logger(__name__)


class CompatibilityBuilder:
    """
    Сервис сборки обратно-совместимого JSON-макета для downstream-пайплайна.
    """

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
        """
        Собирает и валидирует словарь LayoutPrimaryCompat.

        Возвращает dict, готовый для store.put_json().
        """
        logger.info(
            "Building layout_primary compatibility payload",
            document_id=document_id,
            version_id=document_version_id,
            run_id=run_id,
            target_language=target_language,
        )

        elements: list[ProjectedElement] = list(projection_result.elements)

        # Интеграция таблиц как compatibility-элементов (Вариант B)
        for table in canonical_tables:
            table_text = table.markdown if table.markdown else f"Таблица {table.table_id}"

            # Извлекаем все доступные тексты ячеек, если markdown пуст
            if not table.markdown and table.cells:
                cell_texts = [c.text for c in table.cells if c.text.strip()]
                table_text = "Таблица: " + " | ".join(cell_texts)

            table_element_id = f"{target_language}:table:{table.table_id.replace('table:', '')}"
            table_projected_el = ProjectedElement(
                element_id=table_element_id,
                source_element_ids=[table.table_id],
                text=table_text,
                page=table.page,
                reading_order=10000,  # Таблицы идут в конец страницы или по порядку
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
                projection_method="table_plain_text",
                projection_confidence=1.0,
                is_table=True,
                table_ref=f"canonical:{table.table_id}",
            )
            elements.append(table_projected_el)

        # Сортируем все элементы (текст + таблицы) по страницам и порядку чтения
        elements.sort(key=lambda el: (el.page, el.reading_order))

        # Формируем метаданные для активации canonical bypass в extract_worker
        metadata: dict[str, Any] = {
            "language_filter": {
                "analysis_source_kind": "canonical_filtered_layout_v2",
                "downstream_requires_primary_source": False,
                "target_language": target_language,
            },
            "schema_contract": "layout_primary_compat_v1",
        }

        validation = LayoutPrimaryCompatValidation(
            source_atom_count=projection_result.source_atom_count,
            projected_atom_count=len(elements),
            projected_marker_only_atom_count=projection_result.projected_marker_only_atom_count,
            shared_atoms_included=projection_result.shared_atoms_included,
            mixed_atoms_resolved=projection_result.mixed_atoms_resolved,
            mixed_atoms_unresolved=projection_result.mixed_atoms_unresolved,
            tables_included=len(canonical_tables),
            marker_trace=projection_result.marker_trace,
        )

        compat_model = LayoutPrimaryCompat(
            schema_version="layout_primary_compat_v1",
            document_id=document_id,
            document_version_id=document_version_id,
            run_id=run_id,
            language=target_language,
            source_canonical_layout_ref=source_canonical_layout_ref,
            metadata=metadata,
            elements=elements,
            unresolved_mixed_atoms=projection_result.unresolved_mixed_atoms,
            validation=validation,
        )

        logger.info(
            "LayoutPrimaryCompat payload constructed successfully",
            total_elements=len(elements),
            tables_count=len(canonical_tables),
        )

        return compat_model.model_dump()
