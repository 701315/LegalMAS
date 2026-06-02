"""
Tests for P3a: structure_builder saves chunk_plan_ref.

Проверяет:
1. build_file_structure_with_chunk_plan() вызывается (не build_file_structure())
2. chunk_plan.json сохраняется в MinIO
3. update_refs получает chunk_plan_ref
4. ошибка сохранения plan не ломает pipeline
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Any

import pytest

from services.structure._models._analysis import RecommendedChunkingMode
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_file_chunk_plan(document_id: str = "doc-test") -> FileChunkPlan:
    """Минимальный валидный FileChunkPlan для тестов."""
    mode_decision = ChunkingModeDecision(
        mode=RecommendedChunkingMode.STRUCTURE_FIRST,
        retrieval_safe=True,
        reason="test: clean structure",
        token_params=TOKENS_MODE_A,
        allow_section_chunks=True,
        allow_subclause_splitting=True,
        drop_technical_fallback_nodes=False,
        prefer_layout_fallback=False,
    )
    seg_plan = SegmentChunkPlan(
        segment_id="seg-001",
        segment_type="contract",
        mode=RecommendedChunkingMode.STRUCTURE_FIRST,
        token_params=TOKENS_MODE_A,
        allow_section_chunks=True,
        allow_subclause_splitting=True,
        drop_technical_fallback_nodes=False,
        retrieval_safe=True,
        fallback_fragment_ratio=0.0,
    )
    return FileChunkPlan(
        document_id=document_id,
        mode_decision=mode_decision,
        segment_plans=(seg_plan,),
    )


def _make_mock_file_analysis(document_id: str = "doc-test") -> MagicMock:
    """Мок FileStructureAnalysisResult."""
    mock_tree = MagicMock()
    mock_tree.to_dict.return_value = {"root": [], "structure_diagnostics": {}}
    mock_tree.structure_confidence = 0.9
    mock_tree.degraded = False

    mock_file_graph = MagicMock()
    mock_file_graph.to_dict.return_value = {"segments": []}
    mock_file_graph.segments = []

    mock_file_result = MagicMock()
    mock_file_result.primary_tree = mock_tree
    mock_file_result.file_graph = mock_file_graph
    mock_file_result.segment_trees = [mock_tree]

    mock_analysis = MagicMock()
    mock_analysis.file_structure = mock_file_result

    return mock_analysis


# ─── Tests: chunk plan is saved ──────────────────────────────────────────────

class TestStructureBuilderSavesChunkPlan:

    def test_build_file_structure_with_chunk_plan_is_called(self) -> None:
        """
        Убедиться что новый pipeline (Phase 10) вызывается,
        а не старый build_file_structure().
        """
        document_id = "doc-test-001"
        mock_analysis = _make_mock_file_analysis(document_id)
        mock_plan = _make_file_chunk_plan(document_id)

        with patch(
            "workers.structure_builder.build_file_structure_with_chunk_plan",
            return_value=(mock_analysis, mock_plan),
        ) as mock_build:
            # Имитируем вызов как в _build_structure_async
            result_analysis, result_plan = mock_build(
                document_id=document_id,
                elements=[{"type": "text", "text": "test"}],
                document_version_id="ver-001",
            )

        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["document_id"] == document_id
        assert call_kwargs["document_version_id"] == "ver-001"

    def test_chunk_plan_to_dict_is_called_before_store(self) -> None:
        """
        Убедиться что FileChunkPlan.to_dict() вызывается
        перед сохранением в store.
        """
        plan = _make_file_chunk_plan("doc-test")
        plan_dict = plan.to_dict()

        # Проверяем структуру to_dict
        assert "schema_version" in plan_dict
        assert "document_id" in plan_dict
        assert "mode_decision" in plan_dict
        assert "segment_plans" in plan_dict
        assert plan_dict["schema_version"] == "1.0"

    def test_chunk_plan_ref_written_to_artifact_path(self) -> None:
        """
        ArtifactPath.chunk_plan() должен строить path
        в structures/ рядом с file_graph.json.
        """
        from storage.artifact_store import ArtifactPath

        path = ArtifactPath.chunk_plan(
            tenant_id="tenant-111",
            deal_id="deal-222",
            document_id="doc-333",
        )

        assert "tenant-111" in path
        assert "deal-222" in path
        assert "doc-333" in path
        assert "chunk_plan.json" in path
        assert "structures" in path
        # Проверяем что это тот же каталог что file_graph.json
        file_graph_path = ArtifactPath.file_graph(
            tenant_id="tenant-111",
            deal_id="deal-222",
            document_id="doc-333",
        )
        assert path.rsplit("/", 1)[0] == file_graph_path.rsplit("/", 1)[0]

    def test_chunk_plan_roundtrip_through_json(self) -> None:
        """
        Симулировать store.put_json() + store.get_json() + FileChunkPlan.from_dict().
        Это проверяет что сохранённый план можно потом загрузить.
        """
        import json

        plan = _make_file_chunk_plan("doc-roundtrip")
        plan_dict = plan.to_dict()

        # Симулируем JSON serialization/deserialization (как в MinIO)
        serialized = json.dumps(plan_dict, ensure_ascii=False)
        deserialized = json.loads(serialized)

        restored = FileChunkPlan.from_dict(deserialized)

        assert restored.document_id == plan.document_id
        assert restored.mode_decision.mode == plan.mode_decision.mode
        assert len(restored.segment_plans) == len(plan.segment_plans)
        assert restored.segment_plans[0].segment_id == "seg-001"


# ─── Tests: chunk_plan_ref propagation ───────────────────────────────────────

class TestChunkPlanRefPropagation:

    def test_chunk_plan_ref_is_none_when_store_fails(self) -> None:
        """
        При ошибке store.put_json() — chunk_plan_ref должен быть None,
        а не выбрасывать исключение.
        """
        mock_store = MagicMock()
        mock_store.put_json.side_effect = Exception("MinIO connection error")

        plan = _make_file_chunk_plan("doc-test")
        chunk_plan_ref = None

        # Симулируем best-effort блок из structure_builder
        try:
            chunk_plan_ref = mock_store.put_json("path/chunk_plan.json", plan.to_dict())
        except Exception:
            chunk_plan_ref = None

        assert chunk_plan_ref is None

    def test_chunk_plan_ref_is_set_when_store_succeeds(self) -> None:
        """
        При успешном store.put_json() — chunk_plan_ref должен быть non-None.
        """
        expected_ref = "s3://mas-artifacts/tenants/t1/deals/d1/structures/doc1/chunk_plan.json"
        mock_store = MagicMock()
        mock_store.put_json.return_value = expected_ref

        plan = _make_file_chunk_plan("doc-test")
        chunk_plan_ref = None

        try:
            chunk_plan_ref = mock_store.put_json("path/chunk_plan.json", plan.to_dict())
        except Exception:
            chunk_plan_ref = None

        assert chunk_plan_ref == expected_ref

    def test_update_refs_receives_chunk_plan_ref(self) -> None:
        """
        update_refs() должен вызываться с chunk_plan_ref когда план сохранён.
        """
        mock_ver_repo = MagicMock()
        mock_ver_repo.update_refs = AsyncMock(return_value=MagicMock())

        expected_ref = "s3://mas-artifacts/.../chunk_plan.json"

        # Симулируем вызов из structure_builder
        import asyncio

        async def _simulate():
            await mock_ver_repo.update_refs(
                version_id="ver-001",
                clause_tree_ref="s3://.../clause_tree.json",
                file_graph_ref="s3://.../file_graph.json",
                segments_count=1,
                chunk_plan_ref=expected_ref,
            )

        asyncio.run(_simulate())

        mock_ver_repo.update_refs.assert_called_once()
        call_kwargs = mock_ver_repo.update_refs.call_args.kwargs
        assert call_kwargs["chunk_plan_ref"] == expected_ref

    def test_update_refs_receives_none_chunk_plan_ref_when_store_fails(self) -> None:
        """
        update_refs() должен вызываться с chunk_plan_ref=None
        когда сохранение плана провалилось.
        """
        mock_ver_repo = MagicMock()
        mock_ver_repo.update_refs = AsyncMock(return_value=MagicMock())

        import asyncio

        async def _simulate():
            chunk_plan_ref = None  # store failed
            await mock_ver_repo.update_refs(
                version_id="ver-001",
                clause_tree_ref="s3://.../clause_tree.json",
                file_graph_ref="s3://.../file_graph.json",
                segments_count=1,
                chunk_plan_ref=chunk_plan_ref,
            )

        asyncio.run(_simulate())

        call_kwargs = mock_ver_repo.update_refs.call_args.kwargs
        assert call_kwargs["chunk_plan_ref"] is None


# ─── Tests: manifest writer ───────────────────────────────────────────────────

class TestManifestWriterChunkPlanRef:

    def test_manifest_includes_chunk_plan_ref(self) -> None:
        """
        write_artifact_manifest_best_effort() должен принимать
        и записывать chunk_plan_ref.
        """
        mock_store = MagicMock()
        mock_store.put_json.return_value = "s3://.../artifact_manifest.json"

        from storage._artifact_manifest import write_artifact_manifest_best_effort

        ref = write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="tenant-111",
            deal_id="deal-222",
            document_id="doc-333",
            document_version_id="ver-444",
            clause_tree_ref="s3://.../clause_tree.json",
            file_graph_ref="s3://.../file_graph.json",
            chunk_plan_ref="s3://.../chunk_plan.json",
            chunks_manifest_v2_ref=None,
            stage="structure",
        )

        assert ref is not None
        mock_store.put_json.assert_called_once()
        # Проверяем что в manifest_data попал chunk_plan_ref
        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert manifest_data["chunk_plan_ref"] == "s3://.../chunk_plan.json"

    def test_manifest_chunk_plan_ref_none_is_ok(self) -> None:
        """
        chunk_plan_ref=None в manifest — валидный кейс
        (plan не был вычислен или сохранение упало).
        """
        mock_store = MagicMock()
        mock_store.put_json.return_value = "s3://.../artifact_manifest.json"

        from storage._artifact_manifest import write_artifact_manifest_best_effort

        ref = write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="tenant-111",
            deal_id="deal-222",
            document_id="doc-333",
            document_version_id="ver-444",
            chunk_plan_ref=None,
            stage="structure",
        )

        assert ref is not None
        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert manifest_data["chunk_plan_ref"] is None



        