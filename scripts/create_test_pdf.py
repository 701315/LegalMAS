"""
Generate a test SPA (Share Purchase Agreement) PDF for pipeline testing.

The document contains:
  - Russian text with Cyrillic characters (falls back to Latin if no font)
  - Numbered clauses (1., 1.1., etc.) for Structure Builder
  - Change-of-control keywords for Runner (п. 7.2)
  - Party names, phones, emails for PII Sanitizer
  - SPA-specific keywords for Classifier L1

Run:
    python -m scripts.create_test_pdf
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

CYRILLIC_FONT = "Helvetica"

try:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("CyrillicFont", path))
            CYRILLIC_FONT = "CyrillicFont"
            break
except Exception:
    pass

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "fixtures", "test_spa.pdf",
)


def create_test_spa():
    """Create a test SPA PDF with Russian text and SPA-specific structure."""
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
    )
    styles = {
        "title":   ParagraphStyle("Title",   fontName=CYRILLIC_FONT, fontSize=14,
                                  alignment=1, spaceAfter=20, leading=18),
        "heading": ParagraphStyle("Heading", fontName=CYRILLIC_FONT, fontSize=12,
                                  spaceBefore=15, spaceAfter=8, leading=16, bold=True),
        "body":    ParagraphStyle("Body",    fontName=CYRILLIC_FONT, fontSize=10,
                                  spaceAfter=6, leading=14),
    }
    content = []
    if CYRILLIC_FONT == "CyrillicFont":
        _build_cyrillic_content(content, styles)
    else:
        _build_latin_content(content, styles)

    doc.build(content)
    print(f"Test PDF created: {OUTPUT_PATH}")
    print(f"Font used: {CYRILLIC_FONT}")


def _build_cyrillic_content(content, styles):
    """Build content with Cyrillic characters."""
    content += [
        Paragraph("ДОГОВОР КУПЛИ-ПРОДАЖИ АКЦИЙ", styles["title"]),
        Paragraph("Share Purchase Agreement", styles["title"]),
        Spacer(1, 20),
        Paragraph("г. Москва, 15 января 2024 г.", styles["body"]),
        Spacer(1, 10),
        Paragraph(
            "ООО «Альфа Холдинг», ИНН 7707083893, ОГРН 1027700132195, "
            "в лице генерального директора Иванова Ивана Ивановича, "
            "именуемое в дальнейшем «Продавец»,", styles["body"],
        ),
        Paragraph(
            "ООО «Бета Инвест», ИНН 7710140679, "
            "в лице директора Петровой Марии Сергеевны, "
            "именуемое в дальнейшем «Покупатель»,", styles["body"],
        ),
        Paragraph("заключили настоящий договор о нижеследующем:", styles["body"]),
        Spacer(1, 15),

        Paragraph("1. ПРЕДМЕТ ДОГОВОРА", styles["heading"]),
        Paragraph(
            "1.1. Продавец обязуется передать в собственность Покупателя 100 акций "
            "ЗАО «Целевая Компания», составляющих 100% уставного капитала.",
            styles["body"],
        ),
        Paragraph(
            "1.2. Стоимость акций составляет 500 000 000 (пятьсот миллионов) рублей.",
            styles["body"],
        ),

        Paragraph("2. ЦЕНА И ПОРЯДОК РАСЧЁТОВ", styles["heading"]),
        Paragraph("2.1. Общая цена сделки: 500 000 000 рублей.", styles["body"]),
        Paragraph(
            "2.2. Оплата производится в течение 30 рабочих дней с момента подписания.",
            styles["body"],
        ),

        Paragraph("3. ЗАВЕРЕНИЯ И ГАРАНТИИ", styles["heading"]),
        Paragraph(
            "3.1. Продавец заверяет и гарантирует следующее:", styles["body"],
        ),
        Paragraph("3.1.1. Акции свободны от обременений.", styles["body"]),
        Paragraph("3.1.2. Компания не находится в процессе ликвидации.", styles["body"]),
        Paragraph(
            "3.1.3. Финансовая отчётность достоверно отражает положение дел.",
            styles["body"],
        ),

        Paragraph("4. СРОК ДЕЙСТВИЯ ДОГОВОРА", styles["heading"]),
        Paragraph(
            "4.1. Договор вступает в силу с момента подписания и действует 3 года.",
            styles["body"],
        ),
        Paragraph("4.2. Срок закрытия сделки — не позднее 12 месяцев.", styles["body"]),

        Paragraph("5. КОНФИДЕНЦИАЛЬНОСТЬ", styles["heading"]),
        Paragraph(
            "5.1. Стороны обязуются соблюдать конфиденциальность условий сделки.",
            styles["body"],
        ),

        Paragraph("6. РАЗРЕШЕНИЕ СПОРОВ", styles["heading"]),
        Paragraph(
            "6.1. Все споры рассматриваются в Арбитражном суде г. Москвы.",
            styles["body"],
        ),
        Paragraph(
            "6.2. Применимое право — Российская Федерация, Гражданский кодекс РФ.",
            styles["body"],
        ),

        # п. 7 — ключевой для теста Runner: Change of Control
        Paragraph("7. ОСОБЫЕ УСЛОВИЯ", styles["heading"]),
        Paragraph(
            "7.1. В случае наступления обстоятельств непреодолимой силы "
            "стороны освобождаются от ответственности.", styles["body"],
        ),
        Paragraph(
            "7.2. В случае смены контроля над Покупателем прямо или косвенно "
            "Продавец вправе в одностороннем порядке отказаться от исполнения "
            "настоящего Договора. CHANGE OF CONTROL CLAUSE.", styles["body"],
        ),
        Paragraph(
            "7.3. Под сменой контроля понимается переход прав на 50% и более "
            "долей Покупателя. change of control definition.", styles["body"],
        ),

        Paragraph("8. РЕКВИЗИТЫ СТОРОН", styles["heading"]),
        Spacer(1, 15),
        Paragraph("Продавец:", styles["body"]),
        Paragraph("ООО «Альфа Холдинг»", styles["body"]),
        Paragraph("Тел. +7 495 123-45-67", styles["body"]),
        Paragraph("Email: ivanov@alpha-holding.ru", styles["body"]),
        Spacer(1, 10),
        Paragraph("Покупатель:", styles["body"]),
        Paragraph("ООО «Бета Инвест»", styles["body"]),
        Paragraph("Тел. +7 499 987-65-43", styles["body"]),
        Paragraph("Email: petrova@beta-invest.ru", styles["body"]),
    ]


def _build_latin_content(content, styles):
    """Fallback: Latin characters if no Cyrillic font available."""
    content += [
        Paragraph("DOGOVOR KUPLI-PRODAZHI AKTSIY (SPA)", styles["title"]),
        Spacer(1, 20),
        Paragraph("g. Moskva, 15 yanvarya 2024 g.", styles["body"]),
        Spacer(1, 10),
        Paragraph(
            "OOO 'Alfa Holding' INN 7707083893, OGRN 1027700132195, "
            "Ivanov Ivan Ivanovich (Prodavets),", styles["body"],
        ),
        Paragraph(
            "OOO 'Beta Invest' INN 7710140679, "
            "Petrova Maria Sergeevna (Pokupatel).", styles["body"],
        ),
        Spacer(1, 15),
        Paragraph("1. PREDMET DOGOVORA", styles["heading"]),
        Paragraph(
            "1.1. Prodavets peredaet Pokupatelyu 100 aktsiy ZAO 'Tselevaya Kompaniya'.",
            styles["body"],
        ),
        Paragraph("1.2. Stoimost aktsiy sostavlyaet 500 000 000 rubley.", styles["body"]),
        Paragraph("7. OSOBYE USLOVIYA", styles["heading"]),
        Paragraph(
            "7.2. V sluchae smeny kontrolya nad Pokupatelem pryamo ili kosvenno "
            "Prodavets vprave otkazatsya ot ispolneniya Dogovora. CHANGE OF CONTROL CLAUSE.",
            styles["body"],
        ),
        Paragraph(
            "7.3. Pod smenoy kontrolya ponimayetsya perekhod prav na 50% i bolee. "
            "change of control definition.", styles["body"],
        ),
        Paragraph("8. REKVIZITY", styles["heading"]),
        Paragraph("Tel. +7 495 123-45-67, Email: ivanov@alpha-holding.ru", styles["body"]),
    ]


if __name__ == "__main__":
    create_test_spa()
