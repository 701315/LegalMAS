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

# ══════════════════════════════════════════════════════════════════════
# L4GateDecision — результат gating-решения
# ══════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class L4GateDecision:
    l4_enabled: bool
    llm_available: bool
    has_source_and_types: bool
    has_source_text: bool
    has_allowed_types: bool
    need_adjudication: bool
    # ↑ need_adjudication — подавленное значение:
    #   False если strong_final или strong_single_no_conflict,
    #   даже если raw_need_adjudication=True.
    raw_need_adjudication: bool
    # ↑ raw_need_adjudication — сырая потребность в adjudication
    #   до подавления strong-флагами. Используется для диагностики
    #   и для вычисления review_preferred.
    skip_l4: bool
    strong_single_no_conflict: bool
    strong_final: bool
    contradiction_detected: bool
    input_quality: float
    domain_conflict: bool
    final_conf_after_voting: float
    voted_margin: float
    weak_input_for_l4: bool
    l4_useful: bool
    review_preferred: bool
    skip_reason: str | None
    adjudication_reason: str | None


# ══════════════════════════════════════════════════════════════════════
# Вспомогательные функции — типобезопасность
# ══════════════════════════════════════════════════════════════════════


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_type_code(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _is_valid_type_code(value: Any) -> bool:
    type_code = _normalize_type_code(value)
    return bool(type_code and type_code.upper() != "UNKNOWN")


# ══════════════════════════════════════════════════════════════════════
# is_hybrid_confident — общее условие для HYBRID-решения
# ══════════════════════════════════════════════════════════════════════


def is_hybrid_confident(
    *,
    final_conf: float,
    voted_margin: float,
    support_count: int,
    contradiction: bool,
    domain_conflict: bool,
    hybrid_accept: float,
    margin_min: float,
) -> bool:
    """
    Единое условие для «достаточно уверенного» HYBRID-решения.

    Используется в двух местах пайплайна:
      1. hybrid_classifier._resolve_after_priority() — ранний HYBRID выход
         (если True → возвращаем результат без L4).
      2. should_run_l4() — вычисление strong_final
         (если True → L4 пропускается как ненужный).

    Синхронизация этих двух мест критична: изменение порогов здесь
    автоматически применяется к обоим.

    Условия (все должны быть выполнены):
      - decision confidence голосования >= порог принятия;
      - margin между первым и вторым кандидатом >= минимальный;
      - поддержка от как минимум двух уровней (L1+L2, L2+L3, L1+L3);
      - нет contradiction между уровнями;
      - нет domain_conflict (конфликт parent/group доменов).
    """
    return (
        final_conf >= hybrid_accept
        and voted_margin >= margin_min
        and support_count >= 2
        and not contradiction
        and not domain_conflict
    )


# ══════════════════════════════════════════════════════════════════════
# Shortlist и allowed_types для L4
# ══════════════════════════════════════════════════════════════════════


def _extract_shortlist_from_voting(details: dict | None, top_k: int) -> list[str]:
    if not isinstance(details, dict):
        return []

    voting = details.get("voting")
    if not isinstance(voting, dict):
        return []

    ranking = voting.get("ranking")
    if not isinstance(ranking, list):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for item in ranking:
        if not isinstance(item, dict):
            continue

        type_code = _normalize_type_code(item.get("type") or item.get("type_code"))
        if not _is_valid_type_code(type_code) or type_code in seen:
            continue

        result.append(type_code)
        seen.add(type_code)
        if len(result) >= top_k:
            break

    return result


def build_llm_shortlist(
    candidates: list[dict],
    top_k: int = 5,
    details: dict | None = None,
) -> list[str]:
    """
    Строит shortlist type_code для L4.

    Приоритет источников:
    1. voting ranking (если уже есть post-voting ranking);
    2. лучшая raw confidence каждого типа из candidates.

    Важно:
    - один type_code попадает в shortlist только один раз;
    - функция tolerant к плохим / неполным candidate dict;
    - UNKNOWN/пустые type_code игнорируются.
    """
    shortlist_from_voting = _extract_shortlist_from_voting(details, top_k=top_k)
    if shortlist_from_voting:
        return shortlist_from_voting

    ranked: dict[str, float] = {}

    for c in candidates or []:
        if not isinstance(c, dict):
            continue

        type_code = _normalize_type_code(c.get("type_code"))
        if not _is_valid_type_code(type_code):
            continue

        conf = _safe_float(c.get("confidence", 0.0), 0.0)
        ranked[type_code] = max(ranked.get(type_code, 0.0), conf)

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


def _family_keys_for_type(registry: Any, type_code: str) -> set[tuple[str, str]]:
    """
    Возвращает family keys для типа.

    Приоритет family:
    1. parent + group
    2. parent + ""
    3. category + subcategory
    4. category + ""
    """
    if not _is_valid_type_code(type_code):
        return set()

    try:
        cfg = registry.get_config(type_code)
    except Exception:
        cfg = None

    if cfg is None:
        return set()

    raw = getattr(cfg, "raw", {}) or {}
    metadata = raw.get("metadata", {}) or {}

    parent = str(getattr(cfg, "parent", "") or "").strip()
    group = str(getattr(cfg, "group", "") or "").strip()
    category = str(getattr(cfg, "category", "") or "").strip()
    subcategory = str(
        getattr(cfg, "subcategory", "") or metadata.get("subcategory", "") or ""
    ).strip()

    result: set[tuple[str, str]] = set()

    if parent and group:
        result.add((f"parent:{parent}", f"group:{group}"))
    if parent:
        result.add((f"parent:{parent}", ""))
    if category and subcategory:
        result.add((f"category:{category}", f"subcategory:{subcategory}"))
    if category:
        result.add((f"category:{category}", ""))

    return result


def _family_keys_match(
    registry: Any,
    type_code: str,
    family_keys: set[tuple[str, str]],
) -> bool:
    if not family_keys or not _is_valid_type_code(type_code):
        return False

    try:
        cfg = registry.get_config(type_code)
    except Exception:
        cfg = None

    if cfg is None:
        return False

    raw = getattr(cfg, "raw", {}) or {}
    metadata = raw.get("metadata", {}) or {}

    parent = str(getattr(cfg, "parent", "") or "").strip()
    group = str(getattr(cfg, "group", "") or "").strip()
    category = str(getattr(cfg, "category", "") or "").strip()
    subcategory = str(
        getattr(cfg, "subcategory", "") or metadata.get("subcategory", "") or ""
    ).strip()

    candidate_keys: set[tuple[str, str]] = set()
    if parent and group:
        candidate_keys.add((f"parent:{parent}", f"group:{group}"))
    if parent:
        candidate_keys.add((f"parent:{parent}", ""))
    if category and subcategory:
        candidate_keys.add((f"category:{category}", f"subcategory:{subcategory}"))
    if category:
        candidate_keys.add((f"category:{category}", ""))

    return bool(candidate_keys.intersection(family_keys))


def expand_llm_types_by_family(
    registry: Any,
    seed_types: list[str],
    limit: int,
) -> list[str]:
    """
    Мягко расширяет shortlist "родственными" типами через registry.

    Практическая эвристика family (в порядке приоритета):
    - parent + group (самое специфичное);
    - parent;
    - category + subcategory;
    - только category (самое широкое).

    Важно:
    - расширение возможно только от уже существующих seed_types;
    - если shortlist отсутствует или для него не найдено family keys,
      expansion не происходит.
    """
    if limit <= 0 or not seed_types:
        return []

    try:
        all_types = list(registry.list_types() or [])
    except Exception:
        return []

    family_keys: set[tuple[str, str]] = set()

    for seed_type in seed_types:
        normalized = _normalize_type_code(seed_type)
        if not _is_valid_type_code(normalized):
            continue
        family_keys.update(_family_keys_for_type(registry, normalized))

    if not family_keys:
        return []

    result: list[str] = []
    seen = {
        _normalize_type_code(t) for t in seed_types if _is_valid_type_code(_normalize_type_code(t))
    }

    for type_code in all_types:
        type_code = _normalize_type_code(type_code)
        if not _is_valid_type_code(type_code) or type_code in seen:
            continue

        if _family_keys_match(registry, type_code, family_keys):
            result.append(type_code)
            seen.add(type_code)

        if len(result) >= limit:
            break

    return result


def _top2_seed_types(details: dict | None) -> list[str]:
    if not isinstance(details, dict):
        return []

    direct_top2 = _safe_list(details.get("top2_types"))
    result = [_normalize_type_code(x) for x in direct_top2 if _is_valid_type_code(x)]
    if result:
        return result[:2]

    voting = details.get("voting")
    if isinstance(voting, dict):
        voting_top2 = _safe_list(voting.get("top2_types"))
        result = [_normalize_type_code(x) for x in voting_top2 if _is_valid_type_code(x)]
        if result:
            return result[:2]

    return []


def build_llm_allowed_types(
    registry: Any,
    candidates: list[dict],
    base_top_k: int = 5,
    max_total: int = 12,
    details: dict | None = None,
) -> tuple[list[str], dict]:
    """
    Строит allowed_types для L4 с explainable expansion.

    Алгоритм:
    1. shortlist = post-voting ranking, если он есть;
       иначе top-K по candidate confidence;
    2. если есть domain_conflict / contradiction — family expansion делаем
       от top-2 competing types, чтобы не потерять второй domain;
    3. если места ещё есть — добавляем family-related types из registry;
    4. если нет shortlist и нет family expansion — L4 остаётся без allowed_types
       (has_allowed_types=False → skip_reason="missing_allowed_types");
    5. всегда ограничиваем итог max_total.

    Поля source_map для диагностики:
      shortlist             — типы из voting ranking / candidates, вошедшие в result;
      family_seed_types     — типы, от которых делалось family expansion;
      family                — типы, добавленные через family expansion;
      contradiction_detected / domain_conflict — флаги из details;
      used_voting_ranking   — True если shortlist взят из voting ranking;
      empty_candidate_space — True если result пустой;
      empty_reason          — "no_shortlist_and_no_candidates" если result пустой,
                              None если result непустой.
                              Единственная реальная причина пустого result —
                              отсутствие voting ranking и пустые candidates.
                              (если shortlist непустой, его элементы гарантированно
                              попадают в result на первом цикле копирования.)

    Важно:
    - никаких глобальных hardcoded fallback-типов модуль не добавляет;
    - L4 вызывается только при наличии реального candidate space.
    """
    details = details or {}

    shortlist_from_voting = _extract_shortlist_from_voting(details, top_k=base_top_k)
    shortlist = shortlist_from_voting or build_llm_shortlist(
        candidates,
        top_k=base_top_k,
        details=None,
    )

    result: list[str] = []
    seen: set[str] = set()

    for type_code in shortlist:
        if _is_valid_type_code(type_code) and type_code not in seen:
            result.append(type_code)
            seen.add(type_code)
        if len(result) >= max_total:
            break

    contradiction = bool(details.get("contradiction_detected", False))
    domain_conflict = bool(details.get("domain_conflict", False))

    family_selected: list[str] = []
    family_seed_types: list[str] = []

    remaining = max(0, max_total - len(result))
    if remaining > 0 and shortlist:
        if domain_conflict or contradiction:
            family_seed_types = _top2_seed_types(details) or shortlist[:2]
        else:
            family_seed_types = shortlist

        family_candidates = expand_llm_types_by_family(
            registry,
            family_seed_types,
            limit=remaining,
        )
        for type_code in family_candidates:
            if _is_valid_type_code(type_code) and type_code not in seen:
                result.append(type_code)
                family_selected.append(type_code)
                seen.add(type_code)
            if len(result) >= max_total:
                break

    result = result[:max_total]
    result_set = set(result)

    # Диагностика пустого result.
    # Единственная реальная причина — отсутствие shortlist:
    # если shortlist непустой, его элементы гарантированно попадают
    # в result на первом цикле выше, поэтому result не может быть пустым
    # при наличии shortlist с валидными type_code.
    empty_candidate_space = len(result) == 0
    empty_reason: str | None = "no_shortlist_and_no_candidates" if empty_candidate_space else None

    source_map = {
        "shortlist": [t for t in shortlist if t in result_set],
        "family_seed_types": [t for t in family_seed_types if t in result_set or t in shortlist],
        "family": family_selected,
        "contradiction_detected": contradiction,
        "domain_conflict": domain_conflict,
        "used_voting_ranking": bool(shortlist_from_voting),
        "empty_candidate_space": empty_candidate_space,
        "empty_reason": empty_reason,
    }

    return result, source_map


# ══════════════════════════════════════════════════════════════════════
# should_run_l4 — централизованный gating для L4
# ══════════════════════════════════════════════════════════════════════


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

    Инварианты (гарантированы кодом):
      1. strong_final=True  ⟹  need_adjudication=False
         (strong_final математически исключает все компоненты raw_need_adjudication)
      2. strong_single_no_conflict=True  ⟹  need_adjudication=False
         (явное подавление через: need_adjudication = raw AND NOT strong_single)
      3. skip_l4=True  ⟹  skip_reason is not None
         (цепочка if/elif покрывает все случаи skip_l4=True)
      4. need_adjudication=False  ⟹  skip_l4=True
         (через условие `not need_adjudication` в skip_l4)

    Логика:
    - L4 вызывается только если:
      * включён флагом;
      * LLM-драйвер доступен;
      * есть текст;
      * есть allowed_types;
      * нужен adjudication (подавленный);
      * L4 вообще полезен для текущего quality profile;
      * и нет блокирующих strong_final / strong_single_no_conflict.
    """
    details = details or {}

    has_source_text = bool(llm_source_text and llm_source_text.strip())
    normalized_allowed_types = [
        _normalize_type_code(t) for t in (allowed_types or []) if _is_valid_type_code(t)
    ]
    has_allowed_types = bool(normalized_allowed_types)

    contradiction = bool(details.get("contradiction_detected", False))
    domain_conflict = bool(details.get("domain_conflict", False))
    input_quality = _safe_float(details.get("input_quality", 1.0), 1.0)

    strong_l2: float = settings.CLASSIFICATION_L2_STRONG
    strong_l3: float = settings.CLASSIFICATION_L3_STRONG
    margin_min: float = settings.CLASSIFICATION_L4_MARGIN_MIN
    min_input_quality: float = settings.CLASSIFICATION_L4_INPUT_QUALITY_MIN
    review_quality_floor: float = settings.CLASSIFICATION_L4_REVIEW_QUALITY_FLOOR

    voting = details.get("voting") if isinstance(details.get("voting"), dict) else {}
    support_count = _safe_int(
        voting.get("support_count", details.get("voting_support_count", 0)),
        0,
    )

    top_l2 = details.get("L2_top")
    top_l3 = details.get("L3_top")

    top_l2_conf = (
        _safe_float((top_l2 or {}).get("confidence", 0.0), 0.0) if isinstance(top_l2, dict) else 0.0
    )
    top_l3_conf = (
        _safe_float((top_l3 or {}).get("confidence", 0.0), 0.0) if isinstance(top_l3, dict) else 0.0
    )

    # ── strong_final: используем is_hybrid_confident для единого условия ──
    # Это та же проверка что и HYBRID shortcut в hybrid_classifier.py.
    # Если HYBRID shortcut не сработал (мы оказались здесь), то strong_final
    # тоже будет False — но только если final_conf_after_voting = voted conf.
    # Шаг 1 (hybrid_classifier.py) гарантирует это.
    strong_final = is_hybrid_confident(
        final_conf=final_conf_after_voting,
        voted_margin=voted_margin,
        support_count=support_count,
        contradiction=contradiction,
        domain_conflict=domain_conflict,
        hybrid_accept=hybrid_accept,
        margin_min=margin_min,
    )

    # ── strong_single_no_conflict: сильный одиночный сигнал без конфликта ──
    minimal_margin: float = settings.CLASSIFICATION_SINGLE_SOURCE_MARGIN_MIN
    if is_segment:
        strong_single_no_conflict = (
            top_l3_conf >= strong_l3
            and not contradiction
            and not domain_conflict
            and voted_margin >= minimal_margin
        )
    else:
        strong_single_no_conflict = (
            (top_l2_conf >= strong_l2 or top_l3_conf >= strong_l3)
            and not contradiction
            and not domain_conflict
            and voted_margin >= minimal_margin
        )

    # ── raw_need_adjudication: сырая потребность в adjudication ──────────
    # Вычисляется ДО подавления strong-флагами.
    # Используется для:
    #   - диагностики (поле в L4GateDecision);
    #   - вычисления review_preferred (если adjudication нужна, но L4 не может помочь).
    weak_support = support_count < 2
    weak_margin = voted_margin < margin_min
    weak_score = final_conf_after_voting < hybrid_accept

    _raw_need_adjudication = (
        weak_score or weak_margin or weak_support or contradiction or domain_conflict
    )

    # ── need_adjudication: подавленная версия ────────────────────────────
    # Инвариант 1: strong_final математически исключает _raw_need_adjudication=True
    #   (все условия strong_final — это отрицания компонент raw_need_adjudication).
    #   Подавление через `not strong_final` добавлено для явности и защиты от
    #   будущих изменений условий strong_final.
    # Инвариант 2: strong_single_no_conflict явно подавляет need_adjudication,
    #   даже если weak_support=True (support_count=1 при сильном L3/L2).
    need_adjudication = (
        _raw_need_adjudication and not strong_final and not strong_single_no_conflict
    )

    # ── l4_useful и review_preferred ─────────────────────────────────────
    weak_input_for_l4 = input_quality < min_input_quality
    very_weak_input = input_quality < review_quality_floor

    l4_useful = (
        has_source_text
        and has_allowed_types
        and not very_weak_input
        and not (weak_input_for_l4 and contradiction and weak_support)
    )

    # review_preferred опирается на _raw_need_adjudication (не подавленный),
    # потому что даже при strong_single_no_conflict документ может требовать
    # внимания если нет текста или типов для L4.
    # Но не при strong_final — там решение действительно окончательное.
    review_preferred = (
        _raw_need_adjudication
        and not strong_final
        and not strong_single_no_conflict
        and (
            not has_source_text
            or not has_allowed_types
            or very_weak_input
            or (weak_input_for_l4 and contradiction and weak_support)
        )
    )

    # ── skip_l4 ───────────────────────────────────────────────────────────
    skip_l4 = (
        strong_final
        or strong_single_no_conflict
        or not l4_enabled
        or not llm_available
        or not has_source_text
        or not has_allowed_types
        or review_preferred
        or not need_adjudication
        or not l4_useful
    )

    # ── skip_reason ───────────────────────────────────────────────────────
    # Единственный owner skip_reason — эта функция (policy).
    # Executor только читает и сериализует, не переопределяет.
    # Инвариант 3: если skip_l4=True, то skip_reason всегда не None.
    skip_reason: str | None = None
    adjudication_reason: str | None = None

    if strong_final:
        skip_reason = "strong_final"
    elif strong_single_no_conflict:
        skip_reason = "strong_single_no_conflict"
    elif not l4_enabled:
        skip_reason = "l4_disabled"
    elif not llm_available:
        skip_reason = "llm_unavailable"
    elif not has_source_text:
        skip_reason = "missing_source_text"
    elif not has_allowed_types:
        skip_reason = "missing_allowed_types"
    elif review_preferred:
        skip_reason = "manual_review_preferred"
    elif not l4_useful:
        skip_reason = "l4_not_useful"
    elif not need_adjudication:
        skip_reason = "no_adjudication_needed"

    # ── adjudication_reason ───────────────────────────────────────────────
    # Заполняется если raw_need_adjudication=True (сырая потребность была).
    # Используем _raw_need_adjudication, а не need_adjudication, чтобы
    # сохранить причину даже когда adjudication подавлена strong-флагами.
    if _raw_need_adjudication:
        if contradiction:
            adjudication_reason = "contradiction_detected"
        elif domain_conflict:
            adjudication_reason = "domain_conflict"
        elif weak_support:
            adjudication_reason = "weak_multi_level_support"
        elif weak_margin:
            adjudication_reason = "low_margin"
        elif weak_score:
            adjudication_reason = "low_confidence"
        else:
            adjudication_reason = "adjudication_needed"

    return L4GateDecision(
        l4_enabled=l4_enabled,
        llm_available=llm_available,
        has_source_and_types=(has_source_text and has_allowed_types),
        has_source_text=has_source_text,
        has_allowed_types=has_allowed_types,
        need_adjudication=need_adjudication,
        raw_need_adjudication=_raw_need_adjudication,
        skip_l4=skip_l4,
        strong_single_no_conflict=strong_single_no_conflict,
        strong_final=strong_final,
        contradiction_detected=contradiction,
        input_quality=input_quality,
        domain_conflict=domain_conflict,
        final_conf_after_voting=final_conf_after_voting,
        voted_margin=voted_margin,
        weak_input_for_l4=weak_input_for_l4,
        l4_useful=l4_useful,
        review_preferred=review_preferred,
        skip_reason=skip_reason,
        adjudication_reason=adjudication_reason,
    )
