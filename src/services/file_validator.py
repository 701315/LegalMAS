# src/services/file_validator.py

"""
File Validation Service.

Отвечает за первичную проверку файлов перед импортом и загрузкой в MinIO,
чтобы в пайплайн не попали подозрительные, пустые или неподдерживаемые
форматы.

Проверки:
  - extension whitelist (settings.IMPORT_ALLOWED_EXTENSIONS);
  - размер файла (IMPORT_MAX_FILE_SIZE_MB);
  - magic bytes (соответствие содержимого заявленному типу);
  - нулевая длина;
  - скрытые/системные файлы (__MACOSX, .DS_Store, Thumbs.db и т.п.).

Использование:
  - Import Worker (Stage 3) вызывает validate_file(...) для каждого файла
    из ZIP/папки и по результату:
      * SKIP — игнорирует скрытые/системные файлы;
      * QUARANTINE — помечает файл как проблемный и не отправляет в MinIO;
      * VALID — определяет internal filetype (pdf/docx/doc/xlsx/image/unknown),
        который дальше влияет на роутинг:
          - can_process_directly(filetype) → сразу в Extractor (Stage 4, PDF);
          - needs_conversion(filetype) → через конвертацию в PDF;
          - is_spreadsheet/is_image → отдельные ветки.

Важно:
  - сервис НЕ делает бизнес-роутинг по folder_path; он только валидирует файлы.
    folder_path сохраняется Import Worker’ом как сигнал для L1 Rule-Based
    Classifier (Stage 6) через YAML registry (folder_patterns).
"""

import os
from dataclasses import dataclass
from enum import Enum

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class FileStatus(str, Enum):
    """Result of file validation."""

    VALID = "valid"
    QUARANTINE = "quarantine"
    SKIP = "skip"  # hidden files, __MACOSX, etc.


@dataclass
class ValidationResult:
    """Result of validating a single file."""

    status: FileStatus
    filetype: str  # pdf | docx | xlsx | image | doc | unknown
    reason: str | None = None
    original_extension: str | None = None


# ─── Magic bytes ──────────────────────────────────────────────────────────────
MAGIC_BYTES = {
    "pdf": b"%PDF",
    "zip": b"PK\x03\x04",  # DOCX, XLSX, PPTX — all ZIP-based
    "png": b"\x89PNG",
    "jpg": b"\xff\xd8\xff",
    "tiff_le": b"II*\x00",  # Little-endian TIFF
    "tiff_be": b"MM\x00*",  # Big-endian TIFF
    "doc": b"\xd0\xcf\x11\xe0",  # DOC (OLE2)
}

# Extension → internal file type
EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".tif": "image",
}


# ─── Public helpers ───────────────────────────────────────────────────────────


def get_allowed_extensions() -> set[str]:
    return {
        ext.strip().lower() for ext in settings.IMPORT_ALLOWED_EXTENSIONS.split(",") if ext.strip()
    }


