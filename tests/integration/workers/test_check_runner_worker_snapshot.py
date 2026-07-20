"""
Integration test: run_deal_checks вызывает freeze_instruction_snapshot
с doc_types, собранными из реальных (non-duplicate) документов сделки,
а не из плана checks.
"""

from __future__ import annotations
import pytest
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from core.constants import RunStatus
from workers import check_runner_worker


def _make_run_obj(run_id: uuid.UUID, playbook_version_id: uuid.UUID) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.status = RunStatus.PENDING.value
    run.playbook_version_id = playbook_version_id
    run.checks_mode = "global_and_doc_type"
    run.checks_scope = None
    run.total_checks = 0
    run.completed_checks = 0
    run.has_errors = False
    return run


def _make_doc(doc_type: str | None) -> MagicMock:
    doc = MagicMock()
    doc.doc_type = doc_type
    return doc


def _make_mock_session(run_obj: MagicMock) -> MagicMock:
    """
    RunRepository.update_status/get_by_id/mark_run_failed выполняют реальные
    UPDATE/SELECT через session.execute(stmt) и читают .scalar_one_or_none().
    Мы не мокаем RunRepository целиком (только его отдельные методы,
    релевантные сценарию), поэтому session.execute должен быть валидным
    AsyncMock, иначе любой не замоканный метод репозитория, вызванный
    в ходе реального выполнения _run(), уронит тест TypeError'ом.
    """
    session = MagicMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = run_obj
    session.execute = AsyncMock(return_value=exec_result)
    session.flush = AsyncMock()
    return session


def test_freeze_instruction_snapshot_called_with_doc_types_from_deal_documents():
    """
    freeze_instruction_snapshot должен вызываться с уникальными doc_type
    из реальных документов сделки (RunnerRepository.get_non_duplicate_docs),
    а не из execution plan.
    """
    run_id = str(uuid.uuid4())
    deal_id = str(uuid.uuid4())
    run_uuid = uuid.UUID(run_id)
    playbook_version_id = uuid.uuid4()

    run_obj = _make_run_obj(run_uuid, playbook_version_id)
    docs = [_make_doc("nda"), _make_doc("spa"), _make_doc(None), _make_doc("nda")]

    mock_uow_session = _make_mock_session(run_obj)
    mock_uow = MagicMock()
    mock_uow.session = mock_uow_session

    @asynccontextmanager
    async def _fake_db_uow():
        yield mock_uow

    run_snap = MagicMock()
    run_snap.status = RunStatus.PENDING.value
    run_snap.playbook_version_id = playbook_version_id
    run_snap.checks_mode = "global_and_doc_type"
    run_snap.checks_scope = None
    run_snap.id = run_uuid

    fake_plan = {"pairs": [], "processed_docs": 0, "total_checks": 0, "errors": 0}

    mock_playbook = MagicMock()
    mock_pb_version = MagicMock()
    mock_runner_instance = MagicMock()
    mock_runner_instance.plan_checks_for_run = AsyncMock(return_value=fake_plan)

    with patch.object(check_runner_worker, "db_uow", _fake_db_uow), \
         patch.object(
             check_runner_worker.RunRepository, "get", new=AsyncMock(return_value=run_obj)
         ), \
         patch.object(
             check_runner_worker.RunRepository,
             "try_start_run",
             new=AsyncMock(return_value=True),
         ), \
         patch.object(check_runner_worker, "snapshot_run", return_value=run_snap), \
         patch.object(
             check_runner_worker.PlaybookRepository,
             "get_by_id",
             new=AsyncMock(return_value=mock_pb_version),
         ), \
         patch.object(
             check_runner_worker,
             "load_playbook_from_version",
             return_value=mock_playbook,
         ), \
         patch.object(
             check_runner_worker.RunnerRepository,
             "get_non_duplicate_docs",
             new=AsyncMock(return_value=docs),
         ), \
         patch.object(
             check_runner_worker,
             "freeze_instruction_snapshot",
             new=AsyncMock(return_value={"nda": "v1", "spa": "v2"}),
         ) as mock_freeze, \
         patch.object(
             check_runner_worker, "build_doc_type_loader", return_value=MagicMock()
         ), \
         patch.object(
             check_runner_worker, "CheckRunner", return_value=mock_runner_instance
         ):

        check_runner_worker.run_deal_checks(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=None,
            job_id=None,
        )

    mock_freeze.assert_awaited_once()
    _, call_kwargs = mock_freeze.call_args
    assert call_kwargs["run_uuid"] == run_uuid
    assert call_kwargs["doc_types"] == {"nda", "spa"}


