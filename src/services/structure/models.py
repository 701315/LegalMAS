# src/services/structure/models.py

"""
Data models for document clause tree.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API и viewer.

Архитектура ClauseNode:
- own_element_ids    — элементы только самого пункта (до первого дочернего заголовка)
- subtree_element_ids — элементы пункта + всех потомков
- own_text           — материализованный текст самого пункта
- subtree_text       — материализованный текст всего поддерева
- node_kind          — "leaf" (нет детей) или "section" (есть дети)

Обратная совместимость:
- element_ids сохранён как legacy-алиас для own_element_ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClauseNode:
    """
    Узел дерева документа.

    Для непрофессионального программиста:
    - clause_uid:          номер пункта, например "1", "1.2", "3.1.4"
    - title:               заголовок пункта без номера
    - level:               уровень вложенности (1 = корень, 2 = подпункт и т.д.)
    - node_kind:           "leaf" если нет дочерних пунктов, "section" если есть
    - own_element_ids:     id элементов layout, принадлежащих только этому пункту
    - subtree_element_ids: id элементов этого пункта + всех вложенных пунктов
    - own_text:            текст только этого пункта (без вложенных)
    - subtree_text:        текст этого пункта и всех вложенных пунктов
    - children:            дочерние пункты
    """

    clause_uid: str
    title: str
    level: int

    # "leaf" — конечный пункт (нет детей, содержит реальный текст клаузы)
    # "section" — секция (есть дети, собственный текст обычно минимальный)
    # Заполняется в populate_subtree_element_ids после построения дерева.
    node_kind: str = "leaf"

    # Новый корректный контракт
    own_element_ids: list[str] = field(default_factory=list)
    subtree_element_ids: list[str] = field(default_factory=list)
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1
    children: list["ClauseNode"] = field(default_factory=list)

    # ── Legacy-совместимость ────────────────────────────────────────────────
    # Старый код ожидает node.element_ids — возвращаем own_element_ids.

    @property
    def element_ids(self) -> list[str]:
        """Legacy alias → own_element_ids."""
        return self.own_element_ids

    @element_ids.setter
    def element_ids(self, value: list[str]) -> None:
        """Legacy setter → own_element_ids."""
        self.own_element_ids = list(value or [])


@dataclass
class CrossReference:
    """Перекрёстная ссылка между пунктами документа."""
    source_clause_uid: str
    target_clause_uid: str
    reference_text: str  # например: "см. п. 3.2"


@dataclass
class ClauseTree:
    """
    Корневая структура дерева документа.

    nodes_index — плоский словарь uid → ClauseNode для быстрого поиска
    по всему дереву без рекурсивного обхода.
    Заполняется в pipeline.py после build_clause_hierarchy.
    """

    document_id: str
    root: list[ClauseNode]
    references_index: list[CrossReference]
    structure_confidence: str  # LOW | MEDIUM | HIGH
    degraded: bool = False

    # Плоский индекс uid → node. Позволяет downstream-коду делать
    # tree.nodes_index["3.2.1"] вместо рекурсивного обхода root.
    # При degraded=True — пустой словарь (деградированные чанки не индексируются).
    nodes_index: dict[str, "ClauseNode"] = field(default_factory=dict)

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
            # nodes_index не сериализуем — это runtime-индекс для in-memory use,
            # в JSON он избыточен (дерево уже содержит все узлы через root/children).
        }

    def _node_to_dict(self, node: ClauseNode) -> dict[str, Any]:
        return {
            "clause_uid": node.clause_uid,
            "title": node.title,
            "level": node.level,
            "node_kind": node.node_kind,

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
    

    