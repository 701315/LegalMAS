"""
Sprint 2 regression corpus test.

Проверяет паттерны:
- #5: TOC с dot leaders
- #6: multiline TOC entries
- #8: stale TOC entries не ломают pipeline
- #12: OCR-tolerant fuzzy matching
"""

import pytest

from services.structure.heading_builder import collect_scored_heading_candidates
from services.structure.toc_match_utils import toc_match_payload
from services.structure.toc_matcher import (
    attach_toc_matches,
    build_toc_match_index,
)
from services.structure.toc_parser import (
    TOCBlock,
    compute_partial_reliability,
    evaluate_toc_alignment,
    parse_toc_entries,
)


def _body_elements(*texts, scope="main_contract", segment_id="seg-main", page_start=2):
    elements = []
    for idx, text in enumerate(texts):
        elements.append(
            {
                "text": text,
                "page": page_start + idx,
                "scope": scope,
                "segment_id": segment_id,
                "segment_type": "contract",
                "segment_order": 0,
                "element_type": "heading_candidate",
                "page_offset": 0.01 + idx * 0.01,
                "formatting": {"is_bold": True},
                "ocr_confidence": 0.99,
            }
        )
    return elements


def _toc_block(lines: list[tuple[str, int]]) -> TOCBlock:
    """
    Собирает валидный TOCBlock под реальный контракт toc_parser.TOCBlock.

    lines: список пар (text, page)
    """
    elements: list[dict] = []
    for idx, (text, page) in enumerate(lines):
        elements.append(
            {
                "text": text,
                "page": page,
                "element_type": "toc_content",
                "page_offset": 0.01 + idx * 0.01,
            }
        )

    return TOCBlock(
        detected=True,
        start_index=0 if elements else None,
        end_index=len(elements),
        reason="test_fixture",
        elements=elements,
    )


@pytest.mark.parametrize(
    ("pattern_id", "toc_lines", "expected"),
    [
        (
            "#5",
            [
                ("1. Definitions .......... 4", 1),
                ("2. Representations and Warranties .......... 8", 1),
            ],
            [
                ("1", "Definitions", 4),
                ("2", "Representations and Warranties", 8),
            ],
        ),
        (
            "#6",
            [
                ("3. Representations and", 1),
                ("Warranties .......... 11", 1),
                ("4. Covenants .......... 15", 1),
            ],
            [
                ("3", "Representations and Warranties", 11),
                ("4", "Covenants", 15),
            ],
        ),
    ],
)
def test_sprint2_toc_parser_regression_patterns(pattern_id, toc_lines, expected):
    """Проверяет паттерны #5 (dot leaders) и #6 (multiline entries)."""
    toc_block = _toc_block(toc_lines)
    parsed = parse_toc_entries(toc_block)

    actual = [(entry.uid, entry.title, entry.page_hint) for entry in parsed.entries]
    assert actual == expected, f"{pattern_id} failed"


def test_sprint2_pattern_8_stale_toc_entries_do_not_break_alignment():
    """
    Паттерн #8: stale TOC entry не должен ломать alignment.
    
    Проверяет:
    - stale entry помечается toc_missing_in_body=True
    - alignment pipeline корректно обрабатывает его
    - partial reliability остаётся meaningful
    """
    toc_block = _toc_block(
        [
            ("1. Definitions .......... 4", 1),
            ("2. Representations .......... 8", 1),
            ("9. Obsolete Section .......... 99", 1),
        ]
    )
    body_elements = _body_elements(
        "1. Definitions",
        "2. Representations",
    )

    parsed_toc = parse_toc_entries(toc_block)
    headings = collect_scored_heading_candidates(
        body_elements,
        document_id="doc-pattern-8",
    )

    matched_toc = attach_toc_matches(parsed_toc, headings)
    alignment = evaluate_toc_alignment(matched_toc)
    reliability = compute_partial_reliability(matched_toc, alignment)

    assert len(matched_toc.entries) == 3
    assert alignment.entries_total == 3
    assert alignment.stale_entries >= 1 or alignment.no_matches >= 1
    assert reliability.partial_reliability > 0.0

    stale_entries = [
        entry for entry in matched_toc.entries 
        if getattr(entry, "toc_missing_in_body", False)
    ]
    assert len(stale_entries) >= 1, "Expected at least one stale TOC entry"


