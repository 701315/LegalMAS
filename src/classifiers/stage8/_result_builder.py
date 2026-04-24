# src/classifiers/stage8/_result_builder.py
"""
Построение финального результата классификации.

Отвечает за:
  - определение applicable_triggers через YAMLRegistry;
  - вычисление зоны уверенности (confident / low / unknown);
  - сборку HybridClassificationResultDTO и возврат его как dict.
"""
from __future__ import annotations

from typing import Optional

from classifiers.base import HybridClassificationCandidate, HybridClassificationResultDTO
from ..yaml_registry import YAMLRegistry
from core.logging import get_logger

logger = get_logger(__name__)


class ResultBuilder:
    """
    Строит финальный dict-результат из компонентов классификации.
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
        Построить результат через HybridClassificationResultDTO и вернуть .__dict__.

        Внешний контракт HybridClassifier.classify_document остаётся dict.
        """
        dto_candidates = [
            HybridClassificationCandidate(
                doctype=c.get("type_code") or c.get("doctype", "UNKNOWN"),
                confidence=float(c.get("confidence") or 0.0),
                level=str(c.get("level") or ""),
                method=c.get("method"),
                evidence=c.get("evidence"),
                language=c.get("language"),
                jurisdiction=c.get("jurisdiction"),
                extra={
                    k: v for k, v in c.items()
                    if k not in {
                        "type_code", "doctype", "confidence", "level",
                        "method", "evidence", "language", "jurisdiction",
                    }
                },
            )
            for c in (candidates or [])
        ]

        dto = HybridClassificationResultDTO(
            final_type=final_type,
            final_confidence=float(final_confidence or 0.0),
            level=level,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=list(applicable_triggers or []),
            levels_tried=list(levels_tried or []),
            candidates=dto_candidates,
            details=details or {},
        )
        result = dto.__dict__
        # Любые extra-поля (например, copied_from_master) добавляем поверх
        result.update(extra_fields)
        return result
    
    