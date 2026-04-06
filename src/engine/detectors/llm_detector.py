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
   - _call_with_retries выполняет несколько попыток до LLM_MAX_RETRIES;
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
            error_type = error_details.get("error_type")
            error_message = (error_details.get("error_message") or "").lower()

            # Специализация для budget‑ошибок и недоступного провайдера
            if error_type == "permanent_error":
                if "context limit" in error_message or "token budget" in error_message:
                    reason = "llm_token_budget_exceeded"
                elif "insufficient output token budget" in error_message:
                    reason = "llm_insufficient_output_budget"
                else:
                    reason = "llm_permanent_error"
            elif error_type == "unavailable":
                reason = "llm_unavailable"
            elif error_type == "transient_error":
                reason = "llm_transient_error"
            else:
                reason = "llm_call_failed"

            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": reason,
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
            error_type = error_details.get("error_type")
            error_message = (error_details.get("error_message") or "").lower()

            # Специализация для budget‑ошибок и недоступного провайдера
            if error_type == "permanent_error":
                if "context limit" in error_message or "token budget" in error_message:
                    reason = "llm_token_budget_exceeded"
                elif "insufficient output token budget" in error_message:
                    reason = "llm_insufficient_output_budget"
                else:
                    reason = "llm_permanent_error"
            elif error_type == "unavailable":
                reason = "llm_unavailable"
            elif error_type == "transient_error":
                reason = "llm_transient_error"
            else:
                reason = "llm_call_failed"

            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={
                    "reason": reason,
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
                # None здесь означает, что LLMClient вернул "пустой" ответ
                # (например, провайдер выключен на уровне конфигурации),
                # но без исключения. Для детектора это эквивалентно
                # отсутствию ответа от LLM.
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
                # Берём структурный контекст из RetrievedChunk
                evidence_chunks.append(
                    EvidenceChunk(
                        element_id=best_chunk.element_id,
                        text=response.evidence[:500],
                        page=best_chunk.page,
                        clause_uid=response.clause or best_chunk.clause_uid,
                        bbox=best_chunk.bbox,
                        score=best_chunk.combined_score,
                        path_titles=list(best_chunk.path_titles or []),
                        start_page=best_chunk.start_page,
                        end_page=best_chunk.end_page,
                        element_ids=list(best_chunk.element_ids or []),
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
                        path_titles=[],
                        start_page=None,
                        end_page=None,
                        element_ids=[],
                    )
                )

        # DEBUG: логируем, что именно вернул LLM и какой чанк выбран
        try:
            logger.debug(
                "LLMDetector._build_result",
                extra={
                    "found": bool(response.found),
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
            # Лог сам по себе не должен ломать пайплайн
            logger.debug("LLMDetector._build_result: debug logging failed")

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
                "best_chunk_page": getattr(best_chunk, "page", None)
                if best_chunk
                else None,
                "best_chunk_clause_uid": getattr(best_chunk, "clause_uid", None)
                if best_chunk
                else None,
            },
        )

        return best_chunk if best_overlap >= 3 else None
