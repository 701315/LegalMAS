from services.structure.heading_builder import _candidate_priority_tuple
from services.structure._heading_builder._ranking import _select_best_candidates_by_uid
from services.structure.heading_llm_refiner import ScoredHeadingCandidate


def make_candidate(
    *,
    uid: str,
    title: str,
    score: float,
    decision: str = "accepted",
    toc_match_type: str | None = None,
    toc_match_score: float = 0.0,
    element_type: str = "heading_candidate",
    elem_i: int = 0,
    preamble_zone: str | None = None,
    possible_toc: bool = False,
):
    meta = {
        "raw_uid": uid,
        "effective_uid": f"main_contract::{uid}",
        "element_type": element_type,
        "toc_match_type": toc_match_type,
        "toc_match_score": toc_match_score,
    }
    if preamble_zone is not None:
        meta["_preamble_zone"] = preamble_zone
    if possible_toc:
        meta["possible_toc"] = True
    return ScoredHeadingCandidate(
        elem_i=elem_i,
        page=1,
        raw_text=f"{uid} {title}",
        uid=uid,
        title=title,
        decision=decision,
        reason="accepted",
        score=score,
        decision_source="rules",
        scope="main_contract",
        metadata=meta,
    )


def test_candidate_priority_tuple_prefers_exact_toc_over_higher_score():
    exact_toc_candidate = make_candidate(
        uid="2.1",
        title="Definitions",
        score=0.88,
        toc_match_type="exact",
        toc_match_score=0.08,
        elem_i=10,
    )
    no_toc_candidate = make_candidate(
        uid="2.1",
        title="Definitions",
        score=0.95,
        toc_match_type=None,
        toc_match_score=0.0,
        elem_i=9,
    )

    assert _candidate_priority_tuple(exact_toc_candidate) > _candidate_priority_tuple(no_toc_candidate)


def test_candidate_priority_tuple_prefers_fuzzy_toc_over_no_toc():
    fuzzy_toc_candidate = make_candidate(
        uid="3",
        title="Representations",
        score=0.90,
        toc_match_type="fuzzy",
        toc_match_score=0.045,
        elem_i=10,
    )
    no_toc_candidate = make_candidate(
        uid="3",
        title="Representations",
        score=0.93,
        toc_match_type=None,
        toc_match_score=0.0,
        elem_i=8,
    )

    assert _candidate_priority_tuple(fuzzy_toc_candidate) > _candidate_priority_tuple(no_toc_candidate)


def test_candidate_priority_tuple_still_prefers_accepted_over_ambiguous():
    accepted_candidate = make_candidate(
        uid="4",
        title="Covenants",
        score=0.85,
        decision="accepted",
        toc_match_type=None,
        toc_match_score=0.0,
    )
    ambiguous_candidate = make_candidate(
        uid="4",
        title="Covenants",
        score=0.99,
        decision="ambiguous",
        toc_match_type="exact",
        toc_match_score=0.08,
    )

    assert _candidate_priority_tuple(accepted_candidate) > _candidate_priority_tuple(ambiguous_candidate)

# ────────────────────────────────────────────────────────────────────────────
# B7.1 — Body-кандидат должен побеждать ToC при коллизии uid.
# Опирается на _preamble_zone (in_toc / pre_toc / post_toc).
# Реальная клауза живёт в post_toc, ToC-запись — только указатель.
# ────────────────────────────────────────────────────────────────────────────


def test_body_candidate_wins_over_toc_candidate():
    """Body (post_toc) побеждает ToC (in_toc), даже если у ToC exact match."""
    toc_candidate = make_candidate(
        uid="7.3",
        title="Приложение № 1: Форма Акта",
        score=0.80,
        toc_match_type="exact",
        toc_match_score=1.0,
        element_type="list_item",
        elem_i=20,
        preamble_zone="in_toc",
    )
    body_candidate = make_candidate(
        uid="7.3",
        title="Приложение № 1: Форма Акта",
        score=0.90,
        toc_match_type=None,
        toc_match_score=0.0,
        element_type="heading",
        elem_i=84,
        preamble_zone="post_toc",
    )

    assert _candidate_priority_tuple(body_candidate) > _candidate_priority_tuple(toc_candidate)


def test_body_priority_overrides_toc_match_type():
    """Даже fuzzy/exact ToC не помогает, если есть Body-кандидат."""
    toc_candidate = make_candidate(
        uid="7.3",
        title="X",
        score=0.99,
        toc_match_type="fuzzy",
        toc_match_score=0.9,
        elem_i=10,
        preamble_zone="in_toc",
    )
    body_candidate = make_candidate(
        uid="7.3",
        title="X",
        score=0.50,  # ниже score у ToC
        toc_match_type=None,
        toc_match_score=0.0,
        elem_i=90,
        preamble_zone="post_toc",
    )

    assert _candidate_priority_tuple(body_candidate) > _candidate_priority_tuple(toc_candidate)


def test_no_preamble_zone_is_legacy_safe():
    """Без _preamble_zone (legacy документы) in_body_priority=1 — не ухудшает старую логику."""
    no_zone = make_candidate(
        uid="1.1",
        title="Definitions",
        score=0.9,
        toc_match_type=None,
        elem_i=5,
        preamble_zone=None,
    )
    t = _candidate_priority_tuple(no_zone)
    assert t[0] == 1, f"expected in_body_priority=1, got {t[0]}"


def test_pre_toc_candidate_has_zero_body_priority():
    """pre_toc — тоже ToC-зона, in_body_priority=0."""
    pre_toc_candidate = make_candidate(
        uid="1.1",
        title="Definitions",
        score=0.9,
        elem_i=5,
        preamble_zone="pre_toc",
    )
    t = _candidate_priority_tuple(pre_toc_candidate)
    assert t[0] == 0, f"expected in_body_priority=0, got {t[0]}"


def test_select_best_candidates_by_uid_keeps_body_over_toc():
    """
    Интеграционный: реальный сценарий из run d3aa0487.

    В pipeline оба кандидата могут иметь possible_toc=True (ToC-детектор
    даёт false positives на body-элементах рядом с оглавлением). Тогда они
    попадают в одну группу дедупликации (is_toc=True для обоих), и решение
    определяется _candidate_priority_tuple. B7.1 гарантирует победу Body.
    """
    toc_candidate = make_candidate(
        uid="7.3",
        title="Приложение № 1: Форма Акта",
        score=0.80,
        toc_match_type="exact",
        toc_match_score=1.0,
        element_type="list_item",
        elem_i=20,
        preamble_zone="in_toc",
        possible_toc=True,
    )
    body_candidate = make_candidate(
        uid="7.3",
        title="Приложение № 1: Форма Акта",
        score=0.90,
        toc_match_type=None,
        toc_match_score=0.0,
        element_type="heading",
        elem_i=84,
        preamble_zone="post_toc",
        possible_toc=True,
    )

    selected = _select_best_candidates_by_uid(
        [toc_candidate, body_candidate], document_id="test-doc"
    )
    assert len(selected) == 1, f"expected single winner, got {len(selected)}"
    winner = selected[0]
    assert winner.metadata.get("_preamble_zone") == "post_toc", (
        f"expected body candidate to win, got preamble_zone="
        f"{winner.metadata.get('_preamble_zone')}"
    )
    assert winner.elem_i == 84, f"expected elem_i=84, got {winner.elem_i}"
