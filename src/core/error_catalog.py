# src/core/error_catalog.py


"""
Каталог ошибок пайплайна анализа.

Задача модуля:
- Преобразовать технические stage/reason из processing_error_details и Run.error_details
  в короткие человекочитаемые сообщения для юриста.
- Сообщения пишутся простым языком и не раскрывают лишние технические детали.

Контракт:
- Основная функция render_error_message(details: dict | None) -> str | None.
- details ожидается в формате:
    {
        "stage": "import" | "extract" | "pii" | "structure" | "classify" | "checks" | "export" | "orchestrator" | "pipeline",
        "reason": "<machine_code>",
        "message": "<technical message>",  # опционально
        ...
    }
- Если stage/reason не известны, возвращаем None, а фронт может показать дефолтный текст.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Базовый словарь сообщений по (stage, reason).
# Ключи — коды, значения — короткие RU-тексты для юриста.
_ERROR_MESSAGES: dict[tuple[str, str], str] = {
    # import
    ("import", "unsupported_filetype"): "Тип файла не поддерживается для автоматического анализа.",
    ("import", "import_quarantine"): "Файл отправлен в карантин на стадии импорта.",
    # convert
    ("convert", "conversion_error"): "Не удалось конвертировать документ в PDF.",
    # extract
    ("extract", "extraction_failed"): "Не удалось извлечь текст из PDF.",
    ("extract", "no_text_extracted"): "В документе не удалось найти текст для анализа.",
    ("extract", "ocr_low_confidence"): "Качество OCR слишком низкое для надёжного анализа.",
    ("extract", "invalid_pdf"): "Файл повреждён или не является корректным PDF.",
    ("extract", "extraction_error"): "Ошибка при извлечении текста из документа.",
    # pii
    ("pii", "pii_encryption_error"): "Ошибка при защите персональных данных в документе.",
    ("pii", "pii_error"): "Ошибка при обработке персональных данных в документе.",
    # structure
    ("structure", "structure_error"): "Не удалось построить структуру документа.",
    # classify
    ("classify", "classification_error"): "Не удалось классифицировать документ.",
    # checks
    ("checks", "checks_error"): "Ошибка при выполнении проверок по документу.",
    # export
    ("export", "export_error"): "Не удалось сформировать экспортный отчёт по сделке.",
    ("export", "infrastructure_error"): (
        "Не удалось запустить экспорт из‑за внутренней технической ошибки. "
        "Попробуйте повторить позже или обратитесь к администратору."
    ),
    ("export", "queue_unavailable"): (
        "Не удалось запустить экспорт: очередь задач временно недоступна. "
        "Попробуйте ещё раз позже."
    ),
    # orchestrator / pipeline
    # общее сообщение про конфигурацию было слишком широким,
    # теперь делаем более точные коды
    ("orchestrator", "run_not_found"): (
        "Ошибка конфигурации запуска: указанный запуск анализа не найден. "
        "Возможно, он был удалён или указан некорректный идентификатор."
    ),
    ("orchestrator", "deal_not_bound"): (
        "Ошибка конфигурации запуска: запуск анализа не привязан к сделке. "
        "Обратитесь к администратору, чтобы правильно связать запуск с нужной сделкой."
    ),
    # при инфраструктурных проблемах оркестратора (брокер, Celery и т.п.)
    ("orchestrator", "infrastructure_error"): (
        "Не удалось запустить оркестрацию анализа из‑за внутренней технической ошибки. "
        "Попробуйте повторить запуск позже или обратитесь к администратору."
    ),
    ("orchestrator", "queue_unavailable"): (
        "Очередь задач временно недоступна. "
        "Повторите запуск анализа позже или обратитесь к администратору."
    ),
    # общее сообщение для инфраструктурных ошибок пайплайна
    ("pipeline", "infrastructure_error"): "Инфраструктурная ошибка при запуске анализа.",
}


def render_error_message(details: Mapping[str, Any] | None) -> str | None:
    """
    Преобразовать технические детали ошибки в человекочитаемое сообщение.

    Логика:
    - если нет details или нет stage/reason — возвращаем None;
    - если (stage, reason) есть в каталоге — возвращаем готовый текст;
    - иначе — возвращаем None (фронт может показать свой дефолтный текст).
    """
    if not details:
        return None

    stage = str(details.get("stage") or "").strip()
    reason = str(details.get("reason") or "").strip()

    if not stage or not reason:
        return None

    return _ERROR_MESSAGES.get((stage, reason))
