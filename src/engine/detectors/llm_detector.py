# src/engine/detectors/llm_detector.py

"""
LLMDetector: presence‑детектор "есть ли условие в фрагментах договора".

Высокоуровневая идея
--------------------
Этот класс отвечает за то, чтобы по выбранным чанкам текста договора
и LLM‑промпту (описанному в LLMConfig) ответить на вопрос:

  «Есть ли здесь нужное условие, и если да — где именно оно в документе?»

Результат детектора — объект DetectionResult:
- found: True / False (или False, если LLM не смог дать уверенный ответ),
- evidence_chunks: список EvidenceChunk с текстом цитаты и привязкой к chunk
  (page, clause_uid, element_ids, bbox),
- confidence: оценка уверенности LLM,
- details: служебная информация (провайдер, модель, ошибки и т.п.).

Важно: LLMDetector НЕ занимается заполнением полей structured_data
(этим занимается ExtractionLLMDetector). Его задача — именно presence‑детекция
и локация (location) в документе.

Где используется в пайплайне
----------------------------
1. HybridDetector получает:
   - список RetrievedChunk (все/топ чанки по результатам retrieval),
   - конфигурацию LLMConfig из playbook (секция llm в YAML чека).

2. HybridDetector:
   - может сначала выполнить rules‑детекцию (keywords/regex),
   - затем, при необходимости, вызывает:
       - detect() — если промпт ожидает только {context},
       - detect_with_variables() — если промпт ожидает дополнительные
         переменные (например, generic_presence.txt с
         {condition_name}, {legal_base}, {context}).

3. LLMDetector:
   - собирает текстовый контекст из чанков (_build_context),
   - подставляет переменные в промпт,
   - вызывает LLMClient с ретраями (_call_with_retries),
   - парсит ответ через LLMClient/_parse_llm_response (found/evidence/confidence),
   - пытается найти лучший chunk под evidence (_find_evidence_chunk),
   - возвращает DetectionResult с заполненным found/confidence/evidence_chunks.

Источники промпта
-----------------
Метод _resolve_prompt выбирает текст промпта по приоритету:
1. config.prompt_template (inline в playbook),
2. config.prompt_file (имя файла в каталоге prompts/),
3. DEFAULT_PROMPT_FILE ("detection/genericclause").

Для presence‑детектора в LegalMAS:
- глобальные и типовые проверки используют prompt_file
  "detection/generic_presence.txt",
  который ожидает переменные {condition_name}, {legal_base}, {context}
  и возвращает маленький JSON:
    {"found": true/false, "evidence": "...", "confidence": 0.0-1.0}.

Устойчивость и ошибки
---------------------
Класс построен так, чтобы НЕ ломать весь пайплайн при проблемах с LLM:

1) Если LLM недоступен или выключен:
   - detect*/() возвращают None (HybridDetector может опереться только на rules).

2) Если LLM вернул ошибку, timeout или невалидный ответ:
   - возвращается DetectionResult с found=False, пустыми evidence_chunks
     и подробным описанием ошибки в details (reason, error_type, error_message).

3) Для временных ошибок (TransientError):
   - _call_with_retries делегирует в client.call_with_retries() до LLM_MAX_RETRIES;
   - в details фиксируется количество попыток и последний тип ошибки.

Привязка evidence к документу
-----------------------------
Метод _build_result:
- использует response.found и response.evidence, чтобы построить EvidenceChunk;
- через _find_evidence_chunk пытается найти лучший RetrievedChunk:
  сначала по прямому вхождению evidence_text в chunk.text,
  затем по пересечению слов;
- если подходящий chunk найден, EvidenceChunk получает:
  element_id, page, clause_uid, bbox, path_titles, element_ids;
- если нет — EvidenceChunk создаётся без привязки (page=0, element_id="").

Это позволяет:
- наверху показывать юристу конкретную цитату в тексте (evidence),
- и подсвечивать её в UI на нужной странице/клаузе документа.

Важно
-----
LLMDetector — это ИМЕННО слой presence‑детекции:
- отвечает на вопрос «есть ли условие и где оно находится»,
- НЕ заполняет подробные структурные поля (это делает ExtractionLLMDetector),
- встроен в гибридную схему (rules + LLM), чтобы:
  - использовать LLM только там, где это действительно нужно,
  - и не ломать обработку документа при временных проблемах с LLM.

Правило рендеринга промптов (ВАЖНО для разработчиков)
-----------------------------------------------------
Все промпты в этом классе рендерятся ТОЛЬКО через _render_prompt().
Метод использует str.replace() — НЕ str.format().

Причина: промпты могут содержать JSON-примеры ответа с фигурными скобками,
например: {"found": true, "evidence": "..."}.
str.format() интерпретирует любые {} как Python-плейсхолдеры и бросает
KeyError на невинных JSON-ключах вроде {land_category} или {found}.
str.replace() заменяет только те строки, которые явно перечислены
в словаре переменных, и не трогает всё остальное.
"""

