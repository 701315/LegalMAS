# src/services/structure/crossrefs.py

"""
Извлечение перекрёстных ссылок между пунктами документа.

Задача этого модуля:
- не строить дерево;
- не парсить заголовки;
- а только искать в тексте ссылки вида "см. п. 3.2", "ст. 5", "Clause 7" и т.п.
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from services.structure.models import ClauseNode, CrossReference


logger = get_logger(__name__)


_CROSS_REF = re.compile(
    r"(?:см\.\s*п\.?|ст\.\s*|пункт\s+|п\.?\s*)(\d+(?:\.\d+)*)"
    r"|(?:Art(?:icle)?\.?\s*)(\d+(?:\.\d+)*)"
    r"|(?:Sec(?:tion)?\.?\s+)(\d+(?:\.\d+)*)"
    r"|(?:Clause\s+)(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)


def extract_references(
    elements: list[dict],
    element_to_uid: dict[str, str],
    nodes: dict[str, ClauseNode],
    *,
    document_id: str,
    stable_element_id_resolver,
) -> list[CrossReference]:
    """
    Найти перекрёстные ссылки между клаузами.

    elements:
        layout-элементы (text_layout_raw.elements)
    element_to_uid:
        mapping element_id -> clause_uid, построенный при сборке дерева
    nodes:
        индекс ClauseNode по uid
    stable_element_id_resolver:
        функция/метод, превращающая элемент + индекс в стабильный element_id
        (обычно StructureBuilder._stable_element_id)

    Возвращает список CrossReference.
    """
    references: list[CrossReference] = []
    uid_set = set(nodes.keys())
    seen_refs: set[tuple[str, str, str]] = set()

    for idx, el in enumerate(elements):
        try:
            text = el.get("text", "")
            stable_el_id = stable_element_id_resolver(el, idx)
            source_uid = element_to_uid.get(stable_el_id)
            if not source_uid:
                continue

            for match in _CROSS_REF.finditer(text):
                target = (
                    match.group(1)
                    or match.group(2)
                    or match.group(3)
                    or match.group(4)
                )
                if not target or target == source_uid:
                    continue
                if target not in uid_set:
                    continue

                key = (source_uid, target, match.group())
                if key in seen_refs:
                    continue

                seen_refs.add(key)
                references.append(
                    CrossReference(
                        source_clause_uid=source_uid,
                        target_clause_uid=target,
                        reference_text=match.group(),
                    )
                )
        except re.error as e:
            logger.warning(
                "STRUCTURE cross-ref regex error",
                extra={
                    "document_id": document_id,
                    "element_index": idx,
                    "error": str(e),
                },
            )
            continue
        except Exception as e:
            logger.error(
                "STRUCTURE cross-ref unexpected error",
                extra={
                    "document_id": document_id,
                    "element_index": idx,
                    "error": str(e),
                },
            )
            continue

    return references

