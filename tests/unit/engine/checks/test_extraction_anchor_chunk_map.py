"""Unit tests for B6.2/R10 — per-field anchor provenance.

Покрывает:
- _extract_numeric_core: парсинг clause_ref;
- _build_extraction_text: возврат (text, 4-tuple chunk_map);
- _resolve_field_anchor: приоритет источников provenance —
  field_location > chunk_map > base_location.
"""

from __future__ import annotations

import pytest

from core.anchors.models import CheckAnchorMethod
from engine.checks.extraction import ExtractionExecutor


class _FakeRC:
    """Минимальный RetrievedChunk-like объект для тестов R10."""

    def __init__(self, clause_uid: str = "", page: int = 1, start_page: int | None = None):
        self.clause_uid = clause_uid
        self.page = page
        self.start_page = start_page


# ────────────────────────────────────────────────────────────────────────────
# _extract_numeric_core
# ────────────────────────────────────────────────────────────────────────────


class TestExtractNumericCore:
    def test_russian_dotted(self):
        assert ExtractionExecutor._extract_numeric_core("п. 8.1.5") == ["8.1.5"]

    def test_english_dotted(self):
        assert ExtractionExecutor._extract_numeric_core("Section 12.1") == ["12.1"]

    def test_compound_references(self):
        assert ExtractionExecutor._extract_numeric_core("п. 7.1.1, 7.1.2") == ["7.1.1", "7.1.2"]

    def test_simple_number(self):
        assert ExtractionExecutor._extract_numeric_core("Статья 5") == ["5"]

    def test_empty_input(self):
        assert ExtractionExecutor._extract_numeric_core("") == []

    def test_no_numbers(self):
        assert ExtractionExecutor._extract_numeric_core("без ссылок") == []


# ────────────────────────────────────────────────────────────────────────────
# _build_extraction_text
# ────────────────────────────────────────────────────────────────────────────


