# src/services/relations/family_builder.py

"""
Builds document families from detected междокументные связи.

Сервис группирует связанные документы сделки в FamilyGroup, где у каждой
семьи есть master-документ (например, SPA, SHA, Loan Agreement), а остальные
участники семьи — приложения, amendments, drafts, counterparts и другие
связанные документы.

Как работает:
- загружает список master doc types из YAMLRegistry, а если он недоступен —
  использует settings.FAMILY_MASTER_DOC_TYPES;
- выбирает master-кандидатов среди documents: документы с master doc_type,
  которые не выступают source в relation_type == "master";
- сортирует master-кандидатов по приоритету classification_level
  (например, L3 > L2 > L1 > L0), чтобы сначала строить семьи вокруг
  наиболее качественно классифицированных документов;
- строит неориентированный граф relations и для каждого master запускает BFS,
  собирая все достижимые документы с ограничениями RELATIONS_MAX_HOPS и
  RELATIONS_MAX_FAMILY_SIZE;
- формирует FamilyGroup с master_doc_id, member_doc_ids, relations и
  classification metadata master-документа;
- документы, не попавшие ни в одну семью, остаются orphan и в результат
  не включаются.

Назначение:
- семьи используются downstream в Runner, чтобы учитывать cross-document context
  при проверках, когда связанные документы уточняют, изменяют или дополняют
  master-документ.
"""

from collections import defaultdict, deque

from classifiers.yaml_registry import YAMLRegistry
from core.config import settings
from core.logging import get_logger
from services.relations.models import DetectedRelation, FamilyGroup

logger = get_logger(__name__)


class FamilyBuilder:
    def __init__(self) -> None:
        self.max_hops = settings.RELATIONS_MAX_HOPS
        self.max_family_size = settings.RELATIONS_MAX_FAMILY_SIZE
        self.master_doc_types = self._load_master_doc_types()

    def _load_master_doc_types(self) -> list[str]:
        """
        Primary: master doc types from YAMLRegistry.
        Fallback: FAMILY_MASTER_DOC_TYPES from config.
        """
        try:
            registry = YAMLRegistry.get_instance()
            yaml_master_types = registry.get_master_doc_types()
            if yaml_master_types:
                logger.debug(
                    "FamilyBuilder: master_doc_types from YAML",
                    types=yaml_master_types,
                    count=len(yaml_master_types),
                )
                return yaml_master_types
        except Exception as e:
            logger.debug(
                "FamilyBuilder: YAML registry unavailable, using config fallback",
                error=str(e),
            )

        return list(settings.FAMILY_MASTER_DOC_TYPES)

    def build_families(
        self,
        documents: list[dict],
        relations: list[DetectedRelation],
    ) -> list[FamilyGroup]:
        """
        Build family groups from documents and relations.

        Args:
            documents: List of document dicts with keys:
                - id: str
                - doc_type: str
                - filename: str
                - classification_level: str ("L0"…"L3")
                - yaml_instruction_available: bool
                - applicable_triggers: list[str]
            relations: List of DetectedRelation objects

        Returns:
            List of FamilyGroup objects (each document appears
            in at most one family)
        """
        if not documents:
            return []
        if not relations:
            logger.info("No relations to build families from")
            return []

        adjacency = self._build_adjacency(relations)
        masters = self._find_masters(documents, relations)

        assigned: set[str] = set()
        families: list[FamilyGroup] = []

        for master_doc in masters:
            master_id = master_doc["id"]
            if master_id in assigned:
                continue

            family_members = self._bfs_collect(
                start_id=master_id,
                adjacency=adjacency,
                assigned=assigned,
            )

            if len(family_members) < 2:
                continue

            family_relations = [
                r
                for r in relations
                if r.source_doc_id in family_members and r.target_doc_id in family_members
            ]

            family = FamilyGroup(
                master_doc_id=master_id,
                master_doc_type=master_doc.get("doc_type", ""),
                member_doc_ids=list(family_members),
                relations=family_relations,
                master_classification_level=master_doc.get("classification_level"),
                master_yaml_available=master_doc.get("yaml_instruction_available", False),
                master_applicable_triggers=master_doc.get("applicable_triggers", []),
            )
            families.append(family)
            assigned.update(family_members)

        logger.info(
            "Family building complete",
            total_documents=len(documents),
            families_created=len(families),
            documents_in_families=len(assigned),
            orphan_documents=len(documents) - len(assigned),
        )
        return families

    def _find_masters(
        self,
        documents: list[dict],
        relations: list[DetectedRelation],
    ) -> list[dict]:
        """
        Find master document candidates.

        When multiple candidates exist, sort by classification_level
        descending (L3 > L2 > L1 > L0) so highest-quality classified
        documents become masters first.
        """
        has_master: set[str] = set()
        for rel in relations:
            if rel.relation_type == "master":
                has_master.add(rel.source_doc_id)

        level_priority = {
            level: idx for idx, level in enumerate(settings.FAMILY_CLASSIFICATION_LEVEL_PRIORITY)
        }

        masters: list[dict] = []
        non_masters: list[dict] = []

        for doc in documents:
            doc_type = doc.get("doc_type", "")
            doc_id = doc["id"]
            if doc_type in self.master_doc_types and doc_id not in has_master:
                masters.append(doc)
            else:
                non_masters.append(doc)

        # Sort masters by classification_level descending
        masters.sort(
            key=lambda d: level_priority.get(d.get("classification_level", "L0"), 0),
            reverse=True,
        )

        # Fallback: if no explicit masters, take pure targets in relation graph
        if not masters:
            target_ids = {r.target_doc_id for r in relations}
            source_ids = {r.source_doc_id for r in relations}
            pure_targets = target_ids - source_ids
            for doc in documents:
                if doc["id"] in pure_targets:
                    masters.append(doc)

        return masters

    def _build_adjacency(
        self,
        relations: list[DetectedRelation],
    ) -> dict[str, set[str]]:
        """
        Build undirected adjacency list for relations graph.

        Each relation connects source and target in both directions
        for purposes of family grouping.
        """
        adjacency: dict[str, set[str]] = defaultdict(set)

        for rel in relations:
            s = rel.source_doc_id
            t = rel.target_doc_id
            adjacency[s].add(t)
            adjacency[t].add(s)

        return adjacency

    def _bfs_collect(
        self,
        start_id: str,
        adjacency: dict[str, set[str]],
        assigned: set[str],
    ) -> set[str]:
        """
        Collect all documents reachable from start_id using BFS,
        with limits on max_hops and max_family_size.
        """
        visited: set[str] = set()
        queue = deque([(start_id, 0)])

        while queue and len(visited) < self.max_family_size:
            current_id, depth = queue.popleft()
            if current_id in visited:
                continue

            visited.add(current_id)

            if depth >= self.max_hops:
                continue

            for neighbor in adjacency.get(current_id, []):
                if neighbor in visited or neighbor in assigned:
                    continue
                queue.append((neighbor, depth + 1))

        return visited
