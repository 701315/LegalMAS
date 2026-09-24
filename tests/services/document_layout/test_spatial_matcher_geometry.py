"""Геометрические инварианты SpatialMatcher без PDF и внешних сервисов.

Разместить в tests/services/document_layout/test_spatial_matcher_geometry.py.
Сначала запустить на текущем коде: негативные тесты должны обнаружить дефекты.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.document_layout.spatial_marker_recovery import (
    DocumentFingerprint,
    OrphanMarker,
    SpatialMatcher,
)


def _fingerprint(scale: float = 1.0) -> DocumentFingerprint:
    return DocumentFingerprint(
        median_line_height=12.0 * scale,
        median_font_size=11.0 * scale,
        y_tolerance=6.0 * scale,
        column_clusters=[],
        page_count=2,
    )


def _atom(
    bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
    marker: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        bbox=bbox,
        page=page,
        marker=marker,
        text="Условия исполнения договора",
    )


def _orphan(
    bbox: tuple[float, float, float, float],
    *,
    page: int = 1,
    text: str = "7.2",
) -> OrphanMarker:
    return OrphanMarker(
        text=text,
        bbox=bbox,
        page=page,
        font_size=11.0,
        grammar_level=2,
        confidence=1.0,
    )


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_distant_marker_cannot_be_compensated_by_other_features(scale: float) -> None:
    """X, колонка и качество маркера не компенсируют большой разрыв по Y."""
    atom = _atom((100 * scale, 300 * scale, 320 * scale, 315 * scale))
    marker = _orphan((109 * scale, 95 * scale, 115 * scale, 105 * scale))

    matches = SpatialMatcher(_fingerprint(scale)).match([atom], [marker], "far-y")

    assert matches == []


def test_marker_to_right_of_text_block_is_not_a_marginal_prefix() -> None:
    """Маркер целиком справа от текстового блока не является его префиксом."""
    atom = _atom((100, 100, 150, 112))
    marker = _orphan((165, 94, 175, 106))

    matches = SpatialMatcher(_fingerprint()).match([atom], [marker], "right-of-text")

    assert matches == []


def test_nearby_marker_left_of_first_line_is_recovered() -> None:
    """Негативные проверки не должны отключать корректное восстановление."""
    atom = _atom((120, 100, 300, 112))
    marker = _orphan((100, 94, 110, 106))

    matches = SpatialMatcher(_fingerprint()).match([atom], [marker], "valid-left")

    assert len(matches) == 1
    assert matches[0].atom is atom
    assert matches[0].marker is marker


def test_multiline_atom_matches_marker_near_its_first_line() -> None:
    """Высота всего блока не должна исключать маркер у первой строки."""
    atom = _atom((120, 100, 400, 300))
    marker = _orphan((100, 94, 110, 106))

    matches = SpatialMatcher(_fingerprint()).match([atom], [marker], "multiline")

    assert len(matches) == 1
    assert matches[0].atom is atom
    assert matches[0].marker is marker


def test_marker_on_other_page_is_not_matched() -> None:
    """Сопоставления должны оставаться внутри страницы."""
    atom = _atom((120, 100, 300, 112), page=2)
    marker = _orphan((100, 94, 110, 106), page=1)

    matches = SpatialMatcher(_fingerprint()).match([atom], [marker], "other-page")

    assert matches == []


def test_atom_with_native_marker_is_not_a_recovery_target() -> None:
    """Нативный маркер нельзя заменять восстановленным."""
    atom = _atom((120, 100, 300, 112), marker="7.2")
    marker = _orphan((100, 94, 110, 106), text="7.3")

    matches = SpatialMatcher(_fingerprint()).match([atom], [marker], "native")

    assert matches == []


def test_no_assignment_when_all_pairs_are_geometrically_invalid() -> None:
    """Назначение допускает оставить все атомы и маркеры без пары."""
    atoms = [
        _atom((100, 300, 310, 312)),
        _atom((100, 350, 310, 362)),
    ]
    markers = [
        _orphan((109, 95, 115, 105), text="7.2"),
        _orphan((109, 145, 115, 155), text="7.3"),
    ]

    matches = SpatialMatcher(_fingerprint()).match(atoms, markers, "unmatched")

    assert matches == []

def test_marker_far_to_left_is_not_a_prefix_despite_matching_y() -> None:
    """Совпадение строки не оправдывает произвольно большой X-разрыв."""
    atom = _atom((400, 100, 450, 112))
    marker = _orphan((0, 94, 10, 106))

    matches = SpatialMatcher(_fingerprint()).match(
        [atom], [marker], "far-left"
    )

    assert matches == []

def test_nearby_marker_with_moderate_indent_is_recovered() -> None:
    """Допустимый отступ между маркером и началом текста сохраняется."""
    atom = _atom((165, 100, 300, 112))
    marker = _orphan((100, 94, 110, 106))

    matches = SpatialMatcher(_fingerprint()).match(
        [atom], [marker], "moderate-indent"
    )

    assert len(matches) == 1
    assert matches[0].atom is atom
    assert matches[0].marker is marker
