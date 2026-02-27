"""
Exact Dedup Service.

Finds documents with identical content (same SHA256 hash)
within a single deal. When duplicates are found:
- The first document (by creation date) is kept as original
- All others are counted as duplicates
- A "version" relation is created between them

This runs BEFORE relation detection and family building.
"""

from collections import defaultdict
from typing import Dict, List, Tuple

from src.core.logging import get_logger
from src.services.relations.models import (
    DedupResult,
    DetectedRelation,
    RelationDetectionMethod,
)

logger = get_logger(__name__)


class ExactDedupService:
    """Finds and summarizes exact duplicate documents within a deal."""

    def find_duplicates(
        self,
        documents: List[Dict],
    ) -> Tuple[DedupResult, List[DetectedRelation]]:
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
        relations: List[DetectedRelation] = []

        if not documents:
            return result, relations

        # Group documents by SHA256
        hash_groups: Dict[str, List[Dict]] = defaultdict(list)
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