def validate_file(filepath: str) -> ValidationResult:
    """
    Validate a file for import.

    Checks (in order):
      1. Not a hidden, temp, or system file → SKIP
      2. Extension is in allowlist → else QUARANTINE
      3. File exists and is not empty → else QUARANTINE
      4. File size within limits → else QUARANTINE
      5. Magic bytes check:
         - for большинство типов жёстко проверяем соответствие,
         - но для .doc допускаем:
             * старый OLE2 DOC,
             * ZIP (фактически DOCX при расширении .doc),
             * а для странных, но открывающихся файлов — не карантин, а VALID/unknown.
    """
    filename = os.path.basename(filepath)

    # 1. Skip hidden, temp, system files
    if filename.startswith(".") or filename.startswith("~"):
        return ValidationResult(
            status=FileStatus.SKIP,
            filetype="unknown",
            reason="Hidden or temporary file",
        )
    if "__MACOSX" in filepath or ".DS_Store" in filename or "Thumbs.db" in filename:
        return ValidationResult(
            status=FileStatus.SKIP,
            filetype="unknown",
            reason="System file",
        )

    # 2. Extension check
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    allowed = get_allowed_extensions()
    if ext not in allowed:
        return ValidationResult(
            status=FileStatus.QUARANTINE,
            filetype="unknown",
            reason=(
                f"Unsupported file extension '{ext}'. " f"Allowed: {', '.join(sorted(allowed))}"
            ),
            original_extension=ext,
        )
    filetype = EXTENSION_MAP.get(ext, "unknown")

    # 3. Existence + zero-length
    if not os.path.exists(filepath):
        return ValidationResult(
            status=FileStatus.QUARANTINE,
            filetype=filetype,
            reason="File does not exist",
            original_extension=ext,
        )
    filesize = os.path.getsize(filepath)
    if filesize == 0:
        return ValidationResult(
            status=FileStatus.QUARANTINE,
            filetype=filetype,
            reason="File is empty (0 bytes)",
            original_extension=ext,
        )

    # 4. Size limit
    max_bytes = settings.IMPORT_MAX_FILE_SIZE_MB * 1024 * 1024
    if filesize > max_bytes:
        return ValidationResult(
            status=FileStatus.QUARANTINE,
            filetype=filetype,
            reason=(
                f"File too large: {filesize / 1024 / 1024:.1f} MB "
                f"(max {settings.IMPORT_MAX_FILE_SIZE_MB} MB)"
            ),
            original_extension=ext,
        )

    # 5. Magic bytes
    magic_ok, detected_type = _check_magic_bytes(filepath, ext)

    if not magic_ok:
        # Для .doc и похожих кейсов мы больше не отправляем в жёсткий карантин,
        # а пропускаем дальше как unknown, чтобы downstream решил, что делать.
        logger.warning(
            "File content does not strictly match extension; passing as unknown",
            filename=filename,
            extension=ext,
        )
        return ValidationResult(
            status=FileStatus.VALID,
            filetype="unknown",
            reason=(
                f"File content does not strictly match extension '{ext}'. "
                f"File may be mislabeled, passing as 'unknown'."
            ),
            original_extension=ext,
        )

    # Если по магии выяснилось, что это фактически DOCX при расширении .doc —
    # переопределяем filetype, чтобы роутер знал, как обрабатывать.
    if detected_type and detected_type != filetype:
        logger.info(
            "File extension and magic type differ; using detected type",
            filename=filename,
            extension=ext,
            detected_type=detected_type,
        )
        filetype = detected_type

    return ValidationResult(
        status=FileStatus.VALID,
        filetype=filetype,
        original_extension=ext,
    )


def can_process_directly(filetype: str) -> bool:
    """True if the file goes directly to Extractor (Stage 4)."""
    return filetype == "pdf"


def needs_conversion(filetype: str) -> bool:
    """True if DOCX/DOC — needs PDF conversion before extraction."""
    return filetype in ("docx", "doc")


def is_spreadsheet(filetype: str) -> bool:
    """True if XLSX/XLS — stored, processing deferred."""
    return filetype in ("xlsx", "xls")


def is_image(filetype: str) -> bool:
    """True if image — requires OCR pipeline."""
    return filetype == "image"


# ─── Internal ─────────────────────────────────────────────────────────────────


def _check_magic_bytes(filepath: str, extension: str) -> tuple[bool, str | None]:
    """
    Verify that file's magic bytes match its extension.

    Returns:
      (ok, detected_type)

      ok:
        - True  — магия приемлема для этого расширения;
        - False — магия явно не подходит (файл странный).
      detected_type:
        - конкретный тип, если удалось однозначно понять (например, 'docx'),
        - None, если дополнительных выводов нет.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
        if len(header) < 4:
            return False, None

        if extension == ".pdf":
            return header[:4] == MAGIC_BYTES["pdf"], "pdf" if header[:4] == MAGIC_BYTES[
                "pdf"
            ] else None

        if extension in (".docx", ".xlsx", ".xls"):
            # DOCX and XLSX are ZIP-based (PK magic)
            if header[:4] == MAGIC_BYTES["zip"]:
                mapped = EXTENSION_MAP.get(extension, "unknown")
                return True, mapped
            return False, None

        if extension == ".doc":
            # Классический бинарный DOC (OLE2)
            if header[:4] == MAGIC_BYTES["doc"]:
                return True, "doc"
            # Нередко встречается DOCX с расширением .DOC — это ZIP (PK)
            if header[:4] == MAGIC_BYTES["zip"]:
                return True, "docx"
            # Иные варианты — странный, но потенциально открывающийся файл
            return False, None

        if extension == ".png":
            return header[:4] == MAGIC_BYTES["png"], "image" if header[:4] == MAGIC_BYTES[
                "png"
            ] else None

        if extension in (".jpg", ".jpeg"):
            if header[:3] == MAGIC_BYTES["jpg"]:
                return True, "image"
            return False, None

        if extension in (".tiff", ".tif"):
            if header[:4] in (MAGIC_BYTES["tiff_le"], MAGIC_BYTES["tiff_be"]):
                return True, "image"
            return False, None

        # Unknown but allowed — accept, но без дополнительного типа
        return True, None

    except OSError:
        return False, None
