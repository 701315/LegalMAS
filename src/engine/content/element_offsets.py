# src/engine/content/element_offsets.py
"""
Утилиты для element-level позиционирования в тексте чанка.

Вынесено из engine/checks/citation_resolver.py для устранения
кросс-слойной зависимости engine.content -> engine.checks.

Инварианты:
  - element_ids могут приходить в произвольном порядке
    (см. docstring ClauseTreeBuilder.build_element_index) -
    сортировка по _seq обязательна.
  - _ELEMENT_SEPARATOR = "\\n\\n" совпадает с materialize_text_from_element_ids.
"""
from __future__ import annotations

from typing import Any

_ELEMENT_SEPARATOR = "\n\n"


def compute_element_offsets(
    layout_elements: list[dict[str, Any]],
    source_text: str,
) -> tuple[list[tuple[str, int, int]], bool]:
    """
    Воспроизвести логику materialize_text_from_element_ids и вернуть
    offsets каждого непустого элемента в source_text.

    ВНИМАНИЕ: работает против ПРЕ-нормализованного текста
    (выход materialize_text_from_element_ids ДО normalize_clause_chunk_text).

    Для offsets против нормализованного текста (leaf.text / subtext)
    используйте compute_element_offsets_for_normalized_text.

    Returns:
        ([(element_id, start, end), ...], offsets_ok)
    """
    sorted_els = sorted(
        [el for el in layout_elements if el.get("element_id")],
        key=lambda el: int(el.get("_seq", 0)),
    )

    pieces: list[tuple[str, str | None]] = []
    last_page: int | None = None

    for el in sorted_els:
        text = (el.get("text") or "").strip()
        page = el.get("page")

        if not text:
            if isinstance(page, int):
                last_page = page
            continue

        if (
            last_page is not None
            and isinstance(page, int)
            and page != last_page
        ):
            pieces.append(("", None))

        pieces.append((text, str(el["element_id"])))
        last_page = page if isinstance(page, int) else last_page

    if not pieces:
        return [], len(source_text) == 0

    offsets: list[tuple[str, int, int]] = []
    offset = 0
    for i, (text, el_id) in enumerate(pieces):
        if i > 0:
            offset += len(_ELEMENT_SEPARATOR)
        start = offset
        offset += len(text)
        end = offset
        if el_id is not None:
            offsets.append((el_id, start, end))

    return offsets, offset == len(source_text)


def span_to_element_ids(
    span_start: int,
    span_end: int,
    element_offsets: list[tuple[str, int, int]],
) -> list[str]:
    """
    Найти element_ids, чьи [start, end) пересекаются со span.

    Span в координатах source_text; offsets тоже в source_text.
    Возвращает element_ids в порядке следования в документе.
    """
    result: list[str] = []
    for el_id, start, end in element_offsets:
        if end > span_start and start < span_end:
            result.append(el_id)
    return result


def _strip_element_lines(text: str) -> str:
    """
    Применить ту же построчную нормализацию, что делает
    normalize_clause_chunk_text: strip каждой строки, collapse
    consecutive пустых строк в одну, trim ведущих/хвостовых.

    Это гарантирует, что элемент найдётся в нормализованном тексте
    как непрерывная подстрока.
    """
    if not text:
        return ""
    lines = (text or "").splitlines()
    out: list[str] = []
    prev_empty = True
    for raw in lines:
        line = raw.strip()
        if not line:
            if prev_empty:
                continue
            out.append("")
            prev_empty = True
        else:
            out.append(line)
            prev_empty = False
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def compute_element_offsets_for_normalized_text(
    layout_elements: list[dict[str, Any]],
    source_text: str,
) -> tuple[list[tuple[str, int, int]], bool]:
    """
    Найти offsets элементов в НОРМАЛИЗОВАННОМ тексте.

    Используется для leaf.text и sub-chunk text (после
    normalize_clause_chunk_text). Поисковый подход: каждый элемент
    находится последовательно в source_text в порядке _seq.

    Работает одинаково для leaf и sub-chunk: если source_text -
    sub-chunk text, offsets сразу в его координатах.

    Returns:
        ([(element_id, start, end), ...], ok)
        ok = True если ВСЕ непустые элементы найдены в порядке документа.
        ok = False если хотя бы один не найден - caller должен
        отказаться от element_spans для этого чанка.
    """
    sorted_els = sorted(
        [el for el in layout_elements if el.get("element_id")],
        key=lambda el: int(el.get("_seq", 0)),
    )

    offsets: list[tuple[str, int, int]] = []
    cursor = 0
    for el in sorted_els:
        eid = el.get("element_id")
        if not eid:
            continue
        el_text_norm = _strip_element_lines(el.get("text") or "")
        if not el_text_norm:
            continue
        pos = source_text.find(el_text_norm, cursor)
        if pos < 0:
            return [], False
        offsets.append((str(eid), pos, pos + len(el_text_norm)))
        cursor = pos + len(el_text_norm)

    return offsets, True
