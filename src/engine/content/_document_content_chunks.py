# src/engine/content/_document_content_chunks.py

"""
Внутренние helper-функции для нормализации чанков документа.

Модуль выносит повторяющиеся преобразования chunk metadata, адаптацию
canonical chunks в RetrievalChunk и сборку плоского текста из набора чанков.
"""

from __future__ import annotations

import uuid
from typing import Any

from engine.content.chunking import build_chunk_summary
from engine.retrieval.models import RetrievalChunk
from engine.retrieval.tokenization import count_tokens


def build_retrieval_chunk_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Сформировать meta для RetrievalChunk без дублирования top-level полей.
    """
    excluded = {
        "doc_id",
        "chunk_kind",
        "node_kind",
        "level",
        "path_titles",
        "start_page",
        "end_page",
        "element_ids",
        "token_count",
        "summary",
    }
    return {k: v for k, v in meta.items() if k not in excluded}


def normalize_snapshot_chunk_metadata(
    *,
    doc_id: uuid.UUID,
    text: str,
    meta: dict[str, Any],
    chunk_kind: str | None = None,
) -> dict[str, Any]:
    """
    Нормализовать metadata snapshot chunk по canonical shape.
    """
    normalized = dict(meta or {})

    normalized["doc_id"] = normalized.get("doc_id") or str(doc_id)

    if chunk_kind:
        normalized["chunk_kind"] = chunk_kind

    normalized["token_count"] = normalized.get("token_count") or count_tokens(text)

    if "path_titles" in normalized:
        normalized["path_titles"] = list(normalized.get("path_titles") or [])

    if "element_ids" in normalized:
        normalized["element_ids"] = [
            str(element_id) for element_id in normalized.get("element_ids") or []
        ]

    if not normalized.get("summary"):
        summary = build_chunk_summary(
            list(normalized.get("path_titles") or []),
            text,
        )
        if summary:
            normalized["summary"] = summary

    return normalized


def build_canonical_chunk_payload(
    *,
    chunk_id: Any,
    text: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """
    Собрать canonical dict chunk в том же контракте, что использует сервис.
    """
    return {
        "id": chunk_id,
        "text": text,
        "metadata": meta,
    }


def build_retrieval_chunk_from_canonical(
    *,
    chunk: dict[str, Any],
    doc_id: uuid.UUID,
    default_kind: str,
) -> RetrievalChunk | None:
    """
    Построить RetrievalChunk из canonical dict chunk.
    """
    text = (chunk.get("text") or "").strip()
    if not text:
        return None

    meta = chunk.get("metadata") or {}
    effective_uid = meta.get("effective_uid")
    if not effective_uid:
        return None

    chunk_kind = meta.get("chunk_kind") or default_kind

    return RetrievalChunk(
        id=str(chunk.get("id")),
        doc_id=meta.get("doc_id") or str(doc_id),
        kind=chunk_kind,
        clause_uid=effective_uid,
        level=meta.get("level"),
        text=text,
        token_count=meta.get("token_count") or count_tokens(text),
        path_titles=list(meta.get("path_titles") or []),
        start_page=meta.get("start_page"),
        end_page=meta.get("end_page"),
        element_ids=[str(element_id) for element_id in meta.get("element_ids") or []],
        summary=meta.get("summary"),
        meta=build_retrieval_chunk_meta(meta),
    )


def join_chunk_texts(
    chunks: list[dict[str, Any]],
    max_chars: int,
) -> str | None:
    """
    Склеить тексты чанков в один блок с ограничением по длине.
    """
    parts: list[str] = []
    total_len = 0
    separator = "\n\n"

    for ch in chunks:
        text = (ch.get("text") or "").strip()
        if not text:
            continue

        sep_len = len(separator) if parts else 0
        remaining = max_chars - total_len - sep_len
        if remaining <= 0:
            break

        if len(text) > remaining:
            text = text[:remaining].rstrip()

        if not text:
            break

        if parts:
            total_len += len(separator)

        parts.append(text)
        total_len += len(text)

    if not parts:
        return None

    segment_text = separator.join(parts).strip()
    return segment_text or None
