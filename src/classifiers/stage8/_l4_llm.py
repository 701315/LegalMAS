# src/classifiers/stage8/_l4_llm.py

"""
L4-fallback: вызов LLM для классификации документа и парсинг ответа.

Production-ready версия:
- prompt template loading from settings.CLASSIFICATION_L4_PROMPT_PATH
- ChatML-обёртка для qwen2.5-instruct и совместимых моделей
- оптимизированный рендеринг allowed_types (без aliases/doc_types_supported)
- динамическая триммация document_fragment с учётом бюджета токенов
- structured rendering of allowed_types using YAML metadata
- strict JSON parsing and validation
- raw diagnostics for HybridClassifier / postmortem analysis

Контракт:
  call() требует непустой allowed_types — это защитная проверка
  архитектурного инварианта (policy не должна допускать пустой space).
  registry.get_config() вызывается tolerant — сбой registry не роняет L4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import settings
from core.logging import get_logger
from engine.llm.client import LLMClient, LLMResponse

from ..yaml_registry import DocumentTypeConfig, YAMLRegistry

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Константы ChatML
# ---------------------------------------------------------------------------

_CHATML_SYSTEM_INSTRUCTION = (
    "Ты — юридический ассистент. Отвечай СТРОГО одним JSON-объектом "
    "с полями type_code, confidence, reasoning. "
    "Никаких пояснений, никакого markdown, никаких блоков ```json. "
    "Только JSON."
)

# Токены ChatML-формата (Qwen2.5-Instruct / ChatML-совместимые модели)
_CHATML_IM_START = "<|im_start|>"
_CHATML_IM_END = "<|im_end|>"


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


class L4LLMClassifier:
    """
    Отвечает за два шага L4:
      1. build_prompt + call_with_retries -> LLMResponse
      2. parse -> {type_code, confidence, reasoning, parse_success, raw}

    Инварианты:
      - call() требует непустой allowed_types (защитная проверка контракта policy).
      - registry.get_config() вызывается в tolerant-режиме: сбой registry
        не прерывает L4, type попадает в prompt без метаданных.
    """

    def __init__(self, llm_client: LLMClient, registry: YAMLRegistry) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self._prompt_template_cache: str | None = None

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

        Контракт: allowed_types должен быть непустым.
        Это архитектурный инвариант: policy (build_llm_allowed_types +
        should_run_l4) не должна допускать вызов L4 с пустым candidate space.

        Возвращает: (LLMResponse | None, errordetails: dict)
        """
        if not allowed_types:
            raise ValueError(
                "L4LLMClassifier.call requires non-empty allowed_types. "
                "L4 should not be called without a candidate space — "
                "this is a policy violation (see _l4_policy.should_run_l4)."
            )

        prompt = self._build_prompt(
            text=text,
            filename=filename,
            folder_path=folder_path,
            allowed_types=allowed_types,
        )

        # === БЮДЖЕТ-ПРОВЕРКА ===
        # Финальный промпт уже должен быть в бюджете после _build_prompt,
        # но оставляем проверку как защитный слой.
        estimated_prompt_tokens = self._estimate_token_count(prompt)
        max_allowed_tokens = (
            settings.LLM_CONTEXT_LIMIT - settings.LLM_MAX_TOKENS - settings.LLM_SAFETY_MARGIN_TOKENS
        )

        if estimated_prompt_tokens > max_allowed_tokens:
            logger.warning(
                "L4 prompt exceeds safe token budget after build, aborting",
                extra={
                    "estimated_prompt_tokens": estimated_prompt_tokens,
                    "max_allowed_tokens": max_allowed_tokens,
                    "LLM_CONTEXT_LIMIT": settings.LLM_CONTEXT_LIMIT,
                    "LLM_MAX_TOKENS": settings.LLM_MAX_TOKENS,
                    "LLM_SAFETY_MARGIN_TOKENS": settings.LLM_SAFETY_MARGIN_TOKENS,
                    "prompt_len_chars": len(prompt),
                    "filename": filename,
                },
            )
            return None, {
                "failure_reason": "prompt_exceeds_token_budget",
                "error_type": "context_limit_prevention",
                "estimated_tokens": estimated_prompt_tokens,
                "max_allowed": max_allowed_tokens,
            }
        # === КОНЕЦ БЮДЖЕТ-ПРОВЕРКИ ===

        logger.info(
            "L4LLMClassifier.call",
            extra={
                "allowed_types_count": len(allowed_types),
                "allowed_types": allowed_types,
                "filename": filename,
                "folder_path": folder_path,
                "prompt_preview": prompt[:300],
            },
        )

        response, errordetails = self.llm_client.call_with_retries(
            prompt=prompt,
            temperature=0.0,
            max_tokens=settings.LLM_MAX_TOKENS,
            response_format="json_object",  # P8.5: Ollama JSON mode
        )
        return response, errordetails

    def parse(
        self,
        response: LLMResponse,
        *,
        allowed_types: list[str],
    ) -> dict[str, Any]:
        """
        Разобрать JSON из ответа LLM и привести к безопасным значениям.

        Tolerant mode:
        - лишние ключи от LLM игнорируются с warning;
        - неточный type_code допускает ограниченную нормализацию.

        Контракт возврата:
          {type_code, confidence, reasoning, parse_success, raw}
        """
        text = (getattr(response, "text", "") or "").strip()

        raw: dict[str, Any] = {
            "provider": getattr(response, "provider", None),
            "model": getattr(response, "model", None),
            "tokens_used": getattr(response, "tokens_used", None),
            "parse_success": False,
            "error_type": None,
            "error_message": None,
            "response_text": text,
            "parsed_json": None,
            "allowed_types": list(allowed_types or []),
        }

        type_code = "UNKNOWN"
        confidence = 0.0
        reasoning = ""
        parse_success = False

        try:
            obj = self._extract_single_json_object(text)
            if not isinstance(obj, dict):
                raise ValueError("LLM response JSON is not an object")

            raw["parsed_json"] = obj

            allowed_keys = {"type_code", "confidence", "reasoning"}
            extra_keys = set(obj.keys()) - allowed_keys
            if extra_keys:
                logger.warning(
                    "L4LLMClassifier.parse: ignoring extra keys from LLM",
                    extra={"extra_keys": sorted(extra_keys)},
                )
                raw["extra_keys_ignored"] = sorted(extra_keys)

            if "type_code" not in obj:
                raise ValueError("Missing required key: type_code")
            if "confidence" not in obj:
                raise ValueError("Missing required key: confidence")
            if "reasoning" not in obj:
                raise ValueError("Missing required key: reasoning")

            parsed_type_code, normalization_meta = self._normalize_type_code(
                obj.get("type_code"),
                allowed_types,
            )
            raw["type_code_normalization"] = normalization_meta

            raw_conf = obj.get("confidence")
            if isinstance(raw_conf, bool):
                raise ValueError("confidence must be a float, not bool")
            try:
                parsed_confidence = float(raw_conf)
            except (TypeError, ValueError):
                raise ValueError("confidence must be numeric")

            if not (0.0 <= parsed_confidence <= 1.0):
                raise ValueError("confidence must be between 0 and 1")

            raw_reasoning = obj.get("reasoning")
            if not isinstance(raw_reasoning, str):
                raise ValueError("reasoning must be a string")

            parsed_reasoning = raw_reasoning.strip()
            if not parsed_reasoning:
                raise ValueError("reasoning must be non-empty")
            if len(parsed_reasoning) > settings.CLASSIFICATION_L4_REASONING_MAX_CHARS:
                parsed_reasoning = parsed_reasoning[
                    : settings.CLASSIFICATION_L4_REASONING_MAX_CHARS
                ].rstrip()

            if parsed_type_code == "UNKNOWN":
                parsed_confidence = (
                    0.0
                    if parsed_confidence < settings.CLASSIFICATION_L4_UNKNOWN_MIN_CONFIDENCE
                    else parsed_confidence
                )

            type_code = parsed_type_code
            confidence = round(_clamp(parsed_confidence, 0.0, 1.0), 4)
            reasoning = parsed_reasoning
            parse_success = True
            raw["parse_success"] = True

        except Exception as e:
            raw.update(
                {
                    "error_type": "parse_error",
                    "error_message": str(e),
                    "parse_success": False,
                }
            )
            raw.setdefault(
                "type_code_normalization",
                {
                    "raw_type_code": (raw.get("parsed_json") or {}).get("type_code")
                    if isinstance(raw.get("parsed_json"), dict)
                    else None,
                    "normalization_strategy": "failed",
                    "matched_type_code": None,
                },
            )

            type_code = "UNKNOWN"
            confidence = 0.0
            reasoning = ""

            logger.warning(
                "L4LLMClassifier.parse failed",
                extra={
                    "error": str(e),
                    "response_preview": text[:300],
                    "allowed_types": list(allowed_types or []),
                },
            )

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

    def _normalize_type_code(
        self,
        raw_type: object,
        allowed_types: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """
        Нормализует type_code из ответа LLM.

        Стратегия:
        1. None / пустое / UNKNOWN -> UNKNOWN
        2. exact match
        3. case-insensitive exact match
        4. prefix match, только если кандидат ровно один
        5. иначе ошибка
        """
        allowed_list = list(allowed_types or [])
        allowed_set = set(allowed_list)

        meta: dict[str, Any] = {
            "raw_type_code": raw_type,
            "normalization_strategy": None,
            "matched_type_code": None,
        }

        if raw_type is None:
            meta["normalization_strategy"] = "none_to_unknown"
            meta["matched_type_code"] = "UNKNOWN"
            return "UNKNOWN", meta

        if not isinstance(raw_type, str):
            raise ValueError("type_code must be string or null")

        cleaned = raw_type.strip()
        if not cleaned or cleaned.upper() == "UNKNOWN":
            meta["normalization_strategy"] = "explicit_unknown"
            meta["matched_type_code"] = "UNKNOWN"
            return "UNKNOWN", meta

        if cleaned in allowed_set:
            meta["normalization_strategy"] = "exact"
            meta["matched_type_code"] = cleaned
            return cleaned, meta

        lower_map = {t.lower(): t for t in allowed_list}
        lowered = cleaned.lower()
        if lowered in lower_map:
            matched = lower_map[lowered]
            meta["normalization_strategy"] = "case_insensitive_exact"
            meta["matched_type_code"] = matched
            return matched, meta

        prefix_candidates = [
            t for t in allowed_list if cleaned.startswith(t) or t.startswith(cleaned)
        ]
        if len(prefix_candidates) == 1:
            matched = prefix_candidates[0]  # ← FIX: берём элемент, не список
            logger.warning(
                "L4LLMClassifier.parse: fuzzy type_code match",
                extra={"raw": cleaned, "matched": matched},
            )
            meta["normalization_strategy"] = "unique_prefix_fuzzy"
            meta["matched_type_code"] = matched
            return matched, meta
        if len(prefix_candidates) > 1:
            raise ValueError(
                f"type_code '{cleaned}' ambiguously matches multiple allowed_types: "
                f"{prefix_candidates}"
            )

        raise ValueError(f"type_code '{cleaned}' is not in allowed_types")

    def _build_prompt(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        allowed_types: list[str],
    ) -> str:
        """
        Собирает финальный промпт с ChatML-обёрткой и динамической триммацией.

        Порядок сборки:
        1. Рассчитываем бюджет токенов.
        2. Рендерим available_types_block (оптимизированный, без aliases/doc_types).
        3. Подставляем template → получаем «скелет» без document_fragment.
        4. Рассчитываем, сколько токенов осталось на document_fragment.
        5. Динамически обрезаем fragment под оставшийся бюджет.
        6. Оборачиваем в ChatML.
        """
        template = self._load_prompt_template()

        # --- Шаг 1: вычисляем бюджет ---
        n_ctx = settings.LLM_CONTEXT_LIMIT
        max_tokens_output = settings.LLM_MAX_TOKENS
        safety_margin = settings.LLM_SAFETY_MARGIN_TOKENS
        # Оставляем на промпт: весь контекст минус зарезервированное под ответ и запас
        max_prompt_tokens = n_ctx - max_tokens_output - safety_margin
        # ChatML-служебные токены (~25 токенов: теги + system_instruction)
        chatml_overhead_tokens = self._estimate_token_count(
            f"{_CHATML_IM_START}system\n{_CHATML_SYSTEM_INSTRUCTION}{_CHATML_IM_END}\n"
            f"{_CHATML_IM_START}user\n{_CHATML_IM_END}\n{_CHATML_IM_START}assistant\n"
        )

        usable_prompt_tokens = max_prompt_tokens - chatml_overhead_tokens

        # --- Шаг 2: рендерим available_types_block ---
        available_types_block = self._render_available_types(allowed_types)
        available_types_tokens = self._estimate_token_count(available_types_block)

        # --- Шаг 3: «скелет» промпта без fragment ---
        skeleton = template.replace("{available_types}", available_types_block).replace(
            "{document_fragment}", ""
        )
        skeleton_tokens = self._estimate_token_count(skeleton)

        # --- Шаг 4: бюджет на document_fragment ---
        fragment_budget_tokens = usable_prompt_tokens - skeleton_tokens
        # Минимум 300 токенов на текст документа — иначе L4 бессмысленен
        fragment_budget_tokens = max(300, fragment_budget_tokens)
        fragment_budget_chars = fragment_budget_tokens * 3  # обратное от len // 3

        # --- Шаг 5: строим fragment с динамической триммацией ---
        document_fragment = self._build_document_fragment(
            text=text,
            filename=filename,
            folder_path=folder_path,
            max_chars=fragment_budget_chars,
        )
        fragment_tokens = self._estimate_token_count(document_fragment)

        # --- Расширенное логирование бюджета ---
        logger.debug(
            "L4 prompt budget breakdown",
            extra={
                "n_ctx": n_ctx,
                "max_tokens_output": max_tokens_output,
                "safety_margin": safety_margin,
                "max_prompt_tokens": max_prompt_tokens,
                "chatml_overhead_tokens": chatml_overhead_tokens,
                "usable_prompt_tokens": usable_prompt_tokens,
                "skeleton_tokens": skeleton_tokens,
                "available_types_block_tokens": available_types_tokens,
                "fragment_budget_tokens": fragment_budget_tokens,
                "fragment_budget_chars": fragment_budget_chars,
                "fragment_actual_tokens": fragment_tokens,
                "fragment_actual_chars": len(document_fragment),
                "allowed_types_count": len(allowed_types),
            },
        )

        # --- Шаг 6: собираем user_content и оборачиваем в ChatML ---
        user_content = template.replace("{available_types}", available_types_block).replace(
            "{document_fragment}", document_fragment
        )

        prompt = self._wrap_chatml(
            system_instruction=_CHATML_SYSTEM_INSTRUCTION,
            user_content=user_content,
        )

        logger.debug(
            "L4 prompt built",
            extra={
                "prompt_len_chars": len(prompt),
                "prompt_est_tokens": self._estimate_token_count(prompt),
                "document_fragment_len": len(document_fragment),
            },
        )
        return prompt

    @staticmethod
    def _wrap_chatml(*, system_instruction: str, user_content: str) -> str:
        """
        Оборачивает промпт в ChatML-формат для Qwen2.5-Instruct и совместимых моделей.

        Структура:
            <|im_start|>system
            {system_instruction}
            <|im_end|>
            <|im_start|>user
            {user_content}
            <|im_end|>
            <|im_start|>assistant

        Открытый тег <|im_start|>assistant без закрывающего <|im_end|>
        является стандартным способом «подсказать» модели начать генерацию.
        """
        return (
            f"{_CHATML_IM_START}system\n"
            f"{system_instruction}\n"
            f"{_CHATML_IM_END}\n"
            f"{_CHATML_IM_START}user\n"
            f"{user_content}\n"
            f"{_CHATML_IM_END}\n"
            f"{_CHATML_IM_START}assistant\n"
        )

    def _load_prompt_template(self) -> str:
        """
        Загружает prompt-шаблон из пути, заданного в settings.

        Путь берётся из settings.CLASSIFICATION_L4_PROMPT_PATH.
        Кэшируется в памяти после первого чтения.
        """
        if self._prompt_template_cache:
            return self._prompt_template_cache

        path = Path(settings.CLASSIFICATION_L4_PROMPT_PATH)

        if not path.exists():
            raise FileNotFoundError(
                f"L4 prompt template not found: {path}\n"
                f"Проверь настройку CLASSIFICATION_L4_PROMPT_PATH в config.py или .env"
            )

        template = path.read_text(encoding="utf-8").strip()

        if "{available_types}" not in template:
            raise ValueError("Prompt template missing required placeholder: {available_types}")
        if "{document_fragment}" not in template:
            raise ValueError("Prompt template missing required placeholder: {document_fragment}")

        self._prompt_template_cache = template
        return template

    def _render_available_types(self, allowed_types: list[str]) -> str:
        """
        Рендерит allowed_types в компактный JSON-блок для prompt.

        Оптимизирован для малых моделей (3B): рендерит только
        type_code, name и short_desc (~35-40% меньше токенов,
        чем полный рендер с aliases/doc_types_supported/description).

        registry.get_config() вызывается в tolerant-режиме:
        сбой не прерывает L4 — тип попадает без метаданных.
        """
        rendered: list[dict[str, Any]] = []

        for type_code in allowed_types or []:
            try:
                cfg: DocumentTypeConfig | None = self.registry.get_config(type_code)
            except Exception:
                cfg = None

            if cfg is None:
                rendered.append(
                    {
                        "type_code": type_code,
                        "name": "",
                        "short_desc": "",
                    }
                )
                continue

            # Берём description как short_desc — обрезаем до первого предложения
            # или первых 150 символов (достаточно для 3B-модели)
            raw_description = str((cfg.raw or {}).get("description", "") or "").strip()
            short_desc = self._truncate_to_sentence(raw_description, max_chars=150)

            rendered.append(
                {
                    "type_code": cfg.type_code,
                    "name": cfg.name,
                    "short_desc": short_desc,
                }
            )

        return json.dumps(rendered, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _truncate_to_sentence(text: str, max_chars: int) -> str:
        """
        Обрезает текст до первого завершённого предложения в пределах max_chars.
        Если предложение не заканчивается в пределах max_chars — обрезает по символу.
        """
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        # Ищем конец первого предложения
        for sep in (".", "!", "?", "\n"):
            idx = text.find(sep)
            if 0 < idx < max_chars:
                return text[: idx + 1].strip()
        return text[:max_chars].rstrip()

    def _build_document_fragment(
        self,
        *,
        text: str,
        filename: str,
        folder_path: str,
        max_chars: int | None = None,
    ) -> str:
        """
        Строит фрагмент документа для промпта с динамической триммацией.

        max_chars: если задан — используется как бюджет (передаётся из _build_prompt).
                   Если None — fallback к settings.CLASSIFICATION_L4_MAX_INPUT_CHARS.

        Приоритет: начало документа (заголовок, предмет договора).
        """
        if max_chars is None:
            max_chars = int(getattr(settings, "CLASSIFICATION_L4_MAX_INPUT_CHARS", 6000))

        safe_text = (text or "").strip()

        prefix = (
            f"Имя файла: {filename or ''}\n"
            f"Путь к папке: {folder_path or ''}\n\n"
            f"Фрагмент текста:\n"
        )

        available_for_text = max(500, max_chars - len(prefix))
        trimmed_text = safe_text[:available_for_text]
        if len(safe_text) > available_for_text:
            trimmed_text = trimmed_text.rstrip() + "\n...[TRUNCATED]"

        return prefix + trimmed_text

    @staticmethod
    def _extract_single_json_object(text: str) -> dict[str, Any]:
        if not text:
            raise ValueError("Empty LLM response")

        stripped = text.strip()
        start_idx = stripped.find("{")
        end_idx = stripped.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            raise ValueError("No JSON object found in LLM response")

        candidate = stripped[start_idx : end_idx + 1].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        """
        Грубая эвристика оценки количества токенов в тексте.

        Для смешанного русско-английского текста:
        ~2.8-3.2 символа на токен (включая пробелы и пунктуацию).

        Это не замена реальному токенизатору, а защитная оценка
        для предотвращения переполнения контекста.
        """
        if not text:
            return 0
        return max(1, len(text) // 3)
