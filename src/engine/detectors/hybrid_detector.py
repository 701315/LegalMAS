# src/engine/detectors/hybrid_detector.py

"""
Hybrid detector: сначала rules, затем LLM только если rules дали unclear.

Назначение:
- Объединяет быстрый rules‑детектор и более дорогой LLM‑детектор.
- Сначала пытается решить задачу по правилам (keywords/regex).
- LLM вызывается только если rules не дали достаточно определённого ответа.
- Возвращает единый DetectionResult‑подобный словарь, пригодный для записи
  в CheckResult и дальнейшей аналитики.

Принцип работы:
1. Rules всегда запускаются первыми.
2. Если rules дали уверенный positive — возвращаем rules без LLM.
3. Если rules дали "clean negative" (ничего не найдено) — по умолчанию
   тоже возвращаем rules без LLM, чтобы не гонять дорогой LLM без нужды.
4. Если rules дали слабый/неоднозначный сигнал (unclear) — подключаем LLM.
5. Если LLM недоступен или завершился с ошибкой — остаёмся на rules-результате,
   но сохраняем диагностику в raw.

Важно:
- Этот класс не ломает существующую архитектуру:
  - input/output контракты сохранены;
  - RulesDetector и LLMDetector используются как раньше;
  - CheckExecutor по-прежнему может опираться на единый "плоский" результат.
"""

from typing import Any

from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from engine.llm.client import LLMContextLimitError

from ..playbook.models import CheckDefinition
from .llm_detector import LLMDetector
from .models import EvidenceChunk, RetrievedChunk
from .rules_detector import RulesDetector

logger = get_logger(__name__)


RULES_CONFIDENCE_THRESHOLD = settings.RULES_CONFIDENCE_THRESHOLD

RUN_LLM_ON_RULES_CLEAN_NEGATIVE = bool(getattr(settings, "RUN_LLM_ON_RULES_CLEAN_NEGATIVE", False))


