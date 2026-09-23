"""Unit tests for B6.2/R10 — per-field anchor chunk-map resolution."""

from __future__ import annotations

from core.anchors.models import CheckAnchorMethod
from engine.checks.extraction import ExtractionExecutor


class TestBuildExtractionTextChunkMap:
    def test_evidence_branch_without_chunk_map_returns_none(self):
        # Legacy: detection без ключа _evidence_chunk_map → None.
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        text, cmap = ex._build_extraction_text(
            detection={"evidence": "short evidence", "raw": {}},
            contexts=[{"text": "some context"}],
        )
        assert text == "short evidence"
        assert cmap is None

    def test_evidence_branch_with_chunk_map_passes_it_through(self):
        # B6.2/R10 вар. B: executor кладёт chunk_map в _evidence_chunk_map —
        # extraction прокидывает его для per-field provenance.
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        cmap = [
            (0, 10, {"metadata": {"effective_uid": "x:1", "page": 1}}),
            (15, 25, {"metadata": {"effective_uid": "x:2", "page": 5}}),
        ]
        text, cm = ex._build_extraction_text(
            detection={
                "evidence": "short evidence",
                "raw": {},
                "_evidence_chunk_map": cmap,
            },
            contexts=[{"text": "irrelevant"}],
        )
        assert text == "short evidence"
        assert cm == cmap

    def test_evidence_branch_with_malformed_chunk_map_returns_none(self):
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
        assert [text[s:e] for s, e, _ in cmap] == ["AAA", "BBB", "CCC"]
        assert [c["metadata"]["effective_uid"] for _, _, c in cmap] == ["x:1", "x:2", "x:3"]


class TestResolveFieldAnchorChunkMap:
    def test_chunk_map_overrides_fallback_location(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        base = "Клауза 1\n\nКлауза 2: Стороны обязуются соблюдать конфиденциальность.\n\nКлауза 3"
        cm = [
            (0, 8, {"metadata": {"effective_uid": "main:1", "page": 1}}),
            (10, 68, {"metadata": {"effective_uid": "main:2", "page": 5}}),
            (70, 78, {"metadata": {"effective_uid": "main:3", "page": 9}}),
        ]
        anchor = ex._resolve_field_anchor(
            quote="Стороны обязуются соблюдать конфиденциальность",
            source_text=base,
            fallback_clause_uid="main:fallback",
            fallback_page=99,
            chunk_map=cm,
        )
        assert anchor is not None
        assert anchor.anchor_method in (
            CheckAnchorMethod.EXACT_SPAN,
            CheckAnchorMethod.FUZZY_SPAN,
        )
        assert anchor.clause_uid == "main:2"
        assert anchor.page == 5

    def test_fallback_when_chunk_map_none(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        base = "Стороны обязуются соблюдать конфиденциальность."
        anchor = ex._resolve_field_anchor(
            quote="Стороны обязуются соблюдать конфиденциальность",
            source_text=base,
            fallback_clause_uid="main:fallback",
            fallback_page=99,
            chunk_map=None,
        )
        assert anchor is not None
        assert anchor.clause_uid == "main:fallback"
        assert anchor.page == 99

    def test_fallback_when_quote_not_found(self):
        ex = ExtractionExecutor.__new__(ExtractionExecutor)
        base = "Совершенно другой текст документа."
        cm = [
            (0, 32, {"metadata": {"effective_uid": "main:1", "page": 1}}),
        ]
        anchor = ex._resolve_field_anchor(
            quote="обязуются соблюдать конфиденциальность",
            source_text=base,
            fallback_clause_uid="main:fallback",
            fallback_page=99,
            chunk_map=cm,
        )
        assert anchor is not None
        assert anchor.anchor_method in (
            CheckAnchorMethod.CLAUSE_ONLY,
            CheckAnchorMethod.PAGE_ONLY,
        )
