# src/engine/content/layout_fallback_chunker.py

"""
Layout Fallback Chunker — Phase 11 Extension.

Строит retrieval-ready chunks напрямую из layout elements,
когда clause tree ненадёжен (Mode C / LAYOUT_FALLBACK).

Принципы:
- heading element начинает новый chunk;
- body elements (text, listitem) накапливаются внутри chunk;
- page break внутри chunk допустим — не разрезаем по страницам;
- при превышении max_tokens chunk закрывается принудительно;
- chunk без текста пропускается;
- НЕ использует clause tree;
- НЕ требует effective_uid из structure pipeline;
- генерирует stable fallback chunk IDs на основе позиции.

Canonical contract:
- chunk_kind = "layout_fallback"
- effective_uid = "<doc_id>:layout_fallback:<page>:<index>"
- chunk ID = "<doc_id>:layout_fallback:<page>:<index>"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from engine.content.chunk_canonicalization import add_summary
from engine.retrieval.tokenization import count_tokens

logger = get_logger(__name__)

# Типы элементов которые начинают новый chunk
_HEADING_TYPES = frozenset({"heading", "section_heading", "title"})

# Типы элементов которые идут в body chunk
_BODY_TYPES = frozenset({"text", "body", "listitem", "list_item", "paragraph", "table"})


@dataclass
class _ChunkAccumulator:
    """Внутренний аккумулятор для сборки одного layout chunk."""

    heading_text: str | None = None
    body_parts: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)
    token_count: int = 0

    def is_empty(self) -> bool:
        return not self.heading_text and not self.body_parts

    def add_element(
        self,
        *,
        text: str,
        element_id: str | None,
        page: int | None,
        is_heading: bool,
    ) -> None:
        if is_heading:
            self.heading_text = text
        else:
            self.body_parts.append(text)

        if page is not None:
            self.pages.append(page)

        if element_id:
            self.element_ids.append(element_id)

        self.token_count += count_tokens(text)

    def build_text(self) -> str:
        parts: list[str] = []
        if self.heading_text:
            parts.append(self.heading_text)
        parts.extend(self.body_parts)
        return "\n\n".join(p for p in parts if p.strip()).strip()

    def start_page(self) -> int | None:
        return min(self.pages) if self.pages else None

    def end_page(self) -> int | None:
        return max(self.pages) if self.pages else None


def _make_fallback_effective_uid(
    doc_id: uuid.UUID,
    *,
    page: int | None,
    index: int,
) -> str:
    page_str = str(page) if page is not None else "0"
    return f"{doc_id}:layout_fallback:{page_str}:{index}"


def _make_fallback_chunk_id(
    doc_id: uuid.UUID,
    *,
    page: int | None,
    index: int,
) -> str:
    return _make_fallback_effective_uid(doc_id, page=page, index=index)


def _flush_accumulator(
    acc: _ChunkAccumulator,
    *,
    doc_id: uuid.UUID,
    chunk_index: int,
    segment_id: str | None,
    segment_type: str,
) -> dict[str, Any] | None:
    """Построить chunk dict из аккумулятора. None если пустой."""
    if acc.is_empty():
        return None

    text = acc.build_text()
    if not text.strip():
        return None

    start_page = acc.start_page()
    effective_uid = _make_fallback_effective_uid(
        doc_id,
        page=start_page,
        index=chunk_index,
    )
    chunk_id = _make_fallback_chunk_id(
        doc_id,
        page=start_page,
        index=chunk_index,
    )

    token_count = count_tokens(text)
    path_titles = [acc.heading_text] if acc.heading_text else []

    metadata: dict[str, Any] = {
        "doc_id": str(doc_id),
        "chunk_kind": "layout_fallback",
        "effective_uid": effective_uid,
        "raw_uid": None,
        "scope": "layout_fallback",
        "node_kind": "layout_fallback",
        "title": acc.heading_text,
        "level": 1,
        "path_titles": path_titles,
        "section_title": acc.heading_text,
        "start_page": start_page,
        "end_page": acc.end_page(),
        "element_ids": list(acc.element_ids),
        "token_count": token_count,
        "retrieval_safe": False,
        "chunking_mode": "layout_fallback",
        "prefer_layout_fallback": True,
        "is_layout_fallback": True,
    }

    if segment_id is not None:
        metadata["segment_id"] = segment_id
    if segment_type:
        metadata["segment_type"] = segment_type

    return {
        "id": chunk_id,
        "text": text,
        "metadata": metadata,
    }


def build_layout_fallback_chunks(
    *,
    doc_id: uuid.UUID,
    layout: dict[str, Any],
    segment_id: str | None = None,
    segment_type: str = "unknown",
    max_tokens: int = 800,
) -> list[dict[str, Any]]:
    """
    Построить layout fallback chunks из layout dict.

    Алгоритм:
    1. Идём по elements последовательно.
    2. Heading element → закрываем текущий аккумулятор, начинаем новый.
    3. Body element → добавляем в текущий аккумулятор.
    4. Если token_count превышает max_tokens → принудительно закрываем.
    5. В конце закрываем последний аккумулятор.

    Args:
        doc_id:       UUID документа.
        layout:       Layout JSON dict.
        segment_id:   ID сегмента (для metadata).
        segment_type: Тип сегмента.
        max_tokens:   Максимальный размер chunk в токенах.

    Returns:
        Список layout fallback chunks.
    """
    elements = layout.get("elements") or []
    if not elements:
        logger.warning(
            "layout_fallback_chunker: empty layout elements",
            extra={
                "doc_id": str(doc_id),
                "segment_id": segment_id,
            },
        )
        return []

    logger.info(
        "layout_fallback_chunker: start",
        extra={
            "doc_id": str(doc_id),
            "segment_id": segment_id,
            "element_count": len(elements),
            "max_tokens": max_tokens,
        },
    )

    chunks: list[dict[str, Any]] = []
    acc = _ChunkAccumulator()
    chunk_index = 0

    for element in elements:
        if not isinstance(element, dict):
            continue

        text = (element.get("text") or "").strip()
        if not text:
            continue

        el_type = (element.get("type") or "").strip().lower()
        element_id = element.get("element_id")
        page = element.get("page")
        if not isinstance(page, int):
            page = None

        is_heading = el_type in _HEADING_TYPES
        is_body = el_type in _BODY_TYPES or el_type == ""

        if not is_heading and not is_body:
            # Неизвестный тип — трактуем как body
            is_body = True

        # Heading начинает новый chunk
        if is_heading:
            # Закрыть текущий аккумулятор если он не пустой
            if not acc.is_empty():
                chunk = _flush_accumulator(
                    acc,
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    segment_id=segment_id,
                    segment_type=segment_type,
                )
                if chunk is not None:
                    chunks.append(chunk)
                    chunk_index += 1

            acc = _ChunkAccumulator()
            acc.add_element(
                text=text,
                element_id=element_id,
                page=page,
                is_heading=True,
            )

        elif is_body:
            # Проверяем не превысим ли max_tokens
            incoming_tokens = count_tokens(text)

            if (
                not acc.is_empty()
                and acc.token_count + incoming_tokens > max_tokens
            ):
                # Принудительно закрываем текущий аккумулятор
                chunk = _flush_accumulator(
                    acc,
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    segment_id=segment_id,
                    segment_type=segment_type,
                )
                if chunk is not None:
                    chunks.append(chunk)
                    chunk_index += 1

                # Начинаем новый без heading
                acc = _ChunkAccumulator()

            acc.add_element(
                text=text,
                element_id=element_id,
                page=page,
                is_heading=False,
            )

    # Закрыть последний аккумулятор
    if not acc.is_empty():
        chunk = _flush_accumulator(
            acc,
            doc_id=doc_id,
            chunk_index=chunk_index,
            segment_id=segment_id,
            segment_type=segment_type,
        )
        if chunk is not None:
            chunks.append(chunk)

    # Добавить summary
    chunks = add_summary(chunks)

    logger.info(
        "layout_fallback_chunker: done",
        extra={
            "doc_id": str(doc_id),
            "segment_id": segment_id,
            "element_count": len(elements),
            "chunks_count": len(chunks),
        },
    )

    return chunks


