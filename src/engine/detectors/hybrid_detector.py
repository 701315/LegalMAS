# src/engine/detectors/hybrid_detector.py

"""
Hybrid detector: сначала rules, затем LLM при необходимости.

Назначение:
- Объединяет быстрый rules‑детектор и более дорогой LLM‑детектор.
- Сначала пытается решить задачу по правилам (keywords/regex).
- Если уверенность rules ниже порога или совпадений нет — подключает LLM.
- Возвращает единый DetectionResult‑подобный словарь, пригодный для записи
  в CheckResult и дальнейшей аналитики.

Главные принципы (важно для продакшн‑поведения):

1) Rules — первый, дешёвый и устойчивый слой.
   Если rules уверенно нашёл риск, LLM вообще не вызываем.

2) LLM — “усилитель”, но НЕ точка отказа.
   - Если LLM недоступен, даёт ошибку или неопределённый ответ,
     мы НЕ выбрасываем исключения наверх.
   - Вместо этого используем результат rules и помечаем в raw,
     что LLM не смог отработать (тип ошибки, количество попыток).

3) При наличии двух сигналов (rules и LLM) выбираем более уверенный,
   но сохраняем в raw обе confidence, чтобы можно было анализировать поведение.
"""

from typing import Any

from core.config import settings
from core.logging import get_logger
from .llm_detector import LLMDetector
from .models import RetrievedChunk
from .rules_detector import RulesDetector
from ..playbook.models import CheckDefinition

logger = get_logger(__name__)

