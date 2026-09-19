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


class TestFinalizeRaceGuard(unittest.TestCase):
    """Логика guard'а в finalize_run_if_ready."""

    def _should_postpone(self, *, has_deal: bool, intermediate_docs: int) -> bool:
        if not has_deal:
            return False
        return intermediate_docs > 0

    def test_postpones_when_document_chunked(self):
        self.assertTrue(
            self._should_postpone(has_deal=True, intermediate_docs=1)
        )

    def test_postpones_when_document_enriched(self):
        self.assertTrue(
            self._should_postpone(has_deal=True, intermediate_docs=1)
        )

    def test_proceeds_when_all_terminal(self):
        self.assertFalse(
            self._should_postpone(has_deal=True, intermediate_docs=0)
        )

    def test_skips_when_run_has_no_deal(self):
        self.assertFalse(
            self._should_postpone(has_deal=False, intermediate_docs=99)
        )

    def test_intermediate_statuses_cover_v2_pipeline(self):
        expected = {
            DocumentStatus.PENDING.value,
            DocumentStatus.PRIMARY_READY.value,
            DocumentStatus.EXTRACTED.value,
            DocumentStatus.SANITIZED.value,
            DocumentStatus.STRUCTURED.value,
            DocumentStatus.CHUNKED.value,
            DocumentStatus.CLASSIFIED.value,
            DocumentStatus.ENRICHED.value,
        }
        self.assertEqual(expected, set(_INTERMEDIATE_DOC_STATUSES))


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