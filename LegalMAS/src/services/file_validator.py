"""
File Validation Service.

Checks files before import:
  - Extension whitelist
  - File size limits
  - Magic bytes verification (is the file really what the extension claims?)
  - Zero-length detection
  - Hidden/system file detection

Used by Import Worker (Stage 3) to gate files before MinIO upload.

NOTE on folder_path routing:
  Document.folder_path (preserved from ZIP structure) is used downstream
  by the L1 Rule-Based Classifier (Stage 6) via folder_patterns in the
  YAML registry (playbooks/document_types/registry.yaml).
  Example: "02. Contracts/SPA/" → boosts classification to contract1.1spa.
  This service does NOT perform routing — it only validates files.
  Routing signals are preserved via folder_path in Import Worker.
"""

import os
from dataclasses import dataclass
from enum import Enum

from src.core.config import settings
from src.core.logging import get_logger

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
    filetype: str  # pdf | docx | xlsx | image | unknown
    reason: str = None
    original_extension: str = None


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


def get_allowed_extensions() -> set:
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
      5. Magic bytes match extension → else QUARANTINE

    Returns ValidationResult with status, filetype, reason, original_extension.
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
            reason=f"Unsupported file extension '{ext}'. " f"Allowed: {', '.join(sorted(allowed))}",
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
    if not _check_magic_bytes(filepath, ext):
        return ValidationResult(
            status=FileStatus.QUARANTINE,
            filetype=filetype,
            reason=(
                f"File content does not match extension '{ext}'. "
                f"File may be corrupted or mislabeled."
            ),
            original_extension=ext,
        )

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


def _check_magic_bytes(filepath: str, extension: str) -> bool:
    """Verify that file's magic bytes match its extension."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
        if len(header) < 4:
            return False

        if extension == ".pdf":
            return header[:4] == MAGIC_BYTES["pdf"]
        if extension in (".docx", ".xlsx", ".xls"):
            # DOCX and XLSX are ZIP-based (PK magic)
            return header[:4] == MAGIC_BYTES["zip"]
        if extension == ".doc":
            return header[:4] == MAGIC_BYTES["doc"]
        if extension == ".png":
            return header[:4] == MAGIC_BYTES["png"]
        if extension in (".jpg", ".jpeg"):
            return header[:3] == MAGIC_BYTES["jpg"]
        if extension in (".tiff", ".tif"):
            return header[:4] == MAGIC_BYTES["tiff_le"] or header[:4] == MAGIC_BYTES["tiff_be"]
        # Unknown but allowed — accept
        return True
    except OSError:
        return False
