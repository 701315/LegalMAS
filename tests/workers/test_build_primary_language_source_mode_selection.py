from __future__ import annotations

from types import SimpleNamespace

from workers.build_primary_language_source import (
    _determine_primary_source_build_mode,
    _primary_layout_materially_differs,
)


def _el(
    element_id: str,
    text: str,
    *,
    page: int = 1,
    el_type: str = "heading",
) -> dict:
    """
    Создать реалистичный layout-элемент для тестов.

    ВАЖНО:
    После Фазы 1 routing сравнение строится по frozenset element_id.
    Поэтому element_id обязателен — это production-контракт.
    """
    return {
        "element_id": element_id,
        "page": page,
        "type": el_type,
        "text": text,
    }


def _layout(elements: list[dict], *, metadata: dict | None = None) -> dict:
    return {
        "document_id": "doc-1",
        "document_version_id": "ver-1",
        "elements": elements,
        "tables": [],
        "metadata": metadata or {},
    }


def test_primary_layout_materially_differs_false_for_identical_layouts():
    raw_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
            _el("e002", "Текст договора", el_type="text"),
        ]
    )
    primary_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
            _el("e002", "Текст договора", el_type="text"),
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_false_for_metadata_only_changes():
    raw_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
        ],
        metadata={},
    )
    primary_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
        ],
        metadata={
            "language_pipeline": {"target_language": "ru"},
            "language_filter": {"structural_filter_used": False},
        },
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_false_for_text_only_changes():
    """
    После Фазы 1 изменение текста при тех же element_id НЕ является material diff.

    Это ключевое исправление production bug:
    текст мог меняться из-за sanitize, но состав элементов оставался тем же.
    """
    raw_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР / SALE AGREEMENT"),
        ]
    )
    primary_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is False


def test_primary_layout_materially_differs_true_when_element_removed_by_filter():
    raw_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
            _el("e002", "1 SALE AGREEMENT"),
        ]
    )
    primary_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
        ]
    )

    assert _primary_layout_materially_differs(raw_layout, primary_layout) is True


def test_determine_primary_source_build_mode_returns_reuse_for_unchanged_non_bilingual():
    decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
    raw_layout = _layout(
        [_el("e001", "1 ДОГОВОР")]
    )
    primary_layout = _layout(
        [_el("e001", "1 ДОГОВОР")]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "monolingual_reuse"


def test_determine_primary_source_build_mode_returns_reuse_for_text_only_change_non_bilingual():
    """
    Если меняется только текст, но element_id тот же → monolingual_reuse.

    Это основной новый контракт Фазы 1.
    """
    decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
    raw_layout = _layout(
        [_el("e001", "«Покупатель»")]
    )
    primary_layout = _layout(
        [_el("e001", "Покупатель")]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "monolingual_reuse"


def test_determine_primary_source_build_mode_returns_filtered_pdf_for_removed_element():
    decision = SimpleNamespace(is_bilingual=False, is_multilingual=False)
    raw_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
            _el("e002", "1 SALE AGREEMENT"),
        ]
    )
    primary_layout = _layout(
        [
            _el("e001", "1 ДОГОВОР"),
        ]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "monolingual_filtered_pdf"


def test_determine_primary_source_build_mode_returns_single_language_pdf_for_bilingual():
    decision = SimpleNamespace(is_bilingual=True, is_multilingual=True)
    raw_layout = _layout(
        [_el("e001", "1 ДОГОВОР")]
    )
    primary_layout = _layout(
        [_el("e001", "1 ДОГОВОР")]
    )

    mode = _determine_primary_source_build_mode(
        decision=decision,
        raw_layout=raw_layout,
        primary_layout=primary_layout,
    )

    assert mode == "single_language_pdf"


    