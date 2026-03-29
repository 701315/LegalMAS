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

from engine.retrieval.tokenization import count_tokens


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

    # Берём первые 1–2 предложения.
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

    Логика:
    1) Если текст и так короткий (меньше max_tokens) и не выглядит как "простыня" —
       возвращаем его как есть.
    2) Иначе:
       - делим на абзацы по двойному переводу строки ("\n\n");
       - внутри абзацев делим на предложения по простому правилу:
         "точка/вопросительный/восклицательный знак + пробел + заглавная буква";
       - собираем чанки подряд из предложений, пока не наберём target_tokens,
         но не превысим max_tokens;
       - между чанками переносим "хвост" предложений (overlap), чтобы LLM
         не теряла контекст на границе чанков.
    """
    import re

    text = (text or "").strip()
    if not text:
        return []

    # Дополнительный предохранитель по длине строки:
    # если текст КРАЙНЕ длинный, не доверяем одному чанку даже если "по словам"
    # он проходит лимит, и всё равно пойдём в разбиение.
    TOO_LONG_CHARS = 10_000
    is_too_long = len(text) > TOO_LONG_CHARS

    # Если весь текст клаузы и так не больше max_tokens и по символам
    # он не выглядит как "простыня", можно не резать.
    if count_tokens(text) <= max_tokens and not is_too_long:
        return [text]

    # 1. Делим текст на абзацы.
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    # 2. Из каждого абзаца извлекаем предложения.
    sentences: List[str] = []
    for p in paragraphs:
        # Очень простой split по предложениям.
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я0-9])", p)
        for s in parts:
            s = s.strip()
            if s:
                sentences.append(s)

    # Если по какой-то причине не смогли выделить предложения — вернём исходный текст.
    if not sentences:
        return [text]

    chunks: List[str] = []
    current_sentences: List[str] = []
    current_tokens = 0

    # "Хвост" предыдущего чанка для overlap.
    overlap_window: List[str] = []

    def _tokens_of(parts: List[str]) -> int:
        return count_tokens(" ".join(parts))

    for sent in sentences:
        sent_tokens = count_tokens(sent)

        # Если сейчас нет активного чанка, но есть overlap — начинаем с overlap.
        if not current_sentences and overlap_window:
            current_sentences.extend(overlap_window)
            current_tokens = _tokens_of(current_sentences)

        # Если предложение само по себе очень длинное (больше max_tokens) и
        # мы сейчас не собираем другой чанк — кладём его отдельным чанком.
        if sent_tokens > max_tokens and not current_sentences:
            chunks.append(sent)
            overlap_window = []
            current_sentences = []
            current_tokens = 0
            continue

        # Если добавление предложения переполнит max_tokens — закрываем текущий чанк.
        if current_sentences and current_tokens + sent_tokens > max_tokens:
            chunks.append(" ".join(current_sentences).strip())
            overlap_window = take_overlap_window(
                current_sentences,
                overlap_ratio=overlap_ratio,
            )
            current_sentences = []
            current_tokens = 0

        # Добавляем предложение в текущий чанк.
        current_sentences.append(sent)
        current_tokens += sent_tokens

        # Если мы уже достигли целевого размера — тоже закрываем чанк.
        if current_tokens >= target_tokens:
            chunks.append(" ".join(current_sentences).strip())
            overlap_window = take_overlap_window(
                current_sentences,
                overlap_ratio=overlap_ratio,
            )
            current_sentences = []
            current_tokens = 0

    # Если после цикла остались предложения — добавляем их последним чанком.
    if current_sentences:
        chunks.append(" ".join(current_sentences).strip())

    # Убираем пустые строки, если вдруг образовались.
    result = [c for c in chunks if c.strip()]

    return result or [text]


def take_overlap_window(
    sentences: List[str],
    overlap_ratio: float,
) -> List[str]:
    """
    Взять "хвост" из последних предложений для overlap между чанками.

    Для непрофессионального программиста:
    - overlap нужен, чтобы кусочек конца предыдущего чанка попал
      в начало следующего. Тогда модель не потеряет контекст на разрыве.
    - overlap_ratio = 0.15 означает "взять примерно 15% последних предложений".
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
    - Клаузы уже содержат путь заголовков (path_titles).
    - Мы группируем клаузы по первым 1–2 заголовкам пути
      и склеиваем их текст в один крупный блок.
    - Это даёт более высокий уровень "разделов", пригодный для
      обзора документа и контекстного retrieval.
    """
    from collections import defaultdict

    # Группируем клаузы по "шапке" пути заголовков (первые 2 уровня).
    groups: dict[tuple[str, ...], list[Dict[str, Any]]] = defaultdict(list)

    for ch in clause_chunks:
        meta = ch.get("metadata") or {}
        path = meta.get("path_titles") or []
        # Берём первые два уровня заголовков как ключ раздела.
        key = tuple(path[:2]) if path else ()
        if not key:
            # Клаузы без явного пути заголовков можно сгруппировать
            # отдельно, но сейчас их просто пропускаем.
            continue
        groups[key].append(ch)

    sections: List[Dict[str, Any]] = []

    for path_key, items in groups.items():
        if not items:
            continue

        # Сортируем клаузы внутри раздела по страницам и UID (если есть),
        # чтобы текст был в правильном порядке.
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
            continue

        tokens = count_tokens(full_text)
        # Если раздел слишком длинный, можно будет в будущем порезать его
        # по абзацам, но сейчас оставим как есть.
        if tokens > max_tokens:
            # На будущее: можно вызвать split_text_to_sized_chunks
            # для full_text и сделать несколько section-под-чанков.
            pass

        section_id = f"{doc_id}:section:{' / '.join(path_key)}"
        start_page = min(pages) if pages else None
        end_page = max(pages) if pages else None
        path_titles = list(path_key)

        metadata = {
            "doc_id": str(doc_id),
            "clause_uid": None,
            "title": path_titles[-1] if path_titles else None,
            "level": 1,
            "path_titles": path_titles,
            "start_page": start_page,
            "end_page": end_page,
            "element_ids": [],
            "token_count": tokens,
            "summary": build_chunk_summary(path_titles, full_text),
        }

        sections.append(
            {
                "id": section_id,
                "text": full_text,
                "metadata": metadata,
            }
        )

    return sections
