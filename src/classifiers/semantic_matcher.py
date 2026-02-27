"""
L3 Semantic Matcher.
Embeds the first 1000 chars and compares to enriched type prototypes
built from normalized YAML instruction files.
"""

import numpy as np

from src.classifiers.base import BaseClassifier, ClassificationResult
from src.classifiers.registry_loader import load_registry
from src.core.constants import ClassificationLevel
from src.core.logging import get_logger

logger = get_logger(__name__)


class SemanticMatcher(BaseClassifier):
    """L3: cosine similarity between doc embedding and type prototypes."""

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        registry_path: str = "playbooks/document_types",
    ):
        self.model_name = model_name
        self.registry_path = registry_path
        self._model = None
        self._prototypes: dict[str, np.ndarray] = {}
        self._configs: dict[str, dict] = {}  # Храним конфиги для метаданных

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L3_SEMANTIC

    @property
    def model(self):
        """Lazy-load sentence-transformers model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                self._load_prototypes()
            except ImportError:
                logger.warning("sentence-transformers not available, L3 disabled")
        return self._model

    def _load_prototypes(self):
        """Build embeddings for each type that has rules."""
        registry = load_registry(self.registry_path)
        for doc_cfg in registry.get("document_types", []):
            doctype = doc_cfg.get("type")
            if not doctype or not doc_cfg.get("rules"):
                continue

            prototype_text = self._create_enriched_prototype(doc_cfg)
            if prototype_text.strip():
                self._prototypes[doctype] = self._model.encode(
                    prototype_text, normalize_embeddings=True
                )
                self._configs[doctype] = doc_cfg

        logger.info("L3 prototypes loaded", count=len(self._prototypes))

    def _create_enriched_prototype(self, cfg: dict) -> str:
        """
        Build text prototype from normalized YAML config.
        Uses fields flattened by registry_loader.
        """
        parts: list[str] = []

        # 1. Основная информация
        parts.append(cfg.get("name", ""))
        parts.append(cfg.get("description", ""))

        # 2. Ключевые слова и фразы (из нормализованного rules)
        rules = cfg.get("rules", {})
        for impact in ("high", "medium", "low"):
            parts.extend(rules.get("keywords", {}).get(impact, []))
            parts.extend(rules.get("phrases", {}).get(impact, []))

        # 3. Семантические маркеры (нормализованные загрузчиком)
        parts.extend(cfg.get("party_roles", []))
        parts.extend(cfg.get("essential_terms", []))
        parts.extend(cfg.get("section_markers", []))
        parts.extend(cfg.get("aliases", []))

        # Очистка и сборка
        clean_parts = [str(p) for p in parts if p and isinstance(p, str | int | float)]
        return " ".join(clean_parts)[:4000]

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        if self.model is None or not self._prototypes:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="embeddings_unavailable",
            )

        # Косинусное сходство лучше работает на начале документа (заголовок/предмет)
        doc_text = text[:1000]
        doc_embedding = self.model.encode(doc_text, normalize_embeddings=True)

        similarities = {
            dt: float(np.dot(doc_embedding, proto)) for dt, proto in self._prototypes.items()
        }

        if not similarities:
            return ClassificationResult(
                doctype="UNKNOWN", confidence=0.0, level=self.level, method="no_prototypes"
            )

        sorted_types = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        best_type, best_sim = sorted_types[0]

        # Конфиг для метаданных
        best_cfg = self._configs.get(best_type, {})
        meta = best_cfg.get("metadata", {}) or {}

        # Нормализация уверенности: 0.5 (случайно) -> 0.0, 1.0 (идеал) -> 1.0
        confidence = max(0.0, (best_sim - 0.5) * 2)

        return ClassificationResult(
            doctype=best_type,
            confidence=round(confidence, 4),
            level=self.level,
            method="embedding_similarity",
            evidence=f"cosine_sim={best_sim:.3f}",
            language=meta.get("language", "ru"),
            jurisdiction=meta.get("jurisdiction", "RU"),
            alternative_types=[
                {"type": t, "confidence": round(s, 3)} for t, s in sorted_types[1:4]
            ],
        )

    def get_document_embedding(self, text: str) -> np.ndarray | None:
        """Returns embedding for later retrieval (Stage 8)."""
        if self.model is None:
            return None
        return self.model.encode(text[:1000], normalize_embeddings=True)