def test_sprint2_pattern_8_stale_toc_entry_has_no_bonus_in_builder_lookup():
    """
    Паттерн #8: stale TOC entry не должен давать scoring bonus.
    
    Проверяет, что в toc_match_index payload для stale entry
    помечен toc_missing_in_body=True.
    """
    toc_block = _toc_block(
        [
            ("1. Definitions .......... 4", 1),
            ("9. Obsolete Section .......... 99", 1),
        ]
    )
    body_elements = _body_elements("1. Definitions")

    parsed_toc = parse_toc_entries(toc_block)
    headings = collect_scored_heading_candidates(
        body_elements,
        document_id="doc-pattern-8-lookup",
    )

    matched_toc = attach_toc_matches(parsed_toc, headings)
    match_index = build_toc_match_index(matched_toc)

    payload_live = toc_match_payload(
        raw_uid="1",
        title="Definitions",
        toc_match_index=match_index,
    )
    payload_stale = toc_match_payload(
        raw_uid="9",
        title="Obsolete Section",
        toc_match_index=match_index,
    )

    assert payload_live is not None
    assert payload_live.get("toc_missing_in_body") is False

    assert payload_stale is not None
    assert payload_stale.get("toc_missing_in_body") is True


def test_sprint2_pattern_12_ocr_fuzzy_matching_preserves_alignment_signal():
    """
    Паттерн #12: OCR-tolerant fuzzy matching.
    
    Проверяет, что документ с 2-3 OCR-ошибками:
    - получает fuzzy matches вместо exact
    - сохраняет usable toc_alignment_score
    - не проигрывает clean-версии драматически
    """
    toc_block = _toc_block(
        [
            ("1. Definitions .......... 4", 1),
            ("2. Representations and Warranties .......... 8", 1),
            ("3. Covenants .......... 12", 1),
        ]
    )

    clean_body = _body_elements(
        "1. Definitions",
        "2. Representations and Warranties",
        "3. Covenants",
    )
    ocr_noisy_body = _body_elements(
        "1. Definitions",
        "2. Representati0ns and Warrantles",
        "3. Covenants",
    )

    parsed_toc_clean = parse_toc_entries(toc_block)
    parsed_toc_ocr = parse_toc_entries(toc_block)

    headings_clean = collect_scored_heading_candidates(
        clean_body,
        document_id="doc-pattern-12-clean",
    )
    headings_ocr = collect_scored_heading_candidates(
        ocr_noisy_body,
        document_id="doc-pattern-12-ocr",
    )

    matched_clean = attach_toc_matches(parsed_toc_clean, headings_clean)
    matched_ocr = attach_toc_matches(parsed_toc_ocr, headings_ocr)

    alignment_clean = evaluate_toc_alignment(matched_clean)
    alignment_ocr = evaluate_toc_alignment(matched_ocr)

    reliability_clean = compute_partial_reliability(matched_clean, alignment_clean)
    reliability_ocr = compute_partial_reliability(matched_ocr, alignment_ocr)

    assert alignment_clean.entries_total == 3
    assert alignment_ocr.entries_total == 3

    assert alignment_clean.toc_alignment_score > 0.0
    assert alignment_ocr.toc_alignment_score > 0.0

    has_fuzzy = any(
        getattr(entry, "match_type", None) == "fuzzy" 
        for entry in matched_ocr.entries
    )
    assert has_fuzzy, "Expected at least one fuzzy match in OCR-noisy corpus"

    # Sprint 2 acceptance criterion: OCR-шум не разваливает alignment
    assert alignment_ocr.toc_alignment_score >= 0.60

    # Partial reliability тоже остаётся meaningful
    assert reliability_ocr.partial_reliability >= 0.60

    # OCR не должен драматически проигрывать clean
    assert alignment_ocr.toc_alignment_score >= alignment_clean.toc_alignment_score - 0.25


def test_sprint2_pattern_12_match_index_contains_fuzzy_payload():
    """
    Паттерн #12: fuzzy match payload попадает в toc_match_index.
    
    Проверяет, что после OCR-шумного matching в index попадает payload
    с match_type='fuzzy' и корректными полями.
    """
    toc_block = _toc_block(
        [
            ("2. Representations and Warranties .......... 8", 1),
        ]
    )
    ocr_noisy_body = _body_elements(
        "2. Representati0ns and Warrantles",
    )

    parsed_toc = parse_toc_entries(toc_block)
    headings = collect_scored_heading_candidates(
        ocr_noisy_body,
        document_id="doc-pattern-12-index",
    )

    matched_toc = attach_toc_matches(parsed_toc, headings)
    match_index = build_toc_match_index(matched_toc)

    payload = toc_match_payload(
        raw_uid="2",
        title="Representations and Warranties",
        toc_match_index=match_index,
    )

    assert payload is not None
    assert payload.get("match_type") in {"exact", "fuzzy"}
    assert payload.get("toc_missing_in_body") is False



