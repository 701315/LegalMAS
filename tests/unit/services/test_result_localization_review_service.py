"""
Unit tests for ResultLocalizationReviewService — Sprint 6.1

Covers:
- approve / reject / edit / reset transitions
- state machine validation (ReviewStateError)
- reject-requires-comment enforcement
- original translation snapshot on first edit
- audit log entries with tenant_id and deal_id
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.result_localization_review_service import (
    ResultLocalizationReviewService,
    ReviewStateError,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_presentation(
    *,
    presentation_id: uuid.UUID | None = None,
    status: str = "ready",
    locale: str = "en",
    localized_check_name: str | None = "LLM Check Name",
    display_text: str | None = "LLM display text",
    review_message: str | None = "LLM review message",
    dd_request_text: str | None = None,
    original_snapshot: dict | None = None,
) -> MagicMock:
    p = MagicMock()
    p.id = presentation_id or uuid.uuid4()
    p.translation_status = status
    p.locale = locale
    p.localized_check_name = localized_check_name
    p.display_text = display_text
    p.review_message = review_message
    p.dd_request_text = dd_request_text
    p.original_translation_snapshot = original_snapshot
    p.human_override_text = None
    p.reviewed_by = None
    p.reviewed_at = None
    p.approved_by = None
    p.approved_at = None
    p.review_comment = None
    p.error_message = None
    return p


def _make_session(presentation: MagicMock) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = presentation
    result.fetchone.return_value = (uuid.uuid4(), uuid.uuid4())
    session.execute.return_value = result
    return session


# ── Approve ──────────────────────────────────────────────────────────

class TestApproveTranslation:

    @pytest.mark.anyio
    async def test_approve_from_ready(self):
        p = _make_presentation(status="ready")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.approve_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
                comment="Looks good",
            )

        assert result.translation_status == "approved"
        assert result.approved_by is not None
        assert result.approved_at is not None
        assert result.review_comment == "Looks good"
        svc.audit_repo.log.assert_awaited_once()

    @pytest.mark.anyio
    async def test_approve_from_reviewed(self):
        p = _make_presentation(status="reviewed")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.approve_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
            )

        assert result.translation_status == "approved"

    @pytest.mark.anyio
    async def test_approve_from_pending_raises(self):
        p = _make_presentation(status="pending")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)

        with pytest.raises(ReviewStateError, match="Cannot transition"):
            await svc.approve_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
            )


# ── Reject ───────────────────────────────────────────────────────────

class TestRejectTranslation:

    @pytest.mark.anyio
    async def test_reject_from_ready(self):
        p = _make_presentation(status="ready")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.reject_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
                comment="Wrong legal terminology",
            )

        assert result.translation_status == "rejected"
        assert result.review_comment == "Wrong legal terminology"
        svc.audit_repo.log.assert_awaited_once()

    @pytest.mark.anyio
    async def test_reject_empty_comment_raises(self):
        p = _make_presentation(status="ready")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)

        with pytest.raises(ValueError, match="mandatory"):
            await svc.reject_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
                comment="   ",
            )

    @pytest.mark.anyio
    async def test_reject_none_comment_raises(self):
        p = _make_presentation(status="ready")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)

        with pytest.raises(ValueError, match="mandatory"):
            await svc.reject_translation(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="reviewer@example.com",
                comment=None,
            )


# ── Edit ─────────────────────────────────────────────────────────────

class TestEditTranslationOverride:

    @pytest.mark.anyio
    async def test_edit_creates_snapshot_on_first_edit(self):
        p = _make_presentation(
            status="ready",
            display_text="LLM original",
            localized_check_name="LLM Name",
        )
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.edit_translation_override(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="editor@example.com",
                display_text="Human corrected",
                comment="Fixed term",
            )

        assert result.translation_status == "reviewed"
        assert result.display_text == "Human corrected"
        assert result.original_translation_snapshot is not None
        assert result.original_translation_snapshot["display_text"] == "LLM original"
        assert result.original_translation_snapshot["localized_check_name"] == "LLM Name"
        assert result.human_override_text is not None
        assert result.human_override_text["display_text"] == "Human corrected"

    @pytest.mark.anyio
    async def test_edit_preserves_snapshot_on_second_edit(self):
        first_snapshot = {
            "localized_check_name": "Original LLM",
            "display_text": "Original text",
            "review_message": None,
            "dd_request_text": None,
        }
        p = _make_presentation(
            status="reviewed",
            display_text="First edit",
            original_snapshot=first_snapshot,
        )
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.edit_translation_override(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="editor@example.com",
                display_text="Second edit",
            )

        # Snapshot must remain from the FIRST edit
        assert result.original_translation_snapshot["display_text"] == "Original text"
        assert result.display_text == "Second edit"

    @pytest.mark.anyio
    async def test_edit_from_pending_raises(self):
        p = _make_presentation(status="pending")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)

        with pytest.raises(ReviewStateError):
            await svc.edit_translation_override(
                presentation_id=p.id,
                user_id=uuid.uuid4(),
                user_email="editor@example.com",
                display_text="Nope",
            )


# ── Reset ────────────────────────────────────────────────────────────

class TestResetToPending:

    @pytest.mark.anyio
    async def test_reset_from_rejected(self):
        p = _make_presentation(status="rejected")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)
        svc.audit_repo = AsyncMock()

        with patch(
            "services.result_localization_review_service.get_presentation_audit_context",
            new=AsyncMock(return_value=(uuid.uuid4(), uuid.uuid4())),
        ):
            result = await svc.reset_to_pending(
                presentation_id=p.id,
                user_email="admin@example.com",
            )

        assert result.translation_status == "pending"
        assert result.error_message is None

    @pytest.mark.anyio
    async def test_reset_from_ready_raises(self):
        p = _make_presentation(status="ready")
        session = _make_session(p)
        svc = ResultLocalizationReviewService(session)

        with pytest.raises(ReviewStateError):
            await svc.reset_to_pending(
                presentation_id=p.id,
                user_email="admin@example.com",
            )
