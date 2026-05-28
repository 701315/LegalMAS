"""
Sprint 3 integration tests: DocumentContentService canonical contract.

Проверяем end-to-end:
- get_chunks возвращает canonical metadata из CHUNKS v2 snapshot
- get_sized_chunks возвращает subclause с canonical metadata
- get_hierarchical_chunks возвращает все три уровня с canonical metadata
- get_retrieval_chunks_for_checks читает V2 snapshot и fallback на пустой список
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.content.document_content_service import DocumentContentService

# ---------------------------------------------------------------------------
# Общие тестовые данные
# ---------------------------------------------------------------------------

_CLAUSE_CHUNK = {
    "id": "chunk_1",
    "text": "Contract means this agreement.",
    "metadata": {
        "chunk_kind": "clause",
        "effective_uid": "main_contract::1",
        "raw_uid": "1",
        "scope": "main_contract",
        "node_kind": "leaf",
        "level": 1,
        "title": "Definitions",
        "path_titles": ["Definitions"],
        "element_ids": ["e1", "e2"],
    },
}

_SECTION_CHUNK = {
    "id": "section_1",
    "text": "Definitions section text.",
    "metadata": {
        "chunk_kind": "section",
        "effective_uid": "main_contract::sec_1",
        "raw_uid": "sec_1",
        "scope": "main_contract",
        "node_kind": "section",
    },
}

_SUBCLAUSE_CHUNK = {
    "id": "subclause_1",
    "text": "Contract means this agreement.",
    "metadata": {
        "chunk_kind": "subclause",
        "effective_uid": "main_contract::1",
        "raw_uid": "1",
        "scope": "main_contract",
        "node_kind": "leaf",
        "subchunk_index": 0,
        "subchunk_count": 1,
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock AsyncSession."""
    return MagicMock()


def _make_version(*, manifest_ref: str | None = "s3://bucket/manifest_v2.json") -> MagicMock:
    """
    Собрать MagicMock-версию с явно проставленными полями.

    Все атрибуты, которые сервис читает через getattr, задаём явно,
    чтобы MagicMock не возвращал truthy-заглушки вместо None.
    """
    version = MagicMock()
    version.id = uuid.uuid4()
    version.chunks_manifest_v2_ref = manifest_ref
    version.clause_tree_ref = None
    version.layout_primary_sanitized_ref = None
    version.layout_primary_ref = None
    return version


def _make_reader_mock(return_value: list) -> AsyncMock:
    """Собрать AsyncMock для ChunkCorpusReaderV2 с заданным return_value для .load()."""
    mock_reader_instance = AsyncMock()
    mock_reader_instance.load = AsyncMock(return_value=return_value)
    return mock_reader_instance


