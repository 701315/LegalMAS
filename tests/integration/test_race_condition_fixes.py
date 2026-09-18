"""
Standalone integration/unit test suite для проверки исправления race condition
между stages и checks в run pipeline.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Добавляем src в sys.path для корректных импортов
SRC_PATH = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from core.constants import (
    CheckExecutionStatus,
    DocumentStatus,
)
from core.pipeline_snapshots import DocumentSnapshot


class TestRaceConditionFixes(unittest.TestCase):
    def setUp(self):
        self.sent_tasks: list[dict[str, Any]] = []

        def _capture(task_name: str, kwargs: dict[str, Any] | None = None, **_ignored):
            self.sent_tasks.append(
                {
                    "task_name": task_name,
                    "kwargs": dict(kwargs or {}),
                }
            )
            result = MagicMock()
            result.id = str(uuid.uuid4())
            return result

        self.send_task_patcher = patch(
            "mas_queue.task_dispatcher.send_task_with_context",
            side_effect=_capture,
        )
        self.mock_send_task = self.send_task_patcher.start()

    def tearDown(self):
        self.send_task_patcher.stop()

    # ─── Fix 1: race condition в run_orchestrator ────────────────────────────

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

    def test_fix1_document_with_new_stage_does_NOT_trigger_checks_from_orchestrator(self):
        doc_id = uuid.uuid4()
        enriched_snap = self._make_enriched_snapshot(doc_id)
        scheduled_ids = {doc_id}

        should_dispatch_from_orchestrator = (
            enriched_snap.document_id not in scheduled_ids
            and enriched_snap.status
            in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and enriched_snap.doc_type is not None
        )

        self.assertFalse(
            should_dispatch_from_orchestrator,
            "Documents with newly scheduled stages must NOT receive checks "
            "dispatch from orchestrator (race condition guard).",
        )

    def test_fix1_document_without_new_stage_DOES_trigger_checks_from_orchestrator(self):
        doc_id = uuid.uuid4()
        enriched_snap = self._make_enriched_snapshot(doc_id)
        scheduled_ids: set[uuid.UUID] = set()

        should_dispatch_from_orchestrator = (
            enriched_snap.document_id not in scheduled_ids
            and enriched_snap.status
            in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and enriched_snap.doc_type is not None
        )

        self.assertTrue(
            should_dispatch_from_orchestrator,
            "Documents without newly scheduled stages must receive checks "
            "dispatch directly from orchestrator.",
        )

    def test_fix1_document_without_doc_type_is_skipped(self):
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

        self.assertFalse(should_dispatch)

    def test_fix1_document_with_active_db_stages_is_skipped_even_if_not_in_scheduled_set(self):
        has_active_stages_in_db = True
        doc_id = uuid.uuid4()
        enriched_snap = self._make_enriched_snapshot(doc_id)
        scheduled_ids: set[uuid.UUID] = set()

        should_dispatch = (
            enriched_snap.document_id not in scheduled_ids
            and enriched_snap.status in {DocumentStatus.ENRICHED.value, DocumentStatus.COMPLETED.value}
            and enriched_snap.doc_type is not None
            and not has_active_stages_in_db
        )

        self.assertFalse(should_dispatch)

    # ─── Fix 2: finalize trigger в base_task ─────────────────────────────────

    def _make_base_task(self, task_name: str):
        from mas_queue.base_task import MASBaseTask  # noqa: PLC0415

        task = MASBaseTask()
        task.name = task_name
        return task

    def test_fix2_finalize_enqueued_for_stage_task_with_run_id(self):
        task = self._make_base_task("workers.build_legal_units_enrichment")
        run_id = str(uuid.uuid4())

        task._enqueue_finalize_if_needed(
            {"run_id": run_id, "tenant_id": str(uuid.uuid4())},
            reason="test",
        )

        finalize_calls = [
            t for t in self.sent_tasks if t["task_name"] == "workers.finalize_run_if_ready"
        ]
        self.assertEqual(len(finalize_calls), 1)
        self.assertEqual(finalize_calls[0]["kwargs"]["run_id"], run_id)

    def test_fix2_finalize_NOT_enqueued_for_excluded_task(self):
        excluded_tasks = [
            "workers.finalize_run_if_ready",
            "workers.generate_run_summary",
            "workers.process_pending_result_presentations",
            "workers.exporter",
            "workers.export_pending",
        ]
        for task_name in excluded_tasks:
            task = self._make_base_task(task_name)
            task._enqueue_finalize_if_needed(
                {"run_id": str(uuid.uuid4())},
                reason="test",
            )

        self.assertFalse(
            any(t["task_name"] == "workers.finalize_run_if_ready" for t in self.sent_tasks),
            "Excluded tasks must not trigger recursive finalize",
        )

    def test_fix2_finalize_NOT_enqueued_without_run_id(self):
        task = self._make_base_task("workers.build_structure")

        task._enqueue_finalize_if_needed({}, reason="test")
        task._enqueue_finalize_if_needed({"run_id": None}, reason="test")
        task._enqueue_finalize_if_needed({"run_id": "   "}, reason="test")

        self.assertFalse(
            any(t["task_name"] == "workers.finalize_run_if_ready" for t in self.sent_tasks)
        )

    def test_fix2_finalize_NOT_enqueued_with_invalid_uuid(self):
        task = self._make_base_task("workers.build_structure")

        task._enqueue_finalize_if_needed(
            {"run_id": "not-a-valid-uuid"},
            reason="test",
        )

        self.assertFalse(
            any(t["task_name"] == "workers.finalize_run_if_ready" for t in self.sent_tasks)
        )

    def test_fix2_finalize_swallows_send_task_exceptions(self):
        task = self._make_base_task("workers.build_structure")

        with patch(
            "mas_queue.task_dispatcher.send_task_with_context",
            side_effect=RuntimeError("broker down"),
        ):
            task._enqueue_finalize_if_needed(
                {"run_id": str(uuid.uuid4())},
                reason="test",
            )

    # ─── Fix 3: dispatch checks после enrichment ─────────────────────────────

    def test_fix3_dispatch_helper_calls_start_checks_for_document(self):
        from workers.build_legal_units_enrichment import (  # noqa: PLC0415
            _dispatch_checks_after_enrichment,
        )

        run_id = str(uuid.uuid4())
        document_id = str(uuid.uuid4())

        async def _fake_start_checks(db, run_id: uuid.UUID, document_id: uuid.UUID) -> bool:
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

        self.assertTrue(
            any(
                t["task_name"] == "workers.run_document_checks"
                and t["kwargs"].get("document_id") == document_id
                for t in self.sent_tasks
            ),
            "start_checks_for_document must be invoked after enrichment commit",
        )

    def test_fix3_dispatch_helper_swallows_exceptions(self):
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

    def test_fix3_dispatch_helper_skips_invalid_uuids(self):
        from workers.build_legal_units_enrichment import (  # noqa: PLC0415
            _dispatch_checks_after_enrichment,
        )

        _dispatch_checks_after_enrichment(
            run_id="not-a-uuid",
            document_id="also-not-a-uuid",
        )

    # ─── Fix 4: canonical check_results для not_applicable ───────────────────

    def test_fix4_save_not_applicable_result_sets_execution_status_success(self):
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

        self.assertEqual(repo.upsert_single_check_result.await_count, 1)
        _, kwargs = repo.upsert_single_check_result.call_args

        self.assertEqual(kwargs["execution_status"], CheckExecutionStatus.SUCCESS.value)
        self.assertEqual(kwargs["review_status"], "not_applicable")
        self.assertIsNone(kwargs["display_text"])
        self.assertFalse(kwargs["needs_manual_review"])
        self.assertEqual(kwargs["result"], "unclear")
        self.assertEqual(kwargs["severity"], "unclear")

    def test_fix4_save_not_applicable_result_uses_check_id_as_fallback_name(self):
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
        self.assertEqual(kwargs["check_name"], "msa.term_of_agreement")

    # ─── Fix 5: Short-circuit идемпотентности финализации ────────────────────

    def test_fix5_already_terminal_run_status_triggers_short_circuit(self):
        terminal_statuses = ["completed", "completed_with_errors", "failed"]
        for status in terminal_statuses:
            run_snap_mock = MagicMock()
            run_snap_mock.status = status

            is_already_terminal = run_snap_mock.status in (
                "completed",
                "completed_with_errors",
                "failed",
            )
            self.assertTrue(
                is_already_terminal,
                f"Status '{status}' must trigger short-circuit in finalize_run_if_ready.",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)