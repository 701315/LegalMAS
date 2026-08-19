"""
Sprint 3 tests: chunking.py canonical metadata.

Проверяем:
- build_section_chunks_from_clauses использует raw_uid/effective_uid в sort key
- section metadata содержит canonical поля
- группировка по path_titles[0] работает корректно
- language_filter metadata переносится из clause chunks в section chunks
- doc_id соответствует актуальному production-контракту (валидный UUID)
"""

from __future__ import annotations

import uuid

import pytest

from engine.content.chunking import build_section_chunks_from_clauses


# В production build_section_chunk_id() требует валидный UUID.
# Используем фиксированный UUID, а не "test-doc-123".
TEST_DOC_ID = "11111111-1111-1111-1111-111111111111"


class TestSectionChunksCanonicalMetadata:
    """Проверка canonical metadata в section chunks."""

    def test_section_metadata_has_canonical_fields(self):
        """Section chunk metadata содержит canonical поля."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:main_contract::1",
                "text": "First clause text.",
                "metadata": {
                    "doc_id": doc_id,
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "path_titles": ["GENERAL PROVISIONS"],
                    "start_page": 1,
                },
            }
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 1

        meta = sections[0]["metadata"]
        assert meta["chunk_kind"] == "section"
        assert meta["node_kind"] == "section"
        assert meta["raw_uid"] is None
        assert meta["scope"] == "main_contract"

        # Canonical format: "scope:section::slug"
        # scope → raw_uid разделяется одним ':', slug нормализуется с дефисом
        assert meta["effective_uid"] == "main_contract:section::general-provisions"

    def test_section_grouping_by_first_path_title(self):
        """Группировка происходит по path_titles[0]."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:1",
                "text": "First clause.",
                "metadata": {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "path_titles": ["GENERAL PROVISIONS", "1. Definitions"],
                    "start_page": 1,
                },
            },
            {
                "id": f"{doc_id}:2",
                "text": "Second clause.",
                "metadata": {
                    "effective_uid": "main_contract::2",
                    "raw_uid": "2",
                    "scope": "main_contract",
                    "path_titles": ["GENERAL PROVISIONS", "2. Interpretations"],
                    "start_page": 2,
                },
            },
            {
                "id": f"{doc_id}:3",
                "text": "Third clause.",
                "metadata": {
                    "effective_uid": "main_contract::3",
                    "raw_uid": "3",
                    "scope": "main_contract",
                    "path_titles": ["PAYMENT TERMS", "3.1 Price"],
                    "start_page": 3,
                },
            },
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        # Должно быть 2 section: GENERAL PROVISIONS + PAYMENT TERMS
        assert len(sections) == 2

        titles = {s["metadata"]["title"] for s in sections}
        assert titles == {"GENERAL PROVISIONS", "PAYMENT TERMS"}

    def test_section_sort_uses_raw_uid_and_effective_uid(self):
        """Sort key использует raw_uid и effective_uid, не clause_uid."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:2",
                "text": "Second.",
                "metadata": {
                    "raw_uid": "2",
                    "effective_uid": "main_contract::2",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 2,
                },
            },
            {
                "id": f"{doc_id}:1",
                "text": "First.",
                "metadata": {
                    "raw_uid": "1",
                    "effective_uid": "main_contract::1",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 1,
                },
            },
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 1

        # Текст должен быть в правильном порядке: First, потом Second
        text = sections[0]["text"]
        assert "First." in text
        assert "Second." in text
        assert text.index("First.") < text.index("Second.")

    def test_clauses_without_path_titles_skipped(self):
        """Clauses без path_titles пропускаются."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:1",
                "text": "Valid clause.",
                "metadata": {
                    "raw_uid": "1",
                    "effective_uid": "main_contract::1",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 1,
                },
            },
            {
                "id": f"{doc_id}:2",
                "text": "Invalid clause.",
                "metadata": {
                    "raw_uid": "2",
                    "effective_uid": "main_contract::2",
                    "scope": "main_contract",
                    "path_titles": [],
                    "start_page": 2,
                },
            },
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 1
        assert "Valid clause." in sections[0]["text"]
        assert "Invalid clause." not in sections[0]["text"]

    def test_empty_section_text_skipped(self):
        """Section с пустым текстом после сбора пропускается."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:1",
                "text": "",
                "metadata": {
                    "raw_uid": "1",
                    "effective_uid": "main_contract::1",
                    "scope": "main_contract",
                    "path_titles": ["EMPTY SECTION"],
                    "start_page": 1,
                },
            }
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 0

    def test_section_merges_language_filter_from_clauses(self):
        """Section наследует language_filter из clause metadata."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:1",
                "text": "Clause one.",
                "metadata": {
                    "raw_uid": "1",
                    "effective_uid": "main_contract::1",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 1,
                    "language_filter": {
                        "target_language": "ru",
                        "degraded": False,
                    },
                },
            }
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 1
        meta = sections[0]["metadata"]

        assert "language_filter" in meta
        assert meta["language_filter"]["target_language"] == "ru"
        assert meta["language_filter"]["degraded"] is False

    def test_section_averages_position_ratio(self):
        """Section усредняет position_ratio из clauses."""
        doc_id = TEST_DOC_ID

        clause_chunks = [
            {
                "id": f"{doc_id}:1",
                "text": "First.",
                "metadata": {
                    "raw_uid": "1",
                    "effective_uid": "main_contract::1",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 1,
                    "position_ratio": 0.2,
                },
            },
            {
                "id": f"{doc_id}:2",
                "text": "Second.",
                "metadata": {
                    "raw_uid": "2",
                    "effective_uid": "main_contract::2",
                    "scope": "main_contract",
                    "path_titles": ["SECTION"],
                    "start_page": 2,
                    "position_ratio": 0.4,
                },
            },
        ]

        sections = build_section_chunks_from_clauses(doc_id, clause_chunks)

        assert len(sections) == 1
        meta = sections[0]["metadata"]

        # (0.2 + 0.4) / 2 = 0.3
        assert meta["position_ratio"] == pytest.approx(0.3)


