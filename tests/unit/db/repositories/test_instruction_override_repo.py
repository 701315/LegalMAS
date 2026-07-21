# tests/unit/db/repositories/test_instruction_override_repo.py

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.instruction_override_repo import (
    InstructionOverrideRepository,
    InvalidLifecycleTransitionError,
    TenantOwnershipError,
)
from db.models.instruction_override import InstructionOverride


def _make_override(
    *,
    override_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    override_scope: str = "deal",
    status: str = "draft",
    instruction_version_id: uuid.UUID | None = None,
    is_stale: bool = False,
) -> MagicMock:
    override = MagicMock(spec=InstructionOverride)
    override.id = override_id or uuid.uuid4()
    override.tenant_id = tenant_id or uuid.uuid4()
    override.deal_id = deal_id
    override.override_scope = override_scope
    override.status = status
    override.instruction_version_id = instruction_version_id or uuid.uuid4()
    override.is_stale = is_stale
    override.base_content_hash = "abc123"
    override.patch_ops = []
    override.change_summary = None
    override.created_by = None
    return override


def _make_execute_result(*, scalar=None, scalars_all=None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    scalars_obj = MagicMock()
    scalars_obj.all.return_value = scalars_all or []
    result.scalars.return_value = scalars_obj
    return result


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestInstructionOverrideRepository:

    async def test_mark_stale_for_instruction_version_returns_rowcount(
        self,
        mock_session: MagicMock,
    ) -> None:
        execute_result = MagicMock()
        execute_result.rowcount = 4
        mock_session.execute.return_value = execute_result

        repo = InstructionOverrideRepository(mock_session)
        affected = await repo.mark_stale_for_instruction_version(uuid.uuid4())

        assert affected == 4
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()

    async def test_mark_stale_for_instruction_version_zero_when_none(
        self,
        mock_session: MagicMock,
    ) -> None:
        execute_result = MagicMock()
        execute_result.rowcount = 0
        mock_session.execute.return_value = execute_result

        repo = InstructionOverrideRepository(mock_session)
        affected = await repo.mark_stale_for_instruction_version(uuid.uuid4())

        assert affected == 0

    async def test_assert_tenant_owns_raises_for_wrong_tenant(
        self,
        mock_session: MagicMock,
    ) -> None:
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        override = _make_override(tenant_id=tenant_id, override_scope="deal")
        mock_session.execute.return_value = _make_execute_result(scalar=override)

        repo = InstructionOverrideRepository(mock_session)

        with pytest.raises(TenantOwnershipError):
            await repo.assert_tenant_owns(override.id, other_tenant_id)

    async def test_assert_tenant_owns_raises_for_missing_override(
        self,
        mock_session: MagicMock,
    ) -> None:
        mock_session.execute.return_value = _make_execute_result(scalar=None)

        repo = InstructionOverrideRepository(mock_session)

        with pytest.raises(TenantOwnershipError):
            await repo.assert_tenant_owns(uuid.uuid4(), uuid.uuid4())

    async def test_assert_tenant_owns_succeeds_for_correct_tenant(
        self,
        mock_session: MagicMock,
    ) -> None:
        tenant_id = uuid.uuid4()
        override = _make_override(tenant_id=tenant_id)
        mock_session.execute.return_value = _make_execute_result(scalar=override)

        repo = InstructionOverrideRepository(mock_session)
        result = await repo.assert_tenant_owns(override.id, tenant_id)

        assert result is override

    async def test_transition_status_raises_for_wrong_current_status(
        self,
        mock_session: MagicMock,
    ) -> None:
        tenant_id = uuid.uuid4()
        # Override is already 'active', not 'draft'
        override = _make_override(tenant_id=tenant_id, status="active")
        mock_session.execute.return_value = _make_execute_result(scalar=override)

        repo = InstructionOverrideRepository(mock_session)

        with pytest.raises(InvalidLifecycleTransitionError):
            await repo.transition_status(
                override.id,
                from_status="draft",
                to_status="active",
                tenant_id=tenant_id,
            )

    async def test_list_for_tenant_scope_returns_tenant_overrides(
        self,
        mock_session: MagicMock,
    ) -> None:
        tenant_id = uuid.uuid4()
        overrides = [
            _make_override(tenant_id=tenant_id, override_scope="tenant"),
            _make_override(tenant_id=tenant_id, override_scope="tenant"),
        ]
        mock_session.execute.return_value = _make_execute_result(scalars_all=overrides)

        repo = InstructionOverrideRepository(mock_session)
        result = await repo.list_for_tenant_scope(tenant_id)

        assert result == overrides
        mock_session.execute.assert_awaited_once()

    async def test_get_active_tenant_override_returns_none_when_missing(
        self,
        mock_session: MagicMock,
    ) -> None:
        mock_session.execute.return_value = _make_execute_result(scalar=None)

        repo = InstructionOverrideRepository(mock_session)
        result = await repo.get_active_tenant_override(uuid.uuid4(), uuid.uuid4())

        assert result is None

        