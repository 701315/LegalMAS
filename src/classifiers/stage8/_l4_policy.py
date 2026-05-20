# src/classifiers/stage8/_l4_policy.py
"""
L4 policy helpers для HybridClassifier.

Содержит только policy-логику:
  - как строить shortlist/allowed_types для L4;
  - как решать, нужно ли запускать L4;
  - dataclass результата gating-решения.

Намеренно НЕ содержит:
  - вызова LLM;
  - логирования;
  - метрик;
  - построения final result;
  - доступа к HybridClassifier через self.

Это делает модуль безопасным для unit-тестирования и повторного использования.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config import settings


@dataclass(slots=True)
class L4GateDecision:
    l4_enabled: bool
    llm_available: bool
    has_source_and_types: bool
    need_adjudication: bool
    skip_l4: bool
    strong_single_no_conflict: bool
    strong_final: bool
    contradiction_detected: bool
    input_quality: float


def build_llm_shortlist(candidates: list[dict], top_k: int = 5) -> list[str]:
    """
    Строит shortlist type_code для L4 по лучшей confidence каждого типа.

    Важно:
    - один type_code попадает в shortlist только один раз;
    - для каждого type_code берётся максимальная confidence среди кандидатов;
    - функция tolerant к плохим / неполным candidate dict.
    """
    ranked: dict[str, float] = {}

    for c in candidates or []:
        if not isinstance(c, dict):
            continue

        type_code = c.get("type_code")
        if not type_code:
            continue

        try:
            conf = float(c.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0

        ranked[str(type_code)] = max(ranked.get(str(type_code), 0.0), conf)

    if not ranked:
        return []

    return [
        type_code
        for type_code, _ in sorted(
            ranked.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]
    ]


def expand_llm_types_by_family(
    registry: Any,
    seed_types: list[str],
    limit: int,
) -> list[str]:
    """
    Мягко расширяет shortlist "родственными" типами через registry.

    Practical-эвристика family:
    - совпадающий category;
    - и, по возможности, совпадающий metadata.subcategory.
    """
    if limit <= 0 or not seed_types:
        return []

    try:
        all_types = list(registry.list_types() or [])
    except Exception:
        return []

    family_keys: set[tuple[str, str]] = set()

    for seed_type in seed_types:
        try:
            cfg = registry.get_config(seed_type)
        except Exception:
            cfg = None

        if cfg is None:
            continue

        raw = getattr(cfg, "raw", {}) or {}
        metadata = raw.get("metadata", {}) or {}
        category = str(getattr(cfg, "category", "") or "").strip()
        subcategory = str(metadata.get("subcategory", "") or "").strip()

        if category or subcategory:
            family_keys.add((category, subcategory))

    if not family_keys:
        return []

    result: list[str] = []
    seen = set(seed_types)

    for type_code in all_types:
        if type_code in seen:
            continue

        try:
            cfg = registry.get_config(type_code)
        except Exception:
            cfg = None

        if cfg is None:
            continue

        raw = getattr(cfg, "raw", {}) or {}
        metadata = raw.get("metadata", {}) or {}
        category = str(getattr(cfg, "category", "") or "").strip()
        subcategory = str(metadata.get("subcategory", "") or "").strip()

        if (category, subcategory) in family_keys:
            result.append(type_code)
            seen.add(type_code)

        if len(result) >= limit:
            break

    return result


def global_l4_fallback_types() -> list[str]:
    """
    Возвращает глобальный fallback-список типов для L4.

    Приоритет:
    1. settings.CLASSIFICATION_L4_GLOBAL_FALLBACK_TYPES
    2. безопасный встроенный список частых/универсальных типов
    """
    configured = getattr(settings, "CLASSIFICATION_L4_GLOBAL_FALLBACK_TYPES", None)

    if isinstance(configured, (list, tuple)):
        result = [str(x).strip() for x in configured if str(x).strip()]
        if result:
            return result

    return [
        "contract1.1salepurchase",
        "contract1.3goodssupply",
        "contract1.5services",
        "act1.1acceptance",
        "invoice1.1taxinvoice",
        "order1.1purchaseorder",
        "agreement1.1general",
        "specification1.1general",
    ]


def build_llm_allowed_types(
    registry: Any,
    candidates: list[dict],
    base_top_k: int = 5,
    max_total: int = 12,
) -> tuple[list[str], dict]:
    """
    Строит allowed_types для L4 с explainable expansion.

    Алгоритм:
    1. shortlist = top-K по candidate confidence;
    2. если места ещё есть — добавляем family-like related types из registry;
    3. если места ещё есть — добиваем глобальным fallback-списком;
    4. всегда ограничиваем итог max_total.
    """
    shortlist = build_llm_shortlist(candidates, top_k=base_top_k)

    result: list[str] = []
    seen: set[str] = set()

    for type_code in shortlist:
        if type_code not in seen:
            result.append(type_code)
            seen.add(type_code)
        if len(result) >= max_total:
            break

    family_selected: list[str] = []
    remaining = max(0, max_total - len(result))
    if remaining > 0 and shortlist:
        family_candidates = expand_llm_types_by_family(
            registry,
            shortlist,
            limit=remaining,
        )
        for type_code in family_candidates:
            if type_code not in seen:
                result.append(type_code)
                family_selected.append(type_code)
                seen.add(type_code)
            if len(result) >= max_total:
                break

    global_selected: list[str] = []
    remaining = max(0, max_total - len(result))
    if remaining > 0:
        for type_code in global_l4_fallback_types():
            if type_code not in seen:
                result.append(type_code)
                global_selected.append(type_code)
                seen.add(type_code)
            if len(result) >= max_total:
                break

    source_map = {
        "shortlist": result[: min(len(shortlist), len(result))] if shortlist else [],
        "family": family_selected,
        "global": global_selected,
    }

    return result[:max_total], source_map


def should_run_l4(
    *,
    l4_enabled: bool,
    llm_available: bool,
    hybrid_accept: float,
    is_segment: bool,
    llm_source_text: str,
    allowed_types: list[str],
    final_conf_after_voting: float,
    voted_margin: float,
    details: dict,
) -> L4GateDecision:
    """
    Централизованный gating для L4 (document + segment).

    Логика:
    - L4 вызывается только если:
      * включён флагом,
      * LLM-драйвер доступен,
      * есть текст,
      * есть allowed_types,
      * нужен adjudication,
      * и нет блокирующих strong_final / strong_single_no_conflict.
    """
    has_source_text = bool(llm_source_text and llm_source_text.strip())
    has_allowed_types = bool(allowed_types)

    contradiction = bool(details.get("contradiction_detected", False))
    input_quality = float(details.get("input_quality", 1.0))
    strong_final = final_conf_after_voting >= hybrid_accept

    strong_l2 = float(getattr(settings, "CLASSIFICATION_L2_STRONG", 0.85))
    strong_l3 = float(getattr(settings, "CLASSIFICATION_L3_STRONG", 0.85))
    margin_min = float(getattr(settings, "CLASSIFICATION_L4_MARGIN_MIN", 0.15))
    min_input_quality = float(
        getattr(settings, "CLASSIFICATION_L4_INPUT_QUALITY_MIN", 0.60)
    )

    top_l2 = details.get("L2_top")
    top_l3 = details.get("L3_top")

    if is_segment:
        strong_single_no_conflict = (
            top_l3 is not None
            and float(top_l3.get("confidence", 0.0)) >= strong_l3
            and not contradiction
        )
    else:
        strong_single_no_conflict = False

        if top_l2 is not None:
            strong_single_no_conflict = (
                float(top_l2.get("confidence", 0.0)) >= strong_l2
                and not contradiction
            )

        if not strong_single_no_conflict and top_l3 is not None:
            strong_single_no_conflict = (
                float(top_l3.get("confidence", 0.0)) >= strong_l3
                and not contradiction
            )

    need_adjudication = (
        final_conf_after_voting < hybrid_accept
        or voted_margin < margin_min
        or contradiction
        or input_quality < min_input_quality
    )

    skip_l4 = strong_final or strong_single_no_conflict

    return L4GateDecision(
        l4_enabled=l4_enabled,
        llm_available=llm_available,
        has_source_and_types=(has_source_text and has_allowed_types),
        need_adjudication=need_adjudication,
        skip_l4=skip_l4,
        strong_single_no_conflict=strong_single_no_conflict,
        strong_final=strong_final,
        contradiction_detected=contradiction,
        input_quality=input_quality,
    )


