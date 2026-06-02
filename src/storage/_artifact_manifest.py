# src/storage/_artifact_manifest.py

"""
Phase 14.4 — Artifact Manifest Writer.

Best-effort запись document-level artifact_manifest.json после
успешного commit каждой стадии (structure / chunking).

Manifest — это convenience snapshot, НЕ source of truth.
Source of truth остаётся в DB (DocumentVersion + DocumentSegment).

Manifest полезен для:
- debugging / support tooling,
- downstream sync без DB access,
- cleanup reconciliation.

Ошибка записи manifest никогда не ломает pipeline.
"""

from __future__ import annotations

import time
from typing import Any

from core.logging import get_logger
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


def write_artifact_manifest_best_effort(
    *,
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    document_id: str,
    document_version_id: str,
    clause_tree_ref: str | None = None,
    file_graph_ref: str | None = None,
    chunk_plan_ref: str | None = None,
    chunks_manifest_v2_ref: str | None = None,
    segment_refs: list[dict[str, Any]] | None = None,
    stage: str = "unknown",
    extra: dict[str, Any] | None = None,
) -> str | None:
    """
    Best-effort запись artifact_manifest.json в MinIO.

    Parameters
    ----------
    chunk_plan_ref:
        S3 URI к chunk_plan.json (Phase 10 output).
        Записывается structure stage, читается chunk stage.
        None если planning не выполнялся.

    Returns
    -------
    str | None
        S3 URI если запись успешна, None если ошибка.
    """
    manifest_path = ArtifactPath.artifact_manifest(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=document_id,
    )

    manifest_data: dict[str, Any] = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "clause_tree_ref": clause_tree_ref,
        "file_graph_ref": file_graph_ref,
        "chunk_plan_ref": chunk_plan_ref,
        "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
        "segments": segment_refs or [],
        "last_updated_by_stage": stage,
        "last_updated_at": time.time(),
    }

    if extra:
        manifest_data["extra"] = extra

    try:
        ref = store.put_json(manifest_path, manifest_data)
        logger.debug(
            "Artifact manifest written",
            document_id=document_id,
            stage=stage,
            manifest_ref=ref,
        )
        return ref
    except Exception as e:
        logger.warning(
            "Failed to write artifact manifest (non-critical)",
            document_id=document_id,
            stage=stage,
            error=str(e),
        )
        return None
    

