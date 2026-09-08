"""
Integration tests for translation review API endpoints (Sprint 6.2).

Verifies payload validation, HTTP status codes, security bypass mocks,
and state machine exception translation to 409 Conflicts.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient

from api.deps.auth import get_current_user
from api.endpoints.localization_review import router as review_router
from db.session import get_db
from services.result_localization_review_service import ReviewStateError


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(review_router, prefix="/api/v1")

    # Переопределяем зависимости безопасности для изоляции тестов API
    async def override_get_db():
        yield AsyncMock()

    async def override_get_current_user():
        return MagicMock(
            id=uuid.uuid4(),
            email="api.editor@steloom.com",
            ui_locale="en",
        )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return app


@pytest.mark.anyio
async def test_approve_endpoint_success(test_app):
    presentation_id = uuid.uuid4()
    mock_presentation = MagicMock(
        id=presentation_id,
        translation_status="approved",
        locale="en",
        reviewed_by=uuid.uuid4(),
        reviewed_at=None,
        approved_by=uuid.uuid4(),
        approved_at=None,
        review_comment="Approved via API",
        human_override_text=None,
        original_translation_snapshot=None,
    )

    # Мокаем проверку ролей и вызовы сервиса
    with (
        patch("api.endpoints.localization_review._resolve_deal_and_check_access", new_callable=AsyncMock),
        patch(
            "services.result_localization_review_service.ResultLocalizationReviewService.approve_translation",
            new_callable=AsyncMock,
            return_value=mock_presentation,
        ) as mock_approve,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/localization-review/{presentation_id}/approve",
                json={"comment": "Approved via API"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["presentation_id"] == str(presentation_id)
        assert data["translation_status"] == "approved"
        assert data["review_comment"] == "Approved via API"
        mock_approve.assert_called_once()


@pytest.mark.anyio
async def test_approve_endpoint_conflict_on_invalid_transition(test_app):
    presentation_id = uuid.uuid4()

    with (
        patch("api.endpoints.localization_review._resolve_deal_and_check_access", new_callable=AsyncMock),
        patch(
            "services.result_localization_review_service.ResultLocalizationReviewService.approve_translation",
            new_callable=AsyncMock,
            side_effect=ReviewStateError("Cannot transition from pending to approved"),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/localization-review/{presentation_id}/approve",
                json={"comment": "Won't work"},
            )

        # Ошибка бизнес-логики (неверный переход статуса) должна возвращать 409 Conflict
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Cannot transition" in response.json()["detail"]


@pytest.mark.anyio
async def test_reject_endpoint_requires_non_empty_comment(test_app):
    presentation_id = uuid.uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            f"/api/v1/localization-review/{presentation_id}/reject",
            json={"comment": "   "},  # Пустой комментарий после нормализации
        )

    # Должно вернуть 422 Unprocessable Entity
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_edit_endpoint_success(test_app):
    presentation_id = uuid.uuid4()
    mock_presentation = MagicMock(
        id=presentation_id,
        translation_status="reviewed",
        locale="fr",
        reviewed_by=uuid.uuid4(),
        reviewed_at=None,
        approved_by=None,
        approved_at=None,
        review_comment="API Edit",
        human_override_text={"display_text": "Modified Text"},
        original_translation_snapshot={"display_text": "Original LLM"},
    )

    with (
        patch("api.endpoints.localization_review._resolve_deal_and_check_access", new_callable=AsyncMock),
        patch(
            "services.result_localization_review_service.ResultLocalizationReviewService.edit_translation_override",
            new_callable=AsyncMock,
            return_value=mock_presentation,
        ) as mock_edit,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/localization-review/{presentation_id}/edit",
                json={
                    "display_text": "Modified Text",
                    "comment": "API Edit",
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["translation_status"] == "reviewed"
        assert data["has_human_override"] is True
        assert data["has_original_snapshot"] is True
        mock_edit.assert_called_once()


@pytest.mark.anyio
async def test_reset_endpoint_success(test_app):
    presentation_id = uuid.uuid4()
    mock_presentation = MagicMock(
        id=presentation_id,
        translation_status="pending",
        locale="en",
        reviewed_by=None,
        reviewed_at=None,
        approved_by=None,
        approved_at=None,
        review_comment=None,
        human_override_text=None,
        original_translation_snapshot=None,
    )

    with (
        patch("api.endpoints.localization_review._resolve_deal_and_check_access", new_callable=AsyncMock),
        patch(
            "services.result_localization_review_service.ResultLocalizationReviewService.reset_to_pending",
            new_callable=AsyncMock,
            return_value=mock_presentation,
        ) as mock_reset,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as ac:
            response = await ac.post(
                f"/api/v1/localization-review/{presentation_id}/reset"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["translation_status"] == "pending"
        mock_reset.assert_called_once()