from __future__ import annotations

import time

from core.config import settings
from core.logging import get_logger
from engine.retrieval.tokenization import count_tokens

from ..llm.client import (
    LLMClient,
    LLMResponse,
    build_llm_telemetry_from_response,
)
from ..playbook.models import LLMConfig
from ..prompts.loader import get_promptloader
from .models import DetectionResult, EvidenceChunk, RetrievedChunk

import re

logger = get_logger(__name__)

# Нормализованная токенизация для grounding score.
# Использует \w+ вместо split() чтобы:
# - "договора." и "договора" были одним токеном
# - "покупатель," и "покупатель" совпадали
# - Работало корректно для русского и английского текста
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize_for_grounding(text: str) -> set[str]:
    """Нормализованная токенизация текста для расчёта grounding score."""
    return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}


DEFAULT_PROMPT_FILE = "detection/genericclause"

# Количество повторных попыток при временных ошибках LLM.
LLM_MAX_RETRIES = getattr(settings, "LLM_MAX_RETRIES", 2)

# Пороги grounding для evidence от LLM.
# Exact substring match → 1.0
# Token overlap / длина evidence → 0.0-1.0
# При grounding ниже GROUNDING_WARN_THRESHOLD — понижаем confidence.
# При grounding ниже GROUNDING_UNCLEAR_THRESHOLD — evidence считается ненадёжным.
_GROUNDING_WARN_THRESHOLD: float = 0.3
_GROUNDING_UNCLEAR_THRESHOLD: float = 0.1
_GROUNDING_CONFIDENCE_CAP_WEAK: float = 0.7    # cap при grounding < WARN
_GROUNDING_CONFIDENCE_CAP_VERY_WEAK: float = 0.5  # cap при grounding < UNCLEAR



# Все переменные, которые LLMDetector умеет подставлять в промпты.
# Если нужно добавить новую переменную — добавь её сюда и передавай
# в extra_variables при вызове detect_with_variables().
# ВАЖНО: ключи должны быть в формате "{имя_переменной}" — с фигурными скобками.
_KNOWN_PROMPT_VARIABLES = {
    "{context}",
    "{condition_name}",
    "{legal_base}",
    "{doc_type}",
    "{check_name}",
    "{classification_confidence}",
}


