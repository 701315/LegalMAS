"""
Create test PDF fixtures for extraction tests.

Generates:
  - tests/fixtures/test_text_clean.pdf   — clean text PDF (pdfplumber only)
  - tests/fixtures/test_with_table.pdf   — PDF with a table
  - tests/fixtures/test_empty.pdf        — PDF with no content (quarantine case)
  - tests/fixtures/test_image_scan.pdf   — PDF with embedded image (simulated scan)
  - tests/fixtures/test_spa.pdf          — realistic SPA-like document
                                           (used by Structure Builder / Classifier tests)

Run:
    python -m scripts.create_extraction_fixtures
"""
import io
import os

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures",
)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def create_text_clean_pdf():
    """Clean text PDF with numbered sections."""
    if not HAS_REPORTLAB:
        print("Skipping test_text_clean.pdf — reportlab not installed")
        return
    path    = os.path.join(FIXTURES_DIR, "test_text_clean.pdf")
    doc     = SimpleDocTemplate(path, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    s_body  = ParagraphStyle("Normal",  fontSize=10, leading=14)
    s_head  = ParagraphStyle("Heading", fontSize=12, leading=16,
                             spaceBefore=12, spaceAfter=6)
    content = [
        Paragraph("1. INTRODUCTION", s_head),
        Paragraph(
            "This is a test document for PDF extraction testing. "
            "It contains multiple sections with numbered headings.", s_body,
        ),
        Spacer(1, 10),
        Paragraph("1.1. Purpose", s_head),
        Paragraph(
            "The purpose of this document is to verify that the extraction "
            "pipeline correctly handles text-based PDF files.", s_body,
        ),
        Spacer(1, 10),
        Paragraph("2. MAIN CONTENT", s_head),
        Paragraph(
            "This section contains the main body text. "
            "It should be extracted as regular text elements.", s_body,
        ),
        Paragraph("2.1. Subsection with details about the agreement terms and conditions "
                  "that apply to all parties.", s_head),
        Paragraph(
            "The total amount of the transaction is 500,000,000 rubles. "
            "Payment shall be made within 30 business days.", s_body,
        ),
        Spacer(1, 10),
        Paragraph("3. CONCLUSION", s_head),
        Paragraph(
            "This document serves as a test fixture for the MAS DD system.", s_body
        ),
    ]
    doc.build(content)
    print(f"Created {path}")


def create_spa_pdf():
    """
    Realistic SPA-like document.

    Used downstream by:
      - Structure Builder tests (Этап 6): detects clause boundaries
      - Classifier L1/L2 tests: filename + header matching
      - Runner integration tests (Этап 8): change-of-control check
    """
    if not HAS_REPORTLAB:
        print("Skipping test_spa.pdf — reportlab not installed")
        return
    path   = os.path.join(FIXTURES_DIR, "test_spa.pdf")
    doc    = SimpleDocTemplate(path, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    s_body = ParagraphStyle("Normal",  fontSize=10, leading=14)
    s_head = ParagraphStyle("Heading", fontSize=12, leading=16,
                            spaceBefore=12, spaceAfter=6)
    content = [
        Paragraph("ДОГОВОР КУПЛИ-ПРОДАЖИ АКЦИЙ (SPA)", s_head),
        Paragraph("г. Москва, 01 января 2025 г.", s_body),
        Spacer(1, 10),
        Paragraph("1. Предмет договора", s_head),
        Paragraph(
            "Продавец обязуется передать в собственность Покупателя акции ООО «Ромашка» "
            "в количестве 100 штук, составляющих 100% уставного капитала Общества.",
            s_body,
        ),
        Spacer(1, 6),
        Paragraph("1.1. Объект сделки", s_head),
        Paragraph("Акции в количестве 100 штук номинальной стоимостью 1 000 рублей каждая.", s_body),
        Spacer(1, 6),
        Paragraph("2. Цена и порядок расчётов", s_head),
        Paragraph(
            "Цена сделки составляет 500 000 000 (пятьсот миллионов) рублей. "
            "Расчёты производятся в порядке, предусмотренном п. 1.1 настоящего договора.",
            s_body,
        ),
        Spacer(1, 10),
        Paragraph("8. Смена контроля", s_head),
        Paragraph(
            "8.3. Настоящий договор содержит положения о смене контроля (change of control). "
            "В случае смены контроля над Покупателем Продавец вправе потребовать досрочного "
            "исполнения всех обязательств по настоящему договору.",
            s_body,
        ),
        Spacer(1, 10),
        Paragraph("12. Применимое право", s_head),
        Paragraph(
            "Настоящий договор регулируется российским правом. "
            "Все споры подлежат разрешению в Арбитражном суде г. Москвы.",
            s_body,
        ),
    ]
    doc.build(content)
    print(f"Created {path}")


def create_table_pdf():
    """PDF with a table — for table extraction tests."""
    if not HAS_REPORTLAB:
        print("Skipping test_with_table.pdf — reportlab not installed")
        return
    path  = os.path.join(FIXTURES_DIR, "test_with_table.pdf")
    doc   = SimpleDocTemplate(path, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    style = ParagraphStyle("Normal", fontSize=10, leading=14)
    table_data = [
        ["Документ", "Тип", "Страниц"],
        ["SPA_main.pdf", "SPA", "45"],
        ["NDA_final.pdf", "NDA", "12"],
    ]
    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    content = [
        Paragraph("Test document with a table", style),
        Spacer(1, 10),
        table,
    ]
    doc.build(content)
    print(f"Created {path}")


def create_empty_pdf():
    """Empty PDF — for quarantine tests."""
    if not HAS_REPORTLAB:
        print("Skipping test_empty.pdf — reportlab not installed")
        return
    path = os.path.join(FIXTURES_DIR, "test_empty.pdf")
    doc  = SimpleDocTemplate(path, pagesize=A4)
    doc.build([Spacer(1, 1)])
    print(f"Created {path}")


def create_image_scan_pdf():
    """PDF with embedded image — simulated scan for OCR tests."""
    if not HAS_PILLOW or not HAS_REPORTLAB:
        print("Skipping test_image_scan.pdf — Pillow or reportlab not installed")
        return
    path = os.path.join(FIXTURES_DIR, "test_image_scan.pdf")
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50),  "ДОГОВОР АРЕНДЫ",     fill=(0, 0, 0))
    draw.text((50, 100), "1. Предмет договора", fill=(0, 0, 0))
    draw.text((50, 150), "Арендодатель передаёт Арендатору помещение.", fill=(0, 0, 0))

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    c.drawImage(ImageReader(img_bytes), 0, 0, width=width, height=height)
    c.showPage()
    c.save()
    print(f"Created {path}")


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    create_text_clean_pdf()
    create_spa_pdf()          # ← добавлен vs исходный план
    create_table_pdf()
    create_empty_pdf()
    create_image_scan_pdf()
    print(f"\n5 extraction fixtures created in {FIXTURES_DIR}")
