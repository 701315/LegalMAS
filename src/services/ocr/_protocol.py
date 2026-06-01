# src/services/ocr/_protocol.py

"""
OCR Adapter Protocol — Phase 13.3.

Определяет контракт который должен реализовывать любой OCR adapter.

Контракт намеренно минимален:
- на входе: pdf_bytes + page_num + мета для element_id генерации
- на выходе: список Element + avg_confidence

Это ровно то что сейчас возвращает _extract_ocr_page() в pdf_extractor.py.
Новые adapters подключаются без изменения остального pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class OCRPageResult:
    """
    Результат OCR обработки одной страницы.

    elements:        список Element (те же что строит текущий _extract_ocr_page)
    avg_confidence:  средняя уверенность распознавания [0.0, 1.0]
    provider:        имя provider для audit trail
    errors:          диагностические сообщения (non-fatal)
    """

    elements: list = field(default_factory=list)
    avg_confidence: float = 0.0
    provider: str = "unknown"
    errors: list[str] = field(default_factory=list)

    def to_tuple(self) -> tuple[list, float]:
        """
        Backward-compatible tuple для существующего кода в pdf_extractor.py.

        Возвращает (elements, avg_confidence) — ровно то что
        возвращал _extract_ocr_page() до Phase 13.3.
        """
        return self.elements, self.avg_confidence


@runtime_checkable
class OCRAdapterProtocol(Protocol):
    """
    Protocol для OCR адаптеров.

    Любой класс реализующий extract_page() соответствует этому протоколу.
    Нет необходимости наследоваться — достаточно совпадения сигнатуры.
    """

    @property
    def provider_name(self) -> str:
        """Имя provider для логов и audit trail."""
        ...

    def is_available(self) -> bool:
        """
        Проверить доступность OCR engine.

        Возвращает True если engine установлен и готов к работе.
        Failure-isolated: не бросает исключений.
        """
        ...

    def extract_page(
        self,
        pdf_bytes: bytes,
        page_num: int,
        document_id: str,
        start_index: int,
        *,
        dpi: int = 300,
        lang: str = "rus+eng",
        debug: bool = False,
    ) -> OCRPageResult:
        """
        Извлечь текст с одной страницы PDF через OCR.

        Args:
            pdf_bytes:    сырые байты PDF документа
            page_num:     номер страницы (1-based)
            document_id:  для генерации element_id и логирования
            start_index:  глобальный индекс первого element на этой странице
            dpi:          разрешение растеризации
            lang:         языки OCR (формат зависит от provider)
            debug:        включить подробное логирование

        Returns:
            OCRPageResult с elements и avg_confidence.
            При ошибке — пустой OCRPageResult с описанием в errors.
            Никогда не бросает исключений наружу.
        """
        ...



