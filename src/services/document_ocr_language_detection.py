# src/services/document_ocr_language_detection.py

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageFilter, ImageOps, ImageSequence
from pdf2image import convert_from_bytes

from core.exceptions import PermanentError, TransientError

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 3
DEFAULT_MAX_IMAGES = 3
DEFAULT_DPI = 220
DEFAULT_MAX_TEXT_CHARS = 12_000
DEFAULT_TESSERACT_TIMEOUT_SECONDS = 20
DEFAULT_TESSERACT_LIST_LANGS_TIMEOUT_SECONDS = 10

DEFAULT_TESSERACT_LANGUAGES: tuple[str, ...] = (
    "eng",
    "rus",
    "deu",
    "fra",
    "tur",
    "ara",
)

DEFAULT_TESSERACT_PSM = "6"
DEFAULT_TESSERACT_OEM = "1"

SUPPORTED_IMAGE_TYPES = {
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "bmp",
    "webp",
}


@dataclass(slots=True)
class QuickOCRResult:
    text: str
    pages_processed: int
    engine: str
    languages_used: tuple[str, ...]


def extract_quick_ocr_text_for_language_detection(
    *,
    source_bytes: bytes,
    source_filename: str,
    origin_filetype: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_images: int = DEFAULT_MAX_IMAGES,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    tesseract_languages: tuple[str, ...] = DEFAULT_TESSERACT_LANGUAGES,
) -> str:
    """
    Быстро получить OCR text sample для language detection.

    Поддерживает:
    - PDF: OCR только первых `max_pages` страниц;
    - image / scanned formats: OCR первых `max_images` кадров/изображений.

    Возвращает:
    - очищенный текстовый сэмпл, пригодный для language detection.

    Исключения:
    - PermanentError: неподдерживаемый или битый вход;
    - TransientError: временные проблемы OCR/runtime.
    """
    if not source_bytes:
        raise PermanentError("OCR source bytes are empty")

    normalized_type = (origin_filetype or "").strip().lower()
    filename = source_filename or "document"

    _ensure_tesseract_available()
    resolved_languages = _resolve_tesseract_languages(tesseract_languages)

    if normalized_type == "pdf":
        result = _ocr_pdf_bytes(
            pdf_bytes=source_bytes,
            max_pages=max_pages,
            max_text_chars=max_text_chars,
            tesseract_languages=resolved_languages,
        )
        logger.info(
            "Quick OCR completed for PDF",
            extra={
                "source_filename": filename,
                "origin_filetype": normalized_type,
                "pages_processed": result.pages_processed,
                "engine": result.engine,
                "languages_used": list(result.languages_used),
                "text_length": len(result.text),
            },
        )
        return result.text

    if normalized_type in SUPPORTED_IMAGE_TYPES:
        result = _ocr_image_bytes(
            image_bytes=source_bytes,
            image_format=normalized_type,
            max_images=max_images,
            max_text_chars=max_text_chars,
            tesseract_languages=resolved_languages,
        )
        logger.info(
            "Quick OCR completed for image",
            extra={
                "source_filename": filename,
                "origin_filetype": normalized_type,
                "pages_processed": result.pages_processed,
                "engine": result.engine,
                "languages_used": list(result.languages_used),
                "text_length": len(result.text),
            },
        )
        return result.text

    raise PermanentError(
        f"Unsupported file type for OCR language detection: {normalized_type or 'unknown'}. "
        f"Supported types: 'pdf', {sorted(SUPPORTED_IMAGE_TYPES)}. "
        f"Office documents must be converted to PDF before calling this function."
    )


