"""
Tests for ChunkCorpusReaderV2 enrichment projection.

Covers:
- _build_enrichment_index: correct index from sidecar
- _load_segment_snapshot: enriched metadata projected onto legal_unit chunks
- graceful degradation: None sidecar → no projection, no error
- invariants: unknown/empty values not overwritten
- non-legal_unit chunks not projected
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2


# ─── _build_enrichment_index ─────────────────────────────────────────────────


class TestBuildEnrichmentIndex:
    def test_returns_empty_dict_for_none(self) -> None:
        result = ChunkCorpusReaderV2._build_enrichment_index(None)
        assert result == {}

    def test_returns_empty_dict_for_non_dict(self) -> None:
        result = ChunkCorpusReaderV2._build_enrichment_index([])  # type: ignore
        assert result == {}

    def test_returns_empty_dict_for_empty_enrichments(self) -> None:
        result = ChunkCorpusReaderV2._build_enrichment_index({"enrichments": []})
        assert result == {}

    def test_applied_status_uses_effective_layer(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:1.1",
                    "status": "applied",
                    "effective": {
                        "clause_function": "definitions",
                        "unit_type": "definition",
                        "topic_tags": ["term"],
                    },
                    "base": {
                        "clause_function": "unknown",
                        "unit_type": "unknown",
                        "topic_tags": [],
                    },
                }
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)

        assert "main_contract:1.1" in result
        entry = result["main_contract:1.1"]
        assert entry["clause_function"] == "definitions"
        assert entry["unit_type"] == "definition"
        assert entry["topic_tags"] == ["term"]
        assert entry["enrichment_status"] == "applied"

    def test_no_change_status_uses_effective_layer(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:1.8",
                    "status": "no_change",
                    "effective": {
                        "clause_function": "definitions",
                        "unit_type": "definition",
                        "topic_tags": [],
                    },
                    "base": {
                        "clause_function": "unknown",
                        "unit_type": "unknown",
                    },
                }
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)

        assert result["main_contract:1.8"]["clause_function"] == "definitions"
        assert result["main_contract:1.8"]["enrichment_status"] == "no_change"

    def test_failed_status_uses_base_layer(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:__preamble__",
                    "status": "failed",
                    "effective": {
                        "clause_function": "unknown",
                        "unit_type": "unknown",
                    },
                    "base": {
                        "clause_function": "unknown",
                        "unit_type": "unknown",
                    },
                }
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)

        assert result["main_contract:__preamble__"]["enrichment_status"] == "failed"
        assert result["main_contract:__preamble__"]["clause_function"] == "unknown"

    def test_skipped_status_uses_base_layer(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:2.1",
                    "status": "skipped",
                    "effective": {
                        "clause_function": "obligations",
                        "unit_type": "obligation",
                    },
                    "base": {
                        "clause_function": "obligations",
                        "unit_type": "obligation",
                        "topic_tags": [],
                    },
                }
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)

        # For skipped: base is used, but base has the same values here
        assert result["main_contract:2.1"]["clause_function"] == "obligations"
        assert result["main_contract:2.1"]["enrichment_status"] == "skipped"

    def test_multiple_units_indexed_correctly(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:1.1",
                    "status": "applied",
                    "effective": {"clause_function": "definitions", "unit_type": "definition"},
                    "base": {},
                },
                {
                    "unit_id": "main_contract:2.1",
                    "status": "no_change",
                    "effective": {"clause_function": "obligations", "unit_type": "obligation"},
                    "base": {},
                },
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)

        assert len(result) == 2
        assert result["main_contract:1.1"]["clause_function"] == "definitions"
        assert result["main_contract:2.1"]["clause_function"] == "obligations"

    def test_item_without_unit_id_skipped(self) -> None:
        sidecar = {
            "enrichments": [
                {"status": "applied", "effective": {"clause_function": "definitions"}},
                {"unit_id": "main_contract:1.1", "status": "applied",
                 "effective": {"clause_function": "definitions"}, "base": {}},
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)
        assert len(result) == 1
        assert "main_contract:1.1" in result

    def test_topic_tags_defaults_to_empty_list_if_not_list(self) -> None:
        sidecar = {
            "enrichments": [
                {
                    "unit_id": "main_contract:1.1",
                    "status": "applied",
                    "effective": {"clause_function": "definitions", "topic_tags": None},
                    "base": {},
                }
            ]
        }
        result = ChunkCorpusReaderV2._build_enrichment_index(sidecar)
        assert result["main_contract:1.1"]["topic_tags"] == []


# ─── Projection in _load_segment_snapshot ────────────────────────────────────


def _make_minimal_reader() -> ChunkCorpusReaderV2:
    """Create a ChunkCorpusReaderV2 with mocked session and artifact store."""
    session = MagicMock()
    store = MagicMock()
    reader = ChunkCorpusReaderV2(session=session, artifact_store=store)
    return reader


def _make_valid_snapshot(
    legal_unit_chunks: list[dict],
    section_chunks: list[dict] | None = None,
) -> dict:
    """Build a minimal valid V2 segment snapshot."""
    return {
        "scope": "segment",
        "schema_version": 2,
        "chunks": {
            "legal_unit": legal_unit_chunks,
            "section": section_chunks or [],
        },
    }


@pytest.mark.asyncio
async def test_projection_applies_clause_function_to_legal_unit_chunk() -> None:
    """Enriched clause_function must be written into legal_unit chunk metadata."""
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[
            {
                "id": "doc123:main_contract:1.8",
                "text": "Стороны означает Покупателя и Продавца.",
                "metadata": {
                    "effective_uid": "main_contract:1.8",
                    "chunk_kind": "legal_unit",
                    "clause_function": "unknown",
                    "unit_type": "unknown",
                },
            }
        ]
    )

    enrichment_index = {
        "main_contract:1.8": {
            "clause_function": "definitions",
            "unit_type": "definition",
            "topic_tags": [],
            "enrichment_status": "no_change",
        }
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index=enrichment_index,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    assert meta["clause_function"] == "definitions"
    assert meta["unit_type"] == "definition"
    assert meta.get("enrichment_projected") is True
    assert meta.get("enrichment_status") == "no_change"


@pytest.mark.asyncio
async def test_projection_does_not_overwrite_with_unknown() -> None:
    """
    If enriched value is 'unknown', existing baseline value must be preserved.
    This invariant prevents degrading good deterministic classification.
    """
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[
            {
                "id": "doc:1.1",
                "text": "Some clause text here.",
                "metadata": {
                    "effective_uid": "main_contract:1.1",
                    "chunk_kind": "legal_unit",
                    "clause_function": "obligations",
                    "unit_type": "obligation",
                },
            }
        ]
    )

    enrichment_index = {
        "main_contract:1.1": {
            "clause_function": "unknown",
            "unit_type": "unknown",
            "topic_tags": [],
            "enrichment_status": "failed",
        }
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index=enrichment_index,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    # Original deterministic values must be preserved
    assert meta["clause_function"] == "obligations"
    assert meta["unit_type"] == "obligation"


@pytest.mark.asyncio
async def test_projection_does_not_apply_to_section_chunks() -> None:
    """Section chunks must not be projected — only legal_unit chunks."""
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[],
        section_chunks=[
            {
                "id": "doc:section:1",
                "text": "Section heading text.",
                "metadata": {
                    "effective_uid": "main_contract:1",
                    "chunk_kind": "section",
                    "clause_function": "unknown",
                },
            }
        ],
    )

    enrichment_index = {
        "main_contract:1": {
            "clause_function": "definitions",
            "unit_type": "definition",
            "topic_tags": [],
            "enrichment_status": "applied",
        }
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"section"},
        enrichment_index=enrichment_index,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    # Section chunk must NOT be projected
    assert meta["clause_function"] == "unknown"
    assert meta.get("enrichment_projected") is None


@pytest.mark.asyncio
async def test_no_projection_when_enrichment_index_is_none() -> None:
    """When enrichment_index is None, chunks are returned unchanged."""
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[
            {
                "id": "doc:1.8",
                "text": "Стороны означает.",
                "metadata": {
                    "effective_uid": "main_contract:1.8",
                    "chunk_kind": "legal_unit",
                    "clause_function": "unknown",
                },
            }
        ]
    )

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index=None,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    assert meta["clause_function"] == "unknown"
    assert meta.get("enrichment_projected") is None


@pytest.mark.asyncio
async def test_no_projection_when_uid_not_in_index() -> None:
    """Chunk whose uid is not in enrichment_index is returned unchanged."""
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[
            {
                "id": "doc:1.9",
                "text": "Some other clause.",
                "metadata": {
                    "effective_uid": "main_contract:1.9",
                    "chunk_kind": "legal_unit",
                    "clause_function": "unknown",
                },
            }
        ]
    )

    enrichment_index = {
        "main_contract:1.8": {  # different uid
            "clause_function": "definitions",
            "unit_type": "definition",
            "topic_tags": [],
            "enrichment_status": "no_change",
        }
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index=enrichment_index,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    assert meta["clause_function"] == "unknown"
    assert meta.get("enrichment_projected") is None


@pytest.mark.asyncio
async def test_topic_tags_projected_when_not_empty() -> None:
    """Non-empty topic_tags from enrichment must be set in chunk metadata."""
    reader = _make_minimal_reader()

    snapshot = _make_valid_snapshot(
        legal_unit_chunks=[
            {
                "id": "doc:2.1",
                "text": "Покупатель обязан оплатить.",
                "metadata": {
                    "effective_uid": "main_contract:2.1",
                    "chunk_kind": "legal_unit",
                    "clause_function": "obligations",
                    "topic_tags": [],
                },
            }
        ]
    )

    enrichment_index = {
        "main_contract:2.1": {
            "clause_function": "obligations",
            "unit_type": "obligation",
            "topic_tags": ["payment", "buyer_obligation"],
            "enrichment_status": "applied",
        }
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index=enrichment_index,
    )

    assert len(result) == 1
    meta = result[0]["metadata"]
    assert meta["topic_tags"] == ["payment", "buyer_obligation"]


@pytest.mark.asyncio
async def test_invalid_snapshot_schema_returns_empty() -> None:
    """Snapshot with wrong schema_version must be rejected."""
    reader = _make_minimal_reader()

    snapshot = {
        "scope": "segment",
        "schema_version": 1,  # wrong version
        "chunks": {"legal_unit": [{"id": "x", "text": "t", "metadata": {}}]},
    }

    reader._load_json_async = AsyncMock(return_value=snapshot)

    import uuid
    result = await reader._load_segment_snapshot(
        doc_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        segment_id="seg-main",
        segment_chunks_ref="s3://bucket/seg.json",
        level_set={"legal_unit"},
        enrichment_index={},
    )

    assert result == []


    