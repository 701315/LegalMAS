"""
Unit tests for translation audit events — Sprint 6.4

Covers:
- All 8 translation audit action constants are defined in ALL_ACTIONS
- log_translation_event writes through AuditRepository with correct fields
- Actor role resolution (system vs user)
- Rejection of invalid audit action names
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.translation_audit import (
    ACTION_APPROVED,
    ACTION_CLAIMED,
    ACTION_EDITED,
    ACTION_FAILED,
    ACTION_REJECTED,
    ACTION_REQUESTED,
    ACTION_RESET,
    ACTION_TRANSLATED,
    ACTOR_WORKER,
    ALL_ACTIONS,
    log_translation_event,
)


def test_all_8_action_constants_defined():
    """Verify all 8 expected audit action constants exist."""
    expected = {
        "result_presentation.requested",
        "result_presentation.claimed",
        "result_presentation.translated",
        "result_presentation.failed",
        "result_presentation.approved",
        "result_presentation.rejected",
        "result_presentation.edited",
        "result_presentation.reset",
    }
    assert ALL_ACTIONS == expected
    assert len(ALL_ACTIONS) == 8


@pytest.mark.anyio
async def test_log_translation_event_worker_actor():
    """Worker actor gets actor_role='system'."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()

    with patch("services.translation_audit.AuditRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        MockRepo.return_value = mock_repo_instance

        await log_translation_event(
            session,
            tenant_id=tenant_id,
            deal_id=deal_id,
            action=ACTION_TRANSLATED,
            actor=ACTOR_WORKER,
            details={"locale": "en", "duration_ms": 120},
        )

        MockRepo.assert_called_once_with(session)
        mock_repo_instance.log.assert_awaited_once_with(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.translated",
            actor="system:translation_worker",
            actor_role="system",
            details={"locale": "en", "duration_ms": 120},
        )


@pytest.mark.anyio
async def test_log_translation_event_user_actor():
    """User actor gets actor_role='user'."""
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    deal_id = uuid.uuid4()

    with patch("services.translation_audit.AuditRepository") as MockRepo:
        mock_repo_instance = AsyncMock()
        MockRepo.return_value = mock_repo_instance

        await log_translation_event(
            session,
            tenant_id=tenant_id,
            deal_id=deal_id,
            action=ACTION_REQUESTED,
            actor="lawyer@example.com",
            details={"locale": "de"},
        )

        mock_repo_instance.log.assert_awaited_once_with(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.requested",
            actor="lawyer@example.com",
            actor_role="user",
            details={"locale": "de"},
        )


@pytest.mark.anyio
async def test_log_translation_event_invalid_action_raises():
    """Unknown action raises ValueError."""
    session = AsyncMock()

    with pytest.raises(ValueError, match="Unknown translation audit action"):
        await log_translation_event(
            session,
            tenant_id=uuid.uuid4(),
            deal_id=uuid.uuid4(),
            action="result_presentation.unknown_custom_action",
            actor="user",
            details={},
        )
