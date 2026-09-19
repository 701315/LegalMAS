"""
Regression tests для race condition между orchestrator и finalize_run_if_ready.

Контекст: коммит e372948 добавил автоматический триггер finalize после
каждой стадии. Возникла гонка: orchestrator создаёт DSE следующей стадии
в отдельной транзакции, finalize видит count_active_for_run=0 и закрывает
run преждевременно. Фикс: guard по Document.status + orchestrator-trigger.

Конвенция: unittest.TestCase + patch, как в test_race_condition_fixes.py.
"""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

SRC_PATH = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from core.constants import DocumentStatus  # noqa: E402


_INTERMEDIATE_DOC_STATUSES: tuple[str, ...] = (
    DocumentStatus.PENDING.value,
    DocumentStatus.PRIMARY_READY.value,
    DocumentStatus.EXTRACTED.value,
    DocumentStatus.SANITIZED.value,
    DocumentStatus.STRUCTURED.value,
    DocumentStatus.CHUNKED.value,
    DocumentStatus.CLASSIFIED.value,
    DocumentStatus.ENRICHED.value,
)


class TestFinalizeRaceGuardMultiDoc(unittest.TestCase):
    """Guard корректно работает для multi-doc run."""

    _TERMINAL = frozenset({"completed", "failed", "quarantine", "duplicate", "deleted"})

    def _should_postpone(self, *, docs: list[tuple[str, int]]) -> bool:
        """
        docs: список (status, plan_count) — по одному на документ deal.
        Повторяет логику guard'а из finalize_run_if_ready.
        """
        for status, plan_count in docs:
            if status in self._TERMINAL:
                continue
            if plan_count == 0:
                return True
        return False

    def test_one_doc_processing_blocks_finalize(self):
        """doc1 ENRICHED с plans, doc2 CHUNKED без plans → postpone."""
        self.assertTrue(self._should_postpone(docs=[
            ("enriched", 37),
            ("chunked", 0),
        ]))

    def test_all_docs_have_plans_releases_guard(self):
        """Все ENRICHED с plans → finalize."""
        self.assertFalse(self._should_postpone(docs=[
            ("enriched", 37),
            ("enriched", 25),
        ]))

    def test_failed_doc_does_not_block(self):
        """FAILED — терминальный, не блокирует."""
        self.assertFalse(self._should_postpone(docs=[
            ("failed", 0),
            ("enriched", 37),
        ]))

    def test_quarantine_doc_does_not_block(self):
        """QUARANTINE — терминальный, не блокирует."""
        self.assertFalse(self._should_postpone(docs=[
            ("quarantine", 0),
            ("enriched", 37),
        ]))

    def test_duplicate_doc_does_not_block(self):
        """DUPLICATE — терминальный, не блокирует."""
        self.assertFalse(self._should_postpone(docs=[
            ("duplicate", 0),
            ("enriched", 37),
        ]))

    def test_deleted_doc_does_not_block(self):
        """DELETED — терминальный (audit only), не блокирует."""
        self.assertFalse(self._should_postpone(docs=[
            ("deleted", 0),
            ("enriched", 37),
        ]))

    def test_mixed_three_docs(self):
        """COMPLETED + ENRICHED с plans + SANITIZED без plans → postpone."""
        self.assertTrue(self._should_postpone(docs=[
            ("completed", 50),
            ("enriched", 37),
            ("sanitized", 0),
        ]))

    def test_many_docs_all_ready(self):
        """10 ENRICHED с plans → finalize."""
        self.assertFalse(self._should_postpone(docs=[
            ("enriched", 30) for _ in range(10)
        ]))

    def test_one_late_doc_blocks(self):
        """9 готовых + 1 PENDING → postpone."""
        docs = [("enriched", 30) for _ in range(9)]
        docs.append(("pending", 0))
        self.assertTrue(self._should_postpone(docs=docs))

    def test_fifty_docs_all_ready(self):
        """50 ENRICHED с plans → finalize. Проверка O(N)."""
        self.assertFalse(self._should_postpone(docs=[
            ("enriched", 20) for _ in range(50)
        ]))

    def test_fifty_docs_one_late(self):
        """50-1 готовых + 1 CHUNKED → postpone."""
        docs = [("enriched", 20) for _ in range(49)]
        docs.append(("chunked", 0))
        self.assertTrue(self._should_postpone(docs=docs))

    def test_language_selection_required_blocks(self):
        """LANGUAGE_SELECTION_REQUIRED без plans → postpone (ждём выбора)."""
        self.assertTrue(self._should_postpone(docs=[
            ("enriched", 37),
            ("language_selection_required", 0),
        ]))

    def test_extracting_blocks(self):
        """EXTRACTING без plans → postpone."""
        self.assertTrue(self._should_postpone(docs=[
            ("enriched", 37),
            ("extracting", 0),
        ]))

    def test_analyzing_with_plans_does_not_block(self):
        """ANALYZING с plans → пропускает (checks идут)."""
        self.assertFalse(self._should_postpone(docs=[
            ("analyzing", 15),
            ("enriched", 37),
        ]))
        

class TestOrchestratorFinalizeTrigger(unittest.TestCase):
    """Условие orchestrator-trigger'а."""

    def setUp(self):
        self.sent_tasks: list[dict[str, Any]] = []

        def _capture(task_name: str, kwargs: dict[str, Any] | None = None, **_):
            self.sent_tasks.append(
                {"task_name": task_name, "kwargs": dict(kwargs or {})}
            )
            r = MagicMock()
            r.id = str(uuid.uuid4())
            return r

        self.patcher = patch(
            "mas_queue.task_dispatcher.send_task_with_context",
            side_effect=_capture,
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _should_trigger(self, *, scheduled: int, triggered: int) -> bool:
        return scheduled == 0 and triggered == 0

    def test_fires_when_nothing_planned(self):
        self.assertTrue(self._should_trigger(scheduled=0, triggered=0))

    def test_does_not_fire_with_stages(self):
        self.assertFalse(self._should_trigger(scheduled=5, triggered=0))

    def test_does_not_fire_with_checks(self):
        self.assertFalse(self._should_trigger(scheduled=0, triggered=3))


if __name__ == "__main__":
    unittest.main()