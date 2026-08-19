"""
Валидатор качества экспортированного PDF.

Назначение:
- проверить что PDF export прошёл успешно и пригоден для использования;
- НЕ блокировать analysis pipeline при неудаче — export является derived artifact;
- дать чёткую диагностику если export деградирован.

Используется в Фазе 6 (Export lifecycle):
- вызывается ПОСЛЕ build_pdf_from_layout();
- результат определяет судьбу PDF: publish / diagnostic only;
- НЕ влияет на layout_primary_ref и analysis pipeline.

Контракт:
- validate_pdf_export() возвращает dict с export_fidelity_status;
- "passed"        → публикуем как primary_source_ref;
- "degraded"      → публикуем с предупреждением (UI может показать disclaimer);
- "failed"        → НЕ публикуем, сохраняем только как diagnostic artifact;
- "not_generated" → export вообще не запускался (exception в build_pdf_from_layout).
"""

from __future__ import annotations

from typing import Any


# Минимальный размер валидного PDF в байтах
# (меньше 700 байт — почти наверняка пустой или деградированный)
_MIN_PDF_SIZE_BYTES = 700

# Минимальный процент элементов от layout которые должны присутствовать в PDF
# (используется для будущей re-extraction validation)
_MIN_COVERAGE_RATIO = 0.50


def validate_pdf_export(
    primary_layout: dict[str, Any],
    pdf_bytes: bytes,
) -> dict[str, Any]:
    """
    Проверить качество экспортированного PDF.

    Для непрофессионального программиста:
    - primary_layout — JSON layout который мы пытались конвертировать в PDF;
    - pdf_bytes — байты PDF который получился;
    - мы проверяем что PDF не пустой и содержит ожидаемый контент.

    Возвращает dict:
    - export_fidelity_status: "passed" | "degraded" | "failed"
    - reason:                 описание проблемы (None если passed)
    - details:                дополнительная диагностика
    """
    # ── Базовые проверки ──────────────────────────────────────────────────────

    if not pdf_bytes:
        return {
            "export_fidelity_status": "failed",
            "reason": "empty_pdf_bytes",
            "details": {"pdf_size": 0},
        }

    if len(pdf_bytes) < _MIN_PDF_SIZE_BYTES:
        return {
            "export_fidelity_status": "failed",
            "reason": "pdf_too_small",
            "details": {
                "pdf_size": len(pdf_bytes),
                "min_expected": _MIN_PDF_SIZE_BYTES,
            },
        }

    # Проверяем PDF signature (все валидные PDF начинаются с %PDF-)
    if not pdf_bytes.startswith(b"%PDF-"):
        return {
            "export_fidelity_status": "failed",
            "reason": "invalid_pdf_signature",
            "details": {
                "pdf_size": len(pdf_bytes),
                "first_bytes": pdf_bytes[:8].hex(),
            },
        }

    # ── Проверка layout ───────────────────────────────────────────────────────

    elements = primary_layout.get("elements") or []
    if not elements:
        return {
            "export_fidelity_status": "failed",
            "reason": "empty_primary_layout",
            "details": {"element_count": 0},
        }

    # ── Базовые эвристики quality ─────────────────────────────────────────────
    #
    # Более глубокая валидация (re-extraction и сравнение текстов) требует
    # запуска extract_pdf() на результирующем PDF, что дорого и создаёт
    # circular dependency. В текущей версии используем size-based эвристики.
    #
    # В будущих версиях можно добавить:
    # - re-extraction + token coverage check
    # - сравнение количества страниц
    # - damaged token detection (например "составл(ядевте" вместо "12 536 000")

    # Примерный ожидаемый минимальный размер: ~50 байт на элемент
    expected_min_size = len(elements) * 50
    if len(pdf_bytes) < expected_min_size:
        return {
            "export_fidelity_status": "degraded",
            "reason": "pdf_smaller_than_expected",
            "details": {
                "pdf_size": len(pdf_bytes),
                "expected_min_size": expected_min_size,
                "element_count": len(elements),
            },
        }

    # ── Всё в порядке ─────────────────────────────────────────────────────────

    return {
        "export_fidelity_status": "passed",
        "reason": None,
        "details": {
            "pdf_size": len(pdf_bytes),
            "element_count": len(elements),
        },
    }



    