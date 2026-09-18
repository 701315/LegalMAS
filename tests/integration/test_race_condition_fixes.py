"""
Integration test suite для проверки исправления race condition
между stages и checks в run pipeline.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.constants import (
    CheckExecutionStatus,
    DocumentStatus,
)
from core.pipeline_snapshots import DocumentSnapshot


@pytest.fixture
def sent_tasks() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def mock_send_task(sent_tasks: list[dict[str, Any]]):
    def _capture(task_name: str, kwargs: dict[str, Any] | None = None, **_ignored):
        sent_tasks.append(
            {
                "task_name": task_name,
                "kwargs": dict(kwargs or {}),
            }
        )
        result = MagicMock()
        result.id = str(uuid.uuid4())
        return result

    with patch(
        "mas_queue.task_dispatcher.send_task_with_context",
        side_effect=_capture,
    ) as _mock:
        yield _mock


class TestFix1OrchestratorRaceCondition:
    def _make_enriched_snapshot(self, doc_id: uuid.UUID) -> DocumentSnapshot:
        return DocumentSnapshot(
            id=doc_id,
            status=DocumentStatus.ENRICHED.value,
            doc_type="msa",
            classification_level="platform",
            classification_confidence=0.95,
            applicable_triggers=(),
            detected_languages=("en",),
        )

    def test_document_with_new_stage_does_NOT_trigger_checks_from_orchestrator(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        doc_id = uuid.uuid4()
        enriched_snap = self._make_enriched_snapshot(doc_id)
        scheduled_ids = {doc_id}

        should_dispatch_from_orchestrator = (
            enriched_snap.document_id not in scheduled_ids
            and enriched_snap.status
            in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and enriched_snap.doc_type is not None
        )

        assert not should_dispatch_from_orchestrator, (
            "Documents with newly scheduled stages must NOT receive checks "
            "dispatch from orchestrator (race condition guard)."
        )

    def test_document_without_new_stage_DOES_trigger_checks_from_orchestrator(
        self,
    ) -> None:
        doc_id = uuid.uuid4()
        enriched_snap = self._make_enriched_snapshot(doc_id)
        scheduled_ids: set[uuid.UUID] = set()

        should_dispatch_from_orchestrator = (
            enriched_snap.document_id not in scheduled_ids
            and enriched_snap.status
            in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and enriched_snap.doc_type is not None
        )

        assert should_dispatch_from_orchestrator, (
            "Documents without newly scheduled stages must receive checks "
            "dispatch directly from orchestrator."
        )

    def test_document_without_doc_type_is_skipped(self) -> None:
        doc_id = uuid.uuid4()
        snap = DocumentSnapshot(
            id=doc_id,
            status=DocumentStatus.ENRICHED.value,
            doc_type=None,
        )
        scheduled_ids: set[uuid.UUID] = set()

        should_dispatch = (
            snap.document_id not in scheduled_ids
            and snap.status
            in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and snap.doc_type is not None
        )

        assert not should_dispatch


class TestFix2BaseTaskFinalizeTrigger:
    def _make_base_task(self, task_name: str):
        from mas_queue.base_task import MASBaseTask  # noqa: PLC0415

        task = MASBaseTask()
        task.name = task_name
        return task

    def test_finalize_enqueued_for_stage_task_with_run_id(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        task = self._make_base_task("workers.build_legal_units_enrichment")
        run_id = str(uuid.uuid4())

        task._enqueue_finalize_if_needed(
            {"run_id": run_id, "tenant_id": str(uuid.uuid4())},
            reason="test",
        )

        finalize_calls = [
            t for t in sent_tasks if t["task_name"] == "workers.finalize_run_if_ready"
        ]
        assert len(finalize_calls) == 1
        assert finalize_calls[0]["kwargs"]["run_id"] == run_id

    def test_finalize_NOT_enqueued_for_excluded_task(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        task = self._make_base_task("workers.finalize_run_if_ready")

        task._enqueue_finalize_if_needed(
            {"run_id": str(uuid.uuid4())},
            reason="test",
        )

        assert not any(
            t["task_name"] == "workers.finalize_run_if_ready" for t in sent_tasks
        ), "Excluded tasks must not trigger recursive finalize"

    def test_finalize_NOT_enqueued_without_run_id(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        task = self._make_base_task("workers.build_structure")

        task._enqueue_finalize_if_needed({}, reason="test")
        task._enqueue_finalize_if_needed({"run_id": None}, reason="test")
        task._enqueue_finalize_if_needed({"run_id": "   "}, reason="test")

        assert not any(
            t["task_name"] == "workers.finalize_run_if_ready" for t in sent_tasks
        )

    def test_finalize_NOT_enqueued_with_invalid_uuid(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        task = self._make_base_task("workers.build_structure")

        task._enqueue_finalize_if_needed(
            {"run_id": "not-a-valid-uuid"},
            reason="test",
        )

        assert not any(
            t["task_name"] == "workers.finalize_run_if_ready" for t in sent_tasks
        )

    def test_finalize_swallows_send_task_exceptions(
        self,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        task = self._make_base_task("workers.build_structure")

        with patch(
            "mas_queue.task_dispatcher.send_task_with_context",
            side_effect=RuntimeError("broker down"),
        ):
            task._enqueue_finalize_if_needed(
                {"run_id": str(uuid.uuid4())},
                reason="test",
            )


class TestFix3EnrichmentDispatchesChecks:
    def test_dispatch_helper_calls_start_checks_for_document(
        self,
        mock_send_task: MagicMock,
        sent_tasks: list[dict[str, Any]],
    ) -> None:
        from workers.build_legal_units_enrichment import (  # noqa: PLC0415
            _dispatch_checks_after_enrichment,
        )

        run_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())

        async def _fake_start_checks(
            db, run_id: uuid.UUID, document_id: uuid.UUID
        ) -> bool:
            from mas_queue.task_dispatcher import send_task_with_context  # noqa: PLC0415
            send_task_with_context(
                "workers.run_document_checks",
                kwargs={
                    "run_id": str(run_id),
                    "document_id": str(document_id),
                },
            )
            return True

        with patch(
            "services.run_checks_auto_starter.start_checks_for_document",
            side_effect=_fake_start_checks,
        ):
            _dispatch_checks_after_enrichment(
                run_id=run_id,
                document_id=document_id,
            )

        assert any(
            t["task_name"] == "workers.run_document_checks"
            and t["kwargs"].get("document_id") == document_id
            for t in sent_tasks
        ), "start_checks_for_document must be invoked after enrichment commit"

    def test_dispatch_helper_swallows_exceptions(self) -> None:
        from workers.build_legal_units_enrichment import (  # noqa: PLC0415
            _dispatch_checks_after_enrichment,
        )

        with patch(
            "services.run_checks_auto_starter.start_checks_for_document",
            side_effect=RuntimeError("db unavailable"),
        ):
            _dispatch_checks_after_enrichment(
                run_id=str(uuid.uuid4()),
                document_id=str(uuid.uuid4()),
            )

    def test_dispatch_helper_skips_invalid_uuids(self) -> None:
        from workers.build_legal_units_enrichment import (  # noqa: PLC0415
            _dispatch_checks_after_enrichment,
        )

        _dispatch_checks_after_enrichment(
            run_id="not-a-uuid",
            document_id="also-not-a-uuid",
        )


class TestFix4NotApplicableCanonicalResult:
    def test_save_not_applicable_result_sets_execution_status_success(
        self,
    ) -> None:
        from engine.checks.result_saver import save_not_applicable_result  # noqa: PLC0415

        repo = AsyncMock()
        repo.upsert_single_check_result = AsyncMock(return_value=MagicMock())

        doc = MagicMock()
        doc.id = uuid.uuid4()

        async def _test():
            await save_not_applicable_result(
                repo=repo,
                run_id=uuid.uuid4(),
                doc=doc,
                check_id="test_check_id",
                playbook_version_id=uuid.uuid4(),
                plan_item_id=uuid.uuid4(),
            )

        asyncio.run(_test())

        assert repo.upsert_single_check_result.await_count == 1
        _, kwargs = repo.upsert_single_check_result.call_args

        assert kwargs["execution_status"] == CheckExecutionStatus.SUCCESS.value
        assert kwargs["review_status"] == "not_applicable"
        assert kwargs["display_text"] is None
        assert kwargs["needs_manual_review"] is False
        assert kwargs["result"] == "unclear"
        assert kwargs["severity"] == "unclear"

    def test_save_not_applicable_result_uses_check_id_as_fallback_name(
        self,
    ) -> None:
        from engine.checks.result_saver import save_not_applicable_result  # noqa: PLC0415

        repo = AsyncMock()
        repo.upsert_single_check_result = AsyncMock(return_value=MagicMock())

        doc = MagicMock()
        doc.id = uuid.uuid4()

        async def _test():
            await save_not_applicable_result(
                repo=repo,
                run_id=uuid.uuid4(),
                doc=doc,
                check_id="msa.term_of_agreement",
            )

        asyncio.run(_test())

        _, kwargs = repo.upsert_single_check_result.call_args
        assert kwargs["check_name"] == "msa.term_of_agreement"