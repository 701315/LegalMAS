# src/services/ocr/_tesseract.py

"""
Tesseract OCR Adapter — Phase 13.3.

Переносит логику из _extract_ocr_page() в pdf_extractor.py
в отдельный adapter класс.

Поведение идентично оригинальному коду — это рефакторинг без изменения логики.
"""

from __future__ import annotations

from core.logging import get_logger
from services.ocr._protocol import OCRAdapterProtocol, OCRPageResult

logger = get_logger(__name__)

# Tesseract availability — проверяем один раз при импорте
_TESSERACT_AVAILABLE = False
try:
    import pytesseract
    from pdf2image import convert_from_bytes as _convert_from_bytes

    pytesseract.get_tesseract_version()
    _TESSERACT_AVAILABLE = True
except Exception:
    pass


class TesseractOCRAdapter:
    """
    OCR adapter на базе Tesseract + pdf2image.

    Реализует OCRAdapterProtocol.
    Логика идентична _extract_ocr_page() из pdf_extractor.py до Phase 13.3.
    """

    @property
    def provider_name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        """Tesseract доступен если pytesseract установлен и tesseract найден."""
        return _TESSERACT_AVAILABLE

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
        Извлечь текст с одной страницы через Tesseract.

        Failure-isolated: при любой ошибке возвращает пустой результат.
        """
        if not _TESSERACT_AVAILABLE:
            return OCRPageResult(
                elements=[],
                avg_confidence=0.0,
                provider=self.provider_name,
                errors=[f"Tesseract not available for page {page_num}"],
            )

        try:
            return self._extract_internal(
                pdf_bytes=pdf_bytes,
                page_num=page_num,
                document_id=document_id,
                start_index=start_index,
                dpi=dpi,
                lang=lang,
                debug=debug,
            )
        except Exception as exc:
            logger.warning(
                "TesseractOCRAdapter: unexpected error",
                document_id=document_id,
                page=page_num,
                error=str(exc),
            )
            return OCRPageResult(
                elements=[],
                avg_confidence=0.0,
                provider=self.provider_name,
                errors=[f"Tesseract failed on page {page_num}: {exc}"],
            )

    # ── Internal ─────────────────────────────────────────────────────────

    def _extract_internal(
        self,
        *,
        pdf_bytes: bytes,
        page_num: int,
        document_id: str,
        start_index: int,
        dpi: int,
        lang: str,
        debug: bool,
    ) -> OCRPageResult:
        """Основная логика — идентична оригинальному _extract_ocr_page()."""
        # Импортируем здесь чтобы не падать при отсутствии библиотек
        from pdf2image import convert_from_bytes
        import pytesseract

        # Импортируем helpers из pdf_extractor чтобы не дублировать код
        from services.pdf_extractor import make_element_id, _classify_element_type, Element

        elements = []
        confidences = []

        images = convert_from_bytes(
            pdf_bytes,
            dpi=dpi,
            first_page=page_num,
            last_page=page_num,
        )

        if not images:
            if debug:
                logger.warning(
                    "TesseractOCRAdapter: no images produced",
                    document_id=document_id,
                    page=page_num,
                    dpi=dpi,
                )
            return OCRPageResult(
                elements=[],
                avg_confidence=0.0,
                provider=self.provider_name,
                errors=[f"No images produced for page {page_num}"],
            )

        image = images[0]
        ocr_data = pytesseract.image_to_data(
            image,
            lang=lang,
            output_type=pytesseract.Output.DICT,
        )

        if debug:
            total_ocr_items = len(ocr_data.get("text", []))
            non_empty = sum(
                1 for t in (ocr_data.get("text", []) or []) if str(t).strip()
            )
            logger.debug(
                "TesseractOCRAdapter: image_to_data snapshot",
                document_id=document_id,
                page=page_num,
                dpi=dpi,
                total_items=total_ocr_items,
                non_empty_words=non_empty,
            )

        current_line_words: list[dict] = []
        current_line_num = -1
        current_block_num = -1

        for idx in range(len(ocr_data["text"])):
            word_text = ocr_data["text"][idx].strip()
            word_conf = int(ocr_data["conf"][idx])
            block_num = ocr_data["block_num"][idx]
            line_num = ocr_data["line_num"][idx]

            if not word_text or word_conf < 0:
                continue

            if line_num != current_line_num or block_num != current_block_num:
                if current_line_words:
                    elem, conf = self._build_ocr_element(
                        words=current_line_words,
                        document_id=document_id,
                        page_num=page_num,
                        element_index=start_index + len(elements),
                        make_element_id_fn=make_element_id,
                        classify_fn=_classify_element_type,
                        element_cls=Element,
                    )
                    if elem is not None:
                        elements.append(elem)
                        confidences.append(conf)
                current_line_words = []
                current_line_num = line_num
                current_block_num = block_num

            current_line_words.append({
                "text": word_text,
                "conf": word_conf,
                "left": ocr_data["left"][idx],
                "top": ocr_data["top"][idx],
                "width": ocr_data["width"][idx],
                "height": ocr_data["height"][idx],
            })

        # Последняя строка
        if current_line_words:
            elem, conf = self._build_ocr_element(
                words=current_line_words,
                document_id=document_id,
                page_num=page_num,
                element_index=start_index + len(elements),
                make_element_id_fn=make_element_id,
                classify_fn=_classify_element_type,
                element_cls=Element,
            )
            if elem is not None:
                elements.append(elem)
                confidences.append(conf)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        if debug:
            logger.debug(
                "TesseractOCRAdapter: page complete",
                document_id=document_id,
                page=page_num,
                elements_count=len(elements),
                avg_conf=round(avg_conf, 4),
            )

        return OCRPageResult(
            elements=elements,
            avg_confidence=avg_conf,
            provider=self.provider_name,
        )

    @staticmethod
    def _build_ocr_element(
        words: list[dict],
        document_id: str,
        page_num: int,
        element_index: int,
        *,
        make_element_id_fn,
        classify_fn,
        element_cls,
    ) -> tuple:
        """Собрать Element из слов одной OCR строки."""
        if not words:
            return None, 0.0

        text = " ".join(w["text"] for w in words).strip()
        if not text:
            return None, 0.0

        avg_conf = sum(w["conf"] for w in words) / len(words)
        bbox = [
            min(w["left"] for w in words),
            min(w["top"] for w in words),
            max(w["left"] + w["width"] for w in words),
            max(w["top"] + w["height"] for w in words),
        ]

        elem_id = make_element_id_fn(document_id, page_num, element_index)
        elem_type = classify_fn(text)

        elem = element_cls(
            element_id=elem_id,
            type=elem_type,
            text=text,
            page=page_num,
            bbox=[round(v, 2) for v in bbox],
            confidence=round(avg_conf / 100.0, 3),
            strategy="ocr",
        )
        return elem, avg_conf / 100.0
    

