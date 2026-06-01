# src/services/ocr/__init__.py

"""
OCR Adapter Layer — Phase 13.3.

Public API:
    OCRAdapterProtocol  — Protocol для всех OCR адаптеров
    TesseractOCRAdapter — production adapter (текущий engine)
    PaddleOCRAdapter    — stub (не реализован)
    get_ocr_adapter     — фабрика: выбирает adapter по config
"""

from services.ocr._protocol import OCRAdapterProtocol, OCRPageResult
from services.ocr._tesseract import TesseractOCRAdapter
from services.ocr._paddle import PaddleOCRAdapter
from services.ocr._registry import get_ocr_adapter, is_ocr_provider_available

__all__ = [
    "OCRAdapterProtocol",
    "OCRPageResult",
    "TesseractOCRAdapter",
    "PaddleOCRAdapter",
    "get_ocr_adapter",
    "is_ocr_provider_available",
]
