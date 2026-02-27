"""
L1 Rule-Based Classifier.

IMPORTANT: L1 is a WEAK HINT only. It never produces a final verdict.
A file named 'spa_draft1.docx' may be an appendix, not an actual SPA.
L1 confidence is CAPPED at 0.60 and serves only as a weighted signal
in the voting cascade (weight 0.20).

Uses filename_patterns and folder_patterns from per-type YAML instructions.
"""

import hashlib
import re

from src.classifiers.base import BaseClassifier, ClassificationResult
from src.classifiers.registry_loader import load_registry
from src.core.constants import ClassificationLevel
from src.core.logging import get_logger

logger = get_logger(__name__)

# L1 confidence is NEVER higher than this
_L1_CONFIDENCE_CAP = 0.60


class RuleBasedClassifier(BaseClassifier):
    """L1: filename + folder pattern matching (hint only)."""

    def __init__(self, registry_path: str):
        self.registry = load_registry(registry_path)
        self._cache: dict[str, ClassificationResult] = {}

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L1_RULES

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        cache_key = self._compute_cache_key(filename, folder_path)
        if cache_key in self._cache:
            return self._cache[cache_key]

        type_scores: dict[str, float] = {}

        for doc_cfg in self.registry.get("document_types", []):
            doctype = doc_cfg.get("type", "")
            if not doctype:
                continue

            # L1 scores ONLY from filename and folder — NOT from text
            score = self._score_filename_folder(doc_cfg, filename, folder_path)
            if score > 0:
                type_scores[doctype] = score

        if not type_scores:
            result = ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_filename_match",
            )
            self._cache[cache_key] = result
            return result

        best_type = max(type_scores, key=type_scores.get)
        confidence = self._calculate_confidence(best_type, type_scores)
        # CAP: L1 is never a final verdict
        confidence = min(confidence, _L1_CONFIDENCE_CAP)

        result = ClassificationResult(
            doctype=best_type,
            confidence=confidence,
            level=self.level,
            method=self._get_match_method(best_type, filename, folder_path),
            evidence=self._get_match_evidence(best_type, filename, folder_path),
            alternative_types=self._get_alternatives(type_scores, best_type),
        )
        self._cache[cache_key] = result
        return result

    def _score_filename_folder(
        self,
        cfg: dict,
        filename: str,
        folder_path: str,
    ) -> float:
        """Score based ONLY on filename and folder patterns from YAML."""
        weights = cfg.get("weights", {})
        score = 0.0

        # Filename patterns
        for pattern in cfg.get("filename_patterns", []):
            try:
                if re.search(pattern, filename, re.IGNORECASE):
                    score += weights.get("filename", 2.0)
                    break  # one match is enough
            except re.error:
                if pattern.lower() in filename.lower():
                    score += weights.get("filename", 2.0)
                    break

        # Folder patterns
        if folder_path:
            for pattern in cfg.get("folder_patterns", []):
                try:
                    if re.search(pattern, folder_path, re.IGNORECASE):
                        score += weights.get("folder", 1.5)
                        break
                except re.error:
                    if pattern.lower() in folder_path.lower():
                        score += weights.get("folder", 1.5)
                        break

        return score

    def _calculate_confidence(
        self,
        best_type: str,
        type_scores: dict[str, float],
    ) -> float:
        best_score = type_scores[best_type]
        if best_score <= 0:
            return 0.0

        other_scores = [s for t, s in type_scores.items() if t != best_type]
        second_best = max(other_scores) if other_scores else 0.0

        # Normalize: max filename(2.0)+folder(1.5) = 3.5 → confidence ~1.0
        base_confidence = min(best_score / 3.5, 1.0)

        if second_best > 0:
            competition_penalty = (second_best / best_score) * 0.3
            base_confidence -= competition_penalty

        return max(0.0, min(1.0, base_confidence))

    def _compute_cache_key(self, filename: str, folder_path: str) -> str:
        content = f"{filename}|{folder_path}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_match_method(
        self,
        doctype: str,
        filename: str,
        folder_path: str,
    ) -> str:
        cfg = self._find_cfg(doctype)
        for pattern in cfg.get("filename_patterns", []):
            try:
                if re.search(pattern, filename, re.IGNORECASE):
                    return "filename_pattern"
            except re.error:
                pass

        if folder_path:
            for pattern in cfg.get("folder_patterns", []):
                try:
                    if re.search(pattern, folder_path, re.IGNORECASE):
                        return "folder_pattern"
                except re.error:
                    pass

        return "filename_pattern"

    def _get_match_evidence(
        self,
        doctype: str,
        filename: str,
        folder_path: str,
    ) -> str:
        cfg = self._find_cfg(doctype)
        for pattern in cfg.get("filename_patterns", []):
            try:
                match = re.search(pattern, filename, re.IGNORECASE)
                if match:
                    return f"filename: '{match.group()}' in '{filename}'"
            except re.error:
                pass

        if folder_path:
            for pattern in cfg.get("folder_patterns", []):
                try:
                    match = re.search(pattern, folder_path, re.IGNORECASE)
                    if match:
                        return f"folder: '{match.group()}' in '{folder_path}'"
                except re.error:
                    pass

        return f"filename: {filename}"

    def _get_alternatives(
        self,
        type_scores: dict[str, float],
        best_type: str,
    ) -> list:
        best_score = type_scores[best_type]
        if best_score <= 0:
            return []

        return [
            {"type": dt, "confidence": round(s / best_score, 2)}
            for dt, s in sorted(
                type_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            if dt != best_type and s > best_score * 0.3
        ][:3]

    def _find_cfg(self, doctype: str) -> dict:
        for c in self.registry.get("document_types", []):
            if c.get("type") == doctype:
                return c
        return {}