class HybridDetector:
    """
    HybridDetector объединяет два источника сигнала:
    - rules: дешёвые и интерпретируемые правила (keywords/regex);
    - llm: сложные проверки по LLM, описанные в LLMConfig внутри CheckDefinition.

    На вход получает:
    - text: текст для rules‑детектора (обычно склеенный контекст чанков);
    - chunks: список RetrievedChunk для LLM‑контекста;
    - check: CheckDefinition из playbook;
    - doc_type: строковый тип документа (для подсказки LLM);
    - classification_confidence: уверенность классификатора по doc_type.

    На выход отдаёт единый DetectionResult‑подобный словарь:
    {
        "found": bool,
        "evidence": str | None,
        "confidence": float,
        "method": "rules" | "llm" | "hybrid",
        "reason": str | None,
        "rule_name": str | None,
        "check_id": str | None,
        "severity": str | None,
        "span": dict | None,
        "location": dict | None,
        "sources": list | None,
        "raw": dict | None,
    }
    """

    def __init__(self, llm_client) -> None:
        self.rules = RulesDetector()
        self.llm = LLMDetector(llm_client)

    def run(
        self,
        text: str,
        chunks: list[RetrievedChunk],
        check: CheckDefinition,
        doc_type: str = "",
        classification_confidence: float = 1.0,
    ) -> dict[str, Any]:
        """
        Запустить гибридную детекцию для одного check.

        Важно:
        - Этот метод НЕ бросает исключения наружу из-за LLM.
        - В худшем случае он возвращает "rules-only" результат
          с пояснением в raw, почему LLM не использовался или не сработал.
        """

        logger.debug(
            "HybridDetector.run: chunks summary",
            extra={
                "check_id": getattr(check, "id", None),
                "chunks_count": len(chunks),
                "first_chunk_page": chunks[0].page if chunks else None,
                "first_chunk_clause_uid": chunks[0].clause_uid if chunks else None,
                "first_chunk_element_id": chunks[0].element_id if chunks else None,
            },
        )

        # --- 1. Rules-based detection ---
        rules_result = self.rules.detect(text, check.rules)
        rules_result["check_id"] = getattr(check, "id", None)
        rules_result.setdefault("raw", {})
        rules_result["method"] = "rules"
        rules_result.setdefault("location", None)
        rules_result.setdefault("sources", None)

        rules_result["raw"]["llm_invoked"] = False
        rules_result["raw"]["rules_threshold"] = RULES_CONFIDENCE_THRESHOLD

        if rules_result.get("found"):
            best_chunk = self._select_best_chunk(chunks)
            if best_chunk is not None:
                location, sources = self._build_location_from_chunk(best_chunk)
                rules_result["location"] = location
                rules_result["sources"] = sources

        # --- 2. Решаем, нужен ли LLM после rules ---
        need_llm, decision_reason = self._should_run_llm(rules_result, check)
        rules_result["raw"]["rules_llm_decision"] = decision_reason

        logger.info(
            "HybridDetector: rules-to-llm decision",
            extra={
                "check_id": getattr(check, "id", None),
                "need_llm": need_llm,
                "decision_reason": decision_reason,
                "rules_found": bool(rules_result.get("found", False)),
                "rules_confidence": float(rules_result.get("confidence", 0.0) or 0.0),
                "rules_reason": rules_result.get("reason"),
            },
        )

        if not need_llm:
            rules_result["raw"]["source"] = decision_reason
            return rules_result

        # --- 3. Проверяем, есть ли вообще LLM-конфигурация для этого check ---
        llm_config = getattr(check, "llm", None)
        if not llm_config:
            rules_result["raw"]["source"] = "rules_unclear_no_llm_config"
            return rules_result

        has_inline_prompt = bool(getattr(llm_config, "prompt_template", "").strip())
        has_file_prompt = bool(getattr(llm_config, "prompt_file", None))

        if not (has_inline_prompt or has_file_prompt):
            rules_result["raw"]["source"] = "rules_unclear_no_llm_prompt"
            return rules_result

        # --- 4. Готовим дополнительные переменные для LLM ---
        try:
            cls_conf = float(classification_confidence or 0.0)
        except (TypeError, ValueError):
            cls_conf = 0.0

        doc_type_for_llm = doc_type if cls_conf >= RULES_CONFIDENCE_THRESHOLD else ""
        cls_conf_percent = f"{cls_conf:.0%}"

        extra_variables = {
            "condition_name": check.name,
            "legal_base": check.description or "",
            "check_id": check.id,
            "check_description": check.description,
            "severity": check.severity,
            "severity_if_fail": check.severity_if_fail or "",
            "severity_if_pass": check.severity_if_pass or "",
            "severity_if_unclear": check.severity_if_unclear or "",
            "doc_types": ", ".join(check.doc_types or []),
            "current_doc_type": doc_type_for_llm,
            "classification_confidence": cls_conf_percent,
        }

        # --- 5. Попытка вызвать LLM-детектор ---
        try:
            rules_result["raw"]["llm_invoked"] = True
            llm_detection = self.llm.detect_with_variables(
                config=llm_config,
                chunks=chunks,
                extra_variables=extra_variables,
            )

        except LLMContextLimitError as e:
            # ── Промпт превысил контекстное окно модели ─────────────────────
            # Этот случай отличается от generic PermanentError: мы знаем точно,
            # что проблема в размере промпта, а не в логике или конфигурации.
            # build_user_explanation() увидит llm_error_type="context_limit"
            # и выставит user_status="manual_review_required".
            logger.warning(
                "HybridDetector: LLM context limit exceeded, staying on rules result",
                extra={
                    "check_id": getattr(check, "id", None),
                    "error": str(e),
                },
            )
            rules_result["raw"]["source"] = "rules_unclear_llm_context_limit"
            rules_result["raw"]["llm_error_type"] = "context_limit"
            rules_result["raw"]["llm_error_message"] = str(e)
            return rules_result

        except PermanentError as e:
            # На практике сюда обычно уже не попадаем, потому что LLMDetector
            # сам превращает ошибки в DetectionResult(details=...),
            # но оставляем защиту на случай регрессий.
            logger.warning(
                "HybridDetector: permanent LLM error, staying on rules result",
                extra={
                    "check_id": getattr(check, "id", None),
                    "error": str(e),
                },
            )
            rules_result["raw"]["source"] = "rules_unclear_llm_permanent_error"
            rules_result["raw"]["llm_error_type"] = "permanent_error"
            rules_result["raw"]["llm_error_message"] = str(e)
            return rules_result

        except TransientError as e:
            logger.warning(
                "HybridDetector: transient LLM error, staying on rules result",
                extra={
                    "check_id": getattr(check, "id", None),
                    "error": str(e),
                },
            )
            rules_result["raw"]["source"] = "rules_unclear_llm_transient_error"
            rules_result["raw"]["llm_error_type"] = "transient_error"
            rules_result["raw"]["llm_error_message"] = str(e)
            return rules_result

        except Exception as e:
            logger.exception(
                "HybridDetector: unexpected error in LLMDetector.detect_with_variables",
                extra={
                    "check_id": getattr(check, "id", None),
                    "error": str(e),
                },
            )
            rules_result["raw"]["source"] = "rules_unclear_llm_exception"
            rules_result["raw"]["llm_error_type"] = "unexpected_exception"
            rules_result["raw"]["llm_error_message"] = str(e)
            return rules_result

        if llm_detection is None:
            rules_result["raw"]["source"] = "rules_unclear_llm_unavailable"
            return rules_result

        # --- 6. Приводим LLM DetectionResult к "плоскому" виду ---
        flat_llm = self._flatten_llm_result(
            llm_result=llm_detection,
            check=check,
            fallback_chunks=chunks,
        )
        flat_llm.setdefault("raw", {})
        flat_llm["method"] = "llm"

        llm_details = getattr(llm_detection, "details", {}) or {}
        flat_llm["raw"].setdefault("llm_details", llm_details)
        flat_llm["raw"]["llm_invoked"] = True
        flat_llm["raw"]["rules_llm_decision"] = decision_reason
        flat_llm["raw"]["rules_confidence_threshold"] = RULES_CONFIDENCE_THRESHOLD

        # Если LLM отработал с ошибкой/деградацией — остаёмся на rules.
        # error_type="context_limit" тоже сюда попадёт через llm_details,
        # если LLMDetector поглотил LLMContextLimitError внутри call_with_retries().
        error_type = llm_details.get("error_type")
        if error_type:
            rules_result["raw"]["source"] = "rules_unclear_llm_error"
            rules_result["raw"]["llm_error_type"] = error_type
            rules_result["raw"]["llm_error_message"] = llm_details.get("error_message")
            rules_result["raw"]["llm_attempts"] = llm_details.get("llm_attempts")
            rules_result["raw"]["llm_reason"] = llm_details.get("reason")
            return rules_result

        # --- 7. Объединение сигналов rules и LLM ---
        found_rules = bool(rules_result.get("found", False))
        conf_rules = float(rules_result.get("confidence", 0.0) or 0.0)
        found_llm = bool(flat_llm.get("found", False))
        conf_llm = float(flat_llm.get("confidence", 0.0) or 0.0)

        if not found_rules and not found_llm:
            flat_llm["raw"]["source"] = "both_not_found_llm_preferred"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm

        if found_rules and not found_llm:
            rules_result["raw"]["source"] = "rules_found_llm_not_found"
            rules_result["raw"]["llm_confidence"] = conf_llm
            return rules_result

        if found_llm and not found_rules:
            flat_llm["raw"]["source"] = "llm_found_rules_not_found"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm

        if conf_llm >= conf_rules:
            flat_llm["raw"]["source"] = "llm_stronger"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm

        rules_result["raw"]["source"] = "rules_stronger"
        rules_result["raw"]["llm_confidence"] = conf_llm
        return rules_result

    def _should_run_llm(
        self,
        rules_result: dict[str, Any],
        check: CheckDefinition,
    ) -> tuple[bool, str]:
        """
        Решить, вызывать ли LLM после rules.

        Возвращает:
        - need_llm: bool
        - decision_reason: str

        Политика по умолчанию:
        - confident positive rules  -> LLM не нужен;
        - clean negative rules      -> LLM не нужен (для экономии ресурсов);
        - всё остальное             -> unclear, вызываем LLM.
        """
        found_rules = bool(rules_result.get("found", False))
        conf_rules = float(rules_result.get("confidence", 0.0) or 0.0)
        reason_rules = str(rules_result.get("reason") or "")

        if found_rules and conf_rules >= RULES_CONFIDENCE_THRESHOLD:
            return False, "rules_confident_positive"

        if (
            not found_rules
            and reason_rules == "no_keywords_or_patterns_matched"
            and not RUN_LLM_ON_RULES_CLEAN_NEGATIVE
        ):
            return False, "rules_clean_negative"

        if not found_rules and reason_rules == "negative_keywords_matched":
            return True, "rules_negative_suppressed_unclear"

        if found_rules and conf_rules < RULES_CONFIDENCE_THRESHOLD:
            return True, "rules_weak_positive_unclear"

        return True, "rules_unclear"

    @staticmethod
    def _select_best_chunk(chunks: list[RetrievedChunk]) -> RetrievedChunk | None:
        """
        Выбрать лучший чанк для привязки location:
        - по максимальному combined_score;
        - если скор не задан или список пуст — вернуть None.
        """
        if not chunks:
            return None

        best = chunks[0]
        best_score = float(getattr(best, "combined_score", 0.0) or 0.0)

        for ch in chunks[1:]:
            score = float(getattr(ch, "combined_score", 0.0) or 0.0)
            if score > best_score:
                best = ch
                best_score = score

        return best

    @staticmethod
    def _build_location_from_chunk(
        chunk: RetrievedChunk,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Построить location и sources из одного RetrievedChunk.
        Используется для rules-результатов, чтобы привязать риск к клаузе.
        """
        base: dict[str, Any] = {
            "element_id": getattr(chunk, "element_id", None),
            "page": getattr(chunk, "page", None),
            "clause_uid": getattr(chunk, "clause_uid", None),
            "bbox": getattr(chunk, "bbox", None) or None,
            "score": float(getattr(chunk, "combined_score", 0.0) or 0.0),
        }

        base["path_titles"] = getattr(chunk, "path_titles", None) or None
        base["start_page"] = getattr(chunk, "start_page", None)
        base["end_page"] = getattr(chunk, "end_page", None)
        base["element_ids"] = getattr(chunk, "element_ids", None) or None

        location = dict(base)
        sources = [dict(base)]
        return location, sources

    @staticmethod
    def _flatten_llm_result(
        llm_result,
        check: CheckDefinition,
        fallback_chunks: list[RetrievedChunk] | None = None,
    ) -> dict[str, Any]:
        """
        Привести результат LLMDetector (с evidence_chunks и details)
        к "плоскому" DetectionResult‑подобному словарю, совместимому с rules‑результатом.

        Использует поля EvidenceChunk, включая структурный контекст
        (path_titles, start_page, end_page, element_ids), если они есть.
        """
        found = bool(getattr(llm_result, "found", False))

        evidence_text = ""
        span = None
        location: dict[str, Any] | None = None
        sources: list[dict[str, Any]] | None = None

        evidence_chunks = getattr(llm_result, "evidence_chunks", []) or []
        if evidence_chunks:
            ec: EvidenceChunk = evidence_chunks[0]
            evidence_text = ec.text or ""

            base = {
                "element_id": ec.element_id,
                "page": ec.page,
                "clause_uid": ec.clause_uid,
                "score": ec.score,
                "bbox": ec.bbox or None,
            }

            base["section_path"] = ec.path_titles or None
            base["start_page"] = ec.start_page
            base["end_page"] = ec.end_page
            base["element_ids"] = ec.element_ids or None

            location = dict(base)
            sources = [dict(base)]

        elif fallback_chunks:
            best_chunk = HybridDetector._select_best_chunk(fallback_chunks)
            if best_chunk is not None:
                loc, srcs = HybridDetector._build_location_from_chunk(best_chunk)
                location = loc
                sources = srcs

        confidence = float(getattr(llm_result, "confidence", 0.0) or 0.0)
        details = getattr(llm_result, "details", {}) or {}
        reason = details.get("reason") or details.get("parse_success")

        try:
            logger.debug(
                "HybridDetector._flatten_llm_result",
                extra={
                    "check_id": getattr(check, "id", None),
                    "found": found,
                    "confidence": confidence,
                    "has_location": location is not None,
                    "location_page": location.get("page") if location else None,
                    "location_clause_uid": location.get("clause_uid") if location else None,
                    "location_element_id": location.get("element_id") if location else None,
                    "location_start_page": location.get("start_page") if location else None,
                    "location_end_page": location.get("end_page") if location else None,
                },
            )
        except Exception:
            logger.debug("HybridDetector._flatten_llm_result: debug logging failed")

        return {
            "found": found,
            "evidence": evidence_text or "",
            "confidence": confidence,
            "method": "llm",
            "reason": str(reason) if reason is not None else None,
            "rule_name": None,
            "check_id": getattr(check, "id", None),
            "severity": None,
            "span": span,
            "location": location,
            "sources": sources,
            "raw": {
                "llm_details": details,
                "llm_error_type": details.get("error_type"),
            },
        }
