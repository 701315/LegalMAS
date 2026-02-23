"""
Base classes for classification cascade.

All classifiers are SYNCHRONOUS — designed for Celery workers.
Full 4-level cascade (L1+L2+L3+L4) implemented in Stage 6.

Classification levels:
  L1  — Rule-Based: filename + folder_path + keyword matching (this stage)
  L2  — Header Analyzer: reads first 1500 chars for document title (Stage 6)
  L3  — Semantic: cosine similarity with type embeddings (Stage 6)
  L4  — LLM: GPT-4o-mini with structured output (Stage 6, fallback only)

applicable_triggers:
  List of trigger IDs relevant to the classified document type.
  Loaded from trigger_definitions section of the YAML config.
  Used by Runner (Stage 8) for conditional check routing:
    - Runner checks applicable_triggers to decide which checks to run
    - Example: ['change_of_control'] → run check coc001
    - Runner.run_checks(doc) skips checks not in applicable_triggers
  In this stage: populated from YAML trigger_definitions keys.
  In Stage 8: also includes triggers from check_catalogue.yaml.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.core.constants import ClassificationLevel


@dataclass
class ClassificationResult:
    """Result of classification by one level."""

    doctype: str
    confidence: float
    level: ClassificationLevel
    method: str
    language: str = "ru"
    jurisdiction: str = "RU"
    evidence: str | None = None
    alternative_types: list = field(default_factory=list)


@dataclass
class FinalClassification:
    """
    Final classification result after cascade.

    Fields saved to Document:
      - doctype              → Document.doctype
      - confidence           → Document.classification_confidence  (new field)
      - level                → Document.classification_level       (new field)
      - language             → Document.language
      - jurisdiction         → Document.jurisdiction_guess
      - details              → Document.classification_details     (new field, JSON)
      - applicable_triggers  → Document.applicable_triggers        (new field, JSON array)

    applicable_triggers drives Runner routing:
      Runner reads this list to decide which checks from check_catalogue are applicable.
      Example: ['change_of_control', 'legal_entity_party']
        → Runner runs coc001 (change-of-control check)
        → Runner runs lep001 (legal entity party check)
    """

    doctype: str
    confidence: float
    level: ClassificationLevel
    language: str
    jurisdiction: str
    details: dict
    applicable_triggers: list = field(default_factory=list)


class BaseClassifier(ABC):
    """Base interface for all classifiers."""

    @abstractmethod
    def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str = None,
        metadata: dict = None,
    ) -> ClassificationResult:
        pass

    @property
    @abstractmethod
    def level(self) -> ClassificationLevel:
        pass
