"""
L3 SemanticClassifier — семантическая классификация на эмбеддингах (Stage 8).

Production-версия с:
- multi-window encoding (первые 800 + средние 600 + последние 400 символов)
- positive/negative prototypes (scope vs anti-scope)
- margin-based calibration (confidence учитывает разницу с runner-up)
- полной диагностикой для orchestrator и voting

Назначение:
- Третий уровень каскада после L1 (filename) и L2 (header).
- Работает по смыслу текста, а не по ключевым словам.
- Позволяет различать типы документов даже при нестандартных названиях/шапках.

Источники знаний:
- YAMLRegistry.get_all_configs() даёт DocumentTypeConfig для каждого типа.
- Для каждого типа строится:
  - positive prototype (обогащённый прототип из name, description, keywords)
  - negative prototype (anti-scope из exclusions и противоположных типов)

Как работает:
- На старте L3 загружает все типы из YAMLRegistry и:
  - собирает текстовый прототип для каждого типа (concat полей),
  - кодирует positive и negative прототипы через EmbeddingService,
  - нормализует векторы и кеширует их в памяти.
- При классификации:
  - извлекает 3 окна из текста (начало, середина, конец),
  - получает embedding для каждого окна,
  - вычисляет взвешенную сумму окон,
  - считает positive_similarity и negative_similarity,
  - финальный score = pos_sim - 0.35 * neg_sim,
  - калибрует confidence через margin (разница с runner-up).

Возвращаемое значение:
- ClassificationResult с полями:
  - doctype: лучший тип по adjusted similarity,
  - confidence: калиброванная уверенность через margin,
  - level: ClassificationLevel.L3_SEMANTIC,
  - method: "embedding_similarity",
  - evidence: строка вида "pos_sim=0.92, neg_sim=0.15, margin=0.23",
  - language, jurisdiction: из YAML-метаданных типа,
  - alternative_types: топ-несколько альтернатив с их similarity,
  - extra: {
      "raw_similarity": float,         # adjusted score (pos - 0.35*neg)
      "positive_similarity": float,    # чистый positive similarity
      "negative_similarity": float,    # чистый negative similarity
      "margin": float,                 # разница между top-1 и top-2
      "signal_quality": float,         # min(1.0, raw_sim + 0.15)
      "negative_hits": 0,              # для voting (L3 не имеет explicit exclusions)
      "ambiguity_penalty": float,      # если margin < 0.20
      "input_quality": float,          # качество входа (длина текста)
      "top_n": [...]
    }

Роль в каскаде:
- L3 — самый «тяжёлый» и умный этап перед LLM.
- HybridClassifier использует margin и input_quality для L4 routing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from ..base import BaseClassifier, ClassificationResult
from ..yaml_registry import DocumentTypeConfig, YAMLRegistry
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger
from services.embeddings.embedding_service import embedding_service

logger = get_logger(__name__)


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Ограничение значения в диапазоне [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def _estimate_input_quality(text: str) -> float:
    """
    Оценка качества входа для orchestrator/voter.
    Короткий текст (< 300 символов) даёт менее надёжный сигнал.
    """
    text_len = len((text or "").strip())
    if text_len <= 0:
        return 0.0
    if text_len >= 1500:
        return 1.0
    return round(_clamp(0.5 + (text_len - 300) / 1200.0 * 0.5, 0.5, 1.0), 3)


class L3SemanticClassifier(BaseClassifier):
    """L3: multi-window cosine similarity with positive/negative prototypes."""

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        self._registry = registry or YAMLRegistry.get_instance()
        self._positive_prototypes: Dict[str, np.ndarray] = {}
        self._negative_prototypes: Dict[str, np.ndarray] = {}
        self._meta: Dict[str, dict] = {}
        self._threshold: float = float(
            getattr(settings, "CLASSIFICATION_L3_ACCEPT", 0.75)
        )

        self._load_prototypes()

    @property
    def level(self) -> ClassificationLevel:
        return ClassificationLevel.L3_SEMANTIC

    def _load_prototypes(self) -> None:
        """Строим positive и negative embedding-прототипы для каждого типа."""
        configs: List[DocumentTypeConfig] = self._registry.get_all_configs()
        if not configs:
            logger.warning("L3SemanticClassifier: no configs in YAMLRegistry")
            return

        positive_texts: List[str] = []
        negative_texts: List[str] = []
        type_codes: List[str] = []
        meta_list: List[dict] = []

        for cfg in configs:
            pos_proto, neg_proto = self._create_dual_prototypes(cfg)

            if not pos_proto.strip():
                continue

            positive_texts.append(pos_proto)
            negative_texts.append(neg_proto if neg_proto.strip() else "neutral document")
            type_codes.append(cfg.type_code)
            meta_list.append(
                {
                    "language": cfg.language,
                    "jurisdiction": cfg.jurisdiction,
                    "name": cfg.name,
                }
            )

        if not positive_texts:
            logger.warning("L3SemanticClassifier: no prototype texts built")
            return

        logger.info(
            "L3 prototypes building",
            extra={"types_count": len(type_codes)},
        )

        try:
            pos_vecs = embedding_service.encode(positive_texts)
            neg_vecs = embedding_service.encode(negative_texts)
        except Exception as e:
            logger.warning(
                "L3SemanticClassifier: failed to encode prototypes",
                error=str(e),
            )
            return

        pos_vecs = np.asarray(pos_vecs, dtype=np.float32)
        neg_vecs = np.asarray(neg_vecs, dtype=np.float32)

        pos_vecs = pos_vecs / (np.linalg.norm(pos_vecs, axis=1, keepdims=True) + 1e-9)
        neg_vecs = neg_vecs / (np.linalg.norm(neg_vecs, axis=1, keepdims=True) + 1e-9)

        for tc, pv, nv, m in zip(type_codes, pos_vecs, neg_vecs, meta_list):
            self._positive_prototypes[tc] = pv
            self._negative_prototypes[tc] = nv
            self._meta[tc] = m

        logger.info(
            "L3 prototypes loaded",
            extra={"count": len(self._positive_prototypes)},
        )

    def _create_dual_prototypes(self, cfg: DocumentTypeConfig) -> Tuple[str, str]:
        pos_parts: List[str] = []
        neg_parts: List[str] = []
        
        # === Positive prototype ===
        pos_parts.append(str(cfg.name or ""))
        raw = cfg.raw or {}
        pos_parts.append(str(raw.get("description", "") or ""))
        
        # Ключевые слова по уровням (high, medium, low)
        for impact in ("high", "medium", "low"):
            pos_parts.extend(cfg.rules_keywords.get(impact, []) or [])
            pos_parts.extend(cfg.rules_phrases.get(impact, []) or [])
        
        # Семантические маркеры
        pos_parts.extend(cfg.aliases or [])
        pos_parts.extend(cfg.section_markers or [])
        
        # Essential elements
        for elem in cfg.essential_elements or []:
            pos_parts.append(str(elem.get("element", "") or ""))
            pos_parts.extend(elem.get("keywords", []) or [])
            pos_parts.extend(elem.get("phrases", []) or [])
        
        # === Negative prototype (anti-scope) ===
        # Извлекаем exclusions из rules_keywords (YAML структура)
        exclusions = []
        
        # Вариант 1: exclusions в rules_keywords["exclusions"]
        if hasattr(cfg, 'rules_keywords') and isinstance(cfg.rules_keywords, dict):
            exclusions = cfg.rules_keywords.get("exclusions", []) or []
        
        # Вариант 2 (fallback): отдельное поле cfg.exclusions
        if not exclusions and hasattr(cfg, 'exclusions'):
            exclusions = getattr(cfg, 'exclusions', []) or []
        
        neg_parts.extend(exclusions)
        
        # Склейка
        clean_pos = [str(p) for p in pos_parts if p and isinstance(p, (str, int, float))]
        clean_neg = [str(p) for p in neg_parts if p and isinstance(p, (str, int, float))]
        
        positive = " ".join(clean_pos)[:4000]
        negative = " ".join(clean_neg)[:2000] if clean_neg else ""
        
        logger.debug(
            "L3 dual prototypes built",
            extra={
                "name": cfg.name,
                "positive_len": len(positive),
                "negative_len": len(negative),
                "exclusions_count": len(exclusions),
            },
        )
        
        return positive, negative

    def _extract_windows(self, text: str) -> List[str]:
        """
        Извлекает 3 окна из текста для multi-window encoding:
        - Первые 800 символов (заголовок + начало)
        - Средние 600 символов (центральная часть)
        - Последние 400 символов (окончание, подписи)

        Для коротких текстов (< 1500 символов) возвращает 1 окно.
        """
        text_len = len(text)

        if text_len <= 1500:
            return [text[:1000]]

        w1 = text[:800]

        mid_start = max(800, (text_len - 600) // 2)
        mid_end = mid_start + 600
        w2 = text[mid_start:mid_end]

        w3 = text[-400:]

        return [w1, w2, w3]

    def _compute_multi_window_embedding(
        self, windows: List[str]
    ) -> np.ndarray:
        """
        Кодирует каждое окно и возвращает взвешенную сумму.

        Веса окон:
        - Первое окно (заголовок): 0.50
        - Среднее окно: 0.30
        - Последнее окно: 0.20
        """
        if len(windows) == 1:
            vec = embedding_service.encode(windows)[0]
            vec = np.asarray(vec, dtype=np.float32)
            return vec / (np.linalg.norm(vec) + 1e-9)

        vecs = embedding_service.encode(windows)
        vecs = [np.asarray(v, dtype=np.float32) for v in vecs]

        weights = [0.50, 0.30, 0.20]
        combined = sum(w * v for w, v in zip(weights, vecs))
        combined = combined / (np.linalg.norm(combined) + 1e-9)

        return combined

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        if not self._positive_prototypes:
            logger.warning(
                "L3 classify skipped: no prototypes",
                extra={"filename": filename, "folder_path": folder_path},
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_prototypes",
                extra={
                    "raw_similarity": 0.0,
                    "margin": 0.0,
                    "signal_quality": 0.0,
                    "negative_hits": 0,
                    "ambiguity_penalty": 0.0,
                    "input_quality": 0.0,
                },
            )

        if not text or not text.strip() or not settings.RUNNER_EMBEDDINGS_ENABLED:
            input_quality = _estimate_input_quality(text or "")
            logger.info(
                "L3 classify skipped: empty text or embeddings disabled",
                extra={
                    "filename": filename,
                    "folder_path": folder_path,
                    "text_present": bool(text and text.strip()),
                    "embeddings_enabled": bool(settings.RUNNER_EMBEDDINGS_ENABLED),
                    "input_quality": input_quality,
                },
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="empty_or_embeddings_disabled",
                extra={
                    "raw_similarity": 0.0,
                    "margin": 0.0,
                    "signal_quality": 0.0,
                    "negative_hits": 0,
                    "ambiguity_penalty": 0.0,
                    "input_quality": input_quality,
                },
            )

        input_quality = _estimate_input_quality(text)

        logger.info(
            "L3 classify start",
            extra={
                "filename": filename,
                "folder_path": folder_path,
                "doc_text_len": len(text),
                "doc_text_excerpt": repr(text[:400]),
                "input_quality": input_quality,
            },
        )

        windows = self._extract_windows(text)

        try:
            doc_vec = self._compute_multi_window_embedding(windows)
        except Exception as e:
            logger.warning(
                "L3SemanticClassifier: failed to encode document",
                error=str(e),
                extra={"filename": filename, "folder_path": folder_path},
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="embedding_error",
                extra={
                    "raw_similarity": 0.0,
                    "margin": 0.0,
                    "signal_quality": 0.0,
                    "negative_hits": 0,
                    "ambiguity_penalty": 0.0,
                    "input_quality": input_quality,
                },
            )

        pos_sims: Dict[str, float] = {}
        neg_sims: Dict[str, float] = {}
        adjusted_sims: Dict[str, float] = {}

        for tc in self._positive_prototypes.keys():
            pos_proto = self._positive_prototypes[tc]
            neg_proto = self._negative_prototypes.get(tc)

            pos_sim = float(np.dot(doc_vec, pos_proto))
            neg_sim = float(np.dot(doc_vec, neg_proto)) if neg_proto is not None else 0.0

            pos_sims[tc] = pos_sim
            neg_sims[tc] = neg_sim

            adjusted = pos_sim - 0.35 * neg_sim
            adjusted_sims[tc] = adjusted

        if not adjusted_sims:
            logger.warning(
                "L3 classify: no similarities computed",
                extra={"filename": filename},
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="no_similarities",
                extra={
                    "raw_similarity": 0.0,
                    "margin": 0.0,
                    "signal_quality": 0.0,
                    "negative_hits": 0,
                    "ambiguity_penalty": 0.0,
                    "input_quality": input_quality,
                },
            )

        sorted_types = sorted(adjusted_sims.items(), key=lambda x: x[1], reverse=True)
        best_type, best_adjusted_sim = sorted_types[0]

        best_pos_sim = pos_sims[best_type]
        best_neg_sim = neg_sims[best_type]

        margin = 0.0
        if len(sorted_types) >= 2:
            margin = best_adjusted_sim - sorted_types[1][1]

        signal_quality = min(1.0, best_adjusted_sim + 0.15)

        ambiguity_penalty = 0.0
        if margin < 0.20:
            ambiguity_penalty = 0.15 * (1.0 - margin / 0.20)
            ambiguity_penalty = _clamp(ambiguity_penalty, 0.0, 0.15)

        alternatives = [
            {
                "type": t,
                "similarity": round(s, 4),
                "positive_sim": round(pos_sims[t], 4),
                "negative_sim": round(neg_sims[t], 4),
            }
            for t, s in sorted_types[1:4]
        ]

        logger.info(
            "L3 similarities",
            extra={
                "filename": filename,
                "best_type": best_type,
                "best_adjusted_sim": round(best_adjusted_sim, 4),
                "best_pos_sim": round(best_pos_sim, 4),
                "best_neg_sim": round(best_neg_sim, 4),
                "margin": round(margin, 4),
                "top_alt": [
                    {"type": a["type"], "similarity": a["similarity"]}
                    for a in alternatives
                ],
            },
        )

        best_sim_clamped = _clamp(best_adjusted_sim, 0.5, 1.0)
        margin_clamped = _clamp(margin, 0.0, 0.3)

        confidence_raw = 0.55 * (best_sim_clamped - 0.5) * 2.0 + 0.45 * (margin_clamped / 0.3)
        confidence = round(_clamp(confidence_raw, 0.0, 1.0), 4)

        meta = self._meta.get(best_type, {})

        extra: Dict[str, Any] = {
            "raw_similarity": round(best_adjusted_sim, 4),
            "positive_similarity": round(best_pos_sim, 4),
            "negative_similarity": round(best_neg_sim, 4),
            "margin": round(margin, 4),
            "signal_quality": round(signal_quality, 3),
            "negative_hits": 0,
            "ambiguity_penalty": round(ambiguity_penalty, 3),
            "input_quality": input_quality,
            "top_n": alternatives,
        }

        logger.info(
            "L3 final result",
            extra={
                "filename": filename,
                "best_type": best_type,
                "confidence": confidence,
                "raw_similarity": round(best_adjusted_sim, 4),
                "margin": round(margin, 4),
            },
        )

        return ClassificationResult(
            doctype=best_type,
            confidence=confidence,
            level=self.level,
            method="embedding_similarity",
            evidence=f"pos_sim={best_pos_sim:.3f}, neg_sim={best_neg_sim:.3f}, margin={margin:.3f}",
            language=meta.get("language", "ru"),
            jurisdiction=meta.get("jurisdiction", "RU"),
            alternative_types=alternatives,
            extra=extra,
        )



