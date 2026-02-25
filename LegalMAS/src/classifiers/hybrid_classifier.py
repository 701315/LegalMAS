"""
HybridClassifier — orchestrates the classification cascade.

Stage 2.5: L1 only (RuleBasedClassifier).
Stage 6:   L1 → L2 → L3 → L4 (full cascade with confidence thresholds).

Outputs FinalClassification with:
  - doctype:             winner type code
  - confidence:          normalized [0.0 … 1.0]
  - level:               ClassificationLevel.L1 (this stage)
  - language:            detected via LanguageDetector
  - jurisdiction:        from winner YAML metadata
  - details:             {levels_tried, l1_score, alternatives, evidence, ...}
  - applicable_triggers: trigger IDs from TriggerDetector + YAML trigger_definitions

applicable_triggers flow:
  1. HybridClassifier runs RuleBasedClassifier → gets winner type
  2. TriggerDetector scans text against winner.trigger_definitions
  3. applicable_triggers list saved to Document.applicable_triggers
  4. Runner reads Document.applicable_triggers to decide which checks to run
  5. Stage 8: Runner cross-references with check_catalogue.yaml
"""

from src.classifiers.base import ClassificationResult, FinalClassification
from src.classifiers.language_detector import LanguageDetector
from src.classifiers.rule_based import RuleBasedClassifier
from src.classifiers.trigger_detector import TriggerDetector
from src.classifiers.yaml_registry import YAMLRegistry
from src.core.constants import ClassificationLevel
from src.core.logging import get_logger

logger = get_logger(__name__)


class HybridClassifier:
    """
    Hybrid classifier cascade.

    Stage 2.5: L1 only.
    Prepares interfaces for Stage 6 full cascade.
    """

    def __init__(self, registry: YAMLRegistry = None):
        reg = registry or YAMLRegistry.get_instance()
        self._l1 = RuleBasedClassifier(reg)
        self._trigger = TriggerDetector()
        self._lang = LanguageDetector()
        self._registry = reg

    def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str = None,
        metadata: dict = None,
    ) -> FinalClassification:
        """
        Run classification cascade and return FinalClassification.

        Stage 2.5 cascade:
          L1 (RuleBasedClassifier)
            → winner + confidence
            → TriggerDetector → applicable_triggers
            → LanguageDetector → language

        Returns FinalClassification with all fields needed for DB write:
          classification_confidence, classification_level,
          classification_details, applicable_triggers.
        """
        levels_tried = []

        # L1
        l1_result: ClassificationResult = self._l1.classify(
            text=text,
            filename=filename,
            folder_path=folder_path,
            text_sanitized=text_sanitized,
            metadata=metadata,
        )
        levels_tried.append("L1")

        # Detect language
        language = self._lang.detect(text)

        # Detect triggers from winner type's trigger_definitions
        winner_cfg = self._registry.get_config(l1_result.doctype)
        triggers = self._trigger.detect(text, winner_cfg) if winner_cfg else []

        # Build details dict (saved as classification_details JSON)
        details = {
            "levels_tried": levels_tried,
            "l1_score": l1_result.confidence,
            "l1_method": l1_result.method,
            "l1_evidence": l1_result.evidence,
            "alternatives": l1_result.alternative_types,
            "triggers_from_yaml": triggers,
        }

        logger.info(
            "HybridClassifier result",
            doctype=l1_result.doctype,
            confidence=l1_result.confidence,
            level="L1",
            language=language,
            triggers=triggers,
        )

        return FinalClassification(
            doctype=l1_result.doctype,
            confidence=l1_result.confidence,
            level=ClassificationLevel.L1_RULES,
            language=language,
            jurisdiction=l1_result.jurisdiction,
            details=details,
            applicable_triggers=triggers,
        )
