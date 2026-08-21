r"""
Compatibility Builder Module (Phase 5 / Layer 10 v3).

Отвечает за сборку финального JSON-макета layout_primary.json:
- Интеграция с TableSemanticsProcessor (Layer 7);
- Ячеечная фильтрация таблиц (отбрасывание ячеек чужого языка);
- Построчное Markdown-форматирование таблиц;
- Сборка простого layout_primary.json для downstream.
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
from services.document_layout.table_semantics import TableSemanticsProcessor

logger = get_logger(__name__)


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

        # Интеграция таблиц с ячеечной фильтрацией через TableSemanticsProcessor (Layer 7)
        for table in canonical_tables:
            table_text, topology = self.table_processor.process_table(table, target_lang)

            table_element_id = f"{target_lang}:table:{table.table_id.replace('table:', '')}"
            table_projected_el = ProjectedElement(
                element_id=table_element_id,
                source_element_ids=[table.table_id],
                text=table_text,
                page=table.page,
                reading_order=10000,
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
                projection_method=f"table_filtered_{topology.value}",
                projection_confidence=1.0,
                is_table=True,
                table_ref=f"canonical:{table.table_id}",
            )
            elements.append(table_projected_el)

        elements.sort(key=lambda el: (el.page, el.reading_order))

        metadata: dict[str, Any] = {
            "language_filter": {
                "analysis_source_kind": "canonical_filtered_layout_v2",
                "downstream_requires_primary_source": False,
                "target_language": target_lang,
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
            language=target_lang,
            source_canonical_layout_ref=source_canonical_layout_ref,
            metadata=metadata,
            elements=elements,
            unresolved_mixed_atoms=projection_result.unresolved_mixed_atoms,
            validation=validation,
        )

        return compat_model.model_dump()
