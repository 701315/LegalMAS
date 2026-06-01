# src/services/ocr/_registry.py

"""
OCR Adapter Registry — Phase 13.3.

Отвечает за:
- выбор OCR adapter по EXTRACTION_OCR_PROVIDER из config;
- проверку доступности выбранного provider;
- fallback на Tesseract если запрошенный provider недоступен.

Принципы:
- Failure-isolated: любая ошибка возвращает TesseractOCRAdapter.
- Singleton-per-provider: adapters создаются один раз и кэшируются.
- Не мутирует config.
"""

from __future__ import annotations

from core.logging import get_logger
from services.ocr._paddle import PaddleOCRAdapter
from services.ocr._protocol import OCRAdapterProtocol
from services.ocr._tesseract import TesseractOCRAdapter

logger = get_logger(__name__)

# Module-level cache: provider_name -> adapter instance
_ADAPTER_CACHE: dict[str, OCRAdapterProtocol] = {}


def get_ocr_adapter(
    provider: str | None = None,
) -> OCRAdapterProtocol:
    """
    Вернуть OCR adapter для указанного provider.

    Если provider не указан — читает EXTRACTION_OCR_PROVIDER из settings.
    Если provider недоступен — fallback на Tesseract с предупреждением.
    Если Tesseract тоже недоступен — возвращает TesseractOCRAdapter
    (он вернёт пустой результат с описанием ошибки при вызове).

    Failure-isolated: никогда не бросает исключений.
    """
    try:
        resolved_provider = _resolve_provider(provider)
        return _get_or_create_adapter(resolved_provider)
    except Exception as exc:
        logger.warning(
            "OCR registry: failed to resolve adapter, using Tesseract",
            error=str(exc),
        )
        return TesseractOCRAdapter()


def is_ocr_provider_available(provider: str | None = None) -> bool:
    """
    Проверить доступность OCR provider.

    Failure-isolated: при любой ошибке возвращает False.
    """
    try:
        adapter = get_ocr_adapter(provider)
        return adapter.is_available()
    except Exception:
        return False


# ── Internal ──────────────────────────────────────────────────────────────────

def _resolve_provider(provider: str | None) -> str:
    """Определить имя provider из аргумента или config."""
    if provider is not None:
        return str(provider).lower().strip()

    try:
        from core.config import settings
        configured = getattr(settings, "EXTRACTION_OCR_PROVIDER", "tesseract")
        return str(configured).lower().strip() or "tesseract"
    except Exception:
        return "tesseract"


def _get_or_create_adapter(provider: str) -> OCRAdapterProtocol:
    """
    Вернуть adapter из кэша или создать новый.

    При недоступности запрошенного provider — fallback на Tesseract.
    """
    if provider in _ADAPTER_CACHE:
        return _ADAPTER_CACHE[provider]

    adapter = _build_adapter(provider)

    if not adapter.is_available():
        logger.warning(
            "OCR registry: requested provider not available, falling back to Tesseract",
            requested=provider,
        )
        fallback = TesseractOCRAdapter()
        _ADAPTER_CACHE[provider] = fallback
        return fallback

    logger.info(
        "OCR registry: adapter initialized",
        provider=adapter.provider_name,
    )
    _ADAPTER_CACHE[provider] = adapter
    return adapter


def _build_adapter(provider: str) -> OCRAdapterProtocol:
    """Создать adapter по имени provider."""
    if provider == "tesseract":
        return TesseractOCRAdapter()
    if provider in ("paddle", "paddleocr"):
        return PaddleOCRAdapter()

    logger.warning(
        "OCR registry: unknown provider, falling back to Tesseract",
        unknown_provider=provider,
    )
    return TesseractOCRAdapter()


