"""
ExtractionLLMDetector: LLM-based structured data extractor.

Назначение:
- На основе ExtractionConfig (список полей) и текстового контекста
  вызвать LLM с промптом "верни JSON с полями" и распарсить ответ.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from src.core.logging import get_logger
from src.engine.llm.client import LLMClient, LLMResponse
from src.engine.playbook.models import CheckDefinition, ExtractionConfig, ExtractionFieldConfig

logger = get_logger(__name__)


class ExtractionLLMDetector:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def extract(self, check: CheckDefinition, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Выполнить LLM-извлечение structured_data.

        Возвращает словарь вида:
          {
            "field_name": {"value": ..., "confidence": 0.0-1.0},
            ...
          }
        или пустой dict при ошибке/отсутствии данных.
        """
        extraction_cfg: ExtractionConfig | None = getattr(check, "extraction", None)
        if not extraction_cfg or not extraction_cfg.enabled:
            return {}

        if not self.client.is_available():
            logger.debug("LLM not available for extraction")
            return {}

        if not text.strip():
            return {}

        prompt = self._build_prompt(check, extraction_cfg, text)

        try:
            response: LLMResponse | None = self.client.call(
                prompt=prompt,
                temperature=None,  # можно завести отдельные настройки для extraction
                max_tokens=None,
            )
        except Exception as e:
            logger.warning("LLM extraction call failed", error=str(e))
            return {}

        if response is None or not response.text.strip():
            return {}

        return self._parse_response(response.text)

    def _build_prompt(
        self,
        check: CheckDefinition,
        extraction_cfg: ExtractionConfig,
        context_text: str,
    ) -> str:
        """
        Построить промпт для LLM по списку полей.

        Формат: описываем каждое поле (name, type, description, allowed_values, unit),
        даём текст и просим вернуть строго JSON.
        """
        # Описываем поля
        lines: list[str] = []
        lines.append(
            "You are a legal assistant. Extract the following fields from the contract fragment."
        )
        lines.append("")
        lines.append("Fields:")

        for field in extraction_cfg.fields:
            desc = field.description or ""
            type_name = field.type.name.lower()
            allowed = ""
            if field.allowed_values:
                allowed = f" Allowed values: {', '.join(map(str, field.allowed_values))}."
            unit = f" Unit: {field.unit}." if field.unit else ""
            lines.append(
                f"- {field.name}: type={type_name}. {desc}{allowed}{unit}"
            )

        lines.append("")
        lines.append("Text:")
        lines.append("---")
        lines.append(context_text)
        lines.append("---")
        lines.append("")
        lines.append(
            "Return ONLY valid JSON in this exact format:"
        )
        # Структура ожидаемого JSON
        # fields: field_name -> {value, confidence}
        lines.append(
            '{ "fields": { "field_name": { "value": <value or null>, "confidence": <0.0-1.0> } } }'
        )

        return "\n".join(lines)

    def _parse_response(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Распарсить JSON-ответ LLM.

        Ожидаем:
        {
          "fields": {
            "field_name": {
              "value": ...,
              "confidence": 0.0-1.0
            },
            ...
          }
        }
        """
        text = text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Попробуем вытащить JSON "изнутри" как в LLMClient._extract_json (можно переиспользовать идею)
            from src.engine.llm.client import _extract_json  # если не хочешь, можно скопировать
            candidate = _extract_json(text)
            if not candidate:
                logger.warning("Failed to parse LLM extraction JSON", raw=text[:500])
                return {}
            data = candidate

        if not isinstance(data, dict):
            return {}

        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for name, payload in fields.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("value")
            conf_raw = payload.get("confidence", 0.7)
            try:
                confidence = float(conf_raw)
            except (TypeError, ValueError):
                confidence = 0.7

            result[name] = {
                "value": value,
                "confidence": confidence,
            }

        return result
