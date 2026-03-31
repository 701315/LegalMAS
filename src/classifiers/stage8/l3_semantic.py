# src/classifiers/stage8/l3_semantic.py

"""
L3 SemanticClassifier — семантическая классификация на эмбеддингах (Stage 8).


Назначение:
- Третий уровень каскада после L1 (filename) и L2 (header).
- Работает по смыслу текста, а не по ключевым словам.
- Позволяет различать типы документов даже при нестандартных названиях/шапках.


Источники знаний:
- YAMLRegistry.get_all_configs() даёт DocumentTypeConfig для каждого типа.
- Для каждого типа строится "обогащённый прототип" из:
  - name, description,
  - rules_keywords / rules_phrases (high/medium/low) из classification_runtime_v1.rules,
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
  - alternative_types: топ-несколько альтернатив с их similarity,
  - extra: {
      "raw_similarity": float,
      "top_n": [{ "type": str, "similarity": float }, ...],
    }


Роль в каскаде:
- L3 — самый «тяжёлый» и умный этап перед LLM.
- Новый HybridClassifier использует CLASSIFICATION_L3_ACCEPT и общий voting,
  чтобы решать, когда L3 может дать финальный вердикт или перебить L1/L2.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
        # Порог используется в HybridClassifier, здесь храним для совместимости
        self._threshold: float = float(
            getattr(settings, "CLASSIFICATION_L3_ACCEPT", 0.75)
        )

        self._load_prototypes()

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L3_SEMANTIC

    def _load_prototypes(self) -> None:
        """Строим embedding-прототипы для каждого типа из YAMLRegistry."""
        configs: List[DocumentTypeConfig] = self._registry.get_all_configs()
        if not configs:
            logger.warning("L3SemanticClassifier: no configs in YAMLRegistry")
            return

        texts: List[str] = []
        type_codes: List[str] = []
        meta_list: List[dict] = []

        for cfg in configs:
            # cfg — нормализованный конфиг типа (DocumentTypeConfig)
            proto_text = self._create_enriched_prototype(cfg)

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

        logger.info(
            "L3 prototypes building",
            extra={
                "types_count": len(type_codes),
            },
        )

        try:
            vecs = embedding_service.encode(texts)
        except Exception as e:
            logger.warning(
                "L3SemanticClassifier: failed to encode prototypes",
                error=str(e),
            )
            return

        vecs = np.asarray(vecs, dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
        vecs = vecs / norms

        for tc, v, m in zip(type_codes, vecs, meta_list):
            self._prototypes[tc] = v
            self._meta[tc] = m

        logger.info(
            "L3 prototypes loaded",
            extra={"count": len(self._prototypes)},
        )

    def _create_enriched_prototype(self, cfg: DocumentTypeConfig) -> str:
        """
        Обогащённый прототип для семантической классификации L3.

        Для непрофессионального программиста:
        - Здесь мы собираем один большой текст, который описывает тип документа.
        - Этот текст потом кодируется в вектор (embedding) и используется
          для сравнения с текстом конкретного документа.

        Используем поля DocumentTypeConfig, которые уже собраны из YAML:
        - cfg.name, cfg.raw["description"]
        - cfg.rules_keywords / cfg.rules_phrases (high/medium/low)
        - cfg.aliases, cfg.section_markers
        - cfg.essential_elements (element, keywords, phrases)
        """
        parts: list[str] = []

        # 1. Основная информация о типе
        parts.append(str(cfg.name or ""))
        raw = cfg.raw or {}
        parts.append(str(raw.get("description", "") or ""))

        # 2. Ключевые слова и фразы по уровням влияния
        for impact in ("high", "medium", "low"):
            parts.extend(cfg.rules_keywords.get(impact, []) or [])
            parts.extend(cfg.rules_phrases.get(impact, []) or [])

        # 3. Семантические маркеры из metadata
        parts.extend(cfg.aliases or [])
        parts.extend(cfg.section_markers or [])

        # 4. Ключевые элементы договора (essential_elements)
        for elem in cfg.essential_elements or []:
            parts.append(str(elem.get("element", "") or ""))
            parts.extend(elem.get("keywords", []) or [])
            parts.extend(elem.get("phrases", []) or [])

        # Фильтруем пустые значения и нестроковые типы,
        # склеиваем всё в одну строку и обрезаем до разумной длины.
        clean_parts = [str(p) for p in parts if p and isinstance(p, (str, int, float))]
        proto = " ".join(clean_parts)[:4000]

        logger.debug(
            "L3 prototype built",
            extra={
                "name": cfg.name,
                "length": len(proto),
            },
        )

        return proto

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        if not self._prototypes:
            logger.warning(
                "L3 classify skipped: no prototypes",
                extra={"filename": filename, "folder_path": folder_path},
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_prototypes",
            )

        if not text or not text.strip() or not settings.RUNNER_EMBEDDINGS_ENABLED:
            logger.info(
                "L3 classify skipped: empty text or embeddings disabled",
                extra={
                    "filename": filename,
                    "folder_path": folder_path,
                    "text_present": bool(text and text.strip()),
                    "embeddings_enabled": bool(settings.RUNNER_EMBEDDINGS_ENABLED),
                },
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="empty_or_embeddings_disabled",
            )

        # Берём первые ~1000 символов как репрезентативный фрагмент
        doc_text = text[:1000]

        logger.info(
            "L3 classify start",
            extra={
                "filename": filename,
                "folder_path": folder_path,
                "doc_text_len": len(text),
                "doc_text_excerpt": repr(doc_text[:400]),
            },
        )

        try:
            doc_vec = embedding_service.encode([doc_text])[0]
        except Exception as e:
            logger.warning(
                "L3SemanticClassifier: failed to encode document",
                error=str(e),
                extra={
                    "filename": filename,
                    "folder_path": folder_path,
                },
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
        sims: Dict[str, float] = {
            tc: float(np.dot(doc_vec, proto)) for tc, proto in self._prototypes.items()
        }

        if not sims:
            logger.warning(
                "L3 classify: no similarities computed",
                extra={"filename": filename},
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_similarities",
            )

        sorted_types = sorted(sims.items(), key=lambda x: x[1], reverse=True)
        best_type, best_sim = sorted_types[0]

        # Топ-альтернатив для логов
        top_alt_for_log = [
            {"type": t, "similarity": float(s)} for t, s in sorted_types[1:4]
        ]

        logger.info(
            "L3 similarities",
            extra={
                "filename": filename,
                "best_type": best_type,
                "best_sim": float(best_sim),
                "top_alt": top_alt_for_log,
            },
        )

        # Нормализация similarity → confidence в [0, 1].
        # Линейная шкала вокруг 0.5: 0.5 → 0.0, 1.0 → 1.0
        confidence_raw = max(0.0, (best_sim - 0.5) * 2.0)
        confidence = round(confidence_raw, 4)

        meta = self._meta.get(best_type, {})
        alternatives = [
            {"type": t, "similarity": round(s, 4)} for t, s in sorted_types[1:4]
        ]

        extra: Dict[str, Any] = {
            "raw_similarity": float(best_sim),
            "top_n": alternatives,
        }

        logger.info(
            "L3 final result",
            extra={
                "filename": filename,
                "best_type": best_type,
                "confidence": confidence,
                "raw_similarity": float(best_sim),
            },
        )

        return ClassificationResult(
            doctype=best_type,
            confidence=confidence,
            level=self.level,
            method="embedding_similarity",
            evidence=f"cosine_sim={best_sim:.3f}",
            language=meta.get("language", "ru"),
            jurisdiction=meta.get("jurisdiction", "RU"),
            alternative_types=alternatives,
            extra=extra,
        )