# src/classifiers/stage8/_content_fetcher.py

"""
Canonical classification content fetcher для HybridClassifier.

Зачем файл нужен:
- это отдельный I/O-слой без бизнес-логики классификации;
- его удобно мокировать в тестах;
- он отвечает за качество входа для последующих этапов:
  - header_text → основной вход для L2;
  - body_text   → основной вход для L3/L4.

Дизайн-решение:
- единственный источник: DocumentContentService.get_classification_content();
- fetcher отвечает только за:
  - безопасный вызов canonical source;
  - нормализацию текста (clean_text);
  - диагностическое логирование качества входа.
- никакой бизнес-логики классификации;
- fetcher работает только через canonical classification content bundle;
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from core.config import settings
from core.logging import get_logger
from engine.content._document_content_classification import ClassificationContentBundle
from engine.content.document_content_service import DocumentContentService

logger = get_logger(__name__)


class ContentFetcher:
    """
    Thin adapter над DocumentContentService.get_classification_content().

    Поведение:
    - безопасно вызывает get_classification_content();
    - нормализует header_text и body_text через _clean_text();
    - логирует качество полученного bundle;
    - при ошибке или отсутствии content_service возвращает empty bundle;
    - не роняет pipeline при сбоях content service.
    """

    HEADER_WEAK_MIN_LEN = 20
    BODY_WEAK_MIN_LEN = 50
    PREVIEW_LIMIT = 1200

    def __init__(self, content_service: DocumentContentService | None) -> None:
        self.content_service = content_service

    async def fetch(
        self,
        doc_id: str | UUID | Any,
        *,
        hot_patterns: list[re.Pattern[str]] | None = None,
    ) -> ClassificationContentBundle:
        """
        Возвращает canonical classification content bundle.

        Источник:
        - DocumentContentService.get_classification_content(doc_id)

        Phase 3.2:
        - hot_patterns: compiled regex patterns from YAML keywords.high
          (distinctiveness=high) for forced inclusion in body_text.

        ВАЖНО:
        - fetcher не использует get_header_and_snippet() / get_snippet_from_layout();
        - header_text и body_text приходят из canonical semantic corpus;
        - fetcher отвечает только за safe fetch, нормализацию и диагностику.
        """
        if self.content_service is None:
            logger.warning(
                "ContentFetcher: content_service is not configured, "
                "downstream classification quality will be limited",
                doc_id=self._doc_id_for_logs(doc_id),
            )
            return self._empty_bundle()

        try:
            max_body_chars = self._calculate_max_body_chars()

            bundle = await self.content_service.get_classification_content(
                doc_id,
                hot_keyword_patterns=hot_patterns,
                max_body_chars=max_body_chars,
            )
        except Exception as e:
            logger.exception(
                "ContentFetcher failed to fetch canonical classification content",
                doc_id=self._doc_id_for_logs(doc_id),
                service_class=type(self.content_service).__name__,
                error=str(e),
            )
            return self._empty_bundle()

        header_text = self._clean_text(bundle.header_text)
        body_text = self._clean_text(bundle.body_text)

        cleaned_bundle = ClassificationContentBundle(
            header_text=header_text,
            body_text=body_text,
            header_source=bundle.header_source,
            body_source=bundle.body_source,
            header_refs=list(bundle.header_refs or []),
            body_refs=list(bundle.body_refs or []),
            body_levels=list(bundle.body_levels or []),
            body_scopes=list(bundle.body_scopes or []),
            diagnostics=dict(bundle.diagnostics or {}),
        )

        self._log_bundle_result(
            doc_id=doc_id,
            bundle=cleaned_bundle,
        )

        return cleaned_bundle

    @staticmethod
    def _calculate_prompt_overhead_tokens() -> int:
        """
        Динамически вычисляет overhead промпта L4 на основе реального шаблона.
        Универсальное решение: устраняет необходимость в захардкоженном значении.
        """
        from pathlib import Path

        prompt_path = Path(getattr(settings, "CLASSIFICATION_L4_PROMPT_PATH", ""))
        if not prompt_path.exists():
            logger.warning(
                "ContentFetcher: prompt template not found, using fallback overhead",
                prompt_path=str(prompt_path),
            )
            return 1500

        try:
            template = prompt_path.read_text(encoding="utf-8").strip()
            skeleton = template.replace("{available_types}", "[]")
            skeleton = skeleton.replace("{document_fragment}", "")

            chatml_system_instruction = (
                "Ты — юридический ассистент. Отвечай СТРОГО одним JSON-объектом "
                "с полями type_code, confidence, reasoning. "
                "Никаких пояснений, никакого markdown, никаких блоков ```json. "
                "Только JSON."
            )
            chatml_overhead = (
                f"<|im_start|>system\n"
                f"{chatml_system_instruction}\n"
                f"<|im_end|>\n"
                f"<|im_start|>user\n"
                f"{skeleton}\n"
                f"<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

            chars_per_token = float(getattr(settings, "LLM_TOKENIZER_CHARS_PER_TOKEN", 2.2))
            tokens = max(1, int(len(chatml_overhead) / chars_per_token))

            return tokens
        except Exception as e:
            logger.warning("ContentFetcher: failed to calculate prompt overhead, using fallback", error=str(e))
            return 1500

    @staticmethod
    def _calculate_max_body_chars() -> int:
        """
        Динамически вычисляет максимальный размер body_text на основе
        бюджета LLM.

        Универсальный принцип (Universal Solution):
        - Overhead промпта рассчитывается динамически на основе реального шаблона.
        - Все критические параметры вынесены в settings (настраиваются через .env).
        - Коэффициент конверсии токенов в символы (LLM_TOKENIZER_CHARS_PER_TOKEN)
          зависит от токенизатора модели и настраивается через .env.
        - Абсолютный лимит (CLASSIFICATION_L4_MAX_BODY_CHARS) защищает от аномалий.

        Адаптируется автоматически при смене модели, LLM_CONTEXT_LIMIT или шаблона промпта.
        """
        llm_context_limit = int(
            getattr(settings, "LLM_CONTEXT_LIMIT", 16384)
        )
        max_output_tokens = int(
            getattr(settings, "LLM_MAX_TOKENS", 1024)
        )
        safety_margin = int(
            getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 256)
        )

        # Динамический расчёт overhead промпта (без магических чисел)
        prompt_overhead_tokens = ContentFetcher._calculate_prompt_overhead_tokens()

        # Минимальный доступный объём для текста документа (архитектурный инвариант)
        min_available_tokens = int(
            getattr(settings, "CLASSIFICATION_L4_MIN_AVAILABLE_TOKENS", 1000)
        )

        # Универсальный коэффициент конверсии токенов в символы.
        # Зависит от токенизатора модели (BPE, SentencePiece и т.д.).
        # Настраивается через LLM_TOKENIZER_CHARS_PER_TOKEN в .env.
        chars_per_token = float(
            getattr(settings, "LLM_TOKENIZER_CHARS_PER_TOKEN", 2.2)
        )

        # Абсолютный защитный лимит на случай аномалий
        max_body_chars_cap = int(
            getattr(settings, "CLASSIFICATION_L4_MAX_BODY_CHARS", 35_000)
        )

        available_tokens = (
            llm_context_limit
            - max_output_tokens
            - safety_margin
            - prompt_overhead_tokens
        )
        available_tokens = max(available_tokens, min_available_tokens)

        max_body_chars = int(available_tokens * chars_per_token)
        max_body_chars = min(max_body_chars, max_body_chars_cap)

        logger.debug(
            "ContentFetcher: dynamic max_body_chars calculated",
            llm_context_limit=llm_context_limit,
            max_output_tokens=max_output_tokens,
            safety_margin=safety_margin,
            prompt_overhead_tokens=prompt_overhead_tokens,
            min_available_tokens=min_available_tokens,
            chars_per_token=chars_per_token,
            max_body_chars_cap=max_body_chars_cap,
            available_tokens=available_tokens,
            max_body_chars=max_body_chars,
        )

        return max_body_chars


    @staticmethod
    def _empty_bundle() -> ClassificationContentBundle:
        return ClassificationContentBundle(
            header_text=None,
            body_text=None,
            header_source="empty",
            body_source="empty",
            header_refs=[],
            body_refs=[],
            body_levels=[],
            body_scopes=[],
            diagnostics={
                "header_source": "empty",
                "body_source": "empty",
                "header_refs": [],
                "body_refs": [],
                "body_levels": [],
                "body_scopes": [],
                "header_len": 0,
                "body_len": 0,
            },
        )

    def _log_bundle_result(
        self,
        *,
        doc_id: str | UUID | Any,
        bundle: ClassificationContentBundle,
    ) -> None:
        """
        Диагностика качества полученного classification content bundle.

        Что логируем:
        - источники header и body;
        - длины текстов;
        - признаки отсутствия / слабости;
        - refs и scopes для трассировки.
        """
        header_text = bundle.header_text
        body_text = bundle.body_text

        header_len = len(header_text or "")
        body_len = len(body_text or "")

        payload: dict[str, Any] = {
            "doc_id": self._doc_id_for_logs(doc_id),
            "header_source": bundle.header_source,
            "body_source": bundle.body_source,
            "header_len": header_len,
            "body_len": body_len,
            "header_missing": header_text is None,
            "body_missing": body_text is None,
            "header_weak": bool(header_text) and header_len < self.HEADER_WEAK_MIN_LEN,
            "body_weak": bool(body_text) and body_len < self.BODY_WEAK_MIN_LEN,
            "header_refs": list(bundle.header_refs or [])[:5],
            "body_refs": list(bundle.body_refs or [])[:15],
            "body_levels": list(bundle.body_levels or []),
            "body_scopes": list(bundle.body_scopes or []),
            "header_preview": self._preview(header_text),
            "body_preview": self._preview(body_text),
        }

        logger.debug("ContentFetcher fetched classification content", **payload)

        if header_text is None:
            logger.warning(
                "ContentFetcher header_text is missing",
                doc_id=self._doc_id_for_logs(doc_id),
                header_source=bundle.header_source,
                body_source=bundle.body_source,
                body_len=body_len,
                header_preview=self._preview(header_text, 300),
                body_preview=self._preview(body_text, 300),
            )

        if body_text is None:
            logger.warning(
                "ContentFetcher body_text is missing",
                doc_id=self._doc_id_for_logs(doc_id),
                header_source=bundle.header_source,
                body_source=bundle.body_source,
                header_len=header_len,
                header_preview=self._preview(header_text, 300),
            )

    @staticmethod
    def _clean_text(text: str | None) -> str | None:
        """
        Нормализует текст, не ломая исходный смысл.

        Что делаем:
        - None → None;
        - заменяем NBSP на обычный пробел;
        - унифицируем переводы строк;
        - схлопываем хвостовые/начальные пробелы по строкам;
        - если после очистки текст пустой → None.

        Важно:
        - не схлопываем весь текст в одну строку;
        - сохраняем структуру абзацев для downstream-анализа.
        """
        if text is None:
            return None

        if not isinstance(text, str):
            text = str(text)

        text = text.replace("\xa0", " ")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines).strip()

        return text or None

    @classmethod
    def _preview(cls, text: str | None, limit: int | None = None) -> str | None:
        """
        Возвращает безопасный preview для логов.
        """
        if not text:
            return None

        limit = limit or cls.PREVIEW_LIMIT
        s = text[:limit]

        s = s.replace("\n", "\\n").replace("\r", "\\r")
        s = re.sub(r"\s+", " ", s).strip()

        return s or None

    @staticmethod
    def _doc_id_for_logs(doc_id: str | UUID | Any) -> str:
        """
        Безопасно приводит doc_id к строке только для логов.
        """
        try:
            return str(doc_id)
        except Exception:
            return "<unprintable-doc-id>"
        

        
