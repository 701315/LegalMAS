"""
Relation Detector Service.

Finds relationships between documents using two methods:

1. Filename-based detection:
   - Pattern matching: "Appendix 1 to SPA" → appendix relation to SPA
   - Version detection: "SPA_v1.pdf", "SPA_v2.pdf" → version relation
   - Fuzzy name similarity: similar names might be related

2. Text-based detection:
   - References in document text: "к Договору от 01.01.2024 №123"
   - "является неотъемлемой частью" → appendix relation

Both methods produce DetectedRelation objects that are later
used by the Family Builder to group documents.
"""

import re
from typing import Dict, List, Optional, Tuple

from thefuzz import fuzz

from src.core.config import settings
from src.core.logging import get_logger
from src.services.relations.models import (
    DetectedRelation,
    RelationDetectionMethod,
)

logger = get_logger(__name__)

# ============================================================
# Filename patterns for relation detection
# ============================================================

# Appendix patterns (Russian)
_RE_APPENDIX_RU = re.compile(
    r"(?i)(?:приложение|прилож)\s*(?:№\s*)?(\d+)"
    r"(?:\s+к\s+(.+?))?(?:\.\w+)?$"
)

# Appendix patterns (English)
_RE_APPENDIX_EN = re.compile(
    r"(?i)(?:appendix|annex|exhibit|schedule)\s*(?:No\.?\s*)?(\d+)"
    r"(?:\s+to\s+(.+?))?(?:\.\w+)?$"
)

# Amendment patterns (Russian)
_RE_AMENDMENT_RU = re.compile(
    r"(?i)(?:дополнительное\s+соглашение|доп\s*\.?\s*соглашение|изменение)\s*(?:№\s*)?(\d+)"
    r"(?:\s+к\s+(.+?))?(?:\.\w+)?$"
)

# Amendment patterns (English)
_RE_AMENDMENT_EN = re.compile(
    r"(?i)(?:amendment|addendum|supplement)\s*(?:No\.?\s*)?(\d+)"
    r"(?:\s+to\s+(.+?))?(?:\.\w+)?$"
)

# Version patterns: filename_v1.pdf, filename_v2.pdf
_RE_VERSION = re.compile(
    r"(?i)(.+?)[\s_]*v(?:er(?:sion)?)?[\s._]*(\d+)(?:\.\w+)?$"
)

# Draft patterns: filename_draft.pdf, filename_проект.pdf
_RE_DRAFT = re.compile(
    r"(?i)(.+?)[\s_]*(draft|проект|черновик)(?:\.\w+)?$"
)

# Counterpart patterns: filename_counterpart.pdf
_RE_COUNTERPART = re.compile(
    r"(?i)(.+?)[\s_]*(counterpart|контрагент|экземпляр\s*\d*)(?:\.\w+)?$"
)

# ============================================================
# Text patterns for relation detection
# ============================================================

# "к Договору ... от DD.MM.YYYY №NNN" (Russian)
_RE_TEXT_REF_CONTRACT_RU = re.compile(
    r"(?i)к\s+(?:договор[уа]|соглашени[юя]|контракт[уа])"
    r"(?:\s+\S+){0,5}?"
    r"(?:\s+от\s+\d{1,2}[./]\d{1,2}[./]\d{2,4})?"
    r"(?:\s*(?:№|номер)\s*\S+)?"
)

# "является неотъемлемой частью" (Russian)
_RE_TEXT_INTEGRAL_PART_RU = re.compile(
    r"(?i)(?:является|составляет)\s+"
    r"(?:неотъемлемой|неотделимой)\s+"
    r"(?:частью|приложением)"
)

# "в дополнение к" (Russian)
_RE_TEXT_SUPPLEMENT_RU = re.compile(
    r"(?i)(?:в\s+дополнение|дополнительно)\s+к\s+"
    r"(?:договор[уа]|соглашени[юя])"
)

# English text patterns
_RE_TEXT_REF_CONTRACT_EN = re.compile(
    r"(?i)(?:pursuant|subject)\s+to\s+(?:the\s+)?"
    r"(?:agreement|contract|deed)"
    r"(?:\s+dated\s+\S+)?"
    r"(?:\s+(?:No\.?|number)\s*\S+)?"
)

_RE_TEXT_INTEGRAL_PART_EN = re.compile(
    r"(?i)(?:forms?\s+an?\s+)?integral\s+part\s+of"
)