# Порог уверенности rules, при котором LLM не вызывается.
RULES_CONFIDENCE_THRESHOLD = getattr(settings, "RULES_CONFIDENCE_THRESHOLD", 0.7)


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
        # --- 1. Rules-based detection ---
        rules_result = self.rules.detect(text, check.rules)
        rules_result["check_id"] = getattr(check, "id", None)
        rules_result.setdefault("raw", {})
        rules_result["method"] = "rules"

        # Ветка: rules уверенный, LLM не нужен
        if rules_result["found"] and rules_result["confidence"] >= RULES_CONFIDENCE_THRESHOLD:
            rules_result["raw"]["source"] = "rules_confident"
            return rules_result

        # --- 2. Проверяем, есть ли вообще LLM-конфигурация для этого check ---
        llm_config = getattr(check, "llm", None)
        if not llm_config:
            # LLM не настроен для этого check — возвращаем то, что дали правила.
            rules_result["raw"]["source"] = "rules_no_llm_config"
            return rules_result

        # Если в LLMConfig не задан ни inline-шаблон, ни файл промпта,
        # вызывать LLM бессмысленно — остаёмся на rules.
        has_inline_prompt = bool(getattr(llm_config, "prompt_template", "").strip())
        has_file_prompt = bool(getattr(llm_config, "prompt_file", None))

        if not (has_inline_prompt or has_file_prompt):
            rules_result["raw"]["source"] = "rules_no_llm_prompt"
            return rules_result

        # --- 3. Попытка вызвать LLM-детектор ---
        # Если уверенность классификации низкая — не подсказываем тип документа LLM'у,
        # чтобы не усиливать возможную ошибку классификатора.
        try:
            cls_conf = float(classification_confidence or 0.0)
        except (TypeError, ValueError):
            cls_conf = 0.0

        doc_type_for_llm = doc_type if cls_conf >= 0.70 else ""
        cls_conf_percent = f"{cls_conf:.0%}"

        extra_variables = {
            "condition_name": check.name,
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

        try:
            llm_detection = self.llm.detect_with_variables(
                config=llm_config,
                chunks=chunks,
                extra_variables=extra_variables,
            )
        except Exception as e:
            # На всякий случай: если внутри LLMDetector что-то пошло совсем не так,
            # мы не роняем весь check, а логируем и остаёмся на rules.
            logger.exception(
                "HybridDetector: unexpected error in LLMDetector.detect_with_variables",
                extra={
                    "check_id": getattr(check, "id", None),
                    "error": str(e),
                },
            )
            rules_result["raw"]["source"] = "rules_llm_exception"
            rules_result["raw"]["llm_error_type"] = "unexpected_exception"
            rules_result["raw"]["llm_error_message"] = str(e)
            return rules_result

        # Если LLMDetector вернул None — он считает, что LLM не может быть использован
        # (нет провайдера, промпта или других базовых условий).
        if llm_detection is None:
            rules_result["raw"]["source"] = "rules_llm_unavailable"
            return rules_result

        # --- 4. Приводим LLMDetectionResult к "плоскому" виду ---
        flat_llm = self._flatten_llm_result(llm_detection, check)
        flat_llm.setdefault("raw", {})
        flat_llm["method"] = "llm"

        # Перенесём служебную информацию из details LLM-детектора в raw.llm_details
        llm_details = getattr(llm_detection, "details", {}) or {}
        flat_llm["raw"].setdefault("llm_details", llm_details)

        # Если LLM сам по себе не нашёл ничего (found=False, confidence≈0)
        # и при этом есть ошибки в details, то это хороший сигнал, что
        # алгоритм должен оставаться на rules-результате.
        error_type = llm_details.get("error_type")
        if error_type:
            # LLM не смог отработать или отработал с ошибкой — не считаем это
            # позитивным сигналом, а лишь дополняем rules-информацию.
            rules_result["raw"]["source"] = "rules_llm_error"
            rules_result["raw"]["llm_error_type"] = error_type
            rules_result["raw"]["llm_error_message"] = llm_details.get("error_message")
            rules_result["raw"]["llm_attempts"] = llm_details.get("llm_attempts")
            return rules_result

        # --- 5. Объединение сигналов rules и LLM ---
        found_rules = bool(rules_result.get("found", False))
        conf_rules = float(rules_result.get("confidence", 0.0) or 0.0)
        found_llm = bool(flat_llm.get("found", False))
        conf_llm = float(flat_llm.get("confidence", 0.0) or 0.0)

        # Оба не нашли
        if not found_rules and not found_llm:
            flat_llm["raw"]["source"] = "both_not_found_llm_preferred"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm

        # Rules нашёл, LLM нет
        if found_rules and not found_llm:
            rules_result["raw"]["source"] = "rules_found_llm_not_found"
            rules_result["raw"]["llm_confidence"] = conf_llm
            return rules_result

        # LLM нашёл, rules нет
        if found_llm and not found_rules:
            flat_llm["raw"]["source"] = "llm_found_rules_not_found"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm

        # Оба нашли → сравниваем confidence
        if conf_llm >= conf_rules:
            flat_llm["raw"]["source"] = "llm_stronger"
            flat_llm["raw"]["rules_confidence"] = conf_rules
            return flat_llm
        else:
            rules_result["raw"]["source"] = "rules_stronger"
            rules_result["raw"]["llm_confidence"] = conf_llm
            return rules_result

    @staticmethod
    def _flatten_llm_result(llm_result, check: CheckDefinition) -> dict[str, Any]:
        """
        Привести результат LLMDetector (с evidence_chunks и details)
        к "плоскому" DetectionResult‑подобному словарю, совместимому с rules‑результатом.
        """
        found = bool(getattr(llm_result, "found", False))

        evidence_text = ""
        span = None
        location = None
        sources = None

        evidence_chunks = getattr(llm_result, "evidence_chunks", []) or []
        if evidence_chunks:
            ec = evidence_chunks[0]
            evidence_text = ec.text
            location = {
                "element_id": ec.element_id,
                "page": ec.page,
                "clause_uid": ec.clause_uid,
                "score": ec.score,
            }
            sources = [
                {
                    "element_id": ec.element_id,
                    "page": ec.page,
                    "clause_uid": ec.clause_uid,
                    "score": ec.score,
                }
            ]

        confidence = float(getattr(llm_result, "confidence", 0.0))
        details = getattr(llm_result, "details", {}) or {}
        reason = details.get("reason") or details.get("parse_success")

        return {
            "found": found,
            "evidence": evidence_text or "",
            "confidence": confidence,
            "method": "llm",  # может быть перезаписан выше
            "reason": str(reason) if reason is not None else None,
            "rule_name": None,
            "check_id": getattr(check, "id", None),
            "severity": None,
            "span": span,
            "location": location,
            "sources": sources,
            "raw": {
                "llm_details": details,
            },
        }