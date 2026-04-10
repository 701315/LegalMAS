# src/engine/content/chunk_snapshot_reader.py

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.document_version_repo import DocumentVersionRepository
from storage.artifact_store import ArtifactStore
from core.logging import get_logger

logger = get_logger(__name__)


class ChunkSnapshotReader:
    """
    Read-only adapter for canonical chunk snapshot stored in object storage.

    Source of truth:
    - DocumentVersion.chunks_ref

    Returned normalized items:
    [
        {
            "id": ...,
            "text": ...,
            "metadata": {...},
        }
    ]
    """

    def __init__(
        self,
        session: AsyncSession,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.session = session
        self.versions = DocumentVersionRepository(session)
        self.artifact_store = artifact_store or ArtifactStore()

    async def load(
        self,
        doc_id: uuid.UUID,
        levels: list[str],
    ) -> list[dict[str, Any]]:
        level_set = {
            lvl.strip().lower()
            for lvl in levels
            if isinstance(lvl, str) and lvl.strip()
        }
        if not level_set:
            return []

        version = await self.versions.get_latest(doc_id)
        if not version:
            return []

        chunks_ref = getattr(version, "chunks_ref", None)
        if not chunks_ref:
            return []

        try:
            snapshot = self.artifact_store.get_json(chunks_ref)
        except Exception as e:
            logger.warning(
                "ChunkSnapshotReader: failed to load chunk snapshot",
                extra={
                    "doc_id": str(doc_id),
                    "chunks_ref": chunks_ref,
                    "error": str(e),
                },
            )
            return []

        if not isinstance(snapshot, dict):
            logger.warning(
                "ChunkSnapshotReader: chunk snapshot is not a dict",
                extra={
                    "doc_id": str(doc_id),
                    "chunks_ref": chunks_ref,
                    "snapshot_type": type(snapshot).__name__,
                },
            )
            return []

        snapshot_doc_id = snapshot.get("doc_id")
        if snapshot_doc_id and str(snapshot_doc_id) != str(doc_id):
            logger.warning(
                "ChunkSnapshotReader: snapshot doc_id mismatch",
                extra={
                    "doc_id": str(doc_id),
                    "snapshot_doc_id": str(snapshot_doc_id),
                    "chunks_ref": chunks_ref,
                },
            )

        snapshot_version_id = snapshot.get("document_version_id")
        if snapshot_version_id and str(snapshot_version_id) != str(version.id):
            logger.warning(
                "ChunkSnapshotReader: snapshot version mismatch",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "snapshot_version_id": str(snapshot_version_id),
                    "chunks_ref": chunks_ref,
                },
            )

        chunks_by_level = snapshot.get("chunks") or {}
        if not isinstance(chunks_by_level, dict):
            return []

        out: list[dict[str, Any]] = []

        for lvl, items in chunks_by_level.items():
            if not isinstance(lvl, str):
                continue
            if lvl.strip().lower() not in level_set:
                continue
            if not isinstance(items, list):
                continue

            for ch in items:
                if not isinstance(ch, dict):
                    continue

                text = (ch.get("text") or "").strip()
                if not text:
                    continue

                metadata = ch.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}

                out.append(
                    {
                        "id": ch.get("id"),
                        "text": text,
                        "metadata": metadata,
                    }
                )

        return out