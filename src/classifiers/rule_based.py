"""
L1 Rule-Based Classifier.

Scores document types using weighted signal matching:
  - filename_patterns : 40 pts each match
  - folder_patterns   : 30 pts each match
  - keywords high     : 20 pts each
  - keywords medium   : 10 pts each
  - keywords low      :  5 pts each
  - exclusions        : -50 pts each

Confidence = winner_score / max_possible_score (capped at 1.0).
If no type scores > 0 → returns Generic with confidence 0.1.

This is the only classifier in Stage 2.5.
Full cascade L1+L2+L3+L4 implemented in Stage 6.
"""

from src.classifiers.base import BaseClassifier, ClassificationResult
from src.classifiers.yaml_registry import YAMLRegistry
from src.core.constants import ClassificationLevel
from src.core.logging import get_logger

logger = get_logger(__name__)

# Scoring weights
W_FILENAME = 40
W_FOLDER = 30
W_KW_HIGH = 20
W_KW_MED = 10
W_KW_LOW = 5
W_EXCLUSION = -50

# Minimum score threshold to claim a type
MIN_SCORE_THRESHOLD = 20


class RuleBasedClassifier(BaseClassifier):
    """
    L1 Rule-Based Classifier using YAML-configured rules.

    Loaded from playbooks/document_types/*.yaml via YAMLRegistry.
    No ML — pure weighted scoring on text features.
    """

    def __init__(self, registry: YAMLRegistry | None = None):
        self._registry = registry or YAMLRegistry.get_instance()

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L1_RULES

    def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str = None,
        metadata: dict = None,
    ) -> ClassificationResult:
        """
        Classify document by scoring all known types.

        Args:
            text:           Full text from textlayoutraw (elements joined)
            filename:       Original filename, e.g. "SPA_final.pdf"
            folder_path:    Folder path from ZIP structure, e.g. "02. Contracts/SPA"
            text_sanitized: Sanitized text (not used in L1, reserved for L4)
            metadata:       Extra metadata (not used in L1)

        Returns:
            ClassificationResult with:
              - doctype:             winner type code or "Generic"
              - confidence:          normalized score [0.0 … 1.0]
              - level:               ClassificationLevel.L1
              - applicable_triggers: trigger IDs from winner's trigger_definitions
              - evidence:            summary of matched signals
        """
        configs = self._registry.get_all_configs()
        if not configs:
            logger.warning("YAML registry is empty — returning Generic")
            return self._make_generic()

        text_lower = text.lower()
        filename_lower = filename.lower()
        folder_lower = (folder_path or "").lower()

        scores: dict = {}
        evidence_log: dict = {}

        for cfg in configs:
            score = 0
            evidence = []

            # filename_patterns
            for pattern in cfg.filename_patterns:
                if pattern.search(filename_lower):
                    score += W_FILENAME
                    evidence.append(f"filename~{pattern.pattern}")

            # folder_patterns
            for pattern in cfg.folder_patterns:
                if pattern.search(folder_lower):
                    score += W_FOLDER
                    evidence.append(f"folder~{pattern.pattern}")

            # keywords
            for kw in cfg.keywords_high:
                if kw.lower() in text_lower:
                    score += W_KW_HIGH
                    evidence.append(f"kw_high:{kw}")
            for kw in cfg.keywords_medium:
                if kw.lower() in text_lower:
                    score += W_KW_MED
                    evidence.append(f"kw_med:{kw}")
            for kw in cfg.keywords_low:
                if kw.lower() in text_lower:
                    score += W_KW_LOW
                    evidence.append(f"kw_low:{kw}")

            # exclusions
            for excl in cfg.exclusions:
                if excl.lower() in text_lower:
                    score += W_EXCLUSION
                    evidence.append(f"excl:{excl}")

            scores[cfg.type_code] = score
            evidence_log[cfg.type_code] = evidence

        if not scores:
            return self._make_generic()

        winner = max(scores, key=lambda t: scores[t])
        best_score = scores[winner]

        if best_score < MIN_SCORE_THRESHOLD:
            return self._make_generic()

        # Normalize confidence
        max_possible = W_FILENAME * 2 + W_FOLDER * 2 + W_KW_HIGH * 3
        confidence = min(best_score / max_possible, 1.0)

        winner_cfg = self._registry.get_config(winner)
        triggers = winner_cfg.trigger_ids if winner_cfg else []

        # Runner routing: applicable_triggers tells Runner which checks to run
        # e.g. ['change_of_control'] → Runner will run check coc001
        logger.debug(
            "L1 classification result",
            winner=winner,
            score=best_score,
            confidence=round(confidence, 3),
            triggers=triggers,
            top_evidence=evidence_log[winner][:5],
        )

        # Sort alternatives for details
        sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        alternatives = [
            {"type": t, "score": s, "confidence": round(min(s / max_possible, 1.0), 3)}
            for t, s in sorted_types[1:4]
            if s > 0
        ]

        return ClassificationResult(
            doctype=winner,
            confidence=round(confidence, 3),
            level=ClassificationLevel.L1_RULES,
            method="rule_based_weighted",
            language=winner_cfg.language if winner_cfg else "ru",
            jurisdiction=winner_cfg.jurisdiction if winner_cfg else "RU",
            evidence="; ".join(evidence_log[winner][:10]),
            alternative_types=alternatives,
        )

    def _make_generic(self) -> ClassificationResult:
        return ClassificationResult(
            doctype="Generic",
            confidence=0.1,
            level=ClassificationLevel.L1_RULES,
            method="fallback_generic",
            language="ru",
            jurisdiction="RU",
            evidence="No matching type found",
        )
