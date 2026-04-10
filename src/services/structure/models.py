# src/services/structure/models.py

"""
Data models for document clause tree.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API и viewer.

Новая архитектура:
- ClauseNode теперь различает:
  * own_element_ids — только элементы самого пункта до первого дочернего заголовка;
  * subtree_element_ids — элементы пункта + всех его потомков;
  * own_text — материализованный текст самого пункта;
  * subtree_text — материализованный текст всего блока целиком.
- Это нужно для корректной работы:
  * structure viewer,
  * leaf chunks,
  * block/section chunks,
  * retrieval по родительским и дочерним пунктам.

Обратная совместимость:
- Поле element_ids пока сохраняем как legacy-алиас.
- На переходный период element_ids сериализуется как own_element_ids,
  чтобы старый код не ломался мгновенно.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClauseNode:
    """
    Узел дерева документа.

    Для непрофессионального программиста:
    - clause_uid: номер пункта, например "1", "1.2", "3.1.4"
    - title: заголовок пункта без номера
    - level: уровень вложенности
    - own_element_ids: элементы layout, относящиеся только к самому пункту
      до первого дочернего подпункта
    - subtree_element_ids: элементы самого пункта + всех потомков
    - own_text: текст только самого пункта
    - subtree_text: текст всего поддерева пункта
    - children: дочерние пункты
    """

    clause_uid: str
    title: str
    level: int

    # Новый корректный контракт
    own_element_ids: list[str] = field(default_factory=list)
    subtree_element_ids: list[str] = field(default_factory=list)
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1
    children: list["ClauseNode"] = field(default_factory=list)

    # Legacy-совместимость:
    # старый код ожидает node.element_ids
    @property
    def element_ids(self) -> list[str]:
        """
        Legacy alias.

        На переходный период возвращаем own_element_ids, потому что старый код
        чаще всего ожидает "текст самого узла", а не всё поддерево.
        """
        return self.own_element_ids

    @element_ids.setter
    def element_ids(self, value: list[str]) -> None:
        """
        Legacy setter.

        Если старый код присваивает element_ids, считаем, что это own_element_ids.
        subtree_element_ids в таком случае можно будет достроить позже
        в StructureBuilder.
        """
        self.own_element_ids = list(value or [])


@dataclass
class CrossReference:
    """
    Перекрёстная ссылка между пунктами документа.
    """

    source_clause_uid: str
    target_clause_uid: str
    reference_text: str  # "см. п. 3.2"


@dataclass
class ClauseTree:
    """
    Корневая структура дерева документа.
    """

    document_id: str
    root: list[ClauseNode]
    references_index: list[CrossReference]
    structure_confidence: str  # LOW | MEDIUM | HIGH
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "root": [self._node_to_dict(n) for n in self.root],
            "references_index": [
                {
                    "source": r.source_clause_uid,
                    "target": r.target_clause_uid,
                    "text": r.reference_text,
                }
                for r in self.references_index
            ],
            "structure_confidence": self.structure_confidence,
            "degraded": self.degraded,
        }

    def _node_to_dict(self, node: ClauseNode) -> dict[str, Any]:
        return {
            "clause_uid": node.clause_uid,
            "title": node.title,
            "level": node.level,

            # Новый контракт
            "own_element_ids": node.own_element_ids,
            "subtree_element_ids": node.subtree_element_ids,
            "own_text": node.own_text,
            "subtree_text": node.subtree_text,

            # Legacy-совместимость
            "element_ids": node.element_ids,

            "start_page": node.start_page,
            "end_page": node.end_page,
            "children": [self._node_to_dict(c) for c in node.children],
        }