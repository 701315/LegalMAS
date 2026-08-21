"""
Quality gates для primary_layout (V2).

Проверяет что primary_layout является корректной проекцией raw_layout:
- структурная целостность (source_element_id существует в raw)
- lossless invariant (текст не мутировал, для split — подстрока)
- language fidelity (ratio retention в разумных пределах)

Адаптирован под V2 формат элементов:
- language, visibility и прочие multilingual поля лежат в element["metadata"]
- excluded_element_ids на верхнем уровне отсутствует (V2 не удаляет, а скрывает)
- retention_status отсутствует (V2 использует visibility_in_target_language)

Используется в canonical path build_primary_language_source.py
после вызова run_multilingual_pipeline() перед сохранением в MinIO.
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

    Аргументы:
        raw_layout:             оригинальный layout от extract_pdf()
        primary_layout:         монолингвальный layout от to_monolingual_layout()
        expected_target_ratio:  ожидаемая доля символов целевого языка (0.0-1.0)

    Возвращает dict:
        fidelity_status:          "passed" | "degraded" | "failed"
        structural_fidelity:      "passed" | "failed"
        text_fidelity:            "passed" | "failed"
        language_fidelity:        "passed" | "degraded"
        analysis_eligibility:     "eligible" | "eligible_with_warning" |
                                  "manual_review_required" | "blocked"
        requires_manual_review:   bool
        fidelity_failure_reasons: list[str]
        elements_total:           int  (в raw)
        elements_retained:        int  (visible в primary)
        elements_excluded:        int  (скрыты в V2 pipeline)
        elements_flagged:         int  (orphan или ambiguous)
        retention_ratio:          float
        expected_target_ratio:    float
        ratio_deviation:          float
    """
    failures: list[str] = []
    warnings_list: list[str] = []

    # Индекс raw элементов по element_id
    raw_elements: dict[str, dict[str, Any]] = {
        e["element_id"]: e
        for e in (raw_layout.get("elements") or [])
        if e.get("element_id")
    }

    primary_elements: list[dict[str, Any]] = primary_layout.get("elements") or []
    retained_ids: list[str] = [e.get("element_id", "") for e in primary_elements]
    retained_ids_set: set[str] = set(retained_ids)

    # ── Structural gates ──────────────────────────────────────────────────

    if not primary_elements:
        failures.append("no_retained_elements")

    # Дубли element_id в retained
    if len(retained_ids_set) != len(primary_elements):
        failures.append("duplicate_element_ids_in_retained")

    # ─ Per-element gates ─────────────────────────────────────────────────

    for el in primary_elements:
        eid = el.get("element_id", "")
        el_meta = el.get("metadata") or {}
        
        # V2: Извлекаем source_element_id для split-сегментов
        source_eid = el_meta.get("source_element_id")
        sub_index = el_meta.get("sub_index", 0)
        split_reason = el_meta.get("split_reason", "none")
        
        # Если source_element_id не указан в metadata, используем element_id
        if not source_eid:
            source_eid = eid
        
        raw_el = raw_elements.get(source_eid)

        # ── Проверка 1: source_element_id должен существовать в raw ───────
        if raw_el is None:
            # Для split-сегментов (sub_index > 0) это нормально — 
            # их element_id новый, но source_element_id должен быть в raw
            if sub_index > 0:
                # Проверяем что хотя бы source_element_id существует
                if source_eid != eid and source_eid in raw_elements:
                    continue  # OK для split
                # Если source_eid тоже не найден — ошибка
                failures.append(f"source_element_id_not_in_raw:{source_eid}")
                continue
            else:
                # Для не-split сегментов отсутствие в raw — это ошибка
                failures.append(f"element_id_not_in_raw:{eid}")
                continue

        # ── Проверка 2: текст не должен мутировать ────────────────────────
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Проверяем split_reason, а не sub_index!
        # Если элемент был разрезан (split_reason != "none"), ЛЮБОЙ сегмент
        # (включая sub_index=0) будет содержать только часть оригинала.
        primary_text = el.get("text") or ""
        raw_text = raw_el.get("text") or ""
        
        if split_reason != "none":
            # Split-сегмент (любой sub_index): текст должен быть частью оригинала
            if primary_text and primary_text not in raw_text:
                failures.append(f"text_not_in_source:{source_eid}_sub{sub_index}")
        else:
            # Не-split: полное совпадение
            if primary_text != raw_text:
                failures.append(f"text_mutated:{source_eid}")

        # ── Проверка 3: страница должна совпадать ─────────────────────────
        if el.get("page") != raw_el.get("page"):
            # Для split-сегментов допускаем расхождение
            if split_reason == "none":
                warnings_list.append(f"page_mismatch:{source_eid}")

    # ── V2-специфичные счётчики ───────────────────────────────────────────

    quality_metrics = (
        (primary_layout.get("metadata") or {})
        .get("quality_metrics") or {}
    )

    elements_hidden   = quality_metrics.get("segments_hidden", 0)
    elements_total_v2 = quality_metrics.get("segments_total", len(raw_elements))
    parallel_groups   = quality_metrics.get("parallel_groups_count", 0)
    orphan_groups     = quality_metrics.get("orphan_groups_count", 0)
    orphan_ratio      = quality_metrics.get("orphan_ratio", 0.0)

    if orphan_ratio > 0.40:
        warnings_list.append(f"high_orphan_ratio:{orphan_ratio:.3f}")

    # ── Language fidelity gates ───────────────────────────────────────────

    raw_chars = sum(
        len(e.get("text") or "")
        for e in (raw_layout.get("elements") or [])
    )
    retained_chars = sum(
        len(e.get("text") or "")
        for e in primary_elements
    )
    actual_ratio   = retained_chars / raw_chars if raw_chars else 0.0
    deviation      = abs(actual_ratio - expected_target_ratio)

    if deviation > 0.25:
        warnings_list.append(f"retention_ratio_deviation:{deviation:.3f}")

    flagged_count = sum(
        1 for e in primary_elements
        if (e.get("metadata") or {}).get("is_orphan_foreign", False)
    )
    flagged_ratio = flagged_count / len(primary_elements) if primary_elements else 0.0
    if flagged_ratio > 0.30:
        warnings_list.append(f"high_orphan_foreign_ratio:{flagged_ratio:.3f}")

    # ── Aggregate ─────────────────────────────────────────────────────────

    has_text_failures = any("text_mutated" in f or "text_not_in_source" in f for f in failures)
    has_struct_failures = any(
        any(m in f for m in ["not_in_raw", "duplicate_element_ids"])
        for f in failures
    )

    struct_fidelity = "failed" if has_struct_failures or failures else "passed"
    text_fidelity   = "failed" if has_text_failures else "passed"
    lang_fidelity   = (
        "degraded"
        if any("retention_ratio" in w or "orphan_ratio" in w for w in warnings_list)
        else "passed"
    )

    overall = "failed" if failures else "degraded" if warnings_list else "passed"

    if failures:
        eligibility = "blocked"
    elif flagged_ratio > 0.30:
        eligibility = "manual_review_required"
    elif warnings_list:
        eligibility = "eligible_with_warning"
    else:
        eligibility = "eligible"

    return {
        "fidelity_status":          overall,
        "structural_fidelity":      struct_fidelity,
        "text_fidelity":            text_fidelity,
        "language_fidelity":        lang_fidelity,
        "fidelity_failure_reasons": failures + warnings_list,
        "analysis_eligibility":     eligibility,
        "requires_manual_review":   eligibility == "manual_review_required",
        "elements_total":           len(raw_elements),
        "elements_retained":        len(primary_elements),
        "elements_excluded":        elements_hidden,
        "elements_flagged":         flagged_count,
        "retention_ratio":          round(actual_ratio, 4),
        "expected_target_ratio":    round(expected_target_ratio, 4),
        "ratio_deviation":          round(deviation, 4),
        # V2-specific диагностика
        "parallel_groups":          parallel_groups,
        "orphan_groups":            orphan_groups,
        "orphan_ratio":             round(orphan_ratio, 4),
    }


    