# src/engine/detectors/extraction_llm_detector.py

"""
ExtractionLLMDetector: LLM-based structured data extractor.

Назначение:
- На основе ExtractionConfig (список полей) и текстового контекста
  вызвать LLM с промптом "верни JSON с полями" и распарсить ответ.
"""

from __future__ import annotations

import json
import os
from typing import Any

from core.logging import get_logger
from core.config import settings
from ..llm.client import _extract_json
from ..llm.client import LLMClient, LLMResponse
from ..playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

logger = get_logger(__name__)

PLAYBOOKS_DIR = os.getenv("PLAYBOOKS_DIR", "playbooks")
EXTRACTION_PROMPT_PATH = os.path.join(
    settings.BASE_DIR, "playbooks", "json_format_ru.txt"
)


def _load_prompt_template(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        logger.warning("Failed to load extraction prompt template", path=path)
        return None


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

        Шаблон берётся из playbooks/json_format_ru.txt и заполняется
        динамическими блоками:
        - {CHECK_META}
        - {FIELDS_SCHEMA}
        - {EXAMPLE_JSON}
        - {CONTEXT_TEXT}
        """
        template = _load_prompt_template(EXTRACTION_PROMPT_PATH)

        # 1. Динамический блок про чек
        check_meta_lines: list[str] = []
        if getattr(check, "name", None):
            check_meta_lines.append(f"Текущая проверка: {check.name.strip()}.")
        if getattr(check, "description", None):
            check_meta_lines.append(
                f"Краткое описание проверки: {check.description.strip()}"
            )
        check_meta = "\n".join(check_meta_lines).strip()
        if not check_meta:
            check_meta = "Текущая проверка: (без названия)."

        # 2. Схема полей
        schema_lines: list[str] = []
        for idx, field in enumerate(extraction_cfg.fields or [], 1):
            desc = (field.description or "").strip()
            type_name = field.type.name.lower()

            schema_lines.append(f"{idx}. {field.name} (тип: {type_name})")
            if desc:
                schema_lines.append(f"   Описание: {desc}")

            if field.allowed_values:
                allowed_vals = ", ".join(f'"{v}"' for v in field.allowed_values)
                schema_lines.append(
                    f"   Допустимые значения (СТРОГО только одно из списка, как строка): [{allowed_vals}]"
                )

            if getattr(field, "unit", None):
                schema_lines.append(f"   Единица измерения: {field.unit}")

            schema_lines.append("")
        fields_schema = "\n".join(schema_lines).rstrip()

        # 3. Пример JSON
        example_fields: dict[str, dict[str, Any]] = {}
        for field in extraction_cfg.fields or []:
            if field.allowed_values:
                example_value: Any = str(field.allowed_values[0])
            else:
                if field.type == ExtractionFieldType.NUMBER:
                    example_value = 1000000
                elif field.type == ExtractionFieldType.BOOLEAN:
                    example_value = True
                else:
                    example_value = "пример"

            example_fields[field.name] = {
                "value": example_value,
                "confidence": 0.9,
            }

        example_obj = {"fields": example_fields}
        example_json = json.dumps(example_obj, ensure_ascii=False, indent=2)

        # 4. Контекст
        context_clean = context_text.strip()

        if template:
            prompt = (
                template.replace("{CHECK_META}", check_meta)
                .replace("{FIELDS_SCHEMA}", fields_schema)
                .replace("{EXAMPLE_JSON}", example_json)
                .replace("{CONTEXT_TEXT}", context_clean)
            )
            return prompt

        # Fallback, если файла нет — минимальный встроенный промпт
        lines: list[str] = []
        lines.append("Ты — юридический ассистент по анализу договоров.")
        lines.append(
            "Тебе дан фрагмент договора. Твоя задача — извлечь структурированные поля "
            "по приведённой ниже схеме и вернуть ТОЛЬКО один JSON-объект."
        )
        lines.append("")
        lines.append(check_meta)
        lines.append("")
        lines.append("Схема полей для извлечения:")
        lines.append(fields_schema)
        lines.append("")
        lines.append("Пример формата JSON-ответа (ПРИМЕР, а не реальные значения):")
        lines.append(example_json)
        lines.append("")
        lines.append("Текст договора (фрагмент для анализа):")
        lines.append("---")
        lines.append(context_clean)
        lines.append("---")
        lines.append("")
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
            "- Если по какому-то полю нет достаточно информации, установи value = null и снизь confidence (например, до 0.2)."
        )
        lines.append(
            "- Не добавляй поля, которых нет в описанной схеме."
        )
        lines.append("- Начни ответ сразу с символа {")

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
