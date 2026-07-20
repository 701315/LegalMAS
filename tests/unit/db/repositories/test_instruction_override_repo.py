from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.instruction_override_repo import InstructionOverrideRepository


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


        