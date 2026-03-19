# src/engine/detectors/extraction_llm_detector.py

"""
ExtractionLLMDetector: LLM-based structured data extractor.

Назначение:
- На основе ExtractionConfig (список полей) и текстового контекста
  вызвать LLM с промптом "верни JSON с полями" и распарсить ответ.
"""

from __future__ import annotations

import json
from typing import Any

from core.logging import get_logger

from ..llm.client import _extract_json
from ..llm.client import LLMClient, LLMResponse
from ..playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

logger = get_logger(__name__)


class ExtractionLLMDetector:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def extract(self, check: CheckDefinition, text: str) -> dict[str, dict[str, Any]]:
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
                temperature=0.0,  # детерминированное извлечение
                max_tokens=None,
            )
        except Exception as e:
            logger.warning("LLM extraction call failed", error=str(e))
            return {}

        if response is None or not response.text.strip():
            return {}

        # 1) парсим JSON в "сырую" структуру
        raw_fields = self._parse_response(response.text)
        if not raw_fields:
            return {}

        # 2) нормализуем значения по схеме extraction_cfg
        normalized = self._normalize_fields(raw_fields, extraction_cfg)
        return normalized

    # -------------------------------------------------------------------------
    # PROMPT GENERATION
    # -------------------------------------------------------------------------

    def _build_prompt(
        self,
        check: CheckDefinition,
        extraction_cfg: ExtractionConfig,
        context_text: str,
    ) -> str:
        """
        Построить промпт для LLM по списку полей.

        Используем:
        - роль (юридический ассистент),
        - явное описание схемы полей (имя, тип, allowed_values),
        - один пример JSON-ответа по этой схеме,
        - короткий self-check и жёсткие правила формата.
        """
        lines: list[str] = []

        # 1. Роль и задача
        check_description = ""
        if getattr(check, "description", None):
            check_description = f" Твоя текущая задача связана с проверкой: {check.description.strip()}"

        lines.append(
            "Ты — юридический ассистент по анализу договоров."
            " Тебе дан фрагмент договора. Твоя задача — извлечь структурированные поля"
            " по приведённой ниже схеме и вернуть ТОЛЬКО один JSON-объект."
            f"{check_description}"
        )
        lines.append("")

        # 2. Схема полей
        lines.append("Схема полей для извлечения:")
        lines.append("")

        for idx, field in enumerate(extraction_cfg.fields, 1):
            desc = (field.description or "").strip()
            type_name = field.type.name.lower()

            line = f"{idx}. {field.name} (тип: {type_name})"
            lines.append(line)
            if desc:
                lines.append(f"   Описание: {desc}")

            if field.allowed_values:
                allowed_vals = ", ".join(f'"{v}"' for v in field.allowed_values)
                lines.append(
                    f"   Допустимые значения (СТРОГО только из этого списка): [{allowed_vals}]"
                )

            if getattr(field, "unit", None):
                lines.append(f"   Единица измерения: {field.unit}")

            lines.append("")

        # 3. Пример JSON, сгенерированный из схемы
        example_fields: dict[str, dict[str, Any]] = {}
        for field in extraction_cfg.fields:
            example_value: Any

            if field.allowed_values:
                # берём первый допустимый вариант как пример
                example_value = str(field.allowed_values[0])
            else:
                if field.type == ExtractionFieldType.NUMBER:
                    example_value = 1000000
                elif field.type == ExtractionFieldType.BOOLEAN:
                    example_value = True
                else:
                    example_value = "Пример значения, извлечённого из текста"

            example_fields[field.name] = {
                "value": example_value,
                "confidence": 0.9,
            }

        example_obj = {"fields": example_fields}
        example_json = json.dumps(example_obj, ensure_ascii=False, indent=2)

        lines.append("Пример формата JSON-ответа (ПРИМЕР, а не реальные значения):")
        lines.append(example_json)
        lines.append("")

        # 4. Текст договора
        lines.append("Текст договора (фрагмент для анализа):")
        lines.append("---")
        lines.append(context_text)
        lines.append("---")
        lines.append("")

        # 5. Self-check (короткий чек-лист)
        lines.append("Перед выводом ответа мысленно проверь:")
        lines.append(
            "- Для каждого поля из схемы при необходимости есть запись в JSON."
        )
        lines.append(
            "- Для полей с допустимыми значениями выбрано СТРОГО одно из этих значений."
        )
        lines.append(
            "- JSON синтаксически валиден (кавычки, запятые, фигурные скобки)."
        )
        lines.append("")

        # 6. Жёсткие правила формата и финальная инструкция
        lines.append("ЖЁСТКИЕ правила формата ответа:")
        lines.append(
            "- Выведи ТОЛЬКО один валидный JSON-объект с корневым ключом \"fields\"."
        )
        lines.append(
            "- Не добавляй никакого текста до или после JSON (никаких пояснений, Markdown, бэктиков ``` и т.п.)."
        )
        lines.append(
            "- Все ключи и строковые значения должны быть в двойных кавычках."
        )
        lines.append(
            "- Если по какому-то полю нет информации, установи value = null и выбери низкий confidence (например, 0.2)."
        )
        lines.append(
            "- Не добавляй поля, которых нет в описанной схеме."
        )
        lines.append(
            "- Начни ответ сразу с символа {"
        )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # RESPONSE PARSING
    # -------------------------------------------------------------------------

    def _parse_response(self, text: str) -> dict[str, dict[str, Any]]:
        """
        Распарсить JSON-ответ LLM в "сырую" структуру без учёта схемы.

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
            # Попробуем вытащить JSON "изнутри"
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

        result: dict[str, dict[str, Any]] = {}
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

    # -------------------------------------------------------------------------
    # NORMALIZATION / VALIDATION
    # -------------------------------------------------------------------------

    def _normalize_fields(
        self,
        raw_fields: dict[str, dict[str, Any]],
        extraction_cfg: ExtractionConfig,
    ) -> dict[str, dict[str, Any]]:
        """
        Нормализовать значения из LLM по схеме ExtractionConfig.

        - Приводим confidence к float.
        - Если у поля есть allowed_values, стараемся привести value к одному из них.
        """
        field_by_name: dict[str, ExtractionFieldConfig] = {
            f.name: f for f in (extraction_cfg.fields or [])
        }

        normalized: dict[str, dict[str, Any]] = {}

        for name, payload in raw_fields.items():
            cfg = field_by_name.get(name)
            if not cfg:
                # LLM вернул поле, которого нет в схеме — игнорируем
                continue

            value = payload.get("value")
            confidence = payload.get("confidence", 0.7)
            try:
                confidence_f = float(confidence)
            except (TypeError, ValueError):
                confidence_f = 0.7

            # Нормализация по allowed_values (если заданы)
            if cfg.allowed_values:
                normalized_value = self._normalize_to_allowed_values(
                    value, cfg.allowed_values
                )
            else:
                normalized_value = value

            normalized[name] = {
                "value": normalized_value,
                "confidence": confidence_f,
            }

        return normalized

    def _normalize_to_allowed_values(
        self,
        value: Any,
        allowed_values: list[Any],
    ) -> Any:
        """
        Привести value к одному из allowed_values, если это разумно возможно.

        Логика:
        - если значение уже ровно равно одному из allowed_values (как строка) — оставляем;
        - если отличается только регистром/пробелами — приводим;
        - иначе возвращаем исходную строку (можно поменять на None по политике).
        """
        if value is None:
            return None

        allowed_strs = [str(v) for v in allowed_values]
        value_str = str(value)

        # Точное совпадение
        if value_str in allowed_strs:
            return value_str

        # Сравнение с нормализацией регистра/пробелов
        value_norm = value_str.strip().lower()
        allowed_norm_map = {str(v).strip().lower(): str(v) for v in allowed_values}
        if value_norm in allowed_norm_map:
            return allowed_norm_map[value_norm]

        # Здесь при желании можно добавить дополнительные словари соответствий
        # (например, "да" -> "yes", "нет" -> "no" и т.п.).

        return value_str
