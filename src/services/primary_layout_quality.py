"""
Quality gates для primary_layout.

Назначение:
- проверить что primary_layout является корректной lossless проекцией raw_layout;
- обнаружить текстовую мутацию (retained.text != raw.text);
- обнаружить структурные нарушения (element_id не существует в raw);
- вычислить analysis_eligibility для downstream pipeline.

Используется в canonical path (Фаза 3) после language filtering
перед сохранением layout_primary_ref в MinIO.

Не используется в legacy path (PDF extraction) — там проверки
выполняются через extraction_quality.py.
"""

from __future__ import annotations

from typing import Any


def validate_primary_layout(
    raw_layout: dict[str, Any],
    primary_layout: dict[str, Any],
    expected_target_ratio: float,
) -> dict[str, Any]:
    """
    Проверить качество primary_layout относительно raw_layout.

    Для непрофессионального программиста:
    - raw_layout = то что пришло из extract_pdf() — оригинальный текст
    - primary_layout = то что вышло из language filter — отфильтрованный текст
    - мы проверяем что фильтр НЕ изменил тексты retained элементов

    Возвращает dict с:
    - fidelity_status:        "passed" | "degraded" | "failed"
    - structural_fidelity:    "passed" | "failed"
    - text_fidelity:          "passed" | "failed"
    - language_fidelity:      "passed" | "degraded"
    - analysis_eligibility:   "eligible" | "eligible_with_warning" |
                              "manual_review_required" | "blocked"
    - requires_manual_review: bool
    - fidelity_failure_reasons: list[str]
    - и метрики: elements_total, elements_retained, elements_excluded,
                 elements_flagged, retention_ratio, ratio_deviation
    """
    failures: list[str] = []
    warnings: list[str] = []

    # Строим индекс raw элементов по element_id
    raw_elements: dict[str, dict[str, Any]] = {
        e["element_id"]: e
        for e in (raw_layout.get("elements") or [])
        if e.get("element_id")
    }

    primary_elements: list[dict[str, Any]] = primary_layout.get("elements") or []
    excluded_ids: set[str] = set(primary_layout.get("excluded_element_ids") or [])
    retained_ids: list[str] = [
        e.get("element_id", "") for e in primary_elements
    ]
    retained_ids_set: set[str] = set(retained_ids)

    # ── Structural gates ──────────────────────────────────────────────────────

    if not primary_elements:
        failures.append("no_retained_elements")

    # Дубли element_id в retained
    if len(retained_ids_set) != len(primary_elements):
        failures.append("duplicate_element_ids_in_retained")

    # Пересечение retained и excluded
    overlap = excluded_ids & retained_ids_set
    if overlap:
        sample = sorted(overlap)[:3]
        failures.append(f"element_both_retained_and_excluded:{sample}")

    # ── Per-element gates ─────────────────────────────────────────────────────

    for el in primary_elements:
        eid = el.get("element_id", "")
        raw_el = raw_elements.get(eid)

        if not raw_el:
            failures.append(f"element_id_not_in_raw:{eid}")
            continue

        # ГЛАВНЫЙ ИНВАРИАНТ: текст не должен мутировать
        if el.get("text") != raw_el.get("text"):
            failures.append(f"text_mutated:{eid}")

        # Страница
        if el.get("page") != raw_el.get("page"):
            failures.append(f"page_mismatch:{eid}")

        # Bbox (tolerance 1e-3)
        raw_bbox = raw_el.get("bbox") or []
        primary_bbox = el.get("bbox") or []
        if len(raw_bbox) == 4 and len(primary_bbox) == 4:
            if any(
                abs(float(r) - float(p)) > 1e-3
                for r, p in zip(raw_bbox, primary_bbox)
            ):
                failures.append(f"bbox_mismatch:{eid}")

        # Тип элемента
        if el.get("type") != raw_el.get("type"):
            failures.append(f"type_mismatch:{eid}")

        # Пустой retained элемент (если raw не пуст)
        if raw_el.get("text", "").strip() and not el.get("text", "").strip():
            warnings.append(f"empty_retained_element:{eid}")

        # Потеря reading_order
        if raw_el.get("reading_order") is not None and el.get("reading_order") is None:
            warnings.append(f"reading_order_lost:{eid}")

    # ── Language fidelity gates ───────────────────────────────────────────────

    raw_chars = sum(
        len(e.get("text") or "")
        for e in (raw_layout.get("elements") or [])
    )
    retained_chars = sum(
        len(e.get("text") or "")
        for e in primary_elements
    )
    actual_ratio = retained_chars / raw_chars if raw_chars else 0.0
    deviation = abs(actual_ratio - expected_target_ratio)

    if deviation > 0.20:
        warnings.append(f"retention_ratio_deviation:{deviation:.3f}")

    flagged_count = sum(
        1 for e in primary_elements
        if e.get("retention_status") == "flagged"
    )
    flagged_ratio = flagged_count / len(primary_elements) if primary_elements else 0.0
    if flagged_ratio > 0.30:
        warnings.append(f"high_flagged_ratio:{flagged_ratio:.3f}")

    # ── Aggregate result ──────────────────────────────────────────────────────

    has_text_failures = any("text_mutated" in f for f in failures)
    has_struct_failures = any(
        any(marker in f for marker in [
            "not_in_raw", "duplicate_element_ids", "both_retained_and_excluded"
        ])
        for f in failures
    )

    struct_fidelity = "failed" if has_struct_failures or failures else "passed"
    text_fidelity = "failed" if has_text_failures else "passed"
    lang_fidelity = (
        "degraded"
        if any("retention_ratio" in w or "high_flagged" in w for w in warnings)
        else "passed"
    )

    overall = "failed" if failures else "degraded" if warnings else "passed"

    # analysis_eligibility
    if failures:
        eligibility = "blocked"
    elif flagged_ratio > 0.30:
        eligibility = "manual_review_required"
    elif warnings:
        eligibility = "eligible_with_warning"
    else:
        eligibility = "eligible"

    return {
        "fidelity_status": overall,
        "structural_fidelity": struct_fidelity,
        "text_fidelity": text_fidelity,
        "language_fidelity": lang_fidelity,
        "fidelity_failure_reasons": failures + warnings,
        "analysis_eligibility": eligibility,
        "requires_manual_review": eligibility == "manual_review_required",
        "elements_total": len(raw_elements),
        "elements_retained": len(primary_elements),
        "elements_excluded": len(excluded_ids),
        "elements_flagged": flagged_count,
        "retention_ratio": round(actual_ratio, 4),
        "expected_target_ratio": round(expected_target_ratio, 4),
        "ratio_deviation": round(deviation, 4),
    }



    