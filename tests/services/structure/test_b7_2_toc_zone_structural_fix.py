"""
B7.2 — структурный фикс ToC-зоны.

Проблема (run 767a1d87, deal 21679b18):
  ToC-строка "7.3 Приложение № 1: Форма Акта" (стр. 2) трактовалась как
  тело клаузы. Legal_unit для main_contract:7.3 получал start_page=2,
  exact_text = строки оглавления. Viewer открывал стр. 2 вместо стр. 6
  (реальный текст клаузы 7.3 в теле документа).

Решение:
  1. _heading_builder._core: _is_toc_zone(meta) → toc_entry=True
     для кандидатов в pre_toc/in_toc зоне (структурный сигнал,
     вычислен preamble classifier'ом).
  2. _range_logic._compute_own_range: для ToC-zone heading с детьми
     own_range = только сам элемент (изоляция, не поглощает ToC-строки).
  3. legal_unit_builder._compute_citability: skeleton / toc_rebuild
     → citability low (не retrieval-target).

Универсальность:
  - опирается на _preamble_zone (структурный сигнал, не текст)
  - не зависит от языка, типа документа, формата
  - работает для любого уровня вложенности uid
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.structure._heading_builder._core import (
    _is_toc_zone,
    _scored_to_heading_candidate,
)
from services.structure._hierarchy_builder._range_logic import _compute_own_range
from services.structure.legal_unit_builder import _compute_citability


# ────────────────────────────────────────────────────────────────────────────
# 1. _is_toc_zone — структурный сигнал
# ────────────────────────────────────────────────────────────────────────────


class TestIsTocZone:
    def test_in_toc_returns_true(self):
        assert _is_toc_zone({"_preamble_zone": "in_toc"}) is True

    def test_pre_toc_returns_true(self):
        assert _is_toc_zone({"_preamble_zone": "pre_toc"}) is True

    def test_post_toc_returns_false(self):
        assert _is_toc_zone({"_preamble_zone": "post_toc"}) is False

    def test_empty_zone_returns_false(self):
        assert _is_toc_zone({"_preamble_zone": ""}) is False

    def test_missing_zone_returns_false(self):
        assert _is_toc_zone({}) is False

    def test_none_returns_false(self):
        assert _is_toc_zone(None) is False

    def test_uppercase_normalized(self):
        assert _is_toc_zone({"_preamble_zone": "IN_TOC"}) is True


# ────────────────────────────────────────────────────────────────────────────
# 2. _scored_to_heading_candidate — toc_entry из _preamble_zone
# ────────────────────────────────────────────────────────────────────────────


def _make_scored_candidate(*, raw_uid: str, preamble_zone: str | None, strong_toc: bool = False):
    """Минимальный ScoredHeadingCandidate для тестов."""
    from services.structure.heading_llm_refiner import ScoredHeadingCandidate

    meta = {
        "raw_uid": raw_uid,
        "effective_uid": f"main_contract:{raw_uid}",
        "strong_toc_confirmation": strong_toc,
        "possible_toc": False,
    }
    if preamble_zone is not None:
        meta["_preamble_zone"] = preamble_zone
    return ScoredHeadingCandidate(
        elem_i=21,
        page=2,
        raw_text=f"{raw_uid} title",
        uid=raw_uid,
        title=f"Title {raw_uid}",
        decision="accepted",
        reason="accepted",
        score=0.9,
        decision_source="rules",
        scope="main_contract",
        metadata=meta,
    )


class TestScoredToHeadingCandidateTocEntry:
    def test_in_toc_candidate_sets_toc_entry(self):
        scored = _make_scored_candidate(raw_uid="7.3", preamble_zone="in_toc")
        cand = _scored_to_heading_candidate(scored)
        assert cand is not None
        assert cand.toc_entry is True

    def test_pre_toc_candidate_sets_toc_entry(self):
        scored = _make_scored_candidate(raw_uid="7.3", preamble_zone="pre_toc")
        cand = _scored_to_heading_candidate(scored)
        assert cand is not None
        assert cand.toc_entry is True

    def test_post_toc_candidate_toc_entry_from_strong_toc(self):
        scored = _make_scored_candidate(raw_uid="7.3", preamble_zone="post_toc", strong_toc=False)
        cand = _scored_to_heading_candidate(scored)
        assert cand is not None
        assert cand.toc_entry is False

    def test_post_toc_with_strong_toc_still_toc_entry(self):
        scored = _make_scored_candidate(raw_uid="7.3", preamble_zone="post_toc", strong_toc=True)
        cand = _scored_to_heading_candidate(scored)
        assert cand is not None
        assert cand.toc_entry is True


# ────────────────────────────────────────────────────────────────────────────
# 3. _compute_own_range — изоляция ToC-zone heading
# ────────────────────────────────────────────────────────────────────────────


def _make_node(*, raw_uid: str, source_elem_i: int, children_uids: list[str], level: int = 2):
    """Минимальный MutableHierarchyNode-like объект."""
    children = [
        SimpleNamespace(raw_uid=cu, effective_uid=f"main_contract:{cu}")
        for cu in children_uids
    ]
    return SimpleNamespace(
        raw_uid=raw_uid,
        level=level,
        children=children,
        diagnostics={"source_elem_i": source_elem_i},
        own_element_ids=[],
        own_text="",
    )


def _make_element(*, elem_i: int, page: int, preamble_zone: str, text: str = ""):
    return {
        "element_id": f"ru:node:{page}:{elem_i:04d}",
        "page": page,
        "_preamble_zone": preamble_zone,
        "text": text,
    }


class TestComputeOwnRangeTocIsolation:
    def test_toc_zone_heading_with_children_isolated(self):
        """ToC-heading с детьми — own_range = [heading, heading+1)."""
        # elements: [0..4] in_toc, [5..9] post_toc
        elements = (
            [_make_element(elem_i=i, page=2, preamble_zone="in_toc") for i in range(5)]
            + [_make_element(elem_i=i, page=6, preamble_zone="post_toc") for i in range(5, 10)]
        )
        # heading 7.3 на elem_i=2, дети 7.3.1..7.3.3 на elem_i=5,6,7
        node = _make_node(
            raw_uid="7.3",
            source_elem_i=2,
            children_uids=["7.3.1", "7.3.2", "7.3.3"],
            level=2,
        )
        key_to_elem_i = {
            ("main_contract", "7.3.1"): 5,
            ("main_contract", "7.3.2"): 6,
            ("main_contract", "7.3.3"): 7,
        }
        result = _compute_own_range(
            raw_uid="7.3",
            node=node,
            headings=[],
            elements=elements,
            key_to_elem_i=key_to_elem_i,
            key_to_heading_index={},
            scope="main_contract",
            scope_boundaries={},
        )
        # Изолированный range — только heading-элемент
        assert result.start_elem_i == 2
        assert result.end_elem_i == 3
        assert result.range_end_reason == "toc_zone_heading_isolated"

    def test_post_toc_heading_not_isolated(self):
        """Post_toc heading (нормальная клауза) — range как обычно, не изолирован."""
        elements = (
            [_make_element(elem_i=i, page=2, preamble_zone="in_toc") for i in range(2)]
            + [_make_element(elem_i=i, page=6, preamble_zone="post_toc") for i in range(2, 8)]
        )
        # heading 5.1 на elem_i=2 (post_toc), дети 5.1.1, 5.1.2 на 4,5
        node = _make_node(
            raw_uid="5.1",
            source_elem_i=2,
            children_uids=["5.1.1", "5.1.2"],
            level=2,
        )
        key_to_elem_i = {
            ("main_contract", "5.1.1"): 4,
            ("main_contract", "5.1.2"): 5,
        }
        result = _compute_own_range(
            raw_uid="5.1",
            node=node,
            headings=[],
            elements=elements,
            key_to_elem_i=key_to_elem_i,
            key_to_heading_index={},
            scope="main_contract",
            scope_boundaries={},
        )
        # НЕ изолирован — end_elem_i больше start+1 (первый ребёнок = 4)
        assert result.start_elem_i == 2
        assert result.end_elem_i > 3
        assert result.range_end_reason != "toc_zone_heading_isolated"

    def test_toc_zone_leaf_heading_not_isolated(self):
        """ToC-zone heading БЕЗ детей — изоляция не применяется (листовая обработка)."""
        elements = (
            [_make_element(elem_i=i, page=2, preamble_zone="in_toc") for i in range(5)]
            + [_make_element(elem_i=i, page=6, preamble_zone="post_toc") for i in range(5, 8)]
        )
        # Leaf ToC-строка 7.1 — без детей
        node = _make_node(raw_uid="7.1", source_elem_i=1, children_uids=[], level=2)
        result = _compute_own_range(
            raw_uid="7.1",
            node=node,
            headings=[],
            elements=elements,
            key_to_elem_i={},
            key_to_heading_index={},
            scope="main_contract",
            scope_boundaries={},
        )
        # Leaf — идёт через barrier-логику (end до post_toc), не через isolation
        assert result.start_elem_i == 1
        # Не изолирован до +1
        assert result.range_end_reason != "toc_zone_heading_isolated"


# ────────────────────────────────────────────────────────────────────────────
# 4. _compute_citability — skeleton / toc_rebuild → low
# ────────────────────────────────────────────────────────────────────────────


class TestComputeCitabilitySkeleton:
    def test_skeleton_mode_returns_low(self):
        node = {
            "content_mode": "skeleton",
            "node_origin": "toc_rebuild",
            "own_text": "7.3 Приложение № 1",
            "own_element_ids": ["elem1"],
        }
        c = _compute_citability(node)
        assert c.citability_band == "low"
        assert c.citability_score == 0.1

    def test_toc_rebuild_origin_returns_low(self):
        node = {
            "content_mode": "full_text",
            "node_origin": "toc_rebuild",
            "own_text": "some text",
            "own_element_ids": ["elem1"],
        }
        c = _compute_citability(node)
        assert c.citability_band == "low"
        assert c.citability_score == 0.1

    def test_full_text_semantic_heading_high(self):
        node = {
            "content_mode": "full_text",
            "node_origin": "semantic_heading",
            "own_text": "real clause body",
            "own_element_ids": ["elem1"],
            "citability_hint": "high",
        }
        c = _compute_citability(node)
        assert c.citability_band == "high"
        assert c.citability_score >= 0.8

    def test_technical_fallback_still_takes_priority(self):
        node = {
            "content_mode": "technical_fragment",
            "node_origin": "technical_fallback",
            "own_text": "x",
        }
        c = _compute_citability(node)
        assert c.is_technical_fallback is True


# ────────────────────────────────────────────────────────────────────────────
# 5. Integration — кейс 7.3 из run 767a1d87
# ────────────────────────────────────────────────────────────────────────────


class TestIntegrationCase73:
    def test_toc_zone_heading_full_chain(self):
        """
        Симулируем: ToC-строка 7.3 на стр. 2, 3 ToC-элемента рядом,
        5 children на стр. 6. Проверяем цепочку:
          toc_entry=True → own_range=[21,22) → citability=low.
        """
        # 1) Кандидат в in_toc-зоне → toc_entry=True
        scored = _make_scored_candidate(raw_uid="7.3", preamble_zone="in_toc")
        cand = _scored_to_heading_candidate(scored)
        assert cand is not None
        assert cand.toc_entry is True, "ToC-кандидат должен получить toc_entry=True"

        # 2) Own range изолирован — только сам heading.
        # ВАЖНО: _compute_own_range работает с индексами в списке elements,
        # не с layout elem_i. Используем list-index.
        # elements: [0..2] = ToC (in_toc), [3..7] = body (post_toc)
        elements = (
            [_make_element(elem_i=i, page=2, preamble_zone="in_toc") for i in range(3)]
            + [_make_element(elem_i=i, page=6, preamble_zone="post_toc") for i in range(3, 8)]
        )
        node = _make_node(
            raw_uid="7.3",
            source_elem_i=0,  # 7.3 ToC-маркер — индекс 0 в elements
            children_uids=["7.3.1", "7.3.2", "7.3.3", "7.3.4", "7.3.5"],
            level=2,
        )
        key_to_elem_i = {
            ("main_contract", "7.3.1"): 3,  # первый post_toc-элемент
            ("main_contract", "7.3.2"): 4,
            ("main_contract", "7.3.3"): 5,
            ("main_contract", "7.3.4"): 6,
            ("main_contract", "7.3.5"): 7,
        }
        range_result = _compute_own_range(
            raw_uid="7.3",
            node=node,
            headings=[],
            elements=elements,
            key_to_elem_i=key_to_elem_i,
            key_to_heading_index={},
            scope="main_contract",
            scope_boundaries={},
        )
        assert range_result.range_end_reason == "toc_zone_heading_isolated"
        assert range_result.end_elem_i - range_result.start_elem_i == 1

        # 3) Citability=low для skeleton-узла
        node_dict = {
            "content_mode": "skeleton",
            "node_origin": "toc_rebuild",
            "own_text": "7.3 Приложение № 1",
            "own_element_ids": ["elem21"],
        }
        cit = _compute_citability(node_dict)
        assert cit.citability_band == "low"
        assert cit.citability_score == 0.1
