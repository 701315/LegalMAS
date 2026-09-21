# tests/unit/engine/checks/test_executor_provenance_identity.py

"""
Unit tests for CheckExecutor._extract_primary_context_provenance.

B0.2 verification (from PLAN_DETECTION_AND_ANCHORS.md):
- element_id must be a layout UUID (e.g. "ru:node:3:0004"), not a
  retrieval chunk id ("{doc_id}:{effective_uid}").
- chunk_id must be canonical "{doc_id}:{kind}:{effective_uid}:{idx}".
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from engine.checks.executor import CheckExecutor
from engine.detectors.models import RetrievedChunk


def _make_retrieved_chunk(**overrides) -> RetrievedChunk:
    """Build a minimal RetrievedChunk for provenance tests."""
    defaults = dict(
        element_id="rc-element-id",
        text="sample text",
        page=1,
        clause_uid="main_contract:1.1",
        bbox=[],
        dense_score=0.0,
        sparse_score=0.0,
        metadata_score=0.0,
        combined_score=0.9,
        path_titles=[],
        start_page=1,
        end_page=1,
        element_ids=[],
    )
    defaults.update(overrides)
    return RetrievedChunk(**defaults)


def test_element_id_uses_layout_uuid_from_metadata_element_ids():
    """element_id должен браться из meta['element_ids'][0], не из c['id']."""
    ctx = {
        "id": "36414c0d-bea8-4673-aa87-6fc86e2998eb:main_contract:7.3.2",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:7.3.2",
            "element_ids": ["ru:node:6:0012", "ru:node:6:0013"],
            "start_page": 6,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["element_id"] == "ru:node:6:0012", (
        f"expected layout UUID 'ru:node:6:0012', got {prov['element_id']!r}"
    )
    assert prov["element_id"] != ctx["id"], (
        "element_id must not be the compound retrieval chunk id"
    )


def test_element_id_falls_back_to_metadata_element_id_when_element_ids_empty():
    """Если element_ids пуст, берём meta['element_id']."""
    ctx = {
        "id": "compound-id",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:7.3.2",
            "element_ids": [],
            "element_id": "ru:node:6:0099",
            "start_page": 6,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["element_id"] == "ru:node:6:0099"


def test_element_id_is_none_when_no_layout_uuid_available():
    """Если ни element_ids, ни element_id нет — None, не compound id."""
    ctx = {
        "id": "36414c0d-bea8-4673-aa87-6fc86e2998eb:main_contract:7.3.2",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:7.3.2",
            "element_ids": [],
            "start_page": 6,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["element_id"] is None, (
        f"expected None, got {prov['element_id']!r}. "
        "compound id must not leak into element_id."
    )


def test_chunk_id_uses_fragment_id_from_metadata():
    """chunk_id должен браться из meta['fragment_id'] (canonical form)."""
    doc_id = uuid.uuid4()
    ctx = {
        "id": "some-retrieval-id",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:7.3.2",
            "element_ids": ["ru:node:6:0012"],
            "fragment_id": f"{doc_id}:subclause:main_contract:7.3.2:0",
            "start_page": 6,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["chunk_id"] == f"{doc_id}:subclause:main_contract:7.3.2:0"
    assert ":subclause:" in prov["chunk_id"]
    # chunk_id must not be the same as element_id
    assert prov["chunk_id"] != prov["element_id"]


def test_chunk_id_falls_back_to_metadata_chunk_id():
    """Если fragment_id нет, берём meta['chunk_id']."""
    ctx = {
        "id": "some-retrieval-id",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:1.1",
            "element_ids": ["ru:node:3:0004"],
            "chunk_id": "legacy-chunk-id-123",
            "start_page": 3,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["chunk_id"] == "legacy-chunk-id-123"


def test_chunk_id_falls_back_to_c_id_when_nothing_else_available():
    """Если ни fragment_id, ни chunk_id, ни rc.chunk_id нет — берём c['id']."""
    ctx = {
        "id": "36414c0d-bea8-4673-aa87-6fc86e2998eb:main_contract:7.3.2",
        "text": "some text",
        "metadata": {
            "effective_uid": "main_contract:7.3.2",
            "element_ids": ["ru:node:6:0012"],
            "start_page": 6,
        },
    }
    rc = _make_retrieved_chunk()

    prov = CheckExecutor._extract_primary_context_provenance([ctx], [rc])

    assert prov["chunk_id"] == ctx["id"]


    