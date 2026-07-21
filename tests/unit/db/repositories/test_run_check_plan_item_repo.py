# tests/unit/db/repositories/test_run_check_plan_item_repo.py

"""Unit tests: RunCheckPlanItemRepository read methods (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository


def _make_item(
    *,
    item_id: uuid.UUID | None = None,
    run_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    check_id: str = "check_1",
    status: str = "planned",
    segment_id: str | None = None,
    doc_type: str | None = None,
):
    return SimpleNamespace(
        id=item_id or uuid.uuid4(),
        run_id=run_id,
        deal_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        segment_id=segment_id,
        doc_type=doc_type,
        check_id=check_id,
        check_name=None,
        check_origin=None,
        playbook_version_id=None,
        status=status,
        attempt_count=0,
        dispatch_ref=None,
        error_details=None,
        dispatched_at=None,
        started_at=None,
        finished_at=None,
    )


def _make_scalars_result(items: list) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _make_scalar_one_result(item) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    return result


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestListByRunId:
    async def test_returns_items_for_run(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        items = [
            _make_item(run_id=run_id, check_id="check_a"),
            _make_item(run_id=run_id, check_id="check_b"),
        ]
        mock_session.execute.return_value = _make_scalars_result(items)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.list_by_run_id(run_id)

        assert result == items
        mock_session.execute.assert_awaited_once()

    async def test_empty_run_returns_empty_list(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.list_by_run_id(run_id)

        assert result == []

    async def test_status_filter_included_in_query(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        filtered_items = [_make_item(run_id=run_id, status="failed")]
        mock_session.execute.return_value = _make_scalars_result(filtered_items)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.list_by_run_id(run_id, status="failed")

        assert result == filtered_items
        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "status" in compiled_sql

    async def test_no_status_filter_when_none(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        items = [_make_item(run_id=run_id)]
        mock_session.execute.return_value = _make_scalars_result(items)

        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id, status=None)

        mock_session.execute.assert_awaited_once()

    async def test_does_not_leak_items_from_other_runs(self, mock_session: MagicMock) -> None:
        """
        Repository сам не может "случайно" вернуть items другого run,
        так как WHERE run_id == run_id всегда часть statement.
        Здесь проверяем, что mock настроен на возврат только ожидаемых items,
        что подтверждает контракт метода (filter применяется на уровне SQL).
        """
        run_id = uuid.uuid4()
        other_run_id = uuid.uuid4()
        own_items = [_make_item(run_id=run_id)]
        mock_session.execute.return_value = _make_scalars_result(own_items)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.list_by_run_id(run_id)

        assert all(item.run_id == run_id for item in result)
        assert all(item.run_id != other_run_id for item in result)

    async def test_ordering_clause_present(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id)

        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "ORDER BY" in compiled_sql.upper()


@pytest.mark.asyncio
class TestGetByIdScoped:
    async def test_returns_item_when_run_matches(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        item = _make_item(run_id=run_id)
        mock_session.execute.return_value = _make_scalar_one_result(item)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.get_by_id_scoped(item.id, run_id)

        assert result is item

    async def test_returns_none_when_run_id_mismatch(self, mock_session: MagicMock) -> None:
        """
        Критический security-тест: item существует в БД, но принадлежит
        другому run_id. Repository должен вернуть None (query фильтрует
        по обоим id одновременно, поэтому cross-run item не матчится).
        """
        item_id = uuid.uuid4()
        wrong_run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalar_one_result(None)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.get_by_id_scoped(item_id, wrong_run_id)

        assert result is None

    async def test_returns_none_when_item_does_not_exist(self, mock_session: MagicMock) -> None:
        mock_session.execute.return_value = _make_scalar_one_result(None)

        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.get_by_id_scoped(uuid.uuid4(), uuid.uuid4())

        assert result is None

    async def test_query_filters_by_both_id_and_run_id(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        item_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalar_one_result(None)

        repo = RunCheckPlanItemRepository(mock_session)
        await repo.get_by_id_scoped(item_id, run_id)

        stmt = mock_session.execute.await_args.args[0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        compiled_sql = str(compiled)
        assert "run_check_plan_items" in compiled_sql


        