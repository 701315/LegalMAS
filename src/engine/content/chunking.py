# src/engine/content/chunking.py

"""
Утилиты для работы с текстовыми чанками.

Здесь нет работы с БД и MinIO. Только чистые функции:
- построение summary для чанка;
- разбиение текста клаузы на под-чанки (по предложениям и абзацам);
- построение section-чанков из списка clause-чанков.

Sprint 3 contract:
- canonical identity = effective_uid;
- raw_uid остаётся display/reference field;
- scope обязателен как часть identity space;
- section chunks тоже должны иметь canonical identity, если они создаются
  как полноценные retrieval/viewer objects.

Этап 4 — boundary-aware splitting:
- split_text_to_sized_chunks() теперь делегирует в chunk_boundaries.py
  который знает про юридические аббревиатуры, list items и heading no-split rules.
- Старый fallback через простой regex оставлен как резервный путь.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from core.logging import get_logger
from engine.content.chunk_ids import build_section_chunk_id, build_section_effective_uid
from engine.retrieval.tokenization import count_tokens

logger = get_logger(__name__)


def build_chunk_summary(path_titles: list[str], text: str, max_len: int = 200) -> str:
    """
    Построить короткое текстовое summary для чанка.

    Для непрофессионального программиста:
    - summary — это короткое описание чанка;
    - мы склеиваем путь заголовков (path_titles) и первые 1-2 предложения текста;
    - это помогает UI, retrieval и rerank.

    Поведение:
    - если текста нет, возвращаем только путь;
    - если path_titles пустой, summary строится только из текста;
    - длина summary ограничивается max_len.
    """
    path = " / ".join(str(p).strip() for p in (path_titles or []) if str(p).strip())
    text = (text or "").strip()
    if not text:
        return path

    parts = re.split(r"(?<=[.!?])\s+", text)
    head = " ".join(parts[:2]).strip()

    if path and head:
        base = f"{path}: {head}"
    else:
        base = head or path

    if len(base) > max_len:
        return base[: max_len - 1].rstrip() + "…"
    return base


def split_text_to_sized_chunks(
    text: str,
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
) -> list[str]:
    """
    Разбить текст клаузы на несколько меньших под-чанков.

    Этап 4 — boundary-aware splitting:
    - Основной путь: делегируем в chunk_boundaries.split_legal_text_to_segments()
      который знает про юридические аббревиатуры, list items и heading no-split rules.
    - Fallback: если boundary splitter вернул пустой список или упал —
      используем старый простой алгоритм через regex.

    Алгоритм boundary splitter:
    1. Анализирует текст на сегменты: paragraph / list_item / sentence.
    2. Помечает каждый сегмент: is_heading / is_list_item / boundary_after.
    3. Набирает сегменты в чанк пока не достигнем target_tokens.
    4. Разрез делает только в допустимом месте:
       - heading не отрывается от следующего body;
       - список не разрезается посередине пункта;
       - аббревиатуры (Ltd., п., ст.) не считаются концом предложения.

    Важно:
    - Функция не должна терять текст.
    - Если отдельный сегмент сам по себе длиннее max_tokens — он остаётся
      отдельным chunk как forced fallback.
    """
    text = (text or "").strip()
    if not text:
        return []

    if target_tokens <= 0:
        raise ValueError("target_tokens must be > 0")
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    if target_tokens > max_tokens:
        raise ValueError("target_tokens must be <= max_tokens")

    overlap_ratio = max(0.0, min(float(overlap_ratio), 1.0))

    too_long_chars = 10_000
    is_too_long = len(text) > too_long_chars

    if count_tokens(text) <= max_tokens and not is_too_long:
        return [text]

    # ── Этап 4: boundary-aware splitting ─────────────────────────────────────
    # Пробуем новый boundary-aware splitter первым.
    # Он знает про юридические аббревиатуры и no-split правила.
    try:
        from engine.content.chunk_boundaries import split_legal_text_to_segments

        boundary_result = split_legal_text_to_segments(
            text=text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )
        if boundary_result:
            logger.debug(
                "chunking: boundary-aware split used",
                extra={
                    "text_len": len(text),
                    "chunks_count": len(boundary_result),
                    "target_tokens": target_tokens,
                    "max_tokens": max_tokens,
                },
            )
            return boundary_result
    except Exception as boundary_exc:
        logger.warning(
            "chunking: boundary-aware split failed, falling back to simple split",
            extra={
                "text_len": len(text),
                "error": str(boundary_exc),
            },
        )

    # ── Fallback: старый простой алгоритм ────────────────────────────────────
    # Используется если boundary splitter вернул пустой список или упал.
    # Оставлен как safety net — не удалять.
    logger.debug(
        "chunking: using legacy simple split fallback",
        extra={
            "text_len": len(text),
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
        },
    )

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    sentences: list[str] = []
    for p in paragraphs:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я0-9])", p)
        if len(parts) == 1:
            parts = re.split(r"(?<=[.;])\s+(?=[A-ZА-Я0-9])", p)

        for s in parts:
            s = s.strip()
            if s:
                sentences.append(s)

    if not sentences:
        return [text]

    chunks: list[str] = []
    current_sentences: list[str] = []
    current_tokens = 0
    overlap_window: list[str] = []

    def _tokens_of(parts: list[str]) -> int:
        if not parts:
            return 0
        return count_tokens(" ".join(parts))

    for sent in sentences:
        sent_tokens = count_tokens(sent)

        if not current_sentences and overlap_window:
            current_sentences.extend(overlap_window)
            current_tokens = _tokens_of(current_sentences)

        if sent_tokens > max_tokens and not current_sentences:
            chunks.append(sent)
            overlap_window = []
            current_sentences = []
            current_tokens = 0
            continue

        if current_sentences and current_tokens + sent_tokens > max_tokens:
            chunks.append(" ".join(current_sentences).strip())
            overlap_window = take_overlap_window(
                current_sentences,
                overlap_ratio=overlap_ratio,
            )
            current_sentences = list(overlap_window)
            current_tokens = _tokens_of(current_sentences)

        current_sentences.append(sent)
        current_tokens += sent_tokens

        if current_tokens >= target_tokens:
            chunks.append(" ".join(current_sentences).strip())
            overlap_window = take_overlap_window(
                current_sentences,
                overlap_ratio=overlap_ratio,
            )
            current_sentences = []
            current_tokens = 0

    if current_sentences:
        chunks.append(" ".join(current_sentences).strip())

    result = [c.strip() for c in chunks if c and c.strip()]
    return result or [text]


def take_overlap_window(
    sentences: list[str],
    overlap_ratio: float,
) -> list[str]:
    """
    Взять хвост из последних предложений для overlap между chunk'ами.

    overlap_ratio:
    - 0.0 -> overlap нет;
    - 0.15 -> примерно последние 15% предложений;
    - 1.0 -> весь chunk (на практике это обычно бессмысленно, но допустимо).
    """
    if not sentences or overlap_ratio <= 0:
        return []

    overlap_ratio = max(0.0, min(float(overlap_ratio), 1.0))
    n = max(1, int(len(sentences) * overlap_ratio))
    return sentences[-n:]


def build_section_chunks_from_clauses(
    doc_id: str,
    clause_chunks: list[dict[str, Any]],
    max_tokens: int = 1200,
) -> list[dict[str, Any]]:
    """
    Собрать крупные section-чанки на основе списка clause-чанков.

    Sprint 3 invariant:
    - section chunk — это тоже canonical chunk object;
    - у него должен быть effective_uid;
    - scope обязателен;
    - section строится только из clause chunks, у которых уже есть
      валидная canonical identity.

    Группировка:
    - по первому заголовку path_titles[0], то есть по "разделу" документа.
    """
    if not clause_chunks:
        logger.debug(
            "Section builder: no clause chunks provided",
            extra={"doc_id": str(doc_id)},
        )
        return []

    logger.info(
        "Section builder: start building section chunks",
        extra={
            "doc_id": str(doc_id),
            "clause_chunks_count": len(clause_chunks),
            "max_tokens": max_tokens,
        },
    )

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    clauses_without_path_count = 0
    clauses_without_effective_uid_count = 0
    clauses_without_scope_count = 0

    for ch in clause_chunks:
        meta = ch.get("metadata") or {}

        effective_uid = meta.get("effective_uid")
        scope = meta.get("scope")
        path = meta.get("path_titles") or []

        if not effective_uid:
            clauses_without_effective_uid_count += 1
            continue

        if not scope:
            clauses_without_scope_count += 1
            continue

        if not path:
            clauses_without_path_count += 1
            continue

        first_title = str(path[0]).strip()
        if not first_title:
            clauses_without_path_count += 1
            continue

        key = (scope, first_title)
        groups[key].append(ch)

    logger.info(
        "Section builder: groups built",
        extra={
            "doc_id": str(doc_id),
            "groups_count": len(groups),
            "clauses_without_path_count": clauses_without_path_count,
            "clauses_without_effective_uid_count": clauses_without_effective_uid_count,
            "clauses_without_scope_count": clauses_without_scope_count,
        },
    )

    sections: list[dict[str, Any]] = []
    long_section_count = 0
    empty_section_text_count = 0

    for (scope, section_title), items in groups.items():
        if not items:
            continue

        def _sort_key(c: dict[str, Any]) -> tuple:
            meta = c.get("metadata") or {}
            start_page = meta.get("start_page") or 0
            effective_uid = meta.get("effective_uid") or ""
            raw_uid = meta.get("raw_uid") or ""
            return (int(start_page), str(effective_uid), str(raw_uid))

        items_sorted = sorted(items, key=_sort_key)

        texts: list[str] = []
        pages: list[int] = []
        element_ids: list[str] = []
        position_ratios: list[float] = []
        lf_merged: dict[str, Any] = {}

        segment_id = None
        segment_type = None
        segment_title = None
        segment_order = None
        is_primary_segment = None

        for it in items_sorted:
            t = (it.get("text") or "").strip()
            if t:
                texts.append(t)

            meta = it.get("metadata") or {}

            sp = meta.get("start_page")
            ep = meta.get("end_page")
            if isinstance(sp, int):
                pages.append(sp)
            if isinstance(ep, int):
                pages.append(ep)

            for eid in meta.get("element_ids") or []:
                eid = str(eid).strip()
                if eid and eid not in element_ids:
                    element_ids.append(eid)

            pos = meta.get("position_ratio")
            if isinstance(pos, int | float):
                position_ratios.append(float(pos))

            lf = meta.get("language_filter") or {}
            if lf:
                for k, v in lf.items():
                    lf_merged.setdefault(k, v)

            segment_id = segment_id or meta.get("segment_id")
            segment_type = segment_type or meta.get("segment_type")
            segment_title = segment_title or meta.get("segment_title")
            segment_order = (
                segment_order if segment_order is not None else meta.get("segment_order")
            )
            is_primary_segment = (
                is_primary_segment
                if is_primary_segment is not None
                else meta.get("is_primary_segment")
            )

        full_text = "\n\n".join(texts).strip()
        if not full_text:
            empty_section_text_count += 1
            logger.debug(
                "Section builder: group produced empty section text, skipping",
                extra={
                    "doc_id": str(doc_id),
                    "scope": scope,
                    "section_title": section_title,
                    "items_count": len(items_sorted),
                },
            )
            continue

        tokens = count_tokens(full_text)
        if tokens > max_tokens:
            long_section_count += 1
            logger.debug(
                "Section builder: section exceeds max_tokens",
                extra={
                    "doc_id": str(doc_id),
                    "scope": scope,
                    "section_title": section_title,
                    "items_count": len(items_sorted),
                    "token_count": tokens,
                    "max_tokens": max_tokens,
                },
            )

        start_page = min(pages) if pages else None
        end_page = max(pages) if pages else None
        path_titles = [section_title]

        section_effective_uid = build_section_effective_uid(
            scope=scope,
            section_title=section_title,
        )
        section_id = build_section_chunk_id(
            doc_id=doc_id,
            effective_uid=section_effective_uid,
        )

        metadata: dict[str, Any] = {
            "doc_id": str(doc_id),
            "chunk_kind": "section",
            "node_kind": "section",
            "effective_uid": section_effective_uid,
            "raw_uid": None,
            "scope": scope,
            "title": section_title,
            "section_title": section_title,
            "level": 1,
            "path_titles": path_titles,
            "start_page": start_page,
            "end_page": end_page,
            "element_ids": element_ids,
            "token_count": tokens,
            "summary": build_chunk_summary(path_titles, full_text),
        }

        if lf_merged:
            metadata["language_filter"] = lf_merged
        if position_ratios:
            metadata["position_ratio"] = sum(position_ratios) / len(position_ratios)

        if segment_id is not None:
            metadata["segment_id"] = segment_id
        if segment_type is not None:
            metadata["segment_type"] = segment_type
        if segment_title is not None:
            metadata["segment_title"] = segment_title
        if segment_order is not None:
            metadata["segment_order"] = segment_order
        if start_page is not None and end_page is not None:
            metadata["segment_page_range"] = [start_page, end_page]
        if is_primary_segment is not None:
            metadata["is_primary_segment"] = bool(is_primary_segment)

        sections.append(
            {
                "id": section_id,
                "text": full_text,
                "metadata": metadata,
            }
        )

    logger.info(
        "Section builder: finished",
        extra={
            "doc_id": str(doc_id),
            "clause_chunks_count": len(clause_chunks),
            "sections_count": len(sections),
            "groups_count": len(groups),
            "clauses_without_path_count": clauses_without_path_count,
            "clauses_without_effective_uid_count": clauses_without_effective_uid_count,
            "clauses_without_scope_count": clauses_without_scope_count,
            "empty_section_text_count": empty_section_text_count,
            "long_section_count": long_section_count,
        },
    )

    if sections:
        sample = sections[0]
        sample_meta = sample.get("metadata") or {}
        logger.debug(
            "Section builder: sample section",
            extra={
                "doc_id": str(doc_id),
                "section_id": sample.get("id"),
                "effective_uid": sample_meta.get("effective_uid"),
                "scope": sample_meta.get("scope"),
                "title": sample_meta.get("title"),
                "path_titles": sample_meta.get("path_titles"),
                "token_count": sample_meta.get("token_count"),
                "start_page": sample_meta.get("start_page"),
                "end_page": sample_meta.get("end_page"),
                "chunk_kind": sample_meta.get("chunk_kind"),
            },
        )

    return sections
