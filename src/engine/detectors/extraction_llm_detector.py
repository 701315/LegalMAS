# src/engine/detectors/extraction_llm_detector.py

"""
ExtractionLLMDetector: LLM‑экстрактор структурированных полей из текста договора.

Высокоуровневая идея
--------------------
Этот класс отвечает ТОЛЬКО за извлечение значений полей (structured_data)
из уже отобранного фрагмента договора, по заранее описанной схеме полей
(ExtractionConfig). Он НЕ решает, есть ли вообще нужная оговорка в документе
— этим занимается отдельный детектор (LLMDetector + rules).

Где в пайплайне используется
----------------------------
1. CheckRunner / CheckExecutor для конкретного чека вызывают ExtractionExecutor.
2. ExtractionExecutor:
   - определяет, какие поля нужно заполнить (check.extraction.fields),
   - формирует контекст текста (обычно вокруг evidence/location детектора),
   - вызывает ExtractionLLMDetector.extract(check, basetext).
3. ExtractionLLMDetector:
   - строит промпт для LLM по общему шаблону playbooks/json_format_ru.txt,
   - подмешивает доменный инструктаж из check.extraction.llm_prompt_extraction
     (если он есть для этого чека),
   - вызывает LLMClient и получает ответ в виде JSON {"fields": {...}},
   - нормализует значения по схеме (allowed_values, confidence и т.п.),
   - возвращает словарь вида:
       {
         "field_name": {
           "value": ...,
           "confidence": 0.0–1.0,
         },
         ...
       }
     который потом попадает в CheckResult.structured_data.

Источники знаний для промпта
----------------------------
Промпт для LLM собирается из четырёх частей:

1) Шаблон playbooks/json_format_ru.txt (универсальный каркас):
   - описывает роль модели,
   - объясняет, что нужно вернуть ТОЛЬКО один JSON‑объект с корневым ключом "fields",
   - задаёт общие правила интерпретации и confidence.

2) CHECK_META (динамический блок про чек):
   - если в ExtractionConfig задано поле llm_prompt_extraction (как в кейсе
     governing_law_and_forum), сюда подставляется этот длинный юридический
     инструктаж (role, steps, edge cases и т.п.);
   - если в тексте llm_prompt_extraction встречается плейсхолдер {context},
     он автоматически заменяется на реальный текст договора;
   - если llm_prompt_extraction нет, используется простое описание:
       "Текущая проверка: <name>. Краткое описание проверки: <description>".

3) FIELDS_SCHEMA:
   - генерируется по extraction_cfg.fields (name, type, allowed_values, unit, description),
   - в человекочитаемом виде объясняет модели, какие именно поля нужно заполнить
     и какие значения допустимы.

4) EXAMPLE_JSON:
   - автогенерируемый пример структуры ответа:
       {
         "fields": {
           "field_name": {
             "value": <пример значения>,
             "confidence": 0.9
           },
           ...
         }
       }
   - помогает модели придерживаться нужного JSON‑формата.

Правило рендеринга промптов (ВАЖНО для разработчиков)
-----------------------------------------------------
Все подстановки в этом классе делаются ТОЛЬКО через _render_template()
или последовательные .replace() — НЕ через str.format().

Причина: промпты могут содержать JSON-примеры ответа с фигурными скобками,
например: {"found": true, "land_category": "земли ИЖС"}.
str.format() интерпретирует любые {} как Python-плейсхолдеры и бросает
KeyError на невинных JSON-ключах. str.replace() заменяет только те строки,
которые явно указаны в словаре, и не трогает всё остальное.

Контракт ответа от LLM
----------------------
Ожидаемый формат ответа (после всех подсказок):

{
  "fields": {
    "<field_name>": {
      "value": ...,
      "confidence": 0.0–1.0
    },
    ...
  }
}

Где:
- "value":
  - строка, число, булево или null — в зависимости от типа поля и схемы;
  - для полей с allowed_values должно быть одним из допустимых значений
    (после нормализации).
- "confidence":
  - вещественное число от 0.0 до 1.0;
  - по смыслу: насколько уверенно модель извлекла это значение
    именно из данного текста (а не "придумала").

Парсинг и нормализация
----------------------
- _parse_response:
  - пытается распарсить ответ как JSON полностью;
  - если не удаётся, пробует вытащить JSON‑объект "изнутри" текста (_extract_json);
  - забирает только блок "fields" и для каждого поля — "value" и "confidence".

- _normalize_fields:
  - сопоставляет имена полей с ExtractionConfig;
  - приводит confidence к float;
  - если у поля есть allowed_values — старательно приводит value к одному из них
    (учитывая регистр/пробелы).

Гарантии устойчивости
---------------------
- Если LLM недоступен, вернул пустой ответ или невалидный JSON:
  - метод extract() возвращает пустой словарь {},
  - пайплайн не падает, просто не заполняет structured_data этим способом.

- Если LLM вернул лишние поля, которых нет в схеме:
  - такие поля игнорируются.

- Если значение нельзя уверенно привести к allowed_values:
  - возвращается оригинальная строка (по политике это можно поменять на None).

Важно
-----
Этот класс рекомендуется использовать только после того, как:
- детектор (rules + LLMDetector) уже нашёл релевантную оговорку
  и дал текстовый контекст (evidence/location),
- и нужно "выжать" из этого места максимум структурированных полей
  по конкретной юридической проверке.
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

        # Обрезаем текст до безопасного бюджета ДО сборки промпта.
        _limit = int(getattr(settings, "LLM_CONTEXT_LIMIT", 0) or 0)
        if _limit > 0:
            from engine.retrieval.tokenization import count_tokens
            _max_out = int(getattr(settings, "LLM_MAX_TOKENS", 512))
            _safety = int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 256))
            # Грубая оценка overhead шаблона промпта: ~300 слов
            _template_overhead = 300
            _text_budget = _limit - _max_out - _safety - _template_overhead
            _text_budget = max(200, _text_budget)
            # Обрезка по словам
            words = text.split()
            max_words = int(_text_budget / 2.5)
            if len(words) > max_words:
                text = " ".join(words[:max_words])
                logger.debug(
                    "ExtractionLLMDetector: text truncated to fit token budget",
                    original_words=len(words),
                    truncated_words=max_words,
                    budget=_text_budget,
                )

        prompt = self._build_prompt(check, extraction_cfg, text)
        grammar_path = getattr(settings, "LLM_EXTRACTION_JSON_GRAMMAR_PATH", None)

        response, error_details = self.client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=None,
            grammar_path=grammar_path,
        )
        if response is None:
            logger.warning(
                "LLM extraction call failed",
                error_type=error_details.get("error_type"),
                error_message=error_details.get("error_message"),
                attempts=error_details.get("llm_attempts"),
            )
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

        Все подстановки выполняются через _render_template() — безопасный
        метод на основе .replace(). НЕ используем str.format(), чтобы избежать
        KeyError на JSON-фигурных скобках внутри промптов.
        """
        template = _load_prompt_template(EXTRACTION_PROMPT_PATH)

        # 1. Динамический блок про чек
        check_meta_lines: list[str] = []

        # 1.1. Если в extraction есть свой LLM-промпт — используем его как основу.
        # ВАЖНО: если в llm_prompt_extraction написано {context} — заменяем его
        # на реальный текст договора прямо здесь, через _render_template.
        # Это необходимо для чеков вроде governing_law_and_forum, где юридический
        # инструктаж включает блок с анализируемым текстом.
        custom_extraction_prompt = getattr(extraction_cfg, "llm_prompt_extraction", None)
        if isinstance(custom_extraction_prompt, str) and custom_extraction_prompt.strip():
            # Подставляем {context} в кастомный промпт, если он там есть.
            # Остальные плейсхолдеры (если есть) оставляем как есть — они могут
            # быть частью JSON-примеров внутри инструктажа.
            rendered_custom = self._render_template(
                template=custom_extraction_prompt.strip(),
                variables={"{context}": context_text},
            )
            check_meta_lines.append(rendered_custom)
        else:
            # 1.2. Иначе — минимальная метаинформация по чеку
            if getattr(check, "name", None):
                check_meta_lines.append(f"Текущая проверка: {check.name.strip()}.")
            if getattr(check, "description", None):
                check_meta_lines.append(
                    f"Краткое описание проверки: {check.description.strip()}"
                )

        check_meta = "\n".join(check_meta_lines).strip()
        if not check_meta:
            check_meta = "Текущая проверка: (без названия)."
            logger.warning(
                "ExtractionLLMDetector: check has no name, description "
                "or llm_prompt_extraction — using fallback check_meta",
                check_id=getattr(check, "id", None),
            )

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
                    "   Допустимые значения (СТРОГО только одно из списка, как строка): "
                    f"[{allowed_vals}]"
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
            # Используем _render_template() — безопасная замена через .replace().
            # str.format() здесь НЕ используется намеренно: шаблон json_format_ru.txt
            # и example_json содержат фигурные скобки как часть JSON-примеров,
            # и str.format() падал бы с KeyError на каждом таком символе.
            prompt = self._render_template(
                template=template,
                variables={
                    "{CHECK_META}": check_meta,
                    "{FIELDS_SCHEMA}": fields_schema,
                    "{EXAMPLE_JSON}": example_json,
                    "{CONTEXT_TEXT}": context_clean,
                },
            )
            return prompt

        # Fallback, если файла нет — минимальный встроенный промпт.
        # Используем обычную конкатенацию строк, не format().
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
        lines.append("ЖЁСТКИЕ правила формата ответа (ОБЯЗАТЕЛЬНО):")
        lines.append(
            '- Выведи ТОЛЬКО один валидный JSON-объект с корневым ключом "fields".'
        )
        lines.append(
            "- НЕ добавляй НИКАКОГО текста до или после JSON: "
            "никаких пояснений, инструкций, комментариев, Markdown, списков, "
            '"Шаг 1", "Ответ:", подсказок по форматированию и т.п.'
        )
        lines.append(
            '- НЕ объясняй, КАК нужно оформить JSON, не пиши советы типа '
            '"заверши ответ запятой". Просто СРАЗУ выведи готовый JSON.'
        )
        lines.append(
            "- Все ключи и строковые значения должны быть в двойных кавычках."
        )
        lines.append(
            "- Если по какому-то полю нет достаточно информации, установи "
            "value = null и confidence = 0.2."
        )
        lines.append("- Не добавляй поля, которых нет в описанной схеме.")
        lines.append(
            "- Начни ответ СРАЗУ с символа { и закончи СРАЗУ символом } "
            "(никаких символов или переводов строк до и после)."
        )
        lines.append(
            "- Пример выше — это только пример структуры. В ответе выведи "
            "ТОЛЬКО реальный JSON, БЕЗ слов \"пример\", \"ответ\" и т.п."
        )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # TEMPLATE RENDERING
    # -------------------------------------------------------------------------

    @staticmethod
    def _render_template(
        template: str,
        variables: dict[str, str],
    ) -> str:
        """
        Безопасно подставить переменные в шаблон через последовательные .replace().

        Принимает:
        - template: строка шаблона с плейсхолдерами вида {PLACEHOLDER}
        - variables: словарь {"{PLACEHOLDER}": "значение"}

        Возвращает строку с выполненными подстановками.

        Почему НЕ str.format():
        - Шаблоны промптов содержат JSON-примеры ответа LLM с фигурными скобками,
          например: {"fields": {"land_category": {"value": "пример", ...}}}.
        - str.format() интерпретирует {land_category} как Python-плейсхолдер
          и падает с KeyError, хотя это просто JSON-пример внутри текста.
        - .replace() работает с конкретными подстроками и не трогает
          ничего, что не указано явно в словаре variables.

        Для непрофессионального программиста:
        - Представь шаблон как листок с напечатанным текстом, где выделены
          специальные метки: {CHECK_META}, {CONTEXT_TEXT} и т.п.
        - _render_template находит каждую метку и заменяет её на нужное значение.
        - Если в тексте есть другие фигурные скобки (например, в JSON-примере),
          они остаются нетронутыми — метод их просто не замечает.
        """
        result = template
        for placeholder, value in variables.items():
            result = result.replace(placeholder, value)
        return result

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
                logger.warning(
                    "Failed to parse LLM extraction JSON", raw=text[:500]
                )
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

        Делает следующее:
        - выбрасывает поля, которых нет в схеме;
        - приводит confidence к float в диапазон [0.0, 1.0];
        - приводит value к типу поля (NUMBER / BOOLEAN / STRING);
        - если заданы allowed_values — маппит к ним, иначе значение выкидывается;
        - опционально логирует нарушения required.
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
            conf_raw = payload.get("confidence", 0.7)
            try:
                confidence_f = float(conf_raw)
            except (TypeError, ValueError):
                confidence_f = 0.7

            # Жёстко обрезаем confidence в [0.0, 1.0]
            if confidence_f < 0.0:
                confidence_f = 0.0
            elif confidence_f > 1.0:
                confidence_f = 1.0

            # 1) типовая нормализация
            value_cast = self._cast_to_type(cfg, value)

            # 2) allowed_values (если заданы)
            if cfg.allowed_values:
                value_allowed = self._normalize_to_allowed_values(
                    value_cast,
                    cfg.allowed_values,
                )
                if value_allowed is None:
                    # Не смогли привести к allowed_values — выбрасываем
                    logger.warning(
                        "ExtractionLLMDetector: value not in allowed_values, discarding",
                        extra={
                            "field_name": cfg.name,
                            "value": str(value_cast),
                            "allowed_values": [str(v) for v in cfg.allowed_values],
                        },
                    )
                    continue
                value_cast = value_allowed

            # 3) required-поля: если required == True, а value_cast пустое → логируем
            if getattr(cfg, "required", False) and (value_cast is None or str(value_cast).strip() == ""):
                logger.warning(
                    "ExtractionLLMDetector: required field has empty value after normalization",
                    extra={
                        "field_name": cfg.name,
                        "raw_value": str(payload.get("value", "")),
                    },
                )
                # Поле всё равно записываем (value=None), чтобы UI видел,
                # что required-поле не заполнено, а не терялось бесследно.
                normalized[name] = {
                    "value": None,
                    "confidence": confidence_f,
                }
                continue

            normalized[name] = {
                "value": value_cast,
                "confidence": confidence_f,
            }

        return normalized

    def _normalize_to_allowed_values(
        self,
        value: Any,
        allowed_values: list[Any],
    ) -> Any | None:
        """
        Привести value к одному из allowed_values.

        Логика:
        - если значение уже ровно равно одному из allowed_values (строго) — оставляем;
        - если отличается только регистром/пробелами — маппим к каноническому значению;
        - иначе возвращаем None (значение считается невалидным).
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

        return None
    

    def _cast_to_type(
        self,
        cfg: ExtractionFieldConfig,
        value: Any,
    ) -> Any:
        """
        Привести value к типу поля из схемы.

        - NUMBER: float/int при возможности, иначе исходная строка.
        - BOOLEAN: нормализация да/нет/true/false/1/0, иначе исходная строка.
        - STRING: str(value) или None, если value пустое/null-подобное.
        """
        if value is None:
            return None

        if cfg.type == ExtractionFieldType.NUMBER:
            # Сначала строковая нормализация, как в ExtractionExecutor._cast_value
            s = str(value).replace(" ", "").replace(",", ".")
            try:
                num = float(s)
                return int(num) if num.is_integer() else num
            except ValueError:
                return str(value)

        if cfg.type == ExtractionFieldType.BOOLEAN:
            v = str(value).strip().lower()
            true_vals = {"yes", "true", "1", "да", "верно"}
            false_vals = {"no", "false", "0", "нет", "неверно"}
            if v in true_vals:
                return True
            if v in false_vals:
                return False
            return str(value)

        # STRING / default
        s = str(value)
        return s if s.strip() else None    
    