class TestBuildExtractionTextChunkMap:
    def test_evidence_branch_without_chunk_map(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        text, cmap = ex._build_extraction_text(
            detection={"evidence": "short evidence", "raw": {}},
            contexts=[{"text": "some context"}],
        )
        assert text == "short evidence"
        assert cmap is None

    def test_evidence_branch_with_chunk_map_passes_through(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        rc = _FakeRC("x:1", 1)
        cmap_in = [(0, 10, {"metadata": {"effective_uid": "x:1", "page": 1}}, rc)]
        text, cm = ex._build_extraction_text(
            detection={
                "evidence": "short evidence",
                "raw": {},
                "_evidence_chunk_map": cmap_in,
            },
            contexts=[{"text": "irrelevant"}],
        )
        assert text == "short evidence"
        assert cm == cmap_in

    def test_evidence_branch_with_malformed_chunk_map(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        text, cmap = ex._build_extraction_text(
            detection={
                "evidence": "short evidence",
                "raw": {},
                "_evidence_chunk_map": "not-a-list",
            },
            contexts=[{"text": "irrelevant"}],
        )
        assert text == "short evidence"
        assert cmap is None

    def test_contexts_branch_returns_offsets(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        text, cmap = ex._build_extraction_text(
            detection={"evidence": "", "raw": {}},
            contexts=[
                {"text": "AAA", "metadata": {"effective_uid": "x:1", "page": 1}},
                {"text": "BBB", "metadata": {"effective_uid": "x:2", "page": 2}},
                {"text": "CCC", "metadata": {"effective_uid": "x:3", "page": 3}},
            ],
        )
        assert text == "AAA\n\nBBB\n\nCCC"
        assert cmap is not None
        assert len(cmap) == 3
        # 4-tuple контракт: (start, end, ctx, rc)
        assert [text[s:e] for s, e, _, _ in cmap] == ["AAA", "BBB", "CCC"]
        assert [c["metadata"]["effective_uid"] for _, _, c, _ in cmap] == ["x:1", "x:2", "x:3"]
        # rc=None в contexts-ветви (retrieved_chunks недоступны)
        assert all(rc is None for _, _, _, rc in cmap)


# ────────────────────────────────────────────────────────────────────────────
# _resolve_field_anchor — приоритет источников provenance
# ────────────────────────────────────────────────────────────────────────────


class TestResolveFieldAnchorChunkMap:
    def _base_text_with_three_chunks(self) -> str:
        # 3 "чанка" через "AAA...BBB...CCC" с явными границами
        return (
            "AAA " * 200
            + "BBB Стороны применяют право РФ. " * 10
            + "CCC " * 200
        )

    def _cmap_three(self, base: str) -> list:
        return [
            (0, 800, {"metadata": {"effective_uid": "main_contract:1", "page": 1, "raw_uid": "1"}}, _FakeRC("main_contract:1", 1)),
            (800, 1800, {"metadata": {"effective_uid": "main_contract:8.1.5", "page": 7, "raw_uid": "8.1.5"}}, _FakeRC("main_contract:8.1.5", 7)),
            (1800, len(base), {"metadata": {"effective_uid": "main_contract:9", "page": 9, "raw_uid": "9"}}, _FakeRC("main_contract:9", 9)),
        ]

    # ── Приоритет 2: chunk_map (owner-chunk по span) ────────────────────────
    def test_chunk_map_overrides_fallback_location(self):
        base = self._base_text_with_three_chunks()
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:fallback",
            fallback_page=99,
            chunk_map=self._cmap_three(base),
        )
        assert anchor is not None
        assert anchor.anchor_method in (
            CheckAnchorMethod.EXACT_SPAN,
            CheckAnchorMethod.FUZZY_SPAN,
        )
        assert anchor.clause_uid == "main_contract:8.1.5"
        assert anchor.page == 7

    def test_chunk_map_with_rc_none_is_safe(self):
        # contexts-ветвь отдаёт rc=None — metadata несёт всё нужное
        base = self._base_text_with_three_chunks()
        cmap = [
            (0, 800, {"metadata": {"effective_uid": "main_contract:1", "page": 1, "raw_uid": "1"}}, None),
            (800, 1800, {"metadata": {"effective_uid": "main_contract:8.1.5", "page": 7, "raw_uid": "8.1.5"}}, None),
            (1800, len(base), {"metadata": {"effective_uid": "main_contract:9", "page": 9, "raw_uid": "9"}}, None),
        ]
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:fallback",
            fallback_page=99,
            chunk_map=cmap,
        )
        assert anchor is not None
        assert anchor.clause_uid == "main_contract:8.1.5"
        assert anchor.page == 7

    def test_fallback_when_chunk_map_none(self):
        base = "Стороны обязуются соблюдать конфиденциальность."
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны обязуются соблюдать конфиденциальность",
            source_text=base,
            fallback_clause_uid="main_contract:fallback",
            fallback_page=99,
            chunk_map=None,
        )
        assert anchor is not None
        assert anchor.clause_uid == "main_contract:fallback"
        assert anchor.page == 99

    def test_fallback_when_quote_not_found(self):
        base = "Совершенно другой текст документа."
        cmap = [
            (0, 32, {"metadata": {"effective_uid": "main:1", "page": 1, "raw_uid": "1"}}, _FakeRC("main:1", 1)),
        ]
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="обязуются соблюдать конфиденциальность",
            source_text=base,
            fallback_clause_uid="main_contract:fallback",
            fallback_page=99,
            chunk_map=cmap,
        )
        assert anchor is not None
        assert anchor.anchor_method in (
            CheckAnchorMethod.CLAUSE_ONLY,
            CheckAnchorMethod.PAGE_ONLY,
        )

    # ── Приоритет 1: field_location ────────────────────────────────────────
    def test_field_page_overrides_chunk_map(self):
        base = self._base_text_with_three_chunks()
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:8",
            fallback_page=6,
            chunk_map=self._cmap_three(base),
            field_page=11,
            field_clause_ref=None,
        )
        # field_page побеждает chunk_map (в chunk_map было 7, теперь 11)
        assert anchor.page == 11

    def test_field_clause_ref_matched_by_raw_uid(self):
        base = self._base_text_with_three_chunks()
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:8",
            fallback_page=6,
            chunk_map=self._cmap_three(base),
            field_page=11,
            field_clause_ref="п. 8.1.5",
        )
        # clause_uid из chunk, где raw_uid == "8.1.5"
        assert anchor.clause_uid == "main_contract:8.1.5"
        # field_page приоритетнее даже если chunk нашёлся
        assert anchor.page == 11

    def test_field_location_when_no_chunk_map(self):
        # Chunk_map отсутствует — только field_location
        base = "Стороны применяют право РФ."
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:8",
            fallback_page=6,
            chunk_map=None,
            field_page=11,
            field_clause_ref=None,
        )
        assert anchor.page == 11
        assert anchor.clause_uid == "main_contract:8"  # fallback

    def test_field_location_missing_falls_back_to_chunk_map(self):
        # Ни field_page, ни field_clause_ref — работает chunk_map
        base = self._base_text_with_three_chunks()
        anchor = ExtractionExecutor._resolve_field_anchor(
            quote="Стороны применяют право РФ.",
            source_text=base,
            fallback_clause_uid="main_contract:8",
            fallback_page=6,
            chunk_map=self._cmap_three(base),
            field_page=None,
            field_clause_ref=None,
        )
        assert anchor.clause_uid == "main_contract:8.1.5"
        assert anchor.page == 7

