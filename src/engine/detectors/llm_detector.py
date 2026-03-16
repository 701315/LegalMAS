# src/engine/detectors/llm_detector.py

"""
LLM-based detector for complex checks.

Использует:
- LLMConfig из playbook (promptfile / prompttemplate / context_k / temperature / max_tokens)
- PromptLoader для загрузки шаблона промпта
- LLMClient для вызова провайдера (OpenAI / Ollama / llamacpp)
- RetrievedChunk из RetrievalEngine для формирования контекста

Ожидаемый формат ответа LLM (JSON):
{
  "found": true/false,
  "evidence": "...",
  "clause": "...",
  "confidence": 0.0-1.0,
  "reasoning": "..."
}
"""

from __future__ import annotations

from core.logging import get_logger
from .models import DetectionResult, EvidenceChunk, RetrievedChunk
from ..llm.client import LLMClient, LLMResponse
from ..playbook.models import LLMConfig
from ..prompts.loader import get_promptloader

logger = get_logger(__name__)


DEFAULT_PROMPT_FILE = "detection/genericclause"


class LLMDetector:
    """LLM-based detector for checks described by LLMConfig."""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()
        self.promptloader = get_promptloader()

    def detect(
        self,
        config: LLMConfig,
        chunks: list[RetrievedChunk],
        use_sanitized: bool = True,  # задел на будущую работу с PII
    ) -> DetectionResult | None:
        """
        Run LLM-based detection on retrieved chunks.

        Args:
            config: LLMConfig из playbook.
            chunks: список RetrievedChunk от RetrievalEngine (уже в порядке убывания score).
            use_sanitized: зарезервировано на будущее (для выбора между raw/sanitized текстом).

        Returns:
            DetectionResult или None, если LLM недоступен / нет промпта / нет чанков.
        """
        if not self.client.is_available():
            logger.debug("LLM not available, skipping LLM detection")
            return None

        prompt_template = self._resolve_prompt(config)
        if not prompt_template:
            logger.debug("No prompt available for LLM detection")
            return None

        if not chunks:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={"reason": "no_chunks_for_context"},
            )

        context_k = config.context_k if hasattr(config, "context_k") else 5
        context_chunks = chunks[: max(1, context_k)]
        context_text = self._build_context(context_chunks)

        try:
            prompt = prompt_template.replace("{context}", context_text)
        except Exception as e:
            logger.warning(
                "LLM prompt formatting failed",
                error=str(e),
            )
            return None

        try:
            response: LLMResponse | None = self.client.call(
                prompt=prompt,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        except Exception as e:
            logger.warning("LLM call failed", error=str(e))
            return None

        if response is None:
            return None

        return self._build_result(response, context_chunks)

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
            return None

        prompt_template = self._resolve_prompt(config)
        if not prompt_template:
            return None

        if not chunks:
            return DetectionResult(
                found=False,
                evidence_chunks=[],
                confidence=0.0,
                detector_type="llm",
                details={"reason": "no_chunks_for_context"},
            )

        context_k = config.context_k if hasattr(config, "context_k") else 5
        context_chunks = chunks[: max(1, context_k)]
        context_text = self._build_context(context_chunks)

        try:
            variables = {"context": context_text, **extra_variables}
            prompt = prompt_template.format(**variables)
        except KeyError as e:
            logger.warning(
                "Missing variable in prompt template",
                variable=str(e),
                prompt_source=(config.prompt_template or config.prompt_file or DEFAULT_PROMPT_FILE),
            )
            return None
        except Exception as e:
            logger.warning("LLM prompt formatting failed", error=str(e))
            return None

        try:
            response = self.client.call(
                prompt=prompt,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        except Exception as e:
            logger.warning("LLM call failed", error=str(e))
            return None

        if response is None:
            return None

        return self._build_result(response, context_chunks)

    # --- internal helpers ---

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
                        "Failed to load prompt file, falling back",
                        prompt_file=prompt_file,
                        error=str(e),
                    )
            else:
                logger.warning(
                    "Prompt file not found, falling back to default",
                    prompt_file=prompt_file,
                    available=self.promptloader.list_prompts("detection"),
                )

        # 3. Файл по умолчанию
        try:
            return self.promptloader.load_raw(DEFAULT_PROMPT_FILE)
        except FileNotFoundError:
            logger.error("Default prompt file not found", path=DEFAULT_PROMPT_FILE)
            return None

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        """
        Построить текст контекста для LLM из чанков.

        Формат: пронумерованные части с указанием страницы/клаузы.
        """
        parts: list[str] = []
        for i, chunk in enumerate(chunks, start=1):
            clause_info = f" [clause {chunk.clause_uid}]" if chunk.clause_uid else ""
            header = f"[{i}] page {chunk.page}{clause_info}:"
            parts.append(f"{header}\n{chunk.text}\n")
        return "\n".join(parts)

    def _build_result(
        self,
        response: LLMResponse,
        context_chunks: list[RetrievedChunk],
    ) -> DetectionResult:
        """
        Превратить LLMResponse в DetectionResult.

        Если LLM дал текст evidence, пытаемся найти подходящий chunk,
        иначе создаём evidence без привязки к элементу.
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
