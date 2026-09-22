"""
B5 — _provenance_dict содержит anchor-поля.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from db.repositories.result_repo import _provenance_dict


def _make_cr(**overrides) -> MagicMock:
    cr = MagicMock()
    cr.page = None
    cr.clause_uid = None
    cr.element_id = None
    cr.bbox = None
    cr.segment_id = None
    cr.segment_type = None
    cr.segment_title = None
    cr.segment_order = None
    cr.is_primary_segment = None
    cr.chunk_id = None
    cr.chunk_index = None
    cr.context_trace = None
    cr.primary_anchor_id = None
    cr.primary_anchor_method = None
    cr.primary_anchor_confidence = None
    cr.anchor_stale = False
    for k, v in overrides.items():
        setattr(cr, k, v)
    return cr


def test_provenance_dict_includes_anchor_fields_when_present():
    anchor_id = uuid.uuid4()
    cr = _make_cr(
        primary_anchor_id=anchor_id,
        primary_anchor_method="exact_span",
        primary_anchor_confidence=1.0,
        anchor_stale=False,
    )
    out = _provenance_dict(cr)
    assert out["primary_anchor_id"] == str(anchor_id)
    assert out["primary_anchor_method"] == "exact_span"
    assert out["primary_anchor_confidence"] == 1.0
    assert out["anchor_stale"] is False


def test_provenance_dict_anchor_fields_none_for_legacy():
    cr = _make_cr()
    out = _provenance_dict(cr)
    assert out["primary_anchor_id"] is None
    assert out["primary_anchor_method"] is None
    assert out["primary_anchor_confidence"] is None
    assert out["anchor_stale"] is False


def test_provenance_dict_preserves_existing_fields():
    cr = _make_cr(page=5, clause_uid="main_contract:7.1")
    out = _provenance_dict(cr)
    assert out["page"] == 5
    assert out["clause_uid"] == "main_contract:7.1"