# ────────────────────────────────────────────────────────────────────────────
# Интеграционный тест: chunk_map от executor ↔ _resolve_field_anchor
# Закрывает дыру: unit-тесты extraction использовали фейковые 4-tuple,
# реальный executor отдавал 3-tuple → ValueError в проде.
# ────────────────────────────────────────────────────────────────────────────


class TestExecutorIntegration:
    def test_build_limited_context_returns_4tuple_chunk_map_no_limit(self):
        """Безлимитная ветвь _build_limited_context отдаёт 4-tuple chunk_map."""
        from engine.checks.executor import CheckExecutor

        class _RC:
            element_id = "x:1"
            text = "test"
            page = 1
            clause_uid = "main_contract:8"
            combined_score = 1.0
            path_titles = []
            start_page = None
            end_page = None
            bbox = []
            segment_id = None
            segment_type = None
            segment_title = None
            segment_order = None
            is_primary_segment = None

        ex = CheckExecutor.__new__(CheckExecutor)
        ctx1 = {"text": "AAA BBB", "metadata": {"effective_uid": "main_contract:8", "page": 6}}
        ctx2 = {"text": "CCC DDD", "metadata": {"effective_uid": "main_contract:9", "page": 7}}
        rc1, rc2 = _RC(), _RC()

        joined, chunks, ctxs, tokens, trunc, cmap = ex._build_limited_context(
            contexts=[ctx1, ctx2],
            retrieved_chunks=[rc1, rc2],
            important_terms=[],
            max_tokens=0,  # безлимитная ветвь
        )
        assert cmap is not None
        assert len(cmap) == 2
        for entry in cmap:
            assert len(entry) == 4, f"expected 4-tuple, got {len(entry)}"
            s, e, c, rc = entry  # распаковка как в _resolve_field_anchor
            assert isinstance(s, int)
            assert isinstance(e, int)
            assert isinstance(c, dict)
        assert cmap[0][3] is rc1
        assert cmap[1][3] is rc2

    def test_build_limited_context_returns_4tuple_chunk_map_with_limit(self):
        """Ветвь без truncation отдаёт 4-tuple chunk_map."""
        from engine.checks.executor import CheckExecutor

        class _RC:
            element_id = "x:1"
            text = "test"
            page = 1
            clause_uid = "main_contract:8"
            combined_score = 1.0
            path_titles = []
            start_page = None
            end_page = None
            bbox = []
            segment_id = None
            segment_type = None
            segment_title = None
            segment_order = None
            is_primary_segment = None

        ex = CheckExecutor.__new__(CheckExecutor)
        ctx = {"text": "AAA BBB", "metadata": {"effective_uid": "main_contract:8", "page": 6}}
        rc = _RC()

        joined, chunks, ctxs, tokens, trunc, cmap = ex._build_limited_context(
            contexts=[ctx],
            retrieved_chunks=[rc],
            important_terms=[],
            max_tokens=10000,  # достаточно для одного чанка → без truncation
        )
        assert cmap is not None
        assert len(cmap) == 1
        assert len(cmap[0]) == 4, f"expected 4-tuple, got {len(cmap[0])}"
        s, e, c, r = cmap[0]
        assert r is rc
