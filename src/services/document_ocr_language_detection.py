# src/services/document_ocr_language_detection.py

"""
Быстрое OCR-извлечение текста для определения языка документа.

Модуль предоставляет утилиты для запуска Tesseract OCR над PDF-файлами
и изображениями с целью получения текстового сэмпла, достаточного для
последующего language detection.

Основные принципы:
- Обрабатываются только первые N страниц/кадров — скорость важнее полноты;
- Изображения масштабируются до рабочего диапазона перед OCR;
- Временные файлы изолированы в tempdir и удаляются автоматически;
- Все ошибки классифицируются как PermanentError или TransientError.

Зависимости:
- tesseract-ocr должен быть установлен и доступен в PATH;
- language packs устанавливаются отдельно (tesseract-ocr-eng, tesseract-ocr-rus, и т.д.);
- pdf2image использует pdftocairo для рендеринга PDF.
"""

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

from PIL import Image, ImageOps, ImageSequence
from pdf2image import convert_from_bytes

from core.exceptions import PermanentError, TransientError

logger = logging.getLogger(__name__)

# ─── Настройки обработки страниц ──────────────────────────────────────────────

DEFAULT_MAX_PAGES = 3
"""Максимальное количество страниц PDF для OCR."""

DEFAULT_MAX_IMAGES = 3
"""Максимальное количество кадров изображения для OCR."""

DEFAULT_DPI = 150
"""
DPI для рендеринга PDF в изображение.
150 DPI достаточно для language detection и существенно быстрее, чем 220+.
"""

DEFAULT_MAX_TEXT_CHARS = 12_000
"""Максимальный размер итогового текстового сэмпла в символах."""

# ─── Настройки масштабирования изображений ────────────────────────────────────

DEFAULT_OCR_TARGET_WIDTH = 1200
"""
Максимальная ширина изображения перед OCR в пикселях.
Изображения шире этого значения будут уменьшены.
"""

DEFAULT_OCR_MAX_HEIGHT = 2000
"""
Максимальная высота изображения перед OCR в пикселях.
Изображения выше этого значения будут уменьшены.
"""

DEFAULT_OCR_MIN_WIDTH = 800
"""
Минимальная ширина изображения перед OCR в пикселях.
Изображения (thumbnails) уже этого значения будут увеличены.
"""

# ─── Настройки Tesseract ──────────────────────────────────────────────────────

DEFAULT_TESSERACT_TIMEOUT_SECONDS = 60
"""Таймаут на один вызов Tesseract OCR в секундах."""

DEFAULT_TESSERACT_LIST_LANGS_TIMEOUT_SECONDS = 10
"""Таймаут на получение списка установленных языков Tesseract в секундах."""

DEFAULT_TESSERACT_LANGUAGES: tuple[str, ...] = (
    "eng",
    "rus",
    "deu",
    "fra",
    "tur",
    "ara",
)
"""
Языки Tesseract, используемые по умолчанию для OCR.
Фактически применяются только те, language packs которых установлены в системе.
"""

DEFAULT_TESSERACT_PSM = "6"
"""
Page Segmentation Mode для Tesseract.
6 — предполагает единый блок текста; подходит для большинства документов.
"""

DEFAULT_TESSERACT_OEM = "1"
"""
OCR Engine Mode для Tesseract.
1 — LSTM neural net; наилучшее качество распознавания.
"""

# ─── Поддерживаемые форматы изображений ──────────────────────────────────────

SUPPORTED_IMAGE_TYPES = {
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "bmp",
    "webp",
}
"""Расширения файлов изображений, поддерживаемых для прямого OCR."""


# ─── Результат OCR ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class QuickOCRResult:
    """
    Результат быстрого OCR для language detection.

    Attributes:
        text: Нормализованный текстовый сэмпл.
        pages_processed: Количество обработанных страниц или кадров.
        engine: Название использованного OCR-движка (например, 'tesseract').
        languages_used: Языковые пакеты, переданные в OCR-движок.
    """

    text: str
    pages_processed: int
    engine: str
    languages_used: tuple[str, ...]


