# src/services/extract_router.py

"""
Extract Router.

Отвечает за принятие решения, что делать с файлом после импорта
в зависимости от его внутреннего типа (filetype из services.file_validator).

Задачи:
  - по внутреннему filetype (pdf, docx, xlsx, image, ...) определить:
      * нужно ли сразу запускать extractor;
      * требуется ли конвертация (например, DOCX → PDF);
      * является ли тип пока неподдерживаемым;
  - вернуть понятную структуру решения, которую использует Import Worker.

На данном этапе:
  - 'pdf'        → сразу отправляем в существующий PDF-extractor
                   (Celery-задача workers.extract_document).
  - 'docx'/'doc' → считаем, что нужна конвертация в PDF перед анализом,
                   ставим задачу workers.convert_to_pdf (сама конвертация
                   пока реализована как заглушка).
  - 'xlsx'/'xls' → таблицы пока не поддерживаются пайплайном анализа → unsupported.
  - 'image'      → изображения требуют OCR (не реализовано) → unsupported.
  - остальные    → явно неподдерживаемые типы → unsupported.

Как добавить новый extractor:
  1. Реализовать Celery-задачу (например, workers.extract_document_docx).
  2. Добавить правило в decide_extraction_strategy для соответствующего filetype:
       - вернуть action='extract' и extractor_task='workers.extract_document_docx';
  3. Import Worker начнёт ставить эту задачу автоматически, без изменения своего кода.

Как включить конвертацию для нового типа (пример DOCX/DOC):
  1. Реализовать конвертацию в workers.convert_to_pdf (convert_worker.py).
  2. В decide_extraction_strategy вернуть action='convert_then_extract'
     и extractor_task='workers.convert_to_pdf' для нужного filetype.
  3. Import Worker уже умеет ставить такие задачи и не требует доп. правок.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractRoutingDecision:
    """
    Решение роутера по типу файла.

    action:
      - 'extract'              — сразу отправляем в extractor
      - 'convert_then_extract' — сначала конвертация (docx → pdf), потом extractor
      - 'unsupported'          — пока не поддерживается, файл останется без пайплайна,
                                 обычно в статусе QUARANTINE

    extractor_task:
      - имя Celery-задачи для extract'а (если action == 'extract')
      - имя Celery-задачи для конвертации (если action == 'convert_then_extract')
      - None, если unsupported

    reason:
      - текст для логов / возможных processing_error_details
    """

    action: str
    extractor_task: str | None = None
    reason: str | None = None


def decide_extraction_strategy(filetype: str | None) -> ExtractRoutingDecision:
    """
    Централизованный роутер по внутреннему filetype (из services.file_validator).

    Примеры filetype:
      - 'pdf'
      - 'docx', 'doc'
      - 'xlsx', 'xls'
      - 'image'
      - 'unknown' и т.п.
    """
    ft = filetype or "unknown"

    # PDF уже поддерживается текущим пайплайном
    if ft == "pdf":
        return ExtractRoutingDecision(
            action="extract",
            extractor_task="workers.extract_document",  # текущий PDF-extractor
            reason=None,
        )

    # Форматы, требующие конвертации в PDF перед анализом (Office, RTF, OpenDocument, Text, Web)
    # Import Worker при action='convert_then_extract' поставит задачу workers.convert_to_pdf
    if ft in ("docx", "doc", "rtf", "odt", "txt", "pptx", "ppt", "odp", "html", "htm"):
        return ExtractRoutingDecision(
            action="convert_then_extract",
            extractor_task="workers.convert_to_pdf",
            reason="Document will be converted to PDF before analysis",
        )

    # Таблицы — пока не поддерживаются текстовым пайплайном
    if ft in ("xlsx", "xls"):
        return ExtractRoutingDecision(
            action="unsupported",
            extractor_task=None,
            reason="Spreadsheet files are not yet supported by the analysis pipeline",
        )

    # Изображения — нужен OCR, которого пока нет
    if ft == "image":
        return ExtractRoutingDecision(
            action="unsupported",
            extractor_task=None,
            reason="Image files require OCR pipeline (not implemented yet)",
        )

    # Все остальные типы — явно неподдерживаемые
    return ExtractRoutingDecision(
        action="unsupported",
        extractor_task=None,
        reason=f"Unsupported file type for analysis: {ft}",
    )
