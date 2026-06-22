"""
Tests for ChunkCorpusReaderV2.load() with enrichment_sidecars_by_segment.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2


def _make_segment_snapshot(
    segment_id: str,
    segment_type: str,
    legal_unit_count: int,
    with_enrichment: bool = False,
) -> dict[str, Any]:
    """Build a minimal valid v2 segment snapshot."""
    units = []
    for i in range(legal_unit_count):
        unit_id = f"{segment_id}:unit:{i}"
        meta: dict[str, Any] = {
            "effective_uid": unit_id,
            "segment_id": segment_id,
            "segment_type": segment_type,
            "chunk_kind": "legal_unit",
        }
        if with_enrichment:
            meta["clause_function"] = "obligations"

        units.append({
            "id": f"chunk-{unit_id}",
            "text": f"Text of unit {i} in {segment_id}",
            "metadata": meta,
        })

    return {
        "scope": "segment",
        "schema_version": 2,
        "chunks": {
            "legal_unit": units,
            "section": [],
        },
    }


def _make_manifest(segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {"segments": segments}


def _make_enrichment_sidecar(unit_ids: list[str]) -> dict[str, Any]:
    return {
        "enrichments": [
            {
                "unit_id": uid,
                "status": "applied",
                "effective": {
                    "clause_function": "obligations",
                    "unit_type": "warranty",
                    "topic_tags": ["transfer"],
                },
                "base": {
                    "clause_function": "unknown",
                    "unit_type": "unknown",
                    "topic_tags": [],
                },
            }
            for uid in unit_ids
        ]
    }


@pytest.fixture()
def doc_id() -> uuid.UUID:
    return uuid.UUID("d0d0fcba-8b6a-4ab5-bbd2-1ab005943503")


@pytest.fixture()
def version_id() -> uuid.UUID:
    return uuid.UUID("3ad33555-c012-4e0d-8d9c-361e1307b528")


@pytest.fixture()
def contract_segment_id() -> str:
    return "c794da13-b0b7-5a78-a658-1d0d793ab119"


@pytest.fixture()
def appendix_segment_id() -> str:
    return "0d4c5b74-9800-52b4-a790-e530dda603c1"


def _build_reader_with_mocks(
    doc_id: uuid.UUID,
    version_id: uuid.UUID,
    manifest: dict,
    snapshots_by_ref: dict[str, dict],
    db_segment_ids: list[str],
) -> ChunkCorpusReaderV2:
    """
    Build a ChunkCorpusReaderV2 with mocked DB and storage.
    """
    session = MagicMock()

    mock_version = MagicMock()
    mock_version.id = version_id
    mock_version.document_id = doc_id
    mock_version.chunks_manifest_v2_ref = "s3://bucket/manifest.json"

    version_repo = AsyncMock()
    version_repo.get_latest.return_value = mock_version
    version_repo.get_by_id.return_value = mock_version

    mock_db_segments = []
    for seg_id in db_segment_ids:
        seg = MagicMock()
        seg.segment_id = seg_id
        mock_db_segments.append(seg)

    segment_repo = AsyncMock()
    segment_repo.list_by_version.return_value = mock_db_segments

    artifact_store = MagicMock()

    def _get_json(ref: str) -> dict:
        if ref == "s3://bucket/manifest.json":
            return manifest
        if ref in snapshots_by_ref:
            return snapshots_by_ref[ref]
        raise FileNotFoundError(f"Unknown ref: {ref}")

    artifact_store.get_json.side_effect = _get_json

    reader = ChunkCorpusReaderV2.__new__(ChunkCorpusReaderV2)
    reader.session = session
    reader.versions = version_repo
    reader.segments = segment_repo
    reader.artifact_store = artifact_store

    return reader


class TestChunkCorpusReaderV2LoadWithSidecars:
    @pytest.mark.asyncio
    async def test_load_without_sidecars_returns_all_segments(
        self,
        doc_id,
        version_id,
        contract_segment_id,
        appendix_segment_id,
    ):
        contract_ref = "s3://bucket/chunks_contract.json"
        appendix_ref = "s3://bucket/chunks_appendix.json"

        manifest = _make_manifest([
            {
                "segment_id": contract_segment_id,
                "segment_type": "contract",
                "segment_chunks_ref": contract_ref,
            },
            {
                "segment_id": appendix_segment_id,
                "segment_type": "appendix",
                "segment_chunks_ref": appendix_ref,
            },
        ])

        snapshots = {
            contract_ref: _make_segment_snapshot(contract_segment_id, "contract", 5),
            appendix_ref: _make_segment_snapshot(appendix_segment_id, "appendix", 3),
        }

        reader = _build_reader_with_mocks(
            doc_id=doc_id,
            version_id=version_id,
            manifest=manifest,
            snapshots_by_ref=snapshots,
            db_segment_ids=[contract_segment_id, appendix_segment_id],
        )

        chunks = await reader.load(
            doc_id=doc_id,
            levels=["legal_unit"],
        )

        assert len(chunks) == 8  # 5 contract + 3 appendix

        segment_types = {
            c["metadata"]["segment_type"] for c in chunks
        }
        assert "contract" in segment_types
        assert "appendix" in segment_types

    @pytest.mark.asyncio
    async def test_load_with_sidecars_applies_enrichment_per_segment(
        self,
        doc_id,
        version_id,
        contract_segment_id,
        appendix_segment_id,
    ):
        contract_ref = "s3://bucket/chunks_contract.json"
        appendix_ref = "s3://bucket/chunks_appendix.json"

        manifest = _make_manifest([
            {
                "segment_id": contract_segment_id,
                "segment_type": "contract",
                "segment_chunks_ref": contract_ref,
            },
            {
                "segment_id": appendix_segment_id,
                "segment_type": "appendix",
                "segment_chunks_ref": appendix_ref,
            },
        ])

        snapshots = {
            contract_ref: _make_segment_snapshot(contract_segment_id, "contract", 2),
            appendix_ref: _make_segment_snapshot(appendix_segment_id, "appendix", 2),
        }

        # Sidecar only for contract segment
        contract_unit_ids = [
            f"{contract_segment_id}:unit:0",
            f"{contract_segment_id}:unit:1",
        ]
        sidecars_by_segment = {
            contract_segment_id: _make_enrichment_sidecar(contract_unit_ids),
        }

        reader = _build_reader_with_mocks(
            doc_id=doc_id,
            version_id=version_id,
            manifest=manifest,
            snapshots_by_ref=snapshots,
            db_segment_ids=[contract_segment_id, appendix_segment_id],
        )

        chunks = await reader.load(
            doc_id=doc_id,
            levels=["legal_unit"],
            enrichment_sidecars_by_segment=sidecars_by_segment,
        )

        assert len(chunks) == 4  # 2 + 2

        contract_chunks = [
            c for c in chunks
            if c["metadata"]["segment_type"] == "contract"
        ]
        appendix_chunks = [
            c for c in chunks
            if c["metadata"]["segment_type"] == "appendix"
        ]

        # Contract chunks should have enrichment projection applied
        for c in contract_chunks:
            assert c["metadata"].get("enrichment_projected") is True
            assert c["metadata"].get("clause_function") == "obligations"

        # Appendix chunks should NOT have enrichment projection
        for c in appendix_chunks:
            assert c["metadata"].get("enrichment_projected") is not True

    @pytest.mark.asyncio
    async def test_load_with_sidecars_for_both_segments(
        self,
        doc_id,
        version_id,
        contract_segment_id,
        appendix_segment_id,
    ):
        contract_ref = "s3://bucket/chunks_contract.json"
        appendix_ref = "s3://bucket/chunks_appendix.json"

        manifest = _make_manifest([
            {
                "segment_id": contract_segment_id,
                "segment_type": "contract",
                "segment_chunks_ref": contract_ref,
            },
            {
                "segment_id": appendix_segment_id,
                "segment_type": "appendix",
                "segment_chunks_ref": appendix_ref,
            },
        ])

        snapshots = {
            contract_ref: _make_segment_snapshot(contract_segment_id, "contract", 2),
            appendix_ref: _make_segment_snapshot(appendix_segment_id, "appendix", 2),
        }

        sidecars_by_segment = {
            contract_segment_id: _make_enrichment_sidecar([
                f"{contract_segment_id}:unit:0",
                f"{contract_segment_id}:unit:1",
            ]),
            appendix_segment_id: _make_enrichment_sidecar([
                f"{appendix_segment_id}:unit:0",
                f"{appendix_segment_id}:unit:1",
            ]),
        }

        reader = _build_reader_with_mocks(
            doc_id=doc_id,
            version_id=version_id,
            manifest=manifest,
            snapshots_by_ref=snapshots,
            db_segment_ids=[contract_segment_id, appendix_segment_id],
        )

        chunks = await reader.load(
            doc_id=doc_id,
            levels=["legal_unit"],
            enrichment_sidecars_by_segment=sidecars_by_segment,
        )

        assert len(chunks) == 4

        for c in chunks:
            assert c["metadata"].get("enrichment_projected") is True

    @pytest.mark.asyncio
    async def test_load_empty_sidecars_dict_no_projection(
        self,
        doc_id,
        version_id,
        contract_segment_id,
    ):
        contract_ref = "s3://bucket/chunks_contract.json"

        manifest = _make_manifest([
            {
                "segment_id": contract_segment_id,
                "segment_type": "contract",
                "segment_chunks_ref": contract_ref,
            },
        ])

        snapshots = {
            contract_ref: _make_segment_snapshot(contract_segment_id, "contract", 3),
        }

        reader = _build_reader_with_mocks(
            doc_id=doc_id,
            version_id=version_id,
            manifest=manifest,
            snapshots_by_ref=snapshots,
            db_segment_ids=[contract_segment_id],
        )

        chunks = await reader.load(
            doc_id=doc_id,
            levels=["legal_unit"],
            enrichment_sidecars_by_segment={},  # empty dict
        )

        assert len(chunks) == 3
        for c in chunks:
            assert c["metadata"].get("enrichment_projected") is not True


            