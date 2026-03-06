"""
Hybrid detector: сначала rules, затем LLM при необходимости.

Назначение:
- Объединяет быстрый rules‑детектор и более дорогой LLM‑детектор.
- Сначала пытается решить задачу по правилам (keywords/regex).
- Если уверенность rules ниже порога или совпадений нет — подключает LLM.
- Возвращает единый DetectionResult‑подобный словарь, пригодный для записи
  в CheckResult и дальнейшей аналитики.

Поведение:
- Если rules дал достаточную уверенность → возвращаем его результат, LLM не зовём.
- Если rules слабый или ничего не нашёл, а LLM включён в CheckDefinition → вызываем LLM.
- При конфликте (оба дали found=True, но разную уверенность) побеждает результат
  с большей confidence. В raw можно хранить обе уверенности для анализа.
"""

from typing import Any

from core.config import settings
from .llm_detector import LLMDetector
from .models import RetrievedChunk
from .rules_detector import RulesDetector
from ..playbook.models import CheckDefinition

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
    - check: CheckDefinition из playbook.

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
    ) -> dict[str, Any]:
        """
        Запустить гибридную детекцию для одного check.

        Args:
            text: текст, по которому будут работать rules (обычно join контекстных чанков).
            chunks: чанки из RetrievalEngine (для LLM‑контекста).
            check: определение проверки из playbook (rules + llm‑часть).

        Returns:
            DetectionResult‑подобный словарь (см. описание класса).
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

        # --- 2. LLM fallback (если включён в check) ---
        llm_config = getattr(check, "llm", None)
        if not llm_config:
            # LLM не настроен для этого check — возвращаем то, что дали правила
            rules_result["raw"]["source"] = "rules_no_llm_config"
            return rules_result

        # Если в LLMConfig не задан ни inline-шаблон, ни файл промпта,
        # вызывать LLM бессмысленно — остаёмся на rules.
        has_inline_prompt = bool(getattr(llm_config, "prompt_template", "").strip())
        has_file_prompt = bool(getattr(llm_config, "prompt_file", None))

        if not (has_inline_prompt or has_file_prompt):
            rules_result["raw"]["source"] = "rules_no_llm_prompt"
            return rules_result

        # Вызов LLM; если он не сможет отработать, detect_with_variables вернёт None

        extra_variables = {
            "condition_name": check.name,
            "check_id": check.id,
            "check_description": check.description,
            "severity": check.severity,
            "severity_if_fail": check.severity_if_fail or "",
            "severity_if_pass": check.severity_if_pass or "",
            "severity_if_unclear": check.severity_if_unclear or "",
            "doc_types": ", ".join(check.doc_types or []),
        }

        llm_result = self.llm.detect_with_variables(
            config=llm_config,
            chunks=chunks,
            extra_variables=extra_variables,
        )

        if llm_result is None:
            # LLM не смог отработать — опираемся только на rules
            rules_result["raw"]["source"] = "rules_llm_unavailable"
            return rules_result

        # --- 3. Приводим LLMResult к "плоскому" DetectionResult ---
        flat_llm = self._flatten_llm_result(llm_result, check)
        flat_llm.setdefault("raw", {})
        flat_llm["method"] = "llm"

        # --- 4. Объединение: выбираем более уверенный сигнал ---
        found_rules = bool(rules_result.get("found", False))
        conf_rules = float(rules_result.get("confidence", 0.0) or 0.0)
        found_llm = bool(flat_llm.get("found", False))
        conf_llm = float(flat_llm.get("confidence", 0.0) or 0.0)

        # Оба не нашли
        if not found_rules and not found_llm:
            flat_llm["raw"]["source"] = "both_not_found_llm_preferred"
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
