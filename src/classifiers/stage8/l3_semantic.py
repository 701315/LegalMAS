# src/classifiers/stage8/l3_semantic.py

"""
L3 SemanticClassifier — семантическая классификация на эмбеддингах (Stage 8).

Назначение:
- Третий уровень каскада после L1 (filename) и L2 (header).
- Работает по смыслу текста, а не по ключевым словам.
- Позволяет различать типы документов даже при нестандартных названиях/шапках.

Источники знаний:
- YAMLRegistry.get_all_configs() даёт полный YAML-конфиг для каждого типа.
- Для каждого типа строится "обогащённый прототип" из:
  - name, description,
  - rules.keywords / rules.phrases (high/medium/low),
  - metadata (aliases, section_markers),
  - essential_elements (ключевые элементы договора).

Как работает:
- На старте L3 загружает все типы из YAMLRegistry и:
  - собирает текстовый прототип для каждого типа (concat полей),
  - кодирует прототипы через общий EmbeddingService,
  - нормализует векторы и кеширует их в памяти.
- При классификации:
  - берём первые ~1000 символов текста документа,
  - получаем embedding документа,
  - считаем косинусное сходство со всеми прототипами,
  - выбираем лучший тип и несколько альтернатив.

Возвращаемое значение:
- ClassificationResult с полями:
  - doctype: лучший тип по косинусному сходству,
  - confidence: нормализованная уверенность (0–1, на основе similarity),
  - level: ClassificationLevel.L3_SEMANTIC,
  - method: "embedding_similarity",
  - evidence: строка вида "cosine_sim=0.923",
  - language, jurisdiction: из YAML-метаданных типа,
  - alternative_types: топ-несколько альтернатив с их similarity.

Роль в каскаде:
- L3 — самый «тяжёлый» и умный этап перед LLM.
- Новый HybridClassifier использует CLASSIFICATION_L3_ACCEPT и общий voting,
  чтобы решать, когда L3 может дать финальный вердикт или перебить L1/L2.
"""

from __future__ import annotations

import numpy as np

from ..base import BaseClassifier, ClassificationResult
from ..yaml_registry import DocumentTypeConfig, YAMLRegistry
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger
from services.embeddings.embedding_service import embedding_service

logger = get_logger(__name__)


class L3SemanticClassifier(BaseClassifier):
    """L3: cosine similarity between doc embedding and type prototypes."""

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        # Используем singleton по умолчанию, но даём возможность подменять в тестах
        self._registry = registry or YAMLRegistry.get_instance()
        self._prototypes: dict[str, np.ndarray] = {}
        self._meta: dict[str, dict] = {}  # метаданные типа (язык, юрисдикция и др.)
        self._threshold: float = settings.CLASSIFICATION_L3_ACCEPT

        self._load_prototypes()

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L3_SEMANTIC

    def _load_prototypes(self) -> None:
        """Строим embedding-прототипы для каждого типа из YAMLRegistry."""
        configs: list[DocumentTypeConfig] = self._registry.get_all_configs()
        if not configs:
            logger.warning("L3SemanticClassifier: no configs in YAMLRegistry")
            return

        texts: list[str] = []
        type_codes: list[str] = []
        meta_list: list[dict] = []

        for cfg in configs:
            # cfg.raw — оригинальный YAML-конфиг
            proto_text = self._create_enriched_prototype(cfg.raw)
            if not proto_text.strip():
                continue

            texts.append(proto_text)
            type_codes.append(cfg.type_code)
            meta_list.append(
                {
                    "language": cfg.language,
                    "jurisdiction": cfg.jurisdiction,
                    "name": cfg.name,
                }
            )

        if not texts:
            logger.warning("L3SemanticClassifier: no prototype texts built")
            return

        try:
            vecs = embedding_service.encode(texts)
        except Exception as e:
            logger.warning("L3SemanticClassifier: failed to encode prototypes", error=str(e))
            return

        vecs = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        vecs = vecs / norms

        for tc, v, m in zip(type_codes, vecs, meta_list):
            self._prototypes[tc] = v
            self._meta[tc] = m

        logger.info("L3 prototypes loaded", count=len(self._prototypes))

    def _create_enriched_prototype(self, cfg: dict) -> str:
        """
        Обогащённый прототип, аналогичный твоему SemanticMatcher:

        - name, description
        - rules.keywords/phrases (по уровням high/medium/low)
        - semantic маркеры (party_roles, essential_terms, aliases и т.п.)
        """
        parts: list[str] = []

        # 1. Основная информация
        parts.append(str(cfg.get("name", "") or ""))
        parts.append(str(cfg.get("description", "") or ""))

        # 2. Ключевые слова и фразы
        rules: dict = cfg.get("rules", {}) or {}
        for impact in ("high", "medium", "low"):
            parts.extend(rules.get("keywords", {}).get(impact, []) or [])
            parts.extend(rules.get("phrases", {}).get(impact, []) or [])

        # 3. Семантические поля (если нормализованы загрузчиком/редактором YAML)
        metadata = cfg.get("metadata", {}) or {}
        parts.extend(metadata.get("aliases", []) or [])
        parts.extend(metadata.get("section_markers", []) or [])

        # 4. essential_elements (если есть)
        for elem in cfg.get("essential_elements") or []:
            parts.append(str(elem.get("element", "") or ""))
            parts.extend(elem.get("keywords", []) or [])
            parts.extend(elem.get("phrases", []) or [])

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

        if not text or not text.strip() or not settings.RUNNER_EMBEDDINGS_ENABLED:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="empty_or_embeddings_disabled",
            )

        # Берём первые ~1000 символов как репрезентативный фрагмент
        doc_text = text[:1000]

        try:
            doc_vec = embedding_service.encode([doc_text])[0]
        except Exception as e:
            logger.warning(
                "L3SemanticClassifier: failed to encode document",
                error=str(e),
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="embedding_error",
            )

        doc_vec = np.asarray(doc_vec, dtype=np.float32)
        doc_vec = doc_vec / (np.linalg.norm(doc_vec) + 1e-9)

        # Косинусная близость со всеми прототипами
        sims: dict[str, float] = {
            tc: float(np.dot(doc_vec, proto)) for tc, proto in self._prototypes.items()
        }

        if not sims:
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_similarities",
            )

        sorted_types = sorted(sims.items(), key=lambda x: x[1], reverse=True)
        best_type, best_sim = sorted_types[0]

        # Сырый score можно чуть нормализовать к [0, 1]
        confidence_raw = max(0.0, (best_sim - 0.5) * 2.0)

        # Порог L3 применяем на уровне HybridClassifier, здесь отдаём сырую оценку
        meta = self._meta.get(best_type, {})
        alternatives = [{"type": t, "confidence": round(s, 3)} for t, s in sorted_types[1:4]]

        return ClassificationResult(
            doctype=best_type,
            confidence=round(confidence_raw, 4),
            level=self.level,
            method="embedding_similarity",
            evidence=f"cosine_sim={best_sim:.3f}",
            language=meta.get("language", "ru"),
            jurisdiction=meta.get("jurisdiction", "RU"),
            alternative_types=alternatives,
        )
