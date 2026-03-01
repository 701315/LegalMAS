"""

LEGACY HybridClassifier (pre-Stage 8).

Оставлен для обратной совместимости/референса.
Новый Runner использует src.classifiers.stage8.hybrid_classifier.HybridClassifier.

Hybrid 4-level classifier: L1 → L2 → L3 → L4 with early stopping.

Business rules:
  - L1 (filename/path): WEAK HINT only, never a final verdict (weight 0.20)
  - L2 (keywords/regex): FROM YAML only, can early-stop at >=0.85 (weight 0.40)
  - L3 (embeddings): can early-stop at >=0.80 (weight 0.40)
  - L4 (LLM): uses SANITIZED text for cloud, raw for local GGUF
  - Triggers: loaded dynamically from YAML trigger_definitions
"""

from src.classifiers.base import (
    BaseLLMClassifier,
    ClassificationResult,
    FinalClassification,
)
from src.classifiers.keyword_analyzer import KeywordAnalyzer
from src.classifiers.registry_loader import load_registry
from src.classifiers.rule_based import RuleBasedClassifier
from src.classifiers.semantic_matcher import SemanticMatcher
from src.classifiers.trigger_detector import detect_triggers
from src.core.constants import (
    CLASSIFICATION_THRESHOLDS,
    CLASSIFICATION_WEIGHTS,
    ClassificationLevel,
)
from src.core.logging import get_logger

logger = get_logger(__name__)


