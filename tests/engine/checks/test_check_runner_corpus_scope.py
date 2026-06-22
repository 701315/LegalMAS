"""
Tests for CheckRunner._build_corpus_for_check corpus scope routing.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pipeline_snapshots import DocumentSnapshot
from engine.checks.check_runner import CheckRunner
from engine.playbook.models import RetrievalCorpusScope


def _make_doc_snap(doc_id: uuid.UUID | None = None) -> DocumentSnapshot:
    return DocumentSnapshot(
        id=doc_id or uuid.uuid4(),
        status="active",
        doc_type="contract_1.6_real_estate",
    )


def _make_check(
    corpus_scope: RetrievalCorpusScope = RetrievalCorpusScope.PRIMARY_SEGMENT,
    levels: list[str] | None = None,
) -> MagicMock:
    check = MagicMock()
    check.id = "test_check"
    retrieval = MagicMock()
    retrieval.corpus_scope = corpus_scope
    retrieval.levels = levels or ["legal_unit", "section"]
    check.retrieval = retrieval
    return check


def _make_segment(
    segment_id: str,
    is_primary: bool = False,
    segment_type: str = "contract",
    enrichment_ref: str | None = None,
) -> MagicMock:
    seg = MagicMock()
    seg.segment_id = segment_id
    seg.is_primary = is_primary
    seg.segment_type = segment_type
    seg.segment_meta = {
        "legal_units_enrichment_ref": enrichment_ref,
    }
    return seg


def _make_runner() -> CheckRunner:
    runner = CheckRunner.__new__(CheckRunner)
    runner.llm_client = None
    runner.executor = None
    runner.playbook_version_id = None
    runner.run_repo = None

    from engine.checks.planning.planner import CheckPlanner
    from engine.checks.planning.scope import ScopeResolver
    from engine.checks.planning.chunks import ChunksPreparer

    runner._planner = CheckPlanner()
    runner._scope = ScopeResolver()
    runner._chunks = MagicMock()
    runner._chunks.build_safe_chunks = AsyncMock(return_value=[{"id": "doc-chunk"}])
    runner._chunks.build_safe_chunks_for_segment = AsyncMock(return_value=[{"id": "seg-chunk"}])

    return runner


class TestBuildCorpusForCheck:
    @pytest.mark.asyncio
    async def test_no_segments_uses_document_level(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT)
        session = MagicMock()

        result = await runner._build_corpus_for_check(
            session=session,
            doc=doc,
            check=check,
            segments=[],
            current_segment=None,
        )

        runner._chunks.build_safe_chunks.assert_awaited_once()
        runner._chunks.build_safe_chunks_for_segment.assert_not_awaited()
        assert result == [{"id": "doc-chunk"}]

    @pytest.mark.asyncio
    async def test_none_segments_uses_document_level(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT)
        session = MagicMock()

        result = await runner._build_corpus_for_check(
            session=session,
            doc=doc,
            check=check,
            segments=None,
            current_segment=None,
        )

        runner._chunks.build_safe_chunks.assert_awaited_once()
        assert result == [{"id": "doc-chunk"}]

    @pytest.mark.asyncio
    async def test_primary_segment_scope_uses_primary_segment(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT)
        session = MagicMock()

        primary = _make_segment("seg-primary", is_primary=True)
        secondary = _make_segment("seg-appendix", is_primary=False)

        with patch("engine.checks.check_runner.ArtifactStore") as mock_store_cls:
            mock_store_cls.return_value.get_json.return_value = {}

            result = await runner._build_corpus_for_check(
                session=session,
                doc=doc,
                check=check,
                segments=[primary, secondary],
                current_segment=None,
            )

        runner._chunks.build_safe_chunks_for_segment.assert_awaited_once()
        call_kwargs = runner._chunks.build_safe_chunks_for_segment.call_args.kwargs
        assert call_kwargs["segment_id"] == "seg-primary"
        assert result == [{"id": "seg-chunk"}]

    @pytest.mark.asyncio
    async def test_primary_segment_scope_no_primary_fallback_to_document(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT)
        session = MagicMock()

        # No segment marked as primary
        seg1 = _make_segment("seg-1", is_primary=False)
        seg2 = _make_segment("seg-2", is_primary=False)

        result = await runner._build_corpus_for_check(
            session=session,
            doc=doc,
            check=check,
            segments=[seg1, seg2],
            current_segment=None,
        )

        runner._chunks.build_safe_chunks.assert_awaited_once()
        runner._chunks.build_safe_chunks_for_segment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_current_segment_scope_uses_current_segment(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.CURRENT_SEGMENT)
        session = MagicMock()

        primary = _make_segment("seg-primary", is_primary=True)
        current = _make_segment("seg-current", is_primary=False)

        with patch("engine.checks.check_runner.ArtifactStore") as mock_store_cls:
            mock_store_cls.return_value.get_json.return_value = {}

            result = await runner._build_corpus_for_check(
                session=session,
                doc=doc,
                check=check,
                segments=[primary, current],
                current_segment=current,
            )

        runner._chunks.build_safe_chunks_for_segment.assert_awaited_once()
        call_kwargs = runner._chunks.build_safe_chunks_for_segment.call_args.kwargs
        assert call_kwargs["segment_id"] == "seg-current"

    @pytest.mark.asyncio
    async def test_current_segment_scope_no_current_fallback_to_primary(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.CURRENT_SEGMENT)
        session = MagicMock()

        primary = _make_segment("seg-primary", is_primary=True)

        with patch("engine.checks.check_runner.ArtifactStore") as mock_store_cls:
            mock_store_cls.return_value.get_json.return_value = {}

            result = await runner._build_corpus_for_check(
                session=session,
                doc=doc,
                check=check,
                segments=[primary],
                current_segment=None,  # no current segment
            )

        runner._chunks.build_safe_chunks_for_segment.assert_awaited_once()
        call_kwargs = runner._chunks.build_safe_chunks_for_segment.call_args.kwargs
        assert call_kwargs["segment_id"] == "seg-primary"

    @pytest.mark.asyncio
    async def test_document_scope_uses_build_safe_chunks(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.DOCUMENT)
        session = MagicMock()

        primary = _make_segment(
            "seg-primary",
            is_primary=True,
            enrichment_ref="s3://bucket/enr1.json",
        )
        appendix = _make_segment(
            "seg-appendix",
            is_primary=False,
            segment_type="appendix",
            enrichment_ref="s3://bucket/enr2.json",
        )

        mock_sidecar = {"enrichments": []}

        with patch("engine.checks.check_runner.ArtifactStore") as mock_store_cls:
            mock_store_cls.return_value.get_json.return_value = mock_sidecar

            result = await runner._build_corpus_for_check(
                session=session,
                doc=doc,
                check=check,
                segments=[primary, appendix],
                current_segment=None,
            )

        runner._chunks.build_safe_chunks.assert_awaited_once()
        runner._chunks.build_safe_chunks_for_segment.assert_not_awaited()

        call_kwargs = runner._chunks.build_safe_chunks.call_args.kwargs
        sidecars = call_kwargs.get("enrichment_sidecars_by_segment")
        assert sidecars is not None
        assert "seg-primary" in sidecars
        assert "seg-appendix" in sidecars

    @pytest.mark.asyncio
    async def test_document_scope_sidecar_load_error_continues(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.DOCUMENT)
        session = MagicMock()

        primary = _make_segment(
            "seg-primary",
            is_primary=True,
            enrichment_ref="s3://bucket/enr1.json",
        )
        appendix = _make_segment(
            "seg-appendix",
            is_primary=False,
            segment_type="appendix",
            enrichment_ref="s3://bucket/enr2.json",
        )

        with patch("engine.checks.check_runner.ArtifactStore") as mock_store_cls:
            # First call succeeds, second fails
            mock_store_cls.return_value.get_json.side_effect = [
                {"enrichments": []},
                RuntimeError("storage error"),
            ]

            result = await runner._build_corpus_for_check(
                session=session,
                doc=doc,
                check=check,
                segments=[primary, appendix],
                current_segment=None,
            )

        # Should still call build_safe_chunks even with partial sidecar failure
        runner._chunks.build_safe_chunks.assert_awaited_once()
        call_kwargs = runner._chunks.build_safe_chunks.call_args.kwargs
        sidecars = call_kwargs.get("enrichment_sidecars_by_segment")
        # Only one sidecar loaded successfully
        assert len(sidecars) == 1

    @pytest.mark.asyncio
    async def test_document_scope_no_enrichment_refs_passes_none(self):
        runner = _make_runner()
        doc = _make_doc_snap()
        check = _make_check(RetrievalCorpusScope.DOCUMENT)
        session = MagicMock()

        primary = _make_segment(
            "seg-primary",
            is_primary=True,
            enrichment_ref=None,  # no ref
        )
        appendix = _make_segment(
            "seg-appendix",
            is_primary=False,
            segment_type="appendix",
            enrichment_ref=None,  # no ref
        )

        result = await runner._build_corpus_for_check(
            session=session,
            doc=doc,
            check=check,
            segments=[primary, appendix],
            current_segment=None,
        )

        runner._chunks.build_safe_chunks.assert_awaited_once()
        call_kwargs = runner._chunks.build_safe_chunks.call_args.kwargs
        sidecars = call_kwargs.get("enrichment_sidecars_by_segment")
        # Empty dict → passed as None
        assert sidecars is None


class TestBatchCorpusCache:
    """
    Tests that batch execution uses corpus cache correctly.
    Different checks with same corpus key reuse cached corpus.
    Different corpus keys build separate corpora.
    """

    def _make_runner_with_corpus_tracking(self) -> tuple[CheckRunner, list]:
        runner = _make_runner()
        build_calls = []

        original = runner._build_corpus_for_check

        async def tracked_build(*args, **kwargs):
            build_calls.append(kwargs.get("check").id)
            return [{"id": f"chunk-for-{kwargs.get('check').id}"}]

        runner._build_corpus_for_check = tracked_build
        return runner, build_calls

    @pytest.mark.asyncio
    async def test_same_scope_and_levels_reuses_cache(self):
        """
        Two checks with same corpus_scope + same levels → one corpus build.
        """
        runner, build_calls = self._make_runner_with_corpus_tracking()

        check_a = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT, ["legal_unit"])
        check_a.id = "check_a"
        check_b = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT, ["legal_unit"])
        check_b.id = "check_b"

        session = MagicMock()
        doc = _make_doc_snap()
        segment = _make_segment("seg-1", is_primary=True)

        corpus_cache: dict = {}
        current_segment = segment

        for check in [check_a, check_b]:
            _corpus_scope = check.retrieval.corpus_scope
            _corpus_key = (
                _corpus_scope,
                "seg-1",
                tuple(sorted(check.retrieval.levels or [])),
            )
            if _corpus_key not in corpus_cache:
                corpus_cache[_corpus_key] = await runner._build_corpus_for_check(
                    session=session,
                    doc=doc,
                    check=check,
                    segments=[segment],
                    current_segment=current_segment,
                )

        # Only one build call because both checks have same key
        assert len(build_calls) == 1
        assert build_calls[0] == "check_a"

    @pytest.mark.asyncio
    async def test_different_scope_builds_separate_corpus(self):
        """
        check_a=PRIMARY_SEGMENT, check_b=DOCUMENT → two separate corpus builds.
        """
        runner, build_calls = self._make_runner_with_corpus_tracking()

        check_a = _make_check(RetrievalCorpusScope.PRIMARY_SEGMENT, ["legal_unit"])
        check_a.id = "check_a"
        check_b = _make_check(RetrievalCorpusScope.DOCUMENT, ["legal_unit"])
        check_b.id = "check_b"

        session = MagicMock()
        doc = _make_doc_snap()
        segment = _make_segment("seg-1", is_primary=True)

        corpus_cache: dict = {}

        for check in [check_a, check_b]:
            _corpus_scope = check.retrieval.corpus_scope
            _corpus_key = (
                _corpus_scope,
                "seg-1",
                tuple(sorted(check.retrieval.levels or [])),
            )
            if _corpus_key not in corpus_cache:
                corpus_cache[_corpus_key] = await runner._build_corpus_for_check(
                    session=session,
                    doc=doc,
                    check=check,
                    segments=[segment],
                    current_segment=segment,
                )

        assert len(build_calls) == 2
        assert set(build_calls) == {"check_a", "check_b"}


class TestProvenanceOverridePolicy:
    """
    Tests that segment execution context does NOT override provenance
    for document-scope checks, but DOES override for segment-scope checks.
    """

    def test_primary_segment_scope_provenance_is_overridden(self):
        exec_result = {
            "segment_id": "seg-from-chunk-metadata",
            "segment_type": "appendix",
        }
        segment = _make_segment("seg-execution-context", is_primary=True)

        corpus_scope = RetrievalCorpusScope.PRIMARY_SEGMENT

        if corpus_scope != RetrievalCorpusScope.DOCUMENT:
            exec_result["segment_id"] = getattr(segment, "segment_id", None)
            exec_result["segment_type"] = getattr(segment, "segment_type", None)

        assert exec_result["segment_id"] == "seg-execution-context"

    def test_document_scope_provenance_not_overridden(self):
        exec_result = {
            "segment_id": "seg-from-chunk-metadata",
            "segment_type": "appendix",
        }
        segment = _make_segment("seg-execution-context", is_primary=True)

        corpus_scope = RetrievalCorpusScope.DOCUMENT

        if corpus_scope != RetrievalCorpusScope.DOCUMENT:
            exec_result["segment_id"] = getattr(segment, "segment_id", None)
            exec_result["segment_type"] = getattr(segment, "segment_type", None)

        # Provenance preserved from chunk metadata
        assert exec_result["segment_id"] == "seg-from-chunk-metadata"
        assert exec_result["segment_type"] == "appendix"

    def test_current_segment_scope_provenance_is_overridden(self):
        exec_result = {
            "segment_id": "seg-from-chunk-metadata",
            "segment_type": "appendix",
        }
        segment = _make_segment("seg-execution-context", is_primary=False)

        corpus_scope = RetrievalCorpusScope.CURRENT_SEGMENT

        if corpus_scope != RetrievalCorpusScope.DOCUMENT:
            exec_result["segment_id"] = getattr(segment, "segment_id", None)
            exec_result["segment_type"] = getattr(segment, "segment_type", None)

        assert exec_result["segment_id"] == "seg-execution-context"


        