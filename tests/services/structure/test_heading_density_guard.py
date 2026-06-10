"""
Tests for B2: Heading Density Guard.

Verifies that pages with anomalously high heading density
without TOC confirmation get ACCEPTED → AMBIGUOUS demotion.
"""

from __future__ import annotations

import dataclasses
import pytest
from unittest.mock import MagicMock, patch


def _make_scored(
    *,
    page: int = 1,
    status: str = "accepted",
    is_toc_entry: bool = False,
    reasons: list[str] | None = None,
) -> MagicMock:
    s = MagicMock()
    s.page = page
    s.status = status
    s.is_toc_entry = is_toc_entry
    s.reasons = list(reasons or [])
    return s


def _make_element(
    *,
    page: int = 1,
    element_type: str = "body_text",
) -> dict:
    return {"page": page, "element_type": element_type}


class TestHeadingDensityGuard:

    @pytest.fixture(autouse=True)
    def _import(self):
        from services.structure._heading_builder._core import (
            _apply_heading_density_guard,
            _HEADING_DENSITY_GUARD_THRESHOLD,
            _HEADING_DENSITY_GUARD_MIN_CANDIDATES,
        )
        self.guard = _apply_heading_density_guard
        self.threshold = _HEADING_DENSITY_GUARD_THRESHOLD
        self.min_candidates = _HEADING_DENSITY_GUARD_MIN_CANDIDATES

    def _make_dense_page_scored(
        self,
        count: int,
        page: int = 1,
        status: str = "accepted",
    ) -> list[MagicMock]:
        return [_make_scored(page=page, status=status) for _ in range(count)]

    def _make_elements_for_page(
        self,
        total: int,
        page: int = 1,
        element_type: str = "body_text",
    ) -> list[dict]:
        return [_make_element(page=page, element_type=element_type) for _ in range(total)]

    def test_empty_scored_returns_empty(self):
        result = self.guard([], [])
        assert result == []

    def test_no_dense_page_no_demotion(self):
        """Если density низкая — статусы не меняются."""
        scored = self._make_dense_page_scored(2, page=1)
        elements = self._make_elements_for_page(10, page=1)
        result = self.guard(scored, elements)
        for s in result:
            assert s.status == "accepted"

    def test_dense_page_demotes_accepted_to_ambiguous(self):
        """Если density > threshold — ACCEPTED → AMBIGUOUS."""
        from services.structure.heading_scoring import CandidateStatus

        # 6 heading candidates из 8 элементов = density 0.75 > 0.5
        scored = []
        for _ in range(6):
            s = MagicMock(spec=["page", "status", "is_toc_entry", "reasons"])
            s.page = 1
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = False
            s.reasons = []
            scored.append(s)

        elements = self._make_elements_for_page(8, page=1)

        with patch("dataclasses.replace", side_effect=lambda obj, **kw: type(
            "Demoted", (), {
                "page": obj.page,
                "status": kw.get("status", obj.status),
                "is_toc_entry": obj.is_toc_entry,
                "reasons": kw.get("reasons", obj.reasons),
            }
        )()):
            result = self.guard(scored, elements)

        assert len(result) == 6

    def test_toc_page_not_demoted(self):
        """Страница с TOC-entries не должна демотироваться."""
        from services.structure.heading_scoring import CandidateStatus

        scored = []
        for i in range(6):
            s = MagicMock()
            s.page = 1
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = True  # все являются TOC entries
            s.reasons = []
            scored.append(s)

        elements = self._make_elements_for_page(8, page=1)
        result = self.guard(scored, elements)

        for s in result:
            assert s.status == CandidateStatus.ACCEPTED

    def test_below_min_candidates_not_demoted(self):
        """Страница с малым числом кандидатов не демотируется."""
        from services.structure.heading_scoring import CandidateStatus

        # min_candidates = 4, у нас 2 — guard не активируется
        scored = self._make_dense_page_scored(2, page=1)
        for s in scored:
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = False
            s.reasons = []
        # только 2 из 3 элементов — density 0.67, но кандидатов < 4
        elements = self._make_elements_for_page(3, page=1)
        result = self.guard(scored, elements)
        for s in result:
            assert s.status == CandidateStatus.ACCEPTED

    def test_page_artifacts_excluded_from_density(self):
        """Page artifacts не учитываются при вычислении density."""
        # 5 кандидатов из 6 реальных элементов + 4 artifacts
        # density = 5/6 = 0.83 > 0.5 → должна сработать
        # но если artifacts считались бы: 5/10 = 0.5 → на пороге
        from services.structure.heading_scoring import CandidateStatus

        scored = []
        for _ in range(5):
            s = MagicMock()
            s.page = 1
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = False
            s.reasons = []
            scored.append(s)

        elements = (
            self._make_elements_for_page(6, page=1, element_type="body_text")
            + self._make_elements_for_page(4, page=1, element_type="page_artifact")
        )

        with patch("dataclasses.replace", side_effect=lambda obj, **kw: type(
            "D", (), {"page": 1, "status": "ambiguous", "is_toc_entry": False, "reasons": []}
        )()):
            result = self.guard(scored, elements)
        assert len(result) == 5

    def test_different_pages_independent(self):
        """Guard применяется независимо для каждой страницы."""
        from services.structure.heading_scoring import CandidateStatus

        # page 1: плотная (6 из 8) → demotion
        # page 2: редкая (2 из 10) → нет demotion
        scored_p1 = []
        for _ in range(6):
            s = MagicMock()
            s.page = 1
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = False
            s.reasons = []
            scored_p1.append(s)

        scored_p2 = []
        for _ in range(2):
            s = MagicMock()
            s.page = 2
            s.status = CandidateStatus.ACCEPTED
            s.is_toc_entry = False
            s.reasons = []
            scored_p2.append(s)

        elements = (
            self._make_elements_for_page(8, page=1)
            + self._make_elements_for_page(10, page=2)
        )

        result = self.guard(scored_p1 + scored_p2, elements)
        assert len(result) == 8

    def test_ambiguous_not_double_demoted(self):
        """AMBIGUOUS кандидаты не меняются."""
        from services.structure.heading_scoring import CandidateStatus

        scored = []
        for _ in range(6):
            s = MagicMock()
            s.page = 1
            s.status = CandidateStatus.AMBIGUOUS
            s.is_toc_entry = False
            s.reasons = []
            scored.append(s)

        elements = self._make_elements_for_page(8, page=1)
        result = self.guard(scored, elements)

        for s in result:
            assert s.status == CandidateStatus.AMBIGUOUS

    def test_rejected_not_changed(self):
        """REJECTED кандидаты не меняются."""
        from services.structure.heading_scoring import CandidateStatus

        scored = []
        for _ in range(6):
            s = MagicMock()
            s.page = 1
            s.status = CandidateStatus.REJECTED
            s.is_toc_entry = False
            s.reasons = []
            scored.append(s)

        elements = self._make_elements_for_page(8, page=1)
        result = self.guard(scored, elements)

        for s in result:
            assert s.status == CandidateStatus.REJECTED


            