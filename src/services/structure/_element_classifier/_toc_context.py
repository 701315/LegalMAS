# src/services/structure/element_classifier/_toc_context.py

"""TOC-контекст для классификатора элементов.

Содержит только локальный контекст, который classifier может определить
самостоятельно (без alignment с headings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.structure.toc_parser import ParsedTOC, TOCBlock, detect_toc_block, parse_toc_entries


@dataclass(slots=True)
class _TocContext:
    """Локальный TOC-контекст для classifier.

    Содержит только то, что classifier может знать самостоятельно:
    - результат detect_toc_block / parse_toc_entries;
    - локальный contextual state (видели ли header, на какой странице).

    НЕ содержит authoritative guard verdict — он придёт из pipeline после alignment.
    """

    toc_block: TOCBlock | None = None
    parsed_toc: ParsedTOC | None = None

    # TOC source element indexes из parsed entries — для contextual enrichment
    toc_source_indexes: set[int] = field(default_factory=set)

    # Contextual state в процессе итерации
    header_seen: bool = False
    header_page: int | None = None
    recent_strong_toc_indexes: list[int] = field(default_factory=list)

    @classmethod
    def build(cls, elements: list[dict[str, Any]]) -> _TocContext:
        """Строит TocContext из elements.

        Вызывается один раз до цикла classify.

        Args:
            elements: Список элементов документа

        Returns:
            Сконфигурированный _TocContext
        """
        toc_block = detect_toc_block(elements)
        parsed_toc = parse_toc_entries(toc_block)

        # Собираем все source_element_indexes из parsed entries.
        # Это позволяет быстро проверить "входит ли элемент в TOC block"
        # без повторного прохода по entries.
        source_indexes: set[int] = set()
        for entry in parsed_toc.entries:
            for idx in entry.source_element_indexes or []:
                if isinstance(idx, int) and idx >= 0:
                    source_indexes.add(idx)

        return cls(
            toc_block=toc_block,
            parsed_toc=parsed_toc,
            toc_source_indexes=source_indexes,
        )
