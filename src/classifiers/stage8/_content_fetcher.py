# src/classifiers/stage8/_content_fetcher.py
"""
Получение header/snippet из DocumentContentService.

Вынесено отдельно, потому что:
  - это чистый I/O без бизнес-логики;
  - легко мокируется в тестах;
  - метод get_header_and_snippet (legacy) уже не используется —
    новый код явно отражает это разделение.
"""
from __future__ import annotations

from typing import Optional

from engine.content.document_content_service import DocumentContentService
from core.logging import get_logger

logger = get_logger(__name__)


class ContentFetcher:
    """
    Обёртка над DocumentContentService.
    Защищает от AttributeError на случай, если методы ещё не задеплоены.
    """

    def __init__(self, content_service: DocumentContentService | None) -> None:
        self.content_service = content_service

    async def fetch(self, doc_id: str) -> tuple[str | None, str | None]:
        """
        Возвращает (header_text, snippet_text).

        header_text — нормализованная шапка (title + преамбула) → источник для L2.
        snippet_text — начало текста из layout → источник для L3/L4.
        """
        if self.content_service is None:
            logger.warning(
                "ContentFetcher: content_service is not configured, L2/L3/L4 will be limited",
                doc_id=str(doc_id),
            )
            return None, None

        header_text = await self._safe_call("get_title_and_preamble", doc_id)
        snippet_text = await self._safe_call("get_snippet_from_layout", doc_id)
        return header_text, snippet_text

    async def _safe_call(self, method_name: str, doc_id: str) -> str | None:
        """Вызывает метод сервиса; при AttributeError — возвращает None."""
        method = getattr(self.content_service, method_name, None)
        if method is None:
            return None
        try:
            return await method(doc_id)
        except AttributeError:
            return None
        
        