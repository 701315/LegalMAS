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
            bundle = await self.content_service.get_classification_content(
                doc_id,
                hot_keyword_patterns=hot_patterns,
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
        

        
