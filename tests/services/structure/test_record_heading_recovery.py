"""
Tests for deterministic numbered-record heading recovery.
"""

from __future__ import annotations

from services.structure._pipeline._record_heading_recovery import (
    attempt_record_heading_recovery,
)


def _el(
    text: str,
    *,
    page: int,
    element_type: str,
) -> dict:
    return {
        "text": text,
        "page": page,
        "element_type": element_type,
        "scope": "appendix_1",
        "segment_id": "seg-1",
        "segment_type": "appendix",
        "segment_order": 1,
        "metadata": {},
    }


def test_applies_to_numbered_record_topology() -> None:
    elements = [
        _el("17 Наименование объекта: земельный участок", page=1, element_type="list_item"),
        _el("17.1 Кадастровый номер: 78:36:0005503:4", page=1, element_type="body_text"),
        _el("17.2 Площадь объекта: 21 041 кв.м.", page=1, element_type="body_text"),
        _el("18 Наименование объекта: нежилое здание", page=2, element_type="list_item"),
        _el("18.1 Кадастровый номер: 78:36:0005503:5", page=2, element_type="body_text"),
        _el("18.2 Площадь объекта: 1 500 кв.м.", page=2, element_type="body_text"),
    ]

    result = attempt_record_heading_recovery(
        document_id="doc-1",
        elements=elements,
    )

    assert result.applied is True
    assert result.diagnostics["root_count"] == 2
    assert result.diagnostics["child_count"] >= 4

    for idx in range(len(elements)):
        assert result.elements[idx]["element_type"] == "heading_candidate"
        meta = result.elements[idx]["metadata"]
        assert meta["record_heading_recovery"] is True
        assert meta["record_heading_recovery_mode"] == "numbered_record"


def test_does_not_apply_to_single_root_family_only() -> None:
    elements = [
        _el("17 Наименование объекта: земельный участок", page=1, element_type="list_item"),
        _el("17.1 Кадастровый номер: 78:36:0005503:4", page=1, element_type="body_text"),
        _el("17.2 Площадь объекта: 21 041 кв.м.", page=1, element_type="body_text"),
    ]

    result = attempt_record_heading_recovery(
        document_id="doc-2",
        elements=elements,
    )

    assert result.applied is False
    assert result.diagnostics["reason"] in {
        "insufficient_numeric_record_lines",
        "insufficient_roots_with_children",
    }


def test_does_not_apply_to_long_numbered_prose() -> None:
    elements = [
        _el(
            "1 Настоящим стороны подтверждают, что в рамках исполнения настоящего договора все обязательства подлежат толкованию исключительно в соответствии с применимым правом и сложившейся судебной практикой без каких-либо дополнительных ограничений и оговорок.",
            page=1,
            element_type="body_text",
        ),
        _el(
            "1.1 Настоящим стороны дополнительно подтверждают, что любые разногласия подлежат урегулированию посредством переговоров в разумный срок до обращения в суд.",
            page=1,
            element_type="body_text",
        ),
        _el(
            "2 Настоящим стороны также подтверждают, что обмен документами может осуществляться посредством электронных средств связи при соблюдении внутренних процедур.",
            page=2,
            element_type="body_text",
        ),
        _el(
            "2.1 Каждая сторона обязуется обеспечить сохранность соответствующих подтверждений отправки и получения сообщений в течение срока действия договора.",
            page=2,
            element_type="body_text",
        ),
    ]

    result = attempt_record_heading_recovery(
        document_id="doc-3",
        elements=elements,
    )

    assert result.applied is False


def test_preserves_non_record_lines() -> None:
    elements = [
        _el("17 Наименование объекта: земельный участок", page=1, element_type="list_item"),
        _el("17.1 Кадастровый номер: 78:36:0005503:4", page=1, element_type="body_text"),
        _el("Произвольный абзац описания объекта без номера.", page=1, element_type="body_text"),
        _el("18 Наименование объекта: нежилое здание", page=2, element_type="list_item"),
        _el("18.1 Кадастровый номер: 78:36:0005503:5", page=2, element_type="body_text"),
    ]

    result = attempt_record_heading_recovery(
        document_id="doc-4",
        elements=elements,
    )

    assert result.applied is True
    assert result.elements[2]["element_type"] == "body_text"
    assert result.elements[2]["metadata"] == {}


    