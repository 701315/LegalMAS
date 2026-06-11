"""
Tests for enrichment_loader.
Uses mock ArtifactStore — no real MinIO dependency.
"""
from unittest.mock import MagicMock

import pytest

from engine.checks.enrichment_loader import (
    _extract_clause_functions,
    _extract_topic_tags,
    _extract_units_from_snapshot,
    load_enrichment_context_for_segment,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_segment(
    segment_id="seg-1",
    segment_type="contract",
    segment_title="Main Contract",
    is_primary=True,
    enrichment_ref="s3://bucket/enrichment.json",
):
    seg = MagicMock()
    seg.segment_id = segment_id
    seg.segment_type = segment_type
    seg.segment_title = segment_title
    seg.is_primary = is_primary
    seg.segment_meta = (
        {"legal_units_enrichment_ref": enrichment_ref}
        if enrichment_ref
        else {}
    )
    return seg


def _make_store(snapshot=None, raises=None):
    store = MagicMock()
    if raises:
        store.get_json.side_effect = raises
    else:
        store.get_json.return_value = snapshot
    return store


# ── Unit: _extract_clause_functions ──────────────────────────────────────────


def test_extract_clause_functions_basic():
    units = [
        {"clause_function": "Confidentiality"},
        {"clause_function": "assignment"},
        {"clause_function": None},
        {},
        "not_a_dict",
    ]
    result = _extract_clause_functions(units)
    assert result == frozenset({"confidentiality", "assignment"})


def test_extract_clause_functions_empty():
    assert _extract_clause_functions([]) == frozenset()


def test_extract_clause_functions_all_null():
    units = [{"clause_function": None}, {"clause_function": ""}]
    assert _extract_clause_functions(units) == frozenset()


# ── Unit: _extract_topic_tags ────────────────────────────────────────────────


def test_extract_topic_tags_basic():
    units = [
        {"topic_tags": ["GDPR", "Data Protection"]},
        {"topic_tags": ["assignment"]},
        {"topic_tags": None},
        {},
    ]
    result = _extract_topic_tags(units)
    assert "gdpr" in result
    assert "data protection" in result
    assert "assignment" in result


def test_extract_topic_tags_empty():
    assert _extract_topic_tags([]) == frozenset()


# ── Unit: _extract_units_from_snapshot ───────────────────────────────────────


def test_extract_units_dict_format():
    snapshot = {"units": [{"clause_function": "confidentiality"}]}
    units = _extract_units_from_snapshot(snapshot)
    assert len(units) == 1
    assert units[0]["clause_function"] == "confidentiality"


def test_extract_units_list_format():
    snapshot = [{"clause_function": "assignment"}, {"clause_function": "liability"}]
    units = _extract_units_from_snapshot(snapshot)
    assert len(units) == 2


def test_extract_units_empty_dict():
    assert _extract_units_from_snapshot({}) == []


def test_extract_units_none():
    assert _extract_units_from_snapshot(None) == []


def test_extract_units_filters_non_dicts():
    snapshot = {"units": [{"clause_function": "ok"}, "bad_item", 42, None]}
    units = _extract_units_from_snapshot(snapshot)
    assert len(units) == 1


# ── Integration: load_enrichment_context_for_segment ─────────────────────────


def test_load_success():
    snapshot = {
        "units": [
            {"clause_function": "confidentiality", "topic_tags": ["privacy", "NDA"]},
            {"clause_function": "assignment", "topic_tags": ["transfer"]},
        ]
    }
    ctx = load_enrichment_context_for_segment(
        document_id="doc-1",
        segment=_make_segment(),
        artifact_store=_make_store(snapshot),
    )
    assert ctx.enrichment_available is True
    assert "confidentiality" in ctx.clause_functions
    assert "assignment" in ctx.clause_functions
    assert "privacy" in ctx.topic_tags
    assert "nda" in ctx.topic_tags
    assert ctx.raw_unit_count == 2
    assert ctx.segment_type == "contract"
    assert ctx.segment_id == "seg-1"


def test_load_no_enrichment_ref():
    seg = _make_segment(enrichment_ref=None)
    store = MagicMock()

    ctx = load_enrichment_context_for_segment(
        document_id="doc-1",
        segment=seg,
        artifact_store=store,
    )

    assert ctx.enrichment_available is False
    assert ctx.clause_functions == frozenset()
    store.get_json.assert_not_called()


def test_load_store_raises():
    ctx = load_enrichment_context_for_segment(
        document_id="doc-1",
        segment=_make_segment(),
        artifact_store=_make_store(raises=Exception("connection refused")),
    )
    assert ctx.enrichment_available is False
    assert ctx.clause_functions == frozenset()


def test_load_segment_type_preserved_when_unavailable():
    """Segment ORM info is preserved even when enrichment fails."""
    seg = _make_segment(enrichment_ref=None, segment_type="appendix", is_primary=False)
    ctx = load_enrichment_context_for_segment(
        document_id="doc-1",
        segment=seg,
        artifact_store=MagicMock(),
    )
    assert ctx.enrichment_available is False
    assert ctx.segment_type == "appendix"
    assert ctx.is_primary_segment is False


def test_load_empty_units():
    snapshot = {"units": []}
    ctx = load_enrichment_context_for_segment(
        document_id="doc-1",
        segment=_make_segment(),
        artifact_store=_make_store(snapshot),
    )
    assert ctx.enrichment_available is True
    assert ctx.clause_functions == frozenset()
    assert ctx.raw_unit_count == 0


def test_load_never_raises_on_corrupt_snapshot():
    """Even on completely unexpected snapshot shape, no exception propagates."""
    corrupt_snapshots = [
        "just a string",
        42,
        None,
        {"units": "not_a_list"},
        {"wrong_key": []},
    ]
    for bad in corrupt_snapshots:
        ctx = load_enrichment_context_for_segment(
            document_id="doc-1",
            segment=_make_segment(),
            artifact_store=_make_store(bad),
        )
        assert ctx.enrichment_available is True or ctx.enrichment_available is False
        # Main assertion: no exception raised


        