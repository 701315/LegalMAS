# src/services/structure/cohesion/_signals.py

"""
Вычисление CohesionSignals и CohesionScore из структурных артефактов.

Все функции pure и deterministic.
Никакого LLM, никаких embeddings.

Scoring policy:
- base score строится из структурных сигналов;
- каждый негативный сигнал снижает score;
- каждый позитивный сигнал повышает;
- результат clamp в [0.0, 1.0].
"""

from __future__ import annotations

from services.structure.models import FrozenHierarchyNode

from ._traversal import are_numbering_continuous, is_appendix_boundary
from ._types import (
    CohesionBreakReason,
    CohesionEdgeKind,
    CohesionSignals,
)


# ============================================================================
# Signal extraction
# ============================================================================

def extract_signals(
    left: FrozenHierarchyNode,
    right: FrozenHierarchyNode,
    *,
    kind: CohesionEdgeKind,
    window_distance: int,
    crossref_outgoing: dict[str, tuple[str, ...]],
    crossref_incoming: dict[str, tuple[str, ...]],
) -> CohesionSignals:
    """
    Извлекает структурные сигналы для пары узлов.

    Все сигналы детерминированные — из FrozenHierarchyNode и CrossReferenceGraph.

    Параметры:
    - left / right: анализируемая пара узлов
    - kind: тип edge (sibling/within_section/crossref)
    - window_distance: расстояние в sliding window (1 = adjacent)
    - crossref_outgoing: outgoing_index из CrossReferenceGraph
    - crossref_incoming: incoming_index из CrossReferenceGraph
    """
    same_scope = left.scope == right.scope

    # level_delta: для siblings = 0, для parent-child = abs(right.level - left.level)
    level_delta = abs(right.level - left.level)

    numbering_continuous = are_numbering_continuous(left, right)

    # Cross-reference: есть ли прямая ссылка в любую сторону
    left_targets = crossref_outgoing.get(left.effective_uid, ())
    right_targets = crossref_outgoing.get(right.effective_uid, ())
    has_crossref = (
        right.effective_uid in left_targets
        or left.effective_uid in right_targets
    )

    both_have_own_text = bool(left.own_text) and bool(right.own_text)

    appendix_bnd = is_appendix_boundary(left, right)

    return CohesionSignals(
        same_scope=same_scope,
        level_delta=level_delta,
        numbering_continuous=numbering_continuous,
        has_crossref=has_crossref,
        window_distance=window_distance,
        both_have_own_text=both_have_own_text,
        is_appendix_boundary=appendix_bnd,
    )


# ============================================================================
# Score computation
# ============================================================================

def compute_cohesion_score(
    signals: CohesionSignals,
    *,
    kind: CohesionEdgeKind,
) -> tuple[float, CohesionBreakReason]:
    """
    Вычисляет cohesion score из структурных сигналов.

    Возвращает (score, break_reason).
    break_reason = NONE если score >= 0.35 (не strong boundary).

    Scoring policy v1.0:
    - base score зависит от kind edge;
    - позитивные сигналы добавляют к score;
    - негативные сигналы вычитают из score;
    - appendix_boundary — сильный negative (почти всегда strong boundary);
    - scope_change — сильный negative;
    - has_crossref — сильный positive (явная структурная связь).

    Complexity: O(1).
    """
    # ── Base score по типу edge ──────────────────────────────────────────────
    if kind == CohesionEdgeKind.WITHIN_SECTION:
        # Parent-child всегда начинают с высокого base
        score = 0.75
    elif kind == CohesionEdgeKind.CROSSREF_NEIGHBOR:
        # Cross-ref сам по себе уже является сигналом связи
        score = 0.65
    else:
        # Sibling window: начинаем с умеренного base
        score = 0.55

    # ── Позитивные сигналы ───────────────────────────────────────────────────

    if signals.numbering_continuous:
        # "1.1" → "1.2" — явная continuity
        score += 0.20

    if signals.has_crossref:
        # Прямая cross-reference = явная структурная связь
        score += 0.15

    if signals.both_have_own_text:
        # Оба узла имеют реальный текст (не skeleton)
        score += 0.05

    # ── Негативные сигналы ───────────────────────────────────────────────────

    if not signals.same_scope:
        # Разные scopes = сильная граница
        score -= 0.40

    if signals.is_appendix_boundary:
        # Переход к appendix = очень сильная граница
        score -= 0.45

    if signals.level_delta > 1:
        # Прыжок через уровни — структурный разрыв
        score -= 0.15 * min(signals.level_delta - 1, 3)

    if signals.window_distance > 1:
        # Чем дальше в window — тем слабее связь
        # distance=1: -0.00, distance=2: -0.05, distance=3: -0.10, ...
        score -= 0.05 * (signals.window_distance - 1)

    # ── Clamp ────────────────────────────────────────────────────────────────
    score = max(0.0, min(1.0, score))

    # ── Break reason ─────────────────────────────────────────────────────────
    break_reason = CohesionBreakReason.NONE

    if score < 0.35:
        # Определяем главную причину низкого score
        if signals.is_appendix_boundary:
            break_reason = CohesionBreakReason.APPENDIX_BOUNDARY
        elif not signals.same_scope:
            break_reason = CohesionBreakReason.SCOPE_CHANGE
        elif signals.level_delta > 2:
            break_reason = CohesionBreakReason.LEVEL_JUMP
        elif not signals.numbering_continuous and kind == CohesionEdgeKind.SIBLING_WINDOW:
            break_reason = CohesionBreakReason.NUMBERING_GAP
        elif kind == CohesionEdgeKind.CROSSREF_NEIGHBOR and not signals.has_crossref:
            break_reason = CohesionBreakReason.NO_CROSSREF_LINK
        else:
            break_reason = CohesionBreakReason.NUMBERING_GAP

    return score, break_reason


