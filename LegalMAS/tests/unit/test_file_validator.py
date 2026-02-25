"""
Unit tests for File Validation Service.
"""

import io
import os
import tempfile
import zipfile

import pytest

from src.services.file_validator import (
    FileStatus,
    can_process_directly,
    is_image,
    is_spreadsheet,
    needs_conversion,
    validate_file,
)


@pytest.fixture
def tmpdir():
    """Create a temporary directory for test files."""
    d = tempfile.mkdtemp(prefix="mas_test_")
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def write_file(directory: str, name: str, content: bytes) -> str:
    """Helper: write bytes to a file and return its path."""
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


class TestValidateFile:
    def test_valid_pdf(self, tmpdir):
        path = write_file(tmpdir, "test.pdf", b"%PDF-1.4 content here")
        result = validate_file(path)
        assert result.status == FileStatus.VALID
        assert result.filetype == "pdf"

    def test_empty_file(self, tmpdir):
        path = write_file(tmpdir, "empty.pdf", b"")
        result = validate_file(path)
        assert result.status == FileStatus.QUARANTINE
        assert "empty" in result.reason.lower()

    def test_corrupted_pdf(self, tmpdir):
        """File with .pdf extension but wrong content → quarantine."""
        path = write_file(tmpdir, "fake.pdf", b"This is not a PDF")
        result = validate_file(path)
        assert result.status == FileStatus.QUARANTINE
        assert "content does not match" in result.reason.lower()

    def test_unsupported_extension(self, tmpdir):
        path = write_file(tmpdir, "notes.txt", b"some text notes")
        result = validate_file(path)
        assert result.status == FileStatus.QUARANTINE
        assert "unsupported" in result.reason.lower()

    def test_hidden_file(self, tmpdir):
        path = write_file(tmpdir, ".hidden", b"secret")
        result = validate_file(path)
        assert result.status == FileStatus.SKIP

    def test_macosx_file(self, tmpdir):
        """__MACOSX paths should be skipped."""
        macos_dir = os.path.join(tmpdir, "__MACOSX")
        os.makedirs(macos_dir)
        path = write_file(macos_dir, "file.pdf", b"%PDF-1.4")
        result = validate_file(path)
        assert result.status == FileStatus.SKIP

    def test_ds_store(self, tmpdir):
        path = write_file(tmpdir, ".DS_Store", b"\x00\x00\x00\x01")
        result = validate_file(path)
        assert result.status == FileStatus.SKIP

    def test_temp_file(self, tmpdir):
        """Tilde-prefixed temp files should be skipped."""
        path = write_file(tmpdir, "~document.docx", b"PK\x03\x04temp")
        result = validate_file(path)
        assert result.status == FileStatus.SKIP

    def test_valid_docx(self, tmpdir):
        """Valid DOCX (ZIP-based) should be accepted."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types></Types>',
            )
        path = write_file(tmpdir, "document.docx", buf.getvalue())
        result = validate_file(path)
        assert result.status == FileStatus.VALID
        assert result.filetype == "docx"

    def test_valid_png(self, tmpdir):
        """Valid PNG should be accepted."""
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        path = write_file(tmpdir, "scan.png", png_header)
        result = validate_file(path)
        assert result.status == FileStatus.VALID
        assert result.filetype == "image"

    def test_nonexistent_file(self):
        result = validate_file("nonexistent_path/file.pdf")
        assert result.status == FileStatus.QUARANTINE

    # NEW: folder_path routing — downstream L1 Classifier contract
    def test_valid_pdf_has_original_extension(self, tmpdir):
        """
        ValidationResult.original_extension must be preserved.
        Import Worker stores it as the MinIO artifact extension.
        Structure: validated file → stored as .pdf in MinIO → read by Extractor.
        """
        path = write_file(tmpdir, "spa_main.pdf", b"%PDF-1.4 SPA doc")
        result = validate_file(path)
        assert result.original_extension == ".pdf"

    # NEW: downstream contract for folder_path routing
    def test_docx_needs_conversion_flag(self, tmpdir):
        """
        DOCX must be VALID (passes validation) but needs_conversion() == True.
        Import Worker quarantines it after upload.
        This distinction is important: we upload the file to MinIO for
        manual review / future conversion before quarantining.
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
        path = write_file(tmpdir, "contract.docx", buf.getvalue())
        result = validate_file(path)
        assert result.status == FileStatus.VALID
        assert result.filetype == "docx"
        assert needs_conversion("docx") is True


class TestFileTypeHelpers:
    def test_pdf_can_process_directly(self):
        assert can_process_directly("pdf") is True
        assert can_process_directly("docx") is False
        assert can_process_directly("image") is False

    def test_docx_needs_conversion(self):
        assert needs_conversion("docx") is True
        assert needs_conversion("doc") is True
        assert needs_conversion("pdf") is False

    def test_xlsx_is_spreadsheet(self):
        assert is_spreadsheet("xlsx") is True
        assert is_spreadsheet("xls") is True
        assert is_spreadsheet("pdf") is False

    def test_png_is_image(self):
        assert is_image("image") is True
        assert is_image("pdf") is False

    # NEW: routing matrix — full table of file types vs processing path
    def test_routing_matrix(self):
        """
        Complete routing matrix for Import Worker file type decisions.
        Each file type must map to exactly one processing path:
          pdf   → can_process_directly → Extractor (Stage 4)
          docx  → needs_conversion     → quarantine (future: LibreOffice)
          doc   → needs_conversion     → quarantine (future: LibreOffice)
          xlsx  → is_spreadsheet       → quarantine (future: tabular processing)
          image → is_image             → quarantine (future: OCR pipeline)
        """
        routing = {
            "pdf": ("direct", can_process_directly("pdf")),
            "docx": ("convert", needs_conversion("docx")),
            "doc": ("convert", needs_conversion("doc")),
            "xlsx": ("spreadsheet", is_spreadsheet("xlsx")),
            "image": ("ocr", is_image("image")),
        }
        for filetype, (path_name, flag) in routing.items():
            assert flag is True, f"{filetype} should route to {path_name}"
        # No type should match two routes simultaneously
        for ft in ("docx", "doc", "xlsx", "image"):
            assert not can_process_directly(ft), f"{ft} must not go to Extractor directly"
