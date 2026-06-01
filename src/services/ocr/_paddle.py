# src/services/ocr/_paddle.py

"""
PaddleOCR Adapter — Phase 13.3 (stub).

Placeholder для будущей интеграции PaddleOCR.

Когда активировать:
- когда появятся документы с плохим качеством сканирования
  которые Tesseract не справляется обработать;
- когда paddlepaddle + paddleocr будут установлены в среде.

Текущее состояние: extract_page() возвращает пустой результат.
is_available() всегда возвращает False.
"""

from __future__ import annotations

from core.logging import get_logger
from services.ocr._protocol import OCRPageResult

logger = get_logger(__name__)


class PaddleOCRAdapter:
    """
    OCR adapter на базе PaddleOCR (stub).

    Реализует OCRAdapterProtocol.
    Не реализован — возвращает пустой результат при вызове.

    Для активации:
        1. pip install paddlepaddle paddleocr
        2. Реализовать _extract_internal()
        3. Установить EXTRACTION_OCR_PROVIDER=paddle в .env
    """

    @property
    def provider_name(self) -> str:
        return "paddle"

    def is_available(self) -> bool:
        """
        Stub всегда недоступен.

        Когда будет реальная реализация — этот метод изменится.
        """
        return False

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
        PaddleOCR не реализован.

        Возвращает пустой результат с описанием ошибки.
        Никогда не бросает исключений.
        """
        # Параметры присутствуют для соответствия OCRAdapterProtocol.
        # В stub реализации используется только document_id для логирования.
        _ = (pdf_bytes, start_index, dpi, lang, debug)

        logger.warning(
            "PaddleOCRAdapter: called but not implemented",
            document_id=document_id,
            page=page_num,
        )
        return OCRPageResult(
            elements=[],
            avg_confidence=0.0,
            provider=self.provider_name,
            errors=[
                "PaddleOCR adapter is not implemented. "
                "Set EXTRACTION_OCR_PROVIDER=tesseract or implement PaddleOCRAdapter."
            ],
        )
        

