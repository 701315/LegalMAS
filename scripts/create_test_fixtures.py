"""
Create test fixtures for Import Worker tests.

Generates:
  - tests/fixtures/test_bundle.zip    — mixed valid/invalid files
  - tests/fixtures/test_nested.zip    — realistic Data Room folder structure
  - tests/fixtures/test_duplicates.zip — files with exact SHA-256 match

Run:
    python -m scripts.create_test_fixtures

Folder structure in test_nested.zip mirrors a real Data Room layout.
folder_path values are used downstream by the L1 Classifier (Stage 6)
folder_patterns matching in playbooks/document_types/registry.yaml:

  "02. Contracts/SPA"        → folder_patterns: r'(?i)SPA'       → boost contract1.1spa
  "02. Contracts/NDA"        → folder_patterns: r'(?i)NDA'       → boost contract2.1nda
  "03. Employment"           → folder_patterns: r'(?i)employment' → boost contract3.1employment
  "01. CorporateCharter"     → no match                          → no boost
  "01. CorporateBoard"       → no match                          → no boost
"""
import io
import os
import zipfile

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures",
)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def make_simple_pdf(text: str = "Test document") -> bytes:
    """Create a minimal valid PDF as bytes."""
    if HAS_REPORTLAB:
        buf    = io.BytesIO()
        doc    = SimpleDocTemplate(buf, pagesize=A4)
        styles = getSampleStyleSheet()
        doc.build([Paragraph(text, styles["Normal"])])
        return buf.getvalue()
    else:
        # Minimal hand-crafted PDF — valid magic bytes, passes validation
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n%%EOF"


def make_valid_docx() -> bytes:
    """Create a minimal valid DOCX (ZIP with ContentTypes.xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types"></Types>',
        )
    return buf.getvalue()


def create_test_bundle_zip():
    """
    Create test_bundle.zip with mixed valid/invalid files.

    Contents:
      - spa_main.pdf         → valid PDF (5 items)
      - nda_final.pdf        → valid PDF
      - charter.pdf          → valid PDF
      - employment.pdf       → valid PDF
      - license.pdf          → valid PDF
      - corrupted.pdf        → .pdf extension, wrong magic bytes → QUARANTINE
      - empty.pdf            → 0 bytes → QUARANTINE
      - contract.docx        → valid DOCX → QUARANTINE (needs_conversion)
      - .hidden              → hidden file → SKIP
      - notes.txt            → unsupported extension → QUARANTINE

    Expected: imported_count=5, quarantine_count=3, skipped_count=1
    (notes.txt → quarantine, .hidden → skip, corrupted + empty → quarantine)
    """
    zip_path = os.path.join(FIXTURES_DIR, "test_bundle.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        # 5 valid PDFs
        for name in ["spa_main.pdf", "nda_final.pdf", "charter.pdf",
                     "employment.pdf", "license.pdf"]:
            zf.writestr(name, make_simple_pdf(f"Document: {name}"))
        # Corrupted PDF (wrong magic bytes)
        zf.writestr("corrupted.pdf",    b"This is not a PDF")
        # Empty file
        zf.writestr("empty.pdf",        b"")
        # Valid DOCX → quarantine (needs_conversion)
        zf.writestr("contract.docx",    make_valid_docx())
        # Hidden file → SKIP
        zf.writestr(".hidden",          b"secret")
        # Unsupported extension → QUARANTINE
        zf.writestr("notes.txt",        b"Some notes about the deal")
    print(f"Created {zip_path}")


def create_test_nested_zip():
    """
    Create test_nested.zip with realistic Data Room folder structure.

    Folder layout (mirrors real VDR structure):
      01. CorporateCharter/charter.pdf
      01. CorporateBoard/board_decision.pdf
      02. Contracts/SPA/spa_v1.pdf        ← folder_path used by L1 Classifier
      02. Contracts/NDA/nda.pdf           ← folder_path used by L1 Classifier
      03. Employment/ceo_contract.pdf     ← folder_path used by L1 Classifier

    These folder_path values map to folder_patterns in registry.yaml:
      "02. Contracts/SPA"  → r'(?i)SPA'        → boosts contract1.1spa score
      "02. Contracts/NDA"  → r'(?i)NDA'        → boosts contract2.1nda score
      "03. Employment"     → r'(?i)employment'  → boosts contract3.1employment score

    Expected: imported_count=5
    """
    zip_path = os.path.join(FIXTURES_DIR, "test_nested.zip")
    folders_and_files = [
        ("01. CorporateCharter", "charter.pdf"),
        ("01. CorporateBoard",   "board_decision.pdf"),
        ("02. Contracts/SPA",    "spa_v1.pdf"),
        ("02. Contracts/NDA",    "nda.pdf"),
        ("03. Employment",       "ceo_contract.pdf"),
    ]
    with zipfile.ZipFile(zip_path, "w") as zf:
        for folder, filename in folders_and_files:
            pdf_bytes = make_simple_pdf(f"Document: {folder}/{filename}")
            zf.writestr(f"{folder}/{filename}", pdf_bytes)
    print(f"Created {zip_path}")


def create_test_duplicates_zip():
    """
    Create test_duplicates.zip to test SHA-256 deduplication.

    Contents:
      - original.pdf         → unique content → imported
      - copy_of_original.pdf → exact same bytes as original.pdf → DUPLICATE
      - different.pdf        → different content → imported

    Expected: imported_count=2, duplicate_count=1
    """
    zip_path     = os.path.join(FIXTURES_DIR, "test_duplicates.zip")
    original_pdf = make_simple_pdf("This is the original document")
    different_pdf = make_simple_pdf("This is a completely different document")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("original.pdf",        original_pdf)
        zf.writestr("copy_of_original.pdf", original_pdf)   # exact same bytes
        zf.writestr("different.pdf",        different_pdf)
    print(f"Created {zip_path}")


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    create_test_bundle_zip()
    create_test_nested_zip()
    create_test_duplicates_zip()
    print(f"\nAll 3 fixtures created in {FIXTURES_DIR}")