def test_freeze_instruction_snapshot_failure_marks_run_failed_and_aborts():
    """
    Если freeze_instruction_snapshot падает с исключением, scheduling не должен
    продолжаться. Run помечается failed, а worker поднимает исключение.

    Новый strict snapshot contract:
    - никакого fallback на FilesystemInstructionProvider для новых Run;
    - planning/disaptch без frozen snapshot запрещены.
    """
    run_id = str(uuid.uuid4())
    deal_id = str(uuid.uuid4())
    run_uuid = uuid.UUID(run_id)
    playbook_version_id = uuid.uuid4()

    run_obj = _make_run_obj(run_uuid, playbook_version_id)
    docs = [_make_doc("nda")]

    mock_uow_session = _make_mock_session(run_obj)
    mock_uow = MagicMock()
    mock_uow.session = mock_uow_session

    @asynccontextmanager
    async def _fake_db_uow():
        yield mock_uow

    run_snap = MagicMock()
    run_snap.status = RunStatus.PENDING.value
    run_snap.playbook_version_id = playbook_version_id
    run_snap.checks_mode = "global_and_doc_type"
    run_snap.checks_scope = None
    run_snap.id = run_uuid

    fake_plan = {"pairs": [], "processed_docs": 0, "total_checks": 0, "errors": 0}
    mock_runner_instance = MagicMock()
    mock_runner_instance.plan_checks_for_run = AsyncMock(return_value=fake_plan)

    mark_run_failed_mock = AsyncMock(return_value=MagicMock())

    with patch.object(check_runner_worker, "db_uow", _fake_db_uow), \
         patch.object(
             check_runner_worker.RunRepository, "get", new=AsyncMock(return_value=run_obj)
         ), \
         patch.object(
             check_runner_worker.RunRepository,
             "try_start_run",
             new=AsyncMock(return_value=True),
         ), \
         patch.object(
             check_runner_worker.RunRepository,
             "mark_run_failed",
             new=mark_run_failed_mock,
         ), \
         patch.object(check_runner_worker, "snapshot_run", return_value=run_snap), \
         patch.object(
             check_runner_worker.PlaybookRepository,
             "get_by_id",
             new=AsyncMock(return_value=MagicMock()),
         ), \
         patch.object(
             check_runner_worker, "load_playbook_from_version", return_value=MagicMock()
         ), \
         patch.object(
             check_runner_worker.RunnerRepository,
             "get_non_duplicate_docs",
             new=AsyncMock(return_value=docs),
         ), \
         patch.object(
             check_runner_worker,
             "freeze_instruction_snapshot",
             new=AsyncMock(side_effect=RuntimeError("boom")),
         ), \
         patch.object(
             check_runner_worker, "build_doc_type_loader", return_value=MagicMock()
         ) as build_loader_mock, \
         patch.object(
             check_runner_worker, "CheckRunner", return_value=mock_runner_instance
         ) as check_runner_cls_mock:

        with pytest.raises(RuntimeError, match="Strict instruction snapshot freeze failed"):
            check_runner_worker.run_deal_checks(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=None,
                job_id=None,
            )

    mark_run_failed_mock.assert_awaited_once()
    build_loader_mock.assert_not_called()
    check_runner_cls_mock.assert_not_called()


    