# ─── Публичный интерфейс ──────────────────────────────────────────────────────


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
    Извлечь текстовый сэмпл из документа или изображения для language detection.

    Функция запускает Tesseract OCR над первыми страницами/кадрами входного файла
    и возвращает нормализованный текст, пригодный для последующего определения языка.

    Поддерживаемые форматы:
        - PDF: обрабатываются первые `max_pages` страниц;
        - Изображения (png, jpg, jpeg, tif, tiff, bmp, webp):
          обрабатываются первые `max_images` кадров.

    Office-документы (docx, xlsx и т.д.) должны быть предварительно
    сконвертированы в PDF до вызова этой функции.

    Args:
        source_bytes: Бинарное содержимое файла.
        source_filename: Имя файла (используется только для логирования).
        origin_filetype: Расширение файла без точки в нижнем регистре
            (например, 'pdf', 'png').
        max_pages: Максимальное количество страниц PDF для OCR.
        max_images: Максимальное количество кадров изображения для OCR.
        max_text_chars: Максимальный размер итогового текста в символах.
        tesseract_languages: Предпочтительные языки Tesseract.
            Фактически используются только установленные в системе.

    Returns:
        Нормализованный текстовый сэмпл.

    Raises:
        PermanentError: Входные данные пусты, формат не поддерживается,
            файл повреждён или OCR не дал результата.
        TransientError: Временная ошибка при выполнении OCR
            (таймаут, сбой процесса).
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


# ─── Внутренние реализации ────────────────────────────────────────────────────


