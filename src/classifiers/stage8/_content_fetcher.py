# src/classifiers/stage8/_content_fetcher.py
"""
Получение header/snippet из DocumentContentService.

Зачем файл нужен:
- это отдельный I/O-слой без бизнес-логики классификации;
- его удобно мокировать в тестах;
- он отвечает за качество входа для последующих этапов:
  - header_text -> основной вход для L2;
  - snippet_text -> основной вход для L3/L4.

Основная цель этой версии:
- не терять молча проблемы интеграции;
- дать понятный DEBUG/WARNING-след о том, какой именно текст реально пришёл
  в header_text и snippet_text для конкретного doc_id;
- упростить диагностику ложной/слабой классификации.
"""
from __future__ import annotations

import re
from typing import Any

from engine.content.document_content_service import DocumentContentService
from core.logging import get_logger

logger = get_logger(__name__)


class ContentFetcher:
    """
    Обёртка над DocumentContentService.

    Поведение:
    - безопасно вызывает content-service методы;
    - нормализует результат;
    - логирует качество полученного текста;
    - не роняет пайплайн, если интеграционный сервис недоступен или несовместим.
    """

    HEADER_METHOD = "get_title_and_preamble"
    SNIPPET_METHOD = "get_snippet_from_layout"

    HEADER_WEAK_MIN_LEN = 20
    SNIPPET_WEAK_MIN_LEN = 50
    PREVIEW_LIMIT = 1200
    PREFIX_COMPARE_LEN = 120

    def __init__(self, content_service: DocumentContentService | None) -> None:
        self.content_service = content_service

    async def fetch(self, doc_id: str) -> tuple[str | None, str | None]:
        """
        Возвращает (header_text, snippet_text).

        header_text:
            нормализованная шапка документа (title + preamble),
            основной источник для L2.

        snippet_text:
            начало текста из layout,
            основной источник для L3/L4 и body/any-сигналов.
        """
        if self.content_service is None:
            logger.warning(
                "ContentFetcher: content_service is not configured, downstream classification quality will be limited",
                doc_id=str(doc_id),
            )
            return None, None

        raw_header = await self._safe_call(self.HEADER_METHOD, doc_id)
        raw_snippet = await self._safe_call(self.SNIPPET_METHOD, doc_id)

        header_text = self._clean_text(raw_header)
        snippet_text = self._clean_text(raw_snippet)

        self._log_fetch_result(
            doc_id=doc_id,
            raw_header=raw_header,
            raw_snippet=raw_snippet,
            header_text=header_text,
            snippet_text=snippet_text,
        )

        return header_text, snippet_text

    async def _safe_call(self, method_name: str, doc_id: str) -> str | None:
        """
        Вызывает метод content_service.

        Важно:
        - явно логирует отсутствие метода;
        - явно логирует AttributeError внутри вызова;
        - логирует неожиданные исключения с traceback;
        - пытается безопасно привести нестроковый результат к str.
        """
        method = getattr(self.content_service, method_name, None)
        if method is None:
            logger.warning(
                "ContentFetcher method is missing on content_service",
                doc_id=str(doc_id),
                method_name=method_name,
                service_class=type(self.content_service).__name__,
            )
            return None

        try:
            value = await method(doc_id)

            if value is None:
                logger.debug(
                    "ContentFetcher method returned None",
                    doc_id=str(doc_id),
                    method_name=method_name,
                )
                return None

            if not isinstance(value, str):
                logger.warning(
                    "ContentFetcher method returned non-string value, coercing to str",
                    doc_id=str(doc_id),
                    method_name=method_name,
                    value_type=type(value).__name__,
                )
                return str(value)

            return value

        except AttributeError as e:
            logger.warning(
                "ContentFetcher method failed with AttributeError",
                doc_id=str(doc_id),
                method_name=method_name,
                service_class=type(self.content_service).__name__,
                error=str(e),
            )
            return None

        except Exception as e:
            logger.exception(
                "ContentFetcher method failed with unexpected exception",
                doc_id=str(doc_id),
                method_name=method_name,
                service_class=type(self.content_service).__name__,
                error=str(e),
            )
            return None

    def _log_fetch_result(
        self,
        *,
        doc_id: str,
        raw_header: str | None,
        raw_snippet: str | None,
        header_text: str | None,
        snippet_text: str | None,
    ) -> None:
        """
        Единая диагностика качества входного текста для классификации.

        Что логируем:
        - длины raw/clean;
        - preview реального текста;
        - пустоту / слабость / дублирование;
        - подозрение, что snippet начинается с header.
        """
        header_len = len(header_text or "")
        snippet_len = len(snippet_text or "")

        raw_header_len = len(raw_header or "")
        raw_snippet_len = len(raw_snippet or "")

        header_missing = header_text is None
        snippet_missing = snippet_text is None

        header_weak = bool(header_text) and header_len < self.HEADER_WEAK_MIN_LEN
        snippet_weak = bool(snippet_text) and snippet_len < self.SNIPPET_WEAK_MIN_LEN

        snippet_starts_with_header = False
        header_equals_snippet = False

        if header_text and snippet_text:
            header_equals_snippet = header_text == snippet_text
            compare_prefix = header_text[: self.PREFIX_COMPARE_LEN]
            if compare_prefix:
                snippet_starts_with_header = snippet_text.startswith(compare_prefix)

        payload: dict[str, Any] = {
            "doc_id": str(doc_id),
            "header_raw_len": raw_header_len,
            "snippet_raw_len": raw_snippet_len,
            "header_len": header_len,
            "snippet_len": snippet_len,
            "header_missing": header_missing,
            "snippet_missing": snippet_missing,
            "header_weak": header_weak,
            "snippet_weak": snippet_weak,
            "header_equals_snippet": header_equals_snippet,
            "snippet_starts_with_header": snippet_starts_with_header,
            "header_preview": self._preview(header_text),
            "snippet_preview": self._preview(snippet_text),
        }

        logger.debug("ContentFetcher fetched content", **payload)

        if header_missing:
            logger.warning(
                "ContentFetcher header_text is missing",
                doc_id=str(doc_id),
                header_raw_len=raw_header_len,
                snippet_len=snippet_len,
                header_preview=self._preview(header_text, 300),
                snippet_preview=self._preview(snippet_text, 300),
            )
        elif header_weak:
            logger.warning(
                "ContentFetcher header_text is weak",
                doc_id=str(doc_id),
                header_len=header_len,
                header_preview=self._preview(header_text, 300),
            )

        if snippet_missing:
            logger.warning(
                "ContentFetcher snippet_text is missing",
                doc_id=str(doc_id),
                header_len=header_len,
                snippet_raw_len=raw_snippet_len,
                header_preview=self._preview(header_text, 300),
            )
        elif snippet_weak:
            logger.warning(
                "ContentFetcher snippet_text is weak",
                doc_id=str(doc_id),
                snippet_len=snippet_len,
                snippet_preview=self._preview(snippet_text, 300),
            )

        if header_equals_snippet:
            logger.warning(
                "ContentFetcher header_text equals snippet_text",
                doc_id=str(doc_id),
                header_len=header_len,
                snippet_len=snippet_len,
                header_preview=self._preview(header_text, 300),
            )
        elif snippet_starts_with_header:
            logger.debug(
                "ContentFetcher snippet starts with header prefix",
                doc_id=str(doc_id),
                header_prefix=self._preview(
                    (header_text or "")[: self.PREFIX_COMPARE_LEN],
                    200,
                ),
            )

    @staticmethod
    def _clean_text(text: str | None) -> str | None:
        """
        Нормализует текст, не ломая исходный смысл.

        Что делаем:
        - None -> None;
        - заменяем NBSP на обычный пробел;
        - унифицируем переводы строк;
        - схлопываем хвостовые/начальные пробелы;
        - если после очистки текст пустой -> None.

        Важно:
        - мы НЕ схлопываем весь текст в одну строку;
        - сохраняем структуру абзацев для preview и downstream-анализа.
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

        Preview помогает понять, какой текст реально ушёл в header/snippet,
        не заливая лог целым документом.
        """
        if not text:
            return None

        limit = limit or cls.PREVIEW_LIMIT
        s = text[:limit]

        s = s.replace("\n", "\\n").replace("\r", "\\r")
        s = re.sub(r"\s+", " ", s).strip()

        return s or None
        
        