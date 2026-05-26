import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from engine.content.chunk_canonicalization import (
    build_sized_chunks_from_leaf,
    ensure_clause_metadata,
)
from engine.content.document_content_service import DocumentContentService


pytestmark = pytest.mark.asyncio


@pytest.fixture
def doc_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def valid_clause_chunks() -> list[dict[str, Any]]:
    return [
        {
            "id": "clause_1",
            "text": "This is a valid clause with proper identity.",
            "metadata": {
                "effective_uid": "main:1.1",
                "raw_uid": "1.1",
                "scope": "main",
                "chunk_kind": "clause",
                "level": 2,
                "title": "Section One",
                "path_titles": ["Introduction", "Section One"],
                "start_page": 1,
                "end_page": 1,
                "element_ids": ["elem_1", "elem_2"],
                "segment_id": "seg_001",
                "segment_type": "primary",
                "segment_title": "Main Body",
                "language_filter": {
                    "target_language": "en",
                    "degraded": False,
                },
            },
        },
        {
            "id": "clause_2",
            "text": "Another valid clause with all required fields.",
            "metadata": {
                "effective_uid": "main:1.2",
                "raw_uid": "1.2",
                "scope": "main",
                "chunk_kind": "clause",
                "level": 2,
                "title": "Section Two",
                "path_titles": ["Introduction", "Section Two"],
                "start_page": 2,
                "end_page": 2,
                "element_ids": ["elem_3"],
                "segment_id": "seg_001",
                "segment_type": "primary",
                "range_end_reason": "section_break",
            },
        },
    ]


@pytest.fixture
def clause_chunks_with_broken() -> list[dict[str, Any]]:
    return [
        {
            "id": "clause_valid",
            "text": "Valid clause.",
            "metadata": {
                "effective_uid": "appendix:2.1",
                "raw_uid": "2.1",
                "scope": "appendix",
                "chunk_kind": "clause",
                "level": 1,
                "title": "Valid Clause",
            },
        },
        {
            "id": "clause_broken",
            "text": "Broken clause without effective_uid.",
            "metadata": {
                "raw_uid": "2.2",
                "scope": "appendix",
                "chunk_kind": "clause",
                "level": 1,
                "title": "Broken Clause",
            },
        },
    ]


@pytest.fixture
def snapshot_clause_chunks() -> list[dict[str, Any]]:
    return [
        {
            "id": "snapshot_clause_1",
            "text": "Clause text from snapshot one.",
            "metadata": {
                "effective_uid": "main:1.1",
                "raw_uid": "1.1",
                "scope": "main",
                "chunk_kind": "clause",
                "level": 2,
                "title": "Section One",
                "path_titles": ["Intro", "Section One"],
                "start_page": 1,
                "end_page": 1,
                "element_ids": ["e1", "e2"],
                "segment_id": "seg_001",
                "segment_type": "primary",
            },
        },
        {
            "id": "snapshot_clause_broken",
            "text": "Broken snapshot chunk.",
            "metadata": {
                "raw_uid": "1.9",
                "scope": "main",
                "chunk_kind": "clause",
                "level": 2,
                "title": "Broken",
            },
        },
    ]


def _make_version(doc_id: uuid.UUID, *, manifest_ref: str | None = "s3://bucket/chunks-manifest.json"):
    class Version:
        def __init__(self):
            self.id = uuid.uuid4()
            self.document_id = doc_id
            self.chunks_manifest_v2_ref = manifest_ref
            self.clause_tree_ref = None
            self.layout_primary_ref = None
            self.layout_primary_sanitized_ref = None

    return Version()


def _make_service(mocker, version):
    session = AsyncMock()

    mocker.patch(
        "engine.content.document_content_service.DocumentVersionRepository",
        return_value=AsyncMock(
            get_latest=AsyncMock(return_value=version),
            get_by_id=AsyncMock(return_value=version),
        ),
    )
    mocker.patch(
        "engine.content.document_content_service.DocumentRepository",
        return_value=AsyncMock(),
    )

    return DocumentContentService(session=session)


async def test_clause_chunks_require_effective_uid(
    doc_id: uuid.UUID,
    clause_chunks_with_broken: list[dict[str, Any]],
):
    result = ensure_clause_metadata(doc_id, clause_chunks_with_broken)

    assert len(result) == 1
    assert result[0]["metadata"]["effective_uid"] == "appendix:2.1"
    assert result[0]["metadata"]["raw_uid"] == "2.1"
    assert result[0]["metadata"]["scope"] == "appendix"


