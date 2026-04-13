# src/engine/content/chunking.py

"""
Утилиты для работы с текстовыми чанками.

Здесь нет работы с БД и MinIO. Только чистые функции:
- построение summary для чанка;
- разбиение текста клаузы на под-чанки (по предложениям и абзацам);
- построение "section"-чанков из списка клауз.
"""

from __future__ import annotations

from typing import Any, Dict, List
from engine.content.clause_tree_builder import ClauseTreeBuilder
from core.logging import get_logger
from engine.retrieval.tokenization import count_tokens

logger = get_logger(__name__)


def build_chunk_summary(path_titles: List[str], text: str, max_len: int = 200) -> str:
    """
    Построить короткое текстовое summary для чанка.

    Для непрофессионального программиста:
    - summary — это короткое описание чанка.
    - Мы склеиваем путь заголовков (path_titles) и первые 1–2 предложения текста.
    - Это нужно для:
      * более понятного UI,
      * более качественного поиска (retrieval/rerank по summary).
    """
    import re

    path = " / ".join(path_titles) if path_titles else ""
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
        return base[:max_len]
    return base


def split_text_to_sized_chunks(
    text: str,
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
) -> List[str]:
    """
    Режет текст клаузы на несколько меньших текстов (под-чанков).
    """
    import re

    text = (text or "").strip()
    if not text:
        return []

    TOO_LONG_CHARS = 10_000
    is_too_long = len(text) > TOO_LONG_CHARS

    if count_tokens(text) <= max_tokens and not is_too_long:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    sentences: List[str] = []
    for p in paragraphs:
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я0-9])", p)
        for s in parts:
            s = s.strip()
            if s:
                sentences.append(s)

    if not sentences:
        return [text]

    chunks: List[str] = []
    current_sentences: List[str] = []
    current_tokens = 0

    overlap_window: List[str] = []

    def _tokens_of(parts: List[str]) -> int:
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
            current_sentences = []
            current_tokens = 0

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

    result = [c for c in chunks if c.strip()]

    return result or [text]


def take_overlap_window(
    sentences: List[str],
    overlap_ratio: float,
) -> List[str]:
    """
    Взять "хвост" из последних предложений для overlap между чанками.
    """
    if not sentences or overlap_ratio <= 0:
        return []

    n = max(1, int(len(sentences) * overlap_ratio))
    return sentences[-n:]


def build_section_chunks_from_clauses(
    doc_id: str,
    clause_chunks: List[Dict[str, Any]],
    max_tokens: int = 1200,
) -> List[Dict[str, Any]]:
    """
    Собрать "крупные" section-чанки на основе клауз.

    Для непрофессионального программиста:
    - У каждой клаузы есть path_titles — список заголовков от корня до листа.
      Например:
        ["ПРЕДМЕТ ДОГОВОРА", "1 В течение 5 (пяти) рабочих дней ..."].
    - Мы хотим сделать один крупный блок на каждый РАЗДЕЛ договора.
      Раздел — это как раз верхний заголовок path_titles[0]:
        "ПРЕДМЕТ ДОГОВОРА",
        "ЦЕНА ЗЕМЕЛЬНОГО УЧАСТКА...",
        "ГАРАНТИИ" и т.п.
    - Поэтому:
      * группируем клаузы только по ПЕРВОМУ заголовку пути (path_titles[0]);
      * склеиваем тексты всех клауз из группы в один большой блок.
    - Такой блок и есть "section"-чанк, который удобно показывать во viewer
      и использовать для высокоуровневого поиска.
    """
    from collections import defaultdict

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

    # Группы по верхнему заголовку раздела.
    # Ключом будет кортеж из одного элемента: (path_titles[0],)
    groups: dict[tuple[str, ...], list[Dict[str, Any]]] = defaultdict(list)

    clauses_without_path_count = 0

    for ch in clause_chunks:
        meta = ch.get("metadata") or {}
        path = meta.get("path_titles") or []
        # Если у клаузы нет path_titles — мы не знаем, к какому разделу её отнести.
        if not path:
            clauses_without_path_count += 1
            continue

        # Берём только верхний заголовок раздела.
        key = (str(path[0]).strip(),)
        groups[key].append(ch)

    logger.info(
        "Section builder: groups built",
        extra={
            "doc_id": str(doc_id),
            "groups_count": len(groups),
            "clauses_without_path_count": clauses_without_path_count,
        },
    )

    sections: List[Dict[str, Any]] = []

    long_section_count = 0
    empty_section_text_count = 0

    for path_key, items in groups.items():
        if not items:
            continue

        # Сортируем клаузы внутри раздела по странице и номеру клаузы,
        # чтобы текст секции шёл в правильном порядке.
        def _sort_key(c: Dict[str, Any]) -> tuple:
            meta = c.get("metadata") or {}
            start_page = meta.get("start_page") or 0
            clause_uid = meta.get("clause_uid") or ""
            return (int(start_page), str(clause_uid))

        items_sorted = sorted(items, key=_sort_key)

        texts: List[str] = []
        pages: List[int] = []

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

        full_text = "\n\n".join(texts).strip()
        if not full_text:
            empty_section_text_count += 1
            logger.debug(
                "Section builder: group produced empty section text, skipping",
                extra={
                    "doc_id": str(doc_id),
                    "path_key": list(path_key),
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
                    "path_key": list(path_key),
                    "items_count": len(items_sorted),
                    "token_count": tokens,
                    "max_tokens": max_tokens,
                },
            )
            # Пока сознательно не режем full_text.

        # Идентификатор секции строим из doc_id и верхнего заголовка.
        section_id = f"{doc_id}:section:{' / '.join(path_key)}"
        start_page = min(pages) if pages else None
        end_page = max(pages) if pages else None

        # path_titles для секции — это один элемент: название раздела.
        path_titles = [path_key[0]]

        metadata = {
            "doc_id": str(doc_id),
            # clause_uid для секции оставляем None — это не одна конкретная клауза,
            # а логический блок, объединяющий несколько клауз.
            "clause_uid": None,
            # Заголовок секции — верхний заголовок раздела (например, "ГАРАНТИИ").
            "title": path_titles[0],
            # Уровень 1 — "крупный" блок.
            "level": 1,
            "path_titles": path_titles,
            "start_page": start_page,
            "end_page": end_page,
            # Пока не восстанавливаем element_ids, потому что секция объединяет
            # несколько клауз. При необходимости можно будет добавить их позже.
            "element_ids": [],
            "token_count": tokens,
            "summary": build_chunk_summary(path_titles, full_text),
        }

        # Собираем общие флаги language_filter и средний position_ratio по клаузам.
        lf_merged: dict[str, Any] = {}
        positions: list[float] = []

        for it in items_sorted:
            meta_it = it.get("metadata") or {}
            lf_it = meta_it.get("language_filter") or {}
            if lf_it:
                for k, v in lf_it.items():
                    lf_merged.setdefault(k, v)

            pos_it = meta_it.get("position_ratio")
            if isinstance(pos_it, (int, float)):
                positions.append(float(pos_it))

        if lf_merged:
            metadata["language_filter"] = lf_merged
        if positions:
            metadata["position_ratio"] = sum(positions) / len(positions)

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
                "title": sample_meta.get("title"),
                "path_titles": sample_meta.get("path_titles"),
                "token_count": sample_meta.get("token_count"),
                "start_page": sample_meta.get("start_page"),
                "end_page": sample_meta.get("end_page"),
            },
        )

    return sections

    