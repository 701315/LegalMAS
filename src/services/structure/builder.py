# src/services/structure/builder.py

"""
Structure Builder: parses textlayoutraw elements into a clause tree.

Supports:
  - Numeric: 1., 1.1, 1.1.1
  - Roman: I, II, III, IV (level 1 only)
  - Alphabetic: A., B., a), b) (level 2)
  - Cross-reference detection: см. п. X.X, Art. X
  - Degraded mode: flat chunks when coverage < 60%
"""

import re

from core.config import settings
from core.logging import get_logger
from services.structure.models import ClauseNode, ClauseTree, CrossReference

logger = get_logger(__name__)

_NUMERIC_FULL = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]\s+(.{1,120})")
_ROMAN_L1 = re.compile(
    r"^(I{1,3}|IV|V?I{0,3}|IX|X{0,3}(?:IX|IV|V?I{0,3}))[\.\)]\s+(.{1,120})",
    re.IGNORECASE,
)
_ALPHA = re.compile(
    r"^([A-Fa-f\u0430-\u0436])[\.)\s]\s+(.{1,120})",
)
_CROSS_REF = re.compile(
    r"(?:см\.\s*п\.?|ст\.\s*|пункт\s+|п\.?\s*)(\d+(?:\.\d+)*)|"
    r"(?:Art(?:icle)?\.?\s*)(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)


def _level_from_uid(uid: str) -> int:
    return uid.count(".") + 1


def _parse_element_as_heading(text: str) -> tuple | None:
    stripped = text.strip()
    for pattern in (_NUMERIC_FULL, _ROMAN_L1, _ALPHA):
        m = pattern.match(stripped)
        if m:
            uid, title = m.group(1), m.group(2).strip()
            return uid, title[: settings.STRUCTURE_MAX_CLAUSE_TITLE_LEN]
    return None


class StructureBuilder:
    """Builds a clause tree from textlayoutraw elements."""

    def build(
        self,
        document_id: str,
        elements: list[dict],
    ) -> ClauseTree:
        headings: list[tuple] = []
        for i, el in enumerate(elements):
            text = el.get("text", "")
            parsed = _parse_element_as_heading(text)
            if parsed:
                uid, title = parsed
                headings.append((i, uid, title, el.get("page", 1)))

        if not headings:
            return self._degraded_tree(document_id, elements)

        coverage = self._calculate_coverage(headings, elements)
        confidence, degraded = self._confidence_and_mode(coverage)

        if degraded:
            logger.info(
                "Structure degraded: low coverage",
                document_id=document_id,
                coverage=round(coverage, 3),
            )
            return self._degraded_tree(document_id, elements, coverage)

        root_nodes, references = self._build_tree(headings, elements)
        return ClauseTree(
            document_id=document_id,
            root=root_nodes,
            references_index=references,
            structure_confidence=confidence,
            degraded=False,
        )

    def _build_tree(
        self,
        headings: list,
        elements: list,
    ) -> tuple[list[ClauseNode], list[CrossReference]]:
        nodes: dict[str, ClauseNode] = {}
        root: list[ClauseNode] = []

        for h_idx, (elem_i, uid, title, page) in enumerate(headings):
            next_elem_i = headings[h_idx + 1][0] if h_idx + 1 < len(headings) else len(elements)
            element_ids = [
                elements[j].get("element_id", f"e{j:04d}") for j in range(elem_i, next_elem_i)
            ]
            end_page = elements[next_elem_i - 1].get("page", page) if next_elem_i > elem_i else page

            node = ClauseNode(
                clause_uid=uid,
                title=title,
                level=_level_from_uid(uid),
                element_ids=element_ids,
                start_page=page,
                end_page=end_page,
            )
            nodes[uid] = node

            parent_uid = self._find_parent_uid(uid, nodes)
            if parent_uid and parent_uid in nodes:
                nodes[parent_uid].children.append(node)
            else:
                root.append(node)

        references = self._extract_references(elements, nodes)
        return root, references

    def _find_parent_uid(
        self,
        uid: str,
        nodes: dict,
    ) -> str | None:
        parts = uid.rsplit(".", 1)
        if len(parts) > 1:
            parent = parts[0]
            return parent if parent in nodes else None
        return None

    def _calculate_coverage(
        self,
        headings: list,
        elements: list,
    ) -> float:
        if not elements:
            return 0.0
        assigned = set()
        for h_idx, (elem_i, uid, title, page) in enumerate(headings):
            next_elem_i = headings[h_idx + 1][0] if h_idx + 1 < len(headings) else len(elements)
            for j in range(elem_i, next_elem_i):
                assigned.add(j)
        return len(assigned) / len(elements)

    def _confidence_and_mode(
        self,
        coverage: float,
    ) -> tuple[str, bool]:
        threshold = settings.STRUCTURE_MIN_CLAUSE_COVERAGE
        if coverage < threshold:
            return "LOW", True
        elif coverage < 0.80:
            return "MEDIUM", False
        return "HIGH", False

    def _extract_references(
        self,
        elements: list,
        nodes: dict,
    ) -> list[CrossReference]:
        references: list[CrossReference] = []
        uid_set = set(nodes.keys())

        for el in elements:
            text = el.get("text", "")
            el_id = el.get("element_id", "")
            source_uid = self._element_to_clause(el_id, nodes)
            if not source_uid:
                continue
            for match in _CROSS_REF.finditer(text):
                target = match.group(1) or match.group(2)
                if target and target in uid_set and target != source_uid:
                    references.append(
                        CrossReference(
                            source_clause_uid=source_uid,
                            target_clause_uid=target,
                            reference_text=match.group(),
                        )
                    )
        return references

    def _element_to_clause(
        self,
        element_id: str,
        nodes: dict,
    ) -> str | None:
        for uid, node in nodes.items():
            if element_id in node.element_ids:
                return uid
        return None

    def _degraded_tree(
        self,
        document_id: str,
        elements: list,
        coverage: float = 0.0,
    ) -> ClauseTree:
        chunks: list[ClauseNode] = []
        current_ids: list[str] = []
        current_tokens = 0
        chunk_idx = 1
        max_tokens = settings.STRUCTURE_DEGRADED_CHUNK_TOKENS
        current_start_page: int | None = None
        last_page: int = elements[0].get("page", 1) if elements else 1

        for el in elements:
            text = el.get("text", "")
            tokens = len(text.split())
            page = el.get("page", 1)

            if current_tokens + tokens > max_tokens and current_ids:
                # закрываем текущий чанк
                start_page = current_start_page or last_page
                end_page = last_page
                chunks.append(
                    ClauseNode(
                        clause_uid=str(chunk_idx),
                        title=f"Chunk {chunk_idx}",
                        level=1,
                        element_ids=current_ids,
                        start_page=start_page,
                        end_page=end_page,
                    )
                )
                chunk_idx += 1
                current_ids = []
                current_tokens = 0
                current_start_page = None

            # добавляем элемент в текущий чанк
            current_ids.append(
                el.get("element_id", f"e{len(current_ids):04d}"),
            )
            current_tokens += tokens
            if current_start_page is None:
                current_start_page = page
            last_page = page

        if current_ids:
            start_page = current_start_page or last_page
            end_page = last_page
            chunks.append(
                ClauseNode(
                    clause_uid=str(chunk_idx),
                    title=f"Chunk {chunk_idx}",
                    level=1,
                    element_ids=current_ids,
                    start_page=start_page,
                    end_page=end_page,
                )
            )

        return ClauseTree(
            document_id=document_id,
            root=chunks,
            references_index=[],
            structure_confidence="LOW",
            degraded=True,
        )
