import uuid

import pytest

from core.constants import DocumentStatus, RunStatus
from core.pipeline_snapshots import DocumentSnapshot, RunSnapshot, VersionSnapshot
import workers.run_orchestrator as run_orchestrator


@pytest.mark.asyncio
async def test_classified_single_document_schedules_semantic_enrichment() -> None:
    deal_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()

    version_snap = VersionSnapshot(
        id=version_id,
        segments_count=1,
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
    )

    class FakeSegRepo:
        async def count_by_version_and_has_segment_id(self, version_id_arg):
            assert version_id_arg == version_id
            return 1

        async def count_unclassified_for_version(self, version_id_arg):
            assert version_id_arg == version_id
            return 0

        async def get_chunk_refs_summary(self, version_id_arg):
            return {"total_segments": 1, "segments_with_chunks": 1}

    plan = await run_orchestrator._build_document_task_plan(
        doc_id_str=str(doc_id),
        snap=version_snap,
        status=DocumentStatus.CLASSIFIED.value,
        run_id=str(run_id),
        deal_id_str=str(deal_id),
        tenant_id_str=str(tenant_id),
        is_full_rerun=False,
        force_reclassify=False,
        seg_repo=FakeSegRepo(),
        deal_primary_language="ru",
    )

    assert plan is not None
    assert plan.task_name == "workers.build_legal_units_enrichment"
    assert plan.stage == "build_legal_units_enrichment"
    assert plan.reason == "classification_path_complete"
    assert plan.kwargs["document_id"] == str(doc_id)
    assert plan.kwargs["document_version_id"] == str(version_id)
    assert plan.kwargs["deal_id"] == str(deal_id)
    assert plan.kwargs["run_id"] == str(run_id)


@pytest.mark.asyncio
async def test_classified_multi_document_with_unclassified_segments_schedules_segment_classification() -> None:
    deal_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()

    version_snap = VersionSnapshot(
        id=version_id,
        segments_count=2,
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
    )

    class FakeSegRepo:
        async def count_by_version_and_has_segment_id(self, version_id_arg):
            assert version_id_arg == version_id
            return 2

        async def count_unclassified_for_version(self, version_id_arg):
            assert version_id_arg == version_id
            return 1

        async def get_chunk_refs_summary(self, version_id_arg):
            return {"total_segments": 2, "segments_with_chunks": 2}

    plan = await run_orchestrator._build_document_task_plan(
        doc_id_str=str(doc_id),
        snap=version_snap,
        status=DocumentStatus.CLASSIFIED.value,
        run_id=str(run_id),
        deal_id_str=str(deal_id),
        tenant_id_str=str(tenant_id),
        is_full_rerun=False,
        force_reclassify=False,
        seg_repo=FakeSegRepo(),
        deal_primary_language="ru",
    )

    assert plan is not None
    assert plan.task_name == "workers.classify_document_segments"
    assert plan.stage == "classify_document_segments"


@pytest.mark.asyncio
async def test_enriched_document_has_no_further_document_stage() -> None:
    deal_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()

    version_snap = VersionSnapshot(
        id=version_id,
        segments_count=1,
    )

    class FakeSegRepo:
        async def count_by_version_and_has_segment_id(self, version_id_arg):
            return 1

        async def count_unclassified_for_version(self, version_id_arg):
            return 0

        async def get_chunk_refs_summary(self, version_id_arg):
            return {"total_segments": 1, "segments_with_chunks": 1}

    plan = await run_orchestrator._build_document_task_plan(
        doc_id_str=str(doc_id),
        snap=version_snap,
        status=DocumentStatus.ENRICHED.value,
        run_id=str(run_id),
        deal_id_str=str(deal_id),
        tenant_id_str=str(tenant_id),
        is_full_rerun=False,
        force_reclassify=False,
        seg_repo=FakeSegRepo(),
        deal_primary_language="ru",
    )

    assert plan is None


@pytest.mark.asyncio
async def test_checks_gate_blocks_when_document_only_classified() -> None:
    run_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    run_snap = RunSnapshot(
        id=run_id,
        status=RunStatus.RUNNING.value,
        deal_id=deal_id,
        pipeline_strategy="V2_ONLY",
    )
    doc_snaps = [
        DocumentSnapshot(
            id=doc_id,
            status=DocumentStatus.CLASSIFIED.value,
        )
    ]

    version_obj = type("VersionObj", (), {"id": version_id, "segments_count": 1})()

    class FakeVersionRepo:
        async def get_latest(self, requested_doc_id):
            assert requested_doc_id == doc_id
            return version_obj

    class FakeSegRepo:
        async def count_by_version_and_has_segment_id(self, version_id_arg):
            assert version_id_arg == version_id
            return 1

        async def count_unclassified_for_version(self, version_id_arg):
            assert version_id_arg == version_id
            return 0

    can_start = await run_orchestrator._can_start_checks_for_run(
        run_snap=run_snap,
        doc_snaps=doc_snaps,
        ver_repo=FakeVersionRepo(),
        seg_repo=FakeSegRepo(),
    )

    assert can_start is False


@pytest.mark.asyncio
async def test_checks_gate_allows_when_document_enriched() -> None:
    run_id = uuid.uuid4()
    deal_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()

    run_snap = RunSnapshot(
        id=run_id,
        status=RunStatus.RUNNING.value,
        deal_id=deal_id,
        pipeline_strategy="V2_ONLY",
    )
    doc_snaps = [
        DocumentSnapshot(
            id=doc_id,
            status=DocumentStatus.ENRICHED.value,
        )
    ]

    version_obj = type("VersionObj", (), {"id": version_id, "segments_count": 1})()

    class FakeVersionRepo:
        async def get_latest(self, requested_doc_id):
            assert requested_doc_id == doc_id
            return version_obj

    class FakeSegRepo:
        async def count_by_version_and_has_segment_id(self, version_id_arg):
            assert version_id_arg == version_id
            return 1

        async def count_unclassified_for_version(self, version_id_arg):
            assert version_id_arg == version_id
            return 0

    can_start = await run_orchestrator._can_start_checks_for_run(
        run_snap=run_snap,
        doc_snaps=doc_snaps,
        ver_repo=FakeVersionRepo(),
        seg_repo=FakeSegRepo(),
    )

    assert can_start is True

    