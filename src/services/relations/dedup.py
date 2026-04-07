# src/services/relations/dedup.py

"""
Exact deduplication of documents within a single deal.

Сервис ищет документы с идентичным содержимым по `sha256_file` и
формирует результат дедупликации до запуска relation detection
и family building.

Как работает:
- группирует документы по SHA256-хэшу файла;
- в каждой группе с одинаковым хэшем сортирует документы по `created_at`;
- первый документ в группе считается оригиналом (kept),
  остальные — точными дубликатами;
- собирает DedupResult:
  total_documents, exact_duplicates, duplicate_groups,
  kept_doc_ids, marked_doc_ids;
- для каждого дубликата создаёт DetectedRelation c:
  relation_type="version", confidence=1.0,
  method=RelationDetectionMethod.EXACT_HASH,
  source_doc_id=duplicate, target_doc_id=original.

Назначение:
- убрать точные копии из дальнейшего анализа как отдельные сущности;
- сохранить формальную связь duplicate → original для downstream‑логики;
- дать relation/family processing уже очищенный и размеченный набор документов.

Главная точка входа:
- find_duplicates(documents) -> tuple[DedupResult, list[DetectedRelation]]
"""


from collections import defaultdict

from core.logging import get_logger
from services.relations.models import (
    DedupResult,
    DetectedRelation,
    RelationDetectionMethod,
)

logger = get_logger(__name__)


class ExactDedupService:
    """Finds and summarizes exact duplicate documents within a deal."""

    def find_duplicates(
        self,
        documents: list[dict],
    ) -> tuple[DedupResult, list[DetectedRelation]]:
        """
        Find exact duplicates by SHA256 hash.

        Args:
            documents: List of document dicts with keys:
                - id: str (document UUID)
                - sha256_file: str (SHA256 hash of file content)
                - filename: str
                - created_at: datetime or ISO string (for ordering)

        Returns:
            Tuple of (DedupResult, list of DetectedRelation for duplicates)
        """
        result = DedupResult(total_documents=len(documents))
        relations: list[DetectedRelation] = []

        if not documents:
            return result, relations

        # Group documents by SHA256
        hash_groups: dict[str, list[dict]] = defaultdict(list)
        for doc in documents:
            sha256 = doc.get("sha256_file")
            if sha256:
                hash_groups[sha256].append(doc)

        # Process groups with more than one document
        for sha256, group in hash_groups.items():
            if len(group) <= 1:
                continue

            # Sort by creation date — first created is the "original"
            sorted_group = sorted(
                group,
                key=lambda d: d.get("created_at", ""),
            )

            original = sorted_group[0]
            duplicates = sorted_group[1:]

            group_ids = [d["id"] for d in sorted_group]
            result.duplicate_groups.append(group_ids)
            result.kept_doc_ids.append(original["id"])
            result.exact_duplicates += len(duplicates)

            for dup in duplicates:
                result.marked_doc_ids.append(dup["id"])

                relations.append(
                    DetectedRelation(
                        source_doc_id=dup["id"],
                        target_doc_id=original["id"],
                        relation_type="version",
                        confidence=1.0,
                        evidence_text=(
                            f"Exact SHA256 match: {sha256[:16]}... "
                            f"Original: {original.get('filename', '?')}, "
                            f"Duplicate: {dup.get('filename', '?')}"
                        ),
                        method=RelationDetectionMethod.EXACT_HASH,
                    )
                )

                logger.info(
                    "Exact duplicate found",
                    original_id=original["id"],
                    duplicate_id=dup["id"],
                    sha256=sha256[:16],
                    original_filename=original.get("filename"),
                    duplicate_filename=dup.get("filename"),
                )

        logger.info(
            "Dedup complete",
            total=result.total_documents,
            duplicates=result.exact_duplicates,
            groups=len(result.duplicate_groups),
        )

        return result, relations