async def test_subclause_preserves_segment_metadata(
    doc_id: uuid.UUID,
    valid_clause_chunks: list[dict[str, Any]],
):
    result = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=valid_clause_chunks,
        target_tokens=300,
        max_tokens=800,
        overlap_ratio=0.15,
        total_pages=None,
    )

    assert len(result) >= 2

    sub1 = result[0]
    assert sub1["metadata"]["chunk_kind"] == "subclause"
    assert sub1["metadata"]["effective_uid"] == "main:1.1"
    assert sub1["metadata"]["raw_uid"] == "1.1"
    assert sub1["metadata"]["scope"] == "main"
    assert sub1["metadata"]["segment_id"] == "seg_001"
    assert sub1["metadata"]["segment_type"] == "primary"
    assert sub1["metadata"]["segment_title"] == "Main Body"
    assert sub1["metadata"]["language_filter"]["target_language"] == "en"
    assert sub1["metadata"]["language_filter"]["degraded"] is False

    sub2 = next(ch for ch in result if ch["metadata"]["effective_uid"] == "main:1.2")
    assert sub2["metadata"]["segment_id"] == "seg_001"
    assert sub2["metadata"]["segment_type"] == "primary"
    assert sub2["metadata"]["range_end_reason"] == "section_break"


async def test_subclause_id_uses_effective_uid(
    doc_id: uuid.UUID,
    valid_clause_chunks: list[dict[str, Any]],
):
    result = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=valid_clause_chunks,
        target_tokens=300,
        max_tokens=800,
        overlap_ratio=0.15,
        total_pages=None,
    )

    first = result[0]
    chunk_id = first["id"]

    assert str(doc_id) in chunk_id
    assert "main:1.1" in chunk_id
    assert first["metadata"]["effective_uid"] == "main:1.1"
    assert first["metadata"]["raw_uid"] == "1.1"
    assert first["metadata"]["subchunk_index"] == 0
    assert first["metadata"]["subchunk_count"] >= 1


async def test_scope_preserved_in_metadata(
    doc_id: uuid.UUID,
    valid_clause_chunks: list[dict[str, Any]],
):
    result = build_sized_chunks_from_leaf(
        doc_id=doc_id,
        leaf_chunks=valid_clause_chunks,
        target_tokens=300,
        max_tokens=800,
        overlap_ratio=0.15,
        total_pages=None,
    )

    assert result

    for chunk in result:
        assert "scope" in chunk["metadata"]
        assert chunk["metadata"]["scope"] == "main"
        assert chunk["metadata"]["effective_uid"].startswith("main:")


async def test_service_get_chunks_filters_broken_snapshot_chunks(
    mocker,
    doc_id: uuid.UUID,
    snapshot_clause_chunks: list[dict[str, Any]],
):
    version = _make_version(doc_id, manifest_ref="s3://bucket/chunks-manifest.json")
    service = _make_service(mocker, version)

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")
    reader = reader_cls.return_value
    reader.load = AsyncMock(return_value=snapshot_clause_chunks)

    result = await service.get_chunks(doc_id)

    assert len(result) == 1
    assert result[0]["id"] == "snapshot_clause_1"
    assert result[0]["metadata"]["effective_uid"] == "main:1.1"
    assert result[0]["metadata"]["raw_uid"] == "1.1"
    assert result[0]["metadata"]["scope"] == "main"


async def test_service_requires_snapshot_manifest(
    mocker,
    doc_id: uuid.UUID,
):
    version = _make_version(doc_id, manifest_ref=None)
    service = _make_service(mocker, version)

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")

    result = await service.get_chunks(doc_id)

    assert result == []
    reader_cls.assert_not_called()


async def test_retrieval_chunk_uses_effective_uid_as_clause_uid(
    mocker,
    doc_id: uuid.UUID,
):
    version = _make_version(doc_id, manifest_ref="s3://bucket/chunks-manifest.json")
    service = _make_service(mocker, version)

    snapshot_chunks = [
        {
            "id": "snapshot_clause_1",
            "text": "Clause text from snapshot one.",
            "metadata": {
                "effective_uid": "main:1.1",
                "raw_uid": "1.1",
                "scope": "main",
                "chunk_kind": "clause",
                "level": 2,
                "title": "Section One",
                "path_titles": ["Intro", "Section One"],
                "start_page": 1,
                "end_page": 1,
                "element_ids": ["e1", "e2"],
            },
        }
    ]

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")
    reader = reader_cls.return_value
    reader.load = AsyncMock(return_value=snapshot_chunks)

    result = await service._get_clause_chunks_as_retrieval(doc_id)

    assert len(result) == 1
    rc = result[0]

    assert rc.id == "snapshot_clause_1"
    assert rc.clause_uid == "main:1.1"
    assert rc.clause_uid != "1.1"
    assert rc.kind == "clause"
    assert rc.doc_id == str(doc_id)