# ---------------------------------------------------------------------------
# TestGetChunksCanonicalMetadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetChunksCanonicalMetadata:
    """Проверка canonical metadata в get_chunks."""

    async def test_get_chunks_returns_canonical_metadata(
        self,
        mock_session: MagicMock,
    ) -> None:
        """get_chunks читает CHUNKS v2 snapshot и возвращает chunks с canonical metadata."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock([_CLAUSE_CHUNK])

            doc_id = uuid.uuid4()
            chunks = await service.get_chunks(doc_id)

        assert len(chunks) == 1

        meta = chunks[0]["metadata"]
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"
        assert meta["node_kind"] == "leaf"
        assert meta["chunk_kind"] == "clause"

        # clause_uid не должен попасть в metadata — он идёт только в RetrievalChunk
        assert "clause_uid" not in meta

    async def test_get_chunks_returns_empty_when_no_manifest(
        self,
        mock_session: MagicMock,
    ) -> None:
        """get_chunks возвращает пустой список если chunks_manifest_v2_ref не задан."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version(manifest_ref=None)

        service.versions.get_latest = get_latest

        doc_id = uuid.uuid4()
        chunks = await service.get_chunks(doc_id)

        assert chunks == []

    async def test_get_chunks_skips_broken_chunks_without_effective_uid(
        self,
        mock_session: MagicMock,
    ) -> None:
        """get_chunks пропускает broken chunks у которых нет effective_uid."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        broken_chunk = {
            "id": "broken_1",
            "text": "Some text without effective_uid.",
            "metadata": {
                "raw_uid": "1",
                "scope": "main_contract",
            },
        }

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock([broken_chunk, _CLAUSE_CHUNK])

            doc_id = uuid.uuid4()
            chunks = await service.get_chunks(doc_id)

        # Только валидный chunk должен пройти
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["effective_uid"] == "main_contract::1"


# ---------------------------------------------------------------------------
# TestGetSizedChunksCanonicalMetadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetSizedChunksCanonicalMetadata:
    """Проверка canonical metadata в get_sized_chunks."""

    async def test_get_sized_chunks_returns_subclause_metadata(
        self,
        mock_session: MagicMock,
    ) -> None:
        """get_sized_chunks строится из clause chunks и возвращает subclause с canonical metadata."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock([_CLAUSE_CHUNK])

            doc_id = uuid.uuid4()
            sized_chunks = await service.get_sized_chunks(doc_id)

        assert len(sized_chunks) > 0

        meta = sized_chunks[0]["metadata"]
        assert meta["chunk_kind"] == "subclause"
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"

        # build_sized_chunks_from_leaf обязан проставить subchunk_index и subchunk_count
        assert "subchunk_index" in meta
        assert "subchunk_count" in meta

    async def test_get_sized_chunks_returns_empty_when_no_manifest(
        self,
        mock_session: MagicMock,
    ) -> None:
        """get_sized_chunks возвращает пустой список если нет v2 manifest."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version(manifest_ref=None)

        service.versions.get_latest = get_latest

        doc_id = uuid.uuid4()
        sized_chunks = await service.get_sized_chunks(doc_id)

        assert sized_chunks == []


# ---------------------------------------------------------------------------
# TestGetHierarchicalChunksCanonicalMetadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetHierarchicalChunksCanonicalMetadata:
    """Проверка canonical metadata в get_hierarchical_chunks."""

    async def test_hierarchical_chunks_all_levels_from_snapshot(
        self,
        mock_session: MagicMock,
    ) -> None:
        """
        get_hierarchical_chunks читает section/clause/subclause из snapshot
        и возвращает их с canonical metadata.
        """
        service = DocumentContentService(session=mock_session)

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock(
                [_SECTION_CHUNK, _CLAUSE_CHUNK, _SUBCLAUSE_CHUNK]
            )

            doc_id = uuid.uuid4()
            hierarchical = await service.get_hierarchical_chunks(doc_id)

        assert "section" in hierarchical
        assert "clause" in hierarchical
        assert "subclause" in hierarchical

        clause_chunks = hierarchical["clause"]
        assert len(clause_chunks) > 0
        clause_meta = clause_chunks[0]["metadata"]
        assert clause_meta["chunk_kind"] == "clause"
        assert "effective_uid" in clause_meta
        assert "raw_uid" in clause_meta

        subclause_chunks = hierarchical["subclause"]
        assert len(subclause_chunks) > 0
        subclause_meta = subclause_chunks[0]["metadata"]
        assert subclause_meta["chunk_kind"] == "subclause"

        section_chunks = hierarchical["section"]
        assert len(section_chunks) > 0
        section_meta = section_chunks[0]["metadata"]
        assert section_meta["chunk_kind"] == "section"
        assert section_meta["node_kind"] == "section"

    async def test_hierarchical_chunks_fallback_clause_from_get_chunks(
        self,
        mock_session: MagicMock,
    ) -> None:
        """
        Если snapshot не содержит clause chunks, get_hierarchical_chunks
        достраивает их через get_chunks().
        """
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            # Snapshot возвращает только subclause — clause отсутствует
            # get_chunks() внутри снова обратится к reader, поэтому настраиваем
            # side_effect: первый вызов (hierarchical) — subclause only,
            # второй вызов (get_chunks fallback) — clause.
            mock_reader_instance = AsyncMock()
            mock_reader_instance.load = AsyncMock(
                side_effect=[
                    [_SUBCLAUSE_CHUNK],   # вызов из get_hierarchical_chunks
                    [_CLAUSE_CHUNK],      # вызов из get_chunks (fallback)
                ]
            )
            MockReader.return_value = mock_reader_instance

            doc_id = uuid.uuid4()
            hierarchical = await service.get_hierarchical_chunks(doc_id)

        clause_chunks = hierarchical["clause"]
        assert len(clause_chunks) > 0
        assert clause_chunks[0]["metadata"]["chunk_kind"] == "clause"

    async def test_hierarchical_chunks_skips_broken_chunks_without_effective_uid(
        self,
        mock_session: MagicMock,
    ) -> None:
        """
        get_hierarchical_chunks пропускает broken snapshot chunks без effective_uid.
        """
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        broken = {
            "id": "broken_2",
            "text": "Text without uid.",
            "metadata": {"chunk_kind": "clause", "raw_uid": "x"},
        }

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            mock_reader_instance = AsyncMock()
            mock_reader_instance.load = AsyncMock(
                side_effect=[
                    [broken, _CLAUSE_CHUNK, _SUBCLAUSE_CHUNK],  # hierarchical call
                ]
            )
            MockReader.return_value = mock_reader_instance

            doc_id = uuid.uuid4()
            hierarchical = await service.get_hierarchical_chunks(doc_id)

        clause_chunks = hierarchical["clause"]
        # broken chunk должен быть отфильтрован
        assert all(
            ch["metadata"].get("effective_uid") for ch in clause_chunks
        )


# ---------------------------------------------------------------------------
# TestGetRetrievalChunksForChecksV2Path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetRetrievalChunksForChecksV2Path:
    """Проверка V2-only path в get_retrieval_chunks_for_checks."""

    async def test_returns_empty_when_no_v2_manifest(
        self,
        mock_session: MagicMock,
    ) -> None:
        """Если chunks_manifest_v2_ref отсутствует, возвращаем пустой список."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version(manifest_ref=None)

        service.versions.get_latest = get_latest

        doc_id = uuid.uuid4()
        chunks = await service.get_retrieval_chunks_for_checks(doc_id)

        assert chunks == []

    async def test_reads_v2_snapshot_when_manifest_present(
        self,
        mock_session: MagicMock,
    ) -> None:
        """Если chunks_manifest_v2_ref есть, читаем snapshot через ChunkCorpusReaderV2."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            mock_reader_instance = _make_reader_mock([_SUBCLAUSE_CHUNK])
            MockReader.return_value = mock_reader_instance

            doc_id = uuid.uuid4()
            chunks = await service.get_retrieval_chunks_for_checks(
                doc_id, levels=["subclause"]
            )

        assert len(chunks) == 1
        assert chunks[0]["id"] == "subclause_1"
        assert chunks[0]["metadata"]["chunk_kind"] == "subclause"

        mock_reader_instance.load.assert_called_once_with(
            doc_id=doc_id, levels=["subclause"]
        )

    async def test_returns_empty_when_snapshot_is_empty(
        self,
        mock_session: MagicMock,
    ) -> None:
        """Если manifest есть, но snapshot вернул пустой список — возвращаем []."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock([])

            doc_id = uuid.uuid4()
            chunks = await service.get_retrieval_chunks_for_checks(doc_id)

        assert chunks == []

    async def test_filters_chunks_without_effective_uid(
        self,
        mock_session: MagicMock,
    ) -> None:
        """Broken chunks без effective_uid фильтруются из результата."""
        service = DocumentContentService(session=mock_session)

        async def get_latest(doc_id: uuid.UUID) -> MagicMock:
            return _make_version()

        service.versions.get_latest = get_latest

        broken = {
            "id": "broken_3",
            "text": "Text without uid.",
            "metadata": {
                "chunk_kind": "subclause",
                "raw_uid": "1",
                "scope": "main_contract",
            },
        }

        with patch(
            "engine.content.document_content_service.ChunkCorpusReaderV2"
        ) as MockReader:
            MockReader.return_value = _make_reader_mock([broken, _SUBCLAUSE_CHUNK])

            doc_id = uuid.uuid4()
            chunks = await service.get_retrieval_chunks_for_checks(
                doc_id, levels=["subclause"]
            )

        assert len(chunks) == 1
        assert chunks[0]["metadata"]["effective_uid"] == "main_contract::1"

            