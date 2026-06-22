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
   - строит prompt из двух независимых внешних templates:
       * semantic prompt block (custom llm_prompt_extraction или fallback template),
       * technical response contract (json_format_ru.txt);
   - гарантирует, что контекст договора попадает в prompt ровно один раз;
   - вызывает LLMClient и получает ответ в canonical JSON-виде {"fields": {...}}.
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

from core.config import settings
from core.logging import get_logger
from engine.extraction_normalization import (
    is_null_like_value,
    normalize_scalar_null_like_value,
    normalize_to_allowed_values,
)

from ..llm.client import LLMClient, _extract_json
from ..playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)

logger = get_logger(__name__)

LLM_DEFAULT_CONFIDENCE: float = settings.LLM_DEFAULT_CONFIDENCE

EXTRACTION_PROMPT_PATH = os.path.join(
    settings.BASE_DIR,
    "playbooks",
    "json_format_ru.txt",
)

EXTRACTION_FALLBACK_META_PATH = os.path.join(
    settings.BASE_DIR,
    "playbooks",
    "extraction_fallback_meta_ru.txt",
)

def _salvage_partial_json(text: str) -> dict | None:
    """
    Attempt to recover field data from a truncated canonical JSON response.

    LLM returns canonical format {"fields": {"field_name": {"value": ..., "confidence": ...}}}
    but the JSON string can be cut off mid-way when the output token budget is exhausted.

    This function recovers already-complete field blocks from truncated JSON text.

    Strategy (three passes, in order):

    Pass 1 — complete field blocks:
        Find syntactically complete {"value": ..., "confidence": ...} blocks.
        Handles short strings, null, bool, numbers.
        Never recovers unclosed string values.

    Pass 2 — partial long string values:
        For fields whose string value was not closed (JSON truncated mid-string),
        recover the partial text written so far and append a truncation marker.
        Applied only to fields NOT already recovered in Pass 1.
        Minimum partial value length: 30 characters (avoids junk fragments).

    Pass 3 — short signal values without confidence key:
        For very short string values (≤ 50 chars) where the confidence key
        was not yet written before truncation.
        Applied only to fields NOT already recovered in Pass 1 or 2.

    This is a universal robustness measure for any extraction check with N > 6 fields,
    and specifically for inventory-style checks where a single fact field
    (e.g. asset_schedule_details) carries a long multi-line string value.

    Not specific to any document, language, or check type.
    Never guesses or invents values.

    Returns:
        dict with {"fields": {recovered_field_name: {...}}} if anything recovered, else None.
    """
    import re

    # ── Pass 1: syntactically complete field blocks ────────────────────────────
    # Matches: "field_name": {"value": <complete_value>, "confidence": <float>}
    # <complete_value> = quoted string | null | true | false | number
    _field_pattern = re.compile(
        r'"(?P<name>[a-z_][a-z0-9_]*)"\s*:\s*\{'
        r'\s*"value"\s*:\s*(?P<value>"(?:[^"\\]|\\.)*"|null|true|false|-?\d+(?:\.\d+)?)\s*,'
        r'\s*"confidence"\s*:\s*(?P<confidence>\d+(?:\.\d+)?)\s*\}',
        re.DOTALL,
    )

    recovered: dict[str, dict] = {}

    for m in _field_pattern.finditer(text):
        name = m.group("name")
        raw_value = m.group("value")
        raw_confidence = m.group("confidence")

        try:
            value = json.loads(raw_value)
        except (json.JSONDecodeError, ValueError):
            continue

        try:
            confidence = float(raw_confidence)
            confidence = max(0.0, min(confidence, 1.0))
        except ValueError:
            confidence = LLM_DEFAULT_CONFIDENCE

        recovered[name] = {"value": value, "confidence": confidence}

    # ── Pass 2: partial long string values (truncated mid-string) ─────────────
    # Matches: "field_name": {"value": "<partial text...  (no closing quote)
    # Applied only to fields not already recovered in Pass 1.
    #
    # Rationale: inventory-style checks (e.g. asset_schedule_details) produce
    # long multi-line string values. When LLM output is token-truncated, the
    # closing quote and confidence key are missing. Pass 1 cannot match these.
    # Pass 2 recovers the partial text and appends a truncation marker,
    # so that has_meaningful_extraction() can still return True.
    #
    # Minimum partial length (30 chars) avoids recovering junk opening fragments
    # like "Не" or "Дан" where truncation happened immediately after the quote.
    _PARTIAL_MIN_CHARS = 30
    _TRUNCATION_MARKER = "… [СПИСОК ОБРЕЗАН: вывод превысил лимит токенов]"

    _partial_string_pattern = re.compile(
        r'"(?P<name>[a-z_][a-z0-9_]*)"\s*:\s*\{\s*"value"\s*:\s*"(?P<partial>[^"]{30,})',
        re.DOTALL,
    )

    for m in _partial_string_pattern.finditer(text):
        name = m.group("name")
        if name in recovered:
            # Already recovered in Pass 1 — skip.
            continue

        partial_text = m.group("partial")

        # Strip trailing whitespace / incomplete escape sequences.
        partial_text = partial_text.rstrip()
        if partial_text.endswith("\\"):
            partial_text = partial_text[:-1].rstrip()

        if len(partial_text) < _PARTIAL_MIN_CHARS:
            continue

        recovered[name] = {
            "value": partial_text + _TRUNCATION_MARKER,
            "confidence": 0.5,
        }

    # ── Pass 3: short signal values without confidence key ────────────────────
    # Matches: "field_name": {"value": "<short_value>"  (confidence key missing)
    # Applied only to fields not already recovered in Pass 1 or 2.
    #
    # Rationale: when truncation happens between the value and the confidence key,
    # Pass 1 fails (no "confidence" key). Pass 3 catches these short values,
    # which are typically signal fields (e.g. "defined", "not_defined").
    # Long strings are already handled by Pass 2.
    _short_no_confidence_pattern = re.compile(
        r'"(?P<name>[a-z_][a-z0-9_]*)"\s*:\s*\{\s*"value"\s*:\s*"(?P<value>[^"]{1,50})"\s*(?!,\s*"confidence")',
        re.DOTALL,
    )

    for m in _short_no_confidence_pattern.finditer(text):
        name = m.group("name")
        if name in recovered:
            continue

        raw_value = m.group("value").strip()
        if not raw_value:
            continue

        recovered[name] = {
            "value": raw_value,
            "confidence": LLM_DEFAULT_CONFIDENCE,
        }

    if not recovered:
        return None

    return {"fields": recovered}


