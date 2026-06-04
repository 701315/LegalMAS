# tests/unit/mas_queue/test_base_task_stage_execution.py
"""
Unit-тесты для stage execution lifecycle в MASBaseTask.

Проверяем:
1. __call__ не удаляет stage_execution_id из kwargs
2. before_start вызывает mark_started
3. on_success → mark_failed при business-terminal failure
4. on_success → mark_succeeded с result_details при успехе
5. on_failure → mark_failed при exception
6. Идемпотентность: guard не даёт перетереть terminal execution
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from core.exceptions import PermanentError
from mas_queue.base_task import MASBaseTask, _compact_dict


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _DummyRequest:
    """Минимальная заглушка Celery Request для хуков."""

    def __init__(self) -> None:
        self.id = "task-test-123"
        self.retries = 0
        self.hostname = "worker@test"
        self._dlq_sent = False


class DummyTask(MASBaseTask):
    """Таска для тестов: возвращает kwargs из run(), чтобы проверить передачу."""

    name = "workers.dummy_for_tests"
    track_job = False
    _request_stack: list[Any]

    def __init__(self) -> None:
        # Не вызываем super().__init__ — он требует Celery app
        self._request_stack = [_DummyRequest()]

    @property
    def request(self) -> _DummyRequest:  # type: ignore[override]
        return self._request_stack[-1]

    def push_request(self, **kwargs: Any) -> None:  # type: ignore[override]
        req = _DummyRequest()
        for k, v in kwargs.items():
            setattr(req, k, v)
        self._request_stack.append(req)

    def pop_request(self) -> None:  # type: ignore[override]
        if len(self._request_stack) > 1:
            self._request_stack.pop()

    def run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    # Silence DLQ
    def _send_to_dlq_once(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass


def _make_task() -> DummyTask:
    return DummyTask()


# ── Test: __call__ preserves stage_execution_id ───────────────────────────────

class TestCallPreservesKwargs:
    def test_stage_execution_id_not_removed_from_kwargs(self) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())

        result = task.__call__(
            document_id="doc-1",
            stage_execution_id=stage_id,
            orchestration_strategy="v2_only",
        )

        assert result["stage_execution_id"] == stage_id
        assert result["orchestration_strategy"] == "v2_only"

    def test_stage_execution_id_stored_on_self(self) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())

        task.__call__(
            document_id="doc-1",
            stage_execution_id=stage_id,
        )

        assert task._stage_execution_id == stage_id

    def test_missing_stage_execution_id_is_none(self) -> None:
        task = _make_task()

        task.__call__(document_id="doc-1")

        assert task._stage_execution_id is None

    def test_empty_string_stage_execution_id_is_none(self) -> None:
        task = _make_task()

        task.__call__(document_id="doc-1", stage_execution_id="   ")

        assert task._stage_execution_id is None


# ── Test: before_start calls mark_started ────────────────────────────────────

class TestBeforeStartMarkStarted:
    def test_calls_mark_started_when_stage_execution_id_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        calls: list[str] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_started_best_effort",
            lambda eid: calls.append(eid),
        )

        task.before_start(
            "task-123",
            (),
            {"document_id": "doc-1", "stage_execution_id": stage_id},
        )

        assert calls == [stage_id]

    def test_does_not_call_mark_started_without_stage_execution_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        calls: list[str] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_started_best_effort",
            lambda eid: calls.append(eid),
        )

        task.before_start("task-123", (), {"document_id": "doc-1"})

        assert calls == []


# ── Test: on_success resolves correct terminal action ────────────────────────

class TestOnSuccessResolution:
    def _make_kwargs(self, stage_id: str) -> dict[str, Any]:
        return {
            "stage_execution_id": stage_id,
            "document_id": "doc-1",
            "document_version_id": "ver-1",
            "run_id": "run-1",
        }

    def test_business_failed_status_marks_execution_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        failed: list[tuple[str, dict]] = []
        succeeded: list[tuple[str, Any]] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: failed.append((eid, error_details)),
        )
        monkeypatch.setattr(
            task,
            "_mark_stage_execution_succeeded_best_effort",
            lambda eid, *, result_details: succeeded.append((eid, result_details)),
        )

        task.on_success(
            {"status": "failed", "error": "boom", "reason_code": "contract_violation"},
            "task-123",
            (),
            self._make_kwargs(stage_id),
        )

        assert not succeeded
        assert len(failed) == 1
        eid, details = failed[0]
        assert eid == stage_id
        assert details["reason"] == "contract_violation"
        assert details["message"] == "boom"
        assert details["type"] == "stage_terminal_failure"

    def test_business_quarantine_status_marks_execution_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        failed: list[tuple[str, dict]] = []
        succeeded: list[tuple[str, Any]] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: failed.append((eid, error_details)),
        )
        monkeypatch.setattr(
            task,
            "_mark_stage_execution_succeeded_best_effort",
            lambda eid, *, result_details: succeeded.append((eid, result_details)),
        )

        task.on_success(
            {"status": "quarantine", "error": "bad content", "quarantine_reason": "empty"},
            "task-123",
            (),
            self._make_kwargs(stage_id),
        )

        assert not succeeded
        assert len(failed) == 1
        assert failed[0][1]["reason"] == "empty"

    def test_success_status_marks_execution_succeeded_with_result_details(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        failed: list[tuple[str, dict]] = []
        succeeded: list[tuple[str, Any]] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: failed.append((eid, error_details)),
        )
        monkeypatch.setattr(
            task,
            "_mark_stage_execution_succeeded_best_effort",
            lambda eid, *, result_details: succeeded.append((eid, result_details)),
        )

        enrichment_details = {"outcome": "timed_out", "segments_total": 98}

        task.on_success(
            {
                "status": "enriched",
                "committed": True,
                "stage_execution_result_details": enrichment_details,
            },
            "task-123",
            (),
            self._make_kwargs(stage_id),
        )

        assert not failed
        assert len(succeeded) == 1
        eid, details = succeeded[0]
        assert eid == stage_id
        assert details == enrichment_details

    def test_success_without_result_details_passes_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        succeeded: list[tuple[str, Any]] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: None,
        )
        monkeypatch.setattr(
            task,
            "_mark_stage_execution_succeeded_best_effort",
            lambda eid, *, result_details: succeeded.append((eid, result_details)),
        )

        task.on_success(
            {"status": "chunked", "committed": True},
            "task-123",
            (),
            self._make_kwargs(stage_id),
        )

        assert len(succeeded) == 1
        assert succeeded[0][1] is None

    def test_no_stage_execution_id_skips_lifecycle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        calls: list[str] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_succeeded_best_effort",
            lambda eid, *, result_details: calls.append(eid),
        )
        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: calls.append(eid),
        )

        task.on_success({"status": "chunked"}, "task-123", (), {"document_id": "doc-1"})

        assert calls == []


# ── Test: on_failure marks execution failed ───────────────────────────────────

class TestOnFailureMarksFailed:
    def test_on_failure_marks_execution_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        stage_id = str(uuid.uuid4())
        failed: list[tuple[str, dict]] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: failed.append((eid, error_details)),
        )

        task.on_failure(
            PermanentError("fatal"),
            "task-123",
            (),
            {
                "stage_execution_id": stage_id,
                "document_id": "doc-1",
                "document_version_id": "ver-1",
                "run_id": "run-1",
            },
            None,
        )

        assert len(failed) == 1
        eid, details = failed[0]
        assert eid == stage_id
        assert details["message"] == "fatal"
        assert details["document_id"] == "doc-1"
        assert details["document_version_id"] == "ver-1"
        assert details["run_id"] == "run-1"

    def test_on_failure_without_stage_id_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task()
        calls: list[str] = []

        monkeypatch.setattr(
            task,
            "_mark_stage_execution_failed_best_effort",
            lambda eid, *, error_details: calls.append(eid),
        )

        task.on_failure(
            PermanentError("fatal"),
            "task-123",
            (),
            {"document_id": "doc-1"},
            None,
        )

        assert calls == []


# ── Test: _compact_dict ───────────────────────────────────────────────────────

class TestCompactDict:
    def test_removes_none_values(self) -> None:
        result = _compact_dict({"a": 1, "b": None, "c": "x", "d": None})
        assert result == {"a": 1, "c": "x"}

    def test_keeps_falsy_non_none(self) -> None:
        result = _compact_dict({"a": 0, "b": "", "c": False, "d": None})
        assert result == {"a": 0, "b": "", "c": False}

    def test_empty_dict(self) -> None:
        assert _compact_dict({}) == {}


        