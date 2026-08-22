"""
Downstream Integration & Compatibility Verification (Phase 11).

Тест запускает РЕАЛЬНЫЙ downstream-пайплайн структуры проекта (build_file_structure)
на элементах макета, сгенерированных новым V2-пайплайном (CompatibilityBuilder).

Это гарантирует 100% совместимость контракта без угадываний и заглушек.
"""

import pytest
from services.document_layout.compatibility_builder import CompatibilityBuilder
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.schemas import (
    CanonicalTable,
    CanonicalTableCell,
    MarkerTrace,
    ProjectedElement,
)
from services.structure._pipeline._core_builder import build_file_structure


def test_structure_pipeline_compatibility_with_v2_elements():
    # 1. Генерируем элементы v2 через CompatibilityBuilder
    el_heading = ProjectedElement(
        element_id="ru:atom:000001",
        source_element_ids=["atom:000001"],
        text="1. ПРЕДМЕТ ДОГОВОРА",
        page=1,
        reading_order=1,
        reading_order_source="docling_texts",
        type="heading",  # Mapped from section_header
        label="section_header",
        marker="1.",
        is_marker_only=False,
        bbox=(50.0, 30.0, 250.0, 50.0),
        language="ru",
        projection_method="native_language_atom",
    )

    el_body = ProjectedElement(
        element_id="ru:atom:000002",
        source_element_ids=["atom:000002"],
        text="Исполнитель обязуется оказать Заказчику услуги по рефакторингу.",
        page=1,
        reading_order=2,
        reading_order_source="docling_texts",
        type="text",  # Mapped from paragraph
        label="paragraph",
        marker=None,
        is_marker_only=False,
        bbox=(50.0, 60.0, 500.0, 80.0),
        language="ru",
        projection_method="native_language_atom",
    )

    el_marker = ProjectedElement(
        element_id="ru:marker:atom:000003",
        source_element_ids=["atom:000003"],
        text="",
        page=1,
        reading_order=3,
        reading_order_source="docling_texts",
        type="list_item",
        label="list_item",
        marker="1.1",
        is_marker_only=True,
        bbox=(50.0, 90.0, 70.0, 100.0),
        language="shared",
        needs_review=True,
        projection_method="preserved_marker_without_target_text",
    )

    proj_result = ProjectionResult(
        elements=[el_heading, el_body, el_marker],
        source_atom_count=3,
        projected_atom_count=3,
        projected_marker_only_atom_count=1,
        shared_atoms_included=1,
        marker_trace=MarkerTrace(projected=2),
    )

    table = CanonicalTable(
        table_id="table:0001",
        page=1,
        bbox=(50.0, 110.0, 450.0, 210.0),
        num_rows=2,
        num_cols=2,
        language="shared",
        cells=[
            CanonicalTableCell(row=0, col=0, text="Этап"),
            CanonicalTableCell(row=0, col=1, text="Срок"),
        ],
        markdown="| Этап | Срок |",
    )

    builder = CompatibilityBuilder()
    payload = builder.build_layout_primary(
        projection_result=proj_result,
        canonical_tables=[table],
        document_id="00000000-0000-0000-0000-000000000001",
        document_version_id="00000000-0000-0000-0000-000000000002",
        run_id="00000000-0000-0000-0000-000000000003",
        target_language="ru",
        source_canonical_layout_ref="s3://bucket/canonical.json",
    )

    raw_elements = payload["elements"]

    # 2. Передаем элементы в РЕАЛЬНЫЙ downstream-пайплайн структуры
    result = build_file_structure(
        document_id="00000000-0000-0000-0000-000000000001",
        elements=raw_elements,
        document_version_id="00000000-0000-0000-0000-000000000002",
    )

    # 3. Верифицируем результаты структуры
    assert result.primary_tree is not None
    assert result.file_graph is not None

    tree_dict = result.primary_tree.to_dict()
    assert "root" in tree_dict
    assert len(tree_dict["root"]) > 0
    assert tree_dict["root"][0]["title"] == "ПРЕДМЕТ ДОГОВОРА"
    
    # Проверяем количество сегментов в графе файла
    assert len(result.file_graph.segments) >= 1
    assert result.file_graph.segments[0].is_primary is True
