"""
PII Structural Invariant Tests.

Фиксирует контракт: PII-санитизатор может менять `text`,
но НЕ вправе изменять structural/provenance поля.
"""

from copy import deepcopy

STRUCTURAL_FIELDS = frozenset({
    "element_id",
    "source_element_ids",
    "page",
    "bbox",
    "reading_order",
    "marker",
    "is_marker_only",
    "label",
    "parent_ref",
    "language",
    "needs_review",
})


def _make_sample_layout() -> dict:
    return {
        "schema_version": "layout_primary_compat_v1",
        "document_id": "00000000-0000-0000-0000-000000000001",
        "document_version_id": "00000000-0000-0000-0000-000000000002",
        "run_id": "00000000-0000-0000-0000-000000000003",
        "language": "ru",
        "source_canonical_layout_ref": "s3://bucket/canonical.json",
        "metadata": {},
        "elements": [
            {
                "element_id": "ru:atom:001",
                "source_element_ids": ["atom:001"],
                "text": "Иванов Иван Иванович обязуется выплатить 1 000 000 руб.",
                "page": 1,
                "reading_order": 1,
                "type": "text",
                "label": "paragraph",
                "marker": None,
                "is_marker_only": False,
                "bbox": [72.0, 100.0, 500.0, 120.0],
                "parent_ref": None,
                "language": "ru",
                "needs_review": False,
                "projection_method": "native_language_atom",
            },
            {
                "element_id": "ru:marker:atom:002",
                "source_element_ids": ["atom:002"],
                "text": "",
                "page": 1,
                "reading_order": 2,
                "type": "list_item",
                "label": "list_item",
                "marker": "1.1",
                "is_marker_only": True,
                "bbox": [72.0, 130.0, 90.0, 140.0],
                "parent_ref": None,
                "language": "shared",
                "needs_review": True,
                "projection_method": "preserved_marker_without_target_text",
            },
        ],
    }


def _simulate_pii_sanitization(layout: dict) -> dict:
    result = deepcopy(layout)
    for el in result["elements"]:
        if el.get("text") and "Иванов" in el["text"]:
            el["text"] = el["text"].replace("Иванов Иван Иванович", "[ФИО]")
    return result


class TestPIIInvariant:
    def test_preserves_structural_fields(self):
        original = _make_sample_layout()
        sanitized = _simulate_pii_sanitization(original)
        for orig_el, san_el in zip(original["elements"], sanitized["elements"]):
            for field in STRUCTURAL_FIELDS:
                assert orig_el.get(field) == san_el.get(field), (
                    f"PII broke structural field '{field}'"
                )

    def test_preserves_element_count(self):
        original = _make_sample_layout()
        sanitized = _simulate_pii_sanitization(original)
        assert len(original["elements"]) == len(sanitized["elements"])

    def test_preserves_element_order(self):
        original = _make_sample_layout()
        sanitized = _simulate_pii_sanitization(original)
        for i, (orig, san) in enumerate(
            zip(original["elements"], sanitized["elements"])
        ):
            assert orig["element_id"] == san["element_id"], f"Order broken at {i}"

    def test_preserves_marker_only_elements(self):
        original = _make_sample_layout()
        sanitized = _simulate_pii_sanitization(original)
        orig_markers = [e for e in original["elements"] if e.get("is_marker_only")]
        san_markers = [e for e in sanitized["elements"] if e.get("is_marker_only")]
        assert len(orig_markers) == len(san_markers)
        for om, sm in zip(orig_markers, san_markers):
            assert om["element_id"] == sm["element_id"]
            assert sm["text"] == ""

    def test_text_is_mutated(self):
        original = _make_sample_layout()
        sanitized = _simulate_pii_sanitization(original)
        assert "Иванов" in original["elements"][0]["text"]
        assert "[ФИО]" in sanitized["elements"][0]["text"]
