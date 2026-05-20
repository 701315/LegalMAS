# src/classifiers/stage8/_l4_executor.py

"""
L4 execution: вызов LLM-fallback для документа и сегмента.

PR8: вынесен из hybrid_classifier.py.

Содержит:
  L4Executor — методы run_for_document, run_for_segment

Намеренно НЕ содержит:
  - orchestration каскада;
  - L1/L2/L3 шагов;
  - voting, priority rules, fallback;
  - прямого доступа к HybridClassifier через self.

Зависимости передаются через конструктор.
"""
from __future__ import annotations

import time
from typing import Any

from core.config import settings
from core.logging import get_logger

from ._decision_support import (
    build_llm_source_text,
    make_l4_error_details,
)
from ._l4_policy import (
    build_llm_allowed_types,
    should_run_l4,
)
from ._decision_logger import (
    DecisionStrategy,
    describe_l4_skip,
    log_classification_decision,
)

logger = get_logger(__name__)


class L4Executor:
    """
    Выполняет L4 LLM-fallback классификацию.

    Два режима:
      run_for_document  — использует header + snippet
      run_for_segment   — использует только текст сегмента

    Каждый метод возвращает:
      dict  — финальный результат классификации (L4 дал ответ)
      None  — L4 не запустился или не дал ответа (продолжаем fallback)
    """

    def __init__(
        self,
        *,
        llm: Any,
        builder: Any,
        metrics: Any,
        registry: Any,
        l4_enabled: bool,
        hybrid_accept: float,
    ) -> None:
        self._llm = llm
        self._builder = builder
        self._metrics = metrics
        self._registry = registry
        self._l4_enabled = l4_enabled
        self._hybrid_accept = hybrid_accept

    # ──────────────────────────────────────────────────────────────────
    # Document L4
    # ──────────────────────────────────────────────────────────────────

    async def run_for_document(
        self,
        *,
        doc_id: str,
        filename: str,
        folder: str,
        header_text: str | None,
        snippet_text: str | None,
        final_conf_after_voting: float,
        details: dict,
        candidates: list[dict],
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        L4: LLM-fallback для документа.
        Возвращает готовый dict-результат или None.
        """
        llm_source_text = build_llm_source_text(header_text, snippet_text)
        allowed_types, allowed_types_source = build_llm_allowed_types(
            self._registry,
            candidates,
            base_top_k=5,
            max_total=12,
        )
        details["L4_allowed_types_source"] = allowed_types_source
        voted_margin = float(details.get("voting_margin", 1.0))

        gate = should_run_l4(
            l4_enabled=self._l4_enabled,
            llm_available=self._llm.is_available(),
            hybrid_accept=self._hybrid_accept,
            is_segment=False,
            llm_source_text=llm_source_text,
            allowed_types=allowed_types,
            final_conf_after_voting=final_conf_after_voting,
            voted_margin=voted_margin,
            details=details,
        )

        if not (
            gate.l4_enabled
            and gate.llm_available
            and gate.has_source_and_types
            and gate.need_adjudication
            and not gate.skip_l4
        ):
            self._log_skip(
                entity_id=doc_id,
                entity_key="doc_id",
                gate=gate,
                final_conf_after_voting=final_conf_after_voting,
                voted_margin=voted_margin,
                allowed_types_source=allowed_types_source,
            )
            return None

        details["levels_tried"].append("L4")
        logger.debug(
            "Hybrid L4 call",
            extra={
                "doc_id": doc_id,
                "final_conf_after_voting": final_conf_after_voting,
                "pre_l4_best_signal": details.get("pre_l4_best_signal"),
                "voting_margin": voted_margin,
                "need_adjudication": gate.need_adjudication,
                "contradiction_detected": gate.contradiction_detected,
                "input_quality": gate.input_quality,
                "allowed_types_source": allowed_types_source,
                "allowed_types": allowed_types,
            },
        )

        parsed = self._call_and_parse(
            llm_source_text=llm_source_text,
            filename=filename,
            folder=folder,
            allowed_types=allowed_types,
            details=details,
            entity_id=doc_id,
            entity_key="doc_id",
        )
        if parsed is None:
            return None

        if parsed["type_code"] and parsed["type_code"] != "UNKNOWN":
            self._metrics.classification_duration.labels(source="l4").observe(
                time.time() - started_at
            )
            if settings.CLASSIFICATION_LOG_DECISIONS:
                log_classification_decision(
                    doc_id=doc_id,
                    decided_by=DecisionStrategy.L4_LLM,
                    final_type=parsed["type_code"],
                    final_confidence=parsed["confidence"],
                    levels_tried=details["levels_tried"],
                    started_at=started_at,
                    l4_triggered=True,
                    contradiction=details.get("contradiction_detected", False),
                    voting_score=(details.get("voting") or {}).get("score"),
                    single_source_cap_applied=(details.get("voting") or {}).get(
                        "single_source_cap_applied"
                    ),
                    extra={
                        "l4_parse_success": parsed["parse_success"],
                        "voting_margin": details.get("voting_margin"),
                    },
                )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=parsed["type_code"],
                final_confidence=parsed["confidence"],
                level="L4",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=self._builder.build_triggers(
                    doc_id, parsed["type_code"]
                ),
                details=details,
            )

        return None

    # ──────────────────────────────────────────────────────────────────
    # Segment L4
    # ──────────────────────────────────────────────────────────────────

    async def run_for_segment(
        self,
        *,
        segment_id: str,
        text: str,
        filename: str,
        folder: str,
        final_conf_after_voting: float,
        details: dict,
        candidates: list[dict],
        language: str | None,
        jurisdiction: str | None,
        applicable_triggers: list[str],
        started_at: float,
    ) -> dict | None:
        """
        L4: LLM-fallback для сегмента.

        Отличия от run_for_document:
        - не использует DocumentContentService и header/snippet;
        - работает только по тексту сегмента;
        - не строит triggers (они уже есть из L3).
        """
        llm_source_text = (text or "").strip()
        if not llm_source_text:
            return None

        allowed_types, allowed_types_source = build_llm_allowed_types(
            self._registry,
            candidates,
            base_top_k=5,
            max_total=12,
        )
        details["L4_allowed_types_source"] = allowed_types_source
        voted_margin = float(details.get("voting_margin", 1.0))

        gate = should_run_l4(
            l4_enabled=self._l4_enabled,
            llm_available=self._llm.is_available(),
            hybrid_accept=self._hybrid_accept,
            is_segment=True,
            llm_source_text=llm_source_text,
            allowed_types=allowed_types,
            final_conf_after_voting=final_conf_after_voting,
            voted_margin=voted_margin,
            details=details,
        )

        if not (
            gate.l4_enabled
            and gate.llm_available
            and gate.has_source_and_types
            and gate.need_adjudication
            and not gate.skip_l4
        ):
            self._log_skip(
                entity_id=segment_id,
                entity_key="segment_id",
                gate=gate,
                final_conf_after_voting=final_conf_after_voting,
                voted_margin=voted_margin,
                allowed_types_source=allowed_types_source,
            )
            return None

        details["levels_tried"].append("L4")
        logger.debug(
            "Hybrid segment L4 call",
            extra={
                "segment_id": segment_id,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "pre_l4_best_signal": details.get("pre_l4_best_signal"),
                "need_adjudication": gate.need_adjudication,
                "contradiction_detected": gate.contradiction_detected,
                "input_quality": gate.input_quality,
                "allowed_types_source": allowed_types_source,
                "allowed_types": allowed_types,
            },
        )

        parsed = self._call_and_parse(
            llm_source_text=llm_source_text,
            filename=filename,
            folder=folder,
            allowed_types=allowed_types,
            details=details,
            entity_id=segment_id,
            entity_key="segment_id",
        )
        if parsed is None:
            return None

        if parsed["type_code"] and parsed["type_code"] != "UNKNOWN":
            self._metrics.classification_duration.labels(
                source="segment_l4"
            ).observe(time.time() - started_at)
            if settings.CLASSIFICATION_LOG_DECISIONS:
                log_classification_decision(
                    doc_id=f"segment:{segment_id}",
                    decided_by=DecisionStrategy.L4_LLM,
                    final_type=parsed["type_code"],
                    final_confidence=parsed["confidence"],
                    levels_tried=details["levels_tried"],
                    started_at=started_at,
                    l4_triggered=True,
                    contradiction=details.get("contradiction_detected", False),
                    voting_score=(details.get("voting") or {}).get("score"),
                    single_source_cap_applied=(details.get("voting") or {}).get(
                        "single_source_cap_applied"
                    ),
                    extra={
                        "l4_parse_success": parsed["parse_success"],
                        "segment_id": segment_id,
                    },
                )
            return self._builder.build(
                levels_tried=details["levels_tried"],
                candidates=candidates,
                final_type=parsed["type_code"],
                final_confidence=parsed["confidence"],
                level="L4",
                language=language,
                jurisdiction=jurisdiction,
                applicable_triggers=applicable_triggers,
                details=details,
            )

        return None

    # ──────────────────────────────────────────────────────────────────
    # Общие внутренние методы
    # ──────────────────────────────────────────────────────────────────

    def _call_and_parse(
        self,
        *,
        llm_source_text: str,
        filename: str,
        folder: str,
        allowed_types: list[str],
        details: dict,
        entity_id: str,
        entity_key: str,
    ) -> dict | None:
        """
        Вызывает LLM, парсит ответ, пишет details["L4"].

        Возвращает parsed dict или None (если ошибка или нет ответа).

        entity_key — "doc_id" или "segment_id" (для логов).
        """
        try:
            llm_response, errordetails = self._llm.call(
                text=llm_source_text,
                filename=filename,
                folder_path=folder,
                allowed_types=allowed_types,
            )
        except Exception as e:
            logger.warning(
                "HybridClassifier: L4 LLM classification failed",
                extra={entity_key: entity_id, "error": str(e)},
            )
            details["L4"] = make_l4_error_details(e)
            return None

        if llm_response is None:
            return None

        parsed = self._llm.parse(llm_response, allowed_types=allowed_types)
        for key in ("llm_attempts", "error_type", "error_message"):
            if (val := errordetails.get(key)) is not None:
                parsed["raw"][key] = val

        details["L4"] = {
            "type": parsed["type_code"],
            "confidence": parsed["confidence"],
            "method": "llm",
            "reasoning": parsed["reasoning"],
            "parse_success": parsed["parse_success"],
            "raw": parsed["raw"],
        }
        logger.debug(
            "Hybrid L4 result",
            extra={
                entity_key: entity_id,
                "doctype": parsed["type_code"],
                "confidence": parsed["confidence"],
            },
        )
        return parsed

    def _log_skip(
        self,
        *,
        entity_id: str,
        entity_key: str,
        gate: Any,
        final_conf_after_voting: float,
        voted_margin: float,
        allowed_types_source: dict,
    ) -> None:
        """Логирует причину пропуска L4, если настройка включена."""
        if not settings.CLASSIFICATION_LOG_L4_SKIPS:
            return

        skip_reason = describe_l4_skip(
            l4_enabled=gate.l4_enabled,
            llm_available=gate.llm_available,
            has_source_and_types=gate.has_source_and_types,
            need_adjudication=gate.need_adjudication,
            strong_single=gate.strong_single_no_conflict,
        )
        logger.debug(
            "l4_skipped",
            extra={
                entity_key: entity_id,
                "reason": skip_reason,
                "need_adjudication": gate.need_adjudication,
                "strong_single": gate.strong_single_no_conflict,
                "strong_final": gate.strong_final,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "allowed_types_source": allowed_types_source,
                "input_quality": gate.input_quality,
            },
        )


