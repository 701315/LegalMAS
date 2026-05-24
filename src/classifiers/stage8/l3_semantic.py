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

_L3_VECTOR_NORM_EPSILON: float = 1e-9
_L3_WEIGHT_SUM_TOLERANCE: float = 1e-3
_L3_DEFAULT_NEGATIVE_PROTOTYPE_TEXT: str = "neutral document"


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Ограничение значения в диапазоне [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def _estimate_input_quality(text: str) -> float:
    """
    Оценка качества входа для orchestrator/voter.

    Короткий текст даёт менее надёжный сигнал. Параметры шкалы
    управляются через settings.
    """
    text_len = len((text or "").strip())
    if text_len <= 0:
        return 0.0

    min_chars: int = settings.CLASSIFICATION_L3_INPUT_QUALITY_MIN_CHARS
    full_chars: int = settings.CLASSIFICATION_L3_INPUT_QUALITY_FULL_CHARS

    if text_len >= full_chars:
        return 1.0

    quality_span = max(1, full_chars - min_chars)
    return round(
        _clamp(0.5 + (text_len - min_chars) / quality_span * 0.5, 0.5, 1.0),
        3,
    )


def _validate_weight_sum(weights: List[float], name: str) -> None:
    """Логируем неконсистентную конфигурацию весов."""
    total = float(sum(weights))
    if not np.isclose(total, 1.0, atol=_L3_WEIGHT_SUM_TOLERANCE):
        logger.warning(
            f"L3 {name} weights sum is not 1.0",
            extra={
                "weights": [round(float(w), 6) for w in weights],
                "weights_sum": round(total, 6),
            },
        )


class L3SemanticClassifier(BaseClassifier):
    """
    L3: semantic classifier на embeddings.

    Production-версия с:
    - multi-window encoding с размерами и весами из settings,
    - positive/negative prototypes,
    - margin-based calibration для confidence,
    - полной диагностикой для orchestrator и voting.
    """

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        self._registry = registry or YAMLRegistry.get_instance()
        self._positive_prototypes: Dict[str, np.ndarray] = {}
        self._negative_prototypes: Dict[str, np.ndarray] = {}
        self._meta: Dict[str, dict] = {}

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
            negative_texts.append(
                neg_proto if neg_proto.strip() else _L3_DEFAULT_NEGATIVE_PROTOTYPE_TEXT
            )
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

        pos_vecs = pos_vecs / (
            np.linalg.norm(pos_vecs, axis=1, keepdims=True) + _L3_VECTOR_NORM_EPSILON
        )
        neg_vecs = neg_vecs / (
            np.linalg.norm(neg_vecs, axis=1, keepdims=True) + _L3_VECTOR_NORM_EPSILON
        )

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

        pos_parts.append(str(cfg.name or ""))
        raw = cfg.raw or {}
        pos_parts.append(str(raw.get("description", "") or ""))

        for impact in ("high", "medium", "low"):
            pos_parts.extend(cfg.rules_keywords.get(impact, []) or [])
            pos_parts.extend(cfg.rules_phrases.get(impact, []) or [])

        pos_parts.extend(cfg.aliases or [])
        pos_parts.extend(cfg.section_markers or [])

        for elem in cfg.essential_elements or []:
            pos_parts.append(str(elem.get("element", "") or ""))
            pos_parts.extend(elem.get("keywords", []) or [])
            pos_parts.extend(elem.get("phrases", []) or [])

        exclusions: List[str] = []

        if hasattr(cfg, "rules_keywords") and isinstance(cfg.rules_keywords, dict):
            exclusions = cfg.rules_keywords.get("exclusions", []) or []

        if not exclusions and hasattr(cfg, "exclusions"):
            exclusions = getattr(cfg, "exclusions", []) or []

        neg_parts.extend(exclusions)

        clean_pos = [str(p) for p in pos_parts if p and isinstance(p, (str, int, float))]
        clean_neg = [str(p) for p in neg_parts if p and isinstance(p, (str, int, float))]

        positive = " ".join(clean_pos)[
            : settings.CLASSIFICATION_L3_POSITIVE_PROTOTYPE_MAX_CHARS
        ]
        negative = (
            " ".join(clean_neg)[: settings.CLASSIFICATION_L3_NEGATIVE_PROTOTYPE_MAX_CHARS]
            if clean_neg
            else ""
        )

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
        Извлекает окна из текста для multi-window encoding.

        Для коротких текстов возвращает одно окно, для длинных — head/middle/tail.
        Все размеры управляются через settings.
        """
        text_len = len(text)

        multi_window_min_chars: int = settings.CLASSIFICATION_L3_MULTI_WINDOW_MIN_TEXT_CHARS
        single_window_max_chars: int = settings.CLASSIFICATION_L3_SINGLE_WINDOW_MAX_CHARS
        head_chars: int = settings.CLASSIFICATION_L3_WINDOW_HEAD_CHARS
        middle_chars: int = settings.CLASSIFICATION_L3_WINDOW_MIDDLE_CHARS
        tail_chars: int = settings.CLASSIFICATION_L3_WINDOW_TAIL_CHARS

        if text_len <= multi_window_min_chars:
            return [text[:single_window_max_chars]]

        w1 = text[:head_chars]

        mid_start = max(head_chars, (text_len - middle_chars) // 2)
        mid_end = mid_start + middle_chars
        w2 = text[mid_start:mid_end]

        w3 = text[-tail_chars:]

        return [w1, w2, w3]

    def _compute_multi_window_embedding(self, windows: List[str]) -> np.ndarray:
        """
        Кодирует окна документа и возвращает нормализованную взвешенную сумму.

        Веса окон управляются через settings.
        """
        if len(windows) == 1:
            vec = embedding_service.encode(windows)[0]
            vec = np.asarray(vec, dtype=np.float32)
            return vec / (np.linalg.norm(vec) + _L3_VECTOR_NORM_EPSILON)

        vecs = embedding_service.encode(windows)
        vecs = [np.asarray(v, dtype=np.float32) for v in vecs]

        weights = [
            settings.CLASSIFICATION_L3_WINDOW_WEIGHT_HEAD,
            settings.CLASSIFICATION_L3_WINDOW_WEIGHT_MIDDLE,
            settings.CLASSIFICATION_L3_WINDOW_WEIGHT_TAIL,
        ]
        _validate_weight_sum(weights, "window")

        if len(vecs) != len(weights):
            logger.warning(
                "L3 window vectors/weights length mismatch",
                extra={
                    "windows_count": len(vecs),
                    "weights_count": len(weights),
                },
            )

        combined = sum(w * v for w, v in zip(weights, vecs))
        combined = combined / (np.linalg.norm(combined) + _L3_VECTOR_NORM_EPSILON)

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

        negative_factor: float = settings.CLASSIFICATION_L3_NEGATIVE_PROTOTYPE_FACTOR

        for tc in self._positive_prototypes.keys():
            pos_proto = self._positive_prototypes[tc]
            neg_proto = self._negative_prototypes.get(tc)

            pos_sim = float(np.dot(doc_vec, pos_proto))
            neg_sim = float(np.dot(doc_vec, neg_proto)) if neg_proto is not None else 0.0

            pos_sims[tc] = pos_sim
            neg_sims[tc] = neg_sim

            adjusted = pos_sim - negative_factor * neg_sim
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

        signal_quality = min(
            1.0,
            best_adjusted_sim + settings.CLASSIFICATION_L3_SIGNAL_QUALITY_UPLIFT,
        )

        ambiguity_penalty = 0.0
        ambiguity_margin: float = settings.CLASSIFICATION_L3_AMBIGUITY_MARGIN
        max_ambiguity_penalty: float = settings.CLASSIFICATION_L3_MAX_AMBIGUITY_PENALTY

        if ambiguity_margin > 0.0 and margin < ambiguity_margin:
            ambiguity_penalty = max_ambiguity_penalty * (1.0 - margin / ambiguity_margin)
            ambiguity_penalty = _clamp(
                ambiguity_penalty,
                0.0,
                max_ambiguity_penalty,
            )

        top_alternatives: int = max(0, settings.CLASSIFICATION_L3_TOP_ALTERNATIVES)
        alternatives = [
            {
                "type": t,
                "similarity": round(s, 4),
                "positive_sim": round(pos_sims[t], 4),
                "negative_sim": round(neg_sims[t], 4),
            }
            for t, s in sorted_types[1 : 1 + top_alternatives]
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

        sim_threshold: float = settings.CLASSIFICATION_L3_ACCEPT

        if best_adjusted_sim >= sim_threshold:
            sim_component = (best_adjusted_sim - sim_threshold) / (1.0 - sim_threshold)
        else:
            sim_component = 0.0

        margin_saturation: float = settings.CLASSIFICATION_L3_MARGIN_SATURATION
        sim_weight: float = settings.CLASSIFICATION_L3_CONFIDENCE_SIMILARITY_WEIGHT
        margin_weight: float = settings.CLASSIFICATION_L3_CONFIDENCE_MARGIN_WEIGHT

        _validate_weight_sum([sim_weight, margin_weight], "confidence")

        margin_factor = (
            _clamp(margin / margin_saturation, 0.0, 1.0)
            if margin_saturation > 0.0
            else 0.0
        )

        confidence_raw = sim_weight * sim_component + margin_weight * margin_factor
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
            evidence=(
                f"pos_sim={best_pos_sim:.3f}, "
                f"neg_sim={best_neg_sim:.3f}, "
                f"margin={margin:.3f}"
            ),
            language=meta.get("language", "ru"),
            jurisdiction=meta.get("jurisdiction", "RU"),
            alternative_types=alternatives,
            extra=extra,
        )



