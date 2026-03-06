"""
LEGACY SemanticMatcher (Stage 6/7).

Новый L3-уровень реализован в src.classifiers.stage8.l3_semantic.L3SemanticClassifier.

L3 Semantic Matcher.
Embeds the first 1000 chars and compares to enriched type prototypes
built from normalized YAML instruction files.

Stage 8: вместо локальной SentenceTransformer используем shared EmbeddingService.
"""

from __future__ import annotations

import numpy as np

from .base import BaseClassifier, ClassificationResult
from .registry_loader import load_registry
from core.constants import CLASSIFICATION_THRESHOLDS, ClassificationLevel
from core.logging import get_logger
from services.embeddings.embedding_service import embedding_service

logger = get_logger(__name__)


class SemanticMatcher(BaseClassifier):
    """L3: cosine similarity between doc embedding and type prototypes."""

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        registry_path: str = "playbooks/document_types",
    ):
        # model_name сохраняем для обратной совместимости, но embedding_service общий
        self.model_name = model_name
        self.registry_path = registry_path
        self._prototypes: dict[str, np.ndarray] = {}
        self._configs: dict[str, dict] = {}  # Храним конфиги для метаданных
        self._threshold = CLASSIFICATION_THRESHOLDS.get("L3_accept", 0.80)

        # Загружаем прототипы сразу; embedding_service уже инициализирован на уровне сервиса
        self._load_prototypes()

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L3_SEMANTIC

    def _load_prototypes(self) -> None:
        """Build embeddings for each type that has rules."""
        try:
            registry = load_registry(self.registry_path)
        except Exception as e:
            logger.warning("SemanticMatcher: failed to load registry", error=str(e))
            return

        for doc_cfg in registry.get("document_types", []):
            doctype = doc_cfg.get("type")
            if not doctype or not doc_cfg.get("rules"):
                continue

            prototype_text = self._create_enriched_prototype(doc_cfg)
            if prototype_text.strip():
                try:
                    vec = embedding_service.encode([prototype_text])[0]
                except Exception as e:
                    logger.warning(
                        "SemanticMatcher: failed to encode prototype",
                        type=doctype,
                        error=str(e),
                    )
                    continue

                # Нормализуем сразу для косинусной близости
                norm = np.linalg.norm(vec) + 1e-9
                self._prototypes[doctype] = vec / norm
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
        rules: dict = cfg.get("rules", {}) or {}
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
        if not self._prototypes:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_prototypes",
            )

        # Косинусное сходство лучше работает на начале документа (заголовок/предмет)
        doc_text = (text or "")[:1000]
        if not doc_text.strip():
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="empty_text",
            )

        try:
            doc_vec = embedding_service.encode([doc_text])[0]
        except Exception as e:
            logger.warning(
                "SemanticMatcher: failed to encode document",
                error=str(e),
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="embedding_error",
            )

        # Нормализация и косинусные схожести
        doc_vec = doc_vec / (np.linalg.norm(doc_vec) + 1e-9)
        similarities = {dt: float(np.dot(doc_vec, proto)) for dt, proto in self._prototypes.items()}

        if not similarities:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_prototypes",
            )

        sorted_types = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
        best_type, best_sim = sorted_types[0]

        # Конфиг для метаданных
        best_cfg = self._configs.get(best_type, {})
        meta = best_cfg.get("metadata", {}) or {}

        # Нормализация уверенности, как раньше: 0.5 → 0.0, 1.0 → 1.0
        confidence_raw = max(0.0, (best_sim - 0.5) * 2)

        # На уровне L3 сам по себе порог не режем, это делает HybridClassifier через L3_accept
        return ClassificationResult(
            doctype=best_type,
            confidence=round(confidence_raw, 4),
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
        doc_text = (text or "")[:1000]
        if not doc_text.strip():
            return None
        try:
            vec = embedding_service.encode([doc_text])[0]
        except Exception as e:
            logger.warning(
                "SemanticMatcher: failed to encode document for retrieval",
                error=str(e),
            )
            return None
        return vec / (np.linalg.norm(vec) + 1e-9)