class LLMDetector:
    """LLM-based detector for checks described by LLMConfig."""

    def __init__(self, client: LLMClient | None = None) -> None:
        # client: обёртка над конкретным провайдером (OpenAI / Ollama / llamacpp)
        self.client = client or LLMClient()
        self.promptloader = get_promptloader()

    # ------------------------------------------------------------------
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ------------------------------------------------------------------

    def detect(
        self,
        config: LLMConfig,
        chunks: list[RetrievedChunk],
        use_sanitized: bool = True,
    ) -> DetectionResult | None:
        """
        Запустить LLM-детекцию по списку чанков.
        """
        if not self.client.is_available():
            logger.debug("LLMDetector: LLM not available, skipping LLM detection")
            return None

        prompt_template = self._resolve_prompt(config)
        if not prompt_template:
            logger.debug("LLMDetector: no prompt available for LLM detection")
            return None

        if not chunks:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "no_chunks_for_context",
                    "error_type": "no_context",
                },
            )

        context_k = config.context_k if hasattr(config, "context_k") else 5
        context_chunks = chunks[: max(1, context_k)]

        # Считаем бюджет под контекст: окно - резерв под output - safety - шаблон промпта.
        # В detect() нет extra_variables — только {context}, поэтому template уже финальный.
        _template_tokens = count_tokens(prompt_template)

        logger.debug(
            "LLMDetector.detect: template tokens calculated",
            template_tokens=_template_tokens,
        )

        _max_out = int(config.max_tokens or settings.LLM_MAX_TOKENS)
        _limit = int(getattr(settings, "LLM_CONTEXT_LIMIT", 0) or 0)
        if _limit > 0:
            _context_budget = (
                _limit
                - _max_out
                - int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 512))
                - _template_tokens
            )
            _context_budget = max(200, _context_budget)
            context_text = self._fit_context_to_budget(context_chunks, _context_budget)
        else:
            context_text = self._build_context(context_chunks)

        # Рендерим промпт через безопасный _render_prompt().
        prompt, render_error = self._render_prompt(
            template=prompt_template,
            variables={"{context}": context_text},
        )

        if render_error:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "prompt_format_error",
                    "error_type": "prompt_format_error",
                    "error_message": render_error,
                },
            )

        llm_started_at = time.time()
        response, error_details = self._call_with_retries(
            prompt=prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        llm_duration_ms = int((time.time() - llm_started_at) * 1000)

        if response is None:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": self._classify_error_reason(error_details),
                    "duration_ms": llm_duration_ms,
                    **error_details,
                },
            )

        telemetry = build_llm_telemetry_from_response(
            response,
            duration_ms=llm_duration_ms,
            llm_attempts=error_details.get("llm_attempts"),
        )

        base_result = self._build_result(response, context_chunks)
        base_result.details.update(telemetry)
        base_result.details.update(error_details)
        return base_result

    def detect_with_variables(
        self,
        config: LLMConfig,
        chunks: list[RetrievedChunk],
        extra_variables: dict[str, object],
    ) -> DetectionResult | None:
        """
        Вариант detect, когда промпт ожидает дополнительные переменные.
        """
        if not self.client.is_available():
            logger.debug("LLMDetector: LLM not available, skipping detect_with_variables")
            return None

        prompt_template = self._resolve_prompt(config)
        if not prompt_template:
            logger.debug("LLMDetector: no prompt available for detect_with_variables")
            return None

        if not chunks:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "no_chunks_for_context",
                    "error_type": "no_context",
                },
            )

        context_k = config.context_k if hasattr(config, "context_k") else 5
        context_chunks = chunks[: max(1, context_k)]

        # Собираем все переменные ДО расчёта template_tokens
        variables: dict[str, str] = {"{context}": ""}  # Пустой context для расчёта template
        for key, value in extra_variables.items():
            normalized_key = key if key.startswith("{") else f"{{{key}}}"
            variables[normalized_key] = str(value) if value is not None else ""

        # Рендерим template со ВСЕМИ переменными кроме {context}
        template_only_vars = {k: v for k, v in variables.items() if k != "{context}"}
        template_rendered_no_context, _ = self._render_prompt(prompt_template, template_only_vars)
        _template_tokens = count_tokens(template_rendered_no_context)

        logger.debug(
            "LLMDetector.detect_with_variables: template tokens calculated",
            template_tokens=_template_tokens,
            variables_count=len(template_only_vars),
        )

        # Считаем бюджет под контекст
        _max_out = int(config.max_tokens or settings.LLM_MAX_TOKENS)
        _limit = int(getattr(settings, "LLM_CONTEXT_LIMIT", 0) or 0)
        if _limit > 0:
            _context_budget = (
                _limit
                - _max_out
                - int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 512))
                - _template_tokens
            )
            _context_budget = max(200, _context_budget)
            context_text = self._fit_context_to_budget(context_chunks, _context_budget)
        else:
            context_text = self._build_context(context_chunks)

        # Обновляем {context} в variables реальным текстом
        variables["{context}"] = context_text

        # Рендерим финальный prompt
        prompt, render_error = self._render_prompt(
            template=prompt_template,
            variables=variables,
        )

        if render_error:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "prompt_format_error",
                    "error_type": "prompt_format_error",
                    "error_message": render_error,
                },
            )

        llm_started_at = time.time()
        response, error_details = self._call_with_retries(
            prompt=prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        llm_duration_ms = int((time.time() - llm_started_at) * 1000)

        if response is None:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": self._classify_error_reason(error_details),
                    "duration_ms": llm_duration_ms,
                    **error_details,
                },
            )

        telemetry = build_llm_telemetry_from_response(
            response,
            duration_ms=llm_duration_ms,
            llm_attempts=error_details.get("llm_attempts"),
        )

        base_result = self._build_result(response, context_chunks)
        base_result.details.update(telemetry)
        base_result.details.update(error_details)
        return base_result

    # ------------------------------------------------------------------
    # ВНУТРЕННИЕ ХЕЛПЕРЫ: РЕНДЕРИНГ ПРОМПТА
    # ------------------------------------------------------------------

    @staticmethod
    def _render_prompt(
        template: str,
        variables: dict[str, str],
    ) -> tuple[str, str | None]:
        """
        Безопасно подставить переменные в шаблон промпта.

        Возвращает кортеж: (готовый промпт, текст ошибки или None).

        Почему str.replace(), а не str.format():
        - Промпты часто содержат JSON-примеры ответа с фигурными скобками,
          например: {"found": true, "land_category": "не найдено"}.
        - str.format() видит {land_category} как Python-плейсхолдер
          и бросает KeyError, хотя это просто часть JSON-примера.
        - str.replace() заменяет ровно те строки, которые перечислены
          в словаре variables, и не трогает ничего остального.

        Для непрофессионального программиста:
        - Представь, что в промпте написано:
            "Ответь в формате: {found: true, land_category: 'земли ИЖС'}"
        - str.format() попытается найти переменные found и land_category
          в твоём коде и упадёт с ошибкой, потому что их нет.
        - str.replace() просто ищет подстроку "{context}" и заменяет её
          на текст договора — и больше ничего не трогает.
        """
        try:
            result = template
            for placeholder, value in variables.items():
                result = result.replace(placeholder, value)
            return result, None
        except Exception as e:
            return template, str(e)

    # ------------------------------------------------------------------
    # ВНУТРЕННИЕ ХЕЛПЕРЫ: КЛАССИФИКАЦИЯ ОШИБОК
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_error_reason(error_details: dict) -> str:
        """
        Преобразовать технический error_type из _call_with_retries
        в человекочитаемый reason для details DetectionResult.

        Вынесено в отдельный метод, чтобы не дублировать одинаковые
        блоки if/elif в detect() и detect_with_variables().
        """
        error_type = error_details.get("error_type")
        error_message = (error_details.get("error_message") or "").lower()

        if error_type == "context_limit":
            return "llm_context_limit_exceeded"
        if error_type == "permanent_error":
            # Fallback для случаев, когда context_limit пришёл как permanent_error
            # от старого кода без LLMContextLimitError.
            if "context limit" in error_message or "token budget" in error_message:
                return "llm_token_budget_exceeded"
            if "insufficient output token budget" in error_message:
                return "llm_insufficient_output_budget"
            return "llm_permanent_error"
        if error_type == "unavailable":
            return "llm_unavailable"
        if error_type == "transient_error":
            return "llm_transient_error"
        return "llm_call_failed"

    # ------------------------------------------------------------------
    # ВНУТРЕННИЕ ХЕЛПЕРЫ: ВЫЗОВ LLM, ПОСТРОЕНИЕ РЕЗУЛЬТАТА
    # ------------------------------------------------------------------

    def _call_with_retries(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызвать LLM с несколькими попытками при временных ошибках.

        Делегирует retry-логику в LLMClient.call_with_retries(), чтобы:
        - не дублировать обработку TransientError / PermanentError;
        - корректно получать error_type='context_limit' из LLMContextLimitError,
        который LLMClient ловит отдельным блоком перед PermanentError.

        Возвращает кортеж:
        - LLMResponse или None (если все попытки неудачны);
        - словарь error_details для details DetectionResult.
        """
        response, error_details = self.client.call_with_retries(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=LLM_MAX_RETRIES,
        )
        return response, error_details

    def _resolve_prompt(self, config: LLMConfig) -> str | None:
        """
        Выбрать источник промпта по приоритету:
        1. config.prompt_template (inline)
        2. config.prompt_file (имя файла в prompts/)
        3. DEFAULT_PROMPT_FILE
        """
        if getattr(config, "prompt_template", None):
            return config.prompt_template

        prompt_file = getattr(config, "prompt_file", None)
        if prompt_file:
            if self.promptloader.exists(prompt_file):
                try:
                    return self.promptloader.load_raw(prompt_file)
                except Exception as e:
                    logger.warning(
                        "LLMDetector: failed to load prompt file, falling back",
                        prompt_file=prompt_file,
                        error=str(e),
                    )
            else:
                logger.warning(
                    "LLMDetector: prompt file not found, falling back to default",
                    prompt_file=prompt_file,
                    available=self.promptloader.list_prompts("detection"),
                )

        try:
            return self.promptloader.load_raw(DEFAULT_PROMPT_FILE)
        except FileNotFoundError:
            logger.error(
                "LLMDetector: default prompt file not found",
                path=DEFAULT_PROMPT_FILE,
            )
            return None

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        """
        Построить текст контекста для LLM из чанков.

        Формат: пронумерованные части с указанием страницы/клаузы.

        Для непрофессионального программиста:
        - Иногда сюда могут прилетать не объекты, а обычные dict.
        - Мы аккуратно читаем нужные поля в обоих случаях, чтобы
          не падать с ошибкой и не ломать весь пайплайн.
        """
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            if isinstance(chunk, dict):
                page = chunk.get("page", 0)
                clause_uid = chunk.get("clause_uid") or ""
                text = chunk.get("text", "")
            else:
                page = getattr(chunk, "page", 0)
                # Показываем LLM только raw_uid (человекочитаемый "5.2"),
                # не полный effective_uid ("main_contract:5.2").
                # effective_uid используется для anchor, а не для LLM промпта.
                _full_clause_uid = getattr(chunk, "clause_uid", "") or ""
                clause_uid = (
                    _full_clause_uid.split(":")[-1] if ":" in _full_clause_uid else _full_clause_uid
                )
                text = getattr(chunk, "text", "")

            clause_info = f" [clause {clause_uid}]" if clause_uid else ""
            header = f"[{i}] page {page}{clause_info}:"
            parts.append(f"{header}\n{text}\n")

        return "\n".join(parts)

    @staticmethod
    def _fit_context_to_budget(
        chunks: list[RetrievedChunk],
        token_budget: int,
    ) -> str:
        """
        Собрать контекст из чанков, не превышая token_budget токенов.

        Берём чанки по одному пока бюджет позволяет.
        Если первый чанк уже превышает бюджет — берём его обрезанным,
        чтобы LLM всегда получал хоть что-то.

        token_budget считается через count_tokens (слова × 2.5).
        """
        from engine.retrieval.tokenization import count_tokens

        parts: list[str] = []
        used = 0

        for i, chunk in enumerate(chunks, start=1):
            if isinstance(chunk, dict):
                page = chunk.get("page", 0)
                clause_uid = chunk.get("clause_uid") or ""
                text = chunk.get("text", "")
            else:
                page = getattr(chunk, "page", 0)
                # Показываем LLM только raw_uid (человекочитаемый "5.2"),
                # не полный effective_uid ("main_contract:5.2").
                # effective_uid используется для anchor, а не для LLM промпта.
                _full_clause_uid = getattr(chunk, "clause_uid", "") or ""
                clause_uid = (
                    _full_clause_uid.split(":")[-1] if ":" in _full_clause_uid else _full_clause_uid
                )
                text = getattr(chunk, "text", "")

            clause_info = f" [clause {clause_uid}]" if clause_uid else ""
            header = f"[{i}] page {page}{clause_info}:"
            entry = f"{header}\n{text}\n"
            entry_tokens = count_tokens(entry)

            if used + entry_tokens > token_budget:
                if not parts:
                    # Первый чанк не вмещается целиком — берём обрезанный.
                    # Грубая обрезка по словам: token_budget / 2.5 слов.
                    max_words = max(50, int(token_budget / 2.5))
                    words = text.split()
                    truncated = " ".join(words[:max_words])
                    parts.append(f"{header}\n{truncated}\n[...обрезано]\n")
                break

            parts.append(entry)
            used += entry_tokens

        logger.info(
            "LLMDetector: context fitted to budget",
            original_chunks=len(chunks),
            kept_chunks=len(parts),
            dropped_chunks=len(chunks) - len(parts),
            used_tokens=used,
            budget_tokens=token_budget,
            utilization=f"{100 * used / token_budget:.1f}%",
        )

        return "\n".join(parts)

    def _build_result(
        self,
        response: LLMResponse,
        context_chunks: list[RetrievedChunk],
    ) -> DetectionResult:
        """
        Превратить LLMResponse в DetectionResult с grounding-проверкой evidence.

        Grounding-логика (порядок применения):
        1. Рассчитываем grounding_score для evidence из LLM.
        2. Если grounding < UNCLEAR_THRESHOLD (0.1) — evidence почти наверняка
           hallucinated: гасим found=False, confidence cap до 0.5.
        3. Если grounding < WARN_THRESHOLD (0.3) — слабое grounding:
           confidence cap до 0.7, anchor в UI не проставляем.
        4. Если grounding >= WARN_THRESHOLD — evidence достаточно заземлён:
           confidence не трогаем, ищем лучший chunk для anchor.

        Это предотвращает попадание LLM-галлюцинаций в risk findings
        и ложную привязку несуществующих цитат к страницам документа.
        """
        evidence_chunks: list[EvidenceChunk] = []

        # --- Шаг 1: Grounding score ---
        # Рассчитываем ДО любых решений по found/confidence/anchor.
        # grounding_score = 0.0 когда found=False или evidence пустой —
        # в этом случае он не влияет на результат.
        grounding_score: float = 0.0
        raw_found = bool(response.found) if response.found is not None else False

        if raw_found and response.evidence:
            grounding_score = self._calculate_grounding_score(
                response.evidence, context_chunks
            )

        # --- Шаг 2: adjusted_found ---
        # Если grounding очень слабый — evidence почти наверняка hallucinated.
        # Гасим found, чтобы это не стало полноценным fail в executor.
        # Порог _GROUNDING_UNCLEAR_THRESHOLD (0.1): менее 10% слов evidence
        # встречается в реальном тексте — это не цитата, это выдумка.
        if raw_found and response.evidence and grounding_score < _GROUNDING_UNCLEAR_THRESHOLD:
            adjusted_found = False
            logger.debug(
                "LLMDetector._build_result: evidence suppressed due to very low grounding",
                extra={
                    "grounding_score": grounding_score,
                    "threshold": _GROUNDING_UNCLEAR_THRESHOLD,
                    "evidence_preview": (response.evidence or "")[:100],
                },
            )
        else:
            adjusted_found = raw_found

        # --- Шаг 3: adjusted_confidence ---
        # Корректируем confidence на основе grounding.
        # Если evidence найдено, но слабо заземлено — понижаем cap.
        # Если found был suppressed (adjusted_found=False) — confidence
        # понижается независимо, но это не критично т.к. found=False.
        raw_confidence = response.confidence if response.confidence is not None else 0.0

        if raw_found and response.evidence:
            if grounding_score < _GROUNDING_UNCLEAR_THRESHOLD:
                adjusted_confidence = min(raw_confidence, _GROUNDING_CONFIDENCE_CAP_VERY_WEAK)
            elif grounding_score < _GROUNDING_WARN_THRESHOLD:
                adjusted_confidence = min(raw_confidence, _GROUNDING_CONFIDENCE_CAP_WEAK)
            else:
                adjusted_confidence = raw_confidence
        else:
            adjusted_confidence = raw_confidence

        # --- Шаг 4: EvidenceChunk с защитой anchor ---
        # Якорим в документ (page/element_id/clause_uid) ТОЛЬКО если:
        # - adjusted_found=True (evidence не suppressed)
        # - grounding >= WARN_THRESHOLD (evidence достаточно заземлён)
        # При слабом grounding — EvidenceChunk создаётся без anchor,
        # чтобы UI не показывал ложную ссылку на страницу/клаузу.
        if adjusted_found and response.evidence:
            # Ищем chunk для anchor только при достаточном grounding
            best_chunk = None
            if grounding_score >= _GROUNDING_WARN_THRESHOLD:
                best_chunk = self._find_evidence_chunk(response.evidence, context_chunks)

            if best_chunk:
                # Хорошее grounding + найден matching chunk → полный anchor
                evidence_chunks.append(
                    EvidenceChunk(
                        element_id=best_chunk.element_id,
                        text=response.evidence[:500],
                        page=best_chunk.page,
                        clause_uid=best_chunk.clause_uid or response.clause,
                        bbox=best_chunk.bbox,
                        score=best_chunk.combined_score,
                        path_titles=list(best_chunk.path_titles or []),
                        start_page=best_chunk.start_page,
                        end_page=best_chunk.end_page,
                        element_ids=list(best_chunk.element_ids or []),
                    )
                )
            else:
                # Слабый grounding или chunk не найден → evidence без anchor.
                # page=0, element_id="" сигнализируют UI что привязки нет.
                evidence_chunks.append(
                    EvidenceChunk(
                        element_id="",
                        text=response.evidence[:500],
                        page=0,
                        clause_uid=response.clause,
                        bbox=[],
                        score=0.0,
                        path_titles=[],
                        start_page=None,
                        end_page=None,
                        element_ids=[],
                    )
                )

        try:
            logger.debug(
                "LLMDetector._build_result",
                extra={
                    "raw_found": raw_found,
                    "adjusted_found": adjusted_found,
                    "grounding_score": grounding_score,
                    "adjusted_confidence": adjusted_confidence,
                    "evidence_preview": (response.evidence or "")[:200],
                    "clause": response.clause,
                    "context_chunks_count": len(context_chunks),
                    "evidence_chunks_count": len(evidence_chunks),
                    "best_chunk_element_id": (
                        evidence_chunks[0].element_id if evidence_chunks else None
                    ),
                    "best_chunk_page": (
                        evidence_chunks[0].page if evidence_chunks else None
                    ),
                    "best_chunk_clause_uid": (
                        evidence_chunks[0].clause_uid if evidence_chunks else None
                    ),
                    "best_chunk_start_page": (
                        evidence_chunks[0].start_page if evidence_chunks else None
                    ),
                    "best_chunk_end_page": (
                        evidence_chunks[0].end_page if evidence_chunks else None
                    ),
                    "best_chunk_element_ids": (
                        evidence_chunks[0].element_ids if evidence_chunks else None
                    ),
                },
            )
        except Exception:
            logger.debug("LLMDetector._build_result: debug logging failed")

        return DetectionResult(
            found=adjusted_found,
            evidence_chunks=evidence_chunks,
            confidence=adjusted_confidence,
            detector_type="llm",
            details={
                "provider": response.provider,
                "model": response.model,
                "tokens_used": response.tokens_used,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "parse_success": response.parse_success,
                "llm_clause": response.clause,
                "reason": getattr(response, "reasoning", None),
                "raw_response": response.raw_response,
                # Grounding metadata — используется downstream в extraction.py
                # для решения: брать detection["evidence"] или fallback на contexts.
                # evidence_grounded=True означает grounding >= WARN_THRESHOLD (0.3).
                "grounding_score": grounding_score,
                "evidence_grounded": grounding_score >= _GROUNDING_WARN_THRESHOLD,
                # raw_found для диагностики: было ли found до grounding-коррекции
                "raw_found_before_grounding": raw_found,
            },
        )

    @staticmethod
    def _find_evidence_chunk(
        evidence_text: str,
        chunks: list[RetrievedChunk],
    ) -> RetrievedChunk | None:
        """
        Найти chunk, который лучше всего соответствует evidence_text.

        Сначала пробуем прямое вхождение, потом по пересечению слов.
        """
        evidence_lower = evidence_text.lower()[:100]

        logger.debug(
            "LLMDetector._find_evidence_chunk.start",
            extra={
                "evidence_preview": evidence_lower,
                "chunks_count": len(chunks),
            },
        )

        if not evidence_lower.strip():
            logger.debug(
                "LLMDetector._find_evidence_chunk.empty_evidence",
                extra={"evidence_preview": evidence_lower},
            )
            return None

        # 1. Прямое вхождение
        for chunk in chunks:
            if evidence_lower in chunk.text.lower():
                logger.debug(
                    "LLMDetector._find_evidence_chunk.direct_match",
                    extra={
                        "chunk_element_id": getattr(chunk, "element_id", None),
                        "chunk_page": getattr(chunk, "page", None),
                        "chunk_clause_uid": getattr(chunk, "clause_uid", None),
                    },
                )
                return chunk

        # 2. Пересечение слов
        evidence_words = set(evidence_lower.split())
        best_chunk: RetrievedChunk | None = None
        best_overlap = 0

        for chunk in chunks:
            chunk_words = set(chunk.text.lower().split())
            overlap = len(evidence_words & chunk_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_chunk = chunk

        logger.debug(
            "LLMDetector._find_evidence_chunk.overlap_result",
            extra={
                "best_overlap": best_overlap,
                "best_chunk_element_id": getattr(best_chunk, "element_id", None)
                if best_chunk
                else None,
                "best_chunk_page": getattr(best_chunk, "page", None) if best_chunk else None,
                "best_chunk_clause_uid": getattr(best_chunk, "clause_uid", None)
                if best_chunk
                else None,
            },
        )

        return best_chunk if best_overlap >= 3 else None

    @staticmethod
    def _calculate_grounding_score(
        evidence_text: str,
        chunks: list[RetrievedChunk],
    ) -> float:
        """
        Рассчитать насколько evidence_text заземлён в реальном тексте чанков.

        Возвращает float от 0.0 до 1.0:
        - 1.0 — точное вхождение evidence в один из чанков (substring match)
        - 0.5-0.99 — сильное пересечение нормализованных токенов
        - 0.1-0.49 — слабое пересечение токенов
        - 0.0 — нет совпадений или evidence пустой

        Алгоритм:
        1. Exact substring match → 1.0 (самый надёжный сигнал)
        2. Нормализованный token overlap: overlap / len(evidence_tokens)
           Нормируем по числу токенов evidence, чтобы
           короткие evidence с несколькими общими словами не давали
           ложно высокий score.
           Используем _tokenize_for_grounding() а не split() чтобы
           "договора." и "договора" считались одним токеном.
        """
        if not evidence_text or not chunks:
            return 0.0

        evidence_lower = evidence_text.lower().strip()
        if not evidence_lower:
            return 0.0

        # 1. Exact substring match → максимальный score
        for chunk in chunks:
            chunk_text = chunk.text.lower() if hasattr(chunk, "text") else ""
            if evidence_lower in chunk_text:
                return 1.0

        # 2. Нормализованный token overlap ratio
        evidence_tokens = _tokenize_for_grounding(evidence_text)
        if not evidence_tokens:
            return 0.0

        best_ratio = 0.0
        for chunk in chunks:
            chunk_tokens = _tokenize_for_grounding(
                chunk.text if hasattr(chunk, "text") else ""
            )
            if not chunk_tokens:
                continue
            overlap = len(evidence_tokens & chunk_tokens)
            # Нормируем по длине evidence: насколько evidence покрыт реальным текстом
            ratio = overlap / len(evidence_tokens)
            if ratio > best_ratio:
                best_ratio = ratio

        return round(min(1.0, best_ratio), 4)




