# src/classifiers/stage8/_l4_llm.py
"""
L4-fallback: вызов LLM для классификации документа и парсинг ответа.

Изолируем от HybridClassifier по двум причинам:
  1) Логика промпта и парсинга меняется независимо от оркестрации.
  2) Класс можно протестировать без поднятия всего пайплайна.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..yaml_registry import YAMLRegistry
from engine.llm.client import LLMClient, LLMResponse
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class L4LLMClassifier:
    """
    Отвечает за два шага L4:
      1. _build_prompt + call_with_retries → LLMResponse
      2. parse → {type_code, confidence, reasoning, parse_success, raw}
    """

    def __init__(self, llm_client: LLMClient, registry: YAMLRegistry) -> None:
        self.llm_client = llm_client
        self.registry = registry

    def is_available(self) -> bool:
        return self.llm_client.is_available()

    def call(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызывает LLM для задачи классификации документа.

        Возвращает:
          (LLMResponse | None, errordetails: dict)
        """
        prompt = self._build_prompt(
            text=text,
            filename=filename,
            folder_path=folder_path,
            allowed_types=allowed_types,
        )
        response, errordetails = self.llm_client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        return response, errordetails

    def parse(
        self,
        response: LLMResponse,
        *,
        allowed_types: List[str],
    ) -> Dict[str, Any]:
        """
        Аккуратно разобрать JSON из ответа LLM и привести к безопасным значениям.

        Контракт возврата:
          {type_code, confidence, reasoning, parse_success, raw}
        """
        text = (response.text or "").strip()
        allowed_set = set(allowed_types or [])

        raw: Dict[str, Any] = {
            "provider": getattr(response, "provider", None),
            "model": getattr(response, "model", None),
            "tokens_used": getattr(response, "tokens_used", None),
            "parse_success": False,
            "error_type": None,
            "error_message": None,
            "response_text": text,
            "parsed_json": None,
        }

        type_code = "UNKNOWN"
        confidence = 0.0
        reasoning = ""
        parse_success = False

        try:
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx == -1 or end_idx <= start_idx:
                raise ValueError("No JSON object found in LLM response")

            obj = json.loads(text[start_idx:end_idx])
            if not isinstance(obj, dict):
                raise ValueError("LLM response JSON is not an object")

            raw["parsed_json"] = obj

            # --- type_code ---
            raw_type = obj.get("type_code") or obj.get("doctype")
            raw_type = raw_type.strip() if isinstance(raw_type, str) else ""

            if raw_type.upper() == "UNKNOWN":
                raw_type = ""

            type_code = raw_type if (raw_type and raw_type in allowed_set) else "UNKNOWN"

            # --- confidence ---
            try:
                confidence = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
            except (TypeError, ValueError):
                confidence = 0.0

            # --- reasoning ---
            reasoning_val = obj.get("reasoning", "")
            reasoning = reasoning_val if isinstance(reasoning_val, str) else str(reasoning_val)

            parse_success = True
            raw["parse_success"] = True

        except Exception as e:
            raw.update({
                "error_type": "parse_error",
                "error_message": str(e),
                "parse_success": False,
            })
            type_code, confidence, reasoning = "UNKNOWN", 0.0, ""

        return {
            "type_code": type_code,
            "confidence": confidence,
            "reasoning": reasoning,
            "parse_success": parse_success,
            "raw": raw,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> str:
        rows = [
            f"- {tc}: {(self.registry.get_config(tc).name if self.registry.get_config(tc) else '')}"
            for tc in allowed_types
        ]
        types_block = "\n".join(rows)

        instruction = (
            "Ты — классификатор юридических документов.\n"
            "Твоя задача — выбрать наиболее подходящий код типа документа из разрешённого списка.\n\n"
            f"Разрешённые типы документов (type_code: человекочитаемое название):\n{types_block}\n\n"
            "Инструкция:\n"
            "1) Внимательно прочитай имя файла, путь к папке и начало текста документа.\n"
            "2) Выбери РОВНО ОДИН type_code из списка выше, который лучше всего описывает документ.\n"
            "3) Если ни один тип не подходит, верни значение null или строку \"UNKNOWN\" в поле type_code.\n"
            "4) Ответ ДОЛЖЕН быть строго в формате JSON:\n"
            "{\"type_code\": \"...\", \"confidence\": 0.0, \"reasoning\": \"...\"}\n\n"
            "Не добавляй никакого текста до или после JSON.\n"
        )

        return (
            f"{instruction}"
            f"Имя файла: {filename}\n"
            f"Путь к папке: {folder_path}\n\n"
            f"Начало текста документа:\n{text}\n"
        )
    
    