class HybridClassifier:
    """
    4-level cascade with early stopping.
    L1 is ALWAYS a hint — never terminates the cascade.
    L2 and L3 can terminate if confidence exceeds threshold
    and agrees with prior levels.
    Weighted voting aggregates all levels before falling back to L4.
    """

    def __init__(
        self,
        rule_based: RuleBasedClassifier,
        keyword_analyzer: KeywordAnalyzer,
        semantic_matcher: SemanticMatcher,
        llm_classifier: BaseLLMClassifier | None = None,
        thresholds: dict | None = None,
        weights: dict | None = None,
        registry_path: str = "playbooks/document_types",
    ):
        self.l1 = rule_based
        self.l2 = keyword_analyzer
        self.l3 = semantic_matcher
        self.l4 = llm_classifier
        self.thresholds = thresholds or CLASSIFICATION_THRESHOLDS
        self.weights = weights or CLASSIFICATION_WEIGHTS
        self._registry = load_registry(registry_path)

    async def classify(
        self,
        text: str,
        text_sanitized: str,
        filename: str,
        folder_path: str,
    ) -> FinalClassification:
        details: dict = {"levels_tried": [], "candidates": []}

        # --- L1: hint only, NEVER early-stops ---
        l1 = await self.l1.classify(text, filename, folder_path)
        details["levels_tried"].append("L1")
        details["L1"] = {
            "type": l1.doctype,
            "confidence": l1.confidence,
            "method": l1.method,
            "evidence": l1.evidence,
            "language": getattr(l1, "language", "ru"),
            "jurisdiction": getattr(l1, "jurisdiction", "RU"),
            "note": "hint_only_never_final",
        }
        if l1.doctype != "UNKNOWN":
            details["candidates"].append(
                {
                    "type": l1.doctype,
                    "confidence": l1.confidence,
                    "level": "L1",
                    "language": getattr(l1, "language", "ru"),
                    "jurisdiction": getattr(l1, "jurisdiction", "RU"),
                }
            )
        # L1 NEVER returns early — always proceed to L2

        # --- L2: keywords/regex from YAML ---
        l2 = await self.l2.classify(text, filename, folder_path)
        details["levels_tried"].append("L2")
        details["L2"] = {
            "type": l2.doctype,
            "confidence": l2.confidence,
            "method": l2.method,
            "evidence": l2.evidence,
            "language": getattr(l2, "language", "ru"),
            "jurisdiction": getattr(l2, "jurisdiction", "RU"),
        }
        if l2.doctype != "UNKNOWN":
            details["candidates"].append(
                {
                    "type": l2.doctype,
                    "confidence": l2.confidence,
                    "level": "L2",
                    "language": getattr(l2, "language", "ru"),
                    "jurisdiction": getattr(l2, "jurisdiction", "RU"),
                }
            )
        # L2 early stop: high confidence AND L1 agrees (or L1 was UNKNOWN)
        if l2.confidence >= self.thresholds["L2_accept"]:
            if l1.doctype == "UNKNOWN" or l1.doctype == l2.doctype:
                return self._finalize(l2, l2.confidence, details, text)

        # --- L3: embeddings ---
        l3 = await self.l3.classify(text, filename, folder_path)
        details["levels_tried"].append("L3")
        details["L3"] = {
            "type": l3.doctype,
            "confidence": l3.confidence,
            "method": l3.method,
            "evidence": l3.evidence,
            "language": getattr(l3, "language", "ru"),
            "jurisdiction": getattr(l3, "jurisdiction", "RU"),
        }
        if l3.doctype != "UNKNOWN":
            details["candidates"].append(
                {
                    "type": l3.doctype,
                    "confidence": l3.confidence,
                    "level": "L3",
                    "language": getattr(l3, "language", "ru"),
                    "jurisdiction": getattr(l3, "jurisdiction", "RU"),
                }
            )
        # L3 early stop: high confidence AND agrees with L2
        if l3.confidence >= self.thresholds["L3_accept"]:
            if l2.doctype == l3.doctype:
                return self._finalize(l3, l3.confidence, details, text)

        # --- Weighted voting (L1×0.20 + L2×0.40 + L3×0.40) ---
        voted = self._weighted_voting(details["candidates"])
        if voted and voted["confidence"] >= self.thresholds["voting_threshold"]:
            details["voting"] = voted
            return FinalClassification(
                doctype=voted["type"],
                confidence=voted["confidence"],
                level=ClassificationLevel.HYBRID,
                details=details,
                applicable_triggers=detect_triggers(self._registry, text, voted["type"]),
                # язык/юрисдикция от побеждающего кандидата
                language=voted.get("language", "ru"),
                jurisdiction=voted.get("jurisdiction", "RU"),
            )

        # --- L4: LLM fallback ---
        if self.l4 is not None:
            # Cloud LLM gets sanitized text; local GGUF can get raw text
            l4_text = text_sanitized
            if hasattr(self.l4, "model_path"):
                # Local GGUF — safe, no PII leak
                l4_text = text

            l4 = await self.l4.classify(
                l4_text,
                filename,
                folder_path,
                metadata={"candidates": details["candidates"]},
            )
            details["levels_tried"].append("L4")
            details["L4"] = {
                "type": l4.doctype,
                "confidence": l4.confidence,
                "method": l4.method,
                "evidence": l4.evidence,
                "language": getattr(l4, "language", "ru"),
                "jurisdiction": getattr(l4, "jurisdiction", "RU"),
            }
            if l4.confidence >= self.thresholds["uncertain_threshold"]:
                return self._finalize(l4, l4.confidence, details, text)

        # --- UNKNOWN fallback ---
        best_candidate = max(
            details["candidates"],
            key=lambda c: c["confidence"],
            default=None,
        )
        fallback_type = best_candidate["type"] if best_candidate else "UNKNOWN"
        fallback_conf = best_candidate["confidence"] if best_candidate else 0.0

        return FinalClassification(
            doctype=fallback_type,
            confidence=fallback_conf,
            level=ClassificationLevel.HYBRID,
            details=details,
            applicable_triggers=(
                detect_triggers(self._registry, text, fallback_type)
                if fallback_type != "UNKNOWN"
                else []
            ),
            language=best_candidate.get("language", "ru") if best_candidate else "ru",
            jurisdiction=best_candidate.get("jurisdiction", "RU") if best_candidate else "RU",
        )

    def _weighted_voting(
        self,
        candidates: list[dict],
    ) -> dict | None:
        """Weighted voting: L1×0.20 + L2×0.40 + L3×0.40."""
        if not candidates:
            return None

        type_scores: dict[str, float] = {}
        type_meta: dict[str, dict] = {}  # язык/юрисдикция по лучшему представителю
        total_weight = 0.0

        for c in candidates:
            w = self.weights.get(c["level"], 0.20)
            doctype = c["type"]
            score = c["confidence"] * w
            type_scores[doctype] = type_scores.get(doctype, 0.0) + score
            total_weight += w

            # сохраняем метаданные для типа с наибольшим вкладом
            prev = type_meta.get(doctype)
            if prev is None or score > prev.get("score", 0.0):
                type_meta[doctype] = {
                    "language": c.get("language", "ru"),
                    "jurisdiction": c.get("jurisdiction", "RU"),
                    "score": score,
                }

        if not type_scores:
            return None

        best_type = max(type_scores, key=type_scores.get)
        confidence = type_scores[best_type] / total_weight if total_weight > 0 else 0.0

        meta = type_meta.get(best_type, {})
        return {
            "type": best_type,
            "confidence": round(confidence, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
        }

    def _finalize(
        self,
        result: ClassificationResult,
        confidence: float,
        details: dict,
        text: str,
    ) -> FinalClassification:
        return FinalClassification(
            doctype=result.doctype,
            confidence=confidence,
            level=result.level,
            details=details,
            applicable_triggers=detect_triggers(self._registry, text, result.doctype),
            language=getattr(result, "language", "ru"),
            jurisdiction=getattr(result, "jurisdiction", "RU"),
        )
