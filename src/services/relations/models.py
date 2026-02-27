"""
Relations & Family Data Models.

Defines service-level models for document relationships:
- RelationDetectionMethod: enum for detection methods
- DetectedRelation: a candidate relation found by detector
- DedupResult: result of deduplication check
- FamilyGroup: a group of related documents with master
- RelationsReport: summary of all detected relations for a deal

These are NOT ORM models — they are used by the service layer
and then persisted through repositories.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class RelationDetectionMethod(str, Enum):
    """How the relation was detected."""

    EXACT_HASH = "exact_hash"              # SHA256 match
    FILENAME_PATTERN = "filename_pattern"  # Regex on filename
    FILENAME_SIMILARITY = "filename_similarity"  # Fuzzy filename match
    TEXT_REFERENCE = "text_reference"      # Reference found in document text
    MANUAL = "manual"                      # Manually created by user


@dataclass
class DetectedRelation:
    """A candidate relation found by a detector."""

    # Document that references another
    source_doc_id: str
    # Document being referenced
    target_doc_id: str
    # From constants: master, appendix, amendment, version, etc.
    relation_type: str
    # 0.0 to 1.0
    confidence: float
    # Why we think this relation exists
    evidence_text: str
    # How it was detected
    method: RelationDetectionMethod


@dataclass
class DedupResult:
    """Result of deduplication check for a deal."""

    total_documents: int = 0
    # Same SHA256
    exact_duplicates: int = 0
    # Groups of doc IDs
    duplicate_groups: List[List[str]] = field(default_factory=list)
    # First in each group (kept)
    kept_doc_ids: List[str] = field(default_factory=list)
    # Rest (marked as duplicate)
    marked_doc_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_documents": self.total_documents,
            "exact_duplicates": self.exact_duplicates,
            "duplicate_groups": self.duplicate_groups,
            "kept_doc_ids": self.kept_doc_ids,
            "marked_doc_ids": self.marked_doc_ids,
        }


@dataclass
class FamilyGroup:
    """A group of related documents with a master document."""

    # UUID, assigned after saving
    family_id: Optional[str] = None
    # The main document
    master_doc_id: str = ""
    # Doc type of master
    master_doc_type: str = ""
    # All members including master
    member_doc_ids: List[str] = field(default_factory=list)
    # Relations in family
    relations: List[DetectedRelation] = field(default_factory=list)

    # NEW: classification metadata from HybridClassifier (Stage 6)
    # "L0"…"L3"
    master_classification_level: Optional[str] = None
    # YAML instruction loaded
    master_yaml_available: bool = False
    # Trigger IDs applicable to master
    master_applicable_triggers: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.member_doc_ids)

    def to_dict(self) -> dict:
        return {
            "family_id": self.family_id,
            "master_doc_id": self.master_doc_id,
            "master_doc_type": self.master_doc_type,
            "member_doc_ids": self.member_doc_ids,
            "size": self.size,
            "master_classification_level": self.master_classification_level,
            "master_yaml_available": self.master_yaml_available,
            "master_applicable_triggers": self.master_applicable_triggers,
        }


@dataclass
class RelationsReport:
    """Summary of all detected relations for a deal."""

    deal_id: str
    dedup_result: DedupResult
    relations_found: int = 0
    families_created: int = 0
    family_groups: List[FamilyGroup] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "dedup": self.dedup_result.to_dict(),
            "relations_found": self.relations_found,
            "families_created": self.families_created,
            "family_groups": [f.to_dict() for f in self.family_groups],
            "errors": self.errors,
        }

