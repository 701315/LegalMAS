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

from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO
from core.config import settings
from core.logging import get_logger

from ..yaml_registry import YAMLRegistry

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
      * согласованность level / applicable_triggers / details при UNKNOWN
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

    def build_triggers(self, entity_id: str, final_type: str) -> list[str]:
        """
        Построить applicable_triggers для финального типа документа/сегмента.
        Если тип UNKNOWN или конфиг не найден — возвращаем [].
        """
        normalized_final_type = self._normalize_final_type(final_type)
        if normalized_final_type == "UNKNOWN":
            return []

        try:
            cfg = self.registry.get_config(normalized_final_type)
        except Exception as e:
            logger.warning(
                "ResultBuilder: failed to load YAML config for final_type",
                extra={
                    "entity_id": entity_id,
                    "final_type": normalized_final_type,
                    "error": str(e),
                },
            )
            return []

        if cfg is None:
            logger.info(
                "ResultBuilder: no YAML config found for final_type",
                extra={"entity_id": entity_id, "final_type": normalized_final_type},
            )
            return []

        try:
            raw = list(getattr(cfg, "trigger_ids", []) or [])
            return [str(x).strip() for x in raw if str(x).strip()]
        except Exception as e:
            logger.warning(
                "ResultBuilder: failed to build applicable_triggers",
                extra={
                    "entity_id": entity_id,
                    "final_type": normalized_final_type,
                    "error": str(e),
                },
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
        Если уверенность ниже или равна unknown_max — принудительно возвращаем 'UNKNOWN'.
        """
        normalized_final_type = self._normalize_final_type(final_type)
        return "UNKNOWN" if final_conf <= self.unknown_max else normalized_final_type

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_float(self, value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _normalize_final_type(self, value: object) -> str:
        if value is None:
            return "UNKNOWN"
        result = str(value).strip()
        if not result:
            return "UNKNOWN"
        if result.upper() == "UNKNOWN":
            return "UNKNOWN"
        return result

    def _normalize_string_list(self, values: list[object] | None) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for value in values or []:
            text = str(value).strip() if value is not None else ""
            if not text or text in seen:
                continue
            result.append(text)
            seen.add(text)

        return result

    def _normalize_candidates(
        self,
        candidates: list[dict] | None,
    ) -> list[HybridClassificationCandidate]:
        normalized: list[HybridClassificationCandidate] = []

        for c in candidates or []:
            if not isinstance(c, dict):
                logger.warning(
                    "ResultBuilder: candidate is not a dict, skipped",
                    extra={"candidate_type": type(c).__name__},
                )
                continue

            normalized.append(
                HybridClassificationCandidate(
                    doctype=self._normalize_final_type(c.get("type_code") or c.get("doctype")),
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

    def _merge_extra_fields(self, result: dict, extra_fields: dict) -> dict:
        reserved = {
            "final_type",
            "final_confidence",
            "level",
            "language",
            "jurisdiction",
            "applicable_triggers",
            "levels_tried",
            "candidates",
            "details",
        }
        for key, value in (extra_fields or {}).items():
            if key in reserved:
                logger.warning(
                    "ResultBuilder: extra_field ignored because it would overwrite canonical result field",
                    extra={"field": key},
                )
                continue
            result[key] = value
        return result

    # ------------------------------------------------------------------
    # Final assembly
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        final_type: str | None,
        final_confidence: float,
        level: str | None,
        language: str | None,
        jurisdiction: str | None,
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
        - консистентность UNKNOWN-результата:
          * level = None
          * applicable_triggers = []
          * details["unknown_corridor"] содержит факт override
        """
        safe_final_confidence = self._safe_float(final_confidence, 0.0)
        original_final_type = self._normalize_final_type(final_type)

        safe_details = dict(details or {})
        safe_details.setdefault(
            "schema_version",
            int(getattr(settings, "CLASSIFICATION_DECISION_TRACE_SCHEMA_VERSION", 1)),
        )

        normalized_final_type = self.apply_unknown_corridor(
            final_type=original_final_type,
            final_conf=safe_final_confidence,
        )
        corridor_applied = normalized_final_type != original_final_type

        zone_name, manual_review_by_confidence = self.confidence_zone(safe_final_confidence)
        existing_requires_review = bool(safe_details.get("requires_manual_review", False))

        safe_details["confidence_zone"] = zone_name
        safe_details["requires_manual_review_by_confidence"] = manual_review_by_confidence
        safe_details["requires_manual_review"] = (
            existing_requires_review
            or manual_review_by_confidence
            or normalized_final_type == "UNKNOWN"
        )
        safe_details["final_decision_zone"] = (
            "unknown" if normalized_final_type == "UNKNOWN" else zone_name
        )

        if not isinstance(safe_details.get("unknown_corridor"), dict):
            safe_details["unknown_corridor"] = {}

        safe_details["unknown_corridor"].update(
            {
                "applied": corridor_applied,
                "original_type": original_final_type,
                "original_confidence": safe_final_confidence,
                "threshold": self.unknown_max,
                "final_type_after_corridor": normalized_final_type,
            }
        )

        safe_level = level
        safe_applicable_triggers = self._normalize_string_list(applicable_triggers)
        safe_levels_tried = self._normalize_string_list(levels_tried)

        if normalized_final_type == "UNKNOWN":
            safe_level = None
            safe_applicable_triggers = []

        dto_candidates = self._normalize_candidates(candidates)

        dto = HybridClassificationResultDTO(
            final_type=normalized_final_type,
            final_confidence=safe_final_confidence,
            level=safe_level,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=safe_applicable_triggers,
            levels_tried=safe_levels_tried,
            candidates=dto_candidates,
            details=safe_details,
        )

        result = asdict(dto)
        return self._merge_extra_fields(result, extra_fields)
