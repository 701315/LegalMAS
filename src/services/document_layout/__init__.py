"""
Document Layout Extraction Pipeline v2.

Модуль заменяет legacy-пайплайн (pdfplumber → ReportLab → extract_pdf)
на единый цикл: Docling extraction + PyMuPDF enrichment + language classification
+ monolingual projection → flat elements[] JSON.

Архитектурная граница:
- UPSTREAM (этот модуль): PDF bytes → layout_primary.json
- DOWNSTREAM (не меняется): PII → structure → chunks → classification

Контракт output:
- JSON с root-ключом "elements" (list[dict])
- bbox в системе координат Fitz/PyMuPDF (origin top-left, y↓)
- поле "type" маппится из Docling label (section_header → "heading")
"""