async def test_get_retrieval_chunks_for_checks_v2_only(
    mocker,
    doc_id: uuid.UUID,
):
    version = _make_version(doc_id, manifest_ref="s3://bucket/chunks-manifest.json")
    service = _make_service(mocker, version)

    snapshot_chunks = [
        {
            "id": "sub_1",
            "text": "Subclause text",
            "metadata": {
                "effective_uid": "main:1.1",
                "raw_uid": "1.1",
                "scope": "main",
                "chunk_kind": "subclause",
            },
        },
        {
            "id": "broken_sub",
            "text": "Broken subclause text",
            "metadata": {
                "raw_uid": "1.2",
                "scope": "main",
                "chunk_kind": "subclause",
            },
        },
        {
            "id": "section_1",
            "text": "Section text",
            "metadata": {
                "effective_uid": "main:sec-1",
                "raw_uid": "sec-1",
                "scope": "main",
                "chunk_kind": "section",
            },
        },
    ]

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")
    reader = reader_cls.return_value
    reader.load = AsyncMock(return_value=snapshot_chunks)

    result = await service.get_retrieval_chunks_for_checks(
        doc_id,
        levels=["subclause", "section"],
    )

    assert len(result) == 2
    ids = {chunk["id"] for chunk in result}
    assert ids == {"sub_1", "section_1"}

    for chunk in result:
        assert chunk["metadata"]["effective_uid"]


async def test_get_sized_chunks_from_service_preserves_canonical_contract(
    mocker,
    doc_id: uuid.UUID,
    valid_clause_chunks: list[dict[str, Any]],
):
    version = _make_version(doc_id, manifest_ref="s3://bucket/chunks-manifest.json")
    service = _make_service(mocker, version)

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")
    reader = reader_cls.return_value
    reader.load = AsyncMock(return_value=valid_clause_chunks)

    result = await service.get_sized_chunks(doc_id)

    assert result

    for chunk in result:
        meta = chunk["metadata"]
        assert meta["chunk_kind"] == "subclause"
        assert meta["effective_uid"].startswith("main:")
        assert meta["scope"] == "main"
        assert "subchunk_index" in meta
        assert "subchunk_count" in meta


async def test_get_hierarchical_chunks_uses_snapshot_and_fallbacks(
    mocker,
    doc_id: uuid.UUID,
):
    version = _make_version(doc_id, manifest_ref="s3://bucket/chunks-manifest.json")
    service = _make_service(mocker, version)

    snapshot_chunks = [
        {
            "id": "section_1",
            "text": "Section text",
            "metadata": {
                "effective_uid": "main:sec-1",
                "raw_uid": "sec-1",
                "scope": "main",
                "chunk_kind": "section",
            },
        },
        {
            "id": "broken_clause",
            "text": "Broken clause text",
            "metadata": {
                "raw_uid": "1.2",
                "scope": "main",
                "chunk_kind": "clause",
            },
        },
    ]

    reader_cls = mocker.patch("engine.content.document_content_service.ChunkCorpusReaderV2")
    reader = reader_cls.return_value
    reader.load = AsyncMock(return_value=snapshot_chunks)

    mocker.patch.object(
        service,
        "get_chunks",
        AsyncMock(
            return_value=[
                {
                    "id": "clause_ok",
                    "text": "Clause ok",
                    "metadata": {
                        "effective_uid": "main:1.1",
                        "raw_uid": "1.1",
                        "scope": "main",
                        "chunk_kind": "clause",
                    },
                }
            ]
        ),
    )
    mocker.patch.object(
        service,
        "get_sized_chunks",
        AsyncMock(
            return_value=[
                {
                    "id": "sub_ok",
                    "text": "Sub ok",
                    "metadata": {
                        "effective_uid": "main:1.1",
                        "raw_uid": "1.1",
                        "scope": "main",
                        "chunk_kind": "subclause",
                        "subchunk_index": 0,
                        "subchunk_count": 1,
                    },
                }
            ]
        ),
    )

    result = await service.get_hierarchical_chunks(doc_id)

    assert len(result["section"]) == 1
    assert len(result["clause"]) == 1
    assert len(result["subclause"]) == 1

    assert result["section"][0]["metadata"]["effective_uid"] == "main:sec-1"
    assert result["clause"][0]["metadata"]["effective_uid"] == "main:1.1"
    assert result["subclause"][0]["metadata"]["effective_uid"] == "main:1.1"


