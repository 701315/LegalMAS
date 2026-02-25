"""
Trigger Detector.

Detects applicable triggers from YAML trigger_definitions.

In Stage 2.5: used by HybridClassifier after L1 classification.
In Stage 8: TriggerDetector results are cross-referenced with
check_catalogue.yaml to build the final list of checks to run.

trigger_definitions schema (in type YAML):
  trigger_definitions:
    change_of_control:
      any_keywords: ["смена контроля", "change of control"]
    legal_entity_party:
      any_keywords: ["ООО", "АО", "LLC"]

Output: list of trigger IDs that matched in the document text.
  → Stored in Document.applicable_triggers (JSON array)
  → Read by Runner to decide which checks to execute
"""

from src.classifiers.yaml_registry import DocumentTypeConfig
from src.core.logging import get_logger

logger = get_logger(__name__)


class TriggerDetector:
    """
    Detects applicable triggers for a classified document type.

    Usage:
        detector = TriggerDetector()
        triggers = detector.detect(text, winner_config)
    """

    def detect(self, text: str, cfg: DocumentTypeConfig) -> list:
        """
        Detect triggered conditions from document text.

        Args:
            text: Full document text (lowercased internally)
            cfg:  DocumentTypeConfig of the winner type

        Returns:
            List of trigger IDs that matched, e.g. ['change_of_control']
        """
        if not cfg or not cfg.trigger_definitions:
            return []

        text_lower = text.lower()
        matched_ids = []

        for trigger_id, trigger_cfg in cfg.trigger_definitions.items():
            any_keywords = trigger_cfg.get("any_keywords", [])
            if any(kw.lower() in text_lower for kw in any_keywords):
                matched_ids.append(trigger_id)
                logger.debug(
                    "Trigger matched",
                    trigger_id=trigger_id,
                    type_code=cfg.type_code,
                )

        return matched_ids
