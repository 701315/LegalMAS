"""
Tests for ChunksPreparer enrichment_sidecar parameter propagation.

Covers:
- enrichment_sidecar is passed through to ChunkCorpusReaderV2.load_segment
- None sidecar → graceful degradation, no error
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.checks.planning.chunks import ChunksPreparer
from engine.checks.planning.scope import ScopeResolver


def _make_preparer() -> ChunksPreparer:
    scope = ScopeResolver(checks_scope=None)
    return ChunksPreparer(scope_resolver=scope)


def _make_mock_doc(doc_id: str = "8dcc255b-4e59-4b20-af70-dea3f3cef89c"):
    import uuid
    doc = MagicMock()
    doc.id = uuid.UUID(doc_id)
    return doc


@pytest.mark.asyncio
async def test_build_safe_chunks_for_segment_passes_sidecar_to_reader() -> None:
    """enrichment_sidecar must reach ChunkCorpusReaderV2.load_segment."""
    preparer = _make_preparer()
    doc = _make_mock_doc()

    sidecar = {"enrichments": []}
    captured_kwargs: dict = {}

    async def _mock_load_segment(**kwargs):
        captured_kwargs.update(kwargs)
        return [
            {
                "id": "chunk1",
                "text": "Some text for retrieval.",
                "metadata": {"effective_uid": "main:1.1", "chunk_kind": "legal_unit"},
            }
        ]

    with patch(
        "engine.content.chunk_snapshot_reader.ChunkCorpusReaderV2.load_segment",
        side_effect=_mock_load_segment,
    ):
        result = await preparer.build_safe_chunks_for_segment(
            session=MagicMock(),
            doc=doc,
            checks=[],
            segment_id="seg-main",
            enrichment_sidecar=sidecar,
        )

    assert captured_kwargs.get("enrichment_sidecar") is sidecar
    assert len(result) == 1


@pytest.mark.asyncio
async def test_build_safe_chunks_for_segment_none_sidecar_no_error() -> None:
    """None sidecar must not raise any exception."""
    preparer = _make_preparer()
    doc = _make_mock_doc()

    async def _mock_load_segment(**kwargs):
        assert kwargs.get("enrichment_sidecar") is None
        return [
            {
                "id": "chunk1",
                "text": "Some legal text.",
                "metadata": {"effective_uid": "main:1.1", "chunk_kind": "legal_unit"},
            }
        ]

    with patch(
        "engine.content.chunk_snapshot_reader.ChunkCorpusReaderV2.load_segment",
        side_effect=_mock_load_segment,
    ):
        result = await preparer.build_safe_chunks_for_segment(
            session=MagicMock(),
            doc=doc,
            checks=[],
            segment_id="seg-main",
            enrichment_sidecar=None,
        )

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_build_safe_chunks_for_segment_empty_segment_id_returns_empty() -> None:
    """Empty segment_id must return empty list without calling reader."""
    preparer = _make_preparer()
    doc = _make_mock_doc()

    with patch(
        "engine.content.chunk_snapshot_reader.ChunkCorpusReaderV2.load_segment",
    ) as mock_reader:
        result = await preparer.build_safe_chunks_for_segment(
            session=MagicMock(),
            doc=doc,
            checks=[],
            segment_id="",
            enrichment_sidecar={"enrichments": []},
        )

    assert result == []
    mock_reader.assert_not_called()


    