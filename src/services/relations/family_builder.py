"""
Family Builder Service.

Groups related documents into families:
- Each family has one master document (SPA, SHA, Loan, etc.)
- Related documents: appendices, amendments, drafts, counterparts
- Uses BFS traversal to collect all connected documents
- Max family size and max hops limits prevent runaway grouping

The family is used by the Runner to provide cross-document context
when checking conditions (e.g., appendix modifies a clause in master).

Algorithm:
1. Find master candidates (documents with master doc_types and no
   incoming "master" relations)
2. For each master: BFS through all relations (max N hops)
3. Collect all reachable documents into one family
4. Handle orphans (documents not in any family)
"""

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

from src.classifiers.yaml_registry import YAMLRegistry
from src.core.config import settings
from src.core.logging import get_logger
from src.services.relations.models import DetectedRelation, FamilyGroup

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
        documents: List[Dict],
        relations: List[DetectedRelation],
    ) -> List[FamilyGroup]:
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

        assigned: Set[str] = set()
        families: List[FamilyGroup] = []

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
                if r.source_doc_id in family_members
                and r.target_doc_id in family_members
            ]

            family = FamilyGroup(
                master_doc_id=master_id,
                master_doc_type=master_doc.get("doc_type", ""),
                member_doc_ids=list(family_members),
                relations=family_relations,
                master_classification_level=master_doc.get(
                    "classification_level"
                ),
                master_yaml_available=master_doc.get(
                    "yaml_instruction_available", False
                ),
                master_applicable_triggers=master_doc.get(
                    "applicable_triggers", []
                ),
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
        documents: List[Dict],
        relations: List[DetectedRelation],
    ) -> List[Dict]:
        """
        Find master document candidates.

        When multiple candidates exist, sort by classification_level
        descending (L3 > L2 > L1 > L0) so highest-quality classified
        documents become masters first.
        """
        has_master: Set[str] = set()
        for rel in relations:
            if rel.relation_type == "master":
                has_master.add(rel.source_doc_id)

        level_priority = {
            level: idx
            for idx, level in enumerate(
                settings.FAMILY_CLASSIFICATION_LEVEL_PRIORITY
            )
        }

        masters: List[Dict] = []
        non_masters: List[Dict] = []

        for doc in documents:
            doc_type = doc.get("doc_type", "")
            doc_id = doc["id"]
            if doc_type in self.master_doc_types and doc_id not in has_master:
                masters.append(doc)
            else:
                non_masters.append(doc)

        # Sort masters by classification_level descending
        masters.sort(
            key=lambda d: level_priority.get(
                d.get("classification_level", "L0"), 0
            ),
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
        relations: List[DetectedRelation],
    ) -> Dict[str, Set[str]]:
        """
        Build undirected adjacency list for relations graph.

        Each relation connects source and target in both directions
        for purposes of family grouping.
        """
        adjacency: Dict[str, Set[str]] = defaultdict(set)

        for rel in relations:
            s = rel.source_doc_id
            t = rel.target_doc_id
            adjacency[s].add(t)
            adjacency[t].add(s)

        return adjacency

    def _bfs_collect(
        self,
        start_id: str,
        adjacency: Dict[str, Set[str]],
        assigned: Set[str],
    ) -> Set[str]:
        """
        Collect all documents reachable from start_id using BFS,
        with limits on max_hops and max_family_size.
        """
        visited: Set[str] = set()
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
