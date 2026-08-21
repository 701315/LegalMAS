"""Contract tests для Pydantic-схем document_layout v2."""

import pytest
from services.document_layout.schemas import (
    CanonicalAtom,
    LayoutPrimaryCompat,
    ProjectedElement,
)


def _make_atom(**overrides) -> dict:
    base = {
        "element_id": "atom:000001",
        "page": 1,
        "bbox": (72.0, 100.0, 500.0, 120.0),
        "source_reading_order": 1,
        "layout_order": 1,
        "text": "Test paragraph",
        "label": "paragraph",
        "source": {"docling_collection": "texts"},
    }
    base.update(overrides)
    return base


class TestCanonicalAtom:
    def test_valid_atom_parses(self):
        atom = CanonicalAtom(**_make_atom())
        assert atom.element_id == "atom:000001"
        assert atom.bbox == (72.0, 100.0, 500.0, 120.0)

    def test_null_bbox_is_valid(self):
        atom = CanonicalAtom(**_make_atom(bbox=None))
        assert atom.bbox is None

    def test_marker_only_atom(self):
        atom = CanonicalAtom(
            **_make_atom(text="", marker="3.2", is_marker_only=True)
        )
        assert atom.is_marker_only is True
        assert atom.text == ""


class TestProjectedElement:
    def test_fitz_bbox_coordinates(self):
        el = ProjectedElement(
            element_id="ru:atom:001",
            source_element_ids=["atom:001"],
            text="Текст",
            page=1,
            reading_order=1,
            type="text",
            label="paragraph",
            bbox=(72.0, 100.0, 500.0, 120.0),
            language="ru",
            projection_method="native_language_atom",
        )
        assert el.bbox[1] < el.bbox[3], "Fitz: y_top must be < y_bottom"

    def test_null_bbox_is_valid(self):
        el = ProjectedElement(
            element_id="ru:atom:002",
            source_element_ids=["atom:002"],
            text="No bbox",
            page=1,
            reading_order=2,
            type="text",
            label="paragraph",
            bbox=None,
            language="ru",
            projection_method="native_language_atom",
        )
        assert el.bbox is None

    def test_marker_only_element(self):
        el = ProjectedElement(
            element_id="ru:marker:atom:003",
            source_element_ids=["atom:003"],
            text="",
            page=1,
            reading_order=3,
            type="list_item",
            label="list_item",
            marker="3.2",
            is_marker_only=True,
            language="shared",
            needs_review=True,
            projection_method="preserved_marker_without_target_text",
        )
        assert el.text == ""
        assert el.is_marker_only is True
        assert el.needs_review is True


class TestLayoutPrimaryCompat:
    def test_minimal_valid_layout(self):
        layout = LayoutPrimaryCompat(
            document_id="00000000-0000-0000-0000-000000000001",
            document_version_id="00000000-0000-0000-0000-000000000002",
            run_id="00000000-0000-0000-0000-000000000003",
            language="ru",
            source_canonical_layout_ref="s3://bucket/canonical.json",
            elements=[],
        )
        assert layout.schema_version == "layout_primary_compat_v1"
        assert layout.elements == []

    def test_elements_array_is_root_key(self):
        layout = LayoutPrimaryCompat(
            document_id="00000000-0000-0000-0000-000000000001",
            document_version_id="00000000-0000-0000-0000-000000000002",
            run_id="00000000-0000-0000-0000-000000000003",
            language="ru",
            source_canonical_layout_ref="s3://bucket/canonical.json",
            elements=[
                ProjectedElement(
                    element_id="ru:atom:001",
                    source_element_ids=["atom:001"],
                    text="Текст",
                    page=1,
                    reading_order=1,
                    type="text",
                    label="paragraph",
                    language="ru",
                    projection_method="native_language_atom",
                )
            ],
        )
        data = layout.model_dump()
        assert "elements" in data
        assert len(data["elements"]) == 1
