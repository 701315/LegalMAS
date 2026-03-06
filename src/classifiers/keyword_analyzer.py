"""
L2 Keyword/Regex Analyzer.

ALL patterns come from YAML instruction files — nothing is hardcoded.
Scans document text using:
  - rules.keywords.high/medium/low
  - rules.phrases.high/medium (regex for document titles/headers)
  - rules.exclusions (penalty terms)

Patterns are loaded via registry_loader which merges registry.yaml
with per-type instruction files.
"""

import re

from .base import BaseClassifier, ClassificationResult
from .registry_loader import load_registry
from core.constants import ClassificationLevel
from core.logging import get_logger

logger = get_logger(__name__)


class KeywordAnalyzer(BaseClassifier):
    """
    L2: keyword/phrase matching from YAML registry.
    Scans document text using rules defined in per-type YAML files.
    """

    def __init__(self, registry_path: str, header_chars: int = 2000):
        self.registry = load_registry(registry_path)
        self.header_chars = header_chars

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L2_KEYWORDS

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        matches: list[dict] = []

        for doc_cfg in self.registry.get("document_types", []):
            doctype = doc_cfg.get("type", "")
            rules = doc_cfg.get("rules")
            if not rules:
                # This type has no instruction file or no rules section
                continue

            score_info = self._score_document(text, doc_cfg)
            if score_info["total_score"] > 0:
                # language/jurisdiction из YAML.metadata, с дефолтами
                meta = doc_cfg.get("metadata", {}) or {}
                lang = meta.get("language", "ru")
                juris = meta.get("jurisdiction", "RU")

                matches.append(
                    {
                        "type": doctype,
                        "score": score_info["total_score"],
                        "confidence": score_info["confidence"],
                        "method": score_info["primary_method"],
                        "evidence": score_info["evidence"],
                        "language": lang,
                        "jurisdiction": juris,
                    }
                )

        if not matches:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_keyword_match",
            )

        # Sort by confidence
        matches.sort(key=lambda x: x["confidence"], reverse=True)
        best = matches[0]

        # Ambiguity penalty: if close competitor exists
        if len(matches) > 1:
            gap = best["confidence"] - matches[1]["confidence"]
            if gap < 0.10:
                best["confidence"] *= 0.85

        return ClassificationResult(
            doctype=best["type"],
            confidence=min(best["confidence"], 1.0),
            level=self.level,
            method=best["method"],
            evidence=best["evidence"],
            language=best["language"],
            jurisdiction=best["jurisdiction"],
            alternative_types=[
                {"type": m["type"], "confidence": round(m["confidence"], 3)} for m in matches[1:4]
            ],
        )

    def _score_document(self, text: str, cfg: dict) -> dict:
        """Score a document against one type config from YAML."""
        rules = cfg.get("rules", {})
        weights = cfg.get("weights", {})
        text_lower = text.lower()
        header_lower = text[: self.header_chars].lower()

        total_score = 0.0
        evidence_parts: list[str] = []
        primary_method = "keywords"

        # 1. Phrase matching in header area (highest signal)
        phrases = rules.get("phrases", {})
        for impact, phrase_list in phrases.items():
            if not isinstance(phrase_list, list):
                continue
            phrase_weight = {"high": 4.0, "medium": 2.0, "low": 1.0}.get(impact, 1.0)
            for phrase in phrase_list:
                matched = False
                try:
                    if re.search(phrase, header_lower, re.IGNORECASE):
                        matched = True
                except re.error:
                    if phrase.lower() in header_lower:
                        matched = True
                if matched:
                    total_score += phrase_weight
                    if len(evidence_parts) < 5:
                        evidence_parts.append(f"phrase({impact}): {phrase}")
                    primary_method = "header_phrase"

        # 2. Keyword matching in full text
        keywords = rules.get("keywords", {})
        for impact, kw_list in keywords.items():
            if not isinstance(kw_list, list):
                continue
            kw_weight = weights.get(
                f"keyword_{impact}",
                {"high": 3.0, "medium": 1.5, "low": 0.5}.get(impact, 1.0),
            )
            for kw in kw_list:
                if kw.lower() in text_lower:
                    total_score += kw_weight
                    if len(evidence_parts) < 8:
                        evidence_parts.append(f"keyword({impact}): {kw}")

        # 3. Exclusion penalty
        for exc in rules.get("exclusions", []):
            if exc.lower() in text_lower:
                total_score *= 0.3
                evidence_parts.append(f"exclusion_hit: {exc}")
                break

        # Confidence normalization (max ~12 for strong match)
        confidence = min(total_score / 12.0, 1.0)

        return {
            "total_score": total_score,
            "confidence": confidence,
            "primary_method": primary_method,
            "evidence": "; ".join(evidence_parts[:5]) if evidence_parts else "",
        }
