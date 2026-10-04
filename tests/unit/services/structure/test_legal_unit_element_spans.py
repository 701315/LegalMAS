"""Тест: element_spans генерируется в LegalUnit и пробрасывается в retrieval metadata."""
import uuid as _uuid

from services.structure.legal_unit_models import (
    LegalUnit,
    LegalUnitsSnapshot,
)
from services.structure.legal_unit_retrieval import (
    build_retrieval_units_from_legal_units,
)


def _make_unit_with_spans():
    return LegalUnit(
        unit_id="main_contract:S",
        raw_uid="S",
        scope="main_contract",
        title="ДОГОВОР",
        level=1,
        own_text="ДОГОВОР\n\nМежду",
        exact_text="ДОГОВОР\n\nМежду",
        retrieval_text="ДОГОВОР\n\nМежду",
        own_element_ids=["el_1", "el_2"],
        element_spans=[
            ["el_1", 1, 0, 7],
            ["el_2", 2, 9, 14],
        ],
    )


def test_legal_unit_has_element_spans():
    u = _make_unit_with_spans()
    assert len(u.element_spans) == 2
    assert u.element_spans[0] == ["el_1", 1, 0, 7]


def test_legal_unit_to_dict_has_element_spans():
    u = _make_unit_with_spans()
    d = u.to_dict()
    assert "element_spans" in d
    assert len(d["element_spans"]) == 2


def test_legal_unit_from_dict_preserves_element_spans():
    u = _make_unit_with_spans()
    d = u.to_dict()
    u2 = LegalUnit.from_dict(d)
    assert len(u2.element_spans) == 2
    assert u2.element_spans[0] == ["el_1", 1, 0, 7]


def test_retrieval_metadata_has_element_spans():
    u = _make_unit_with_spans()
    snapshot = LegalUnitsSnapshot(
        document_id="d1",
        document_version_id="v1",
        segment_id="seg1",
        segment_type="contract",
        segment_order=0,
        is_primary_segment=True,
        units=[u],
    )
    chunks = build_retrieval_units_from_legal_units(
        snapshot=snapshot, doc_id=_uuid.uuid4(),
    )
    assert len(chunks) >= 1
    meta = chunks[0]["metadata"]
    assert "element_spans" in meta
    assert meta["element_spans"] == [["el_1", 1, 0, 7], ["el_2", 2, 9, 14]]
