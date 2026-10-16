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

Соглашения:
  - skip_reason — единственный owner: _l4_policy.should_run_l4().
    Executor только читает gate.skip_reason и сериализует его.
    Никакого пересчёта или переопределения skip_reason здесь нет.
"""

from __future__ import annotations

import time
from typing import Any

from core.config import settings
from core.logging import get_logger

from ._decision_logger import (
    DecisionStrategy,
    log_classification_decision,
)
from ._decision_support import (
    build_llm_source_text,
    make_l4_error_details,
)
from ._l4_policy import (
    build_llm_allowed_types,
    should_run_l4,
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

    Инварианты:
      - final_conf_after_voting, передаваемый снаружи — это voted confidence
        (из apply_voting), а НЕ pre-L4 signal confidence.
        Шаг 1 (hybrid_classifier.py) гарантирует это.
      - skip_reason читается из gate, не пересчитывается здесь.
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
        body_text: str | None,
        final_conf_after_voting: float,
        details: dict,
        candidates: list[dict],
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        L4: LLM-fallback для документа.

        final_conf_after_voting — voted decision confidence (из apply_voting).
        Использует header + body как source text для LLM.
        Возвращает готовый dict-результат или None.
        """
        llm_source_text = build_llm_source_text(header_text, body_text)
        allowed_types, allowed_types_source = build_llm_allowed_types(
            self._registry,
            candidates,
            base_top_k=5,
            max_total=int(
                getattr(settings, "CLASSIFICATION_L4_MAX_ALLOWED_TYPES", 6)
            ),
            details=details,
        )
        details["L4_allowed_types_source"] = allowed_types_source

        voted_margin = self._safe_float(details.get("voting_margin", 0.0), 0.0)

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
        details["L4_gate"] = self._serialize_gate(gate)
        details["L4_gate"]["allowed_types_count"] = len(allowed_types or [])
        details["L4_gate"]["allowed_types"] = list(allowed_types or [])
        details["L4_gate"]["allowed_types_source"] = allowed_types_source

        if not self._should_execute_l4(gate):
            self._record_skip_details(
                details=details,
                gate=gate,
                final_conf_after_voting=final_conf_after_voting,
                voted_margin=voted_margin,
                allowed_types=allowed_types,
                allowed_types_source=allowed_types_source,
            )
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
        if isinstance(details.get("L4_gate"), dict):
            details["L4_gate"]["status"] = "executing"

        logger.debug(
            "Hybrid L4 call",
            extra={
                "doc_id": doc_id,
                "final_conf_after_voting": final_conf_after_voting,
                "pre_l4_best_signal": details.get("pre_l4_best_signal"),
                "voting_margin": voted_margin,
                "need_adjudication": gate.need_adjudication,
                "raw_need_adjudication": gate.raw_need_adjudication,
                "adjudication_reason": getattr(gate, "adjudication_reason", None),
                "review_preferred": getattr(gate, "review_preferred", False),
                "l4_useful": gate.l4_useful,
                "weak_input_for_l4": gate.weak_input_for_l4,
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
                        "adjudication_reason": (details.get("L4_gate") or {}).get(
                            "adjudication_reason"
                        ),
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
                applicable_triggers=self._builder.build_triggers(doc_id, parsed["type_code"]),
                details=details,
            )

        if isinstance(details.get("L4_gate"), dict):
            details["L4_gate"]["status"] = "completed_unknown"
            details["L4_gate"]["failure_reason"] = "parsed_unknown_type"

        return None

    # ──────────────────────────────────────────────────────────────────
    # Segment L4
    # ──────────────────────────────────────────────────────────────────

    async def run_for_segment(  # ← 4 пробела отступа, внутри класса
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

        final_conf_after_voting — voted decision confidence (из apply_voting).

        Отличия от run_for_document:
        - не использует DocumentContentService и header/snippet;
        - работает только по тексту сегмента;
        - не строит triggers (они уже есть из L3).

        Все skip-пути (включая пустой текст) идут через should_run_l4() —
        policy является единственным owner'ом gating semantics.
        """
        # llm_source_text может быть пустым — это нормально.
        # should_run_l4() увидит has_source_text=False и выставит
        # skip_reason="missing_source_text" через стандартный путь.
        # Никакого ручного gate здесь нет.
        llm_source_text = (text or "").strip()

        allowed_types, allowed_types_source = build_llm_allowed_types(
            self._registry,
            candidates,
            base_top_k=5,
            max_total=int(
                getattr(settings, "CLASSIFICATION_L4_MAX_ALLOWED_TYPES", 6)
            ),
            details=details,
        )
        details["L4_allowed_types_source"] = allowed_types_source

        voted_margin = self._safe_float(details.get("voting_margin", 0.0), 0.0)

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
        details["L4_gate"] = self._serialize_gate(gate)
        details["L4_gate"]["allowed_types_count"] = len(allowed_types or [])
        details["L4_gate"]["allowed_types"] = list(allowed_types or [])
        details["L4_gate"]["allowed_types_source"] = allowed_types_source

        if not self._should_execute_l4(gate):
            self._record_skip_details(
                details=details,
                gate=gate,
                final_conf_after_voting=final_conf_after_voting,
                voted_margin=voted_margin,
                allowed_types=allowed_types,
                allowed_types_source=allowed_types_source,
            )
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
        if isinstance(details.get("L4_gate"), dict):
            details["L4_gate"]["status"] = "executing"

        logger.debug(
            "Hybrid segment L4 call",
            extra={
                "segment_id": segment_id,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "pre_l4_best_signal": details.get("pre_l4_best_signal"),
                "need_adjudication": gate.need_adjudication,
                "raw_need_adjudication": gate.raw_need_adjudication,
                "adjudication_reason": getattr(gate, "adjudication_reason", None),
                "review_preferred": getattr(gate, "review_preferred", False),
                "l4_useful": gate.l4_useful,
                "weak_input_for_l4": gate.weak_input_for_l4,
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
            self._metrics.classification_duration.labels(source="segment_l4").observe(
                time.time() - started_at
            )
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
                        "adjudication_reason": (details.get("L4_gate") or {}).get(
                            "adjudication_reason"
                        ),
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

        if isinstance(details.get("L4_gate"), dict):
            details["L4_gate"]["status"] = "completed_unknown"
            details["L4_gate"]["failure_reason"] = "parsed_unknown_type"

        return None

    # ──────────────────────────────────────────────────────────────────
    # Общие внутренние методы
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _serialize_gate(gate: Any) -> dict:
        """
        Сериализует L4GateDecision в dict для details["L4_gate"].

        Все поля читаются через getattr с безопасным дефолтом —
        метод устойчив к частично заполненным объектам.
        """
        return {
            "l4_enabled": bool(getattr(gate, "l4_enabled", False)),
            "llm_available": bool(getattr(gate, "llm_available", False)),
            "has_source_and_types": bool(getattr(gate, "has_source_and_types", False)),
            "has_source_text": bool(getattr(gate, "has_source_text", False)),
            "has_allowed_types": bool(getattr(gate, "has_allowed_types", False)),
            "need_adjudication": bool(getattr(gate, "need_adjudication", False)),
            # raw_need_adjudication — сырая потребность до подавления strong-флагами.
            # Показывает: была ли потребность в adjudication до того как
            # strong_final / strong_single_no_conflict её заблокировали.
            "raw_need_adjudication": bool(getattr(gate, "raw_need_adjudication", False)),
            "skip_l4": bool(getattr(gate, "skip_l4", False)),
            "strong_single_no_conflict": bool(getattr(gate, "strong_single_no_conflict", False)),
            "strong_final": bool(getattr(gate, "strong_final", False)),
            "contradiction_detected": bool(getattr(gate, "contradiction_detected", False)),
            "input_quality": L4Executor._safe_float(getattr(gate, "input_quality", 0.0), 0.0),
            "domain_conflict": bool(getattr(gate, "domain_conflict", False)),
            "final_conf_after_voting": L4Executor._safe_float(
                getattr(gate, "final_conf_after_voting", 0.0), 0.0
            ),
            "voted_margin": L4Executor._safe_float(getattr(gate, "voted_margin", 0.0), 0.0),
            "weak_input_for_l4": bool(getattr(gate, "weak_input_for_l4", False)),
            "l4_useful": bool(getattr(gate, "l4_useful", True)),
            "review_preferred": bool(getattr(gate, "review_preferred", False)),
            "skip_reason": getattr(gate, "skip_reason", None),
            "adjudication_reason": getattr(gate, "adjudication_reason", None),
        }

    @staticmethod
    def _should_execute_l4(gate: Any) -> bool:
        return bool(
            gate.l4_enabled
            and gate.llm_available
            and gate.has_source_and_types
            and gate.need_adjudication
            and gate.l4_useful
            and not gate.skip_l4
            and not getattr(gate, "review_preferred", False)
        )

    def _record_skip_details(
        self,
        *,
        details: dict,
        gate: Any,
        final_conf_after_voting: float,
        voted_margin: float,
        allowed_types: list[str],
        allowed_types_source: dict,
    ) -> None:
        """
        Записывает детали пропуска L4 в details["L4_gate"].

        skip_reason читается из gate — policy является единственным
        owner'ом этого поля. Здесь нет никакого пересчёта или
        переопределения skip_reason.
        """
        skip_reason = getattr(gate, "skip_reason", None)

        details["L4_gate"] = {
            **self._serialize_gate(gate),
            "status": "skipped",
            "skip_reason": skip_reason,
            "allowed_types_count": len(allowed_types or []),
            "allowed_types": list(allowed_types or []),
            "allowed_types_source": allowed_types_source,
            "final_conf_after_voting": final_conf_after_voting,
            "voted_margin": voted_margin,
        }

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
            if isinstance(details.get("L4_gate"), dict):
                details["L4_gate"]["status"] = "failed"
                details["L4_gate"]["failure_reason"] = "llm_call_exception"
            return None

        if llm_response is None:
            # Прокидываем реальную причину из errordetails, если она есть.
            # Молчаливая замена на "llm_returned_none" маскировала баги
            # конфигурации (инцидент run_id=545411d1-...: реальный
            # failure_reason=prompt_exceeds_token_budget превращался
            # в llm_returned_none и уводил диагностику в сторону Ollama).
            real_reason = (
                (errordetails or {}).get("failure_reason")
                if isinstance(errordetails, dict)
                else None
            ) or "llm_returned_none"
            if isinstance(details.get("L4_gate"), dict):
                details["L4_gate"]["status"] = "no_result"
                details["L4_gate"]["failure_reason"] = real_reason
                if isinstance(errordetails, dict) and errordetails:
                    details["L4_gate"]["error_details"] = errordetails
            return None

        parsed = self._llm.parse(llm_response, allowed_types=allowed_types)
        raw_payload = parsed.get("raw") if isinstance(parsed.get("raw"), dict) else {}
        parsed["raw"] = raw_payload

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
        if isinstance(details.get("L4_gate"), dict):
            details["L4_gate"]["status"] = "completed"
            details["L4_gate"]["parse_success"] = bool(parsed.get("parse_success", False))
            details["L4_gate"]["resolved_type"] = parsed.get("type_code")

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
        """
        Логирует причину пропуска L4.

        skip_reason читается напрямую из gate — policy является
        единственным owner'ом этого поля. Никакого пересчёта здесь нет.
        """
        if not settings.CLASSIFICATION_LOG_L4_SKIPS:
            return

        skip_reason = getattr(gate, "skip_reason", None)

        logger.debug(
            "l4_skipped",
            extra={
                entity_key: entity_id,
                "reason": skip_reason,
                "need_adjudication": gate.need_adjudication,
                "raw_need_adjudication": getattr(gate, "raw_need_adjudication", None),
                "adjudication_reason": getattr(gate, "adjudication_reason", None),
                "review_preferred": getattr(gate, "review_preferred", False),
                "l4_useful": gate.l4_useful,
                "weak_input_for_l4": gate.weak_input_for_l4,
                "strong_single": gate.strong_single_no_conflict,
                "strong_final": gate.strong_final,
                "final_conf_after_voting": final_conf_after_voting,
                "voting_margin": voted_margin,
                "allowed_types_source": allowed_types_source,
                "input_quality": gate.input_quality,
            },
        )