def _ocr_pdf_bytes(
    *,
    pdf_bytes: bytes,
    max_pages: int,
    max_text_chars: int,
    tesseract_languages: tuple[str, ...],
) -> QuickOCRResult:
    try:
        pages = convert_from_bytes(
            pdf_bytes,
            dpi=DEFAULT_DPI,
            first_page=1,
            last_page=max_pages,
            fmt="png",
            thread_count=1,
            grayscale=True,
            use_pdftocairo=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as e:
        raise TransientError("PDF rasterization timed out for OCR") from e
    except Exception as e:
        raise PermanentError(f"Failed to rasterize PDF for OCR: {e}") from e

    if not pages:
        raise PermanentError("PDF rasterization produced no pages for OCR")

    texts: list[str] = []
    processed = 0
    accumulated_chars = 0

    for page in pages:
        processed += 1
        text = _run_tesseract_on_image(
            page,
            tesseract_languages=tesseract_languages,
        )
        if text:
            texts.append(text)
            accumulated_chars += len(text)

        if accumulated_chars >= max_text_chars:
            break

    merged = _normalize_ocr_text("\n".join(texts), max_chars=max_text_chars)

    if not merged.strip():
        raise PermanentError("Quick OCR for PDF produced empty text")

    return QuickOCRResult(
        text=merged,
        pages_processed=processed,
        engine="tesseract",
        languages_used=tesseract_languages,
    )


def _ocr_image_bytes(
    *,
    image_bytes: bytes,
    image_format: str,
    max_images: int,
    max_text_chars: int,
    tesseract_languages: tuple[str, ...],
) -> QuickOCRResult:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            frames = list(_iter_limited_frames(img, max_images))
    except Exception as e:
        raise PermanentError(f"Failed to open image for OCR: {e}") from e

    if not frames:
        raise PermanentError("Image OCR source produced no frames")

    texts: list[str] = []
    processed = 0
    accumulated_chars = 0

    for frame in frames:
        processed += 1
        text = _run_tesseract_on_image(
            frame,
            tesseract_languages=tesseract_languages,
        )
        if text:
            texts.append(text)
            accumulated_chars += len(text)

        if accumulated_chars >= max_text_chars:
            break

    merged = _normalize_ocr_text("\n".join(texts), max_chars=max_text_chars)

    if not merged.strip():
        raise PermanentError(
            f"Quick OCR for image type '{image_format}' produced empty text"
        )

    return QuickOCRResult(
        text=merged,
        pages_processed=processed,
        engine="tesseract",
        languages_used=tesseract_languages,
    )


def _iter_limited_frames(image: Image.Image, limit: int) -> Iterable[Image.Image]:
    count = 0
    for frame in ImageSequence.Iterator(image):
        yield frame.copy()
        count += 1
        if count >= limit:
            break

    if count == 0:
        yield image.copy()


def _run_tesseract_on_image(
    image: Image.Image,
    *,
    tesseract_languages: tuple[str, ...],
) -> str:
    prepared = _prepare_image_for_ocr(image)

    with tempfile.TemporaryDirectory(prefix="quick-ocr-") as tmpdir:
        input_path = os.path.join(tmpdir, "input.png")
        output_base = os.path.join(tmpdir, "ocr_out")

        prepared.save(input_path, format="PNG")

        cmd = [
            "tesseract",
            input_path,
            output_base,
            "--oem",
            DEFAULT_TESSERACT_OEM,
            "--psm",
            DEFAULT_TESSERACT_PSM,
            "-l",
            "+".join(tesseract_languages),
        ]

        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=DEFAULT_TESSERACT_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
        except subprocess.TimeoutExpired as e:
            raise TransientError("Tesseract OCR timed out") from e
        except Exception as e:
            raise TransientError(f"Failed to execute Tesseract OCR: {e}") from e

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise PermanentError(
                f"Tesseract OCR failed with exit code {completed.returncode}: {stderr}"
            )

        output_txt = f"{output_base}.txt"
        if not os.path.exists(output_txt):
            raise PermanentError("Tesseract OCR did not produce output text file")

        try:
            with open(output_txt, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            raise TransientError(f"Failed to read OCR output text: {e}") from e


def _prepare_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Лёгкая и быстрая preprocessing-подготовка:
    - exif transpose;
    - grayscale;
    - autocontrast;
    - upscale небольших изображений;
    - median filter;
    - мягкая бинаризация для лучшей читаемости.
    """
    img = ImageOps.exif_transpose(image)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)

    min_width = 1600
    if img.width < min_width:
        scale = min_width / max(img.width, 1)
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.Resampling.LANCZOS,
        )

    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.point(lambda p: 255 if p > 180 else 0)

    return img


def _normalize_ocr_text(text: str, *, max_chars: int) -> str:
    """
    Нормализация OCR output для language detection:
    - схлопываем пробелы;
    - выкидываем короткие/шумовые строки;
    - ограничиваем итоговый размер.
    """
    if not text:
        return ""

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line = re.sub(r"\s+", " ", line)

        alnum_count = sum(ch.isalnum() for ch in line)
        if alnum_count < 3:
            continue

        lines.append(line)

    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip()

    return normalized


def _resolve_tesseract_languages(
    requested_languages: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Оставить только реально доступные языки Tesseract.

    Если часть language packs не установлена, исключаем их из hint.
    Если не осталось ни одного языка, явно падаем.
    """
    available = _get_installed_tesseract_languages()

    resolved = tuple(
        lang.strip().lower()
        for lang in requested_languages
        if lang and lang.strip().lower() in available
    )

    if resolved:
        return resolved

    if "eng" in available:
        return ("eng",)

    raise PermanentError(
        "No requested Tesseract language packs are installed. "
        f"Requested={requested_languages}, available={sorted(available)}"
    )


def _get_installed_tesseract_languages() -> set[str]:
    """
    Получить список установленных языков Tesseract.

    У некоторых сборок `tesseract --list-langs` ведёт себя нестабильно,
    поэтому пробуем две команды.
    """
    commands = [
        ["tesseract", "--list-langs"],
        ["tesseract", "--list-langs", "-l", "eng"],
    ]

    for cmd in commands:
        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=DEFAULT_TESSERACT_LIST_LANGS_TIMEOUT_SECONDS,
                check=False,
                text=True,
            )
        except Exception:
            continue

        if completed.returncode != 0:
            continue

        combined = "\n".join(
            part for part in (completed.stdout, completed.stderr) if part
        )

        languages = {
            line.strip().lower()
            for line in combined.splitlines()
            if line.strip()
            and "list of available languages" not in line.lower()
            and re.fullmatch(r"[A-Za-z0-9_]+", line.strip()) is not None
        }

        if languages:
            return languages

    raise PermanentError("Failed to determine installed Tesseract languages")


def _ensure_tesseract_available() -> None:
    """
    Проверяем наличие tesseract в PATH.
    """
    if shutil.which("tesseract") is None:
        raise PermanentError("Tesseract executable is not available in PATH")



        