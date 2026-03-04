"""
Base classes for classification cascade.

All classifiers are designed for Celery workers and used in a 4-level cascade:
  L1 — Rule-Based: filename + folder_path + keyword matching
  L2 — Header/Keyword Analyzer: text keywords, phrases, regex
  L3 — Semantic: embeddings similarity
  L4 — LLM: provider-agnostic, fallback only

applicable_triggers:
  List of trigger IDs relevant to the classified document type.
  Loaded from trigger_definitions section of the YAML config.
  Used by Runner (Stage 8) for conditional check routing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from core.constants import ClassificationLevel


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
      - confidence           → Document.classification_confidence
      - level                → Document.classification_level
      - language             → Document.language
      - jurisdiction         → Document.jurisdiction_guess
      - details              → Document.classification_details
      - applicable_triggers  → Document.applicable_triggers

    applicable_triggers drives Runner routing:
      Runner reads this list to decide which checks from check_catalogue are applicable.
    """

    doctype: str
    confidence: float
    level: ClassificationLevel
    language: str
    jurisdiction: str
    details: dict
    applicable_triggers: list = field(default_factory=list)


class BaseClassifier(ABC):
    """Interface for L1–L3 classifiers."""

    @property
    @abstractmethod
    def level(self) -> ClassificationLevel:
        pass

    @abstractmethod
    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        pass


class BaseLLMClassifier(BaseClassifier):
    """
    Interface for L4 LLM classifiers.
    Implementations: LocalLLMClassifier (GGUF), OpenAIClassifier, AnthropicClassifier.

    Cloud providers MUST receive sanitized text only.
    Local providers MAY receive raw text (no PII leak risk).
    """

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L4_LLM

    @abstractmethod
    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        pass
