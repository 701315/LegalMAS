# src/classifiers/stage8/_result_builder.py

"""
Построение финального результата классификации.

Отвечает за:
 - определение applicable_triggers через YAMLRegistry;
 - вычисление зоны уверенности (confident / low / unknown);
 - применение unknown-corridor для final_type;
 - сборку HybridClassificationResultDTO и возврат его как dict.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO
from ..yaml_registry import YAMLRegistry
from core.logging import get_logger


logger = get_logger(__name__)


class ResultBuilder:
    """
    Строит финальный dict-результат из компонентов классификации.

    ВАЖНО:
    - HybridClassifier вызывает builder как финальную точку во множестве веток
      (copied / early-return / hybrid voting / L4 / fallback).
    - Поэтому builder должен сам гарантировать консистентный финальный контракт:
      * details["confidence_zone"]
      * details["requires_manual_review"]
      * применение unknown corridor к final_type
    """

    def __init__(
        self,
        registry: YAMLRegistry,
        hybrid_accept: float,
        unknown_max: float,
    ) -> None:
        self.registry = registry
        self.hybrid_accept = hybrid_accept
        self.unknown_max = unknown_max

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_triggers(self, doc_id: str, final_type: str) -> list[str]:
        """
        Построить applicable_triggers для финального типа документа.
        Если тип UNKNOWN или конфиг не найден — возвращаем [].
        """
        if not isinstance(final_type, str) or not final_type or final_type == "UNKNOWN":
            return []

        cfg = self.registry.get_config(final_type)
        if cfg is None:
            logger.info(
                "ResultBuilder: no YAML config found for final_type",
                extra={"doc_id": doc_id, "final_type": final_type},
            )
            return []

        try:
            return list(getattr(cfg, "trigger_ids", []) or [])
        except Exception as e:
            logger.warning(
                "ResultBuilder: failed to build applicable_triggers",
                extra={"doc_id": doc_id, "final_type": final_type, "error": str(e)},
            )
            return []

    def confidence_zone(self, confidence: float) -> tuple[str, bool]:
        """
        Возвращает (zone_name, requires_manual_review).

        Зоны:
          confident  — >= hybrid_accept, проверка не нужна;
          low        — между unknown_max и hybrid_accept, желательна проверка;
          unknown    — <= unknown_max, требует внимания.
        """
        if confidence >= self.hybrid_accept:
            return "confident", False
        if confidence <= self.unknown_max:
            return "unknown", True
        return "low", True

    def apply_unknown_corridor(self, final_type: str, final_conf: float) -> str:
        """
        Если уверенность ниже unknown_max — принудительно возвращаем 'UNKNOWN'.
        """
        return "UNKNOWN" if final_conf <= self.unknown_max else final_type

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_float(self, value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _normalize_candidates(
        self,
        candidates: list[dict] | None,
    ) -> list[HybridClassificationCandidate]:
        normalized: list[HybridClassificationCandidate] = []

        for c in (candidates or []):
            if not isinstance(c, dict):
                logger.warning(
                    "ResultBuilder: candidate is not a dict, skipped",
                    extra={"candidate_type": type(c).__name__},
                )
                continue

            normalized.append(
                HybridClassificationCandidate(
                    doctype=c.get("type_code") or c.get("doctype", "UNKNOWN"),
                    confidence=self._safe_float(c.get("confidence")),
                    level=str(c.get("level") or ""),
                    method=c.get("method"),
                    evidence=c.get("evidence"),
                    language=c.get("language"),
                    jurisdiction=c.get("jurisdiction"),
                    extra={
                        k: v
                        for k, v in c.items()
                        if k
                        not in {
                            "type_code",
                            "doctype",
                            "confidence",
                            "level",
                            "method",
                            "evidence",
                            "language",
                            "jurisdiction",
                        }
                    },
                )
            )

        return normalized

    # ------------------------------------------------------------------
    # Final assembly
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        final_type: Optional[str],
        final_confidence: float,
        level: Optional[str],
        language: Optional[str],
        jurisdiction: Optional[str],
        applicable_triggers: list[str],
        levels_tried: list[str],
        candidates: list[dict],
        details: dict,
        **extra_fields,
    ) -> dict:
        """
        Построить результат через HybridClassificationResultDTO и вернуть dict.

        Внешний контракт HybridClassifier.classify_document остаётся dict.

        Builder сам гарантирует:
        - details["confidence_zone"]
        - details["requires_manual_review"]
        - unknown corridor для final_type
        """
        safe_final_confidence = self._safe_float(final_confidence, 0.0)

        # Defensive copy: builder — финальная граница контракта,
        # не держим внешнюю mutable-ссылку на details.
        safe_details = dict(details or {})

        zone_name, manual_review = self.confidence_zone(safe_final_confidence)
        safe_details["confidence_zone"] = zone_name
        safe_details["requires_manual_review"] = manual_review

        normalized_final_type = self.apply_unknown_corridor(
            final_type=(final_type or "UNKNOWN"),
            final_conf=safe_final_confidence,
        )

        dto_candidates = self._normalize_candidates(candidates)

        dto = HybridClassificationResultDTO(
            final_type=normalized_final_type,
            final_confidence=safe_final_confidence,
            level=level,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=list(applicable_triggers or []),
            levels_tried=list(levels_tried or []),
            candidates=dto_candidates,
            details=safe_details,
        )

        result = asdict(dto)

        # Любые extra-поля (например, copied_from_master) добавляем поверх
        result.update(extra_fields)
        return result
    

    