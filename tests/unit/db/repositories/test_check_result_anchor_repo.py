"""Unit tests: CheckResultAnchorRepository (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from db.models.check_result_anchor import CheckResultAnchor
from db.repositories.check_result_anchor_repo import (
    CheckResultAnchorRepository,
)


# pytest-asyncio STRICT mode: mark every async test in this module.
pytestmark = pytest.mark.asyncio


def _anchor(**overrides) -> CheckAnchor:
    defaults: dict = {
        "anchor_method": CheckAnchorMethod.CLAUSE_ONLY,
        "anchor_confidence": 0.5,
    }
    defaults.update(overrides)
    return CheckAnchor(**defaults)


def _orm_anchor(*, cr_id: uuid.UUID, anchor_id: uuid.UUID | None = None) -> CheckResultAnchor:
    return CheckResultAnchor(
        id=anchor_id or uuid.uuid4(),
        check_result_id=cr_id,
        anchor_method="clause_only",
        anchor_confidence=0.5,
        is_primary=False,
        layout_element_ids=[],
        anchor_validation_passed=False,
        anchor_diagnostics={},
    )


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock(spec=AsyncSession)
    s.add = MagicMock()  # session.add is synchronous on real AsyncSession
    return s


# ── create_many ───────────────────────────────────────────────────────────


async def test_create_many_empty_input_short_circuits(session: AsyncMock) -> None:
    repo = CheckResultAnchorRepository(session)
    result = await repo.create_many(
        check_result_id=uuid.uuid4(),
        anchors=[],
    )
    assert result == []
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


async def test_create_many_adds_rows_and_flushes(session: AsyncMock) -> None:
    repo = CheckResultAnchorRepository(session)
    cr_id = uuid.uuid4()

    created = await repo.create_many(
        check_result_id=cr_id,
        anchors=[_anchor(), _anchor()],
    )

    assert len(created) == 2
    assert all(isinstance(row, CheckResultAnchor) for row in created)
    assert session.add.call_count == 2
    session.flush.assert_awaited_once()
    for row in created:
        assert row.check_result_id == cr_id
        assert row.is_primary is False


async def test_create_many_maps_all_fields(session: AsyncMock) -> None:
    repo = CheckResultAnchorRepository(session)
    cr_id = uuid.uuid4()

    src = CheckAnchor(
        clause_uid="main_contract:7.3.2",
        clause_ref="п. 7.3.2",
        quoted_text="Sample text",
        span_start=10,
        span_end=20,
        source_content_hash="a" * 64,
        page=4,
        layout_element_ids=["ru:node:4:0010"],
        bbox_union=[1.0, 2.0, 3.0, 4.0],
        segment_id="main_contract",
        anchor_method=CheckAnchorMethod.EXACT_SPAN,
        anchor_confidence=1.0,
        anchor_validation_passed=True,
        anchor_diagnostics={"ratio": 1.0},
    )

    (row,) = await repo.create_many(check_result_id=cr_id, anchors=[src])

    assert row.check_result_id == cr_id
    assert row.clause_uid == "main_contract:7.3.2"
    assert row.clause_ref == "п. 7.3.2"
    assert row.quoted_text == "Sample text"
    assert row.span_start == 10
    assert row.span_end == 20
    assert row.source_content_hash == "a" * 64
    assert row.page == 4
    assert row.layout_element_ids == ["ru:node:4:0010"]
    assert row.bbox_union == [1.0, 2.0, 3.0, 4.0]
    assert row.segment_id == "main_contract"
    assert row.anchor_method == "exact_span"
    assert row.anchor_confidence == 1.0
    assert row.anchor_validation_passed is True
    assert row.anchor_diagnostics == {"ratio": 1.0}
    assert row.is_primary is False


# ── list_for_check_result ─────────────────────────────────────────────────


async def test_list_for_check_result_returns_rows(session: AsyncMock) -> None:
    cr_id = uuid.uuid4()
    rows = [MagicMock(), MagicMock()]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.list_for_check_result(check_result_id=cr_id)

    assert got == rows
    session.execute.assert_awaited_once()


# ── get_primary ───────────────────────────────────────────────────────────


async def test_get_primary_returns_none_when_absent(session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.get_primary(check_result_id=uuid.uuid4())

    assert got is None


async def test_get_primary_returns_row(session: AsyncMock) -> None:
    row = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.get_primary(check_result_id=uuid.uuid4())

    assert got is row


# ── set_primary ───────────────────────────────────────────────────────────


async def test_set_primary_unknown_anchor_returns_none(session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.set_primary(
        check_result_id=uuid.uuid4(),
        anchor_id=uuid.uuid4(),
    )

    assert got is None


async def test_set_primary_sets_flag_and_clears_others(session: AsyncMock) -> None:
    cr_id = uuid.uuid4()
    anchor_id = uuid.uuid4()
    target = _orm_anchor(cr_id=cr_id, anchor_id=anchor_id)

    # 1-й execute — SELECT target, 2-й — UPDATE остальных
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = target
    update_result = MagicMock()
    session.execute = AsyncMock(side_effect=[lookup_result, update_result])

    repo = CheckResultAnchorRepository(session)
    got = await repo.set_primary(check_result_id=cr_id, anchor_id=anchor_id)

    assert got is target
    assert target.is_primary is True
    assert session.execute.await_count == 2
    session.flush.assert_awaited_once()


# ── clear_primary ─────────────────────────────────────────────────────────


async def test_clear_primary_returns_rowcount(session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.rowcount = 1
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.clear_primary(check_result_id=uuid.uuid4())

    assert got == 1
    session.flush.assert_awaited_once()


# ── delete_for_check_result ───────────────────────────────────────────────


async def test_delete_for_check_result_returns_rowcount(session: AsyncMock) -> None:
    mock_result = MagicMock()
    mock_result.rowcount = 3
    session.execute = AsyncMock(return_value=mock_result)

    repo = CheckResultAnchorRepository(session)
    got = await repo.delete_for_check_result(check_result_id=uuid.uuid4())

    assert got == 3
    session.flush.assert_awaited_once()


# ── replace_for_check_result ──────────────────────────────────────────────


async def test_replace_deletes_then_creates(session: AsyncMock) -> None:
    cr_id = uuid.uuid4()
    delete_result = MagicMock()
    delete_result.rowcount = 2
    session.execute = AsyncMock(return_value=delete_result)

    repo = CheckResultAnchorRepository(session)
    created = await repo.replace_for_check_result(
        check_result_id=cr_id,
        anchors=[_anchor()],
    )

    assert len(created) == 1
    assert created[0].check_result_id == cr_id
    assert session.add.call_count == 1

    