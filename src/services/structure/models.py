# src/services/structure/models.py

"""
Data models for document clause tree.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API и viewer.

Модели:
- ClauseNode — узел дерева (секция/пункт/подпункт) с:
  clause_uid ("1", "1.1", "II", "A"), заголовком, уровнем, диапазоном страниц,
  списком element_ids из layout и рекурсивным списком children.
- CrossReference — перекрёстная ссылка между пунктами
  (source_clause_uid → target_clause_uid с текстом ссылки, например "см. п. 3.2").
- ClauseTree — корневая структура дерева документа:
  document_id, список корневых ClauseNode, индекс cross‑references и флаги
  качества (structure_confidence: LOW|MEDIUM|HIGH, degraded).

Метод ClauseTree.to_dict() сериализует дерево в JSON‑совместный dict,
который сохраняется как clause_tree_ref и отдаётся через API
для UI‑просмотра структуры документа.
"""

from dataclasses import dataclass, field


@dataclass
class ClauseNode:
    clause_uid: str  # "1", "1.1", "1.1.1", "II", "A"
    title: str  # truncated to MAX_CLAUSE_TITLE_LEN
    level: int  # 1 — top level
    element_ids: list = field(default_factory=list)
    start_page: int = 1
    end_page: int = 1
    children: list = field(default_factory=list)


@dataclass
class CrossReference:
    source_clause_uid: str
    target_clause_uid: str
    reference_text: str  # "см. п. 3.2"


@dataclass
class ClauseTree:
    document_id: str
    root: list  # top-level ClauseNode list
    references_index: list  # list[CrossReference]
    structure_confidence: str  # LOW | MEDIUM | HIGH
    degraded: bool = False

    def to_dict(self) -> dict:
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

    def _node_to_dict(self, node: ClauseNode) -> dict:
        return {
            "clause_uid": node.clause_uid,
            "title": node.title,
            "level": node.level,
            "element_ids": node.element_ids,
            "start_page": node.start_page,
            "end_page": node.end_page,
            "children": [self._node_to_dict(c) for c in node.children],
        }

