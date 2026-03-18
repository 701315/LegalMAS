# src/engine/detectors/llm_detector.py

"""
LLM-based detector for complex checks.

Задача этого класса — аккуратно вызвать LLM для проверки условия
и вернуть результат в виде DetectionResult.

Важно понимать несколько принципов:

1) Не ломаем весь пайплайн из-за ошибки LLM.
   - Если LLM недоступен, упал по timeout или вернул некорректный ответ,
     мы НЕ выбрасываем исключение наружу.
   - Вместо этого мы либо:
       а) возвращаем DetectionResult с found=False и подробным описанием
          ошибки в details;
       б) или, если совсем нечем работать (нет промпта/чанков) — None,
          чтобы HybridDetector мог честно остаться на rules.

2) Добавляем простые ретраи для временных ошибок (TransientError).
   - Пробуем несколько раз вызвать LLM.
   - Если все попытки неудачны, пишем в details, сколько было попыток
     и какой тип ошибки произошёл.

3) Детали для последующей аналитики:
   - В details детектора попадает:
       provider, model, tokens_used (если известны),
       parse_success,
       error_type (timeout, rate_limit, network, server_error, parse_failed и т.п.),
       error_message (короткое описание ошибки),
       last_exception (опционально, для дебага).
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from core.config import settings
from core.exceptions import TransientError, PermanentError
from .models import DetectionResult, EvidenceChunk, RetrievedChunk
from ..llm.client import LLMClient, LLMResponse
from ..playbook.models import LLMConfig
from ..prompts.loader import get_promptloader

logger = get_logger(__name__)


DEFAULT_PROMPT_FILE = "detection/genericclause"

# Количество повторных попыток при временных ошибках LLM.
LLM_MAX_RETRIES = getattr(settings, "LLM_MAX_RETRIES", 2)


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
        use_sanitized: bool = True,  # зарезервировано на будущее (PII)
    ) -> DetectionResult | None:
        """
        Запустить LLM-детекцию по списку чанков.

        Возвращает:
        - DetectionResult: если удалось построить осмысленный результат
          (даже если LLM дал ошибку — мы всё равно описываем её в details).
        - None: только если совсем невозможно запустить LLM (нет провайдера,
          нет промпта, нет чанков). В этом случае HybridDetector останется
          на правилах (rules_only).
        """
        if not self.client.is_available():
            logger.debug("LLMDetector: LLM not available, skipping LLM detection")
            return None

        prompt_template = self._resolve_prompt(config)
        if not prompt_template:
            logger.debug("LLMDetector: no prompt available for LLM detection")
            return None

        if not chunks:
            # Чанков нет — считаем, что LLM нечего анализировать.
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
        context_text = self._build_context(context_chunks)

        # Простой шаблон: заменяем {context} в тексте промпта.
        try:
            prompt = prompt_template.replace("{context}", context_text)
        except Exception as e:
            logger.warning(
                "LLMDetector: prompt formatting failed in detect()",
                error=str(e),
            )
            # Здесь тоже можно вернуть "честный" DetectionResult с ошибкой.
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "prompt_format_error",
                    "error_type": "prompt_format_error",
                    "error_message": str(e),
                },
            )

        # Вызов LLM с ретраями и аккуратной обработкой ошибок.
        response, error_details = self._call_with_retries(
            prompt=prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        if response is None:
            # LLM не дал ответа даже после ретраев — возвращаем DetectionResult
            # с описанием ошибки, чтобы верхний уровень мог показать "unclear".
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "llm_call_failed",
                    **error_details,
                },
            )

        # Успешный ответ от LLM → строим DetectionResult, добавив туда детали вызова.
        base_result = self._build_result(response, context_chunks)
        # Дополняем details служебной информацией о вызове
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

        Например, genericpresence.txt с плейсхолдерами:
          {condition_name}, {legal_base}, {context}
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
        context_text = self._build_context(context_chunks)

        try:
            variables: dict[str, Any] = {"context": context_text, **extra_variables}
            prompt = prompt_template.format(**variables)
        except KeyError as e:
            logger.warning(
                "LLMDetector: missing variable in prompt template",
                variable=str(e),
                prompt_source=(
                    config.prompt_template or config.prompt_file or DEFAULT_PROMPT_FILE
                ),
            )
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "prompt_variable_missing",
                    "error_type": "prompt_variable_missing",
                    "missing_variable": str(e),
                },
            )
        except Exception as e:
            logger.warning(
                "LLMDetector: prompt formatting failed in detect_with_variables()",
                error=str(e),
            )
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "prompt_format_error",
                    "error_type": "prompt_format_error",
                    "error_message": str(e),
                },
            )

        response, error_details = self._call_with_retries(
            prompt=prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        if response is None:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": "llm_call_failed",
                    **error_details,
                },
            )

        base_result = self._build_result(response, context_chunks)
        base_result.details.update(error_details)
        return base_result

    # ------------------------------------------------------------------
    # ВНУТРЕННИЕ ХЕЛПЕРЫ: ВЫБОР ПРОМПТА, ВЫЗОВ LLM, ПОСТРОЕНИЕ РЕЗУЛЬТАТА
    # ------------------------------------------------------------------

    def _call_with_retries(
        self,
        prompt: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызвать LLM с несколькими попытками при временных ошибках.

        Возвращает кортеж:
        - LLMResponse или None (если все попытки неудачны);
        - словарь error_details, который можно положить в details DetectionResult.

        Логика:
        - Если получили TransientError (timeout, сеть, 5xx и т.п.) —
          пробуем ещё несколько раз.
        - При PermanentError (неправильный ключ, неверный запрос) —
          сразу выходим без ретраев.
        - Любая другая неожиданная ошибка логируется и возвращается как
          error_type="unexpected_error".
        """
        attempts = 0
        last_error_type = None
        last_error_message = None

        while attempts <= LLM_MAX_RETRIES:
            try:
                attempts += 1
                response = self.client.call(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # None здесь означает, что клиент сам решил "ничего не делать"
                # (например, провайдер выключен). Это не ошибка, просто отсутствие ответа.
                return response, {
                    "llm_attempts": attempts,
                    "error_type": None,
                    "error_message": None,
                }
            except TransientError as e:
                # Временная ошибка — можно попробовать ещё раз.
                last_error_type = "transient_error"
                last_error_message = str(e)
                logger.warning(
                    "LLMDetector: transient LLM error, will retry",
                    error=str(e),
                    attempt=attempts,
                    max_retries=LLM_MAX_RETRIES,
                )
                if attempts > LLM_MAX_RETRIES:
                    break
                continue
            except PermanentError as e:
                # Неисправимая ошибка — ретраи бессмысленны.
                last_error_type = "permanent_error"
                last_error_message = str(e)
                logger.warning(
                    "LLMDetector: permanent LLM error, no retries",
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }
            except Exception as e:
                # Любая другая неожиданная ошибка клиента
                last_error_type = "unexpected_error"
                last_error_message = str(e)
                logger.error(
                    "LLMDetector: unexpected exception from LLM client",
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }

        # Сюда попадаем, если все ретраи по TransientError исчерпаны.
        return None, {
            "llm_attempts": attempts,
            "error_type": last_error_type or "transient_error",
            "error_message": last_error_message,
        }

    def _resolve_prompt(self, config: LLMConfig) -> str | None:
        """
        Выбрать источник промпта по приоритету:
        1. config.prompt_template (inline)
        2. config.prompt_file (имя файла в prompts/)
        3. DEFAULT_PROMPT_FILE
        """
        # 1. Inline template
        if getattr(config, "prompt_template", None):
            return config.prompt_template

        # 2. prompt_file из конфигурации
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

        # 3. Файл по умолчанию
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
        Юристу это не видно напрямую, но делает ответы LLM более точными.

        Для непрофессионального программиста:
        - Иногда сюда могут прилетать не объекты, а обычные dict.
        - Мы аккуратно читаем нужные поля в обоих случаях, чтобы
          не падать с ошибкой и не ломать весь пайплайн.
        """
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            # Унифицированный доступ к полям и для объектов, и для dict
            if isinstance(chunk, dict):
                page = chunk.get("page", 0)
                clause_uid = chunk.get("clause_uid") or ""
                text = chunk.get("text", "")
            else:
                page = getattr(chunk, "page", 0)
                clause_uid = getattr(chunk, "clause_uid", "") or ""
                text = getattr(chunk, "text", "")

            clause_info = f" [clause {clause_uid}]" if clause_uid else ""
            header = f"[{i}] page {page}{clause_info}:"
            parts.append(f"{header}\n{text}\n")

        return "\n".join(parts)


    def _build_result(
        self,
        response: LLMResponse,
        context_chunks: list[RetrievedChunk],
    ) -> DetectionResult:
        """
        Превратить LLMResponse в DetectionResult.

        Если LLM дал текст evidence, пытаемся найти подходящий chunk,
        иначе создаём evidence без привязки к конкретному элементу документа.
        """
        evidence_chunks: list[EvidenceChunk] = []

        if response.found and response.evidence:
            best_chunk = self._find_evidence_chunk(response.evidence, context_chunks)
            if best_chunk:
                evidence_chunks.append(
                    EvidenceChunk(
                        element_id=best_chunk.element_id,
                        text=response.evidence[:500],
                        page=best_chunk.page,
                        clause_uid=response.clause or best_chunk.clause_uid,
                        bbox=best_chunk.bbox,
                        score=best_chunk.combined_score,
                    )
                )
            else:
                evidence_chunks.append(
                    EvidenceChunk(
                        element_id="",
                        text=response.evidence[:500],
                        page=0,
                        clause_uid=response.clause,
                        bbox=[],
                        score=0.0,
                    )
                )

        return DetectionResult(
            found=bool(response.found) if response.found is not None else False,
            evidence_chunks=evidence_chunks,
            confidence=response.confidence,
            detector_type="llm",
            details={
                "provider": response.provider,
                "model": response.model,
                "tokens_used": response.tokens_used,
                "parse_success": response.parse_success,
                "llm_clause": response.clause,
                "reason": getattr(response, "reasoning", None),
                "raw_response": response.raw_response,
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
        evidence_lower = evidence_text.lower()[:100]  # ограничим длину
        if not evidence_lower.strip():
            return None

        # 1. Прямое вхождение
        for chunk in chunks:
            if evidence_lower in chunk.text.lower():
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

        return best_chunk if best_overlap >= 3 else None
