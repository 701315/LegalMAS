"""
Sprint 3 integration tests: DocumentContentService canonical contract.

Проверяем end-to-end:
- get_chunks возвращает canonical metadata
- get_sized_chunks возвращает subclause с canonical metadata
- get_hierarchical_chunks возвращает все три уровня с canonical metadata
- get_retrieval_chunks_for_checks читает V2 snapshot и fallback на пустой список
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from engine.content.document_content_service import DocumentContentService


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_storage_client():
    """Mock storage client, возвращающий clause tree."""
    client = AsyncMock()
    
    async def load_tree(uri):
        return {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Definitions",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["e1", "e2"],
                }
            ],
            "structure_diagnostics": {
                "quality_gates": {
                    "section_chunking_allowed": True,
                }
            }
        }
    
    client.load_json = load_tree
    return client


@pytest.fixture
def mock_layout_client():
    """Mock layout client."""
    client = AsyncMock()
    
    async def load_layout(uri):
        return {
            "elements": [
                {"element_id": "e1", "type": "heading", "text": "1. Definitions", "page": 1},
                {"element_id": "e2", "type": "text", "text": "Contract means this agreement.", "page": 1},
            ],
            "metadata": {"page_count": 10}
        }
    
    client.load_json = load_layout
    return client


@pytest.mark.asyncio
class TestGetChunksCanonicalMetadata:
    """Проверка canonical metadata в get_chunks."""

    async def test_get_chunks_returns_canonical_metadata(
        self,
        mock_session,
        mock_storage_client,
        mock_layout_client,
    ):
        """get_chunks возвращает chunks с canonical metadata."""
        service = DocumentContentService(
            session=mock_session,
            storage_client=mock_storage_client,
            layout_client=mock_layout_client,
        )
        
        # Моки для версии
        async def get_latest(doc_id):
            version = MagicMock()
            version.clause_tree_ref = "s3://bucket/tree.json"
            version.layout_primary_sanitized_ref = "s3://bucket/layout.json"
            return version
        
        service.versions.get_latest = get_latest
        
        doc_id = uuid.uuid4()
        chunks = await service.get_chunks(doc_id)
        
        assert len(chunks) == 1
        
        meta = chunks[0]["metadata"]
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"
        assert meta["node_kind"] == "leaf"
        assert meta["chunk_kind"] == "clause"
        
        # clause_uid НЕ в metadata
        assert "clause_uid" not in meta


@pytest.mark.asyncio
class TestGetSizedChunksCanonicalMetadata:
    """Проверка canonical metadata в get_sized_chunks."""

    async def test_get_sized_chunks_returns_subclause_metadata(
        self,
        mock_session,
        mock_storage_client,
        mock_layout_client,
    ):
        """get_sized_chunks возвращает subclause chunks с canonical metadata."""
        service = DocumentContentService(
            session=mock_session,
            storage_client=mock_storage_client,
            layout_client=mock_layout_client,
        )
        
        async def get_latest(doc_id):
            version = MagicMock()
            version.clause_tree_ref = "s3://bucket/tree.json"
            version.layout_primary_sanitized_ref = "s3://bucket/layout.json"
            return version
        
        service.versions.get_latest = get_latest
        
        doc_id = uuid.uuid4()
        sized_chunks = await service.get_sized_chunks(doc_id)
        
        assert len(sized_chunks) > 0
        
        meta = sized_chunks[0]["metadata"]
        assert meta["chunk_kind"] == "subclause"
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"
        
        # Должны быть subchunk_index и subchunk_count
        assert "subchunk_index" in meta
        assert "subchunk_count" in meta


@pytest.mark.asyncio
class TestGetHierarchicalChunksCanonicalMetadata:
    """Проверка canonical metadata в get_hierarchical_chunks."""

    async def test_hierarchical_chunks_all_levels_canonical(
        self,
        mock_session,
        mock_storage_client,
        mock_layout_client,
    ):
        """get_hierarchical_chunks возвращает section/clause/subclause с canonical metadata."""
        service = DocumentContentService(
            session=mock_session,
            storage_client=mock_storage_client,
            layout_client=mock_layout_client,
        )
        
        async def get_latest(doc_id):
            version = MagicMock()
            version.clause_tree_ref = "s3://bucket/tree.json"
            version.layout_primary_sanitized_ref = "s3://bucket/layout.json"
            return version
        
        service.versions.get_latest = get_latest
        
        doc_id = uuid.uuid4()
        hierarchical = await service.get_hierarchical_chunks(doc_id)
        
        assert "section" in hierarchical
        assert "clause" in hierarchical
        assert "subclause" in hierarchical
        
        # Проверим clause
        clause_chunks = hierarchical["clause"]
        assert len(clause_chunks) > 0
        clause_meta = clause_chunks[0]["metadata"]
        assert clause_meta["chunk_kind"] == "clause"
        assert "effective_uid" in clause_meta
        assert "raw_uid" in clause_meta
        
        # Проверим subclause
        subclause_chunks = hierarchical["subclause"]
        assert len(subclause_chunks) > 0
        subclause_meta = subclause_chunks[0]["metadata"]
        assert subclause_meta["chunk_kind"] == "subclause"
        
        # Проверим section
        section_chunks = hierarchical["section"]
        if len(section_chunks) > 0:
            section_meta = section_chunks[0]["metadata"]
            assert section_meta["chunk_kind"] == "section"
            assert section_meta["node_kind"] == "section"


@pytest.mark.asyncio
class TestGetRetrievalChunksForChecksV2Path:
    """Проверка V2-only path в get_retrieval_chunks_for_checks."""

    async def test_returns_empty_when_no_v2_manifest(
        self,
        mock_session,
        mock_storage_client,
        mock_layout_client,
    ):
        """Если chunks_manifest_v2_ref отсутствует, возвращаем пустой список."""
        service = DocumentContentService(
            session=mock_session,
            storage_client=mock_storage_client,
            layout_client=mock_layout_client,
        )
        
        async def get_latest(doc_id):
            version = MagicMock()
            version.chunks_manifest_v2_ref = None  # V2 manifest отсутствует
            return version
        
        service.versions.get_latest = get_latest
        
        doc_id = uuid.uuid4()
        chunks = await service.get_retrieval_chunks_for_checks(doc_id)
        
        # V2-only режим: если manifest нет, возвращаем []
        assert chunks == []

    async def test_reads_v2_snapshot_when_manifest_present(
        self,
        mock_session,
        mock_storage_client,
        mock_layout_client,
    ):
        """Если chunks_manifest_v2_ref есть, читаем snapshot через ChunkCorpusReaderV2."""
        service = DocumentContentService(
            session=mock_session,
            storage_client=mock_storage_client,
            layout_client=mock_layout_client,
        )
        
        async def get_latest(doc_id):
            version = MagicMock()
            version.chunks_manifest_v2_ref = "s3://bucket/manifest_v2.json"
            return version
        
        service.versions.get_latest = get_latest
        
        # Mock ChunkCorpusReaderV2
        with patch("engine.content.document_content_service.ChunkCorpusReaderV2") as MockReader:
            mock_reader_instance = AsyncMock()
            mock_reader_instance.load = AsyncMock(return_value=[
                {
                    "id": "chunk_1",
                    "text": "Chunk from V2 snapshot.",
                    "metadata": {
                        "chunk_kind": "subclause",
                        "effective_uid": "main_contract::1",
                        "raw_uid": "1",
                        "scope": "main_contract",
                    },
                }
            ])
            MockReader.return_value = mock_reader_instance
            
            doc_id = uuid.uuid4()
            chunks = await service.get_retrieval_chunks_for_checks(doc_id, levels=["subclause"])
            
            # Должны получить chunks из V2 snapshot
            assert len(chunks) == 1
            assert chunks[0]["id"] == "chunk_1"
            assert chunks[0]["metadata"]["chunk_kind"] == "subclause"
            
            # Убедимся что reader был вызван с правильными аргументами
            mock_reader_instance.load.assert_called_once_with(doc_id=doc_id, levels=["subclause"])


            