class RelationDetector:
    """Detects relationships between documents."""

    def __init__(self) -> None:
        self.similarity_threshold = settings.RELATIONS_FILENAME_SIMILARITY_THRESHOLD

    def detect_all_relations(
        self,
        documents: List[Dict],
    ) -> List[DetectedRelation]:
        """
        Detect all relations between documents in a deal.

        Args:
            documents: List of document dicts with keys:
                - id: str
                - filename: str
                - folder_path: str
                - doc_type: str
                - text_first_2000: str (first 2000 chars of text_layout_raw)
                - classification_level: str (Stage 7)
        Returns:
            List of detected relations (may contain duplicates,
            caller should deduplicate)
        """
        relations: List[DetectedRelation] = []

        if not documents or len(documents) < 2:
            return relations

        # Step 1: Filename-based detection
        if settings.RELATIONS_FILENAME_ENABLED:
            filename_relations = self._detect_filename_relations(documents)
            relations.extend(filename_relations)

        # Step 2: Text-based detection
        if settings.RELATIONS_TEXT_ENABLED:
            text_relations = self._detect_text_relations(documents)
            relations.extend(text_relations)

        # Deduplicate: keep highest confidence for each pair
        relations = self._deduplicate_relations(relations)

        logger.info(
            "Relation detection complete",
            total_documents=len(documents),
            relations_found=len(relations),
        )

        return relations

    # ============================================================
    # Filename-based detection
    # ============================================================

    def _detect_filename_relations(
        self,
        documents: List[Dict],
    ) -> List[DetectedRelation]:
        """Detect relations from filenames."""
        relations: List[DetectedRelation] = []

        for doc in documents:
            filename = doc.get("filename", "")
            doc_id = doc["id"]

            # Try appendix pattern
            rel = self._check_appendix_pattern(doc_id, filename, documents)
            if rel:
                relations.append(rel)

            # Try amendment pattern
            rel = self._check_amendment_pattern(doc_id, filename, documents)
            if rel:
                relations.append(rel)

            # Try draft pattern
            rel = self._check_draft_pattern(doc_id, filename, documents)
            if rel:
                relations.append(rel)

            # Try counterpart pattern
            rel = self._check_counterpart_pattern(doc_id, filename, documents)
            if rel:
                relations.append(rel)

        # Detect version groups (SPA_v1, SPA_v2, SPA_v3)
        version_relations = self._detect_version_groups(documents)
        relations.extend(version_relations)

        return relations

    def _check_appendix_pattern(
        self,
        doc_id: str,
        filename: str,
        all_docs: List[Dict],
    ) -> Optional[DetectedRelation]:
        """Check if filename matches appendix pattern."""
        match = _RE_APPENDIX_RU.search(filename)
        if not match:
            match = _RE_APPENDIX_EN.search(filename)

        if not match:
            return None

        appendix_num = match.group(1)
        master_hint = match.group(2)  # May be None

        master_id = self._find_master_document(doc_id, master_hint, all_docs)
        if not master_id:
            return None

        return DetectedRelation(
            source_doc_id=doc_id,
            target_doc_id=master_id,
            relation_type="appendix",
            confidence=0.85,
            evidence_text=(
                f"Filename pattern: '{filename}' → "
                f"appendix #{appendix_num}"
            ),
            method=RelationDetectionMethod.FILENAME_PATTERN,
        )

    def _check_amendment_pattern(
        self,
        doc_id: str,
        filename: str,
        all_docs: List[Dict],
    ) -> Optional[DetectedRelation]:
        """Check if filename matches amendment pattern."""
        match = _RE_AMENDMENT_RU.search(filename)
        if not match:
            match = _RE_AMENDMENT_EN.search(filename)

        if not match:
            return None

        amendment_num = match.group(1)
        master_hint = match.group(2)

        master_id = self._find_master_document(doc_id, master_hint, all_docs)
        if not master_id:
            return None

        return DetectedRelation(
            source_doc_id=doc_id,
            target_doc_id=master_id,
            relation_type="amendment",
            confidence=0.85,
            evidence_text=(
                f"Filename pattern: '{filename}' → "
                f"amendment #{amendment_num}"
            ),
            method=RelationDetectionMethod.FILENAME_PATTERN,
        )

    def _check_draft_pattern(
        self,
        doc_id: str,
        filename: str,
        all_docs: List[Dict],
    ) -> Optional[DetectedRelation]:
        """Check if filename matches draft pattern."""
        match = _RE_DRAFT.search(filename)
        if not match:
            return None

        base_name = match.group(1).strip()

        final_id = self._find_similar_document(doc_id, base_name, all_docs)
        if not final_id:
            return None

        return DetectedRelation(
            source_doc_id=doc_id,
            target_doc_id=final_id,
            relation_type="draft",
            confidence=0.75,
            evidence_text=(
                f"Filename pattern: '{filename}' → "
                f"draft of '{base_name}'"
            ),
            method=RelationDetectionMethod.FILENAME_PATTERN,
        )

    def _check_counterpart_pattern(
        self,
        doc_id: str,
        filename: str,
        all_docs: List[Dict],
    ) -> Optional[DetectedRelation]:
        """Check if filename matches counterpart pattern."""
        match = _RE_COUNTERPART.search(filename)
        if not match:
            return None

        base_name = match.group(1).strip()

        original_id = self._find_similar_document(doc_id, base_name, all_docs)
        if not original_id:
            return None

        return DetectedRelation(
            source_doc_id=doc_id,
            target_doc_id=original_id,
            relation_type="counterpart",
            confidence=0.70,
            evidence_text=(
                f"Filename pattern: '{filename}' → "
                f"counterpart of '{base_name}'"
            ),
            method=RelationDetectionMethod.FILENAME_PATTERN,
        )

    def _detect_version_groups(
        self,
        documents: List[Dict],
    ) -> List[DetectedRelation]:
        """
        Detect version groups: SPA_v1.pdf, SPA_v2.pdf, SPA_v3.pdf.

        Groups documents by base name, then creates version relations
        between consecutive versions.
        """
        relations: List[DetectedRelation] = []

        versioned: Dict[str, List[Tuple[int, Dict]]] = {}
        for doc in documents:
            filename = doc.get("filename", "")
            match = _RE_VERSION.search(filename)
            if match:
                base_name = self._normalize_filename(match.group(1))
                version_num = int(match.group(2))
                if base_name not in versioned:
                    versioned[base_name] = []
                versioned[base_name].append((version_num, doc))

        for base_name, versions in versioned.items():
            if len(versions) < 2:
                continue

            sorted_versions = sorted(versions, key=lambda x: x[0])

            for i in range(1, len(sorted_versions)):
                prev_ver_num, prev_doc = sorted_versions[i - 1]
                curr_ver_num, curr_doc = sorted_versions[i]

                relations.append(
                    DetectedRelation(
                        source_doc_id=curr_doc["id"],
                        target_doc_id=prev_doc["id"],
                        relation_type="version",
                        confidence=0.90,
                        evidence_text=(
                            "Version sequence: "
                            f"'{prev_doc.get('filename', '?')}' (v{prev_ver_num}) → "
                            f"'{curr_doc.get('filename', '?')}' (v{curr_ver_num})"
                        ),
                        method=RelationDetectionMethod.FILENAME_PATTERN,
                    )
                )

        return relations

    def _find_master_document(
        self,
        exclude_id: str,
        master_hint: Optional[str],
        all_docs: List[Dict],
    ) -> Optional[str]:
        """
        Find the master document for an appendix/amendment.

        Priority order:
        1. Fuzzy match on master_hint from filename (if provided)
        2. Master doc_type match in same folder
        3. Highest classification_level among master-type candidates
        4. Last resort: any master-type document with highest classification_level
        """
        candidates = [d for d in all_docs if d["id"] != exclude_id]
        if not candidates:
            return None

        # --- Priority 1: Hint fuzzy match ---
        if master_hint:
            master_hint_clean = self._normalize_filename(master_hint)
            best_score = 0
            best_id: Optional[str] = None

            for doc in candidates:
                doc_name = self._normalize_filename(doc.get("filename", ""))
                score = fuzz.partial_ratio(master_hint_clean, doc_name)
                if score > best_score and score >= self.similarity_threshold:
                    best_score = score
                    best_id = doc["id"]

            if best_id:
                return best_id

        # --- Priority 2+3: master doc_type + highest classification_level ---
        exclude_doc = next(
            (d for d in all_docs if d["id"] == exclude_id), None
        )
        exclude_folder = exclude_doc.get("folder_path", "") if exclude_doc else ""

        level_priority = {
            level: idx
            for idx, level in enumerate(
                settings.FAMILY_CLASSIFICATION_LEVEL_PRIORITY
            )
        }

        folder_masters = [
            doc
            for doc in candidates
            if doc.get("doc_type", "") in settings.FAMILY_MASTER_DOC_TYPES
            and doc.get("folder_path", "") == exclude_folder
        ]

        if folder_masters:
            return max(
                folder_masters,
                key=lambda d: level_priority.get(
                    d.get("classification_level", "L0"), 0
                ),
            )["id"]

        # --- Priority 4: any master-type, highest classification_level ---
        any_masters = [
            doc
            for doc in candidates
            if doc.get("doc_type", "") in settings.FAMILY_MASTER_DOC_TYPES
        ]
        if any_masters:
            return max(
                any_masters,
                key=lambda d: level_priority.get(
                    d.get("classification_level", "L0"), 0
                ),
            )["id"]

        return None

    def _find_similar_document(
        self,
        exclude_id: str,
        base_name: str,
        all_docs: List[Dict],
    ) -> Optional[str]:
        """Find a document with a similar filename (fuzzy match)."""
        base_clean = self._normalize_filename(base_name)
        best_score = 0
        best_id: Optional[str] = None

        for doc in all_docs:
            if doc["id"] == exclude_id:
                continue

            doc_name = self._normalize_filename(doc.get("filename", ""))
            score = fuzz.ratio(base_clean, doc_name)
            if score > best_score and score >= self.similarity_threshold:
                best_score = score
                best_id = doc["id"]

        return best_id

    # ============================================================
    # Text-based detection
    # ============================================================

    def _detect_text_relations(
        self,
        documents: List[Dict],
    ) -> List[DetectedRelation]:
        """Detect relations from document text content."""
        relations: List[DetectedRelation] = []

        for doc in documents:
            doc_id = doc["id"]
            text = doc.get("text_first_2000", "")

            if not text:
                continue

            # Check for "integral part" pattern → appendix
            if self._text_is_appendix(text):
                master_id = self._find_master_document(doc_id, None, documents)
                if master_id:
                    relations.append(
                        DetectedRelation(
                            source_doc_id=doc_id,
                            target_doc_id=master_id,
                            relation_type="appendix",
                            confidence=0.80,
                            evidence_text=self._extract_evidence_snippet(
                                text,
                                [
                                    _RE_TEXT_INTEGRAL_PART_RU,
                                    _RE_TEXT_INTEGRAL_PART_EN,
                                ],
                            ),
                            method=RelationDetectionMethod.TEXT_REFERENCE,
                        )
                    )

            # Check for "supplement to" pattern → amendment
            if self._text_is_amendment(text):
                master_id = self._find_master_document(doc_id, None, documents)
                if master_id:
                    relations.append(
                        DetectedRelation(
                            source_doc_id=doc_id,
                            target_doc_id=master_id,
                            relation_type="amendment",
                            confidence=0.75,
                            evidence_text=self._extract_evidence_snippet(
                                text,
                                [
                                    _RE_TEXT_SUPPLEMENT_RU,
                                    _RE_TEXT_REF_CONTRACT_RU,
                                    _RE_TEXT_REF_CONTRACT_EN,
                                ],
                            ),
                            method=RelationDetectionMethod.TEXT_REFERENCE,
                        )
                    )

        return relations

    def _text_is_appendix(self, text: str) -> bool:
        """Check if text indicates document is an appendix."""
        return bool(
            _RE_TEXT_INTEGRAL_PART_RU.search(text)
            or _RE_TEXT_INTEGRAL_PART_EN.search(text)
        )

    def _text_is_amendment(self, text: str) -> bool:
        """Check if text indicates document is an amendment."""
        return bool(
            _RE_TEXT_SUPPLEMENT_RU.search(text)
            or _RE_TEXT_REF_CONTRACT_RU.search(text)
        )

    def _extract_evidence_snippet(
        self,
        text: str,
        patterns: List[re.Pattern],
    ) -> str:
        """Extract snippet around the first matching pattern."""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                snippet = text[start:end].strip()
                return f"...{snippet}..."
        return "Text-based detection (pattern match)"

    # ============================================================
    # Helpers
    # ============================================================

    def _normalize_filename(self, filename: str) -> str:
        """
        Normalize filename for comparison.
        Remove extension, underscores, extra spaces.
        """
        name = re.sub(r"\.\w{2,5}$", "", filename)
        name = re.sub(r"[_\-]+", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        return name.lower()

    def _deduplicate_relations(
        self,
        relations: List[DetectedRelation],
    ) -> List[DetectedRelation]:
        """
        Deduplicate relations: keep highest confidence for each pair.

        If the same source→target pair is detected by multiple methods,
        keep the one with highest confidence.
        """
        best: Dict[Tuple[str, str], DetectedRelation] = {}

        for rel in relations:
            key = (rel.source_doc_id, rel.target_doc_id)
            if key not in best or rel.confidence > best[key].confidence:
                best[key] = rel

        return list(best.values())
