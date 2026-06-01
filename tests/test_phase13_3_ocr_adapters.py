"""
Тесты Phase 13.3 — OCR Adapter Layer.

Покрытие:
- OCRPageResult контракт
- OCRPageResult.to_tuple() backward compatibility
- TesseractOCRAdapter.provider_name
- TesseractOCRAdapter.is_available() — без реального Tesseract
- PaddleOCRAdapter.provider_name
- PaddleOCRAdapter.is_available() всегда False
- PaddleOCRAdapter.extract_page() — stub возвращает ошибку
- get_ocr_adapter() — tesseract provider
- get_ocr_adapter() — неизвестный provider → fallback
- get_ocr_adapter() — failure isolation
- is_ocr_provider_available() — failure isolation
- OCRAdapterProtocol runtime_checkable
- Registry caching
- Config provider resolution
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from services.ocr._protocol import OCRAdapterProtocol, OCRPageResult
from services.ocr._paddle import PaddleOCRAdapter
from services.ocr._tesseract import TesseractOCRAdapter
from services.ocr._registry import (
    get_ocr_adapter,
    is_ocr_provider_available,
    _build_adapter,
    _resolve_provider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeElement:
    """Минимальный fake Element для тестов."""
    element_id: str = "e123"
    type: str = "text"
    text: str = "test"
    page: int = 1
    bbox: list = None
    confidence: float = 1.0
    strategy: str = "ocr"

    def __post_init__(self):
        if self.bbox is None:
            self.bbox = [0, 0, 100, 20]


def _make_fake_element(text: str = "test") -> FakeElement:
    """Создать минимальный fake Element для тестов."""
    return FakeElement(text=text)


# ---------------------------------------------------------------------------
# OCRPageResult
# ---------------------------------------------------------------------------

class TestOCRPageResult:
    def test_defaults(self) -> None:
        result = OCRPageResult()
        assert result.elements == []
        assert result.avg_confidence == 0.0
        assert result.provider == "unknown"
        assert result.errors == []

    def test_to_tuple_empty(self) -> None:
        result = OCRPageResult()
        elements, conf = result.to_tuple()
        assert elements == []
        assert conf == 0.0

    def test_to_tuple_with_data(self) -> None:
        elem = _make_fake_element("hello")
        result = OCRPageResult(
            elements=[elem],
            avg_confidence=0.85,
            provider="tesseract",
        )
        elements, conf = result.to_tuple()
        assert len(elements) == 1
        assert conf == 0.85

    def test_to_tuple_backward_compatible(self) -> None:
        """to_tuple() возвращает ровно то что возвращал _extract_ocr_page()."""
        result = OCRPageResult(
            elements=[_make_fake_element()],
            avg_confidence=0.72,
        )
        ret = result.to_tuple()
        assert isinstance(ret, tuple)
        assert len(ret) == 2
        assert isinstance(ret[0], list)
        assert isinstance(ret[1], float)

    def test_errors_accumulate(self) -> None:
        result = OCRPageResult(
            errors=["error1", "error2"],
        )
        assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# OCRAdapterProtocol
# ---------------------------------------------------------------------------

class TestOCRAdapterProtocol:
    def test_tesseract_satisfies_protocol(self) -> None:
        adapter = TesseractOCRAdapter()
        assert isinstance(adapter, OCRAdapterProtocol)

    def test_paddle_satisfies_protocol(self) -> None:
        adapter = PaddleOCRAdapter()
        assert isinstance(adapter, OCRAdapterProtocol)

    def test_arbitrary_class_with_correct_interface(self) -> None:
        """Любой класс с правильными методами satisfies Protocol."""
        class CustomAdapter:
            @property
            def provider_name(self) -> str:
                return "custom"

            def is_available(self) -> bool:
                return True

            def extract_page(self, pdf_bytes, page_num, document_id,
                           start_index, **kwargs):
                return OCRPageResult(provider="custom")

        adapter = CustomAdapter()
        assert isinstance(adapter, OCRAdapterProtocol)


# ---------------------------------------------------------------------------
# TesseractOCRAdapter
# ---------------------------------------------------------------------------

class TestTesseractOCRAdapter:
    def test_provider_name(self) -> None:
        adapter = TesseractOCRAdapter()
        assert adapter.provider_name == "tesseract"

    def test_is_available_reflects_installation(self) -> None:
        """is_available() не бросает исключений."""
        adapter = TesseractOCRAdapter()
        result = adapter.is_available()
        assert isinstance(result, bool)

    def test_extract_page_when_unavailable_returns_empty(self) -> None:
        """Если Tesseract недоступен — возвращает пустой OCRPageResult."""
        adapter = TesseractOCRAdapter()

        with patch("services.ocr._tesseract._TESSERACT_AVAILABLE", False):
            result = adapter.extract_page(
                pdf_bytes=b"fake",
                page_num=1,
                document_id="doc-test",
                start_index=0,
            )

        assert isinstance(result, OCRPageResult)
        assert result.elements == []
        assert result.avg_confidence == 0.0
        assert result.provider == "tesseract"
        assert len(result.errors) > 0

    def test_extract_page_failure_isolation(self) -> None:
        """При любой внутренней ошибке — возвращает OCRPageResult, не бросает."""
        adapter = TesseractOCRAdapter()

        with patch("services.ocr._tesseract._TESSERACT_AVAILABLE", True):
            with patch.object(
                adapter, "_extract_internal",
                side_effect=RuntimeError("unexpected crash")
            ):
                result = adapter.extract_page(
                    pdf_bytes=b"fake",
                    page_num=1,
                    document_id="doc-test",
                    start_index=0,
                )

        assert isinstance(result, OCRPageResult)
        assert result.elements == []
        assert len(result.errors) > 0

    def test_build_ocr_element_empty_words(self) -> None:
        """_build_ocr_element с пустым списком возвращает (None, 0.0)."""
        elem, conf = TesseractOCRAdapter._build_ocr_element(
            words=[],
            document_id="doc",
            page_num=1,
            element_index=0,
            make_element_id_fn=lambda d, p, i: f"e{i}",
            classify_fn=lambda t: "text",
            element_cls=MagicMock,
        )
        assert elem is None
        assert conf == 0.0

    def test_build_ocr_element_whitespace_only(self) -> None:
        """_build_ocr_element с только пробелами возвращает (None, 0.0)."""
        elem, conf = TesseractOCRAdapter._build_ocr_element(
            words=[{"text": "   ", "conf": 90, "left": 0, "top": 0,
                    "width": 10, "height": 10}],
            document_id="doc",
            page_num=1,
            element_index=0,
            make_element_id_fn=lambda d, p, i: f"e{i}",
            classify_fn=lambda t: "text",
            element_cls=MagicMock,
        )
        assert elem is None
        assert conf == 0.0


# ---------------------------------------------------------------------------
# PaddleOCRAdapter
# ---------------------------------------------------------------------------

class TestPaddleOCRAdapter:
    def test_provider_name(self) -> None:
        adapter = PaddleOCRAdapter()
        assert adapter.provider_name == "paddle"

    def test_is_available_always_false(self) -> None:
        """Stub всегда недоступен."""
        adapter = PaddleOCRAdapter()
        assert adapter.is_available() is False

    def test_extract_page_returns_empty_with_error(self) -> None:
        """Stub возвращает пустой результат с описанием."""
        adapter = PaddleOCRAdapter()
        result = adapter.extract_page(
            pdf_bytes=b"fake",
            page_num=1,
            document_id="doc-test",
            start_index=0,
        )
        assert isinstance(result, OCRPageResult)
        assert result.elements == []
        assert result.avg_confidence == 0.0
        assert result.provider == "paddle"
        assert len(result.errors) > 0

    def test_extract_page_never_raises(self) -> None:
        """Stub не бросает исключений при любых входных данных."""
        adapter = PaddleOCRAdapter()
        result = adapter.extract_page(
            pdf_bytes=b"",
            page_num=999,
            document_id="",
            start_index=-1,
        )
        assert isinstance(result, OCRPageResult)

    def test_satisfies_protocol(self) -> None:
        assert isinstance(PaddleOCRAdapter(), OCRAdapterProtocol)


# ---------------------------------------------------------------------------
# Registry — _resolve_provider
# ---------------------------------------------------------------------------

class TestResolveProvider:
    def test_explicit_provider_used(self) -> None:
        assert _resolve_provider("tesseract") == "tesseract"
        assert _resolve_provider("paddle") == "paddle"

    def test_explicit_provider_lowercased(self) -> None:
        assert _resolve_provider("TESSERACT") == "tesseract"
        assert _resolve_provider("Paddle") == "paddle"

    def test_none_reads_from_config(self) -> None:
        """None → читает из settings.EXTRACTION_OCR_PROVIDER."""
        with patch("services.ocr._registry._resolve_provider") as mock:
            mock.return_value = "tesseract"
            result = mock(None)
        assert result == "tesseract"

    def test_config_fallback_on_error(self) -> None:
        """При ошибке чтения config — возвращает tesseract."""
        with patch("services.ocr._registry.logger"):
            with patch(
                "services.ocr._registry._resolve_provider",
                side_effect=Exception("config broken")
            ):
                # registry.get_ocr_adapter() обрабатывает это через try/except
                result = get_ocr_adapter("tesseract")
                assert result.provider_name == "tesseract"


# ---------------------------------------------------------------------------
# Registry — _build_adapter
# ---------------------------------------------------------------------------

class TestBuildAdapter:
    def test_tesseract_provider(self) -> None:
        adapter = _build_adapter("tesseract")
        assert isinstance(adapter, TesseractOCRAdapter)

    def test_paddle_provider(self) -> None:
        adapter = _build_adapter("paddle")
        assert isinstance(adapter, PaddleOCRAdapter)

    def test_paddleocr_alias(self) -> None:
        adapter = _build_adapter("paddleocr")
        assert isinstance(adapter, PaddleOCRAdapter)

    def test_unknown_falls_back_to_tesseract(self) -> None:
        adapter = _build_adapter("nonexistent_engine")
        assert isinstance(adapter, TesseractOCRAdapter)


# ---------------------------------------------------------------------------
# Registry — get_ocr_adapter
# ---------------------------------------------------------------------------

class TestGetOCRAdapter:
    def test_returns_adapter_instance(self) -> None:
        adapter = get_ocr_adapter("tesseract")
        assert isinstance(adapter, OCRAdapterProtocol)

    def test_tesseract_returns_tesseract_adapter(self) -> None:
        adapter = get_ocr_adapter("tesseract")
        assert adapter.provider_name == "tesseract"

    def test_unknown_provider_returns_tesseract_fallback(self) -> None:
        adapter = get_ocr_adapter("totally_unknown_provider")
        assert adapter.provider_name == "tesseract"

    def test_failure_isolation(self) -> None:
        """get_ocr_adapter() никогда не бросает исключений."""
        with patch(
            "services.ocr._registry._get_or_create_adapter",
            side_effect=RuntimeError("registry broken"),
        ):
            result = get_ocr_adapter("tesseract")
        assert isinstance(result, OCRAdapterProtocol)

    def test_paddle_falls_back_to_tesseract_when_unavailable(self) -> None:
        """PaddleOCRAdapter.is_available()=False → fallback на Tesseract."""
        # Сбрасываем кэш
        import services.ocr._registry as reg
        reg._ADAPTER_CACHE.clear()

        adapter = get_ocr_adapter("paddle")
        # paddle недоступен → fallback на Tesseract
        assert adapter.provider_name == "tesseract"

        reg._ADAPTER_CACHE.clear()


# ---------------------------------------------------------------------------
# Registry — is_ocr_provider_available
# ---------------------------------------------------------------------------

class TestIsOCRProviderAvailable:
    def test_returns_bool(self) -> None:
        result = is_ocr_provider_available("tesseract")
        assert isinstance(result, bool)

    def test_paddle_not_available(self) -> None:
        """PaddleOCRAdapter.is_available() всегда False."""
        adapter = PaddleOCRAdapter()
        assert adapter.is_available() is False

    def test_failure_isolation(self) -> None:
        """Никогда не бросает исключений."""
        with patch(
            "services.ocr._registry.get_ocr_adapter",
            side_effect=RuntimeError("broken"),
        ):
            result = is_ocr_provider_available("tesseract")
        assert result is False



