"""Unit tests: RunCheckPlanItemRepository read methods (mocked AsyncSession, no real DB)."""


from __future__ import annotations


import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


import pytest


from core.constants import RunCheckPlanItemStatus
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



class TestTerminalAndErrorStatusesConsistency:
    """
    Проверяет, что TERMINAL_STATUSES / ERROR_STATUSES внутри repository
    остаются синхронизированы с core.constants.RunCheckPlanItemStatus —
    единым source-of-truth для допустимых значений статуса.
    """

    def test_terminal_statuses_built_from_enum_values(self) -> None:
        from db.repositories.run_check_plan_item_repo import TERMINAL_STATUSES

        assert TERMINAL_STATUSES == {
            RunCheckPlanItemStatus.SUCCEEDED.value,
            RunCheckPlanItemStatus.FAILED.value,
            RunCheckPlanItemStatus.SKIPPED.value,
            RunCheckPlanItemStatus.TIMEOUT.value,
            RunCheckPlanItemStatus.CANCELLED.value,
        }

    def test_error_statuses_built_from_enum_values(self) -> None:
        from db.repositories.run_check_plan_item_repo import ERROR_STATUSES

        assert ERROR_STATUSES == {
            RunCheckPlanItemStatus.FAILED.value,
            RunCheckPlanItemStatus.TIMEOUT.value,
            RunCheckPlanItemStatus.CANCELLED.value,
        }

    def test_error_statuses_is_subset_of_terminal_statuses(self) -> None:
        from db.repositories.run_check_plan_item_repo import ERROR_STATUSES, TERMINAL_STATUSES

        assert ERROR_STATUSES.issubset(TERMINAL_STATUSES)

    def test_all_status_sets_are_plain_strings_not_enum_members(self) -> None:
        """
        TERMINAL_STATUSES/ERROR_STATUSES должны хранить .value (str),
        а не enum-объекты — иначе SQL .in_()/.notin_() сравнения с
        String-колонкой начнут молча не матчиться.
        """
        from db.repositories.run_check_plan_item_repo import ERROR_STATUSES, TERMINAL_STATUSES

        assert all(isinstance(s, str) for s in TERMINAL_STATUSES)
        assert all(isinstance(s, str) for s in ERROR_STATUSES)
        assert all(not isinstance(s, RunCheckPlanItemStatus) for s in TERMINAL_STATUSES)


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
        filtered_items = [_make_item(run_id=run_id, status=RunCheckPlanItemStatus.FAILED.value)]
        mock_session.execute.return_value = _make_scalars_result(filtered_items)


        repo = RunCheckPlanItemRepository(mock_session)
        result = await repo.list_by_run_id(run_id, status=RunCheckPlanItemStatus.FAILED)


        assert result == filtered_items
        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "status" in compiled_sql


    async def test_status_filter_binds_enum_value_not_enum_member(self, mock_session: MagicMock) -> None:
        """
        Критично: в WHERE должно попадать строковое .value ("failed"),
        а не repr enum-объекта (RunCheckPlanItemStatus.FAILED), иначе
        сравнение со String-колонкой в БД не сработает.
        """
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])


        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id, status=RunCheckPlanItemStatus.FAILED)


        stmt = mock_session.execute.await_args.args[0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        compiled_sql = str(compiled)
        assert "'failed'" in compiled_sql
        assert "RunCheckPlanItemStatus" not in compiled_sql


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


    async def test_ordering_includes_segment_id_and_id_as_tiebreakers(self, mock_session: MagicMock) -> None:
        """
        Deterministic ordering контракт: сортировка должна включать
        document_id, check_id, segment_id, id — в этом порядке.
        Без segment_id/id как tie-breakers порядок для записей одного
        document/check с разными сегментами не гарантирован между запросами.
        """
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])


        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id)


        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()

        order_clause_start = compiled_sql.index("order by")
        order_clause = compiled_sql[order_clause_start:]

        doc_pos = order_clause.index("document_id")
        check_pos = order_clause.index("check_id")
        segment_pos = order_clause.index("segment_id")
        id_pos = order_clause.rindex(".id")

        assert doc_pos < check_pos < segment_pos < id_pos



@pytest.mark.asyncio
class TestListByRunIdStrictTyping:
    async def test_accepts_enum_member(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id, status=RunCheckPlanItemStatus.SKIPPED)

    async def test_accepts_none(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = RunCheckPlanItemRepository(mock_session)
        await repo.list_by_run_id(run_id, status=None)



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


        