def _load_prompt_template(path: str) -> str:
    """
    Строгий loader внешнего prompt template.

    Production-принцип:
    - отсутствие prompt template — это deployment/config error,
      а не runtime-warning, который надо silently обходить;
    - extraction pipeline должен fail-fast, если обязательный template отсутствует.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise RuntimeError(
            f"Failed to load extraction prompt template: {path}"
        ) from e


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

        Архитектура бюджетирования токенов
        -----------------------------------
        Правильный порядок операций:
        1. Собрать скелет промпта БЕЗ context (с пустым placeholder).
        2. Измерить реальный размер скелета — это и есть overhead.
        3. Вычесть overhead + max_tokens + safety из n_ctx → остаток под context.
        4. Если остаток <= MIN_CONTEXT_WORDS — вернуть {} с предупреждением
            (скелет не помещается; нужно упрощать llm_prompt_extraction чека).
        5. Обрезать context по остатку.
        6. Собрать финальный промпт с реальным context.

        Почему НЕ используем старый хардкод _template_overhead = 300 слов:
        - Реальный overhead для governing_law_and_forum без context = 1119 слов.
        - Хардкод недооценивал в 3.7x, что приводило к overflow контекстного окна.

        Почему коэффициент 3.8, а не 2.5:
        - count_tokens() использует CYRILLIC_TOKEN_FACTOR = 2.5 (слово → токены).
        - Для Qwen2.5 SentencePiece на юридическом русском реальный коэффициент
            3.5–4.0 токена на слово (кириллица в UTF-8 → субтокены).
        - 3.8 — консервативная оценка, даёт запас ~5–10% от реального значения.
        - Долгосрочно нужно заменить на llm_model.tokenize() для точного подсчёта.
        """
        extraction_cfg: ExtractionConfig | None = getattr(check, "extraction", None)
        if not extraction_cfg or not extraction_cfg.enabled:
            return {}

        if not self.client.is_available():
            logger.debug("LLM not available for extraction")
            return {}

        if not text.strip():
            return {}

        # ------------------------------------------------------------------
        # 1. БЮДЖЕТ: читаем лимиты из settings один раз
        # ------------------------------------------------------------------
        _limit = int(getattr(settings, "LLM_CONTEXT_LIMIT", 0) or 0)
        _max_out = int(getattr(settings, "LLM_MAX_TOKENS", 512))
        _safety = int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 512))

        if _limit > 0:
            # ------------------------------------------------------------------
            # 2. СКЕЛЕТ ПРОМПТА: собираем промпт с пустым context,
            #    чтобы точно измерить overhead всех остальных частей.
            #    Это единственный способ учесть реальный размер:
            #    - json_format_ru.txt шаблона,
            #    - llm_prompt_extraction чека (может быть очень большим),
            #    - fields_schema (список полей с описаниями),
            #    - example_json (пример структуры ответа).
            # ------------------------------------------------------------------
            prompt_skeleton = self._build_prompt(check, extraction_cfg, context_text="")
            skeleton_words = len(prompt_skeleton.split())

            # Консервативный коэффициент для Qwen2.5 на русском юр. тексте.
            # count_tokens() использует 2.5, что занижает реальность на 40-60%.
            # 3.8 даёт запас ~10% к реальному значению.
            token_factor = 3.8
            skeleton_tokens = int(skeleton_words * token_factor)

            # ------------------------------------------------------------------
            # 3. GRACEFUL FALLBACK: если скелет уже не помещается — выходим.
            #    Это значит llm_prompt_extraction чека слишком велик для n_ctx.
            #    Решение: увеличить LLM_LOCAL_N_CTX / LLM_CONTEXT_LIMIT в config,
            #    или упростить llm_prompt_extraction конкретного чека.
            # ------------------------------------------------------------------
            _min_context_words = 50  # меньше этого — извлечение бессмысленно
            _min_context_tokens = int(_min_context_words * token_factor)

            available_for_context = _limit - _max_out - _safety - skeleton_tokens

            if available_for_context < _min_context_tokens:
                logger.warning(
                    "ExtractionLLMDetector: prompt skeleton alone "
                    "exhausts context window — skipping extraction. "
                    "Action required: increase LLM_LOCAL_N_CTX / "
                    "LLM_CONTEXT_LIMIT in config, or simplify "
                    "llm_prompt_extraction for this check.",
                    check_id=getattr(check, "id", None),
                    check_name=getattr(check, "name", None),
                    skeleton_words=skeleton_words,
                    skeleton_tokens_estimated=skeleton_tokens,
                    context_limit=_limit,
                    available_for_context=available_for_context,
                    min_context_tokens=_min_context_tokens,
                )
                return {}

            # ------------------------------------------------------------------
            # 4. ОБРЕЗКА CONTEXT: по реальному остатку бюджета.
            # ------------------------------------------------------------------
            max_context_words = int(available_for_context / token_factor)
            words = text.split()
            if len(words) > max_context_words:
                text = " ".join(words[:max_context_words])
                logger.debug(
                    "ExtractionLLMDetector: context truncated to fit token budget",
                    check_id=getattr(check, "id", None),
                    original_words=len(words),
                    truncated_words=max_context_words,
                    skeleton_tokens=skeleton_tokens,
                    available_for_context=available_for_context,
                    context_limit=_limit,
                )

        # ------------------------------------------------------------------
        # 5. ФИНАЛЬНЫЙ ПРОМПТ: собираем с реальным (возможно обрезанным) context.
        # ------------------------------------------------------------------
        logger.debug(
            "ExtractionLLMDetector: context_text sample",
            check_id=getattr(check, "id", None),
            context_words=len(text.split()),
            context_preview=text[:400] if text else "(empty)",
        )

        prompt = self._build_prompt(check, extraction_cfg, text)
        grammar_path = getattr(settings, "LLM_EXTRACTION_JSON_GRAMMAR_PATH", None)

        extraction_max_tokens = getattr(extraction_cfg, "llm_max_tokens", None)
        if extraction_max_tokens is None:
            extraction_max_tokens = int(
                getattr(settings, "LLM_EXTRACTION_MAX_TOKENS", 512)
            )

        response, error_details = self.client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=extraction_max_tokens,
            grammar_path=grammar_path,
            response_format="json_object",  # P8.5: Ollama JSON mode
        )
        if response is None:
            logger.warning(
                "LLM extraction call failed",
                error_type=error_details.get("error_type"),
                error_message=error_details.get("error_message"),
                attempts=error_details.get("llm_attempts"),
            )
            return {}

        if not response.text.strip():
            return {}

        # 6) парсим JSON в "сырую" структуру
        raw_fields = self._parse_response(response.text)
        if not raw_fields:
            return {}

        # 7) нормализуем значения по схеме extraction_cfg
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
        Построить extraction prompt.

        Архитектура:
        - semantic block задаётся либо custom llm_prompt_extraction из YAML,
          либо внешним fallback template;
        - context попадает в prompt ровно один раз;
        - response contract задаётся отдельным внешним template
          (json_format_ru.txt);
        - код выполняет только orchestration/rendering, но не хранит
          текстовые prompt instructions внутри Python.
        """
        technical_template = _load_prompt_template(EXTRACTION_PROMPT_PATH)
        fields_schema = self._build_fields_schema(extraction_cfg)
        example_json = self._build_example_json(extraction_cfg)
        context_clean = context_text.strip()

        custom_extraction_prompt = getattr(extraction_cfg, "llm_prompt_extraction", None)
        has_custom_prompt = bool(
            isinstance(custom_extraction_prompt, str)
            and custom_extraction_prompt.strip()
        )

        if has_custom_prompt:
            check_meta = self._build_custom_semantic_block(
                custom_prompt=custom_extraction_prompt.strip(),
                context_text=context_clean,
            )
        else:
            check_meta = self._build_fallback_semantic_block(
                check=check,
                context_text=context_clean,
            )

        prompt = self._render_template(
            template=technical_template,
            variables={
                "{CHECK_META}": check_meta,
                "{FIELDS_SCHEMA}": fields_schema,
                "{EXAMPLE_JSON}": example_json,
            },
        )

        # Universal compactness contract appended to all extraction prompts.
        #
        # Rationale:
        # - Extraction checks with N > 8 fields risk JSON truncation when
        #   LLM writes verbose citations in *_details fields.
        # - Presence/detection layer (LLMDetector + rules) already handles
        #   evidence anchoring and full citations.
        # - Extraction layer is responsible only for compact structured facts.
        # - This instruction is universal: applies to any check, any language,
        #   any document type. Not document-specific tuning.
        _COMPACTNESS_FOOTER = (
            "\n\nВАЖНО: В каждое поле пиши только краткое резюме "
            "(не более 1–2 предложений). "
            "Не цитируй весь пункт. "
            "Не добавляй пояснений вне JSON-объекта."
        )
        return prompt + _COMPACTNESS_FOOTER


    def _build_custom_semantic_block(
        self,
        *,
        custom_prompt: str,
        context_text: str,
    ) -> str:
        """
        Построить semantic block из llm_prompt_extraction.

        Контракт:
        - custom prompt обязан содержать {context}
        - именно custom prompt управляет placement контекста
        """
        if "{context}" not in custom_prompt:
            raise ValueError(
                "Custom extraction prompt must contain '{context}' placeholder"
            )

        return self._render_template(
            template=custom_prompt,
            variables={"{context}": context_text},
        )

    def _build_fallback_semantic_block(
        self,
        *,
        check: CheckDefinition,
        context_text: str,
    ) -> str:
        """
        Построить fallback semantic block через внешний template.
        """
        fallback_template = _load_prompt_template(EXTRACTION_FALLBACK_META_PATH)

        check_name = (getattr(check, "name", None) or "(без названия)").strip()
        check_description = (
            getattr(check, "description", None)
            or "Описание проверки не задано."
        ).strip()

        return self._render_template(
            template=fallback_template,
            variables={
                "{CHECK_NAME}": check_name,
                "{CHECK_DESCRIPTION}": check_description,
                "{CONTEXT}": context_text,
            },
        )

    def _build_fields_schema(
        self,
        extraction_cfg: ExtractionConfig,
    ) -> str:
        """
        Построить человекочитаемую схему полей.
        """
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
                    "   Допустимые значения: "
                    f"[{allowed_vals}]"
                )

            if getattr(field, "unit", None):
                schema_lines.append(f"   Единица измерения: {field.unit}")

            schema_lines.append("")

        return "\n".join(schema_lines).rstrip()

    def _build_example_json(
        self,
        extraction_cfg: ExtractionConfig,
    ) -> str:
        """
        Построить canonical example JSON.
        """
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
        return json.dumps(example_obj, ensure_ascii=False, indent=2)



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
        Распарсить JSON-ответ LLM.

        Canonical contract:
        {
          "fields": {
            "field_name": {
              "value": ...,
              "confidence": 0.0-1.0
            }
          }
        }

        Runtime robustness:
        - если LLM вернул top-level flat JSON вместо {"fields": ...},
          parser принимает его как fallback и логирует warning;
        - это не backward compatibility со старыми данными,
          а устойчивость к occasional model drift.
        """
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            candidate = _extract_json(text)
            if candidate:
                data = candidate
            else:
                # Full JSON parse and _extract_json both failed.
                # JSON is likely truncated due to output token budget exhaustion.
                # Attempt partial salvage: recover field blocks that are already
                # syntactically complete in the truncated text.
                # Only recovers fields that LLM already finished writing.
                # Never invents or guesses missing values.
                salvaged = _salvage_partial_json(text)
                if salvaged:
                    recovered_count = len(salvaged.get("fields", {}))
                    logger.warning(
                        "ExtractionLLMDetector: JSON truncated, "
                        "partial salvage recovered %d field(s). "
                        "Consider increasing llm_max_tokens for this check.",
                        recovered_count,
                        raw_preview=text[:300],
                    )
                    data = salvaged
                else:
                    logger.warning(
                        "Failed to parse LLM extraction JSON",
                        raw=text[:500],
                    )
                    return {}

        if not isinstance(data, dict):
            return {}

        if isinstance(data.get("fields"), dict):
            raw_fields = data["fields"]
        else:
            logger.warning(
                "ExtractionLLMDetector: non-canonical flat JSON response received; "
                "accepting via tolerant parser"
            )
            raw_fields = data

        result: dict[str, dict[str, Any]] = {}

        for name, payload in raw_fields.items():
            if isinstance(payload, dict):
                value = payload.get("value")
                conf_raw = payload.get("confidence", LLM_DEFAULT_CONFIDENCE)
            else:
                value = payload
                conf_raw = LLM_DEFAULT_CONFIDENCE

            try:
                confidence = float(conf_raw)
            except (TypeError, ValueError):
                confidence = LLM_DEFAULT_CONFIDENCE

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
            conf_raw = payload.get("confidence", LLM_DEFAULT_CONFIDENCE)
            try:
                confidence_f = float(conf_raw)
            except (TypeError, ValueError):
                confidence_f = LLM_DEFAULT_CONFIDENCE

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
                    # null-like value без not_found в allowed_values —
                    # это не schema violation, а отсутствие значения.
                    if is_null_like_value(value_cast):
                        logger.debug(
                            "ExtractionLLMDetector: null-like value normalized to empty",
                            extra={
                                "field_name": cfg.name,
                                "value": str(value_cast),
                                "allowed_values": [str(v) for v in cfg.allowed_values],
                            },
                        )
                        continue

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
            if getattr(cfg, "required", False) and (
                value_cast is None or str(value_cast).strip() == ""
            ):
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

            # Universal string length cap for extraction field values.
            # Prevents structured_data from bloating with full-paragraph citations.
            # Applied universally: any check, any language, any document type.
            _MAX_EXTRACTION_FIELD_CHARS = 500
            if isinstance(value_cast, str) and len(value_cast) > _MAX_EXTRACTION_FIELD_CHARS:
                value_cast = value_cast[:_MAX_EXTRACTION_FIELD_CHARS].rstrip() + "…"

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

        Поведение:
        - null-like -> 'not_found', если он разрешён, иначе None;
        - case-insensitive exact match -> канонический вариант из YAML;
        - иначе None.
        """
        return normalize_to_allowed_values(value, allowed_values)

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
        value = normalize_scalar_null_like_value(value)
        if value is None:
            return None

        if cfg.type == ExtractionFieldType.NUMBER:
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

        s = str(value)
        return s if s.strip() else None
    
