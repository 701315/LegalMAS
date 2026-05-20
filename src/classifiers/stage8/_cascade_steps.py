# src/classifiers/stage8/_cascade_steps.py

"""
Шаги каскада классификации L1, L2, L3.

PR6: вынесены из hybrid_classifier.py.

Содержит:
  CascadeSteps — методы run_l1, run_l2, run_l3

Намеренно НЕ содержит:
  - L4 execution (_run_l4, _run_l4_for_segment остаются в фасаде);
  - orchestration flow;
  - voting, priority rules, fallback;
  - прямого доступа к HybridClassifier через self.

Зависимости передаются через конструктор:
  - l1, l2, l3 — классификаторы уровней

Каждый метод:
  - принимает текущий state (candidates, details, ...);
  - возвращает обновлённый state;
  - не хранит промежуточный state между вызовами.
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class CascadeSteps:
    """
    Инкапсулирует шаги L1 / L2 / L3 каскада классификации.

    Принимает ссылки на классификаторы уровней через конструктор.
    Не хранит промежуточный state между вызовами методов.

    Все методы возвращают обновлённые (candidates, details, ...) —
    без скрытых побочных эффектов на других полях.
    """

    def __init__(self, l1: Any, l2: Any, l3: Any) -> None:
        self._l1 = l1
        self._l2 = l2
        self._l3 = l3

    # ──────────────────────────────────────────────────────────────────
    # L1
    # ──────────────────────────────────────────────────────────────────

    def run_l1(
        self,
        doc_id: str,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
    ) -> tuple[dict | None, list[dict], dict]:
        """
        L1: классификация по имени файла / пути к папке.

        Возвращает:
          (top_l1, candidates, details)

        Важно:
          - candidates изменяется in-place через extend;
          - details изменяется in-place;
          - top_l1 — первый результат или None.
        """
        l1_results = self._l1.classify(filename, folder)
        details["levels_tried"].append("L1")

        top_l1: dict | None = None
        if l1_results:
            top_l1 = l1_results[0]
            details["L1"] = {
                "type": top_l1["type_code"],
                "confidence": top_l1["confidence"],
                "method": top_l1["method"],
                "details": top_l1.get("details"),
                "note": "filename_hint",
            }
            candidates.extend(l1_results)
        else:
            details["L1"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "filename",
                "note": "no_patterns_matched",
            }

        logger.debug(
            "Hybrid L1 result",
            extra={
                "doc_id": doc_id,
                "filename": filename,
                "folder_path": folder,
                "top_type": top_l1["type_code"] if top_l1 else "UNKNOWN",
                "top_conf": top_l1["confidence"] if top_l1 else 0.0,
                "candidates_count": len(l1_results),
            },
        )

        return top_l1, candidates, details

    # ──────────────────────────────────────────────────────────────────
    # L2
    # ──────────────────────────────────────────────────────────────────

    async def run_l2(
        self,
        doc_id: str,
        header_text: str | None,
        snippet_text: str | None,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
    ) -> tuple[Any | None, list[dict], dict]:
        """
        L2: классификация по заголовку и YAML-паттернам.

        Возвращает:
          (top_l2, candidates, details)

        Важные детали реализации:
          - sq_in_conf: signal_quality уже учтён внутри confidence
            для формата extended_v1 — voter не должен применять его повторно;
          - exclusion_hits >= excl_hard: hard exclusion сбрасывает тип в UNKNOWN;
          - details["L2_top"] пишется только если doctype != UNKNOWN.
        """
        top_l2: Any | None = None

        if not header_text and not snippet_text:
            details["levels_tried"].append("L2")
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "header_pattern",
                "evidence": None,
                "note": "no_header_or_snippet_text",
            }

            logger.debug(
                "Hybrid L2 skipped",
                extra={
                    "doc_id": doc_id,
                    "reason": "no_header_or_snippet_text",
                },
            )

            return top_l2, candidates, details

        l2_result = await self._l2.classify(
            text=header_text or "",
            filename=filename,
            folder_path=folder,
            text_sanitized=None,
            metadata={
                "snippet_text": snippet_text or "",
            },
        )
        details["levels_tried"].append("L2")

        l2_extra = getattr(l2_result, "extra", {}) or {}
        has_exclusion_hit = bool(l2_extra.get("has_exclusion_hit"))
        exclusion_hits = int(l2_extra.get("exclusion_hits", 0))
        excl_hard = int(getattr(settings, "CLASSIFICATION_L2_EXCL_HARD", 2))

        if has_exclusion_hit and exclusion_hits >= excl_hard:
            details["L2"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "extra": l2_extra,
                "note": "l2_exclusion_hard_hit",
            }
        else:
            details["L2"] = {
                "type": l2_result.doctype,
                "confidence": l2_result.confidence,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "extra": l2_extra or None,
            }
            if l2_result.doctype != "UNKNOWN":
                top_l2 = l2_result
                # extended_v1: signal_quality уже учтён внутри confidence
                # (не применять повторно в voter)
                # legacy-format: signal_quality НЕ входит в confidence
                # (voter применяет как внешний множитель)
                sq_in_conf = l2_extra.get("format") == "extended_v1"
                candidates.append(
                    {
                        "type_code": l2_result.doctype,
                        "confidence": l2_result.confidence,
                        "level": "L2",
                        "method": l2_result.method,
                        "signal_quality": l2_extra.get("signal_quality", 1.0),
                        "signal_quality_in_confidence": sq_in_conf,
                        "negative_hits": int(
                            l2_extra.get("soft_exclusion_hits", 0)
                        ),  # legacy compatibility
                        "soft_negative_hits": int(
                            l2_extra.get("soft_exclusion_hits", 0)
                        ),
                        "hard_negative_hits": int(
                            l2_extra.get("hard_exclusion_hits", 0)
                        ),
                        "ambiguity_penalty": float(
                            l2_extra.get("ambiguity_penalty", 0.0)
                        ),
                        "input_quality": float(l2_extra.get("input_quality", 1.0)),
                    }
                )

                details["L2_top"] = {
                    "type": l2_result.doctype,
                    "confidence": float(l2_result.confidence),
                }

        logger.debug(
            "Hybrid L2 result",
            extra={
                "doc_id": doc_id,
                "type": l2_result.doctype,
                "confidence": l2_result.confidence,
                "method": l2_result.method,
                "evidence": l2_result.evidence,
                "has_exclusion_hit": has_exclusion_hit,
                "exclusion_hits": exclusion_hits,
            },
        )

        return top_l2, candidates, details

    # ──────────────────────────────────────────────────────────────────
    # L3
    # ──────────────────────────────────────────────────────────────────

    async def run_l3(
        self,
        doc_id: str,
        snippet_text: str | None,
        filename: str,
        folder: str,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        applicable_triggers: list[str],
    ) -> tuple[Any | None, list[dict], dict, str | None, str | None, list[str]]:
        """
        L3: семантическая классификация через эмбеддинги.

        Возвращает:
          (top_l3, candidates, details, language, jurisdiction, applicable_triggers)

        Важные детали реализации:
          - language и jurisdiction обновляются из l3_result;
          - applicable_triggers обновляются из l3_result;
          - details["input_quality"] берётся как min(текущий, l3_extra);
          - details["L3_top"] пишется только если doctype != UNKNOWN.
        """
        top_l3: Any | None = None

        if not snippet_text or not settings.RUNNER_EMBEDDINGS_ENABLED:
            details["levels_tried"].append("L3")
            note = (
                "empty_text"
                if not snippet_text
                else "embeddings_disabled_or_no_snippet"
            )
            details["L3"] = {
                "type": "UNKNOWN",
                "confidence": 0.0,
                "method": "embedding_similarity",
                "evidence": None,
                "note": note,
            }

            logger.debug(
                "Hybrid L3 skipped",
                extra={"doc_id": doc_id, "reason": note},
            )

            return (
                top_l3,
                candidates,
                details,
                language,
                jurisdiction,
                applicable_triggers,
            )

        l3_result = await self._l3.classify(
            text=snippet_text,
            filename=filename,
            folder_path=folder,
            text_sanitized=None,
            metadata=None,
        )
        details["levels_tried"].append("L3")

        language = getattr(l3_result, "language", "ru")
        jurisdiction = getattr(l3_result, "jurisdiction", "RU")
        if hasattr(l3_result, "applicable_triggers"):
            applicable_triggers = list(
                getattr(l3_result, "applicable_triggers") or []
            )

        l3_extra = getattr(l3_result, "extra", {}) or {}
        raw_sim = float(l3_extra.get("raw_similarity", 0.0))

        details["L3"] = {
            "type": l3_result.doctype,
            "confidence": l3_result.confidence,
            "method": l3_result.method,
            "evidence": l3_result.evidence,
            "language": language,
            "jurisdiction": jurisdiction,
            "alternative_types": getattr(l3_result, "alternative_types", []),
            "extra": l3_extra or None,
        }

        details["input_quality"] = min(
            float(details.get("input_quality", 1.0)),
            float(l3_extra.get("input_quality", 1.0)),
        )

        if l3_result.doctype != "UNKNOWN":
            top_l3 = l3_result
            candidates.append(
                {
                    "type_code": l3_result.doctype,
                    "confidence": l3_result.confidence,
                    "level": "L3",
                    "method": l3_result.method,
                    "language": language,
                    "jurisdiction": jurisdiction,
                    "raw_similarity": raw_sim,
                    "signal_quality": l3_extra.get(
                        "signal_quality", min(1.0, raw_sim + 0.15)
                    ),
                    "negative_hits": int(l3_extra.get("negative_hits", 0)),
                    "ambiguity_penalty": float(
                        l3_extra.get("ambiguity_penalty", 0.0)
                    ),
                    "input_quality": float(l3_extra.get("input_quality", 1.0)),
                    "margin": float(l3_extra.get("margin", 0.0)),
                }
            )
            details["L3_top"] = {
                "type": l3_result.doctype,
                "confidence": float(l3_result.confidence),
            }

        logger.debug(
            "Hybrid L3 result",
            extra={
                "doc_id": doc_id,
                "type": l3_result.doctype,
                "confidence": l3_result.confidence,
                "method": l3_result.method,
                "language": language,
                "jurisdiction": jurisdiction,
                "raw_similarity": raw_sim,
            },
        )

        return (
            top_l3,
            candidates,
            details,
            language,
            jurisdiction,
            applicable_triggers,
        )
    

