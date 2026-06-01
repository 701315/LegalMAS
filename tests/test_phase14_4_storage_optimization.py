"""
Phase 14.4 — Storage Optimization tests.

Covers:
- ArtifactStore.delete_many_best_effort()
- Stale segment_meta cleanup in chunk_builder
- SegmentArtifactRefs extended fields (legal_units, enrichment)
- write_artifact_manifest_best_effort()
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from services.structure._models._artifacts import (
    CanonicalArtifactRefs,
    SegmentArtifactRefs,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SegmentArtifactRefs — extended fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestSegmentArtifactRefsExtended:
    """Tests for legal_units_ref and legal_units_enrichment_ref fields."""

    def test_has_legal_units_false_by_default(self) -> None:
        seg = SegmentArtifactRefs(segment_id="seg-1")
        assert seg.has_legal_units is False
        assert seg.has_enrichment is False

    def test_has_legal_units_true_when_set(self) -> None:
        seg = SegmentArtifactRefs(
            segment_id="seg-1",
            legal_units_ref="s3://bucket/lu.json",
        )
        assert seg.has_legal_units is True
        assert seg.has_enrichment is False

    def test_has_enrichment_true_when_set(self) -> None:
        seg = SegmentArtifactRefs(
            segment_id="seg-1",
            legal_units_enrichment_ref="s3://bucket/enr.json",
        )
        assert seg.has_legal_units is False
        assert seg.has_enrichment is True

    def test_to_dict_includes_new_fields(self) -> None:
        seg = SegmentArtifactRefs(
            segment_id="seg-1",
            segment_clause_tree_ref="s3://bucket/tree.json",
            segment_chunks_ref="s3://bucket/chunks.json",
            legal_units_ref="s3://bucket/lu.json",
            legal_units_enrichment_ref="s3://bucket/enr.json",
        )
        d = seg.to_dict()
        assert d["legal_units_ref"] == "s3://bucket/lu.json"
        assert d["legal_units_enrichment_ref"] == "s3://bucket/enr.json"
        assert d["has_legal_units"] is True
        assert d["has_enrichment"] is True

    def test_to_dict_new_fields_none_by_default(self) -> None:
        seg = SegmentArtifactRefs(segment_id="seg-1")
        d = seg.to_dict()
        assert d["legal_units_ref"] is None
        assert d["legal_units_enrichment_ref"] is None
        assert d["has_legal_units"] is False
        assert d["has_enrichment"] is False

    def test_backward_compat_existing_fields_unchanged(self) -> None:
        """Existing has_tree / has_chunks still work with new fields."""
        seg = SegmentArtifactRefs(
            segment_id="seg-1",
            segment_clause_tree_ref="tree-ref",
            segment_chunks_ref="chunks-ref",
            legal_units_ref="lu-ref",
        )
        assert seg.has_tree is True
        assert seg.has_chunks is True
        assert seg.has_legal_units is True
        assert seg.has_enrichment is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ArtifactStore.delete_many_best_effort
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeleteManyBestEffort:
    """Tests for ArtifactStore.delete_many_best_effort()."""

    def _make_store(self) -> MagicMock:
        """Create a mock ArtifactStore with delete_many_best_effort."""
        from storage.artifact_store import ArtifactStore

        store = MagicMock(spec=ArtifactStore)

        # Use real implementation
        store.delete_many_best_effort = ArtifactStore.delete_many_best_effort.__get__(
            store, ArtifactStore
        )
        store._normalize_object_path = ArtifactStore._normalize_object_path.__get__(
            store, ArtifactStore
        )
        store.bucket = "test-bucket"
        return store

    def test_empty_list_returns_zero_counts(self) -> None:
        store = self._make_store()
        result = store.delete_many_best_effort([])
        assert result["requested"] == 0
        assert result["deleted"] == 0
        assert result["failed"] == 0
        assert result["errors"] == []

    def test_successful_deletes_counted(self) -> None:
        store = self._make_store()
        store.client = MagicMock()
        store.client.remove_object = MagicMock()

        result = store.delete_many_best_effort(["path/a.json", "path/b.json"])
        assert result["requested"] == 2
        assert result["deleted"] == 2
        assert result["failed"] == 0

    def test_failed_delete_does_not_raise(self) -> None:
        store = self._make_store()
        store.client = MagicMock()
        store.client.remove_object = MagicMock(
            side_effect=Exception("connection refused")
        )

        result = store.delete_many_best_effort(["path/a.json"])
        assert result["requested"] == 1
        assert result["deleted"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert "connection refused" in result["errors"][0]["error"]

    def test_partial_failure_continues(self) -> None:
        store = self._make_store()
        store.client = MagicMock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("timeout")

        store.client.remove_object = MagicMock(side_effect=side_effect)

        result = store.delete_many_best_effort(
            ["path/a.json", "path/b.json", "path/c.json"]
        )
        assert result["requested"] == 3
        assert result["deleted"] == 2
        assert result["failed"] == 1

    def test_s3_uri_normalized(self) -> None:
        store = self._make_store()
        store.client = MagicMock()
        store.client.remove_object = MagicMock()

        store.delete_many_best_effort(
            ["s3://test-bucket/path/a.json"]
        )

        store.client.remove_object.assert_called_once_with(
            bucket_name="test-bucket",
            object_name="path/a.json",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Stale segment_meta cleanup logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestStaleSegmentMetaCleanup:
    """
    Tests for Phase 14.4 fix: stale legal_units_ref / enrichment_ref
    must be removed from segment_meta when new snapshot is not built.
    """

    def _apply_meta_logic(
        self,
        existing_meta: dict,
        legal_units_ref: str | None,
        legal_units_enrichment_ref: str | None,
    ) -> dict:
        """Reproduce the fixed logic from chunk_builder."""
        meta = dict(existing_meta)
        if legal_units_ref is not None:
            meta["legal_units_ref"] = legal_units_ref
        else:
            meta.pop("legal_units_ref", None)

        if legal_units_enrichment_ref is not None:
            meta["legal_units_enrichment_ref"] = legal_units_enrichment_ref
        else:
            meta.pop("legal_units_enrichment_ref", None)
        return meta

    def test_new_refs_overwrite_old(self) -> None:
        old_meta = {
            "legal_units_ref": "old-lu",
            "legal_units_enrichment_ref": "old-enr",
            "other_key": "preserved",
        }
        result = self._apply_meta_logic(old_meta, "new-lu", "new-enr")
        assert result["legal_units_ref"] == "new-lu"
        assert result["legal_units_enrichment_ref"] == "new-enr"
        assert result["other_key"] == "preserved"

    def test_missing_lu_removes_stale_ref(self) -> None:
        old_meta = {
            "legal_units_ref": "old-lu",
            "other_key": "preserved",
        }
        result = self._apply_meta_logic(old_meta, None, None)
        assert "legal_units_ref" not in result
        assert result["other_key"] == "preserved"

    def test_missing_enrichment_removes_stale_ref(self) -> None:
        old_meta = {
            "legal_units_ref": "old-lu",
            "legal_units_enrichment_ref": "old-enr",
        }
        result = self._apply_meta_logic(old_meta, "new-lu", None)
        assert result["legal_units_ref"] == "new-lu"
        assert "legal_units_enrichment_ref" not in result

    def test_no_old_refs_no_crash(self) -> None:
        old_meta = {"other_key": "val"}
        result = self._apply_meta_logic(old_meta, None, None)
        assert "legal_units_ref" not in result
        assert "legal_units_enrichment_ref" not in result
        assert result["other_key"] == "val"

    def test_empty_meta_with_new_refs(self) -> None:
        result = self._apply_meta_logic({}, "new-lu", "new-enr")
        assert result["legal_units_ref"] == "new-lu"
        assert result["legal_units_enrichment_ref"] == "new-enr"

    def test_both_absent_cleans_both(self) -> None:
        old_meta = {
            "legal_units_ref": "old-lu",
            "legal_units_enrichment_ref": "old-enr",
        }
        result = self._apply_meta_logic(old_meta, None, None)
        assert "legal_units_ref" not in result
        assert "legal_units_enrichment_ref" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Artifact Manifest Writer
# ═══════════════════════════════════════════════════════════════════════════════


class TestArtifactManifestWriter:
    """Tests for write_artifact_manifest_best_effort()."""

    def test_writes_manifest_successfully(self) -> None:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        mock_store = MagicMock()
        mock_store.put_json = MagicMock(return_value="s3://bucket/manifest.json")

        ref = write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
            clause_tree_ref="ct-ref",
            file_graph_ref="fg-ref",
            stage="structure",
        )

        assert ref == "s3://bucket/manifest.json"
        mock_store.put_json.assert_called_once()

        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert manifest_data["document_id"] == "doc1"
        assert manifest_data["clause_tree_ref"] == "ct-ref"
        assert manifest_data["file_graph_ref"] == "fg-ref"
        assert manifest_data["last_updated_by_stage"] == "structure"

    def test_returns_none_on_failure(self) -> None:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        mock_store = MagicMock()
        mock_store.put_json = MagicMock(side_effect=Exception("MinIO down"))

        ref = write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
            stage="chunking",
        )

        assert ref is None

    def test_manifest_includes_segment_refs(self) -> None:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        mock_store = MagicMock()
        mock_store.put_json = MagicMock(return_value="s3://ref")

        seg_refs = [
            {
                "segment_id": "seg-1",
                "segment_clause_tree_ref": "tree-1",
                "segment_chunks_ref": "chunks-1",
                "legal_units_ref": "lu-1",
            },
        ]

        write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
            segment_refs=seg_refs,
            stage="chunking",
        )

        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert len(manifest_data["segments"]) == 1
        assert manifest_data["segments"][0]["legal_units_ref"] == "lu-1"

    def test_manifest_includes_extra(self) -> None:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        mock_store = MagicMock()
        mock_store.put_json = MagicMock(return_value="s3://ref")

        write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
            stage="chunking",
            extra={"chunk_count_total": 42},
        )

        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert manifest_data["extra"]["chunk_count_total"] == 42

    def test_manifest_has_timestamp(self) -> None:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        mock_store = MagicMock()
        mock_store.put_json = MagicMock(return_value="s3://ref")

        before = time.time()
        write_artifact_manifest_best_effort(
            store=mock_store,
            tenant_id="t1",
            deal_id="d1",
            document_id="doc1",
            document_version_id="v1",
            stage="structure",
        )
        after = time.time()

        call_args = mock_store.put_json.call_args
        manifest_data = call_args[0][1]
        assert before <= manifest_data["last_updated_at"] <= after


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Stale ref computation logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestStaleRefComputation:
    """Tests for the stale ref detection logic used in workers."""

    def test_no_old_refs_means_nothing_to_clean(self) -> None:
        old_refs: list[str] = []
        current_refs: set[str] = {"ref-1", "ref-2"}
        stale = [r for r in old_refs if r not in current_refs]
        assert stale == []

    def test_all_old_refs_still_current(self) -> None:
        old_refs = ["ref-1", "ref-2"]
        current_refs = {"ref-1", "ref-2"}
        stale = [r for r in old_refs if r not in current_refs]
        assert stale == []

    def test_some_old_refs_are_stale(self) -> None:
        old_refs = ["ref-1", "ref-2", "ref-3"]
        current_refs = {"ref-2"}
        stale = [r for r in old_refs if r not in current_refs]
        assert set(stale) == {"ref-1", "ref-3"}

    def test_all_old_refs_are_stale(self) -> None:
        old_refs = ["old-1", "old-2"]
        current_refs: set[str] = {"new-1"}
        stale = [r for r in old_refs if r not in current_refs]
        assert set(stale) == {"old-1", "old-2"}

    def test_deterministic_segment_id_same_path_not_stale(self) -> None:
        """
        When segment_id is deterministic (uuid5) and segment count unchanged,
        old and new refs are the same path → nothing stale.
        """
        old_refs = ["structures/doc1/segment_550e8400.json"]
        current_refs = {"structures/doc1/segment_550e8400.json"}
        stale = [r for r in old_refs if r not in current_refs]
        assert stale == []

    def test_segment_count_decreased_creates_stale(self) -> None:
        """When segment count decreases, old extra segments become stale."""
        old_refs = [
            "structures/doc1/segment_550e8400.json",
            "structures/doc1/segment_660f9511.json",
            "structures/doc1/segment_770a0622.json",
        ]
        current_refs = {
            "structures/doc1/segment_550e8400.json",
            "structures/doc1/segment_660f9511.json",
        }
        stale = [r for r in old_refs if r not in current_refs]
        assert stale == ["structures/doc1/segment_770a0622.json"]


        