def _ocr_pdf_bytes(
    *,
    pdf_bytes: bytes,
    max_pages: int,
    max_text_chars: int,
    tesseract_languages: tuple[str, ...],
) -> QuickOCRResult:
    """
    Выполнить OCR над PDF-файлом.

    Рендерит первые `max_pages` страниц PDF в изображения и запускает
    Tesseract на каждой странице до достижения `max_text_chars` символов.

    Args:
        pdf_bytes: Бинарное содержимое PDF-файла.
        max_pages: Максимальное количество страниц для обработки.
        max_text_chars: Лимит символов итогового текста.
        tesseract_languages: Языки для передачи в Tesseract.

    Returns:
        QuickOCRResult с извлечённым текстом и метаданными.

    Raises:
        PermanentError: PDF повреждён, не содержит страниц или OCR дал пустой результат.
        TransientError: Таймаут рендеринга PDF.
    """
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
        text = _run_tesseract_on_image(page, tesseract_languages=tesseract_languages)
        if text:
            texts.append(text)
            accumulated_chars += len(text)

        if accumulated_chars >= max_text_chars:
            break

    merged = _normalize_ocr_text("\n".join(texts), max_chars=max_text_chars)

    if not merged.strip():
        raise PermanentError(
            f"Quick OCR for PDF produced empty text "
            f"(processed {processed} page(s), dpi={DEFAULT_DPI})"
        )

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
    """
    Выполнить OCR над изображением или последовательностью кадров.

    Открывает изображение и обрабатывает первые `max_images` кадров
    (актуально для многостраничных TIFF и анимированных форматов).

    Args:
        image_bytes: Бинарное содержимое файла изображения.
        image_format: Расширение формата (используется в сообщениях об ошибках).
        max_images: Максимальное количество кадров для обработки.
        max_text_chars: Лимит символов итогового текста.
        tesseract_languages: Языки для передачи в Tesseract.

    Returns:
        QuickOCRResult с извлечённым текстом и метаданными.

    Raises:
        PermanentError: Файл повреждён, не содержит кадров или OCR дал пустой результат.
        TransientError: Временная ошибка при выполнении OCR.
    """
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
        text = _run_tesseract_on_image(frame, tesseract_languages=tesseract_languages)
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
    """
    Итерировать по кадрам изображения с ограничением количества.

    Для одиночных изображений возвращает единственный кадр.
    Для многокадровых форматов (TIFF, GIF) возвращает не более `limit` кадров.

    Args:
        image: Открытый объект изображения Pillow.
        limit: Максимальное количество кадров для извлечения.

    Yields:
        Копии кадров изображения.
    """
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
    """
    Запустить Tesseract OCR на одном изображении.

    Сохраняет предобработанное изображение во временный файл,
    запускает tesseract как subprocess и читает результирующий текстовый файл.

    Tesseract запускается с OMP_THREAD_LIMIT=1 для снижения конкуренции
    между параллельными Celery-воркерами за ресурсы CPU.

    Args:
        image: Изображение для распознавания.
        tesseract_languages: Языки для передачи через флаг `-l`.

    Returns:
        Сырой текст, извлечённый Tesseract (до нормализации).

    Raises:
        PermanentError: Tesseract завершился с ненулевым кодом или
            не создал выходной файл.
        TransientError: Таймаут или сбой при запуске процесса Tesseract.
    """
    prepared = _prepare_image_for_ocr(image)

    logger.debug(
        "Running Tesseract OCR",
        extra={
            "image_size": prepared.size,
            "languages": tesseract_languages,
            "timeout": DEFAULT_TESSERACT_TIMEOUT_SECONDS,
        },
    )

    with tempfile.TemporaryDirectory(prefix="quick-ocr-") as tmpdir:
        input_path = os.path.join(tmpdir, "input.png")
        output_base = os.path.join(tmpdir, "ocr_out")

        prepared.save(input_path, format="PNG")

        cmd = [
            "tesseract",
            input_path,
            output_base,
            "--oem", DEFAULT_TESSERACT_OEM,
            "--psm", DEFAULT_TESSERACT_PSM,
            "-l", "+".join(tesseract_languages),
        ]

        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=DEFAULT_TESSERACT_TIMEOUT_SECONDS,
                check=False,
                text=True,
                env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            )
        except subprocess.TimeoutExpired as e:
            logger.error(
                "Tesseract OCR timed out",
                extra={
                    "image_size": prepared.size,
                    "languages": tesseract_languages,
                    "timeout": DEFAULT_TESSERACT_TIMEOUT_SECONDS,
                },
            )
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
    Подготовить изображение к OCR.

    Применяет следующие преобразования:
    1. EXIF transpose — корректирует ориентацию по метаданным;
    2. Grayscale — переводит в оттенки серого;
    3. Масштабирование — downscale если изображение слишком большое,
       upscale если изображение-thumbnail слишком маленькое;
    4. Autocontrast — растягивает гистограмму для улучшения контраста;
    5. Бинаризация — пороговая фильтрация для чёткости текста.

    Масштабирование выполняется одним проходом:
    - если ширина > DEFAULT_OCR_TARGET_WIDTH или высота > DEFAULT_OCR_MAX_HEIGHT
      — изображение уменьшается с сохранением пропорций;
    - если ширина < DEFAULT_OCR_MIN_WIDTH
      — изображение увеличивается до минимальной ширины.

    Args:
        image: Исходное изображение в любом режиме и размере.

    Returns:
        Подготовленное grayscale-изображение, готовое для передачи в Tesseract.
    """
    img = ImageOps.exif_transpose(image)
    img = img.convert("L")

    w, h = img.width, img.height
    scale = 1.0

    if w > DEFAULT_OCR_TARGET_WIDTH or h > DEFAULT_OCR_MAX_HEIGHT:
        scale = min(
            DEFAULT_OCR_TARGET_WIDTH / max(w, 1),
            DEFAULT_OCR_MAX_HEIGHT / max(h, 1),
        )
    elif w < DEFAULT_OCR_MIN_WIDTH:
        scale = DEFAULT_OCR_MIN_WIDTH / max(w, 1)

    if scale != 1.0:
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    img = ImageOps.autocontrast(img)
    img = img.point(lambda p: 255 if p > 180 else 0)

    return img


def _normalize_ocr_text(text: str, *, max_chars: int) -> str:
    """
    Нормализовать сырой OCR-текст для language detection.

    Выполняет следующие преобразования:
    - удаляет пустые строки;
    - схлопывает множественные пробелы внутри строк;
    - отфильтровывает шумовые строки (менее 3 буквенно-цифровых символов);
    - схлопывает множественные пустые строки (более 2 подряд);
    - обрезает результат до `max_chars` символов.

    Args:
        text: Сырой текст из OCR-движка.
        max_chars: Максимальное количество символов в результате.

    Returns:
        Нормализованный текст или пустую строку, если входной текст пуст
        или содержит только шум.
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
    Определить фактически доступные языки Tesseract из запрошенных.

    Сверяет запрошенные языки со списком установленных language packs
    и возвращает только доступные. Если ни один из запрошенных языков
    не установлен, возвращает ('eng',) как fallback при наличии английского.

    Args:
        requested_languages: Предпочтительные языки для OCR.

    Returns:
        Кортеж языков, доступных в текущей системе.

    Raises:
        PermanentError: Ни один из запрошенных языков не установлен
            и английский также недоступен.
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
    Получить множество установленных языковых пакетов Tesseract.

    Пробует две команды последовательно, так как поведение
    `tesseract --list-langs` различается между версиями и сборками.
    Вывод может приходить в stdout или stderr в зависимости от версии.

    Returns:
        Множество строк с кодами языков в нижнем регистре (например, {'eng', 'rus'}).

    Raises:
        PermanentError: Не удалось получить список языков ни одним из способов.
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
    Проверить наличие исполняемого файла tesseract в системном PATH.

    Raises:
        PermanentError: Tesseract не найден в PATH.
    """
    if shutil.which("tesseract") is None:
        raise PermanentError("Tesseract executable is not available in PATH")
        